# 12 · Acceptance Tests & Quality Gates — Droran

> **Audience:** every engineer writing code under `dronan/`. **Read this before opening a PR.**
> **Companion files:** `00-overview.md` (rubric), `01-architecture.md` (topology), `02-mongodb-data-model.md` (collections + indexes), `04-langchain-agents.md` (graph nodes), `05-state-recovery.md` (saga + checkpointer), `03-mongodb-vector-rag.md` (adaptive RAG), `10-self-evolution.md` (reflection loop), `11-demo-script.md` (every claim below maps to an act).
> **Mandate:** every wow hook in `11-demo-script.md` is gated by ≥ 1 test in this document. If it's not tested, it's not in the demo.

---

## 1 · Test Philosophy

We use a **strict pyramid**: many fast unit tests, a tight band of integration tests against a real MongoDB Atlas cluster, a thin e2e layer through the FastAPI HTTP surface and Next.js UI, and a single **demo-smoke** test that runs the entire Act 1 scenario in <60 s as the last gate before merging to `main`.

**Five non-negotiables:**

1. **Real Atlas, not just mongomock.** Unit tests may use `mongomock-motor` for speed, but every test that touches `$vectorSearch`, `$search`, change streams, time-series, Queryable Encryption, or transactions runs against a real Atlas Sandbox cluster (`droran_test` DB, scoped service account). Atlas Sandbox is the **eligibility-mandatory** substrate for the hackathon — losing parity with it loses the £15K.
2. **Determinism.** All randomness is seeded (`PYTHONHASHSEED=0`, `random.seed(42)`, `numpy.random.seed(42)`). LLM calls in deterministic tests are replayed via `respx` cassettes captured from a one-time golden run; live LLM tests exist but are isolated under `pytest -m live_llm`.
3. **State isolation.** Every test acquires a unique DB suffix (`droran_test_{uuid}`) via the `mongo_db` fixture, runs against it, and the fixture drops it on teardown. Tests never share state.
4. **Trace assertions.** Every integration test asserts on LangSmith trace metadata via the `langsmith` SDK in addition to MongoDB state — this catches regressions where the right document is written but via the wrong reasoning path.
5. **Demo parity.** The `tests/demo/` directory mirrors the five acts in `11-demo-script.md`. CI fails if any act test fails — no exceptions, no skips.

---

## 2 · Tooling

We use **`uv`** for environment + dependency management. **Never `pip`.** All commands assume `uv` is on PATH and `pyproject.toml` is at repo root.

### 2.1 `pyproject.toml` test deps (excerpt)

```toml
[dependency-groups]
test = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-mongodb>=2.4",
    "pytest-benchmark>=4.0",
    "pytest-xdist>=3.6",
    "pytest-cov>=5.0",
    "pytest-timeout>=2.3",
    "mongomock-motor>=0.0.34",
    "respx>=0.21",
    "freezegun>=1.5",
    "hypothesis>=6.110",
    "langsmith>=0.1.140",
    "playwright>=1.47",
    "pytest-playwright>=0.5",
    "anyio>=4.6",
]
```

### 2.2 Standard invocations

```bash
# everything
uv run pytest

# fast feedback loop (unit only, parallel)
uv run pytest tests/unit -n auto -q

# integration suite (real Atlas, sequential, longer timeout)
uv run pytest tests/integration --timeout=120

# e2e (Playwright + FastAPI + LiveKit ephemeral room)
uv run pytest tests/e2e --headed=false

# demo smoke (the gate before any merge to main)
uv run pytest tests/demo/test_demo_smoke.py -q

# perf gates
uv run pytest tests/integration --benchmark-only --benchmark-min-rounds=10

# live LLM (manual; never in CI on PRs)
uv run pytest -m live_llm
```

### 2.3 `pytest.ini` markers

```ini
[pytest]
asyncio_mode = auto
markers =
    unit: pure logic, mongomock allowed
    integration: real MongoDB Atlas, may hit external APIs via respx
    e2e: full HTTP + WS + browser
    demo: mirrors 11-demo-script.md
    live_llm: hits real LLM/Voyage/ElevenLabs (excluded by default)
    slow: > 5 s
filterwarnings = error::DeprecationWarning
addopts = --strict-markers -ra
```

---

## 3 · Directory Layout

```
tests/
├── conftest.py                     # global fixtures: mongo_db, vector_index, seeded_state, fake_llm
├── _data/                          # cassettes, golden Q/A, seed JSON
├── unit/
│   ├── test_mission_state_machine.py        # FSM transitions: planning→dispatched→in_flight→delivered (and all rejections)
│   ├── test_idempotency_keys.py             # tool_call_log unique-index protects against duplicate dispatch_drone
│   ├── test_route_planner_vrp.py            # OR-Tools VRP solver yields valid tours under battery + payload constraints
│   ├── test_geofence.py                     # point-in-polygon vs no_fly_zones, including dynamic TFRs
│   ├── test_weather_gate.py                 # WeatherAgent blocks dispatch when wind > 18 m/s or thunderstorm flag set
│   ├── test_voyage_rerank.py                # rerank-2.5 reorders mocked candidate set as expected
│   ├── test_voice_intent.py                 # pydantic intent schema accepts/rejects 30 utterance fixtures
│   ├── test_anomaly_detector.py             # GPS drift, battery sag, telemetry-loss heuristics fire correctly
│   ├── test_deconfliction.py                # right-of-way rules between sibling drones at merge nodes
│   ├── test_preflight_checks.py             # boot health: 8 vector indexes READY, 17 skill cards present
│   └── test_audit_trail_append_only.py      # writes succeed, updates/deletes raise AuditImmutabilityError
├── integration/
│   ├── test_skill_discovery.py              # $vectorSearch over agent_skills picks correct peer (Act 1)
│   ├── test_a2a_replay.py                   # replay agent_messages by trace_id reconstructs the conversation
│   ├── test_checkpoint_resume.py            # kill mid-graph; MongoDBSaver resumes from same node (Act 3)
│   ├── test_tool_call_recovery.py           # saga compensations roll back partial dispatch on failure
│   ├── test_adaptive_rag.py                 # critic loop converges ≤ 3 iters; ≥ 2 citations (Act 2)
│   ├── test_livekit_session.py              # voice loop ≤ 2.5 s P95, end-to-end with Deepgram + ElevenLabs stubs
│   └── test_demand_forecast.py              # DemandForecastAgent produces a 7-day heat-map from synthetic_emergencies
├── e2e/
│   └── test_dashboard_live_mission.py       # Playwright drives Next.js light-mode dashboard through Act 1
└── demo/
    ├── test_self_evolution.py               # Take 3 ETA ≥ 10 % faster than Take 1 over reflection_eval (Act 4)
    └── test_demo_smoke.py                   # full Act 1 in < 60 s, gates merges to main
```

---

## 4 · Key Test Specifications

These are the eight tests with the highest signal. They exist primarily to **prove the demo claims in `11-demo-script.md`**, not to chase coverage.

### 4.1 `test_skill_discovery.py` (integration, gates Act 1)

**Arrange:** load 17 seed `agent_skills` cards into a fresh DB; build the `agent_skills_voyage` Atlas Vector Search index; embed each `capability` field with `voyage-3-large` (1024 dims). Embed the query "dispatch cold-chain plasma to a multi-casualty road accident" and pass to the SupervisorAgent's skill router.

**Act:** call `SkillRouter.discover(query, top_k=3, filter={"side_effect_class": {"$in": ["read","plan"]}})`.

**Assert:**

```python
async def test_skill_router_picks_payload_agent(seeded_skills, voyage_client):
    router = SkillRouter(db=seeded_skills, embedder=voyage_client, index="agent_skills_voyage")
    hits = await router.discover(
        query="dispatch cold-chain plasma to a multi-casualty road accident",
        top_k=3,
        filter={"side_effect_class": {"$in": ["read", "plan"]}},
    )
    assert hits[0].agent_id == "payload-coldchain-01"
    assert hits[0].score >= 0.80
    assert {h.agent_id for h in hits[:3]} >= {"payload-coldchain-01", "planner-vrp-01"}
    # confirm the underlying $vectorSearch ran (not a python fallback)
    assert hits.metadata["pipeline_stage"] == "atlas_vector_search"
```

### 4.2 `test_checkpoint_resume.py` (integration, gates Act 3)

**Arrange:** start a LangGraph mission graph wired to `MongoDBSaver(client, db_name="droran_test_{uuid}", collection_name="langgraph_checkpoints")`. Drive the graph to the `replanner` node, then `await graph.ainvoke(...)` is **cancelled** mid-node via `asyncio.Task.cancel()` to simulate `kill -9`.

**Act:** create a new `StateGraph` instance from the same checkpointer with the same `thread_id`; call `await graph.ainvoke(None, config={"configurable": {"thread_id": MID}})` (None resumes).

**Assert:**

```python
async def test_resume_from_replanner(mongo_db, mission_graph):
    mission_id = "m25-j14-take-test"
    cfg = {"configurable": {"thread_id": mission_id}}
    task = asyncio.create_task(mission_graph.ainvoke(seed_input(), config=cfg))
    await wait_for_node(mongo_db, mission_id, "replanner", timeout=10)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    cps = await mongo_db.langgraph_checkpoints.find({"thread_id": mission_id}).to_list(length=None)
    assert len(cps) >= 1
    assert cps[-1]["next"] == ["replanner"]

    fresh_graph = build_mission_graph(mongo_db)  # new instance, simulates process restart
    t0 = time.perf_counter()
    final_state = await fresh_graph.ainvoke(None, config=cfg)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"resume budget breached: {elapsed:.2f}s"
    assert final_state["mission"]["status"] == "delivered"

    dispatches = await mongo_db.tool_call_log.count_documents(
        {"mission_id": mission_id, "name": "dispatch_drone"}
    )
    assert dispatches == 3, f"idempotency broken: {dispatches} dispatches recorded"
```

### 4.3 `test_self_evolution.py` (demo, gates Act 4 — the **winning beat**)

**Arrange:** wipe `mission_memory` and `reflection_eval`. Build a deterministic scenario `m25-j14` with seeded telemetry. Run the full mission graph 3× back-to-back, each time letting `ReflectionAgent` finalise.

**Act:** read `reflection_eval` ordered by `take`.

**Assert:**

```python
@pytest.mark.demo
async def test_take3_beats_take1_by_at_least_10_percent(mongo_db, mission_graph):
    scenario = "m25-j14"
    etas = []
    for take in (1, 2, 3):
        result = await run_scenario(mission_graph, scenario=scenario, take=take, seed=42 + take)
        etas.append(result["eta_seconds"])

    rows = await mongo_db.reflection_eval.find({"scenario": scenario}).sort("take", 1).to_list(3)
    assert [r["take"] for r in rows] == [1, 2, 3]

    take1, take3 = etas[0], etas[2]
    improvement = (take1 - take3) / take1
    assert improvement >= 0.10, f"self-evolution failed: only {improvement:.1%} improvement"

    # prove the planner actually consumed lessons (not just coincidence)
    take3_lessons = await mongo_db.mission_memory.count_documents(
        {"scenario": scenario, "kind": {"$in": ["route_lesson", "weather_lesson"]}, "consumed_in_takes": 3}
    )
    assert take3_lessons >= 3, "planner did not retrieve enough lessons in Take 3"
```

A **statistical** sibling test (`test_self_evolution_statistical`) under `@pytest.mark.slow` runs the same loop 50× with seeds 1..50 and asserts ≥ 90 % of runs hit the 10 % improvement bar — this is the answer to judge Q&A #4.

### 4.4 `test_a2a_replay.py` (integration)

**Arrange:** run a mission that emits ≥ 12 A2A envelopes into `agent_messages`, each tagged with the same `trace_id`.

**Act:** call `Replayer.reconstruct(trace_id=...)` which streams docs sorted by `seq` and rebuilds the conversation tree.

**Assert:**

```python
async def test_a2a_replay_reconstructs_full_thread(mongo_db, finished_mission):
    trace_id = finished_mission["trace_id"]
    replay = await Replayer(mongo_db).reconstruct(trace_id)

    assert replay.envelope_count >= 12
    assert replay.root.intent == "mission.dispatch"
    # every reply has a parent in the same trace
    for env in replay.envelopes:
        if env.in_reply_to:
            assert any(e.message_id == env.in_reply_to for e in replay.envelopes)
    # ordering is monotonic in seq
    seqs = [e.seq for e in replay.envelopes]
    assert seqs == sorted(seqs)
```

### 4.5 `test_adaptive_rag.py` (integration, gates Act 2)

**Arrange:** load 1 247 regulation chunks into `regulations` with `regulations_voyage` (vector) and `regulations_text` (Atlas Search BM25) indexes built. Mock the LLM critic to score the first answer 0.55 (insufficient) and the second 0.92 (grounded), via `respx` cassette.

**Act:** invoke `AdaptiveRAGPipeline.answer("Class A2 drone loses C2 link over populated congested area at night — what does CAP 722 require?")`.

**Assert:**

```python
async def test_critic_loop_converges_with_citations(mongo_db, rag_pipeline):
    out = await rag_pipeline.answer(
        "If a Class A2 drone loses C2 link over a populated congested area at night, "
        "what does CAP 722 require us to do, and how long do we have?"
    )
    assert out.iterations <= 3
    assert out.iterations >= 2, "single-pass answer means the critic isn't actually critiquing"
    assert len(out.citations) >= 2
    assert any("CAP-722" in c.paragraph_id for c in out.citations)
    assert out.faithfulness >= 0.85

    # prove we hit hybrid retrieval, not pure vector
    assert out.retrieval_trace.stages == ["rewrite", "multi_query", "hybrid", "rrf", "rerank", "critic",
                                          "rewrite", "hybrid", "rrf", "rerank", "critic", "synthesize"]
```

### 4.6 `test_tool_call_recovery.py` (integration)

Drives the saga in `state/saga.py`: dispatches 3 drones, forces drone-2's `dispatch_drone` tool to raise after writing to `tool_call_log` but before the drone-side ack; asserts the compensating action releases the reservation lock and writes a `compensation` event to `audit_trail`. Re-runs the saga; asserts `tool_call_log.count({name:'dispatch_drone'}) == 3` (idempotency).

### 4.7 `test_idempotency_keys.py` (unit)

Hammers `dispatch_drone(payload, idempotency_key=K)` 100× concurrently with the same `K`; asserts exactly one `tool_call_log` insert succeeds, the other 99 return the cached result, and zero exceptions escape. Uses the unique compound index `{mission_id:1, name:1, idempotency_key:1}` defined in `02-mongodb-data-model.md §4`.

### 4.8 `test_demo_smoke.py` (demo, gates `main`)

```python
@pytest.mark.demo
@pytest.mark.timeout(60)
async def test_full_act1_under_60s(mongo_db, fastapi_client, livekit_room):
    t0 = time.perf_counter()
    await livekit_room.speak(
        "Droran — multi-vehicle accident, M25 junction 14, three priority casualties. "
        "Dispatch O-negative blood, two units of plasma, and a trauma kit. Cold chain critical. Go now."
    )
    mission = await wait_for_mission_status(mongo_db, status="dispatched", timeout=15)
    assert len(mission["drones"]) == 3
    delivered = await wait_for_mission_status(mongo_db, status="delivered", mission_id=mission["_id"], timeout=45)
    elapsed = time.perf_counter() - t0
    assert elapsed < 60.0
    assert delivered["payloads_delivered"] == 4   # blood + 2× plasma + trauma kit
```

---

## 5 · Retrieval Evaluation Harness

### 5.1 Golden set

`tests/_data/retrieval_golden.jsonl` — **30 Q/A pairs minimum**, evenly split:

- 12 over `regulations` (CAP 722, EASA Part-UAS, FAA Part 107)
- 10 over `mission_memory` (route lessons, weather lessons, facility intel)
- 8 over `facilities` + `no_fly_zones` cross-collection joins

Each row: `{question, expected_paragraph_ids[], expected_kind, region, difficulty}`.

### 5.2 Metrics

- **Recall@5** ≥ 0.85 (regulations) / ≥ 0.75 (mission_memory)
- **MRR@10** ≥ 0.70
- **Faithfulness** (LLM-as-judge with `gpt-4o-mini`) ≥ 0.85 mean across the set
- **Citation presence** = 100 % (every answer must cite ≥ 1 source)

### 5.3 CI gate

`uv run pytest tests/integration/test_retrieval_eval.py` is required on every PR touching `rag/`, `prompts/`, or any seed file. Below-threshold runs fail the build.

### 5.4 Drift report

A nightly GitHub Actions job re-runs the harness and writes a row to the `retrieval_eval` Mongo collection: `{date, recall_at_5, mrr, faithfulness, voyage_model_version, n_corpus_chunks}`. The dashboard's `/analyst/retrieval-drift` page surfaces a 30-day trend; >5 % regression triggers a Slack alert.

---

## 6 · Performance Gates (`pytest-benchmark`)

| Metric | Budget | Gating test |
|---|---|---|
| Atlas `$vectorSearch` over `mission_memory` (top-5, region filter) | **P95 < 250 ms** | `test_vector_search_latency.py` |
| End-to-end voice → agent → TTS first byte | **P95 < 2 500 ms** | `test_livekit_session.py::test_loop_latency` |
| LangGraph mission resume after `kill -9` | **< 5 000 ms** | `test_checkpoint_resume.py` (asserted inline) |
| Skill discovery `$vectorSearch` over `agent_skills` | **P95 < 80 ms** | `test_skill_discovery.py::test_latency` |
| Adaptive RAG full loop (rewrite → critic → synthesize, 2 iters) | **P95 < 3 500 ms** | `test_adaptive_rag.py::test_latency` |
| Demo smoke (Act 1 end-to-end) | **< 60 000 ms** | `test_demo_smoke.py` |

`pytest-benchmark` is configured with `--benchmark-min-rounds=10 --benchmark-warmup=on --benchmark-disable-gc`. Budgets are encoded as `pytest.fail` calls when `stats.stats.q95 > BUDGET`.

---

## 7 · CI Matrix — `.github/workflows/ci.yml`

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12"]
    env:
      MONGODB_URI: ${{ secrets.MONGODB_URI_TEST }}        # Atlas Sandbox cluster, droran_test_* DBs
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      VOYAGE_API_KEY: ${{ secrets.VOYAGE_API_KEY }}
      LIVEKIT_API_KEY: ${{ secrets.LIVEKIT_API_KEY }}
      LIVEKIT_API_SECRET: ${{ secrets.LIVEKIT_API_SECRET }}
      LIVEKIT_URL: ${{ secrets.LIVEKIT_URL }}
      ELEVENLABS_API_KEY: ${{ secrets.ELEVENLABS_API_KEY }}
      DEEPGRAM_API_KEY: ${{ secrets.DEEPGRAM_API_KEY }}
      LANGSMITH_API_KEY: ${{ secrets.LANGSMITH_API_KEY }}
      LANGSMITH_PROJECT: droran-ci
      PYTHONHASHSEED: "0"
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - name: Sync deps
        run: uv sync --frozen --group test
      - name: Install Playwright browsers
        run: uv run playwright install --with-deps chromium
      - name: Lint
        run: uv run ruff check . && uv run ruff format --check .
      - name: Type check
        run: uv run mypy droran
      - name: Unit tests
        run: uv run pytest tests/unit -n auto -q --cov=droran --cov-report=xml
      - name: Integration tests (real Atlas)
        run: uv run pytest tests/integration --timeout=120
      - name: E2E (Playwright)
        run: uv run pytest tests/e2e
      - name: Demo smoke (Act 1 < 60 s)
        run: uv run pytest tests/demo/test_demo_smoke.py -q
      - name: Self-evolution gate (Act 4)
        run: uv run pytest tests/demo/test_self_evolution.py -q
      - name: Perf budgets
        run: uv run pytest tests/integration --benchmark-only --benchmark-min-rounds=10
      - uses: codecov/codecov-action@v4
        with:
          files: coverage.xml
```

The Atlas `droran_test` DB is namespaced per-job via `droran_test_${{ github.run_id }}_${{ github.run_attempt }}` and dropped in a `post:` step. Vector indexes are pre-provisioned on the cluster (creating them per-job exceeds Sandbox quota).

---

## 8 · Smoke Script — `scripts/smoke.sh`

Run this **30 minutes before the demo**. Exits non-zero with a friendly diagnosis if anything is off.

```bash
#!/usr/bin/env bash
set -euo pipefail
fail() { echo "❌  $*" >&2; exit 1; }
ok()   { echo "✅  $*"; }

[ -n "${MONGODB_URI:-}" ] || fail "MONGODB_URI not set"
for v in OPENAI_API_KEY VOYAGE_API_KEY LIVEKIT_API_KEY LIVEKIT_API_SECRET \
         ELEVENLABS_API_KEY DEEPGRAM_API_KEY; do
  eval "[ -n \"\${$v:-}\" ]" || fail "$v not set"
done
ok "env vars present"

uv run python -c "
import asyncio, time
from motor.motor_asyncio import AsyncIOMotorClient
import os, sys
async def main():
    c = AsyncIOMotorClient(os.environ['MONGODB_URI'])
    t = time.perf_counter()
    await c.admin.command('ping')
    rtt = (time.perf_counter() - t) * 1000
    if rtt > 200: sys.exit(f'Mongo ping {rtt:.0f}ms exceeds 200ms')
    db = c.droran_demo
    skills = await db.agent_skills.count_documents({})
    if skills != 17: sys.exit(f'agent_skills has {skills} cards (expected 17)')
    regs = await db.regulations.count_documents({})
    if regs < 1000: sys.exit(f'regulations has {regs} chunks (expected >=1000)')
    cps = await db.langgraph_checkpoints.count_documents({})
    if cps != 0: sys.exit(f'langgraph_checkpoints not reset ({cps} docs)')
    indexes = await db.command('listSearchIndexes', 'mission_memory')
    ready = [i for i in indexes['cursor']['firstBatch'] if i.get('status') == 'READY']
    if len(ready) < 1: sys.exit('mission_memory_voyage index not READY')
asyncio.run(main())
" || fail "Atlas pre-flight failed (see message above)"
ok "Atlas pre-flight"

uv run python -m droran.scripts.check_voyage   || fail "Voyage AI quota/keys"
uv run python -m droran.scripts.check_livekit  || fail "LiveKit token mint failed"
uv run python -m droran.scripts.check_11labs   || fail "ElevenLabs voice 'Aria-medical-v3' unavailable"
uv run python -m droran.scripts.check_deepgram || fail "Deepgram Nova-3 stream failed"
ok "external services"

uv run pytest tests/demo/test_demo_smoke.py -q --tb=line || fail "Act 1 smoke test failed"
ok "Act 1 smoke"

echo "🟢  ALL GREEN — demo cluster is ready."
```

---

## 9 · Acceptance Checklist (40+ checkboxes — every requirement in `00-overview.md`)

### Eligibility & substrate

- [ ] MongoDB Atlas Sandbox cluster provisioned, connection string committed only to GitHub Encrypted Secrets.
- [ ] All 16 collections from `02-mongodb-data-model.md` exist in `droran_demo` and `droran_test`.
- [ ] All 8 Atlas Vector Search indexes are `READY` and listed in `infra/atlas_indexes.json`.
- [ ] All 4 Atlas Search (BM25) indexes are `READY`.
- [ ] Time-series collections (`telemetry`, `weather_observations`, `synthetic_emergencies`) created with `timeseries: { timeField, metaField, granularity }`.
- [ ] Queryable Encryption configured on `audit_trail.recipient_pii`.
- [ ] Change streams subscribed by `dronan/api/ws.py` for the dashboard.

### Agents & graph (`04-langchain-agents.md`)

- [ ] All 17 specialist agents register skill cards on boot (`test_preflight_checks.py`).
- [ ] SupervisorAgent picks peers via `$vectorSearch` over `agent_skills` (`test_skill_discovery.py`).
- [ ] A2A messages persisted to `agent_messages` and replayable by `trace_id` (`test_a2a_replay.py`).
- [ ] Validator agent enforces `confidence ≥ 0.7` on every tool call (`test_voice_intent.py`).

### State & recovery (`05-state-recovery.md`)

- [ ] LangGraph wired to `MongoDBSaver` with `thread_id = mission_id`.
- [ ] `tool_call_log` enforces unique `{mission_id, name, idempotency_key}` index.
- [ ] `kill -9` resume completes in < 5 s and produces zero duplicate `dispatch_drone` calls (`test_checkpoint_resume.py`).
- [ ] Saga compensations roll back partial dispatch (`test_tool_call_recovery.py`).
- [ ] `audit_trail` rejects updates and deletes (`test_audit_trail_append_only.py`).

### Adaptive RAG (`03-mongodb-vector-rag.md`)

- [ ] Voyage `voyage-3-large` embeddings (1024 dims) for write-side; `rerank-2.5` for read-side.
- [ ] Hybrid retrieval = `$vectorSearch` ⊕ Atlas Search BM25 fused via RRF.
- [ ] Critic loop bounded ≤ 3 iterations (`test_adaptive_rag.py`).
- [ ] Recall@5 ≥ 0.85 on `regulations` golden set; faithfulness ≥ 0.85.

### Self-evolution (`10-self-evolution.md`)

- [ ] ReflectionAgent runs unconditionally on mission completion.
- [ ] ≥ 6 typed memory cards written per mission (`reflection`, `incident`, `route_lesson`, `weather_lesson`, `facility_intel`, `operator_pref`).
- [ ] Take 3 ETA ≥ 10 % faster than Take 1 on the `m25-j14` scenario (`test_self_evolution.py`).
- [ ] Statistical sibling (`test_self_evolution_statistical`) hits the bar in ≥ 90 % of 50 seeded runs.

### Voice loop (`06-voice-livekit-elevenlabs.md`)

- [ ] LiveKit room `mission-console` minted with Egress recording armed.
- [ ] Deepgram Nova-3 streaming STT integrated; Silero VAD upstream.
- [ ] ElevenLabs Turbo v2.5 TTS with voice `Aria-medical-v3`.
- [ ] Voice → agent → TTS first byte P95 < 2.5 s (`test_livekit_session.py`).

### Frontend (`08-frontend-nextjs.md`)

- [ ] Next.js 15 App Router, **light mode default**, Tailwind v4, shadcn/ui.
- [ ] Leaflet + deck.gl mission map, react-three-fiber drone HUD.
- [ ] Reasoning Stream and Memory Inspector panels visible simultaneously on `/missions/live`.
- [ ] Playwright e2e `test_dashboard_live_mission.py` passes.

### Backend (`07-backend-fastapi.md`)

- [ ] FastAPI + Motor; WebSocket endpoint streams change-stream events.
- [ ] `/api/missions/{id}/trace` reconstructs A2A + LangGraph + tool calls (Replay).
- [ ] Outbox pattern guarantees WS notifications survive worker restart.

### Demo (`11-demo-script.md`)

- [ ] Act 1 voice command → 3-drone dispatch in < 12 s.
- [ ] Act 2 critic loop converges with ≥ 2 citations.
- [ ] Act 3 `kill -9` → resume in < 5 s; `tool_call_log` count for `dispatch_drone` equals 3.
- [ ] Act 4 Take 3 ETA strictly < 0.9 × Take 1 ETA, ≥ 3 lessons retrieved.
- [ ] Act 5 Analyst dashboard renders 7-day demand heat-map in < 1 s.
- [ ] All 6 wow hooks have a backup video in `assets/`.

### Observability & ops

- [ ] LangSmith project `droran-demo` receives traces with `mission_id` tag.
- [ ] `traces` Mongo collection mirrors LangSmith spans for offline replay.
- [ ] Smoke script `scripts/smoke.sh` exits 0 in < 90 s.
- [ ] CI badge on README is green; `uv run pytest` passes locally on macOS + Linux.
- [ ] Submission packet includes Atlas cluster ID, GitHub repo, demo video, and this file as evidence of test rigour.

---

**Definition of Done for the hackathon submission:** every box above is ticked, `uv run pytest` is green, `scripts/smoke.sh` is green, and `11-demo-script.md` §6 dry-run checklist hit ≥ 23/25 on three consecutive rehearsals.
