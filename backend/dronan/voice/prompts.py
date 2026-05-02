"""System prompts and narration templates for the Mission Control voice persona.

Why this lives in its own file:

- The supervisor in :mod:`dronan.graph` (Session A) injects ``MISSION_CONTROL_SYSTEM``
  into its system message when invoked from the LiveKit worker.
- The narrator stream renders ``NARRATION_TEMPLATES`` against ``flight_logs.payload``.
- The signature task speaks ``SIGNATURE_PROMPT`` and listens for one utterance.

Keep these strings short and operationally focused. The persona is *calm,
authoritative, no filler*. We avoid hedging language ("I think", "maybe") and
chit-chat — operators are clinicians under time pressure.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Mission Control persona prompt — injected by the LangGraph supervisor as a
# system message when the LiveKit worker is the caller (text mode keeps the
# default supervisor prompt). ~200 words, deliberately terse.
# --------------------------------------------------------------------------- #

MISSION_CONTROL_SYSTEM = """\
You are Dronan Mission Control. You operate a fleet of three medical delivery
drones over east London for the NHS. The operator is a paramedic on a hand
mic; their time is more valuable than yours.

Style:
- Speak in short, declarative sentences. No filler ("um", "well", "I think").
- Confirm intent before dispatching. Read back: drone, supply, destination, ETA.
- Lead with the action, then the reason. Bad: "Because of wind, I'll reroute."
  Good: "Rerouting Drone 1 inland — wind shear at 90 metres."
- Numbers as words for ETAs ("ten minutes"), digits for IDs ("Drone 2").
- Never repeat narration the operator just heard. The narrator already covered it.
- If you can't act (no drones available, weather hard-block, geofence violation),
  state the blocker and propose the next-best option in one sentence.

Always retrieve relevant lessons from mission_memory before planning. Cite the
lesson IDs in your reasoning trace (the operator does not hear them, but the
ReflectionAgent does). Reply in the operator's language; default English.

You will be evaluated on time-to-first-token (≤350 ms) and end-to-end voice
loop latency (≤1200 ms p50, ≤900 ms p95). Brevity is correctness.
"""


# --------------------------------------------------------------------------- #
# Narration templates — keyed by flight_logs.event. Rendered against
# flight_logs.payload via str.format(**payload). Add new events here, not in
# the narrator stream itself.
# --------------------------------------------------------------------------- #

NARRATION_TEMPLATES: dict[str, str] = {
    "takeoff": "{drone} is wheels up from {from_}.",
    "waypoint_reached": "{drone} reached {place}.",
    "obstacle": "Obstacle ahead. {drone} is climbing to {alt} metres to clear it.",
    "reroute": "Rerouting {drone} via {via}. ETA slips by {delta}.",
    "delivered": "Payload delivered at {place}. Cold chain held at {temp} degrees.",
    "battery_low": "Heads up — {drone} battery at {pct} percent. Returning to depot.",
    "weather_alert": "Storm cell over {place}. Replanner is engaged.",
    "no_fly_violation": "Warning. {drone} flagged a no-fly proximity at {place}. Diverting.",
    "anomaly": "Anomaly: {kind} on {drone}. Investigating.",
    "landed": "{drone} is on the ground at {place}.",
}


# --------------------------------------------------------------------------- #
# Signature capture
# --------------------------------------------------------------------------- #

SIGNATURE_PROMPT = (
    "Please confirm receipt for the audit log. State your full name, role, and "
    "the supply you received. I will read it back."
)


def render_narration(event: str, payload: dict) -> str | None:
    """Render the narration for a flight_logs document.

    Returns ``None`` when ``event`` has no template (we silently drop, the
    operator already sees it on the map). Falls back to ``payload['message']``
    if the template references missing keys, then to a generic ``"<event> event."``.
    """
    template = NARRATION_TEMPLATES.get(event)
    if template is None:
        return None
    try:
        return template.format(**payload)
    except KeyError:
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
        return f"{event.replace('_', ' ').capitalize()} event."
