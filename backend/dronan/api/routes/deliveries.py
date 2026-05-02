"""``/deliveries`` — operator-facing delivery composer."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..deps import get_db
from ._helpers import serialise

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


class DeliveryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_id: str
    supply: str
    payload_weight_kg: float = Field(gt=0)
    priority: str = "normal"
    cold_chain_required: bool = False


@router.get("")
async def list_deliveries(db: Any = Depends(get_db), limit: int = 50) -> list[dict]:
    cursor = db.deliveries.find({}).sort("created_at", -1).limit(limit)
    return [serialise(d) async for d in cursor]


@router.post("", status_code=201)
async def create_delivery(payload: DeliveryCreate, db: Any = Depends(get_db)) -> dict:
    fac = await db.facilities.find_one({"_id": payload.destination_id})
    if fac is None:
        raise HTTPException(status_code=404, detail=f"facility {payload.destination_id} not found")
    now = datetime.now(timezone.utc)
    doc = {
        "_id": f"DEL-{uuid.uuid4().hex[:8]}",
        "destination_id": payload.destination_id,
        "supply": payload.supply,
        "payload_weight_kg": payload.payload_weight_kg,
        "priority": payload.priority,
        "status": "pending",
        "cold_chain_required": payload.cold_chain_required,
        "created_at": now,
        "updated_at": now,
    }
    await db.deliveries.insert_one(doc)
    return serialise(doc)
