# 00 · Overview — Dronan / Agentic Evolution

> **Project codename:** `dronan-mongo`
> **Hackathon:** MongoDB Agentic Evolution Hackathon (London, May 2026 — co-hosted with LangChain & NVIDIA)
> **Stakes:** £15,000 grand prize + London Founder House residency
> **Audience for this file:** every engineer, designer, and pitch-deck writer on the team — read this **first**, then move to `01-architecture.md`, `02-mongodb-data-model.md`, …, `13-implementation-plan.md`.

---

## 1 · North Star

Build the **first voice-first, memory-augmented, self-evolving multi-agent platform for medical drone logistics**, where every agent decision, reflection, and improvement is durably persisted in **MongoDB Atlas**, every reasoning thread is **checkpointed via `langgraph-checkpoint-mongodb`**, every long-term lesson is **embedded with Voyage AI `voyage-3-large` and recalled via `$vectorSearch`**, and every operator interaction is **mediated by a LiveKit room with ElevenLabs Turbo v2.5 narration and Deepgram Nova-3 transcription**.

When the judges leave the room, they should not be able to point at any single component and say "that part wasn't MongoDB-native, that part wasn't LangGraph, that part was a mock". Every claim in the demo must be traceable to a document in Atlas.

## 2 · Elevator Pitch (60 words)

> Dronan is a multi-agent control tower for medical drone fleets. Operators speak to a LiveKit room; a LangGraph supervisor delegates to seventeen specialist agents that plan, reroute, narrate, and reflect — all sharing a MongoDB Atlas brain. After every mission a **ReflectionAgent** writes new memory cards back to Atlas Vector Search, and the **next** mission is provably faster. We end the demo by replaying the same scenario and watching it win by 11 %.

## 3 · Hackathon Track Fit

The hackathon scores submissions across four tracks. We deliberately straddle all four so judges in any rubric can vote for us.

| Track | How Dronan lands it | Concrete evidence in the demo |
|---|---|---|
| **AI Agent Integrations & Orchestration** | LangGraph `StateGraph` with a SupervisorAgent and 16 specialists, each invoked over MCP-style tool calls. Agent-to-agent (A2A) routing is dynamic — peers are selected via vector search over an `agent_skills` registry, not hard-coded. | Live mission shows Supervisor → Interpreter → Memory → Planner → Geofence → Weather → Dispatch → Replanner cascade in <4 s, with every transition rendered in the **Reasoning Stream** panel. |
| **Memory Systems** | Four memory tiers: **short-term** (`MongoDBChatMessageHistory`), **episodic** (`mission_memory` reflections), **semantic** (regulations + facility intel pre-embedded), **procedural** (planner prompt augmented from top-k retrieval). All tiers live in MongoDB. Embeddings via Voyage AI `voyage-3-large` (1024 dims default; document Matryoshka 2048 / 256 modes). | Memory Inspector panel lights up with the 5 retrieved cards on every dispatch. Cards expand to show cosine score, region filter, and origin mission. |
| **Self-Evolution & Learning** | `ReflectionAgent` runs unconditionally on every mission completion, summarises *what worked / what failed*, embeds, and writes ≥6 cards to `mission_memory`. Planner prompt template explicitly injects recalled lessons. | We run **Demo Take 1** vs **Demo Take 3** of the identical scenario and chart the deltas: distance −8 %, ETA −11 %, reroutes −2, battery −7 %. Recorded in `experiments` collection for the judges to query live. |
| **Vertical Solution — Healthcare** | End-to-end medical logistics: cold-chain payload tracking (blood, insulin, vaccine), chain-of-custody audit (write-once `audit_trail`), voice-signature recipient confirmation, NHS-formatted PDF reports stored in GridFS, regulation-aware planning (UK CAA + EASA + FAA Part 107). | The demo dispatches O-negative blood + a defibrillator + a vaccine kit across east London facilities seeded from real NHS hospital data. |

### Judging-criteria mapping

The published hackathon weights are **Live Demo 45 %, Creativity 35 %, Impact 20 %**.

| Weight | Where we attack it |
|---|---|
| **Live Demo 45 %** | Phase 8 polish budget is largest. Single-command boot (`make demo`). 4-minute scripted run with voice + map + memory inspector + reflection feed visible simultaneously. Recovery rehearsal: kill the agent worker mid-flight; checkpointer resumes from the last LangGraph thread state. |
| **Creativity 35 %** | (a) **Agent Skill Registry** with vector search for peer discovery, (b) **MongoDB checkpointed multi-agent recovery**, (c) **Self-evolving memory** that *demonstrably* improves planning, (d) **Voice-first ops** that judges literally talk to. None of these are commodity. |
| **Impact 20 %** | NHS-applicable, disaster-relief-applicable, low-resource-country-applicable. Cold-chain integrity quantified. £/life-year ROI in slide 5. |

---

## 4 · Why We Win on Creativity

Four ideas, none of which are stock LangGraph tutorials. They are listed here so every PR, prompt, and slide reinforces them.

### 4.1 Agent Skill Registry (peer discovery via vector search)

Every agent on boot **inserts a "skill card"** into the `agent_skills` collection with: capability description, supported intents, side-effect class, average latency, success ratio. The `description` field is embedded with `voyage-3-large`. When the SupervisorAgent receives a sub-task, it does a **filtered `$vectorSearch`** over `agent_skills` to pick the right peer instead of relying on a static `if/elif` router. Cold-start cost is ≤30 ms; agents can be added without changing supervisor code.

This is the answer to *"how do agents convey their skills, identify suitable peers for a sub-task?"* — see `01-architecture.md §7`.

### 4.2 Checkpointed Multi-Agent Recovery (`MongoDBSaver`)

Every LangGraph thread (`thread_id = mission_id`) commits its node state to MongoDB through `langgraph-checkpoint-mongodb`'s `MongoDBSaver`. If any worker crashes — the FastAPI process, the LiveKit worker, the OS — the same thread can be resumed mid-mission with **zero replay of completed tool calls**. Tool calls are themselves logged to `tool_call_log` with an idempotency key so retries are safe.

We will **rehearse a kill -9 mid-flight** as part of the demo. Judges will see the operator speak again and the agent pick up from the exact reasoning frame.

### 4.3 Self-Evolving Memory

This is the heart of the pitch. After every mission `ReflectionAgent` writes ≥6 typed memory cards (`reflection`, `incident`, `route_lesson`, `weather_lesson`, `facility_intel`, `operator_pref`) and the next planning step retrieves them by region/weather/kind filters. We *prove* improvement by re-running the identical scenario and showing the metric delta on screen.

### 4.4 Voice-First Operator Surface

LiveKit + ElevenLabs + Deepgram is not a gimmick — it is the **interaction model that maps best to high-stakes ops**. Surgeons, paramedics, and disaster-response controllers cannot click. The demo is judged on flow, and a hands-free flow is more compelling than a click-driven one.

---

## 5 · Impact Narrative

### 5.1 NHS — the immediate beachhead

- The NHS already runs blood-courier drones (Apian, NHS Blood and Transplant trials in Northumbria, 2023). Cold-chain failure rates are non-trivial; chain-of-custody is paper-based in many trusts.
- Dronan plugs in as the **mission control plane** above any drone vendor. Atlas time-series collections give per-second cold-chain telemetry; `audit_trail` (Queryable Encryption on recipient PII) replaces clipboards.
- ROI: a single avoided emergency O-negative re-issue (~£140 net of waste) per drone per week pays for the platform.

### 5.2 Disaster relief

- After flooding or earthquake, road networks degrade faster than airspace. The `no_fly_zones` collection accepts dynamic TFRs; the PlannerAgent re-solves under live constraints.
- Demand-forecast pre-positioning (`DemandForecastAgent` over `synthetic_emergencies`, 44 118 rows) lets responders move drones to high-probability draw-down points hours before requests arrive.

### 5.3 Low-resource countries

- Zipline-style fixed-wing networks in Rwanda and Ghana proved the model. The bottleneck now is **decision software** rather than airframes.
- A MongoDB-only architecture (no GPU at the edge, no cloud-vendor lock-in) is deployable on a single Atlas free-tier cluster + a Raspberry Pi running the FastAPI worker.

### 5.4 Quantified outcomes (claims we are willing to make on stage)

| Metric | Baseline (ground couriers) | Dronan target |
|---|---|---|
| Median delivery time, urban 5 km | 27 min | **8 min** |
| Cold-chain breach rate (blood) | 4.3 % | **<0.5 %** (continuous Atlas time-series alerting) |
| Chain-of-custody dispute rate | 1.1 % | **0** (immutable `audit_trail` + voice signature) |
| Plan re-issue cost on weather change | manual, ~6 min | **<10 s** (Atlas Trigger → ReplannerAgent) |

---

## 6 · Glossary (Project-Specific Terms)

These terms appear across all 13 prompt files. Bind them now.

| Term | Definition | Where it lives |
|---|---|---|
| **Mission** | One end-to-end delivery operation, possibly multi-stop, by one or more drones. Lifecycle: `pending → planning → dispatched → in_flight → completed | failed | aborted`. | `missions` collection |
| **Reflection** | Structured post-mission summary written by `ReflectionAgent`. Always produces ≥6 typed memory cards. | `mission_memory` (`kind:"reflection"` and friends) |
| **Skill Card** | A document describing one agent's capability surface, embedded for peer discovery. | `agent_skills` |
| **Memory Card** | Any document in `mission_memory` retrievable via `$vectorSearch`. Typed by `kind`. | `mission_memory` |
| **Lesson** | A specific actionable insight inside a Reflection (e.g., *"avoid west corridor when wind > 12 m/s"*). Stored as a list under `metadata.lessons`. | `mission_memory.metadata.lessons[]` |
| **Plan State** | The TypedDict shared across LangGraph nodes during a mission (`MissionPlanState` in `src/dronan/graph.py`). | In-memory + checkpointed |
| **Checkpoint** | A `MongoDBSaver` snapshot of a LangGraph thread, keyed by `thread_id = mission_id`. | `checkpoints` (managed by `langgraph-checkpoint-mongodb`) |
| **Reasoning Stream** | The live UI panel that tails the `traces` collection via Change Streams and renders supervisor decisions. | `traces` + `/ws/traces/{mission_id}` |
| **Skill Registry** | The vector-searchable index over `agent_skills` used by Supervisor for peer discovery. | Atlas Vector Search index `agent_skills_vec` |
| **Take** | A demo run of the canonical scenario. Take 1 is the cold run; Take 3 must beat Take 1 by ≥10 % mission time. | `experiments` collection |
| **Cold Chain** | The temperature-integrity contract on a payload (e.g., blood at 2–6 °C). Tracked per second in `telemetry`. | `telemetry.payload_temp_c` |

---

## 7 · Success Metrics (the bar we hold ourselves to)

These are not aspirational — they gate the pitch. Every metric is computed from MongoDB, not from logs.

| ID | Metric | Target | Source query |
|---|---|---|---|
| **SM-1** | Take-3 median mission time vs Take-1 | **≥10 % reduction** | `experiments.aggregate([{$group:{_id:"$take",t:{$avg:"$actual_time_s"}}}])` |
| **SM-2** | New memory cards per completed mission | **≥6** | `mission_memory.count({mission_id:X})` after reflection |
| **SM-3** | Memory recall precision @ 5 (does the planner use the right card?) | **≥0.8** | tagged `mission_memory.metadata.used_in_mission` and validated by `tests/test_memory_recall.py` |
| **SM-4** | Replan latency (weather event → updated route in UI) | **<3 s P95** | timestamp delta `weather_observations.ts` → `flight_logs.event:"reroute"` |
| **SM-5** | Recovery time from worker crash mid-mission | **<8 s** to first new tool call after restart | `tool_call_log` resume marker |
| **SM-6** | Voice round-trip latency (end-of-utterance → first TTS audio frame) | **<900 ms** | LiveKit Agents metrics |
| **SM-7** | Cold-chain breach rate in scenario | **0** | aggregation over `telemetry.payload_temp_c` outside `[2,6]` |
| **SM-8** | Change-stream → WebSocket fanout latency | **<500 ms** | `tests/test_change_stream.py` |
| **SM-9** | Vector search latency (1024-dim, k=5, region filter) | **<150 ms P95** | Atlas Vector Search profiler |
| **SM-10** | Supervisor peer-discovery accuracy on the held-out task set | **≥0.9 top-1** | `tests/test_skill_registry.py` |

---

## 8 · Non-Goals (write these down so we don't drift)

| We will NOT | Because |
|---|---|
| Fly a real drone | Mock controller is sufficient for live demo; AirSim/PX4 are optional adapters only. |
| Require an OpenWeather key | We seed `weather_observations` with a deterministic synthetic generator + a `--storm` button. OpenWeather is opt-in. |
| Ship a Supabase, SQLite, or Postgres dependency | MongoDB Atlas is the **only** system of record. Eligibility depends on this. |
| Build a custom STT/TTS | Deepgram Nova-3 + ElevenLabs Turbo v2.5 are the chosen stack. Local Whisper fallback only for the no-network branch. |
| Build a generic mobile app | Operator surface is **one** Next.js 15 web app + a LiveKit voice room. No Flutter, no React Native. |
| Implement a separate auth system | Atlas App Services email/password (or NextAuth + MongoDB adapter for the web). No third-party auth vendors. |
| Use OpenAI embeddings | Voyage AI `voyage-3-large` (1024 dim default; Matryoshka 2048 / 256 documented). OpenAI is reasoning-only. |
| Hand-roll a vector store | `langchain-mongodb` `MongoDBAtlasVectorSearch` only. |
| Maintain an in-memory fleet scheduler | All scheduling state lives in `missions` + `deliveries`; UI subscribes via Change Streams. |
| Build a charts library | Recharts only. |

---

## 9 · Top 10 Risks + Mitigations

Read this before every standup. Update mitigations as we learn.

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Atlas Vector Search index build slow on free tier; demo cluster cold-starts | Med | High | Pre-create indexes in `seeds/create_indexes.py`; warm the cluster 30 min before demo; ship a docker-compose Atlas Local fallback. |
| 2 | LiveKit + ElevenLabs streaming latency spikes on conference Wi-Fi | High | High | Pre-record a fallback narration track keyed to the scripted demo; add `--text-mode` flag that bypasses voice; rehearse on hotel Wi-Fi. |
| 3 | LangGraph + checkpointer thread state grows unbounded → slow resume | Med | Med | Configure `MongoDBSaver` with TTL on `checkpoints_writes`; serialize only the slim `MissionPlanState`, not raw tool outputs. |
| 4 | Voyage AI rate limits during demo | Low | High | Cache embeddings in `embedding_cache` collection keyed by SHA-256 of input text; pre-embed all seed corpora in Phase 0. |
| 5 | Self-evolution doesn't actually beat Take-1 (the planner is already optimal) | Med | Existential | Engineer the scenario so Take-1 chooses a corridor that fails; ReflectionAgent writes a card that biases Take-3. Tested in `test_self_evolution.py`. |
| 6 | Multi-agent supervisor enters infinite delegation loop | Med | High | Cap recursion depth in `StateGraph` config; emit `traces` event on every transition; add a circuit breaker tool. |
| 7 | Atlas Trigger weather-reroute fires on dev cluster during demo | Low | Med | Triggers gated by a `mission.environment="demo"` filter; Trigger Function checks env before invoking. |
| 8 | Map performance degrades with deck.gl + Leaflet + 3 drones + arcs | Med | Med | Throttle telemetry to 2 Hz on the wire (UI only); aggregate to per-mission summary on the server. |
| 9 | Cold-chain alerting noisy → drowns voice channel | Low | Med | NarratorAgent debounces on event class; only blood/vaccine breaches trigger spoken alerts; logs always still fire. |
| 10 | Judges ask *"is this just a wrapper?"* — pitch fails the originality test | Med | Existential | Rehearse the *Skill Registry + Checkpointed Recovery + Self-Evolution Demo* triple as the unmissable creative beats. Have the `agent_skills` Atlas Vector Search query open in a browser tab to show on demand. |

---

## 10 · How This File Relates to the Others

| File | Role |
|---|---|
| `00-overview.md` (this file) | North star, glossary, success metrics, risks. |
| `01-architecture.md` | System diagram, agent topology, sequence diagrams, deployment, the two big concrete answers (skills/peers, recovery/consistency). |
| `02-mongodb-data-model.md` | Every collection schema, every index, every Atlas Search / Vector Search definition. |
| `03-agents-langgraph.md` | LangGraph node names, edges, MissionPlanState TypedDict, prompt templates. |
| `04-memory-and-rag.md` | Voyage AI usage, retrieval strategies, ContextualCompressionRetriever, summary buffer. |
| `05-tools-mcp.md` | Every `@tool` signature with idempotency keys. |
| `06-voice-livekit.md` | LiveKit worker, Deepgram pipeline, ElevenLabs voice IDs. |
| `07-frontend-nextjs.md` | App Router structure, light-mode design tokens, shadcn/ui usage. |
| `08-realtime-change-streams.md` | Watched collections, WS endpoints, fanout. |
| `09-simulation-and-mocks.md` | Mock drone controller, weather generator, obstacle injector. |
| `10-self-evolution-demo.md` | The Take-1 vs Take-3 protocol, the seeded scenario, the chart. |
| `11-security-privacy.md` | Queryable Encryption fields, role-based access, secret hygiene. |
| `12-acceptance-tests.md` | Pytest suite, traceability to SM-1…SM-10. |
| `13-implementation-plan.md` | Day-by-day phases, `pyproject.toml`, `package.json`, `.env.example`, single-command demo. |

If a claim in this file is not enforced by a downstream file, fix the downstream file. This document is the contract.

---

## 11 · One-Sentence Tagline (for the slide)

> **"Three drones, one operator, zero clicks — and a mission that gets smarter every time it flies, because every memory it forms lives in MongoDB."**
