"""WeatherAgent — flyability check per leg."""

from __future__ import annotations

from typing import Any

from ..tools.weather import get_weather
from ._base import agent_node


@agent_node("weather")
async def weather_node(state: dict, *, db: Any) -> dict:
    plan = state.get("plan") or {}
    legs = plan.get("legs") or []
    if not legs:
        return {"weather": {"checked": 0, "flyable": True}}

    flyable = True
    summaries: list[dict] = []
    for leg in legs:
        for endpoint in (leg.get("from"), leg.get("to")):
            if not endpoint:
                continue
            obs = await get_weather(
                db=db,
                location_id=endpoint,
                idempotency_key=f"wx:{state.get('mission_id', 'anon')}:{endpoint}",
            )
            if obs is None:
                summaries.append({"location": endpoint, "flyable": True, "missing": True})
                continue
            summaries.append({"location": endpoint, "flyable": obs.get("flyable", True)})
            flyable = flyable and obs.get("flyable", True)

    return {
        "weather": {"flyable": flyable, "legs": summaries},
        "tool_calls": [{"tool": "get_weather", "agent": "weather", "n": len(summaries)}],
    }
