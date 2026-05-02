"""Internal endpoints — invoked by Atlas Triggers, not by the operator UI.

CORS is intentionally locked down (only configured trigger origins).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from ..tools._decorator import ToolError
from ..tools.drone_control import land_drone
from .deps import get_db

router = APIRouter(prefix="/internal", tags=["internal"])


class ReplanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_id: str
    reason: str = "weather_change"


@router.post("/replan")
async def replan(req: ReplanRequest, db: Any = Depends(get_db)) -> dict:
    """Mark a mission as needing replan and append an event row.

    A real ReplannerAgent invocation lives in P5; here we just annotate
    the mission so the supervisor will pick the replan branch on the
    next tick.
    """
    res = await db.missions.update_one(
        {"_id": req.mission_id},
        {
            "$set": {
                "needs_replan": True,
                "replan_reason": req.reason,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"mission {req.mission_id} not found")
    return {"mission_id": req.mission_id, "queued_for_replan": True, "reason": req.reason}


class ColdChainBreachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_id: str
    bag_temp_c: float
    threshold_c: float = 6.0


@router.post("/cold_chain_breach")
async def cold_chain_breach(req: ColdChainBreachRequest, db: Any = Depends(get_db)) -> dict:
    await db.alerts.insert_one(
        {
            "mission_id": req.mission_id,
            "kind": "cold_chain_breach",
            "bag_temp_c": req.bag_temp_c,
            "threshold_c": req.threshold_c,
            "ts": datetime.now(timezone.utc),
        }
    )
    return {"queued": True, "kind": "cold_chain_breach", "mission_id": req.mission_id}


class LowBatteryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drone_id: str
    battery_pct: float
    return_to_depot: bool = True


@router.post("/low_battery")
async def low_battery(req: LowBatteryRequest, db: Any = Depends(get_db)) -> dict:
    await db.alerts.insert_one(
        {
            "drone_id": req.drone_id,
            "kind": "low_battery",
            "battery_pct": req.battery_pct,
            "ts": datetime.now(timezone.utc),
        }
    )
    if req.return_to_depot:
        try:
            await land_drone(
                db=db,
                drone_id=req.drone_id,
                idempotency_key=f"low_bat:{req.drone_id}",
            )
        except ToolError:
            pass
    return {"queued": True, "kind": "low_battery", "drone_id": req.drone_id}
