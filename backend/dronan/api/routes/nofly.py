"""``/nofly`` — list active no-fly zones."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..deps import get_db
from ._helpers import serialise

router = APIRouter(prefix="/nofly", tags=["nofly"])


@router.get("")
async def list_nofly(db: Any = Depends(get_db)) -> list[dict]:
    cursor = db.no_fly_zones.find({}).sort("_id", 1)
    return [serialise(d) async for d in cursor]
