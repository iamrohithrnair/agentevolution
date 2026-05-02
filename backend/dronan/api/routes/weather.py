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
    # No explicit idempotency_key: weather is a freshness-sensitive read.
    # An explicit key would make the @mongo_tool decorator return the first
    # cached observation forever, which is dangerous for flight-safety
    # decisions.
    obs = await _get_weather(db=db, location_id=location_id)
    if obs is None:
        raise HTTPException(status_code=404, detail=f"no weather for {location_id}")
    return serialise(obs)
