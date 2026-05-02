# 10 · Self-Evolution Loop Spec
**DroneFleet · MongoDB Agentic Evolution Hackathon**

> Cross-references: `02-mongodb-data-model.md`, `04-langchain-agents.md`,
> `05-state-recovery.md`, `06-skills-discovery.md`, `08-evaluation.md`,
> `09-frontend.md`, `11-demo-script.md`, `12-acceptance-tests.md`.

This is the **centrepiece of the Creativity score**. Without a working
self-evolution loop the submission is a generic agent demo. With it, judges
literally watch the system grow smarter on stage during the encore run.

The architecture is deliberately conservative: every "learning" step is
durably persisted to MongoDB, every retrieved lesson cites its provenance,
and every claim of improvement is measured by an automated harness.

---

## 1 · `ReflectionAgent` Design

### 1.1 Trigger

Runs **after every mission terminus** (success OR fail) — invoked by
`SupervisorAgent` as the last specialist before `__end__` (see
`04-langchain-agents.md §1.3`). Also runs after **synthetic** missions
generated overnight by `DemandForecastAgent` (§10).

### 1.2 Inputs

* The full `missions` doc (status, plan, outcome, timing).
* Every `agent_messages` row for `mission_id`.
* Every `anomalies` event collected during flight.
* The original `parsed_task` and the actual route flown.
* Planned-vs-actual delta object (computed before invocation):

  ```python
  delta = {
      "eta_delta_s":     actual.eta_s - plan.eta_s,
      "distance_delta_m": actual.distance_m - plan.distance_m,
      "reroute_count":   len(actual.reroutes),
      "preflight_warnings": preflight.report.warnings,
      "geofence_violations": list(geofence.events),
      "weather_events":  weather.during_flight,
      "vision_events":   vision.detections,
      "battery_min_pct": min(t.battery_pct for t in telemetry),
      "payload_temp_breaches": payload.breaches,
  }
  ```

### 1.3 Output — `Reflection` Pydantic

```python
# dronefleet/agents/reflection_models.py
from typing import Literal, Optional
from pydantic import BaseModel, Field
from datetime import datetime

LessonKind = Literal[
    "corridor_avoidance", "weather_threshold", "payload_constraint",
    "regulation_clarification", "facility_quirk",
    "agent_underperformance", "tool_failure_pattern",
    "operator_preference",
]

class Lesson(BaseModel):
    kind: LessonKind
    summary: str = Field(..., max_length=600)
    region: Optional[str] = None
    weather_class: Optional[str] = None
    success: bool
    severity: Literal["info", "advice", "hard_block"] = "advice"
    evidence_message_ids: list[str] = []   # provenance: agent_messages._id refs
    proposed_action: Optional[str] = None  # planner-readable hint

class SkillUpdate(BaseModel):
    agent_name: str
    delta: float = Field(..., ge=-0.2, le=0.2)   # bounded EWMA delta
    reason: str

class Reflection(BaseModel):
    mission_id: str
    summary: str
    lessons: list[Lesson]
    causes: list[str]
    proposed_skill_updates: list[SkillUpdate]
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    signature: str = ""    # HMAC; see §12 anti-poisoning
```

### 1.4 System prompt (verbatim, ~330 words)

```text
You are the Reflection Agent. You write durable lessons that the rest of the
fleet will retrieve in future missions. Your output is consumed by the
PlannerAgent, the SupervisorAgent (for skill scoring), and the operator-
facing Reflection Feed in the dashboard.

Inputs you will receive:
  - The mission doc (request, plan, outcome, timing).
  - All agent_messages for the mission, in order.
  - Anomalies, geofence violations, weather events, vision detections.
  - A planned-vs-actual delta object.

You MUST follow these rules:

1. Write lessons that are SPECIFIC and ACTIONABLE. Bad lesson: "weather was
   bad". Good lesson: "wind > 22 kt above 80 m AGL near the Thames Estuary
   corridor caused a battery overspend; PlannerAgent should set
   weather_penalty >= 0.7 in that corridor when forecast 10-m wind exceeds
   18 kt".

2. Each lesson MUST cite at least one agent_messages._id (or anomaly._id)
   as evidence. No evidence → no lesson. This is the anti-hallucination
   guardrail.

3. Choose `severity` carefully:
   - "info"       — interesting but not action-relevant.
   - "advice"     — PlannerAgent should weight this in, soft.
   - "hard_block" — corridor / time / weather window must be excluded.
   You may emit at most ONE hard_block per mission. Hard-blocks require
   the planner to also see at least one corroborating prior lesson before
   acting (anti-overfitting; the planner enforces this).

4. Lesson kinds (taxonomy of 8):
     corridor_avoidance, weather_threshold, payload_constraint,
     regulation_clarification, facility_quirk, agent_underperformance,
     tool_failure_pattern, operator_preference.

5. Skill updates:
   - Use the planned-vs-actual delta + the per-agent latency / retry
     stats to assign each contributing agent a delta in [-0.2, +0.2].
   - Reward agents whose tool calls had attempt==1 and zero retries.
   - Penalise agents whose outputs were rejected by ValidationLayer.

6. Output a STRICT JSON Reflection object. Do not include markdown.

7. If the mission failed, you MUST output at least one lesson with kind
   `tool_failure_pattern` or `agent_underperformance` explaining the
   proximate cause (do not blame "the operator" — that is out-of-scope).

You will be evaluated on whether downstream missions that retrieve your
lessons measurably improve. Useless lessons get demoted (usefulness_score
< 0.2 after 5 retrievals → deprecated).
```

### 1.5 The node implementation

```python
# dronefleet/agents/nodes/reflection_node.py
import hmac, hashlib, json
from datetime import datetime
from dronefleet.agents.reflection_models import Reflection
from dronefleet.embed import voyage_embed
from dronefleet.db import db
from dronefleet.config import REFLECTION_HMAC_KEY

REFL_SYSTEM = open("dronefleet/agents/prompts/reflection.txt").read()

async def reflection_node(state):
    mid = state["mission_id"]
    mission   = await db.missions.find_one({"_id": mid})
    messages  = await db.agent_messages.find({"mission_id": mid}).sort("timestamp", 1).to_list(None)
    anomalies = state.get("anomalies", [])
    delta     = await compute_delta(mid)

    prompt = build_reflection_prompt(REFL_SYSTEM, mission, messages, anomalies, delta)
    raw    = await reflection_llm.ainvoke(prompt)
    reflection = Reflection.model_validate_json(raw.content)
    reflection.signature = _sign(reflection)

    await persist_reflection(reflection, mission)
    await update_agent_skills(reflection.proposed_skill_updates)
    return {"reflection": reflection.model_dump()}

def _sign(refl: Reflection) -> str:
    body = refl.model_dump_json(exclude={"signature"}).encode()
    return hmac.new(REFLECTION_HMAC_KEY.encode(), body, hashlib.sha256).hexdigest()
```

---

## 2 · Lesson Taxonomy (the 8 `kind`s)

| `kind`                    | Trigger                                               | Example summary                                              |
|---------------------------|-------------------------------------------------------|--------------------------------------------------------------|
| `corridor_avoidance`      | Reroute caused by airspace/obstacle in a known leg    | "Avoid Thames Estuary corridor 80–120 m AGL on SW winds >18 kt." |
| `weather_threshold`       | Anomaly correlated with weather variable              | "Below 5 °C, battery EOD margin must be ≥25 %."              |
| `payload_constraint`      | Cold-chain breach or temperature-sensitive payload    | "Vaccines: cap leg duration at 14 min in ambient >24 °C."    |
| `regulation_clarification`| CAA / facility rule discovered or re-confirmed       | "Clinic D: only one approach (south) per CAA NOTAM 2026-09." |
| `facility_quirk`          | Site-specific operational fact                        | "Clinic A roof helipad blocked by HVAC unit 12:00–13:00."    |
| `agent_underperformance`  | A specific agent's reliability dropped                | "InterpreterAgent confidence < 0.6 on synonym 'plasma'."     |
| `tool_failure_pattern`    | A tool deterministically fails on a class of inputs   | "solve_vrp infeasible when battery_wh < 130 and stops > 4."  |
| `operator_preference`     | Operator-explicit preference revealed by escalations  | "Operator J. Lee prefers verbal confirmation before payload release." |

Each lesson becomes a `mission_memory` doc — schema in §3.

---

## 3 · Embedding & Writing Lessons

```python
# dronefleet/agents/persist.py
from datetime import datetime
from dronefleet.embed import voyage_embed
from dronefleet.db import db

EPOCH = datetime(1970, 1, 1)
def recency_bucket(d: datetime) -> int:
    return (d - EPOCH).days // 7

async def persist_reflection(refl: "Reflection", mission: dict):
    region = mission.get("region", "unknown")
    weather_class = mission.get("weather_class", "unknown")
    success = mission.get("status") == "completed"

    docs = []
    for lesson in refl.lessons:
        text = f"[{lesson.kind}] {lesson.summary}"
        emb  = await voyage_embed(text)
        docs.append({
            "_id": f"lsn-{mission['_id']}-{lesson.kind}-{hash(lesson.summary) & 0xffffffff:x}",
            "kind": lesson.kind,
            "summary": lesson.summary,
            "embedding": emb,
            "metadata": {
                "mission_id": mission["_id"],
                "region": lesson.region or region,
                "weather_class": lesson.weather_class or weather_class,
                "success": lesson.success and success,
                "severity": lesson.severity,
                "recency_decay_bucket": recency_bucket(datetime.utcnow()),
                "evidence_message_ids": lesson.evidence_message_ids,
                "signature": refl.signature,
                "deprecated": False,
                "retrieval_count": 0,
                "usefulness_score": 0.5,        # neutral prior
            },
            "created_at": datetime.utcnow(),
        })
    if docs:
        await db.mission_memory.insert_many(docs, ordered=False)
```

### 3.1 Atlas Vector Search index (must be in `02-mongodb-data-model.md §5`)

```json
{
  "name": "mission_memory_vec",
  "type": "vectorSearch",
  "fields": [
    {"path": "embedding", "type": "vector",
     "numDimensions": 1024, "similarity": "cosine"},
    {"path": "kind", "type": "filter"},
    {"path": "metadata.region", "type": "filter"},
    {"path": "metadata.weather_class", "type": "filter"},
    {"path": "metadata.deprecated", "type": "filter"},
    {"path": "metadata.severity", "type": "filter"}
  ]
}
```

### 3.2 Standard indexes

```python
await db.mission_memory.create_index([("kind", 1), ("metadata.region", 1)])
await db.mission_memory.create_index([("metadata.usefulness_score", -1)])
await db.mission_memory.create_index([("metadata.recency_decay_bucket", -1)])
await db.mission_memory.create_index(
    [("metadata.deprecated", 1), ("metadata.recency_decay_bucket", 1)],
    name="reaper_scan",
)
```

---

## 4 · Retrieval Feedback Loop

Every time PlannerAgent (or any other agent) retrieves a lesson, the lesson's
`retrieval_count` increments. When the downstream mission terminates the
ReflectionAgent decides whether each retrieved lesson contributed
positively, and updates its `usefulness_score`.

### 4.1 Retrieval increments

```python
# dronefleet/memory/lessons.py
async def retrieve_lessons_for_planner(query: str, region: str | None,
                                       weather_class: str | None,
                                       k: int = 5) -> list[dict]:
    qvec = await voyage_embed(query)
    pipeline = [
        {"$vectorSearch": {
            "index": "mission_memory_vec",
            "path":  "embedding",
            "queryVector": qvec,
            "numCandidates": 64, "limit": k,
            "filter": {
                "metadata.deprecated": {"$ne": True},
                **({"metadata.region": region} if region else {}),
                **({"metadata.weather_class": weather_class} if weather_class else {}),
            },
        }},
        {"$project": {
            "kind": 1, "summary": 1, "metadata": 1,
            "score": {"$meta": "vectorSearchScore"},
        }},
    ]
    lessons = [d async for d in db.mission_memory.aggregate(pipeline)]
    if lessons:
        await db.mission_memory.update_many(
            {"_id": {"$in": [l["_id"] for l in lessons]}},
            {"$inc": {"metadata.retrieval_count": 1}},
        )
    return lessons
```

### 4.2 Usefulness update (post-mission)

EWMA on a 0–1 scale:

```python
# dronefleet/agents/feedback.py
ALPHA = 0.3

async def update_lesson_usefulness(mission_id: str, success: bool):
    cited = await db.agent_messages.distinct(
        "payload.lessons_used", {"mission_id": mission_id, "from_agent": "planner"},
    )
    if not cited:
        return
    contribution = 1.0 if success else 0.0
    async for l in db.mission_memory.find({"_id": {"$in": cited}}):
        new = (1 - ALPHA) * l["metadata"]["usefulness_score"] + ALPHA * contribution
        await db.mission_memory.update_one(
            {"_id": l["_id"]},
            {"$set": {"metadata.usefulness_score": new}},
        )
```

### 4.3 Demotion of low-usefulness lessons

```python
async def demote_useless_lessons():
    await db.mission_memory.update_many(
        {
            "metadata.retrieval_count": {"$gte": 5},
            "metadata.usefulness_score": {"$lt": 0.2},
            "metadata.deprecated": False,
        },
        {"$set": {"metadata.deprecated": True,
                  "metadata.deprecated_at": datetime.utcnow()}},
    )
```

Run this nightly (Mongo `cron` or APScheduler in `dronefleet.jobs`).

---

## 5 · Skill Score Updates (EWMA)

```python
# dronefleet/agents/skill_scoring.py
from datetime import datetime
EWMA_ALPHA = 0.25

async def update_agent_skills(updates: list["SkillUpdate"]):
    for u in updates:
        agent = await db.agent_skills.find_one({"agent_name": u.agent_name})
        if not agent:
            continue
        old = agent.get("reliability_score", 0.7)
        # u.delta is bounded by ReflectionAgent prompt to [-0.2, +0.2]
        new = max(0.0, min(1.0, (1 - EWMA_ALPHA) * old + EWMA_ALPHA * (old + u.delta)))
        await db.agent_skills.update_one(
            {"_id": agent["_id"]},
            {"$set": {
                "reliability_score": new,
                "last_updated": datetime.utcnow(),
            },
             "$push": {"score_history": {
                 "ts": datetime.utcnow(),
                 "old": old, "new": new, "reason": u.reason,
             }}},
        )
```

The Supervisor's peer-discovery rerank uses `reliability_score` directly —
see `04-langchain-agents.md §3.3`.

---

## 6 · Self-Improvement Evaluation Harness

The single most important file for proving Self-Evolution to the judges.

### 6.1 `eval/self_evolution_runner.py`

```python
# eval/self_evolution_runner.py
"""
Run the same scenario N times against:
  (A) a fresh-seeded cluster (no mission_memory)
  (B) an accumulated-memory cluster (mission_memory persists)
Report per-take metrics; assert measurable improvement.
"""
from __future__ import annotations
import asyncio, json, statistics, time
from dataclasses import dataclass, asdict
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from dronefleet.agents.graph import compile_graph
from dronefleet.state.checkpointer import thread_config
from dronefleet.config import MONGO_URI

@dataclass
class TakeResult:
    scenario_id: str
    take_n: int
    actual_time_s: float
    actual_distance_m: int
    reroute_count: int
    success: bool
    lessons_added: int
    lessons_used: int

async def reset_memory(client):
    await client.dronefleet.mission_memory.delete_many({})
    await client.dronefleet.lesson_seeds.delete_many({})

async def run_scenario_once(scenario: dict, take_n: int, graph) -> TakeResult:
    mission_id = f"eval-{scenario['id']}-take{take_n}-{int(time.time())}"
    initial_state = {
        "mission_id": mission_id,
        "operator_id": "eval-harness",
        "request": scenario["request"],
        "started_at": datetime.utcnow(),
    }
    t0 = time.perf_counter()
    final = await graph.ainvoke(initial_state, config=thread_config(mission_id))
    t1 = time.perf_counter()

    # Pull metrics out of Mongo.
    db = graph.checkpointer.client.dronefleet
    mission = await db.missions.find_one({"_id": mission_id})
    rerouts = await db.agent_messages.count_documents(
        {"mission_id": mission_id, "from_agent": "replanner"},
    )
    lessons_added = await db.mission_memory.count_documents(
        {"metadata.mission_id": mission_id},
    )
    lessons_used_msgs = await db.agent_messages.find(
        {"mission_id": mission_id, "from_agent": "planner",
         "payload.lessons_used": {"$exists": True}},
    ).to_list(None)
    lessons_used = sum(len(m["payload"].get("lessons_used", []))
                       for m in lessons_used_msgs)

    return TakeResult(
        scenario_id=scenario["id"], take_n=take_n,
        actual_time_s=mission.get("actual_time_s", t1 - t0),
        actual_distance_m=mission.get("actual_distance_m", 0),
        reroute_count=rerouts,
        success=mission.get("status") == "completed",
        lessons_added=lessons_added,
        lessons_used=lessons_used,
    )

async def run_with_memory(scenario: dict, n: int) -> list[TakeResult]:
    client = AsyncIOMotorClient(MONGO_URI)
    await reset_memory(client)
    graph = compile_graph(MONGO_URI)
    results = []
    for i in range(1, n + 1):
        r = await run_scenario_once(scenario, take_n=i, graph=graph)
        results.append(r)
        # Persist eval row.
        await client.dronefleet.reflection_eval.insert_one(asdict(r))
    return results

async def run_without_memory(scenario: dict, n: int) -> list[TakeResult]:
    client = AsyncIOMotorClient(MONGO_URI)
    graph = compile_graph(MONGO_URI)
    results = []
    for i in range(1, n + 1):
        await reset_memory(client)        # wipe BETWEEN takes
        r = await run_scenario_once(scenario, take_n=i, graph=graph)
        results.append(r)
    return results

async def main():
    scenario = json.load(open("eval/scenarios/airport_corridor_storm.json"))
    with_mem    = await run_with_memory(scenario, n=5)
    without_mem = await run_without_memory(scenario, n=5)
    print("WITH MEMORY:")
    for r in with_mem:    print(" ", r)
    print("WITHOUT MEMORY:")
    for r in without_mem: print(" ", r)
    return with_mem, without_mem

if __name__ == "__main__":
    asyncio.run(main())
```

### 6.2 Pytest assertion

```python
# tests/eval/test_self_evolution_improves.py
import asyncio, pytest, json
from eval.self_evolution_runner import run_with_memory

@pytest.mark.slow
@pytest.mark.asyncio
async def test_n5_better_than_n1():
    scenario = json.load(open("eval/scenarios/airport_corridor_storm.json"))
    runs = await run_with_memory(scenario, n=5)
    run_1, *_, run_n = runs
    assert run_n.actual_time_s < run_1.actual_time_s * 0.9, (
        f"Expected ≥10% time improvement; got {run_1.actual_time_s:.1f}s → "
        f"{run_n.actual_time_s:.1f}s"
    )
    assert run_n.reroute_count <= run_1.reroute_count, (
        "Reroute count should not regress with accumulated memory."
    )
    assert run_n.success, "Final take must succeed."
```

A `--without-mem` companion test asserts the no-memory baseline does
**not** improve, isolating the benefit to memory-driven self-evolution
rather than environmental noise.

---

## 7 · Live Demo Hook — Reflection Feed

The dashboard's **Reflection Feed** subscribes via WebSocket to a Mongo
Change Stream filtered to `kind:"reflection"` writes. Judges literally
watch lessons appear during the demo.

### 7.1 Server side

```python
# dronefleet/api/reflection_feed.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from dronefleet.db import db
import asyncio, json
router = APIRouter()

@router.websocket("/ws/reflections")
async def reflections_feed(ws: WebSocket):
    await ws.accept()
    pipeline = [{"$match": {"operationType": "insert"}}]
    try:
        async with db.mission_memory.watch(pipeline,
                                           full_document="updateLookup") as stream:
            async for change in stream:
                doc = change["fullDocument"]
                await ws.send_text(json.dumps({
                    "_id": str(doc["_id"]),
                    "kind": doc["kind"],
                    "summary": doc["summary"],
                    "metadata": {
                        "region": doc["metadata"].get("region"),
                        "severity": doc["metadata"].get("severity"),
                        "mission_id": doc["metadata"].get("mission_id"),
                    },
                    "created_at": doc["created_at"].isoformat(),
                }))
    except WebSocketDisconnect:
        return
```

### 7.2 Front-end (recharts panel — see `09-frontend.md`)

Renders each new lesson as a card sliding in from the right; the
"usefulness_score" badge updates live as downstream missions cite it.

---

## 8 · Self-Tuning Planner

PlannerAgent's prompt template includes a Jinja section for retrieved
lessons. Over time the planner avoids previously-failed corridors **but
only when ≥2 corroborating lessons exist** (anti-overfitting).

### 8.1 Prompt template

```jinja
{# dronefleet/agents/prompts/planner.j2 #}
You are the Planner. Your combinatorial work is delegated to solve_vrp.
You decide heuristic, weights, and excluded_legs.

Mission context:
- Operator request: {{ request }}
- Locations:        {{ locations | join(", ") }}
- Region:           {{ region }}
- Weather class:    {{ weather_class }}
- Cold-chain:       {{ cold_chain }}

Retrieved lessons (top {{ lessons|length }}, sorted by score):
{% for lsn in lessons %}
  - [{{ lsn.kind }} · severity={{ lsn.metadata.severity }} · used={{ lsn.metadata.retrieval_count }} · usefulness={{ '%.2f' % lsn.metadata.usefulness_score }}]
    {{ lsn.summary }}
    (provenance: mission {{ lsn.metadata.mission_id }})
{% endfor %}

{% if hard_block_corridors %}
HARD-BLOCK corridors (≥2 corroborating hard_block lessons):
{% for c in hard_block_corridors %}
  - {{ c }}
{% endfor %}
{% endif %}

Decide:
1) heuristic ∈ {PATH_CHEAPEST_ARC, SAVINGS, GUIDED_LOCAL_SEARCH}
2) weights {priority, weather, geofence, payload_temp}
3) excluded_legs (list of leg ids)

Output strict JSON: {"heuristic": ..., "weights": {...}, "excluded_legs": [...]}.
```

### 8.2 Hard-block corroboration logic

```python
# dronefleet/memory/hard_blocks.py
async def hard_block_corridors_for(region: str) -> list[str]:
    pipeline = [
        {"$match": {
            "kind": "corridor_avoidance",
            "metadata.region": region,
            "metadata.severity": "hard_block",
            "metadata.deprecated": {"$ne": True},
        }},
        {"$group": {
            "_id": "$metadata.corridor_id",   # set by ReflectionAgent
            "n":   {"$sum": 1},
            "max_score": {"$max": "$metadata.usefulness_score"},
        }},
        {"$match": {"n": {"$gte": 2}, "max_score": {"$gte": 0.5}}},
    ]
    return [d["_id"] async for d in db.mission_memory.aggregate(pipeline)]
```

This is injected into the planner prompt's `hard_block_corridors` list.

---

## 9 · Anti-Overfitting Guardrails

### 9.1 Single-lesson cap on hard-blocks

Already enforced by §8.2 (`n >= 2`).

### 9.2 Periodic "exploration" missions

10 % of missions ignore the top-1 retrieved lesson (so the system can
discover when an obsolete lesson should be demoted faster).

```python
# dronefleet/jobs/exploration_scheduler.py
import random
EXPLORATION_RATE = 0.1

async def maybe_drop_top_lesson(lessons: list[dict]) -> list[dict]:
    if lessons and random.random() < EXPLORATION_RATE:
        dropped = lessons[0]
        await db.exploration_log.insert_one({
            "lesson_id": dropped["_id"],
            "dropped_at": datetime.utcnow(),
        })
        return lessons[1:]
    return lessons
```

### 9.3 Aggregation: which lessons to schedule for exploration

Pick lessons with high `retrieval_count` and stable `usefulness_score`:

```python
EXPLORATION_PIPELINE = [
    {"$match": {"metadata.deprecated": {"$ne": True},
                "metadata.retrieval_count": {"$gte": 10}}},
    {"$lookup": {
        "from": "exploration_log", "localField": "_id",
        "foreignField": "lesson_id", "as": "explored"}},
    {"$match": {"explored": {"$size": 0}}},
    {"$sort": {"metadata.retrieval_count": -1}},
    {"$limit": 25},
]
```

### 9.4 Re-embedding (drift mitigation)

Voyage upgrades or domain drift mean older embeddings can become stale.
Every 30 days, re-embed any lesson whose embedding model version differs
from the current one:

```python
async def reembed_drifted():
    cur = db.mission_memory.find({"embedding_model": {"$ne": CURRENT_MODEL}})
    async for doc in cur:
        new = await voyage_embed(f"[{doc['kind']}] {doc['summary']}")
        await db.mission_memory.update_one(
            {"_id": doc["_id"]},
            {"$set": {"embedding": new, "embedding_model": CURRENT_MODEL}},
        )
```

---

## 10 · Cross-Mission Curriculum (overnight synthetic learning)

DemandForecastAgent samples from `synthetic_emergencies` distributions and
runs the full graph for each — ReflectionAgent processes the synthetic
mission identically, growing the lesson base without real flights.

### 10.1 Pseudo-code

```python
# dronefleet/agents/nodes/demand_forecast_node.py
from dronefleet.agents.graph import compile_graph
from dronefleet.state.checkpointer import thread_config
from dronefleet.synthetic.distributions import sample_emergency

async def overnight_curriculum(n: int = 200):
    graph = compile_graph(MONGO_URI)
    for _ in range(n):
        scenario = sample_emergency()         # weighted draw
        mid = f"synthetic-{uuid.uuid4()}"
        state = {
            "mission_id": mid,
            "operator_id": "DemandForecastAgent",
            "request": scenario["natural_language"],
            "synthetic": True,
        }
        try:
            await graph.ainvoke(state, config=thread_config(mid))
        except Exception as e:
            log.warning("synthetic mission %s failed: %s", mid, e)
```

Synthetic missions are flagged (`synthetic: True`) so the reflection
agent knows to label proposed_skill_updates with lower magnitude
(synthetic evidence is less trusted than live evidence — the Reflection
prompt clamps `delta` for synthetic missions to `[-0.05, +0.05]`).

### 10.2 Schedule

A nightly cron in `dronefleet.jobs.scheduler` invokes
`overnight_curriculum(200)` between 02:00 and 04:00 local time. The job is
itself a LangGraph thread (`thread_id="curriculum-YYYY-MM-DD"`), so a
process restart resumes from the last completed scenario.

---

## 11 · Metrics Collection — `reflection_eval`

### 11.1 Schema

```json
{
  "_id": ObjectId,
  "scenario_id": "airport_corridor_storm",
  "take_n": 3,
  "actual_time_s": 184.2,
  "actual_distance_m": 11400,
  "reroute_count": 1,
  "success": true,
  "lessons_added": 2,
  "lessons_used": 4,
  "ts": ISODate
}
```

### 11.2 Aggregation pipeline for the front-end chart

```python
SELF_EVOLUTION_PIPELINE = [
    {"$match": {"scenario_id": {"$in": SCENARIO_IDS}}},
    {"$group": {
        "_id": {"scenario": "$scenario_id", "take": "$take_n"},
        "mean_time": {"$avg": "$actual_time_s"},
        "mean_dist": {"$avg": "$actual_distance_m"},
        "mean_rer":  {"$avg": "$reroute_count"},
        "succ_rate": {"$avg": {"$cond": ["$success", 1, 0]}},
        "lessons":   {"$avg": "$lessons_used"},
    }},
    {"$sort": {"_id.scenario": 1, "_id.take": 1}},
]
```

### 11.3 Recharts spec (front-end)

```tsx
// frontend/components/SelfEvolutionChart.tsx
<LineChart data={data}>
  <XAxis dataKey="take" label={{ value: "Take #", position: "insideBottom" }} />
  <YAxis yAxisId="left" label={{ value: "Time (s)", angle: -90 }} />
  <YAxis yAxisId="right" orientation="right"
         label={{ value: "Reroutes / Lessons", angle: 90 }} />
  <Tooltip />
  <Legend />
  <Line yAxisId="left"  dataKey="mean_time" stroke="#0ea5e9" strokeWidth={3} />
  <Line yAxisId="right" dataKey="mean_rer"  stroke="#ef4444" />
  <Line yAxisId="right" dataKey="lessons"   stroke="#22c55e" />
</LineChart>
```

The judges see the blue "Time" line bend down and the green "Lessons"
line tick up over takes 1 → 5. That is the headline visual.

---

## 12 · Failure Modes + Mitigations

### 12.1 Memory poisoning

**Risk:** A malicious or careless operator seeds bad lessons that derail
future missions.

**Mitigations:**
* Every lesson carries `metadata.signature` = HMAC over the canonical body
  using `REFLECTION_HMAC_KEY` (server-only). Lessons missing or failing
  signature verification are filtered out at retrieval time.
* `metadata.evidence_message_ids` must be non-empty and resolve to real
  rows in `agent_messages` for the lesson's `mission_id`. A nightly
  consistency job marks orphaned lessons as deprecated.
* Manual operator-authored lessons enter via a separate
  `operator_lessons` collection and only graduate to `mission_memory`
  after a human-in-the-loop approval (audit-trailed).

```python
async def verify_lesson(lesson: dict) -> bool:
    sig = lesson["metadata"]["signature"]
    body = json.dumps({k: lesson[k] for k in ("kind", "summary")} |
                      {"metadata": {k: v for k, v in lesson["metadata"].items()
                                    if k != "signature"}},
                      sort_keys=True, separators=(",", ":")).encode()
    expected = hmac.new(REFLECTION_HMAC_KEY.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)
```

### 12.2 Embedding drift

Re-embed every 30 days (§9.4). Track the active model version in
`embedding_model` per doc; the retriever filters out lessons embedded
with an unsupported version until they are refreshed.

### 12.3 Runaway memory growth

Per-region cap of 1000 active (non-deprecated) lessons; oldest are
deprecated when the cap is exceeded:

```python
async def cap_per_region(region: str, cap: int = 1000):
    excess = await db.mission_memory.count_documents(
        {"metadata.region": region, "metadata.deprecated": {"$ne": True}}
    ) - cap
    if excess <= 0: return
    # Deprecate oldest, lowest-usefulness first.
    cur = db.mission_memory.find(
        {"metadata.region": region, "metadata.deprecated": False},
    ).sort([("metadata.usefulness_score", 1),
            ("metadata.recency_decay_bucket", 1)]).limit(excess)
    ids = [d["_id"] async for d in cur]
    await db.mission_memory.update_many(
        {"_id": {"$in": ids}}, {"$set": {"metadata.deprecated": True}},
    )
```

Deprecated lessons get a Mongo TTL index (180 days) for hard delete:

```python
await db.mission_memory.create_index(
    "metadata.deprecated_at", expireAfterSeconds=180 * 86400,
    partialFilterExpression={"metadata.deprecated": True},
)
```

---

## 13 · Demo Walk-Through (the encore that wins judges)

This script ties to `11-demo-script.md §4` (the encore run).

### 13.1 Take 1 (cold cluster)

* Operator says: *"Send blood and vaccines to Clinic D urgently. Weather
  looks gusty."*
* Cluster has zero `mission_memory`. PlannerAgent picks
  `PATH_CHEAPEST_ARC`, `weather=0.4`. Route uses the Thames Estuary
  corridor at 100 m AGL.
* Mid-flight, Anomaly + Vision detect a **wind shear event** at 90 m AGL
  in the corridor. ReplannerAgent diverts (reroute_count=1). Mission
  completes but takes 240 s and consumes 35 % battery.
* ReflectionAgent writes:
  * `lsn-A` (corridor_avoidance, severity=advice, region=thames_estuary,
    weather_class=gusty) — "wind shear above 80 m AGL on SW winds >18 kt
    in Thames corridor".
  * `lsn-B` (weather_threshold) — "weather penalty should be ≥0.7 in this
    region when forecast 10-m wind > 18 kt".

### 13.2 Take 2 (memory exists)

* Same operator request.
* PlannerAgent retrieves `lsn-A` and `lsn-B` (top-2 by score).
  `weather_penalty` set to 0.7. Route still uses corridor but at 60 m
  AGL (below the shear band). One reroute due to a transient bird
  detection. Mission completes in 215 s.
* ReflectionAgent writes:
  * `lsn-C` (corridor_avoidance, severity=advice) — "60 m AGL is safe
    when 18-22 kt SW; AVOID 80-120 m" (cites `lsn-A` as evidence).
  * Updates `usefulness_score` of `lsn-A` and `lsn-B` upward (+0.10
    each via EWMA).

### 13.3 Take 3 (the on-stage encore)

* Same operator request.
* PlannerAgent retrieves `lsn-A`, `lsn-B`, `lsn-C` (now top-3, scores
  0.86 / 0.79 / 0.74). With 2 corroborating corridor_avoidance lessons,
  the planner emits `excluded_legs=[thames_corridor_80_120m]`. Heuristic
  switches to `GUIDED_LOCAL_SEARCH` (lesson `lsn-D` from a previous
  unrelated mission suggests it for >5-stop runs). New route uses the
  inland alternative; **zero** reroutes; completes in **170 s**, 22 %
  battery. **29 % faster than Take 1.**
* ReflectionAgent writes one new lesson (operator_preference) and the
  Reflection Feed lights up on the dashboard during the demo.

### 13.4 Specific lessons retrieved on Take 3 that weren't on Take 1

| Lesson id | kind                | retrieved Take 1 | retrieved Take 3 |
|-----------|---------------------|------------------|------------------|
| lsn-A     | corridor_avoidance  | NO               | YES              |
| lsn-B     | weather_threshold   | NO               | YES              |
| lsn-C     | corridor_avoidance  | NO               | YES              |
| lsn-D     | tool_failure_pattern| NO (not present) | YES (cross-domain transfer) |

The pytest assertion in §6.2 mechanises this: `actual_time(Take5) <
0.9 * actual_time(Take1)`.

---

## 14 · Acceptance criteria

* `pytest tests/eval/test_self_evolution_improves.py::test_n5_better_than_n1`
* `pytest tests/agents/test_reflection_agent.py::test_lessons_have_evidence`
* `pytest tests/memory/test_demote_useless_lessons.py`
* `pytest tests/memory/test_hard_block_requires_two.py`
* `pytest tests/security/test_lesson_signature.py`
* Live demo: Reflection Feed shows ≥1 new lesson within 5 s of mission
  completion; Take 3 of the encore scenario completes in ≤80 % of
  Take 1's wall-clock time on stage.

If all five tests pass and the demo encore lands the time-improvement
visual, this spec is satisfied — and the Creativity score is paid for in
full.
