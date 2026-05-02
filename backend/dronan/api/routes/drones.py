"""``/drones`` — read-only drone fleet view."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_db
from ._helpers import serialise

router = APIRouter(prefix="/drones", tags=["drones"])


@router.get("")
async def list_drones(db: Any = Depends(get_db)) -> list[dict]:
    return [serialise(d) async for d in db.drones.find({}).sort("_id", 1)]


@router.get("/{drone_id}")
async def get_drone(drone_id: str, db: Any = Depends(get_db)) -> dict:
    doc = await db.drones.find_one({"_id": drone_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"drone {drone_id} not found")
    return serialise(doc)
