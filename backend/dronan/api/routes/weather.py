"""``/weather`` — observed weather snapshots."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ...tools.weather import get_weather as _get_weather
from ..deps import get_db
from ._helpers import serialise

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/{location_id}")
async def get_weather(location_id: str, db: Any = Depends(get_db)) -> dict:
    obs = await _get_weather(
        db=db,
        location_id=location_id,
        idempotency_key=f"wx:{location_id}",
    )
    if obs is None:
        raise HTTPException(status_code=404, detail=f"no weather for {location_id}")
    return serialise(obs)
