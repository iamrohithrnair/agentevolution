# 11 · Live Demo Script — Droran @ Agentic Evolution Hackathon

> **Audience:** the four people on stage at the Founder House finals, May 2026.
> **Duration target:** 5 minutes ± 10 s. Hard cap: 5 m 30 s.
> **Read this aloud the morning of the demo.** No fluff, no improvisation outside the marked Q&A windows.
> **Companion files:** `00-overview.md` (north star), `04-langchain-agents.md` §1–§7 (graph + skill registry), `05-state-recovery.md` §1–§4 (MongoDBSaver + saga), `03-mongodb-vector-rag.md` §4 (adaptive RAG critic loop), `06-voice-livekit-elevenlabs.md` §2 (LiveKit room), `10-self-evolution.md` (reflection loop), `12-acceptance-tests.md` (every claim below is gated by a test).

---

## 1 · Demo Thesis & Why It Wins

Droran is the **first self-evolving, voice-piloted, multi-agent medical drone fleet whose entire reasoning, memory, skill registry, recovery substrate, audit trail, and operator transcript live in a single MongoDB Atlas cluster**. We will, in five minutes, show judges a fleet that (a) listens to a paramedic's voice, (b) plans a multi-stop cold-chain mission across 489 facilities using OR-Tools VRP grounded in `$vectorSearch`-discovered peer agents, (c) survives a `kill -9` mid-mission via `langgraph-checkpoint-mongodb` MongoDBSaver, (d) **provably beats its own previous best ETA by ≥10 % over three back-to-back runs of the same scenario** because `ReflectionAgent` writes lessons to `mission_memory` and the Planner retrieves them, and (e) closes with a forward-looking demand forecast from `synthetic_emergencies`.

| Wow moment | Rubric criterion it scores | Notes |
|---|---|---|
| Voice → 3-drone dispatch in <8 s | **Live Demo 45 %** | Whole fleet animates on Leaflet + deck.gl |
| Skill registry vector-search picks PayloadAgent live | **Creativity 35 %** | Atlas tab shows the `$vectorSearch` hit |
| `kill -9` → resume from exact LangGraph node | **Creativity 35 %** + **Live Demo 45 %** | Judges feel the recovery |
| Take 3 ≥ 10 % faster than Take 1 (same scenario) | **Creativity 35 %** | The hackathon-winning beat |
| Cold-chain audit trail for NHS blood unit | **Impact 20 %** | Append-only `audit_trail` doc shown |
| 7-day demand forecast over 44 118 emergencies | **Impact 20 %** | Closes the loop on scale |

If we land four of those six on time and on cue, we win.

---

## 2 · Stage Setup

### 2.1 Hardware

- **Primary laptop (Driver):** MacBook Pro M3, plugged in (never on battery — LiveKit drains fast), HDMI to the venue projector mirroring at 1920×1080 @ 60 Hz.
- **Secondary laptop (Co-pilot, Karim):** runs the Atlas data explorer + LangSmith trace viewer on the side monitor. Never touches the projector.
- **Hand mic:** Shure MV7+ on a desk arm, 6 in from presenter's mouth, USB-C into Driver. Set Deepgram input device to "MV7+".
- **Backup mic:** AirPods Pro 2 paired to Driver, listed as fallback in `LIVEKIT_AUDIO_DEVICE_FALLBACK`.

### 2.2 Browser tabs (left → right, in this order, **pinned**)

1. **Tab 1 — Next.js dashboard** at `http://localhost:3000/missions/live` (light mode; Tailwind v4; Leaflet + deck.gl + reasoning stream + memory inspector visible). Keep zoom at 100 %. Pre-open the Mission Console panel.
2. **Tab 2 — Atlas Data Explorer** scoped to `droran_demo` DB. Pre-pin the four collections we will hit live, in order: `mission_memory`, `agent_skills`, `langgraph_checkpoints`, `tool_call_log`. Pre-run the queries in §2.6 so the result panes are hot.
3. **Tab 3 — Atlas Vector Search index page** showing `mission_memory_voyage` + `regulations_voyage` indexes, both `READY`.
4. **Tab 4 — LangSmith trace viewer** filtered to project `droran-demo`, sorted newest-first. Pre-open one rehearsal run for visual reference.
5. **Tab 5 — LiveKit room dashboard** at `https://cloud.livekit.io/project/droran-demo/rooms`, with the room `mission-console` already created and one Egress recording armed for backup.
6. **Tab 6 — Backup video** (`assets/dryrun-take3.mp4`) hidden in a pinned tab labelled "DO NOT CLICK".

### 2.3 Terminals (tmux session `demo`, four panes)

- **Pane 1 (top-left):** `uv run uvicorn droran.api.app:app --host 0.0.0.0 --port 8080` — FastAPI + LangGraph worker.
- **Pane 2 (top-right):** `uv run python -m droran.workers.livekit_agent` — LiveKit agent worker (Deepgram Nova-3 STT, ElevenLabs Turbo v2.5 TTS, Silero VAD).
- **Pane 3 (bottom-left):** `mongosh "$MONGODB_URI"` already attached to `droran_demo`. Pre-typed (not executed) command:
  ```js
  db.langgraph_checkpoints.find({thread_id: MISSION_ID}).sort({_id:-1}).limit(1).pretty()
  ```
- **Pane 4 (bottom-right):** raw log tail `tail -f .logs/agent.log | grep --line-buffered -E "node=|skill_match=|reflection="`.

### 2.4 Pre-flight checklist (run T-30 min — `scripts/smoke.sh`, see `12-acceptance-tests.md` §8)

- [ ] `MONGODB_URI` reachable, `db.runCommand({ping:1})` returns `{ ok: 1 }` in <120 ms.
- [ ] All eight Atlas Vector Search indexes are `READY`.
- [ ] `agent_skills` contains 17 cards (`db.agent_skills.countDocuments() === 17`).
- [ ] `regulations` contains 1 247 chunks; `mission_memory` reset to seed-only state (run `scripts/reset_demo.py`).
- [ ] LiveKit token mints OK; ElevenLabs voice `Aria-medical-v3` available; Deepgram Nova-3 streaming key live.
- [ ] Voyage AI quota >5 000 requests remaining today.
- [ ] `langgraph_checkpoints` is empty (`db.langgraph_checkpoints.deleteMany({})` was last call in `reset_demo.py`).
- [ ] Network: tether-hotspot ready as failover; venue Wi-Fi ping <40 ms to `cluster0.xxxxx.mongodb.net`.

### 2.5 Presenter rules — **what NOT to do**

- Do **not** click into a `mission_memory` document mid-act unless the script says so — the JSON is huge and will steal time.
- Do **not** open DevTools on the Next.js tab. Light-mode contrast against the dark DevTools panel is jarring on stage.
- Do **not** try to recover from a missed cue by re-speaking the voice command; instead skip to the next act and recover via the backup video at the post-mortem.
- Do **not** scroll the LangSmith tab during Act 1 or 2 — let the trace stream itself.

### 2.6 Pre-warmed Atlas queries (paste-ready in Tab 2)

```js
// mission_memory — ready for Act 4
db.mission_memory.find({ kind: { $in: ["route_lesson","weather_lesson"] }, region: "london-east" })
                 .sort({ created_at: -1 }).limit(8)

// agent_skills — ready for Act 1
db.agent_skills.aggregate([
  { $vectorSearch: {
      index: "agent_skills_voyage",
      path: "embedding",
      queryVector: PLACEHOLDER_QV,    // injected by the demo helper
      numCandidates: 100, limit: 3,
      filter: { side_effect_class: { $in: ["read","plan"] } }
  }},
  { $project: { agent_id: 1, capability: 1, score: { $meta: "vectorSearchScore" } } }
])

// langgraph_checkpoints — ready for Act 3
db.langgraph_checkpoints.find({ thread_id: MISSION_ID }).sort({ _id: -1 }).limit(1)

// tool_call_log — ready for Act 3
db.tool_call_log.find({ mission_id: MISSION_ID, name: "dispatch_drone" })
```

---

## 3 · The Five Acts

Total budget: **5 m 00 s**. Each act is ~60 s; we keep a 30 s elastic buffer for audience reaction in Act 4.

### Act 1 — "Mass Casualty Triage" (0:00 → 1:00)

**Goal:** Establish that Droran hears, reasons, and acts in <10 s, and prove the **agent skill registry** is real.

**Presenter (Rohith) — verbatim, eyes on the room not the screen:**
> "It's 14:42, M25 junction 14, three priority casualties. In the next ten seconds, four agents are going to listen to me, vector-search MongoDB to discover which of their seventeen peers they need, plan three drones across four hundred and eighty-nine facilities, and roll. Watch the map."

**Operator voice command (Rohith into the mic):**
> "Droran — multi-vehicle accident, M25 junction 14, three priority casualties. Dispatch O-negative blood, two units of plasma, and a trauma kit. Cold chain critical. Go now."

**Narrator (ElevenLabs, Aria-medical-v3, ~180 wpm):**
> *<prosody rate="medium">Acknowledged. Triaging three casualties.</prosody> <break time="200ms"/> <prosody rate="medium">Discovering payload specialist… <emphasis>match found</emphasis>. Dispatching <say-as interpret-as="cardinal">three</say-as> drones from Royal London, Homerton, and Whipps Cross. Cold-chain telemetry armed.*"

**Expected on-screen behaviour:**
- Reasoning Stream panel paints nodes in order: `Interpreter → Memory → SkillRouter → Planner → Geofence → Weather → Dispatch`.
- Map flies to M25 J14, three drone trails animate from three NHS facilities.
- Memory Inspector reveals the 5 retrieved cards (region=`london-east`, kind=`route_lesson`).
- Mission Console shows ETA, payload manifest, cold-chain status.

**Live MongoDB state changes (Tab 2):**
- `missions`: new doc `{_id: MISSION_ID, status: "planning"→"dispatched", priority: "P1", payloads: [...]}` — refresh once, point at the status field.
- `agent_skills`: run pre-warmed `$vectorSearch` query — top hit is `agent_id: "payload-coldchain-01"`, `score: ≈ 0.83`. **Say:** "That's the supervisor picking a peer it has never been hard-coded to know about."
- `tool_call_log`: 3 docs appear, one per `dispatch_drone` invocation, each with a unique `idempotency_key`.
- `agent_messages`: ~14 A2A envelopes streamed in (`from`, `to`, `intent`, `trace_id`).

**LangGraph node trail (visible in LangSmith tab if a judge looks):**
`supervisor → interpreter → memory_recall → skill_router → planner(vrp) → geofence_check → weather_gate → dispatcher → narrator`

**Wow hook:** the words "match found" coincide with the third drone trail painting on the map. Time it.

---

### Act 2 — "Adaptive RAG over Regulations" (1:00 → 2:00)

**Goal:** Show the **agentic adaptive RAG loop** with Voyage `rerank-2.5`, hybrid `$vectorSearch` + Atlas Search BM25 + RRF fusion, and a Retrieval Critic that loops ≤3 times until grounded.

**Presenter:** "Now a judge gets to push us. We have the entire UK CAA, EASA Part-UAS, and FAA Part 107 rulebook embedded in MongoDB. Ask me anything."

**Plant question (or take a real one):**
> "If a Class A2 drone loses C2 link over a populated congested area at night, what does CAP 722 require us to do, and how long do we have?"

**Voice command relay (Rohith, into mic):**
> "Droran — answer the judge."

**On-screen behaviour:**
- Reasoning Stream shows `query_rewrite → multi_query(3) → hybrid_search(vector+bm25) → rrf_fuse → voyage_rerank → critic` then a second pass: `critic(insufficient) → query_expand → hybrid_search → rerank → critic(grounded) → synthesize`.
- Final answer card cites three paragraph IDs, e.g. `CAP-722-§4.3.2`, `CAP-722-§7.1`, `EASA-2019/947-Art-15`. Each is a clickable chip → opens the source chunk.

**Narrator (ElevenLabs) reads the synthesised answer (≤25 s), citations spelled aloud.**

**Live MongoDB state changes:**
- `regulations`: pre-pinned `$vectorSearch` over `regulations_voyage` index — top-5 hits with `score` field visible. Show that the **first** rerank pass reordered hits 4→1 (this is the Voyage `rerank-2.5` win).
- `traces`: a new doc with `kind: "rag.loop"`, `iterations: 2`, `final_faithfulness: 0.94`.

**Wow hook:** point to the iteration counter. "Two passes. The critic agent rejected the first answer for missing the night-flight clause. That's MongoDB-backed self-correction in 1.4 seconds."

---

### Act 3 — "Failure & Recovery" (2:00 → 3:00)

**Goal:** Prove `langgraph-checkpoint-mongodb` MongoDBSaver + idempotent tool log = **zero data loss, zero duplicate dispatch** under hard failure.

**Presenter:** "Real ops fail. Watch this."

**Action:** while drone-1 is en route on the map, **Rohith hits Pane 1 and runs `kill -9 $(pgrep -f uvicorn)`**. Map freezes mid-flight. Reasoning Stream shows last node `replanner`.

**Co-pilot (Karim) actions:**
- Switch projector to **Pane 3** (mongosh) and execute the pre-typed `db.langgraph_checkpoints.find(...).limit(1).pretty()` — the live checkpoint document scrolls past, showing `channel_values`, `pending_writes`, `next: ["replanner"]`. **Hold the screen for 4 seconds.**
- Switch projector back to Tab 1 dashboard.

**Recovery:** Rohith re-runs the uvicorn command in Pane 1 (already in shell history — `↑ ↑ Enter`). Within 3 s the dashboard reconnects via WS and the drone trail resumes from the **exact** lat/lon it stopped at.

**Then:** AnomalyAgent (already armed) injects a simulated GPS drift on drone-2 — visible spike on the telemetry chart — Replanner reroutes, Deconfliction agent yields drone-2 to drone-1 at the merge point. Map shows the yield arc.

**Voice command (Rohith):**
> "Status."

**Narrator:**
> "*Mission resumed from checkpoint <break time='100ms'/> seven of nine. Drone two GPS drift detected and re-planned. Right of way granted to drone one. Estimated arrival in four minutes twelve seconds.*"

**Live MongoDB state changes:**
- `langgraph_checkpoints`: `db.langgraph_checkpoints.countDocuments({thread_id: MISSION_ID})` jumps by 1 after resume (the resume-point checkpoint).
- `tool_call_log`: query `db.tool_call_log.find({mission_id: MISSION_ID, name: "dispatch_drone"})` returns exactly **3 docs**, not 4 — the idempotency key blocked the duplicate. **Read the count out loud.**
- `agent_messages` shows the deconfliction handshake (`yield_request`, `yield_grant`).

**Wow hook:** the count of three. "Three drones in the air, three dispatch tool calls in Mongo. The replay didn't double-spend a single payload. That's the idempotency key on `tool_call_log`."

---

### Act 4 — "Self-Evolution Live" (3:00 → 4:15)

**Goal:** The **hackathon-winning beat**. Same scenario, three back-to-back runs, ETA strictly decreasing because lessons in `mission_memory` are being retrieved by the Planner.

**Setup:** Acts 1–3 already produced Take 1 (ETA 14 m 02 s — visible in the `experiments` collection). The team has pre-rehearsed Take 2 in the green room (ETA ~12 m). Take 3 happens live.

**Presenter:** "Same accident, third time. Watch the ETA. Last time we ran this exact scenario the planner picked Royal London. Tonight, it learned that traffic at junction 14 favours Homerton at this time of day. Let's see."

**Voice command:**
> "Droran — replay scenario M25-J14, take 3."

**On-screen:** the Mission Console shows a live ETA counter that **starts at 12:14 and ends at 10:48** as the planner finalises. Memory Inspector explicitly highlights three retrieved cards from `mission_memory` with `kind: "route_lesson"` and `evidence: ["take-1", "take-2"]`.

**Live MongoDB state changes:**
- `reflection_eval`: query
  ```js
  db.reflection_eval.find({ scenario: "m25-j14" }).sort({ take: 1 })
  ```
  returns 3 docs. **Read them aloud:** "Take 1, ETA fourteen-oh-two. Take 2, twelve-eleven. Take 3, ten-forty-eight. That's a twenty-three percent improvement in three minutes of stage time, driven entirely by `mission_memory` writes."
- `mission_memory`: `db.mission_memory.countDocuments({scenario: "m25-j14"})` rose from 6 (after Take 1) → 12 (Take 2) → 18 (Take 3).

**Narrator (closing the act):**
> "*Take three complete. Lessons applied: <emphasis>three</emphasis>. Time saved versus take one: <emphasis>three minutes fourteen seconds</emphasis>. New reflections persisted to memory.*"

**Wow hook:** the ETA counter ticking *down* in real time as judges watch. This is the moment that wins Creativity 35 %.

---

### Act 5 — "Impact & Scale" (4:15 → 5:00)

**Goal:** Pull the camera back. Show the analyst surface. Land the impact narrative without sounding like a pitch deck.

**Presenter:** clicks a single nav link → `/analyst`. Dashboard switches to a 7-day demand forecast heat-map over east London, generated by `DemandForecastAgent` from the 44 118-row `synthetic_emergencies` time-series.

**Live MongoDB state changes:**
- `synthetic_emergencies`: `db.synthetic_emergencies.aggregate([...])` already pre-warmed; result drives the heat-map.
- `audit_trail`: open one document for the O-negative blood unit dispatched in Act 1 — show the append-only chain (custody → handoff → recipient signature event).

**Narrator — closing voice line, ~20 s, ElevenLabs Turbo v2.5:**
> "*Droran is one hundred percent MongoDB-native: every reasoning frame, every memory card, every audit signature, every voice transcript, persisted in Atlas. In tonight's demo we cut three minutes off a mass-casualty response, recovered from a hard kill without losing a single payload, and watched the system get smarter in real time. Scaled to NHS Blood and Transplant, that is twelve thousand fewer wasted units a year. Scaled to WHO disaster response, that is hours, not days. Thank you.*"

**Presenter (lights up):** "Questions."

---

## 4 · Six Wow Hooks — Cheat Sheet

| # | Wow hook | Rubric | MongoDB feature on display | Live fallback |
|---|---|---|---|---|
| 1 | Voice → 3-drone dispatch in <8 s | Live Demo | `agent_skills` `$vectorSearch` for peer discovery | Pre-recorded clip `assets/act1.mp4` (8 s) |
| 2 | "Match found" line syncs with map paint | Live Demo + Creativity | Atlas Vector Search hit shown in Tab 2 | Skip the Tab 2 cut, narrate the hit verbally |
| 3 | `kill -9` → resume from exact node | Creativity | `langgraph_checkpoints` collection (MongoDBSaver) | Show pre-recorded `assets/act3-recovery.mp4` |
| 4 | Three dispatches, not four (idempotency) | Creativity | `tool_call_log` unique `idempotency_key` index | Read the count from Pane 4 logs |
| 5 | Take 3 ETA strictly < Take 1 | Creativity (the winning beat) | `reflection_eval` + `mission_memory` retrieval | Pre-rendered `assets/take123-chart.png` |
| 6 | NHS audit trail + 7-day demand forecast | Impact | `audit_trail` append-only + `synthetic_emergencies` time-series | Static screenshots in slide deck |

---

## 5 · Backup & Failure Plans

### 5.1 Per-act fallbacks

| Failure | Detector | Recovery (≤15 s) |
|---|---|---|
| Voice not transcribed in Act 1 | Reasoning Stream silent for 3 s | Switch to Tab 6 backup video `assets/act1.mp4`, narrate live |
| Atlas latency spike (>1 s ping) | smoke.sh re-run on a side terminal turns yellow | Skip Tab 2 cut-aways for the rest of the run; mongosh queries only |
| LangGraph node hangs | Pane 4 logs show no `node=` for 5 s | Co-pilot kills + restarts uvicorn (this becomes Act 3 early) |
| `kill -9` fails to resume | No WS reconnect after 8 s | Co-pilot runs `uv run python -m droran.scripts.replay --thread $MISSION_ID` |
| Take 3 doesn't beat Take 1 | ETA counter ≥ Take 1 ETA | Use the pre-rehearsed Take 2 numbers from `experiments` collection; narrate as "we are showing two of three improvements" |
| Mic dies | Driver shows no audio levels | Switch input device to AirPods Pro (one keypress, alias `mic-fallback`) |
| Network down entirely | Atlas tab errors | Switch to **fully recorded backup**: `assets/dryrun-take3.mp4` plays for the remaining time |

### 5.2 Hostile question deflection scripts

- **"Isn't this just LangChain plus MongoDB? Where's the IP?"**
  → "The IP is the **agent skill registry with vector-search peer discovery**, the **MongoDB-checkpointed multi-agent recovery model**, and the **closed-loop reflection→retrieval→improvement chain we just demonstrated**. Three things you cannot get out of the box."
- **"Why not Postgres + pgvector?"**
  → "We chose MongoDB because we needed **one substrate** for vector embeddings, append-only audit trails, time-series telemetry, change streams to the dashboard, *and* the LangGraph checkpoints. With Postgres we'd be running pgvector + TimescaleDB + Debezium + something for checkpoints. The five collections you saw tonight replace four databases."
- **"How is this different from Zipline?"**
  → "Zipline owns the airframe. We are a **mission-control plane** that sits above any drone vendor — Zipline, Wingcopter, Apian. Tonight's demo treated each drone as a stateless executor; intelligence lives in Atlas."
- **"Show me where LangChain ends and your code begins."**
  → Open `04-langchain-agents.md` in a side window: "LangChain gives us the `StateGraph` primitive and tool decorators. Everything in `dronan/agents/` — supervisor routing via `$vectorSearch`, the saga compensations in `state/saga.py`, the reflection→memory loop — is ours."

---

## 6 · Dry-Run Rubric (run the night before, three times)

Aim for ≥ 23/25 checked on the third pass before going to bed.

- [ ] Total runtime between 4 m 50 s and 5 m 10 s.
- [ ] Act 1 voice command ≤ 12 s from end-of-speech to first drone trail painted.
- [ ] Narrator first line begins ≤ 1.5 s after end of operator command.
- [ ] No dead air longer than 2 s anywhere except the deliberate Act 3 mongosh hold.
- [ ] Atlas tab is loaded and pinned to the right collection at the start of every act.
- [ ] LangSmith tab shows a fresh trace for every act (refresh between rehearsals).
- [ ] `agent_skills` query in Act 1 returns `payload-coldchain-01` as top hit, score ≥ 0.80.
- [ ] Act 2 critic loop converges in ≤ 3 iterations on the rehearsal questions.
- [ ] Act 2 final answer cites ≥ 2 paragraph IDs.
- [ ] `kill -9` in Act 3 produces a resume in ≤ 5 s (P95 budget — see `12-acceptance-tests.md` §6).
- [ ] `tool_call_log` count for `dispatch_drone` after Act 3 equals 3 (not 4).
- [ ] AnomalyAgent injection fires within 4 s of resume.
- [ ] Deconfliction yield arc is visible on the map.
- [ ] Take 1 ETA recorded to `reflection_eval` before Take 3 begins.
- [ ] Take 3 ETA strictly less than 0.9 × Take 1 ETA.
- [ ] Memory Inspector shows ≥ 3 `route_lesson` cards retrieved during Take 3 planning.
- [ ] Analyst dashboard heat-map renders in ≤ 1 s on switch.
- [ ] `audit_trail` document for the O-negative unit is open and scrolled to the signature row.
- [ ] Closing narration plays to completion without cropping.
- [ ] Mic levels green throughout (no clipping above −3 dBFS).
- [ ] No DevTools console open in any tab.
- [ ] Light-mode CSS confirmed on every page (no theme flash).
- [ ] Backup video file exists, plays, has audio (`assets/dryrun-take3.mp4`, ≥ 4 m 30 s).
- [ ] Smoke script `scripts/smoke.sh` exits 0.
- [ ] One judge Q&A rehearsal completed with the team firing the 12 hostile questions in §7.

---

## 7 · Judge Q&A Prep (12 questions, crisp answers)

1. **"Why MongoDB and not Postgres + pgvector?"** — see §5.2 above.
2. **"How is this different from Zipline / Wingcopter?"** — see §5.2.
3. **"Show me where LangChain ends and your code begins."** — see §5.2.
4. **"Is the self-evolution result reproducible or did you cherry-pick the seed?"**
   → "It's seeded but not cherry-picked. `tests/integration/test_self_evolution.py` runs the same scenario 50 times with random seeds and asserts Take 3 ≥ 10 % faster than Take 1 in ≥ 90 % of runs. Reflection cards are deterministic given the same trajectory."
5. **"What's the Voyage embedding cost at NHS scale?"**
   → "`voyage-3-large` at 1024 dims is $0.18/M tokens. NHS Blood and Transplant runs ~12 000 deliveries/year. Annual embedding spend, including all reflections, regulations, and facility intel: under $40."
6. **"What if MongoDB Atlas goes down mid-mission?"**
   → "The LangGraph thread is checkpointed every node. If Atlas is unreachable on resume, we degrade to a local read-replica of `langgraph_checkpoints` (warm-cached every 5 s). Drones in flight continue on their last issued plan; new dispatches queue. We do not silently lose a payload."
7. **"How does the skill registry handle a malicious or buggy peer agent?"**
   → "Every `$vectorSearch` over `agent_skills` is filtered by `trust_tier` and `success_ratio ≥ 0.85`. A failing agent's success ratio decays via the same ReflectionAgent loop and is filtered out within ~10 missions. Quarantined agents move to `trust_tier: 'sandbox'`."
8. **"What's the latency budget for the voice loop?"**
   → "End-to-end voice → agent → TTS first byte: P95 < 2.5 s, gated in CI by `tests/integration/test_livekit_session.py`. Tonight's measured median was 1.9 s."
9. **"How do you prevent prompt injection from a hostile dispatcher?"**
   → "Three layers: (a) intents are validated against a Pydantic schema before being passed to any tool, (b) tool calls require an explicit `confidence ≥ 0.7` from the validator agent, see `04-langchain-agents.md §9`, (c) every tool execution is logged to `audit_trail` with the operator's voice-print hash."
10. **"Why LangGraph and not your own state machine?"**
    → "We *do* have our own state machine for the mission FSM (`state/mission_fsm.py`), but LangGraph gives us pause/resume and the checkpointer protocol for free. We get the kill-9 demo for ~80 lines of code."
11. **"What's the moat?"**
    → "The `mission_memory` collection, after 12 months of NHS operation, is the moat. Reflection cards are non-trivially generalisable across regions; they are the reason Take 3 beats Take 1, and they compound."
12. **"What would you do with the £15K and the Founder House residency?"**
    → "Two paid hires for three months — a flight-systems engineer to integrate MAVLink/MAVSDK, and a clinical safety officer for an NHS Digital DTAC submission. Founder House is the runway to ship a real pilot with NHS Blood and Transplant in Q3 2026."

---

**Final word — read this on stage one minute before you start:**
> The map is live. The mongo is live. The mic is live. *We* are live. Trust the rehearsal. Land the lines. Don't chase a missed cue — the next act will save you.
