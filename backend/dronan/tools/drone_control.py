"""Drone-control adapters — mock controller + optional AirSim / PX4 hooks.

Phase 2 ships only the ``MockController``; real adapters land in P5/P6
when AirSim is wired in. The mock writes mission state transitions into
``missions`` and ``drones`` so the rest of the stack can observe them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ._decorator import ToolError, mongo_tool


@mongo_tool(side_effect_class="actuate", agent="DispatchAgent")
async def dispatch_mission(
    *,
    db: Any,
    mission_id: str,
    drone_id: str,
) -> dict:
    """Bind ``drone_id`` to ``mission_id``; flip both into the flying state.

    Optimistic concurrency: ``drones`` carries a ``version`` field — the
    update only succeeds when the version matches, preventing two
    Supervisors from grabbing the same airframe.
    """
    drone = await db.drones.find_one({"_id": drone_id})
    if drone is None:
        raise ToolError(f"Unknown drone: {drone_id}")
    if drone.get("status") != "idle":
        raise ToolError(f"Drone {drone_id} not idle (status={drone.get('status')})")

    now = datetime.now(timezone.utc)
    # Optimistic concurrency: only flip a drone that is *still* idle. The
    # filter doubles as our version check — two Supervisors racing for the
    # same drone will see exactly one ``modified_count == 1``.
    res = await db.drones.update_one(
        {"_id": drone_id, "status": "idle"},
        {
            "$set": {
                "status": "flying",
                "current_mission_id": mission_id,
                "updated_at": now,
            }
        },
    )
    if res.modified_count == 0:
        raise ToolError(f"Drone {drone_id} no longer idle; replan")

    await db.missions.update_one(
        {"_id": mission_id},
        {
            "$set": {
                "status": "executing",
                "drone_id": drone_id,
                "dispatched_at": now,
            }
        },
        upsert=True,
    )
    return {
        "mission_id": mission_id,
        "drone_id": drone_id,
        "dispatched_at": now,
        "status": "executing",
    }


@mongo_tool(side_effect_class="actuate", agent="DispatchAgent")
async def land_drone(*, db: Any, drone_id: str) -> dict:
    """Mark drone idle. Used by the demo recovery path."""
    now = datetime.now(timezone.utc)
    res = await db.drones.update_one(
        {"_id": drone_id},
        {
            "$set": {
                "status": "idle",
                "current_mission_id": None,
                "updated_at": now,
            }
        },
    )
    if res.matched_count == 0:
        raise ToolError(f"Unknown drone: {drone_id}")
    return {"drone_id": drone_id, "status": "idle", "ts": now}
