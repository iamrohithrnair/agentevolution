"""Phase 1 acceptance tests — every seed runs idempotently against an
in-memory mongomock database.

The corresponding integration tests against a real Atlas Sandbox cluster
are gated behind ``DRONAN_REAL_ATLAS=1``.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from backend.dronan.bootstrap import bootstrap
from backend.seeds import (
    create_indexes,
    seed_agent_skills,
    seed_demo_memory,
    seed_drones,
    seed_facilities,
    seed_no_fly_zones,
    seed_regulations,
    seed_synthetic_emergencies,
)

pytestmark = pytest.mark.unit


async def test_create_indexes_idempotent(mongo_db) -> None:
    s1 = await create_indexes.main(mongo_db)
    s2 = await create_indexes.main(mongo_db)
    # Re-running yields the same set of index names.
    assert s1.keys() == s2.keys()
    # Facilities should have a 2dsphere index after bootstrap.
    assert "loc_2dsphere" in s2.get("facilities", [])


async def test_bootstrap_creates_collections(mongo_db) -> None:
    await bootstrap(mongo_db)
    names = set(await mongo_db.list_collection_names())
    for required in (
        "facilities",
        "no_fly_zones",
        "drones",
        "deliveries",
        "missions",
        "mission_memory",
        "regulations",
        "synthetic_emergencies",
        "agent_skills",
        "agent_messages",
        "tool_call_log",
    ):
        assert required in names, f"missing collection {required}"


async def test_seed_facilities_idempotent(mongo_db) -> None:
    r1 = await seed_facilities.main(mongo_db)
    r2 = await seed_facilities.main(mongo_db)
    assert r1["total"] >= 9
    assert r2["upserted"] == 0
    # The 9 hardcoded LOCATIONS must all be present.
    for name in (
        "Depot", "Clinic A", "Clinic B", "Clinic C", "Clinic D",
        "Royal London", "Homerton", "Newham General", "Whipps Cross",
    ):
        doc = await mongo_db.facilities.find_one({"name": name})
        assert doc is not None
        assert doc["location"]["type"] == "Point"
    depot = await mongo_db.facilities.find_one({"name": "Depot"})
    assert depot["airsim_xy"] == {"x": 0.0, "y": 0.0, "z": -30.0}


async def test_seed_no_fly_zones_idempotent(mongo_db) -> None:
    r1 = await seed_no_fly_zones.main(mongo_db)
    r2 = await seed_no_fly_zones.main(mongo_db)
    assert r1["total"] == 6  # 5 canonical + 1 demo TFR
    assert r2["upserted"] == 0
    heathrow = await mongo_db.no_fly_zones.find_one({"name": "UK CAA Heathrow CTR"})
    assert heathrow is not None
    assert heathrow["severity"] == "prohibited"


async def test_seed_regulations_seeds_memory(mongo_db) -> None:
    r1 = await seed_regulations.main(mongo_db)
    r2 = await seed_regulations.main(mongo_db)
    assert r1["regs_total"] == 5  # UK_CAA + FAA + 3 EASA
    assert r2["regs_upserted"] == 0
    assert r2["mem_upserted"] == 0
    # Each profile produced ≥ 1 memory chunk.
    cnt = await mongo_db.mission_memory.count_documents({"kind": "regulation"})
    assert cnt >= 5
    # Embedding shape is correct.
    sample = await mongo_db.mission_memory.find_one({"kind": "regulation"})
    assert sample is not None
    assert isinstance(sample["embedding"], list)
    assert len(sample["embedding"]) >= 256


async def test_seed_drones_idempotent(mongo_db) -> None:
    r1 = await seed_drones.main(mongo_db)
    r2 = await seed_drones.main(mongo_db)
    assert r1["total"] == 3
    assert r2["upserted"] == 0
    drone1 = await mongo_db.drones.find_one({"_id": "Drone1"})
    assert drone1["status"] == "idle"
    assert drone1["battery"] == 100


async def test_seed_demo_memory_idempotent(mongo_db) -> None:
    r1 = await seed_demo_memory.main(mongo_db)
    r2 = await seed_demo_memory.main(mongo_db)
    assert r1["total"] == 3
    assert r2["upserted"] == 0


async def test_seed_agent_skills_idempotent(mongo_db) -> None:
    r1 = await seed_agent_skills.main(mongo_db)
    r2 = await seed_agent_skills.main(mongo_db)
    assert r1["total"] == 17  # 17 agents
    assert r2["upserted"] == 0
    sup = await mongo_db.agent_skills.find_one({"agent": "SupervisorAgent"})
    assert sup is not None
    assert isinstance(sup["embedding"], list)
    assert len(sup["embedding"]) >= 256


async def test_seed_synthetic_emergencies_skips_when_csv_missing(
    mongo_db, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When the CSV is absent the seed exits cleanly with `skipped:True`."""
    monkeypatch.setenv(
        "DRONAN_EMERGENCIES_CSV",
        str(tmp_path / "does-not-exist.csv"),
    )
    # Reload the module so it re-reads the env var.
    import importlib

    from backend.seeds import seed_synthetic_emergencies as ss

    importlib.reload(ss)
    res = await ss.main(mongo_db)
    assert res.get("skipped") is True
    assert res["total"] == 0


async def test_seed_synthetic_emergencies_loads_csv(
    mongo_db, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Generates a tiny CSV in the expected format and asserts inserts.
    Re-running shows zero diffs (idempotency)."""
    csv_path = tmp_path / "synth.csv"
    headers = [
        "ts", "location_id", "location_lat", "location_lon",
        "emergency_type", "severity", "temperature_c", "weather_condition",
        "is_holiday", "is_event", "hour_of_day", "day_of_week",
    ]
    rows = [
        ["2025-01-01T00:05:24Z", "Clinic B", "51.5174", "-0.135",
         "respiratory", "1", "-0.9", "snow", "true", "false", "0", "2"],
        ["2025-01-01T01:30:00Z", "Royal London", "51.5185", "-0.0590",
         "trauma", "3", "5.2", "clear", "false", "false", "1", "2"],
    ]
    with csv_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(headers)
        w.writerows(rows)
    monkeypatch.setenv("DRONAN_EMERGENCIES_CSV", str(csv_path))
    monkeypatch.setenv("DRONAN_EMERGENCIES_BATCH", "1")

    import importlib

    from backend.seeds import seed_synthetic_emergencies as ss

    importlib.reload(ss)
    r1 = await ss.main(mongo_db)
    r2 = await ss.main(mongo_db)
    assert r1["total"] == 2
    assert r2["upserted"] == 0
