"""Geofence checks against the seeded NFZ corpus."""

from __future__ import annotations

import pytest

from backend.dronan.tools.geofence import check_route_safety

pytestmark = pytest.mark.unit


@pytest.fixture
async def seeded_nfz(mongo_db):
    from backend.seeds.seed_no_fly_zones import main as seed_nfz

    await seed_nfz(mongo_db)
    return mongo_db


async def test_route_clear_of_zones_is_safe(seeded_nfz) -> None:
    res = await check_route_safety(
        db=seeded_nfz,
        # Far west — outside every seeded zone
        waypoints=[(-1.5000, 51.5074), (-1.4000, 51.5074)],
        altitude_m=120,
        idempotency_key="g-1",
    )
    assert res["safe"] is True
    assert res["intrusions"] == []


async def test_route_through_demo_tfr_is_blocked(seeded_nfz) -> None:
    res = await check_route_safety(
        db=seeded_nfz,
        # Cuts directly through the synthetic east-London TFR
        # (lon -0.030 → 0.005, lat 51.515 → 51.530)
        waypoints=[(-0.040, 51.520), (0.010, 51.525)],
        altitude_m=100,
        idempotency_key="g-2",
    )
    assert res["safe"] is False
    names = {i["zone_name"] for i in res["intrusions"]}
    assert "TFR East London Demo" in names


async def test_route_above_ceiling_is_unaffected(seeded_nfz) -> None:
    """The TFR ceiling is 200m — flying at 500m clears it."""
    res = await check_route_safety(
        db=seeded_nfz,
        waypoints=[(-0.040, 51.520), (0.010, 51.525)],
        altitude_m=500,
        idempotency_key="g-3",
    )
    names = {i["zone_name"] for i in res["intrusions"]}
    assert "TFR East London Demo" not in names
