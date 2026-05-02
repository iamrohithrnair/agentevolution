"""Unit tests for the agents layer (regressions for Devin Review BUG_0001-0004)."""

from __future__ import annotations

import pytest

from backend.dronan.agents.interpreter import _extract_locations, interpreter_node
from backend.dronan.agents.geofence import geofence_node
from backend.dronan.agents.payload import payload_node
from backend.dronan.agents.weather import weather_node

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# BUG_0001 — interpreter dedup on facility extraction.
# ---------------------------------------------------------------------------
def test_extract_locations_dedupes_repeated_facility() -> None:
    """A repeated mention of the same facility must collapse to one entry."""
    out = _extract_locations("deliver from depot to depot")
    assert out == ["Depot"]


def test_extract_locations_preserves_order() -> None:
    out = _extract_locations("from depot to clinic a then to royal london")
    assert out == ["Depot", "Clinic A", "Royal London"]


async def test_interpreter_node_dedupes_self_delivery() -> None:
    state = {"request": "deliver blood from depot to depot"}
    out = await interpreter_node(state)
    assert out["depot"] == "Depot"
    assert out["stops"] != ["Depot"], "self-delivery should not survive interpreter"


# ---------------------------------------------------------------------------
# BUG_0002 / BUG_0003 — weather + geofence consume plan["legs"].
# ---------------------------------------------------------------------------
async def test_weather_consumes_plan_legs(mongo_db) -> None:
    from datetime import datetime, timezone

    # 20 m/s wind ≫ 12 m/s threshold → not flyable per backend tools.weather._flyable.
    await mongo_db.weather_observations.insert_one(
        {
            "_id": "wx-RoyalLondon-1",
            "location_id": "Royal London",
            "wind_speed_ms": 20.0,
            "gust_ms": 25.0,
            "visibility_m": 10000,
            "condition": "storm",
            "temperature_c": 5.0,
            "ts": datetime.now(timezone.utc),
        }
    )

    state = {
        "mission_id": "M-wx-1",
        "plan": {
            "legs": [
                {
                    "from": "Depot",
                    "to": "Royal London",
                    "from_coord": (0.0, 51.5),
                    "to_coord": (0.05, 51.52),
                }
            ]
        },
    }
    out = await weather_node(state, db=mongo_db)
    # If the agent had silently bypassed (legs == []), flyable would default
    # to True. Assert the gate actually fired.
    assert out["weather"]["flyable"] is False
    assert any(s.get("flyable") is False for s in out["weather"]["legs"])


async def test_geofence_consumes_plan_legs(mongo_db) -> None:
    """Geofence must call check_route_safety when legs are present."""
    from backend.dronan.agents import geofence as geofence_agent_mod

    calls: list[dict] = []

    async def _spy(**kwargs):
        calls.append(kwargs)
        return {"intrusions": [{"zone_id": "TFR-X"}]}

    real = geofence_agent_mod.check_route_safety
    geofence_agent_mod.check_route_safety = _spy  # type: ignore[assignment]
    try:
        state = {
            "mission_id": "M-geo-1",
            "altitude_m": 100.0,
            "plan": {
                "legs": [
                    {
                        "from": "Depot",
                        "to": "Royal London",
                        "from_coord": (-0.1, 51.5),
                        "to_coord": (0.05, 51.52),
                    }
                ]
            },
        }
        out = await geofence_node(state, db=mongo_db)
        assert calls, "check_route_safety was not called — geofence bypassed"
        assert out["no_fly_violations"] == [{"zone_id": "TFR-X"}]
    finally:
        geofence_agent_mod.check_route_safety = real  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# BUG_0004 — payload reads eta_seconds from the route plan.
# ---------------------------------------------------------------------------
async def test_payload_uses_eta_seconds(mongo_db) -> None:
    """Payload node must use the actual route ETA, not a hardcoded fallback."""
    from datetime import datetime, timezone

    from backend.seeds.seed_drones import main as seed_drones

    # assemble_manifest looks up the drone by _id.
    await seed_drones(mongo_db)
    await mongo_db.deliveries.insert_one(
        {
            "_id": "DEL-cc-1",
            "destination_id": "Royal London",
            "supply": "blood",
            "payload_weight_kg": 1.0,
            "priority": "critical",
            "status": "pending",
            "cold_chain_required": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    from backend.dronan.agents import payload as payload_agent_mod

    captured: dict = {}
    real = payload_agent_mod.cold_chain_predict

    async def _spy(**kw):
        captured.update(kw)
        return await real(**kw)

    payload_agent_mod.cold_chain_predict = _spy  # type: ignore[assignment]
    try:
        state = {
            "mission_id": "M-cc-1",
            "drone_id": "Drone1",
            "delivery_ids": ["DEL-cc-1"],
            "plan": {"eta_seconds": 1800},  # 30 min
        }
        await payload_node(state, db=mongo_db)
    finally:
        payload_agent_mod.cold_chain_predict = real  # type: ignore[assignment]

    # 1800 s / 60 = 30.0 minutes. The default fallback would have been 600/60 = 10.
    assert captured.get("flight_minutes") == pytest.approx(30.0)
