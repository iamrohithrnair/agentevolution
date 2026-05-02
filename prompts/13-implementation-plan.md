# 13 · Implementation Plan

> Companion to `00-overview.md` and `01-architecture.md`. Phase ordering is **mandatory**; do not skip ahead.
> Every "Exit criteria" line maps to an acceptance test in `12-acceptance-tests.md`.

This file specifies:

1. The phase-by-phase plan from **Phase 0 (setup)** through **Phase 8 (polish)**, with goals, files created, exit criteria, and dependencies.
2. The full `pyproject.toml` for the python service (uv-managed).
3. The `web/package.json` for the Next.js 15 / React 19 frontend.
4. The `.env.example`.
5. The one-command demo invocation.

---

## 1 · Phase Ordering Overview

```
Phase 0  Setup & infrastructure          (no agents yet, no UI)
Phase 1  Data model & seeds              (Mongo is the brain — fill it first)
Phase 2  Tools layer                     (pure, idempotent, Mongo-backed @tool functions)
Phase 3  Agents & LangGraph              (Supervisor + 16 specialists, MongoDBSaver)
Phase 4  FastAPI + WebSocket realtime    (REST + change-stream fanout)
Phase 5  Next.js 15 dashboard            (light-mode UI, map, chat)
Phase 6  Voice layer                     (LiveKit worker, Deepgram, ElevenLabs)
Phase 7  Self-evolution proof            (Take-1 vs Take-3 protocol)
Phase 8  Polish, demo rehearsal, recovery rehearsal
```

Dependencies (DAG):

```
P0 ─► P1 ─► P2 ─► P3 ─┬─► P4 ─► P5 ─► P6
                      └────────────────► P7 ─► P8
```

---

## 2 · Phase 0 — Setup & Infrastructure

**Goals**

- Working Atlas Sandbox cluster (or `mongodb:7` replica set in docker-compose for local).
- `uv` venv with all python deps resolvable.
- `next@15` workspace bootstrapped, Tailwind v4 + shadcn/ui registered.
- All required API keys staged in `.env`.
- CI lane: `uv run pytest -q` and `pnpm -C web build` both green on an empty smoke test.

**Files created**

- `pyproject.toml` (see §6).
- `uv.lock` (committed).
- `.env.example` (see §8).
- `.gitignore`, `.editorconfig`.
- `docker-compose.yml` (mongodb replica set, api stub, livekit-worker stub, web stub).
- `Makefile` with targets: `bootstrap`, `seed`, `api`, `web`, `livekit`, `demo`, `test`.
- `web/package.json` (see §7), `web/next.config.ts`, `web/postcss.config.mjs`, `web/tailwind.config.ts`, `web/app/layout.tsx`, `web/app/page.tsx` (placeholder landing).
- `src/dronan/__init__.py`, `src/dronan/config.py` (Pydantic Settings).
- `src/dronan/db.py` (Motor client factory with `tlsAllowInvalidCertificates=False`).
- `tests/test_smoke.py` — asserts `db.command('ping') == {"ok":1}`.

**Exit criteria**

- `make bootstrap` completes with no errors on a clean checkout.
- `uv run python -c "from dronan.db import get_db; import asyncio; asyncio.run(get_db().command('ping'))"` returns `{ok:1}`.
- `pnpm -C web dev` serves the placeholder landing at `/` in light mode.
- `tests/test_smoke.py` passes.

**Dependencies**: none.

---

## 3 · Phase 1 — Data Model & Seeds

**Goals**

- Every collection from `02-mongodb-data-model.md` exists with the documented `$jsonSchema` validator and indexes.
- All seed corpora are loaded **idempotently**.
- Atlas Vector Search indexes (`mission_memory_vec`, `agent_skills_vec`) are created and reachable.

**Files created**

- `seeds/create_indexes.py` — creates 2dsphere, time-series, Atlas Search, Atlas Vector Search indexes via `pymongo` and the Atlas Admin API for vector indexes.
- `seeds/seed_facilities.py` — loads `data/facilities.xlsx` (489 rows) + the 9 hardcoded `LOCATIONS` from the original `DroneFleet/config.py`. Inserts to `facilities` with 2dsphere `location`.
- `seeds/seed_no_fly_zones.py` — FAA P-56, PDOK Netherlands, UK CAA, plus a synthetic east-London TFR for the demo.
- `seeds/seed_regulations.py` — air-law profiles → `regulations` and embedded into `mission_memory` with `kind:"regulation"`.
- `seeds/seed_synthetic_emergencies.py` — `data/synthetic_emergencies.csv` (44 118 rows) into `synthetic_emergencies` with bulk inserts of 1000.
- `seeds/seed_drones.py` — Drone1, Drone2, Drone3 at `Depot` with full status fields.
- `seeds/seed_demo_memory.py` — pre-seeds 3 cards for the canonical scenario so Take-1 has *some* recall surface.
- `seeds/seed_agent_skills.py` — placeholder; real registration happens at agent boot in Phase 3 but this guarantees the index exists.

**Exit criteria**

- `make seed` is idempotent (re-running yields zero diffs).
- `db.facilities.count_documents({}) == 498`.
- `db.command("listSearchIndexes", "mission_memory")` shows `mission_memory_vec` with `status:"READY"`.
- `tests/test_seeds.py` passes.

**Dependencies**: P0.

---

## 4 · Phase 2 — Tools Layer

**Goals**

- Every tool from the agent topology table (`01-architecture.md §2`) implemented as an idempotent `@tool` with `tool_call_log` writes.
- OR-Tools VRP solver wired against `facilities` and `no_fly_zones` (no in-memory shortcuts).
- Voyage AI embedding helper with `embedding_cache` collection (SHA-256 keyed).
- `MongoDBAtlasVectorSearch` retriever helper.
- 100 % unit-test coverage on tool wrappers (idempotency, error path, OTEL span).

**Files created**

- `src/dronan/tools/__init__.py` — exports the registry.
- `src/dronan/tools/_decorator.py` — `mongo_tool` wrapper (see `01-architecture.md §8.1`).
- `src/dronan/tools/facilities.py` — `search_facilities`, `get_facility`.
- `src/dronan/tools/geofence.py` — `check_route_safety` (`$geoIntersects` per segment).
- `src/dronan/tools/route_planner.py` — `compute_route`, `recompute_route`.
- `src/dronan/tools/weather.py` — `get_weather`, `simulate_weather_event`.
- `src/dronan/tools/payload.py` — `cold_chain_predict`, `assemble_manifest`.
- `src/dronan/tools/preflight.py` — `run_preflight`.
- `src/dronan/tools/memory.py` — `vector_search`, `embed_and_store`, `summarise_for_planner`.
- `src/dronan/tools/drone_control.py` — `MockController`, optional `AirSimAdapter`, optional `PX4Adapter`.
- `src/dronan/tools/vision.py` — `detect_obstacles` (YOLO via `ultralytics`), `save_frame` (GridFS bucket `frames`).
- `src/dronan/tools/audit.py` — `record_signature` (Queryable Encryption fields).
- `src/dronan/tools/analytics.py` — `aggregate_metrics`, `generate_report` (PDF → GridFS bucket `reports`).
- `src/dronan/embeddings/voyage.py` — `voyage_embed(text, dim=1024)` with caching; supports `dim in {256, 1024, 2048}` (Matryoshka).
- `tests/test_tools_*.py` — one per tool.

**Exit criteria**

- `tests/test_route_planner.py`, `tests/test_geofence_geo.py`, `tests/test_vector_recall.py` all pass.
- Same idempotency key on `compute_route` returns the cached result with **zero** OR-Tools invocations on the second call (verified by patching).
- `embedding_cache` populated; second call to `voyage_embed` for the same text takes <2 ms.

**Dependencies**: P1.

---

## 5 · Phase 3 — Agents & LangGraph

**Goals**

- 17 agents implemented; each registers a SkillCard at boot.
- LangGraph `StateGraph` compiled with `MongoDBSaver` checkpointer.
- Supervisor uses **vector search over `agent_skills`** for peer discovery (no `if/elif`).
- A2A messages persisted in `agent_messages`.

**Files created**

- `src/dronan/agents/_base.py` — `SkillCard` Pydantic model, `register_skill()`.
- `src/dronan/agents/{supervisor,interpreter,memory_agent,planner,weather_agent,geofence_agent,preflight_agent,payload_agent,dispatch,vision_agent,replanner,anomaly,deconfliction,narrator,analyst,reflection,demand_forecast}.py`.
- `src/dronan/graph.py` — `MissionPlanState` TypedDict, node wiring, conditional edges, recursion limit.
- `src/dronan/memory/chat_history.py` — `MongoDBChatMessageHistory` factory.
- `src/dronan/memory/vector_store.py` — `MongoDBAtlasVectorSearch` factory.
- `src/dronan/memory/summary_buffer.py` — custom `MongoDBConversationSummaryBufferMemory`.
- `tests/test_supervisor_routing.py` — held-out 20-task set; asserts top-1 agent ≥ 0.9.
- `tests/test_checkpoint_recovery.py` — invokes graph, kills mid-flight (simulated by raising), resumes from checkpoint, asserts no duplicate tool calls.

**Exit criteria**

- `tests/test_supervisor_routing.py` ≥ 0.9 top-1 (SM-10).
- `tests/test_checkpoint_recovery.py` passes (SM-5 < 8 s).
- `agent_skills` contains 17 documents after worker boot.
- Killing the worker mid-mission and restarting resumes from the last checkpoint without duplicate `tool_call_log` entries.

**Dependencies**: P2.

---

## 6 · Phase 4 — FastAPI + WebSocket Realtime

**Goals**

- REST surface for the operator UI: `/chat`, `/missions`, `/deliveries`, `/drones`, `/facilities`, `/weather`, `/nofly`, `/memory`, `/reports`.
- WebSocket fanout on the watched collections per `01-architecture.md §4`.
- `/internal/replan` endpoint invoked by Atlas Trigger.
- LiveKit token mint endpoint.

**Files created**

- `src/dronan/api/main.py` — FastAPI app factory; CORS for `localhost:3000` and Vercel domain.
- `src/dronan/api/routes/{chat,missions,deliveries,drones,facilities,weather,nofly,memory,reports,livekit_token}.py`.
- `src/dronan/api/ws.py` — change-stream tail per collection.
- `src/dronan/api/internal.py` — `/internal/replan`, `/internal/cold_chain_breach`, `/internal/low_battery`.
- `src/dronan/triggers/weather_reroute.js` — Atlas Trigger function (deployed via `atlas` CLI in Phase 8).
- `src/dronan/triggers/cold_chain.js`.
- `tests/test_change_stream.py` — insert into `flight_logs` → WS message arrives within 500 ms.

**Exit criteria**

- `tests/test_change_stream.py` passes (SM-8).
- Atlas Trigger `weather_reroute` posts to `/internal/replan` and a ReplannerAgent run completes within 3 s P95 (SM-4).
- All REST routes return 200 on the seeded data.

**Dependencies**: P3.

---

## 7 · Phase 5 — Next.js 15 Dashboard

**Goals**

- Light-mode design system (white/off-white surfaces, slate text, accent indigo, medical-red `#DC2626` for emergencies).
- App Router structure with `(app)/dashboard`, `(app)/deploy`, `(app)/logs`, `(app)/analytics`, `(app)/settings`.
- Real-time map (Leaflet base + deck.gl arcs + animated drone markers).
- Reasoning Stream, Memory Inspector, Reflection Feed panels (all WS-driven).
- Chat panel (text fallback if voice not in this phase).

**Design tokens (Tailwind v4 `@theme` block in `web/app/globals.css`)**

```css
@theme {
  --color-bg: #ffffff;
  --color-surface: #f7f8fa;
  --color-surface-2: #eef0f4;
  --color-fg: #0f172a;            /* slate-900 */
  --color-fg-muted: #475569;       /* slate-600 */
  --color-border: #e2e8f0;         /* slate-200 */
  --color-accent: #4f46e5;         /* indigo-600 */
  --color-accent-2: #6366f1;       /* indigo-500 */
  --color-medical: #dc2626;        /* red-600 */
  --color-success: #15803d;        /* green-700 */
  --font-sans: "Inter", "ui-sans-serif", system-ui;
  --font-mono: "JetBrains Mono", ui-monospace;
}
```

**Files created**

- `web/app/(app)/layout.tsx` — sidebar + topbar, light mode default.
- `web/app/(app)/dashboard/page.tsx` — map + chat + reasoning stream.
- `web/app/(app)/deploy/page.tsx` — delivery composer.
- `web/app/(app)/logs/page.tsx` — flight logs, audit trail.
- `web/app/(app)/analytics/page.tsx` — metrics from `experiments`.
- `web/app/(app)/settings/page.tsx` — operator preferences (writes `mission_memory` cards `kind:"operator_pref"`).
- `web/components/dashboard/{MapView,ReasoningStream,MemoryInspector,ReflectionFeed,ChatPanel,VoiceHUD,FlightLog,WeatherPanel,MetricsPanel,PayloadStatus,DroneScene}.tsx`.
- `web/lib/{api.ts,ws.ts,livekit.ts,types.ts}`.
- `web/components/ui/*` — shadcn/ui registered components.

**Exit criteria**

- Map renders 3 drones, 9 facilities, the 4 demo no-fly polygons in light mode.
- Submitting a chat message dispatches a real mission visible in the map within 3 s.
- Memory Inspector shows the 5 retrieved cards on each dispatch.
- Reflection Feed updates live when `mission_memory` receives an insert (Change Stream → WS).

**Dependencies**: P4.

---

## 8 · Phase 6 — Voice Layer

**Goals**

- LiveKit Agents Worker boots with Deepgram Nova-3 STT, ElevenLabs Turbo v2.5 TTS, Silero VAD.
- LangGraph supervisor wired as the LLM node.
- NarratorAgent subscribes to `flight_logs` Change Stream and emits TTS via the LiveKit room.
- VoiceHUD in the UI shows live transcript + waveform.

**Files created**

- `src/dronan/voice/livekit_worker.py` — `entrypoint(ctx)` builds an `AgentSession` with the three plugins; on `on_user_turn_completed`, invoke the LangGraph supervisor.
- `src/dronan/voice/narrator_stream.py` — async loop tailing `flight_logs` change stream, debouncing, calling `session.say(...)`.
- `src/dronan/voice/prompts.py` — system prompt for "Mission Control" persona (calm, authoritative, no filler).
- `web/lib/livekit.ts` — token fetch + room connect.
- `web/components/dashboard/VoiceHUD.tsx` — push-to-talk + always-on toggle, transcript ribbon, ElevenLabs waveform via `react-audio-visualize`.
- `tests/test_livekit_smoke.py` — feeds a fixture WAV; asserts a non-empty TTS audio chunk back.

**Exit criteria**

- Voice round-trip P95 < 900 ms (SM-6).
- Operator can dispatch the canonical scenario by voice end-to-end.
- NarratorAgent debounces correctly: only one spoken alert per `flight_logs.event class` within a 5 s window.
- `--text-mode` CLI flag bypasses voice for the no-key fallback.

**Dependencies**: P5.

---

## 9 · Phase 7 — Self-Evolution Proof

**Goals**

- The canonical scenario is encoded as a deterministic script (no LLM nondeterminism in the inputs).
- Take-1 → Take-2 → Take-3 produces a measurable, MongoDB-backed improvement.
- Reflection Feed shows the cards written between takes.
- `experiments` collection holds per-take aggregates.

**Files created**

- `src/dronan/demo/scenario.py` — the scripted dispatch (locations, supplies, priorities, the storm trigger time, the obstacle injection time).
- `src/dronan/demo/runner.py` — invokes the scenario N times against a clean `missions` slate; preserves `mission_memory` across takes.
- `src/dronan/demo/charts.py` — produces an SVG chart (no Recharts dependency on the server) of `actual_time_s` per take.
- `tests/test_self_evolution.py` — asserts `experiments.find({take:3})[0].actual_time_s < experiments.find({take:1})[0].actual_time_s * 0.9` (SM-1).
- `tests/test_memory_recall.py` — precision @ 5 ≥ 0.8 (SM-3).

**Exit criteria**

- Take-3 mission time ≤ 90 % of Take-1 (SM-1).
- ≥6 cards written to `mission_memory` per take (SM-2).
- Chart renders in `/analytics` and matches the test data within tolerance.

**Dependencies**: P3 (does not need P5/P6 to test, but those are needed for the live-demo surface).

---

## 10 · Phase 8 — Polish, Demo Rehearsal, Recovery Rehearsal

**Goals**

- Single-command `make demo` boots Atlas check, seeds, API, LiveKit worker, Next.js dev server, opens the browser to `/dashboard`.
- 4-minute demo script rehearsed end-to-end at least 5 times on conference-grade Wi-Fi.
- **Recovery rehearsal**: `kill -9` the LiveKit worker mid-mission; replacement worker resumes the LangGraph thread via `MongoDBSaver`; operator continues the conversation.
- Pitch deck: 5 slides, hand-off to deck owner.
- Pre-recorded 90 s screen capture as failover.

**Files created**

- `scripts/demo.sh` — orchestrates the boot.
- `scripts/rehearse_recovery.sh` — kills the worker at T+90s and asserts resume time.
- `docs/DEMO_SCRIPT.md` — the verbatim presenter script (mirrors `REBUILD_PROMPT.md §8`).
- `docs/PITCH_DECK_OUTLINE.md`.
- `assets/demo-fallback.mp4` — the screen capture.

**Exit criteria**

- `make demo` boots cold in ≤ 60 s on a fresh laptop.
- Recovery rehearsal: time-to-first-new-tool-call after worker kill ≤ 8 s (SM-5).
- Each of SM-1 through SM-10 verified within the 24 hours preceding the demo.

**Dependencies**: P6, P7.

---

## 11 · Definition of Done (per phase, mapped to acceptance tests)

| Phase | DoD | Maps to acceptance tests in `12-acceptance-tests.md` |
|---|---|---|
| P0 | `make bootstrap`, `tests/test_smoke.py` | AT-0.1 |
| P1 | seeds idempotent, vector indexes READY | AT-1.1 (test_seeds), AT-1.2 (vector index reachable) |
| P2 | tools idempotent, vector recall correct | AT-2.1 (test_route_planner), AT-2.2 (test_geofence_geo), AT-2.3 (test_vector_recall) |
| P3 | supervisor routes via vector, checkpointer recovers | AT-3.1 (test_supervisor_routing ≥ 0.9), AT-3.2 (test_checkpoint_recovery) |
| P4 | change-stream → WS in <500 ms | AT-4.1 (test_change_stream), AT-4.2 (trigger replan latency) |
| P5 | live map + memory inspector working | AT-5.1 (Playwright dashboard smoke) |
| P6 | voice round-trip < 900 ms | AT-6.1 (test_livekit_smoke) |
| P7 | Take-3 < 90% Take-1 | AT-7.1 (test_self_evolution), AT-7.2 (test_memory_recall) |
| P8 | recovery in <8 s, `make demo` cold boot <60 s | AT-8.1 (rehearse_recovery), AT-8.2 (boot timer) |

---

## 12 · `pyproject.toml`

> Place at repo root. Managed by `uv`. **Never** `pip install` directly.

```toml
[project]
name = "dronan"
version = "0.1.0"
description = "Voice-first, memory-augmented multi-agent platform for medical drone logistics"
requires-python = ">=3.11,<3.13"
readme = "README.md"
license = { text = "MIT" }
authors = [{ name = "Dronan Team" }]

dependencies = [
  # MongoDB
  "motor>=3.6.0",
  "pymongo[srv,encryption]>=4.10.0",
  # LangChain + LangGraph
  "langchain>=0.3.0",
  "langchain-core>=0.3.0",
  "langchain-community>=0.3.0",
  "langchain-openai>=0.2.0",
  "langchain-mongodb>=0.2.0",
  "langchain-voyageai>=0.1.4",
  "langgraph>=0.2.40",
  "langgraph-checkpoint-mongodb>=0.1.0",
  "voyageai>=0.3.0",
  # LLM client
  "openai>=1.50.0",
  # FastAPI + ASGI
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.32.0",
  "websockets>=13.0",
  "python-multipart>=0.0.12",
  # Routing & geo
  "ortools>=9.11.4210",
  "shapely>=2.0.6",
  # Models & validation
  "pydantic>=2.9.0",
  "pydantic-settings>=2.6.0",
  # Voice
  "livekit-agents>=0.11.0",
  "livekit-plugins-deepgram>=0.7.0",
  "livekit-plugins-elevenlabs>=0.7.0",
  "livekit-plugins-silero>=0.7.0",
  # Vision
  "ultralytics>=8.3.0",
  "pillow>=10.4.0",
  # Optional integrations
  "googlemaps>=4.10.0",
  # Utilities
  "python-dotenv>=1.0.1",
  "openpyxl>=3.1.5",
  "pandas>=2.2.3",
  "numpy>=2.1.0",
  "httpx>=0.27.2",
  "structlog>=24.4.0",
  "opentelemetry-api>=1.27.0",
  "opentelemetry-sdk>=1.27.0",
  "opentelemetry-instrumentation-fastapi>=0.48b0",
  "opentelemetry-instrumentation-pymongo>=0.48b0",
  "reportlab>=4.2.5",     # PDFs to GridFS
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3.3",
  "pytest-asyncio>=0.24.0",
  "pytest-cov>=5.0.0",
  "ruff>=0.6.9",
  "mypy>=1.11.2",
  "types-requests",
  "ipython",
]
airsim = ["airsim>=1.8.1"]
px4 = ["pymavlink>=2.4.41"]

[tool.uv]
package = true
default-groups = ["dev"]

[tool.uv.sources]
# pin nothing third-party here unless we need a fork

[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/dronan"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-q --strict-markers"
```

---

## 13 · `web/package.json`

```json
{
  "name": "dronan-web",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev --turbopack",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "next": "15.1.0",
    "react": "19.0.0",
    "react-dom": "19.0.0",
    "tailwindcss": "^4.0.0",
    "@tailwindcss/postcss": "^4.0.0",
    "postcss": "^8.4.47",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.5.4",
    "@radix-ui/react-dialog": "^1.1.2",
    "@radix-ui/react-tabs": "^1.1.1",
    "@radix-ui/react-tooltip": "^1.1.4",
    "@radix-ui/react-toast": "^1.2.2",
    "@radix-ui/react-popover": "^1.1.2",
    "@radix-ui/react-scroll-area": "^1.2.1",
    "@radix-ui/react-slot": "^1.1.0",
    "framer-motion": "^11.11.0",
    "leaflet": "^1.9.4",
    "react-leaflet": "^4.2.1",
    "deck.gl": "^9.0.0",
    "@deck.gl/react": "^9.0.0",
    "@deck.gl/layers": "^9.0.0",
    "@deck.gl/geo-layers": "^9.0.0",
    "three": "^0.169.0",
    "@react-three/fiber": "^8.17.7",
    "@react-three/drei": "^9.114.0",
    "livekit-client": "^2.5.7",
    "@livekit/components-react": "^2.7.4",
    "@livekit/components-styles": "^1.1.4",
    "lucide-react": "^0.454.0",
    "recharts": "^2.13.0",
    "sonner": "^1.5.0",
    "zod": "^3.23.8",
    "swr": "^2.2.5"
  },
  "devDependencies": {
    "@types/node": "^22.7.5",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@types/leaflet": "^1.9.12",
    "@types/three": "^0.169.0",
    "typescript": "^5.6.2",
    "eslint": "^9.12.0",
    "eslint-config-next": "15.1.0",
    "@playwright/test": "^1.48.0"
  }
}
```

---

## 14 · `.env.example`

```dotenv
# ──────────────────────────────────────────────────────────
# MongoDB Atlas (system of record)
# ──────────────────────────────────────────────────────────
MONGODB_URI=mongodb+srv://USER:PASS@cluster0.xxxx.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=dronan
MONGODB_REPL_SET=                     # leave blank for Atlas; "rs0" for local docker

# Atlas Admin (for vector index management via API)
ATLAS_PROJECT_ID=
ATLAS_PRIVATE_KEY=
ATLAS_PUBLIC_KEY=
ATLAS_CLUSTER_NAME=Cluster0

# ──────────────────────────────────────────────────────────
# Voyage AI (embeddings — default 1024-dim voyage-3-large)
# ──────────────────────────────────────────────────────────
VOYAGE_API_KEY=
VOYAGE_MODEL=voyage-3-large
VOYAGE_DIM=1024                       # 256 | 1024 | 2048 (Matryoshka)

# ──────────────────────────────────────────────────────────
# OpenAI (reasoning only)
# ──────────────────────────────────────────────────────────
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
LLM_PLANNER_MODEL=gpt-4o
LLM_REFLECTION_MODEL=gpt-4o-mini

# ──────────────────────────────────────────────────────────
# Voice stack
# ──────────────────────────────────────────────────────────
LIVEKIT_URL=wss://YOUR-PROJECT.livekit.cloud
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=

ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=                  # "Mission Control" voice
ELEVENLABS_MODEL_ID=eleven_turbo_v2_5

DEEPGRAM_API_KEY=
DEEPGRAM_MODEL=nova-3

# ──────────────────────────────────────────────────────────
# Optional integrations
# ──────────────────────────────────────────────────────────
OPENWEATHER_API_KEY=                  # leave blank to use synthetic generator
GOOGLE_MAPS_API_KEY=                  # leave blank to skip map tile providers
AIRSIM_ENABLED=false
PX4_ENABLED=false

# ──────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────
APP_ENV=demo                          # demo | dev | prod
API_PORT=8000
WEB_PORT=3000
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_WS_BASE=ws://localhost:8000
LOG_LEVEL=INFO

# ──────────────────────────────────────────────────────────
# Encryption (Atlas Queryable Encryption)
# ──────────────────────────────────────────────────────────
QE_KMS_PROVIDER=local                 # local | aws | gcp | azure
QE_LOCAL_KEY=                         # base64 96-byte key for local dev
```

---

## 15 · One-Command Demo Invocation

```bash
make demo
```

Behind that target (`Makefile`):

```makefile
.PHONY: bootstrap seed api livekit web demo test

bootstrap:
	uv sync
	cd web && pnpm install

seed:
	uv run python -m seeds.create_indexes
	uv run python -m seeds.seed_facilities
	uv run python -m seeds.seed_no_fly_zones
	uv run python -m seeds.seed_regulations
	uv run python -m seeds.seed_synthetic_emergencies
	uv run python -m seeds.seed_drones
	uv run python -m seeds.seed_demo_memory

api:
	uv run uvicorn dronan.api.main:app --host 0.0.0.0 --port $${API_PORT:-8000} --reload

livekit:
	uv run python -m dronan.voice.livekit_worker dev

web:
	cd web && pnpm dev

demo: bootstrap seed
	@bash scripts/demo.sh

test:
	uv run pytest -q
	cd web && pnpm typecheck && pnpm playwright test
```

`scripts/demo.sh` (excerpt):

```bash
#!/usr/bin/env bash
set -euo pipefail

# Verify Atlas reachable
uv run python -c "from dronan.db import ping; import asyncio; asyncio.run(ping())"

# Start API + LiveKit worker + Next.js, all backgrounded
( make api  > .logs/api.log  2>&1 & echo $! > .pids/api.pid )
( make livekit > .logs/livekit.log 2>&1 & echo $! > .pids/livekit.pid )
( make web > .logs/web.log 2>&1 & echo $! > .pids/web.pid )

# Wait until healthy
uv run python scripts/wait_healthy.py

# Open the dashboard
open "http://localhost:${WEB_PORT:-3000}/dashboard"

echo "Ready. Press Ctrl-C to tear down."
trap 'kill $(cat .pids/*.pid)' EXIT
wait
```

---

## 16 · Cross-References

| If you are working on… | Read first |
|---|---|
| schemas, indexes, validators | `02-mongodb-data-model.md` |
| LangGraph nodes, MissionPlanState, prompts | `03-agents-langgraph.md` |
| Voyage AI dims, retriever, summary buffer | `04-memory-and-rag.md` |
| `@tool` signatures and idempotency keys | `05-tools-mcp.md` |
| LiveKit worker, voice prompts | `06-voice-livekit.md` |
| Next.js App Router structure, design tokens | `07-frontend-nextjs.md` |
| watched collections, WS topics | `08-realtime-change-streams.md` |
| mock controller, weather generator | `09-simulation-and-mocks.md` |
| canonical scenario, Take-1 vs Take-3 protocol | `10-self-evolution-demo.md` |
| Queryable Encryption, RBAC, secret hygiene | `11-security-privacy.md` |
| pytest suite, traceability matrix | `12-acceptance-tests.md` |

When in doubt: the file that owns a contract is the one that owns the change. Update the owning file, then ripple.
