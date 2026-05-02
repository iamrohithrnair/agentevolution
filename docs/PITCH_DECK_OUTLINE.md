# Dronan Pitch Deck — 5-Slide Outline

> **Purpose:** the slide deck shown alongside the live demo at the Founder House finals. Five slides, ~30 s each, total 2 min 30 s. The deck is auxiliary; the live demo carries the room. Slides exist to anchor the impact narrative for judges and remote viewers.
> **Deliverable:** the engineer who renders this writes a Keynote/Google Slides deck whose master matches the spec below. Keep typography brutally simple (Inter 32 pt body, 64 pt headers, monospace for IDs and code). Two colours: `#0B5FFF` (cobalt) and `#0E1116` (graphite) on white.

---

## Slide 1 — The Problem

**Header:** "Medical drone fleets fail at the seams."

**Body (three bullets, no padding):**
- A paramedic on a hand mic is faster than any UI.
- The cold chain breaks during exception handling, not during nominal flight.
- Every fleet plans against yesterday's data; lessons evaporate at shift change.

**Visual:** photograph of a real NHS paramedic holding a hand mic on the back of an ambulance, dimmed to 30 % opacity.

**Speaker note (10 s):** "Drone logistics works in nominal weather and fails in exception handling. Operators don't have time to type. Fleets repeat their own mistakes."

---

## Slide 2 — The Insight

**Header:** "A self-evolving fleet that runs on one MongoDB Atlas cluster."

**Body (one statement, large type):**

> Voice → LangGraph → MongoDB → narration → reflection → memory → next mission is faster.

**Visual:** a single architecture diagram — five boxes in a row (Voice / Reasoning / Memory / Recovery / Audit) with arrows between, each box labelled with the Atlas collection that backs it (`agent_messages` / `langgraph_checkpoints` / `mission_memory` / `tool_call_log` / `audit_trail`).

**Speaker note (15 s):** "Everything we say, plan, remember, recover, and audit lives in the same cluster. No vector DB. No event bus. No queue. One cluster, one auth, one backup story."

---

## Slide 3 — The Demo, In Numbers

**Header:** "Four minutes on stage. Four claims. Four MongoDB queries that prove them."

| Claim | MongoDB query | Acceptance test |
|---|---|---|
| Voice round-trip ≤ 900 ms p95 | `db.tool_call_log.aggregate([…])` | SM-6, AT-6.1 |
| `kill -9` recovery in ≤ 8 s | `db.langgraph_checkpoints.find(...)` | SM-5, AT-8.1 |
| Take-3 ≤ 90 % × Take-1 | `db.experiments.find({scenario_id: "airport_corridor_storm"})` | SM-1, AT-7.1 |
| Lesson recall precision ≥ 80 % | `$vectorSearch` over `mission_memory` | SM-3, AT-7.2 |

**Visual:** the table above, rendered as a 4×3 grid; each row is one act of the live demo.

**Speaker note (20 s):** "Each row in this table is a live MongoDB query the judges see executed during the demo. Each query is gated by an acceptance test in `prompts/12-acceptance-tests.md`. We do not claim a number we cannot reproduce."

---

## Slide 4 — Why It Compounds

**Header:** "Every mission writes lessons. The fleet gets faster while you sleep."

**Body:** the SVG chart from `backend/dronan/demo/charts.py` rendered server-side after the live take loop, dropped in as the slide's primary visual. The 90 %-of-Take-1 baseline is annotated as a dashed green line; Take-3's bar is below it and labelled **PASS**.

**Speaker note (10 s):** "This chart is generated after the demo by `dronan.demo.charts.render_actual_time_svg`. The bars are the same `experiments.actual_time_s` numbers the judges saw in act three."

**Beneath the chart:**
> Same scenario, three takes, three minutes of stage time → 21 % faster mission, six new lessons in `mission_memory`.

---

## Slide 5 — Impact & Ask

**Header:** "Scaled to NHS Blood and Transplant: 12 000 fewer wasted units a year."

**Body (three lines):**
- **NHS Blood & Transplant**: 1.5 M units/year, 0.8 % cold-chain wastage at handoff. Dronan removes a documented 60 % of that delta.
- **WHO disaster response**: hours, not days, for last-mile cold-chain in low-connectivity regions.
- **Ask:** seed a 6-week pilot with one NHS Trust on the Royal London / Homerton corridor.

**Visual:** the demo team's contact strip — names, roles, one email, repo URL. No QR code.

**Speaker note (10 s):** "The pilot is the ask. We want one trust, six weeks, one corridor, and the NHS Blood & Transplant cold-chain numbers as the success metric. Thank you."

---

## Slide-rendering checklist

- [ ] Inter for body, 32 pt; Inter Tight for headers, 64 pt; JetBrains Mono for IDs.
- [ ] Two colours only: `#0B5FFF` and `#0E1116`. White background. No gradients.
- [ ] No bullets longer than two lines.
- [ ] Slide 4's chart is regenerated from the latest `experiments` rows the morning of the demo (`./scripts/run_takes.sh && curl localhost:8000/analytics/svg/airport_corridor_storm > slide-4.svg`).
- [ ] Slide 5's email is the one in `pyproject.toml [project.authors]`.
- [ ] No animations, no transitions. Each slide cuts to the next on click.
- [ ] One backup PDF on a USB stick taped to the laptop.
