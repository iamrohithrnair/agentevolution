"""Tests for ``compute_route`` / ``recompute_route`` (Phase 2 acceptance)."""

from __future__ import annotations

import pytest

from backend.dronan.tools.route_planner import compute_route, recompute_route

pytestmark = pytest.mark.unit


@pytest.fixture
async def seeded_facilities(mongo_db):
    from backend.seeds.seed_facilities import main as seed_facilities

    await seed_facilities(mongo_db)
    return mongo_db


async def test_compute_route_returns_full_tour(seeded_facilities) -> None:
    db = seeded_facilities
    res = await compute_route(
        db=db,
        depot="Depot",
        stops=["Royal London", "Newham General"],
        idempotency_key="MED-T-1:plan",
    )
    assert res["depot"] == "Depot"
    assert set(res["stops"]) == {"Royal London", "Newham General"}
    assert res["distance_m"] > 0
    assert res["eta_seconds"] > 0
    # Waypoints includes depot, every stop, and a return-to-depot.
    assert res["waypoints"][0]["name"] == "Depot"
    assert res["waypoints"][-1]["kind"] == "depot_return"
    # Solver name reflects whichever path executed.
    assert res["solver"] in {"or-tools", "haversine-nn"}
    # Pre-paired legs — consumed by weather/geofence agents.
    assert "legs" in res and len(res["legs"]) == len(res["waypoints"]) - 1
    leg = res["legs"][0]
    for k in ("from", "to", "from_coord", "to_coord"):
        assert k in leg
    assert leg["from"] == "Depot"
    assert isinstance(leg["from_coord"], tuple) and len(leg["from_coord"]) == 2


async def test_compute_route_idempotency_skips_solver(seeded_facilities) -> None:
    db = seeded_facilities

    from backend.dronan.tools import route_planner as rp

    calls = {"nn": 0, "or": 0}
    real_nn = rp._nn_tour
    real_or = rp._solve_with_ortools

    def _spy_nn(*a, **k):
        calls["nn"] += 1
        return real_nn(*a, **k)

    def _spy_or(*a, **k):  # pragma: no cover — only fires when ortools is available
        calls["or"] += 1
        return real_or(*a, **k)

    rp._nn_tour = _spy_nn  # type: ignore[assignment]
    rp._solve_with_ortools = _spy_or  # type: ignore[assignment]
    try:
        await compute_route(
            db=db,
            depot="Depot",
            stops=["Homerton"],
            idempotency_key="MED-T-2:plan",
        )
        first = calls["nn"] + calls["or"]
        await compute_route(
            db=db,
            depot="Depot",
            stops=["Homerton"],
            idempotency_key="MED-T-2:plan",
        )
        second = calls["nn"] + calls["or"]
        assert first >= 1
        assert second == first  # zero new solver invocations
    finally:
        rp._nn_tour = real_nn  # type: ignore[assignment]
        rp._solve_with_ortools = real_or  # type: ignore[assignment]


async def test_recompute_route_carries_avoid_zones(seeded_facilities) -> None:
    db = seeded_facilities
    res = await recompute_route(
        db=db,
        depot="Depot",
        stops=["Whipps Cross"],
        avoid_zones=["TFR East London Demo"],
        idempotency_key="MED-T-3:replan",
    )
    assert res["avoided_zones"] == ["TFR East London Demo"]
    assert res["depot"] == "Depot"


async def test_compute_route_unknown_stop_raises(seeded_facilities) -> None:
    db = seeded_facilities
    from backend.dronan.tools._decorator import ToolError

    with pytest.raises(ToolError):
        await compute_route(
            db=db,
            depot="Depot",
            stops=["Atlantis Memorial Hospital"],
            idempotency_key="MED-T-4:plan",
        )
