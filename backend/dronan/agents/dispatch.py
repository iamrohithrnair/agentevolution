"""DispatchAgent — bind drone to mission and flip to flying."""

from __future__ import annotations

from typing import Any

from ..tools._decorator import ToolError
from ..tools.drone_control import dispatch_mission
from ._base import agent_node


@agent_node("dispatch")
async def dispatch_node(state: dict, *, db: Any) -> dict:
    mission_id = state.get("mission_id")
    drone_id = state.get("drone_id") or "Drone1"

    if not mission_id:
        return {"errors": [{"agent": "dispatch", "error": "missing mission_id"}]}

    try:
        res = await dispatch_mission(
            db=db,
            mission_id=mission_id,
            drone_id=drone_id,
            idempotency_key=f"dispatch:{mission_id}",
        )
    except ToolError as exc:
        return {"errors": [{"agent": "dispatch", "error": str(exc)}]}

    return {
        "plan_step_log": [{"agent": "dispatch", "drone_id": drone_id}],
        "tool_calls": [{"tool": "dispatch_mission", "agent": "dispatch"}],
        "live_telemetry": {"status": res.get("status")},
    }
