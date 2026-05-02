"""GeofenceAgent — check_route_safety against no_fly_zones."""

from __future__ import annotations

from typing import Any

from ..tools.geofence import check_route_safety
from ._base import agent_node


@agent_node("geofence")
async def geofence_node(state: dict, *, db: Any) -> dict:
    plan = state.get("plan") or {}
    waypoints: list[tuple[float, float]] = []

    # The route plan stores legs with "from_coord"/"to_coord" tuples — fall back
    # to (lon, lat) of facilities looked up from the leg names when tuples
    # aren't present (e.g. a degenerate stub plan).
    for leg in plan.get("legs", []):
        if "from_coord" in leg:
            waypoints.append(tuple(leg["from_coord"]))
        if "to_coord" in leg:
            waypoints.append(tuple(leg["to_coord"]))

    if len(waypoints) < 2:
        return {"no_fly_violations": []}

    res = await check_route_safety(
        db=db,
        waypoints=waypoints,
        altitude_m=state.get("altitude_m", 100.0),
        idempotency_key=f"geo:{state.get('mission_id', 'anon')}",
    )
    return {
        "no_fly_violations": res["intrusions"],
        "tool_calls": [{"tool": "check_route_safety", "agent": "geofence"}],
    }
