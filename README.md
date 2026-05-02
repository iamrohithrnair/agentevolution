# Dronan (Agentic Evolution)

Voice-first, memory-augmented multi-agent platform for **medical drone logistics**. Operator missions are planned, executed, narrated, and improved over time; durable state, retrieval, and telemetry live in **MongoDB Atlas**. Detailed architecture and schemas are in [`prompts/`](prompts/).

---

## Features

### Medical drone mission control

- End-to-end delivery workflows: missions, multi-stop routes, fleet status, and payloads tuned for healthcare logistics (e.g. cold-chain supplies such as blood, insulin, vaccines).
- Facility and airspace awareness: geofencing, no-fly constraints, and regulation-aware planning framed for jurisdictions including UK CAA, EASA, and FAA Part 107.
- Chain-of-custody and audit narrative: immutable audit trail, recipient confirmation flows, and NHS-style reporting artifacts stored for compliance storytelling.

### Voice-first operations

- Operators interact through a **LiveKit** room with streaming **STT** (Deepgram Nova-3) and **TTS** (ElevenLabs Turbo v2.5), suited for hands-busy clinical and field contexts.
- Push-to-talk / always-on modes, barge-in, and **text/chat** fallback when voice is unavailable.

### Multi-agent orchestration

- **LangGraph** supervisor plus specialist agents for interpretation, memory recall, routing and replanning, weather, geofence checks, payload and cold-chain status, preflight, dispatch, vision/obstacles, anomalies, separation, narration, analytics, post-mission reflection, and demand forecasting.
- Dynamic routing: the supervisor discovers peers using **vector search** over an **`agent_skills`** registry rather than a fixed if/elif router.

### Memory and retrieval

- Multiple memory tiers anchored in MongoDB: conversational history, episodic **`mission_memory`** (reflections and lessons), semantic corpora (regulations, facility intel), and planner context built from **top-k** retrieval.
- Embeddings via **Voyage AI**; recall filtered by region, weather class, and memory kind where relevant.

### Real-time operator console

- Web dashboard with live map (routes, facilities, no-fly overlays, drone markers), mission and delivery views, and telemetry-driven status.
- **Reasoning stream** of supervisor and agent transitions; **memory inspector** for retrieved cards; **reflection feed** for post-mission learning surfaced to the UI.

### Self-evolving behavior

- After each mission completes, a **reflection** step writes structured, typed **memory cards** back into **`mission_memory`** so later missions can reuse lessons (routes, weather, facilities, operator preferences, incidents).
- Demo narrative compares repeated runs of the same scenario (e.g. Take 1 vs Take 3) with metrics recorded for measurable improvement.

### Resilience and consistency

- LangGraph **checkpointing** to MongoDB so in-flight missions can resume after worker or process failure without redoing completed steps.
- **Idempotent** tool execution patterns with logged calls for safe retries.

### Automated reactions from data

- **Atlas triggers** can initiate replans or alerts (for example weather-driven reroute, cold-chain breach, low battery) by calling backend endpoints, keeping reactions tied to database events.

### Security and privacy (design targets)

- Sensitive recipient fields designed for **Queryable Encryption** where applicable; role-aware access patterns described alongside the data model.

---

For schemas, API shapes, agent prompts, and acceptance criteria, see the numbered files under [`prompts/`](prompts/) (start with [`prompts/00-overview.md`](prompts/00-overview.md)).
