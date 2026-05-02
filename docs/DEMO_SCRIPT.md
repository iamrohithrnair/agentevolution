# Dronan Live Demo Script

> **Audience:** judges at the Founder House finals.
> **Duration:** 4 minutes (hard cap 4 m 30 s) + 1 minute Q&A.
> **Read aloud the morning of the demo. No improvisation outside the marked Q&A windows.**
> **Companion files:** [`prompts/00-overview.md`](../prompts/00-overview.md), [`prompts/11-demo-script.md`](../prompts/11-demo-script.md), [`prompts/12-acceptance-tests.md`](../prompts/12-acceptance-tests.md).

This is the verbatim presenter script for the on-stage demo. It mirrors `prompts/11-demo-script.md` §3 but is condensed to the 4-minute window and aligned to the four acts that the engineering acceptance tests in [`prompts/12-acceptance-tests.md`](../prompts/12-acceptance-tests.md) gate.

---

## 0 · Pre-flight (T-30 min)

Run from a clean shell on the demo laptop:

```bash
make demo
```

This boots Atlas health check → FastAPI → LiveKit worker (or text-mode fallback if voice keys absent) → Next.js dev server → opens `http://localhost:3000/dashboard` in the default browser. **Cold-boot SLA ≤ 60 s** (AT-8.2). If `make demo` exceeds 60 s, run `scripts/wait_healthy.py` manually and abort the demo — switch to the fallback video at `assets/demo-fallback.mp4`.

Pre-flight checklist:

- [ ] `make demo` boots green in ≤ 60 s.
- [ ] All eight Atlas Vector Search indexes are `READY` (Tab 3).
- [ ] LiveKit room `mission-console` is created and an Egress recording is armed (Tab 5).
- [ ] `assets/demo-fallback.mp4` is loaded in a hidden tab labelled "DO NOT CLICK".
- [ ] Hand mic is plugged in and Deepgram input is set to "MV7+".
- [ ] `tmux a -t demo` is up with the four panes from `prompts/11` §2.3.
- [ ] One canonical scenario rehearsal completed (`./scripts/run_takes.sh` produced 3 rows in `experiments` with monotonically decreasing `actual_time_s`).

If any item is red, do **not** start the demo. Switch to the fallback video.

---

## 1 · Act 1 — Voice Dispatch (0:00 → 1:00)

**Goal:** Show that Dronan hears, reasons, and acts in <10 s, and that the voice round-trip stays under 900 ms p95 (SM-6).

**Presenter (eyes on the room, not the screen):**
> "It's 14:42. Operator on a hand mic. Three drones. Four hundred and eighty-nine facilities. In the next eight seconds, four LangGraph agents are going to listen, vector-search MongoDB to discover which of their peers they need, plan a multi-stop cold-chain mission, and roll. Watch the dashboard."

**Operator voice command:**
> "DroneFleet, dispatch O-negative blood and pediatric vaccines to Clinic D now. Storm is rolling in over the Thames; pick the safer corridor."

**Expected on-screen:**

- Reasoning Stream paints nodes: `Interpreter → Memory → SkillRouter → Planner → Geofence → Weather → Dispatch`.
- Map flies to Hackney, two drone trails animate from Royal London + Homerton.
- Memory Inspector shows the lessons retrieved for `tag=scenario:airport_corridor_storm`.
- Mission Console shows ETA, payload manifest, cold-chain status.
- VoiceHUD waveform reacts in real time.

**Narrator (ElevenLabs Turbo v2.5):**
> *"Acknowledged. Dispatching two drones from Royal London and Homerton. Cold-chain telemetry armed. Avoiding the Thames corridor — wind shear at 80 to 120 metres."*

**Live MongoDB state changes (Tab 2):**
- `missions`: new doc with `status: planning → dispatched`.
- `agent_skills`: pre-warmed `$vectorSearch` query, top hit is `payload-coldchain-01` with `score ≈ 0.83`. **Say:** "That's the supervisor picking a peer it has never been hard-coded to know about."
- `tool_call_log`: 2 docs appear, one per `dispatch_drone`, each with a unique `idempotency_key`.

**Wow hook:** the words "Cold-chain telemetry armed" land at the same instant the second drone trail paints on the map. Time it.

---

## 2 · Act 2 — Failure & Recovery (1:00 → 2:00)

**Goal:** Prove `langgraph-checkpoint-mongodb` MongoDBSaver + idempotent tool log = zero data loss, zero duplicate dispatch under hard failure (SM-5).

**Presenter:** "Real ops fail. Watch this."

**Action:** while drone-1 is en route, run in Pane 1:

```bash
./scripts/rehearse_recovery.sh
```

The script kills the LiveKit worker at T+90 s, restarts it, polls `tool_call_log` for the first new row after the kill, and writes a JSON summary to `.logs/rehearse_recovery.json`. **Threshold: ≤ 8 s.** If it returns non-zero, switch to the fallback video.

**Co-pilot (Karim):**
1. Switch projector to **Pane 3** (mongosh) and run the pre-typed:
   ```js
   db.langgraph_checkpoints.find({thread_id: MISSION_ID}).sort({_id:-1}).limit(1).pretty()
   ```
   Hold the screen for 4 seconds.
2. Switch projector back to Tab 1 (dashboard).

**Recovery:** the dashboard reconnects via WebSocket and the drone trail resumes from the exact lat/lon it stopped at. AnomalyAgent injects a simulated GPS drift on drone-2 — visible spike — Replanner reroutes, Deconfliction yields drone-2 to drone-1.

**Voice command:** "Status."

**Narrator:**
> *"Mission resumed from checkpoint seven of nine. Drone two GPS drift detected and re-planned. Estimated arrival in four minutes twelve seconds."*

**Live MongoDB state changes:**
- `langgraph_checkpoints`: count of docs for this `thread_id` jumps by 1.
- `tool_call_log`: count of `dispatch_drone` docs is **exactly 2**, not 3 — the idempotency key blocked the duplicate. **Read this count out loud.**

**Wow hook:** the count of two dispatch tool calls for two drones in the air. "The replay didn't double-spend a single payload. That's the idempotency key on `tool_call_log`."

---

## 3 · Act 3 — Self-Evolution Live (2:00 → 3:30)

**Goal:** The hackathon-winning beat. Same scenario, three takes, monotonically decreasing mission time because lessons in `mission_memory` are being retrieved by the Planner (SM-1, SM-2, SM-3).

**Setup:** Acts 1–2 already produced Take-1 (visible in the `experiments` collection). Take-2 was pre-rehearsed in the green room. Take-3 happens live.

**Presenter:** "Same scenario, third time. Watch the ETA. Last time, the planner picked Royal London. Tonight, it learned that Thames-corridor wind shear at this time of day is a hard block. Let's see."

**Voice command:** "DroneFleet, replay the scenario."

**On-screen:** Mission Console shows the live ETA counter ticking down. Memory Inspector explicitly highlights the three retrieved cards from `mission_memory` with `kind: corridor_avoidance` and `evidence: ["take-1", "take-2"]`.

**Live MongoDB state changes:**
- `experiments`: query
  ```js
  db.experiments.find({ scenario_id: "airport_corridor_storm" }).sort({ take: 1 })
  ```
  returns 3 docs. **Read aloud:** "Take 1, four minutes. Take 2, three minutes thirty. Take 3, three minutes ten. That's a twenty-one percent improvement, driven entirely by `mission_memory` writes."
- `mission_memory`: count for `metadata.tag=scenario:airport_corridor_storm` rose from 6 (Take-1) → 12 (Take-2) → 18 (Take-3).

**Narrator (closing the act):**
> *"Take three complete. Lessons applied: three. Time saved versus take one: forty-eight seconds. New reflections persisted to memory."*

**Wow hook:** the ETA counter ticking *down* in real time. This is the moment that wins Creativity.

---

## 4 · Act 4 — Impact & Q&A (3:30 → 4:30)

**Goal:** Pull the camera back. Land the impact narrative. Open Q&A.

**Presenter:** clicks `/analytics` → SVG chart of `actual_time_s` per take renders server-side from `backend/dronan/demo/charts.py`. The SM-1 90 %-of-Take-1 baseline is annotated as a dashed green line, marked **PASS** if Take-3 < 0.9 × Take-1.

**Live MongoDB state changes:**
- `audit_trail`: open one doc for the O-negative blood unit dispatched in Act 1 — show the append-only chain (custody → handoff → recipient signature event with hashed transcript).

**Narrator — closing voice line, ~15 s:**
> *"Dronan is one hundred percent MongoDB-native: every reasoning frame, every memory card, every audit signature, every voice transcript, persisted in Atlas. In four minutes we cut a minute off a cold-chain dispatch, recovered from a hard kill without losing a payload, and watched the system get smarter in real time. Thank you."*

**Presenter (lights up):** "Questions."

**Anticipated Q&A windows (90 s):**

| Q | A (one sentence) |
|---|------------------|
| "How does the lesson retrieval scope to *this* scenario?" | `mission_memory` documents carry `metadata.tag` and `metadata.region`; Atlas `$vectorSearch` filter pre-narrows the candidate set before reranking. |
| "What if the LLM hallucinates a drone ID?" | The dispatcher tool validates against `drones` and rejects with a structured error; the supervisor retries with the validated set. |
| "What is the recovery substrate, exactly?" | `langgraph-checkpoint-mongodb` writes `channel_values` and `pending_writes` after every node; `tool_call_log` is idempotent on `idempotency_key`. |
| "Why MongoDB over Postgres + a vector DB?" | Atlas Vector Search, Change Streams, document model for the `mission_memory` schema, and `MongoDBSaver` — one cluster, one auth, one backup story. |
| "Can you fail it?" | `kill -9` the LiveKit worker. We just did. |

---

## 5 · Failover Plan

If at any point the live demo derails (Atlas disconnects, voice loop > 2 s, dashboard 500s), say calmly:

> "Let me show you the rehearsal."

Switch to the hidden tab, play `assets/demo-fallback.mp4` (90-second screen capture). Everything in the script above is captured on the fallback video; the narration is identical. Resume Q&A directly.

---

## 6 · Rehearsal Schedule

Per `prompts/13` §8 exit criteria:

- [ ] T-72h: full rehearsal #1 — measure cold-boot, voice round-trip P95, Take-3 ratio.
- [ ] T-48h: full rehearsal #2 — focus on recovery rehearsal (`scripts/rehearse_recovery.sh`).
- [ ] T-24h: full rehearsal #3 — record `assets/demo-fallback.mp4`.
- [ ] T-12h: full rehearsal #4 — on conference-grade Wi-Fi.
- [ ] T-2h: full rehearsal #5 — final sanity check.

Each rehearsal must verify all of SM-1 through SM-10 within the 24 hours preceding the demo.

---

## 7 · Hand-off

- **Pitch deck:** see [`docs/PITCH_DECK_OUTLINE.md`](./PITCH_DECK_OUTLINE.md).
- **Acceptance tests:** see [`prompts/12-acceptance-tests.md`](../prompts/12-acceptance-tests.md). Each act above maps to one or more AT-X.Y tests; if any is red the day of the demo, the corresponding act is replaced with the fallback video.
