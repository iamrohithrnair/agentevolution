"""Weather tools — read the time-series ``weather_observations`` collection.

``simulate_weather_event`` is used by the demo trigger to inject a synthetic
gust / TFR-like event. ``get_weather`` returns the latest observation per
location with a flyability gate decision.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ._decorator import mongo_tool


def _flyable(obs: dict) -> bool:
    wind = float(obs.get("wind_speed_ms", 0.0))
    gust = float(obs.get("gust_ms", wind))
    visibility = float(obs.get("visibility_m", 5_000))
    cond = (obs.get("condition") or "").lower()
    if wind >= 12.0 or gust >= 16.0:
        return False
    if visibility < 1_500:
        return False
    if any(t in cond for t in ("storm", "fog", "snow")):
        return False
    return True


@mongo_tool(side_effect_class="read", agent="WeatherAgent")
async def get_weather(*, db: Any, location_id: str) -> dict | None:
    """Return the most recent weather observation for ``location_id``."""
    cursor = (
        db.weather_observations.find({"location_id": location_id})
        .sort("ts", -1)
        .limit(1)
    )
    docs = await cursor.to_list(length=1)
    if not docs:
        return None
    obs = docs[0]
    return {
        "location_id": obs.get("location_id"),
        "ts": obs.get("ts"),
        "wind_speed_ms": obs.get("wind_speed_ms", 0.0),
        "gust_ms": obs.get("gust_ms", obs.get("wind_speed_ms", 0.0)),
        "visibility_m": obs.get("visibility_m"),
        "condition": obs.get("condition"),
        "temperature_c": obs.get("temperature_c"),
        "flyable": _flyable(obs),
    }


@mongo_tool(side_effect_class="actuate", agent="WeatherAgent")
async def simulate_weather_event(
    *,
    db: Any,
    location_id: str,
    wind_speed_ms: float,
    gust_ms: float | None = None,
    condition: str = "wind",
    visibility_m: float = 5000.0,
    temperature_c: float = 18.0,
    duration_min: int = 30,
) -> dict:
    """Insert a synthetic weather observation. Used by the demo trigger."""
    now = datetime.now(timezone.utc)
    doc = {
        "ts": now,
        "location_id": location_id,
        "wind_speed_ms": wind_speed_ms,
        "gust_ms": gust_ms if gust_ms is not None else wind_speed_ms * 1.3,
        "visibility_m": visibility_m,
        "condition": condition,
        "temperature_c": temperature_c,
        "expires_at": now + timedelta(minutes=duration_min),
        "synthetic": True,
    }
    await db.weather_observations.insert_one(doc)
    return {
        "inserted": True,
        "location_id": location_id,
        "ts": now,
        "flyable": _flyable(doc),
    }
