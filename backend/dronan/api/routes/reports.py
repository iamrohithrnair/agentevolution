"""``/reports`` — analytics aggregations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ...tools.analytics import aggregate_metrics
from ..deps import get_db
from ._helpers import serialise

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/metrics")
async def metrics(since_minutes: int = 60, db: Any = Depends(get_db)) -> dict:
    # No explicit idempotency_key: metrics are freshness-sensitive. An
    # explicit key would make the @mongo_tool decorator return the first
    # aggregation forever and never reflect new missions / deliveries.
    res = await aggregate_metrics(db=db, since_minutes=since_minutes)
    return serialise(res)
