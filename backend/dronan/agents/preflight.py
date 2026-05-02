"""PreflightAgent — runs the preflight tool."""

from __future__ import annotations

from typing import Any

from ..tools.preflight import run_preflight
from ._base import agent_node


@agent_node("preflight")
async def preflight_node(state: dict, *, db: Any) -> dict:
    res = await run_preflight(
        db=db,
        idempotency_key=f"pf:{state.get('mission_id', 'anon')}",
    )
    return {
        "plan_step_log": [{"agent": "preflight", "ready": res["ready"]}],
        "tool_calls": [{"tool": "run_preflight", "agent": "preflight"}],
    }
