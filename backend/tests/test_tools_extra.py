"""Additional tool coverage: payload, weather, dispatch, preflight."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.dronan.tools import (
    ToolError,
    aggregate_metrics,
    assemble_manifest,
    cold_chain_predict,
    dispatch_mission,
    get_weather,
    inspect_telemetry,
    land_drone,
    record_signature,
    run_preflight,
    simulate_weather_event,
)

pytestmark = pytest.mark.unit


@pytest.fixture
async def seeded_full(mongo_db):
    from backend.seeds.seed_agent_skills import main as seed_skills
    from backend.seeds.seed_demo_memory import main as seed_memory
    from backend.seeds.seed_drones import main as seed_drones
    from backend.seeds.seed_facilities import main as seed_fac
    from backend.seeds.seed_no_fly_zones import main as seed_nfz

    await seed_fac(mongo_db)
    await seed_nfz(mongo_db)
    await seed_drones(mongo_db)
    await seed_memory(mongo_db)
    await seed_skills(mongo_db)
    return mongo_db


# --- payload ----------------------------------------------------------------
async def test_cold_chain_predict_breach_recommends_extra_pack() -> None:
    res = await cold_chain_predict(
        initial_temp_c=4.0,
        ambient_temp_c=24.0,
        ice_pack_count=0,
        flight_minutes=10,
        bag_ceiling_c=6.0,
    )
    assert res["breach"] is True
    assert res["recommended_extra_ice_pack"] is True


async def test_cold_chain_predict_safe_with_packs() -> None:
    res = await cold_chain_predict(
        initial_temp_c=4.0,
        ambient_temp_c=18.0,
        ice_pack_count=2,
        flight_minutes=10,
        bag_ceiling_c=6.0,
    )
    assert res["breach"] is False


async def test_assemble_manifest_validates_drone(seeded_full) -> None:
    db = seeded_full
    await db.deliveries.insert_one(
        {
            "_id": "DEL-T1",
            "supply": "blood",
            "payload_weight_kg": 0.5,
            "destination_id": "Royal London",
            "cold_chain_required": True,
        }
    )
    res = await assemble_manifest(
        db=db,
        delivery_ids=["DEL-T1"],
        drone_id="Drone1",
        idempotency_key="m-1",
    )
    assert res["over_limit"] is False
    assert res["cold_chain_required"] is True


async def test_assemble_manifest_unknown_drone_raises(seeded_full) -> None:
    db = seeded_full
    await db.deliveries.insert_one(
        {"_id": "DEL-T2", "supply": "x", "payload_weight_kg": 0.1}
    )
    with pytest.raises(ToolError):
        await assemble_manifest(
            db=db,
            delivery_ids=["DEL-T2"],
            drone_id="DroneZZZ",
            idempotency_key="m-2",
        )


# --- weather ----------------------------------------------------------------
async def test_simulate_and_get_weather_round_trip(mongo_db) -> None:
    res = await simulate_weather_event(
        db=mongo_db,
        location_id="Royal London",
        wind_speed_ms=14.0,
        gust_ms=18.0,
        condition="wind",
        idempotency_key="w-1",
    )
    assert res["inserted"] is True
    obs = await get_weather(db=mongo_db, location_id="Royal London", idempotency_key="w-2")
    assert obs is not None
    assert obs["flyable"] is False  # 14 m/s exceeds 12 m/s threshold


async def test_get_weather_missing_location(mongo_db) -> None:
    obs = await get_weather(db=mongo_db, location_id="Nowhere", idempotency_key="w-3")
    assert obs is None


# --- dispatch / drone_control -----------------------------------------------
async def test_dispatch_mission_flips_drone_state(seeded_full) -> None:
    db = seeded_full
    await db.missions.insert_one({"_id": "MED-T-DISP-1", "status": "planned"})
    res = await dispatch_mission(
        db=db,
        mission_id="MED-T-DISP-1",
        drone_id="Drone1",
        idempotency_key="d-1",
    )
    assert res["status"] == "executing"
    drone = await db.drones.find_one({"_id": "Drone1"})
    assert drone["status"] == "flying"
    assert drone["current_mission_id"] == "MED-T-DISP-1"


async def test_dispatch_then_land(seeded_full) -> None:
    db = seeded_full
    await db.missions.insert_one({"_id": "MED-T-DISP-2", "status": "planned"})
    await dispatch_mission(
        db=db,
        mission_id="MED-T-DISP-2",
        drone_id="Drone2",
        idempotency_key="d-2",
    )
    res = await land_drone(db=db, drone_id="Drone2", idempotency_key="d-3")
    assert res["status"] == "idle"


# --- preflight --------------------------------------------------------------
async def test_run_preflight_passes_after_seeds(seeded_full) -> None:
    res = await run_preflight(db=seeded_full, idempotency_key="pf-1")
    assert res["ready"] is True
    names = {c["name"] for c in res["checks"]}
    assert {
        "facilities_seeded",
        "drones_idle",
        "agent_skills_seeded",
        "mission_memory_seeded",
        "no_fly_zones_seeded",
    } <= names


async def test_run_preflight_fails_without_seeds(mongo_db) -> None:
    res = await run_preflight(db=mongo_db, idempotency_key="pf-2")
    assert res["ready"] is False


# --- audit + analytics + anomaly -------------------------------------------
async def test_record_signature_appends_row(mongo_db) -> None:
    res = await record_signature(
        db=mongo_db,
        mission_id="MED-T-A1",
        step="plan_route",
        payload={"depot": "Depot", "stops": ["Royal London"]},
        idempotency_key="a-1",
    )
    assert len(res["digest"]) == 64
    row = await mongo_db.audit_trail.find_one(
        {"mission_id": "MED-T-A1", "step": "plan_route"}
    )
    assert row is not None
    assert row["digest"] == res["digest"]


async def test_aggregate_metrics_runs_against_empty_db(mongo_db) -> None:
    res = await aggregate_metrics(db=mongo_db, since_minutes=10, idempotency_key="m-1")
    assert res["missions"] == 0
    assert res["deliveries"] == 0


async def test_inspect_telemetry_battery_sag(mongo_db) -> None:
    now = datetime.now(timezone.utc)
    samples = []
    for i, bat in enumerate([95, 92, 90, 87, 85]):
        samples.append(
            {
                "mission_id": "MED-T-AN1",
                "ts": now - timedelta(seconds=(5 - i) * 30),
                "battery_pct": bat,
                "hdop": 1.0,
            }
        )
    await mongo_db.telemetry.insert_many(samples)

    res = await inspect_telemetry(
        db=mongo_db,
        mission_id="MED-T-AN1",
        window_minutes=10,
        idempotency_key="an-1",
    )
    kinds = {a["kind"] for a in res["anomalies"]}
    assert "battery_sag" in kinds
