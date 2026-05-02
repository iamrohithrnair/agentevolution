"""REST smoke — every operator-facing route returns 200 on seeded data.

Acceptance per ``prompts/13 §6``: "All REST routes return 200 on the
seeded data."
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
async def app(mongo_db):
    from backend.dronan.api.main import create_app
    from backend.seeds.seed_drones import main as seed_drones
    from backend.seeds.seed_facilities import main as seed_fac
    from backend.seeds.seed_no_fly_zones import main as seed_nfz

    await seed_fac(mongo_db)
    await seed_nfz(mongo_db)
    await seed_drones(mongo_db)
    # Inject one weather observation so /weather/{id} resolves.
    await mongo_db.weather_observations.insert_one(
        {
            "_id": "wx-RoyalLondon-1",
            "location_id": "Royal London",
            "wind_kph": 8.0,
            "precip_mm_h": 0.0,
            "visibility_m": 10000,
            "classification": "flyable",
            "flyable": True,
            "ts": datetime.now(timezone.utc),
        }
    )
    return create_app(db=mongo_db, watcher_poll_interval=0.05)


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        # Manually run lifespan so app.state.db is set.
        async with app.router.lifespan_context(app):
            yield c


async def test_healthz(client) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_drones_facilities_nofly(client) -> None:
    r = await client.get("/drones")
    assert r.status_code == 200
    assert len(r.json()) == 3

    r = await client.get("/facilities")
    assert r.status_code == 200
    # ≥9 from the hardcoded LOCATIONS; larger when ``backend/data/facilities.xlsx``
    # is present (489 rows in the production seed).
    assert len(r.json()) >= 9

    r = await client.get("/nofly")
    assert r.status_code == 200
    assert len(r.json()) == 6


async def test_drone_404(client) -> None:
    r = await client.get("/drones/Nonexistent")
    assert r.status_code == 404


async def test_facility_get(client) -> None:
    r = await client.get("/facilities/Royal%20London")
    assert r.status_code == 200
    body = r.json()
    # Seeded facilities use ObjectId-style _id with the human label in `name`.
    assert body.get("name") == "Royal London" or body.get("_id") == "Royal London"


async def test_weather_endpoint(client) -> None:
    r = await client.get("/weather/Royal%20London")
    assert r.status_code == 200
    body = r.json()
    assert body["location_id"] == "Royal London"


async def test_chat_creates_history(client) -> None:
    r = await client.post(
        "/chat",
        json={"operator_id": "op-1", "text": "deliver blood to royal london"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["mission_id"].startswith("M-")


async def test_mission_create_and_get(client) -> None:
    r = await client.post(
        "/missions",
        json={
            "operator_id": "op-1",
            "request": "deliver blood",
            "depot": "Depot",
            "stops": ["Royal London"],
        },
    )
    assert r.status_code == 201
    body = r.json()
    # Response shape changed to match the frontend contract
    # ({mission_id, delivery_ids, drone_id, eta_seconds, mission}).
    mid = body.get("mission_id") or body.get("_id") or body["mission"]["_id"]
    r2 = await client.get(f"/missions/{mid}")
    assert r2.status_code == 200
    assert r2.json()["_id"] == mid


async def test_delivery_create(client, mongo_db) -> None:
    fac = await mongo_db.facilities.find_one({"name": "Royal London"})
    assert fac is not None
    r = await client.post(
        "/deliveries",
        json={
            "destination_id": "Royal London",
            "supply": "blood",
            "payload_weight_kg": 1.2,
            "priority": "critical",
            "cold_chain_required": True,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["destination_id"] == "Royal London"
    r2 = await client.get("/deliveries")
    assert r2.status_code == 200
    assert any(d["_id"] == body["_id"] for d in r2.json())


async def test_delivery_unknown_facility_404(client) -> None:
    r = await client.post(
        "/deliveries",
        json={
            "destination_id": "NoSuchClinic",
            "supply": "blood",
            "payload_weight_kg": 1.0,
        },
    )
    assert r.status_code == 404


async def test_memory_search(client) -> None:
    r = await client.post(
        "/memory/search",
        json={"query": "deliver blood to royal london", "k": 3},
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict) and isinstance(body.get("hits"), list)


async def test_reports_metrics(client) -> None:
    r = await client.get("/reports/metrics")
    assert r.status_code == 200
    body = r.json()
    assert "missions" in body or isinstance(body, dict)


async def test_internal_replan_404(client) -> None:
    r = await client.post(
        "/internal/replan",
        json={"mission_id": "DOES-NOT-EXIST", "reason": "weather_change"},
    )
    assert r.status_code == 404


async def test_internal_replan_marks_mission(client, mongo_db) -> None:
    await mongo_db.missions.insert_one(
        {
            "_id": "M-replan-1",
            "operator_id": "op-1",
            "request": "test",
            "status": "planned",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )
    r = await client.post(
        "/internal/replan",
        json={"mission_id": "M-replan-1", "reason": "weather_no_go"},
    )
    assert r.status_code == 200
    doc = await mongo_db.missions.find_one({"_id": "M-replan-1"})
    assert doc["needs_replan"] is True
    assert doc["replan_reason"] == "weather_no_go"


async def test_internal_low_battery(client, mongo_db) -> None:
    # Drone1 is idle from the seed; flip to flying so land_drone has work.
    await mongo_db.drones.update_one({"_id": "Drone1"}, {"$set": {"status": "flying"}})
    r = await client.post(
        "/internal/low_battery",
        json={"drone_id": "Drone1", "battery_pct": 0.18, "return_to_depot": True},
    )
    assert r.status_code == 200
    alerts = await mongo_db.alerts.count_documents({"kind": "low_battery"})
    assert alerts >= 1


async def test_livekit_token_endpoint_reflects_config(client) -> None:
    """503 when LiveKit creds are absent; 200 + token when present."""
    from backend.dronan.config import get_settings

    s = get_settings()
    r = await client.post("/livekit/token", json={"operator_id": "op-1"})
    if s.livekit_api_key and s.livekit_api_secret and s.livekit_url:
        # 200 (signed token) or 503 ('livekit_sdk_missing') if the SDK isn't installed.
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            body = r.json()
            assert body.get("token")
            assert body.get("url") == s.livekit_url
            assert body.get("room") == "dronan-ops"
    else:
        assert r.status_code == 503
