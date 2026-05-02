"""``/missions`` — list, fetch, create-from-chat."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ...tools.route_planner import compute_route
from ..deps import get_db
from ._helpers import serialise

router = APIRouter(prefix="/missions", tags=["missions"])


class MissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_id: str
    request: str
    depot: str = "Depot"
    stops: list[str] = Field(default_factory=list)


@router.get("")
async def list_missions(db: Any = Depends(get_db), limit: int = 25) -> list[dict]:
    cursor = db.missions.find({}).sort("created_at", -1).limit(limit)
    return [serialise(d) async for d in cursor]


@router.get("/{mission_id}")
async def get_mission(mission_id: str, db: Any = Depends(get_db)) -> dict:
    doc = await db.missions.find_one({"_id": mission_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"mission {mission_id} not found")
    return serialise(doc)


@router.post("", status_code=201)
async def create_mission(payload: MissionCreate, db: Any = Depends(get_db)) -> dict:
    mission_id = f"M-{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)
    plan = None
    if payload.stops:
        plan = await compute_route(
            db=db,
            depot=payload.depot,
            stops=payload.stops,
            idempotency_key=f"plan:{mission_id}",
        )

    doc = {
        "_id": mission_id,
        "operator_id": payload.operator_id,
        "request": payload.request,
        "depot": payload.depot,
        "stops": payload.stops,
        "status": "planned",
        "plan": plan,
        "created_at": now,
        "updated_at": now,
    }
    await db.missions.insert_one(doc)
    return serialise(doc)
