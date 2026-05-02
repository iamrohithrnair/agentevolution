"""``/facilities`` — list/get."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_db
from ._helpers import serialise

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.get("")
async def list_facilities(db: Any = Depends(get_db)) -> list[dict]:
    return [serialise(d) async for d in db.facilities.find({}).sort("_id", 1)]


@router.get("/{facility_id}")
async def get_facility(facility_id: str, db: Any = Depends(get_db)) -> dict:
    doc = await db.facilities.find_one({"_id": facility_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"facility {facility_id} not found")
    return serialise(doc)
