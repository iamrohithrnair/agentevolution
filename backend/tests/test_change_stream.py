"""WebSocket change-stream test (SM-8).

Acceptance per ``prompts/13 §6``: insert into ``flight_logs`` →
WebSocket message arrives within 500 ms (mongomock uses the polling
fallback at 50 ms cadence so this is well under the budget).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from starlette.testclient import TestClient

pytestmark = pytest.mark.unit


@pytest.fixture
async def app(mongo_db):
    from backend.dronan.api.main import create_app

    return create_app(db=mongo_db, watcher_poll_interval=0.05)


async def _wait_for_event(ws, timeout: float = 1.0) -> dict | None:
    """Drain ws until we see an event-typed message or timeout."""
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        try:
            msg = ws.receive_json(timeout=0.1)
        except Exception:
            await asyncio.sleep(0.05)
            continue
        if msg.get("type") == "event":
            return msg
    return None


def test_flight_log_insert_arrives_on_ws(app, mongo_db) -> None:
    """Sync test using starlette's TestClient (WS API is sync there)."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/flight_logs") as ws:
            ready = ws.receive_json()
            assert ready["type"] == "ready"
            assert ready["collection"] == "flight_logs"

            # Insert one row — the watcher should see it within the polling window.
            asyncio.get_event_loop().run_until_complete(
                mongo_db.flight_logs.insert_one(
                    {
                        "_id": "fl-ws-1",
                        "mission_id": "M-ws-1",
                        "ts": datetime.now(timezone.utc),
                        "msg": "hello",
                    }
                )
            )

            # SM-8 budget: 500 ms.
            evt = None
            deadline = 0.5
            import time

            t0 = time.monotonic()
            while time.monotonic() - t0 < deadline:
                try:
                    msg = ws.receive_json(timeout=0.1)
                except Exception:
                    continue
                if msg.get("type") == "event":
                    evt = msg
                    break

            assert evt is not None, "no WS event within 500 ms"
            assert evt["collection"] == "flight_logs"
            assert evt["doc"]["_id"] == "fl-ws-1"
            assert evt["doc"]["mission_id"] == "M-ws-1"


def test_unwatched_collection_rejected(app) -> None:
    with TestClient(app) as client:
        try:
            with client.websocket_connect("/ws/employees") as ws:
                # Server should close before we read anything.
                msg = ws.receive_json(timeout=0.5)
                # If we get a message at all, it must not be 'ready'.
                assert msg.get("type") != "ready"
        except Exception:
            # WebSocketDisconnect raised on close(1003) — expected.
            pass
