# 04 · LangChain + LangGraph Agent Runtime Spec
**Droran · MongoDB Agentic Evolution Hackathon**

> Cross-references: `01-system-architecture.md`, `02-mongodb-data-model.md`,
> `03-realtime-voice.md`, `05-state-recovery.md`, `06-skills-discovery.md`,
> `10-self-evolution.md`, `11-demo-script.md`, `12-acceptance-tests.md`.

This document is the canonical specification for the agent runtime. It must
answer four questions and prove the answer in code:

1. **How do agents convey their skills?** → Each agent self-registers a typed
   capability descriptor into `agent_skills` (Atlas Vector Search backed).
2. **How does an agent identify suitable peers for a sub-task?** → The
   `SupervisorAgent.delegate(sub_task)` method runs a Voyage-embedded vector
   query against `agent_skills`, then re-ranks by `reliability_score`.
3. **How is context shared inside token limits?** → A three-layer memory stack
   (working buffer + episodic retriever + Voyage-rerank compression) governed
   by a `TokenBudgeter` that triggers summarisation at 60 % of model max.
4. **How do agents perform intricate tasks resulting from collaboration?** →
   Four LangGraph collaboration patterns (hierarchical, round-table, pipeline,
   parallel fan-out) compose around a `Supervisor → specialist → Supervisor`
   loop that persists every span to `agent_messages` and every checkpoint to
   `langgraph_checkpoints` (see `05-state-recovery.md`).

Build everything **async** with Motor and `asyncio`. No sync I/O on the hot path.

---

## 1 · LangGraph Topology

### 1.1 `MissionState` TypedDict

This is the single channel-state object passed between every node. Persisted
verbatim by `MongoDBSaver` (see `05-state-recovery.md §1`).

```python
# dronan/agents/state.py
from __future__ import annotations
from typing import TypedDict, Literal, Annotated
from operator import add
from datetime import datetime
from langchain_core.messages import BaseMessage

Route = Literal[
    "interpreter", "memory", "planner", "weather", "geofence",
    "preflight", "dispatch", "vision", "replanner", "anomaly",
    "deconfliction", "payload", "narrator", "analyst", "reflection",
    "demand_forecast", "supervisor", "__end__",
]

class MissionState(TypedDict, total=False):
    operator_id: str
    mission_id: str                       # == LangGraph thread_id
    request: str                          # raw operator utterance
    parsed_task: dict                     # InterpreterAgent output
    route: Route                          # next node decided by Supervisor
    route_history: Annotated[list[Route], add]   # appended each hop
    live_telemetry: dict                  # last drone telemetry frame
    weather: dict                         # WeatherAgent output
    no_fly_violations: list[dict]         # GeofenceAgent output
    payload_status: dict                  # PayloadAgent output (cold-chain)
    anomalies: Annotated[list[dict], add] # AnomalyAgent appends
    obstacles: Annotated[list[dict], add] # VisionAgent appends
    reflection: dict                      # ReflectionAgent output
    errors: Annotated[list[dict], add]    # any node may append
    plan_step_log: Annotated[list[dict], add]
    context_budget_tokens: int            # decremented by TokenBudgeter
    messages: Annotated[list[BaseMessage], add]   # LC chat history channel
    started_at: datetime
    updated_at: datetime
```

The `Annotated[list, add]` pattern is the LangGraph reducer that lets parallel
fan-out nodes (Anomaly + Vision + Weather + Decon) write concurrently without
last-writer-wins clobbering.

### 1.2 `StateGraph` wiring

```python
# dronan/agents/graph.py
from langgraph.graph import StateGraph, START, END
from langgraph_checkpoint_mongodb import MongoDBSaver
from motor.motor_asyncio import AsyncIOMotorClient

from droran.agents.state import MissionState
from droran.agents.nodes import (
    supervisor_node, interpreter_node, memory_node, planner_node,
    weather_node, geofence_node, preflight_node, dispatch_node,
    vision_node, replanner_node, anomaly_node, deconfliction_node,
    payload_node, narrator_node, analyst_node, reflection_node,
    demand_forecast_node,
)

def build_graph(mongo_uri: str) -> "CompiledGraph":
    g = StateGraph(MissionState)

    # --- nodes ---
    g.add_node("supervisor", supervisor_node)
    g.add_node("interpreter", interpreter_node)
    g.add_node("memory", memory_node)
    g.add_node("planner", planner_node)
    g.add_node("weather", weather_node)
    g.add_node("geofence", geofence_node)
    g.add_node("preflight", preflight_node)
    g.add_node("dispatch", dispatch_node)
    g.add_node("vision", vision_node)
    g.add_node("replanner", replanner_node)
    g.add_node("anomaly", anomaly_node)
    g.add_node("deconfliction", deconfliction_node)
    g.add_node("payload", payload_node)
    g.add_node("narrator", narrator_node)
    g.add_node("analyst", analyst_node)
    g.add_node("reflection", reflection_node)
    g.add_node("demand_forecast", demand_forecast_node)

    # --- edges ---
    g.add_edge(START, "supervisor")

    # Supervisor returns to itself after each specialist (loop pattern).
    for specialist in (
        "interpreter", "memory", "planner", "weather", "geofence",
        "preflight", "dispatch", "vision", "replanner", "anomaly",
        "deconfliction", "payload", "narrator", "analyst",
        "reflection", "demand_forecast",
    ):
        g.add_edge(specialist, "supervisor")

    # Supervisor's conditional router.
    def route_from_supervisor(state: MissionState) -> str:
        nxt = state.get("route", "__end__")
        if nxt == "__end__":
            return END
        return nxt
    g.add_conditional_edges("supervisor", route_from_supervisor)

    # Async MongoDB checkpointer (one collection, thread_id == mission_id).
    client = AsyncIOMotorClient(mongo_uri)
    checkpointer = MongoDBSaver(client, db_name="droran", collection_name="langgraph_checkpoints")

    return g.compile(checkpointer=checkpointer)
```

### 1.3 The Supervisor → specialist → Supervisor loop

Every specialist returns `{ "messages": [...], <its outputs>, "route": None }`
and execution returns to `supervisor` which inspects the accumulated state and
either picks the next specialist or emits `__end__`. This guarantees:

* A single planner-of-record (no peer-to-peer chaos).
* Every hop is checkpointed (`MongoDBSaver` after each node — see
  `05-state-recovery.md §1`).
* Replay is trivial: the `route_history` channel is a literal log of routing
  decisions and can be dumped to the Memory Inspector front-end.

---

## 2 · Seventeen Specialist Agents

Each subsection follows the same template:

> **Purpose · System prompt skeleton · Tools · Input schema · Output schema ·
> Success / failure modes · Mongo collections · Trace span**

All agents register themselves at boot via `agent_skills.upsert(...)` (see §3).
All agents emit a span to the `traces` collection (`{trace_id, parent_span_id,
agent, latency_ms, tokens_in, tokens_out, status}` — see `05-state-recovery.md
§8`).

### 2.1 `SupervisorAgent`

* **Purpose:** Decide the next specialist (or end). Owns the `route` channel.
  Performs peer-discovery via vector search whenever the next move is
  ambiguous or a sub-task isn't covered by a static rule.
* **System prompt skeleton** (full text in §8):
  > "You are the Supervisor of a fleet of 17 specialist agents …"
* **Tools:** `delegate(sub_task: str)`, `discover_tool(intent: str)`,
  `escalate_to_operator(reason: str)`.
* **Input:** full `MissionState`.
* **Output:** `{ "route": Route }`.
* **Success:** routes converge to `__end__` with `errors == []`.
* **Failure:** infinite ping-pong → bounded by `len(route_history) > 40` →
  forced escalation.
* **Reads:** `agent_skills`, `tool_registry`, `mission_memory`.
* **Writes:** `traces`, `agent_messages` (one per delegation).
* **Trace span:** `agent="supervisor", intent="route_decision"`.

### 2.2 `InterpreterAgent`

* **Purpose:** Convert raw operator speech into a `parsed_task` (locations,
  supplies, priorities, constraints). Direct port of `ai/coordinator.py` +
  `ai/task_parser.py` with structured output enforcement.
* **System prompt** (full text in §8): few-shot from `ai/test_dataset.py`.
* **Tools:**
  ```python
  @tool
  def normalize_input(text: str) -> str: ...
  @tool
  async def lookup_location(name: str) -> dict: ...   # reads `locations`
  @tool
  def list_supply_terms() -> list[str]: ...
  ```
* **Input:** `{request: str}`.
* **Output:** `parsed_task` matching the dataclass:
  ```python
  class ParsedTask(BaseModel):
      locations: list[str]
      priorities: dict[str, Literal["high", "normal"]]
      supplies: dict[str, str]
      constraints: Constraints
      confidence: ConfidenceScore     # see §9
  ```
* **Failure:** `ValidationLayer` rejects → one retry with a sterner prompt;
  second failure escalates via NarratorAgent.
* **Reads:** `locations`, `supply_catalog`.
* **Writes:** `traces`.

### 2.3 `MemoryAgent`

* **Purpose:** Pull relevant `mission_memory` lessons + recent operator
  context from `chat_history` and inject them into state.
* **Tools:**
  ```python
  @tool
  async def episodic_retrieve(query: str, k: int = 6, region: str | None = None,
                              weather_class: str | None = None) -> list[dict]: ...
  @tool
  async def working_memory(operator_id: str, n: int = 8) -> list[BaseMessage]: ...
  ```
* **Output:** writes into `state["messages"]` and `state["plan_step_log"]`.
* **Reads:** `mission_memory`, `chat_history`.
* **Writes:** `traces`.

### 2.4 `PlannerAgent` (deterministic VRP core, LLM-driven params)

* **Purpose:** Build a feasible drone-route plan. **The combinatorial core is
  Google OR-Tools** (`pywrapcp.RoutingModel` with capacity, time-window, and
  battery dimensions). The LLM only:
  1. Picks the meta-heuristic (`PATH_CHEAPEST_ARC` vs `SAVINGS`),
  2. Sets penalty weights (priority, weather, geofence, payload temperature),
  3. Picks the time-window slack.
* **Tools:**
  ```python
  @tool
  def solve_vrp(params: VRPParams) -> RoutePlan: ...     # OR-Tools wrapper
  @tool
  async def lessons_for_planner(region: str, weather: str, k: int = 5) -> list[dict]: ...
  ```
  `lessons_for_planner` is the self-evolution hook: it injects the top-k
  retrieved lessons into the planner system prompt (see `10-self-evolution.md
  §8`).
* **Output:** `RoutePlan` with `legs[]`, `eta_s`, `distance_m`,
  `chosen_heuristic`, `penalty_weights`.
* **Failure modes:** OR-Tools `Infeasible` → fallback `NaiveSequentialPlanner`
  + lesson written by ReflectionAgent (see `05 §3`).
* **Reads:** `mission_memory`, `weather`, `no_fly_zones`, `drones`, `locations`.
* **Writes:** `plans`, `traces`.

### 2.5 `WeatherAgent`

* **Purpose:** Fetch current + forecast wind, precipitation, visibility for
  every leg of the proposed route, classify each leg as `flyable`,
  `degraded`, or `no-go`.
* **Tools:** `fetch_metar(icao)`, `forecast_window(start, end, bbox)`.
* **Reads:** `weather_cache` (TTL 5 min), external METAR/TAF API.
* **Writes:** `weather_cache`, `traces`.

### 2.6 `GeofenceAgent` (`$geoIntersects`)

* **Purpose:** Validate that no leg intersects an active no-fly zone.
* **Mongo query** (the full power of GeoJSON + 2dsphere):
  ```python
  cursor = db.no_fly_zones.find({
      "geometry": {
          "$geoIntersects": {
              "$geometry": {"type": "LineString", "coordinates": leg_coords}
          }
      },
      "active": True,
      "valid_from": {"$lte": now},
      "valid_to":   {"$gte": now},
  })
  ```
* **Output:** `no_fly_violations: list[{zone_id, leg_index, severity}]`.
* **Index spec:** `{geometry: "2dsphere"}` — see `02 §4`.

### 2.7 `PreflightAgent`

* **Purpose:** Run the full pre-flight checklist (battery, weather, airspace,
  payload, comms, GPS) — direct port of `simulation/backend/preflight.py` to
  async + Mongo-backed.
* **Tools:** one `@tool` per check; the agent composes them and aggregates
  `passed | warning | critical` results.
* **Reads:** `drones`, `weather_cache`, `no_fly_zones`, `payload_orders`.
* **Writes:** `preflight_reports`, `traces`.

### 2.8 `DispatchAgent`

* **Purpose:** Commit the plan: write `mission.status="in_progress"`, push
  way-points to the simulator, register compensating actions (see `05 §4`).
* **Tools:** `commit_mission_plan(plan)`, `arm_drone(drone_id)`,
  `release_payload(drone_id, dest)`.
* **Side-effect class:** **write + external** — every tool here is wrapped in
  `traceable_tool` (see `05 §2`).

### 2.9 `VisionAgent`

* **Purpose:** Run YOLOv8 on incoming drone-camera frames stored in GridFS,
  detect obstacles (people, vehicles, birds, other drones), publish
  `obstacles[]` on the state.
* **Tools:**
  ```python
  @tool
  async def fetch_frame(gridfs_id: str) -> bytes: ...
  @tool
  def detect_obstacles(frame: bytes) -> list[Detection]: ...
  ```
* **Reads:** GridFS bucket `drone_frames`.
* **Writes:** `obstacles`, `traces`.

### 2.10 `ReplannerAgent`

* **Purpose:** Triggered by Supervisor when Anomaly/Vision/Weather/Decon
  produce a critical event. Re-invokes Planner with `excluded_legs[]` and
  produces a delta plan; updates `mission.compensations` accordingly.

### 2.11 `AnomalyAgent`

* **Purpose:** Port of `simulation/backend/anomaly_detector.py` —
  battery drain, speed deviation, route deviation, signal loss. Subscribes
  to a Mongo Change Stream on `telemetry`.

### 2.12 `DeconflictionAgent` (`$near` proximity)

* **Purpose:** Port of `simulation/backend/deconfliction.py`. For each
  active drone, compute pairwise proximity using:
  ```python
  cursor = db.drones.find({
      "live.position": {
          "$near": {
              "$geometry": {"type": "Point", "coordinates": [lon, lat]},
              "$maxDistance": 200       # metres
          }
      },
      "drone_id": {"$ne": self_id},
      "live.alt_m": {"$gte": alt - 30, "$lte": alt + 30},
  })
  ```
* **Index spec:** `{ "live.position": "2dsphere" }`.

### 2.13 `PayloadAgent`

* **Purpose:** Cold-chain monitoring (vaccines, blood). Watch the temperature
  field on telemetry and abort the leg if outside [2 °C, 8 °C] for >120 s.
* **Reads:** `payload_orders`, `telemetry`.
* **Writes:** `payload_events`, `traces`.

### 2.14 `NarratorAgent` (LiveKit + ElevenLabs)

* **Purpose:** Emit voice-mode narration to operator. Calls a LiveKit Worker
  (see `03-realtime-voice.md`) which streams to ElevenLabs TTS. Used for both
  status updates and operator-escalation prompts.
* **Tools:** `say(channel, text, urgency)`, `confirm(prompt) -> bool`.

### 2.15 `AnalystAgent`

* **Purpose:** Run Mongo aggregation pipelines for post-mission analytics
  (mean ETA delta, reroute count by region) and produce an LLM-narrated
  briefing.

### 2.16 `ReflectionAgent`

* **Purpose:** The self-evolution heart. After every mission (success or
  fail) writes `Reflection` doc to `mission_memory` and updates
  `agent_skills.reliability_score`. Full spec: `10-self-evolution.md §1`.

### 2.17 `DemandForecastAgent`

* **Purpose:** Generate synthetic edge-case missions overnight from the
  `synthetic_emergencies` distribution, feed them through the graph, and let
  ReflectionAgent grow the lesson base. Full spec: `10-self-evolution.md §10`.

---

## 3 · Skill Registry & Peer Discovery

### 3.1 `agent_skills` collection

Schema (full index spec in `02-mongodb-data-model.md §6`):

```json
{
  "_id": "agent:planner@v3",
  "agent_name": "PlannerAgent",
  "version": 3,
  "capability_text": "Builds feasible drone-route plans …",
  "tools_offered": ["solve_vrp", "lessons_for_planner"],
  "cost_estimate": {"avg_tokens": 2400, "avg_latency_ms": 1800,
                    "external_calls": 0},
  "reliability_score": 0.91,
  "last_updated": ISODate("…"),
  "embedding": [0.012, ...],     // Voyage voyage-3 (1024-d)
  "metadata": {
      "domain": ["routing", "optimisation"],
      "preferred_for": ["multi-stop", "battery-tight"],
      "avoid_for": ["single-hop-trivial"]
  }
}
```

**Atlas Vector Search index** (declared in `02 §6`):
```json
{
  "name": "agent_skills_vec",
  "type": "vectorSearch",
  "fields": [
    {"path": "embedding", "type": "vector", "numDimensions": 1024,
     "similarity": "cosine"},
    {"path": "metadata.domain", "type": "filter"},
    {"path": "reliability_score", "type": "filter"}
  ]
}
```

### 3.2 Self-registration at boot

```python
# dronan/agents/registry.py
from droran.embed import voyage_embed
from droran.db import db

async def register_skill(agent: "BaseAgent") -> None:
    desc = agent.skill_descriptor()                     # subclass overrides
    desc["embedding"] = await voyage_embed(desc["capability_text"])
    desc["last_updated"] = datetime.utcnow()
    await db.agent_skills.update_one(
        {"_id": f"agent:{agent.name}@v{agent.version}"},
        {"$set": desc},
        upsert=True,
    )

async def register_all(agents: list["BaseAgent"]) -> None:
    await asyncio.gather(*(register_skill(a) for a in agents))
```

### 3.3 `SupervisorAgent.delegate(sub_task)`

Full async code:

```python
# dronan/agents/supervisor.py
from droran.embed import voyage_embed, voyage_rerank
from droran.db import db

async def delegate(sub_task: str, mission_id: str,
                   k_candidates: int = 5) -> str:
    """Vector-search agent_skills, rerank by reliability, return agent_name."""
    qvec = await voyage_embed(sub_task)
    pipeline = [
        {"$vectorSearch": {
            "index": "agent_skills_vec",
            "path": "embedding",
            "queryVector": qvec,
            "numCandidates": 64,
            "limit": k_candidates,
        }},
        {"$project": {
            "agent_name": 1, "capability_text": 1,
            "reliability_score": 1, "cost_estimate": 1,
            "score": {"$meta": "vectorSearchScore"},
        }},
    ]
    candidates = [doc async for doc in db.agent_skills.aggregate(pipeline)]
    if not candidates:
        raise NoCapableAgentError(sub_task)

    # Rerank: 0.6 * vector_score + 0.4 * reliability_score (z-normalised).
    for c in candidates:
        c["final"] = 0.6 * c["score"] + 0.4 * c["reliability_score"]
    chosen = max(candidates, key=lambda c: c["final"])

    # Persist the decision for replay.
    await db.agent_messages.insert_one({
        "mission_id": mission_id,
        "from": "supervisor",
        "to": chosen["agent_name"],
        "intent": "delegate",
        "payload": {"sub_task": sub_task,
                    "candidates": [c["agent_name"] for c in candidates],
                    "scores":     [c["final"]     for c in candidates]},
        "timestamp": datetime.utcnow(),
    })
    return chosen["agent_name"]
```

### 3.4 Worked example

Sub-task: *"verify route segment is below max altitude per UK CAA"*.

* Embed the query.
* `$vectorSearch` returns (cosine scores in brackets):
  * `GeofenceAgent` (0.81)
  * `PreflightAgent` (0.78)
  * `WeatherAgent`   (0.42)
* Rerank with reliability:
  * Geofence:  0.6·0.81 + 0.4·0.74 = **0.782**
  * Preflight: 0.6·0.78 + 0.4·0.93 = **0.840** ← winner (CAA legal checks
    are Preflight's bread and butter; ReflectionAgent has bumped its
    reliability over time).
* Supervisor delegates to `PreflightAgent`. The `agent_messages` row records
  both candidates and scores so the Memory Inspector UI can show *why* the
  pick was made.

### 3.5 Reliability update

After the mission, `ReflectionAgent` walks `agent_messages` and computes
per-agent success deltas, updating `reliability_score` via the EWMA formula
in `10 §5`.

---

## 4 · A2A Messaging Protocol

### 4.1 `AgentMessage` Pydantic model

```python
# dronan/agents/protocol.py
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field
import uuid

Intent = Literal[
    "delegate", "request", "response", "broadcast",
    "escalate", "narrate", "checkpoint", "tool_call", "tool_result",
]
Status = Literal["pending", "ok", "error", "timeout", "skipped"]

class AgentMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str
    parent_span_id: str | None = None
    mission_id: str
    from_agent: str = Field(alias="from")
    to_agent:   str = Field(alias="to")
    intent: Intent
    payload: dict[str, Any]
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    status: Status = "pending"
    retries: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
```

### 4.2 Persistence

```python
async def persist_message(msg: AgentMessage) -> None:
    await db.agent_messages.insert_one(msg.model_dump(by_alias=True))
```

Index spec (full list in `02 §7`):

```python
db.agent_messages.create_index([("mission_id", 1), ("timestamp", 1)])
db.agent_messages.create_index([("trace_id", 1)])
db.agent_messages.create_index([("from", 1), ("to", 1)])
```

### 4.3 Replay

The replay endpoint (powering the Memory Inspector — see `09-frontend.md`):

```python
# dronan/api/replay.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/missions/{mission_id}/replay")
async def replay(mission_id: str):
    msgs = await db.agent_messages.find(
        {"mission_id": mission_id}
    ).sort("timestamp", 1).to_list(length=None)
    chk  = await db.langgraph_checkpoints.find(
        {"thread_id": mission_id}
    ).sort("ts", 1).to_list(length=None)
    tools = await db.tool_call_log.find(
        {"mission_id": mission_id}
    ).sort("started_at", 1).to_list(length=None)
    return {"messages": msgs, "checkpoints": chk, "tool_calls": tools}
```

A debug CLI replays this stream by re-invoking the graph with
`graph.invoke(None, config={"configurable": {"thread_id": mission_id}})` —
all deterministic side-effects are deduped by the idempotency key (see
`05 §2`).

---

## 5 · Context Sharing within Token Limits

### 5.1 Three-layer memory stack

```
┌──────────────────────────────────────────────────────┐
│ Layer 1 · WorkingMemoryBuffer (Mongo-backed)         │  recent N turns
│   ConversationSummaryBufferMemory                    │  + rolling summary
├──────────────────────────────────────────────────────┤
│ Layer 2 · EpisodicRetriever                          │  vector top-k from
│   MongoDBAtlasVectorSearch over mission_memory       │  mission_memory
├──────────────────────────────────────────────────────┤
│ Layer 3 · ContextualCompressionRetriever             │  Voyage rerank →
│   wraps Layer 2 with VoyageAIRerank                  │  drop irrelevant
└──────────────────────────────────────────────────────┘
                       │
                       ▼
                 TokenBudgeter
        (summarise on >60 % of model max)
```

### 5.2 Layer 1 · `WorkingMemoryBuffer`

```python
# dronan/memory/working.py
from langchain_mongodb import MongoDBChatMessageHistory
from langchain.memory import ConversationSummaryBufferMemory
from langchain_openai import ChatOpenAI

def build_working_buffer(operator_id: str, mongo_uri: str,
                         max_tokens: int = 1500) -> ConversationSummaryBufferMemory:
    history = MongoDBChatMessageHistory(
        connection_string=mongo_uri,
        session_id=operator_id,
        database_name="droran",
        collection_name="chat_history",
    )
    return ConversationSummaryBufferMemory(
        chat_memory=history,
        llm=ChatOpenAI(model="gpt-4o-mini", temperature=0),
        max_token_limit=max_tokens,
        return_messages=True,
    )
```

### 5.3 Layer 2 · `EpisodicRetriever`

```python
# dronan/memory/episodic.py
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_voyageai import VoyageAIEmbeddings
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

def episodic_retriever(mongo_uri: str, k: int = 12,
                       region: str | None = None,
                       weather_class: str | None = None):
    store = MongoDBAtlasVectorSearch.from_connection_string(
        connection_string=mongo_uri,
        namespace="droran.mission_memory",
        embedding=VoyageAIEmbeddings(model="voyage-3"),
        index_name="mission_memory_vec",
        text_key="summary",
        embedding_key="embedding",
    )
    pre_filter = {"metadata.deprecated": {"$ne": True}}
    if region:        pre_filter["metadata.region"]        = region
    if weather_class: pre_filter["metadata.weather_class"] = weather_class
    return store.as_retriever(
        search_kwargs={"k": k, "pre_filter": pre_filter},
    )
```

### 5.4 Layer 3 · `ContextualCompressionRetriever` with Voyage rerank

```python
# dronan/memory/compress.py
from langchain.retrievers import ContextualCompressionRetriever
from langchain_voyageai import VoyageAIRerank

def compressed_retriever(base_retriever, top_n: int = 4):
    reranker = VoyageAIRerank(model="rerank-2", top_n=top_n)
    return ContextualCompressionRetriever(
        base_compressor=reranker,
        base_retriever=base_retriever,
    )
```

### 5.5 `TokenBudgeter`

```python
# dronan/memory/budget.py
from __future__ import annotations
import tiktoken
from typing import Iterable
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage

class TokenBudgeter:
    """Tracks cumulative prompt tokens per node. When the running total
    crosses `summarise_threshold * model_max`, replace older turns with
    an LLM summary."""

    def __init__(self, model: str, model_max: int,
                 summarise_threshold: float = 0.6):
        self.encoder = tiktoken.encoding_for_model(model)
        self.model_max = model_max
        self.threshold = int(model_max * summarise_threshold)
        self._cumulative = 0

    def count(self, messages: Iterable[BaseMessage]) -> int:
        return sum(len(self.encoder.encode(m.content or "")) for m in messages)

    def must_summarise(self, messages: list[BaseMessage]) -> bool:
        self._cumulative = self.count(messages)
        return self._cumulative >= self.threshold

    async def summarise(self, messages: list[BaseMessage], llm) -> list[BaseMessage]:
        if not self.must_summarise(messages):
            return messages
        # Keep last 6 turns verbatim; summarise the rest.
        head, tail = messages[:-6], messages[-6:]
        if not head:
            return messages
        prompt = (
            "Summarise the following agent dialogue in <=200 tokens, preserving "
            "decisions, deltas, and any operator preferences. Drop pleasantries.\n\n"
            + "\n".join(f"{m.type.upper()}: {m.content}" for m in head)
        )
        summary = (await llm.ainvoke(prompt)).content
        self._cumulative = self.count(tail) + len(self.encoder.encode(summary))
        return [SystemMessage(content=f"[SUMMARY OF EARLIER TURNS]\n{summary}"), *tail]

    @property
    def remaining(self) -> int:
        return self.model_max - self._cumulative
```

### 5.6 Wiring the three layers into a node

```python
# dronan/agents/nodes/planner_node.py
async def planner_node(state: MissionState) -> dict:
    operator_id = state["operator_id"]
    region      = state.get("parsed_task", {}).get("region")
    weather     = state.get("weather", {}).get("class")

    working = build_working_buffer(operator_id, MONGO_URI)
    episodic = episodic_retriever(MONGO_URI, region=region,
                                  weather_class=weather)
    retriever = compressed_retriever(episodic, top_n=4)

    # Build the prompt under a token budget.
    budgeter = TokenBudgeter(model="gpt-4o", model_max=128_000)
    history  = working.chat_memory.messages
    history  = await budgeter.summarise(history, planner_llm)

    lessons  = await retriever.aget_relevant_documents(state["request"])
    prompt   = render_planner_prompt(state, history, lessons)

    plan = await planner_llm.ainvoke(prompt)
    return {"plan_step_log": [{"agent": "planner", "ok": True}],
            "messages": [AIMessage(content=plan.content)],
            "context_budget_tokens": budgeter.remaining}
```

---

## 6 · Tool Registry

### 6.1 Tool descriptor

```python
# dronan/tools/base.py
from pydantic import BaseModel
from typing import Literal, Any
from langchain_core.tools import BaseTool

SideEffect = Literal["read", "write", "external", "write+external"]

class ToolDescriptor(BaseModel):
    name: str
    args_schema: dict                    # JSON Schema
    side_effect: SideEffect
    idempotency: Literal["natural", "key", "none"]
    retry_policy: dict                   # tenacity kwargs
    cost_estimate: dict                  # {tokens, latency_ms, $}
    embedding: list[float] | None = None
    tool_callable: Any                   # not persisted; resolved at boot
```

Every tool is an `@tool`-decorated async function whose Pydantic schema is
introspected:

```python
# dronan/tools/vrp.py
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

class VRPParams(BaseModel):
    fleet:   list[dict] = Field(..., description="Drones with capacity, battery_wh")
    stops:   list[dict] = Field(..., description="Locations with demand_kg, time_window")
    weights: dict       = Field(default_factory=lambda: {"priority": 1.0, "weather": 0.4})
    heuristic: str = "PATH_CHEAPEST_ARC"

class RoutePlan(BaseModel):
    legs: list[dict]
    eta_s: int
    distance_m: int
    chosen_heuristic: str
    penalty_weights: dict

@tool(args_schema=VRPParams)
@retry(stop=stop_after_attempt(2),
       wait=wait_exponential_jitter(initial=0.2, max=2.0))
async def solve_vrp(**kwargs) -> RoutePlan:
    """Solve the drone vehicle-routing problem with OR-Tools."""
    from droran.planning.vrp import solve
    return await solve(VRPParams(**kwargs))
```

### 6.2 `tool_registry` collection

```python
# dronan/tools/registry.py
async def register_tool(tool_obj, side_effect: SideEffect,
                        idempotency: str = "key"):
    desc = ToolDescriptor(
        name=tool_obj.name,
        args_schema=tool_obj.args_schema.schema(),
        side_effect=side_effect,
        idempotency=idempotency,
        retry_policy={"stop": "after_attempt(2)",
                      "wait": "exponential_jitter(0.2, 2.0)"},
        cost_estimate={"tokens": 0, "latency_ms": 200, "$": 0.0},
    )
    desc.embedding = await voyage_embed(
        f"{tool_obj.name}\n{tool_obj.description}\n"
        f"side_effect={side_effect}"
    )
    await db.tool_registry.update_one(
        {"name": tool_obj.name},
        {"$set": desc.model_dump()},
        upsert=True,
    )
```

### 6.3 Tool discovery (Supervisor fallback)

```python
async def discover_tool(intent: str, k: int = 5) -> str:
    qvec = await voyage_embed(intent)
    cur = db.tool_registry.aggregate([
        {"$vectorSearch": {
            "index": "tool_registry_vec",
            "path": "embedding",
            "queryVector": qvec,
            "numCandidates": 32,
            "limit": k,
        }},
        {"$match": {"side_effect": {"$in": ["read", "write", "external"]}}},
    ])
    candidates = [c async for c in cur]
    if not candidates:
        raise NoToolError(intent)
    return candidates[0]["name"]
```

---

## 7 · Multi-Agent Collaboration Patterns

### 7.1 Hierarchical supervisor (default)

Already shown in §1.2 — every specialist returns to `supervisor`. Use this
for ≥80 % of normal mission flow.

### 7.2 Round-table debate (ambiguous interpretation)

When the InterpreterAgent's confidence < 0.6, Supervisor opens a 2-round
debate between Interpreter, Memory, and Planner — each critiques the other's
parse, then Interpreter emits the final structured task.

```python
# dronan/agents/patterns/debate.py
from langgraph.graph import StateGraph, START, END

class DebateState(TypedDict, total=False):
    request: str
    proposals: Annotated[list[dict], add]
    rounds: int
    final: dict

async def interpreter_propose(state):
    proposal = await interpreter_llm.ainvoke(state["request"])
    return {"proposals": [{"author": "interpreter", "data": proposal}]}

async def memory_critique(state):
    last = state["proposals"][-1]
    critique = await memory_llm.ainvoke(
        f"Critique this parse against past similar missions:\n{last}"
    )
    return {"proposals": [{"author": "memory", "data": critique}]}

async def planner_critique(state):
    last = state["proposals"][-1]
    critique = await planner_llm.ainvoke(
        f"Will this parse produce a feasible plan? Why/why not?\n{last}"
    )
    return {"proposals": [{"author": "planner", "data": critique}]}

async def consolidate(state):
    final = await interpreter_llm.ainvoke({
        "instruction": "Reconcile critiques into a final ParsedTask.",
        "proposals": state["proposals"],
    })
    return {"final": final, "rounds": state.get("rounds", 0) + 1}

def build_debate():
    g = StateGraph(DebateState)
    g.add_node("propose",     interpreter_propose)
    g.add_node("memory",      memory_critique)
    g.add_node("planner",     planner_critique)
    g.add_node("consolidate", consolidate)
    g.add_edge(START, "propose")
    g.add_edge("propose", "memory")
    g.add_edge("memory",  "planner")
    g.add_edge("planner", "consolidate")
    g.add_conditional_edges(
        "consolidate",
        lambda s: "propose" if s["rounds"] < 2 else END,
    )
    return g.compile()
```

### 7.3 Pipeline (Preflight → Dispatch)

Strictly sequential — no Supervisor return-trip in between, since Dispatch
must follow Preflight without re-routing decisions.

```python
g.add_edge("preflight", "dispatch")     # bypass supervisor
g.add_edge("dispatch", "supervisor")    # back to supervisor afterwards
```

### 7.4 Parallel fan-out (live mission monitoring)

While the drone is in flight, `Anomaly + Vision + Weather + Decon` all run
concurrently against the telemetry stream. ReplannerAgent acts as the gate
that triggers only when at least one produces a critical signal.

```python
# dronan/agents/patterns/monitor.py
from langgraph.graph import StateGraph, START, END

class MonitorState(MissionState):
    pass

def build_monitor():
    g = StateGraph(MonitorState)
    g.add_node("anomaly",       anomaly_node)
    g.add_node("vision",        vision_node)
    g.add_node("weather",       weather_node)
    g.add_node("deconfliction", deconfliction_node)
    g.add_node("replanner",     replanner_node)

    # Fan-out from START to all four monitors in parallel.
    g.add_edge(START, "anomaly")
    g.add_edge(START, "vision")
    g.add_edge(START, "weather")
    g.add_edge(START, "deconfliction")

    # Fan-in: ReplannerAgent only runs if any produced critical events.
    def needs_replan(state) -> str:
        critical = (
            any(a["severity"] == "critical" for a in state.get("anomalies", []))
            or any(o["risk"] == "high" for o in state.get("obstacles", []))
            or state.get("weather", {}).get("class") == "no-go"
            or any(c["severity"] == "critical" for c in state.get("conflicts", []))
        )
        return "replanner" if critical else END

    for node in ("anomaly", "vision", "weather", "deconfliction"):
        g.add_conditional_edges(node, needs_replan)
    g.add_edge("replanner", END)
    return g.compile()
```

The fan-in works because all four monitors write to channels with
`Annotated[list, add]` reducers — concurrent writes merge cleanly.

---

## 8 · System Prompts

> Each prompt below is the verbatim string the corresponding agent loads at
> boot. Lengths are 200–400 words to maximise instruction adherence without
> bloating context.

### 8.1 SupervisorAgent

```text
You are the Supervisor of a 17-agent drone-fleet operations team. Your sole
job each turn is to choose the *next* specialist to invoke (or to end the
mission). You never plan, parse, fly, or speak directly to the operator.

Operating rules:

1. Read the current MissionState. Identify what the mission currently NEEDS,
   not what was last done.
2. If the operator's request has not been parsed (`parsed_task` is empty),
   route to `interpreter`.
3. If `parsed_task` exists but no relevant lessons have been retrieved in
   `messages`, route to `memory`.
4. If a plan does not exist or is invalidated by a new event, route to
   `planner` (or `replanner` if a plan exists and an anomaly is present).
5. Once a plan exists, ensure WeatherAgent and GeofenceAgent have validated
   it before PreflightAgent runs.
6. Preflight → Dispatch is a strict pipeline; once Dispatch succeeds you
   transition the mission into the live-monitoring fan-out (Anomaly, Vision,
   Weather, Deconfliction).
7. After mission terminus (success or fail) route to `reflection`, then end.
8. If you cannot identify a suitable specialist for a sub-task, call the
   `delegate(sub_task)` tool — it returns the best agent via vector search
   over `agent_skills`. Trust its choice unless reliability_score < 0.5.
9. If `len(route_history) > 40` or any single specialist appears more than 6
   times consecutively, escalate to operator via `escalate_to_operator`.
10. Output ONLY a JSON object: `{"route": "<agent_name>"|"__end__",
    "reason": "<≤30 words>"}`. No prose, no markdown.

You are forbidden from inventing agents that do not exist in `agent_skills`.
You are forbidden from skipping ReflectionAgent at mission end. Failure to
follow these rules causes audit-trail violations and wastes hackathon judges'
time.
```

### 8.2 InterpreterAgent

```text
You convert raw operator speech into a structured ParsedTask JSON object.
You never invent locations, supplies, or constraints — only extract what is
explicitly present or unambiguously implied.

ParsedTask schema:
  - locations: list[str]        # must match config.VALID_LOCATIONS
  - supplies:  dict[str, str]   # location -> supply_term
  - priorities: dict[str, "high"|"normal"]
  - constraints: { avoid_zones: list[str], weather_concern: str,
                   time_sensitive: bool }

Rules:
1. If ambiguous, set `confidence.<field> < 0.6` so the validator triggers a
   round-table debate (do NOT silently guess).
2. Treat "urgent", "ASAP", "stat", "code red", "critical patient" as
   priority=high.
3. Treat any of {"insulin", "blood", "vaccines", "antibiotics", "bandages",
   "epinephrine", "plasma"} as known supplies. Unknown items go in
   `constraints.weather_concern` is wrong — instead push them into a
   `notes` field and lower confidence.
4. Output STRICT JSON conforming to ParsedTask. No extra keys.

Few-shot examples (drawn from ai/test_dataset.py):

Input:  "Deliver insulin to Clinic A"
Output: {"locations":["Clinic A"],"supplies":{"Clinic A":"insulin"},
         "priorities":{},"constraints":{"avoid_zones":[],"weather_concern":"",
         "time_sensitive":false}}

Input:  "Send blood to Clinic B urgently"
Output: {"locations":["Clinic B"],"supplies":{"Clinic B":"blood"},
         "priorities":{"Clinic B":"high"},"constraints":{"avoid_zones":[],
         "weather_concern":"","time_sensitive":true}}

Input:  "Get vaccines to Clinic D but avoid the airport corridor"
Output: {"locations":["Clinic D"],"supplies":{"Clinic D":"vaccines"},
         "priorities":{},"constraints":{"avoid_zones":["airport_corridor"],
         "weather_concern":"","time_sensitive":false}}

Input:  "Deliver insulin to Clinic A, blood to Clinic B, and bandages to
         Clinic C"
Output: {"locations":["Clinic A","Clinic B","Clinic C"],
         "supplies":{"Clinic A":"insulin","Clinic B":"blood",
                     "Clinic C":"bandages"},
         "priorities":{},"constraints":{"avoid_zones":[],
         "weather_concern":"","time_sensitive":false}}

If the operator utterance is empty, whitespace-only, or > 2000 chars, return
{"error":"invalid_input"}. The orchestrator will handle escalation.
```

### 8.3 ReflectionAgent

Full prompt in `10-self-evolution.md §1`. It runs after every mission and
writes `Reflection` docs to `mission_memory`.

### 8.4 PlannerAgent

```text
You are the Planner. Your combinatorial work is delegated to the
`solve_vrp` tool (Google OR-Tools). YOUR job is to:

1. Choose the meta-heuristic: PATH_CHEAPEST_ARC for tight time-windows,
   SAVINGS for sparse priority deliveries, GUIDED_LOCAL_SEARCH for
   long-horizon optimisation (>10 stops).
2. Set penalty weights for: priority (default 1.0), weather (0.4 base,
   raise to 0.8 in degraded conditions), geofence-buffer (1.5 hard),
   payload-temperature (1.2 for cold-chain).
3. Set time-window slack: 0 s for cold-chain, 60 s for high-priority,
   180 s otherwise.
4. Read the retrieved lessons (passed in via `{lessons}` placeholder).
   Each lesson has `kind`, `summary`, `metadata.usefulness_score`.
5. For lessons with kind=corridor_avoidance and usefulness_score>0.5,
   add the corridor to `excluded_legs`. NEVER hard-block on a single
   lesson — require ≥2 corroborating lessons (anti-overfitting; see
   10-self-evolution.md §9).
6. Output the args you'll pass to solve_vrp as a strict JSON object,
   followed by your reasoning in ≤50 words. Do not produce the route
   yourself — that is solve_vrp's job.

Retrieved lessons:
{lessons}

Mission context:
{state_summary}
```

---

## 9 · Confidence + Validation Gating

### 9.1 `ValidationLayer`

A direct port of `ai/validator.py` and `ai/confidence.py`, callable by both
InterpreterAgent and PlannerAgent.

```python
# dronan/agents/validation.py
from typing import Literal
from pydantic import BaseModel

class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    corrections: dict = {}
    confidence_overall: float

class ValidationLayer:
    def __init__(self, db, threshold: float = 0.6):
        self.db = db
        self.threshold = threshold

    async def validate_parsed(self, parsed: dict, request: str) -> ValidationResult:
        from droran.legacy.validator import validate_parsed_output
        from droran.legacy.confidence import score_confidence
        v = validate_parsed_output(parsed, request)
        c = score_confidence(request, parsed)
        v.confidence_overall = c["overall"]
        v.warnings.extend(c["flags"])
        return ValidationResult(**v.to_dict(), confidence_overall=c["overall"])

    async def validate_plan(self, plan: dict, state: dict) -> ValidationResult:
        errs, warns = [], []
        if not plan.get("legs"):
            errs.append("plan has no legs")
        if plan["eta_s"] > 3600:
            warns.append("eta exceeds 1h soft cap")
        for leg in plan["legs"]:
            if leg.get("battery_margin_pct", 0) < 15:
                errs.append(f"leg {leg['index']} below 15% battery margin")
        return ValidationResult(
            valid=not errs, errors=errs, warnings=warns,
            confidence_overall=1.0 if not errs else 0.4,
        )

    def gate(self, vr: ValidationResult) -> Literal["accept", "warn", "reject"]:
        if not vr.valid: return "reject"
        if vr.confidence_overall < self.threshold: return "warn"
        return "accept"
```

### 9.2 Retry & escalation policy

* `accept` → continue.
* `warn`   → continue but emit a `narrate` event so the operator is told.
* `reject` → re-invoke the producing agent with an *additional* system
  message:
  ```
  "Your previous output was rejected for: {errors}. Re-emit a stricter,
   higher-confidence response."
  ```
  After **one** failed retry → escalate via NarratorAgent, mark mission
  `failed` with cause `validation_persistent`, and let ReflectionAgent
  process the failure into a lesson.

```python
async def with_validation(node, validator, kind: str):
    async def wrapped(state):
        out = await node(state)
        vr  = await validator(out)
        decision = validator.gate(vr)
        if decision == "reject":
            if state.get("retried_" + kind):
                await escalate(state, vr)
                return {"errors": [{"kind": kind, "vr": vr.dict()}],
                        "route": "narrator"}
            stricter = state.get("messages", []) + [
                SystemMessage(content=f"REJECTED: {vr.errors}. Retry strictly.")
            ]
            return await node({**state, "messages": stricter,
                               "retried_" + kind: True})
        return out
    return wrapped
```

---

## 10 · Worked Example — Single Mission Token-by-Token Flow

Operator says: *"Send blood to Clinic B urgently and avoid the airport corridor."*

### 10.1 Trace timeline

| t (ms) | from        | to           | intent     | tokens_in | tokens_out | latency_ms |
|-------:|-------------|--------------|------------|----------:|-----------:|-----------:|
| 0      | operator    | supervisor   | request    | 0         | 0          | 0          |
| 5      | supervisor  | interpreter  | delegate   | 320       | 12         | 5          |
| 1 050  | interpreter | supervisor   | response   | 280       | 95         | 1 045      |
| 1 060  | supervisor  | memory       | delegate   | 410       | 9          | 10         |
| 1 480  | memory      | supervisor   | response   | 0         | 0          | 420        |
| 1 490  | supervisor  | planner      | delegate   | 1 220     | 14         | 10         |
| 3 200  | planner     | supervisor   | response   | 1 800     | 280        | 1 710      |
| 3 210  | supervisor  | weather      | delegate   | 200       | 8          | 10         |
| 3 700  | weather     | supervisor   | response   | 80        | 110        | 490        |
| 3 710  | supervisor  | geofence     | delegate   | 220       | 8          | 10         |
| 4 100  | geofence    | supervisor   | response   | 0         | 0          | 390        |
| 4 110  | supervisor  | preflight    | delegate   | 240       | 8          | 10         |
| 5 200  | preflight   | dispatch     | pipeline   | 0         | 0          | 1 090      |
| 5 950  | dispatch    | supervisor   | response   | 0         | 0          | 750        |
| 5 960  | supervisor  | (fan-out)    | broadcast  | 0         | 0          | 0          |
| …      | …           | …            | …          | …         | …          | …          |
| 92 100 | replanner   | supervisor   | response   | 600       | 220        | 980        |
| 92 110 | supervisor  | reflection   | delegate   | 2 400     | 16         | 10         |
| 94 800 | reflection  | supervisor   | response   | 3 100     | 480        | 2 690      |
| 94 805 | supervisor  | __end__      | end        | 0         | 0          | 5          |

### 10.2 Sample `agent_messages` rows

```json
{
  "trace_id": "trc-7f1c…",
  "parent_span_id": null,
  "mission_id": "mss-2026-05-12-0001",
  "from": "supervisor",
  "to": "interpreter",
  "intent": "delegate",
  "payload": {"sub_task": "parse operator request"},
  "tokens_in": 320, "tokens_out": 12,
  "latency_ms": 5, "status": "pending", "retries": 0,
  "timestamp": "2026-05-12T09:00:00.005Z"
}
{
  "trace_id": "trc-7f1c…",
  "parent_span_id": "spn-int-001",
  "mission_id": "mss-2026-05-12-0001",
  "from": "interpreter",
  "to": "supervisor",
  "intent": "response",
  "payload": {
    "parsed_task": {
      "locations": ["Clinic B"],
      "supplies": {"Clinic B": "blood"},
      "priorities": {"Clinic B": "high"},
      "constraints": {
        "avoid_zones": ["airport_corridor"],
        "weather_concern": "",
        "time_sensitive": true
      },
      "confidence": {"overall": 0.92}
    }
  },
  "tokens_in": 280, "tokens_out": 95,
  "latency_ms": 1045, "status": "ok", "retries": 0,
  "timestamp": "2026-05-12T09:00:01.050Z"
}
```

### 10.3 Sample `traces` spans

```json
{ "_id": "spn-plan-001", "trace_id": "trc-7f1c…",
  "agent": "planner", "tool": "solve_vrp",
  "started_at": "2026-05-12T09:00:01.490Z",
  "ended_at":   "2026-05-12T09:00:03.200Z",
  "tokens_in": 1220, "tokens_out": 280,
  "status": "ok",
  "attrs": {
    "heuristic": "PATH_CHEAPEST_ARC",
    "penalty_weights": {"priority": 1.5, "weather": 0.4, "geofence": 1.5},
    "lessons_used": ["lsn-corridor-airport-2026-04-30",
                     "lsn-weather-blood-cold-2026-05-01"]
  }
}
```

### 10.4 What the judges see in the live demo

* The Memory Inspector renders the `agent_messages` rows in real time
  (Change Stream tail).
* The "Reflection Feed" shows two new lessons appearing post-mission:
  * `lsn-airport-corridor-windshear-2026-05-12` (corridor_avoidance)
  * `lsn-blood-temp-stable-2026-05-12` (payload_constraint, success)
* The encore mission (Take 2) picks both lessons up via the
  `lessons_for_planner` tool — see `10-self-evolution.md §8` and
  `11-demo-script.md §4`.

---

## 11 · Boot sequence (full)

```python
# dronan/main.py
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from droran.agents.graph import build_graph
from droran.agents.registry import register_all
from droran.tools.registry import register_tool
from droran.agents.all import ALL_AGENTS, ALL_TOOLS

async def boot():
    client = AsyncIOMotorClient(MONGO_URI)
    await client.admin.command("ping")
    await register_all(ALL_AGENTS)
    for t, side, idem in ALL_TOOLS:
        await register_tool(t, side, idem)
    graph = build_graph(MONGO_URI)
    return graph

if __name__ == "__main__":
    asyncio.run(boot())
```

---

## 12 · Acceptance criteria for this spec (cross-ref `12-acceptance-tests.md`)

* `pytest tests/agents/test_supervisor_loop.py::test_loop_terminates`
* `pytest tests/agents/test_skill_discovery.py::test_caa_routes_to_preflight`
* `pytest tests/agents/test_token_budgeter.py::test_summarises_at_threshold`
* `pytest tests/agents/test_validation_retry.py::test_one_retry_then_escalate`
* `pytest tests/agents/test_collab_patterns.py::test_parallel_fanout_merges`

If all five pass and the live demo's Memory Inspector renders ≥1 delegation
per second sustained for 60 s, this spec is satisfied.
