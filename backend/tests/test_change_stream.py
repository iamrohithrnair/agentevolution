"""WebSocket change-stream test (SM-8).

Acceptance per ``prompts/13 §6``: insert into ``flight_logs`` →
WebSocket message arrives within 500 ms (mongomock uses the polling
fallback at 50 ms cadence so this is well under the budget).

The insert is triggered through an in-process HTTP route so both the
WebSocket and the database write run on the same event-loop thread that
``TestClient`` spawns; using ``asyncio.run_until_complete`` from the
test thread breaks because mongomock-motor is not safe across loops.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from fastapi import APIRouter
from starlette.testclient import TestClient

pytestmark = pytest.mark.unit


def _make_test_app(mongo_db):
    """Build the real app + a tiny test-only insert route."""
    from backend.dronan.api.main import create_app

    app = create_app(db=mongo_db, watcher_poll_interval=0.05)

    test_router = APIRouter()

    @test_router.post("/_test/insert_flight_log")
    async def insert_flight_log() -> dict:
        doc = {
            "_id": "fl-ws-1",
            "mission_id": "M-ws-1",
            "ts": datetime.now(timezone.utc),
            "msg": "hello",
        }
        await mongo_db.flight_logs.insert_one(doc)
        return {"inserted": doc["_id"]}

    app.include_router(test_router)
    return app


@pytest.fixture
def app(mongo_db):
    return _make_test_app(mongo_db)


def test_flight_log_insert_arrives_on_ws(app) -> None:
    """SM-8: insert into flight_logs → WS event within 500 ms."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/flight_logs") as ws:
            ready = ws.receive_json()
            assert ready["type"] == "ready"
            assert ready["collection"] == "flight_logs"

            # Trigger the insert in the same event loop the watcher runs in.
            r = client.post("/_test/insert_flight_log")
            assert r.status_code == 200
            t0 = time.monotonic()

            # Drain — the next message after `ready` should be the insert event.
            evt = ws.receive_json()
            elapsed = time.monotonic() - t0
            assert evt.get("type") == "event", f"unexpected first frame: {evt}"
            # SM-8 budget: 500 ms.
            assert elapsed <= 0.5, f"event arrived in {elapsed:.2f}s, budget is 500 ms"
            assert evt["collection"] == "flight_logs"
            assert evt["doc"]["_id"] == "fl-ws-1"
            assert evt["doc"]["mission_id"] == "M-ws-1"


def test_unwatched_collection_rejected(app) -> None:
    """Connecting to an un-watched collection should be closed (1003)."""
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/employees") as ws:
                ws.receive_json(timeout=0.5)
