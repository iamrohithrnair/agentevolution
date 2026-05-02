"""Round-trip tests for the Pydantic data models."""

from __future__ import annotations

import pytest

from backend.dronan.models import (
    AgentSkill,
    Delivery,
    Drone,
    Facility,
    Mission,
    MissionMemory,
    NoFlyZone,
    Regulation,
    RouteWaypoint,
    SyntheticEmergency,
    point,
    polygon,
    utcnow,
)

pytestmark = pytest.mark.unit


def test_facility_round_trip() -> None:
    f = Facility(
        name="Royal London",
        type="hospital",
        location=point(-0.0590, 51.5185),
        airsim_xy={"x": 100, "y": 50, "z": -30},
        capabilities=["trauma"],
    )
    blob = f.model_dump(by_alias=True)
    assert blob["location"]["coordinates"] == [-0.0590, 51.5185]
    assert blob["airsim_xy"]["z"] == -30


def test_drone_validates_battery() -> None:
    d = Drone(
        _id="Drone1",
        battery=100,
        position=point(-0.1278, 51.5074),
    )
    assert d.id == "Drone1"
    assert d.battery == 100


def test_no_fly_zone_geometry() -> None:
    z = NoFlyZone(
        name="Demo TFR",
        source="TFR",
        country="GB",
        severity="restricted",
        altitude_floor_m=0,
        altitude_ceiling_m=200,
        geometry=polygon(
            [[
                (-0.030, 51.515),
                (-0.030, 51.530),
                (0.005, 51.530),
                (0.005, 51.515),
                (-0.030, 51.515),
            ]]
        ),
        effective_from=utcnow(),
    )
    assert z.geometry["type"] == "Polygon"


def test_regulation_required_fields() -> None:
    r = Regulation(
        code="UK_CAA",
        country="GB",
        title="UK CAA Article 16",
        version="2024.10",
        max_altitude_m=120,
        bvlos_allowed=False,
        night_allowed=True,
        over_people_allowed=False,
        max_takeoff_mass_kg=25,
        notes_md="## Maximum altitude\nNo more than 120 m AGL.",
    )
    assert r.code == "UK_CAA"


def test_synthetic_emergency_severity_bounds() -> None:
    with pytest.raises(ValueError):
        SyntheticEmergency(
            ts=utcnow(),
            location_id="x",
            location_lat=51.0,
            location_lon=-0.1,
            emergency_type="trauma",
            severity=99,  # out of range
            temperature_c=18,
            weather_condition="clear",
            hour_of_day=0,
            day_of_week=0,
        )


def test_mission_memory_embedding() -> None:
    m = MissionMemory(
        kind="reflection",
        title="t",
        text="hello",
        embedding=[0.1] * 1024,
    )
    assert len(m.embedding) == 1024


def test_agent_skill_reliability_bounds() -> None:
    s = AgentSkill(
        agent="RoutePlannerAgent",
        capability_text="…",
        embedding=[0.0] * 1024,
        reliability_score=0.93,
    )
    assert 0 <= s.reliability_score <= 1


def test_delivery_priority() -> None:
    d = Delivery(
        destination_id="Royal London",
        supply="trauma_kit",
        payload_weight_kg=2.4,
        priority="critical",
        requested_by="user_1",
    )
    assert d.priority == "critical"


def test_mission_with_routes() -> None:
    m = Mission(
        _id="MED-0421",
        delivery_ids=[],
        drone_id="Drone1",
        planned_route=[
            RouteWaypoint(name="Depot", lat=51.5074, lon=-0.1278),
            RouteWaypoint(name="Royal London", lat=51.5185, lon=-0.0590),
        ],
    )
    assert m.id == "MED-0421"
    assert len(m.planned_route) == 2
