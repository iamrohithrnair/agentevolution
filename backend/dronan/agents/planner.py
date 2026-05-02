"""PlannerAgent — wraps the OR-Tools route planner."""

from __future__ import annotations

from typing import Any

from ..tools.route_planner import compute_route
from ._base import agent_node


@agent_node("planner")
async def planner_node(state: dict, *, db: Any) -> dict:
    depot = state.get("depot")
    stops = list(state.get("stops") or [])

    if not depot or not stops:
        return {
            "errors": [{"agent": "planner", "error": "missing depot/stops in state"}]
        }

    plan = await compute_route(
        db=db,
        depot=depot,
        stops=stops,
        idempotency_key=f"plan:{state.get('mission_id', 'anon')}",
    )
    return {
        "plan": plan,
        "tool_calls": [{"tool": "compute_route", "agent": "planner"}],
    }
