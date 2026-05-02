"""SupervisorAgent — owns the ``route`` channel.

Routing strategy (deterministic, LLM-free in P3):

1. **Pre-conditions** force a fixed early sequence: ``interpreter →
   memory → planner → weather → geofence → preflight → payload →
   dispatch``. Each step fires exactly once and is gated on the matching
   state channel being empty.
2. **Post-flight** monitors run after dispatch:
   ``vision → anomaly → deconfliction → replanner → analyst →
   reflection → narrator → __end__``.
3. **Vector search peer discovery** — when the static rule above can't
   pick a winner (e.g. mid-flight anomaly), the supervisor embeds the
   *current goal* and runs a cosine search against ``agent_skills`` to
   pick the closest specialist. This satisfies the prompts/04 §1 + §3
   contract without needing an LLM in the loop.
"""

from __future__ import annotations

from typing import Any

from ..tools.memory import vector_search
from ._base import agent_node
from .state import Route

# Static-rule order. Each entry is (next_route, predicate_on_state).
_STATIC_RULES: list[tuple[Route, Any]] = [
    ("interpreter", lambda s: not s.get("parsed_task")),
    ("memory", lambda s: not any(p.get("agent") == "memory" for p in s.get("plan_step_log", []))),
    ("planner", lambda s: not s.get("plan")),
    ("weather", lambda s: not s.get("weather")),
    ("geofence", lambda s: s.get("no_fly_violations") is None),
    ("preflight", lambda s: not any(p.get("agent") == "preflight" for p in s.get("plan_step_log", []))),
    ("payload", lambda s: not s.get("payload_status")),
    ("dispatch", lambda s: s.get("live_telemetry") is None),
    ("vision", lambda s: not any(p.get("agent") == "vision" for p in s.get("tool_calls", []))),
    ("anomaly", lambda s: s.get("anomalies") is None),
    ("deconfliction", lambda s: not any(p.get("agent") == "deconfliction" for p in s.get("plan_step_log", []))),
    ("replanner", lambda s: not any(p.get("agent") == "replanner" for p in s.get("plan_step_log", []))),
    ("analyst", lambda s: not any(p.get("agent") == "analyst" for p in s.get("plan_step_log", []))),
    ("reflection", lambda s: not s.get("reflection")),
    ("narrator", lambda s: not any(p.get("agent") == "narrator" for p in s.get("plan_step_log", []))),
]

_MAX_HOPS = 40


async def _discover_peer(
    *, db: Any, intent: str, mission_id: str | None
) -> str | None:
    """Return the agent_id whose ``capability_text`` is closest to ``intent``."""
    if db is None or not intent:
        return None
    cards = await vector_search(
        db=db,
        query=intent,
        collection="agent_skills",
        k=1,
        idempotency_key=f"sup:{mission_id or 'anon'}:{intent[:32]}",
    )
    if not cards:
        return None
    # agent_skills rows store ``agent`` at the top level, not in metadata.
    return cards[0].get("agent") or cards[0].get("metadata", {}).get("agent")


@agent_node("supervisor", record_route=False)
async def supervisor_node(state: dict, *, db: Any) -> dict:
    """Pick the next ``route`` (or end)."""
    history: list[Route] = state.get("route_history", []) or []
    if len(history) >= _MAX_HOPS:
        return {"route": "__end__"}

    # 1. Static rules — first one whose predicate fires wins.
    for nxt, predicate in _STATIC_RULES:
        try:
            ok = predicate(state)
        except Exception:
            ok = False
        if ok and (state.get("last_routed_to") != nxt):
            return {"route": nxt, "last_routed_to": nxt}

    # 2. Vector search fallback.
    intent = (
        state.get("request")
        or state.get("parsed_task", {}).get("supplies")
        or "complete the mission"
    )
    peer = await _discover_peer(
        db=db,
        intent=str(intent),
        mission_id=state.get("mission_id"),
    )
    if peer and peer != state.get("last_routed_to"):
        return {"route": peer, "last_routed_to": peer}

    # 3. End — every static channel filled.
    return {"route": "__end__"}
