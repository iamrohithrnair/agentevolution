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

# Static specialist order — each agent fires at most once per mission.
# Termination is driven off ``route_history`` membership, not state-channel
# predicates, because LangGraph reducer-backed channels (``anomalies``,
# ``obstacles``) initialise to ``[]``, making "is None" predicates unreliable.
_STATIC_ORDER: tuple[Route, ...] = (
    "interpreter",
    "memory",
    "planner",
    "weather",
    "geofence",
    "preflight",
    "payload",
    "dispatch",
    "vision",
    "anomaly",
    "deconfliction",
    "replanner",
    "demand_forecast",
    "analyst",
    "reflection",
    "narrator",
)

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
    """Pick the next ``route`` (or end).

    Strategy:
      1. Walk ``_STATIC_ORDER``; the first agent NOT yet in
         ``route_history`` is the next route. This is a cheap, fully
         deterministic baseline.
      2. If the static order is exhausted but ``state["needs_replan"]``
         is True, route back into the planner once.
      3. Otherwise vector-search ``agent_skills`` for the closest peer to
         the operator's request — but never the agent we just visited and
         never one that's already been visited twice.
      4. End.
    """
    history: list[Route] = list(state.get("route_history", []) or [])
    last = state.get("last_routed_to")

    if len(history) >= _MAX_HOPS:
        return {"route": "__end__"}

    visited = set(history)

    # 1. Static order — first unvisited specialist wins.
    for nxt in _STATIC_ORDER:
        if nxt not in visited:
            return {"route": nxt, "last_routed_to": nxt}

    # 2. Re-plan if the replanner flagged it.
    if state.get("needs_replan") and history.count("planner") < 2 and last != "planner":
        return {"route": "planner", "last_routed_to": "planner"}

    # 3. Vector-search fallback for ad-hoc requests.
    intent = state.get("request")
    if intent:
        peer = await _discover_peer(
            db=db,
            intent=str(intent),
            mission_id=state.get("mission_id"),
        )
        if peer and peer != last and history.count(peer) < 2 and peer != "supervisor":
            return {"route": peer, "last_routed_to": peer}

    return {"route": "__end__"}
