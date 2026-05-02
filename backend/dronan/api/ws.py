"""WebSocket fanout — tails MongoDB collections and pushes events to clients.

Supports two modes:
* **Change streams** (production, MongoDB ≥ 4.0 replica set) — uses
  ``collection.watch()`` to stream inserts/updates/deletes.
* **Polling fallback** (tests, mongomock) — periodically polls for new
  ``_id``s and emits inserts. ``CollectionWatcher.poll_interval`` controls
  the cadence; tests use 50 ms.

The watcher is broadcast-style: any number of WebSocket clients can
subscribe per collection.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .deps import get_db

log = logging.getLogger(__name__)

WATCHED_COLLECTIONS: tuple[str, ...] = (
    "missions",
    "flight_logs",
    "telemetry",
    "mission_memory",
    "narrations",
    "traces",
    "drones",
)

# Map Mongo collection names to the WSKind values the frontend subscribes to.
_KIND_FOR_COLLECTION: dict[str, str] = {
    "telemetry": "telemetry",
    "flight_logs": "flight_log",
    "missions": "mission_update",
    "drones": "drone_update",
    "mission_memory": "reflection",
    "narrations": "narration",
    "traces": "trace",
}


def _shape_drone(doc: dict) -> dict:
    """Inline shaping for drone updates (mirror routes/_helpers.to_drone)."""
    pos = doc.get("position") or {}
    coords = (pos or {}).get("coordinates") if isinstance(pos, dict) else None
    if not (isinstance(coords, list) and len(coords) >= 2):
        coords = [0.0, 0.0]
    return {
        "id": str(doc.get("_id") or ""),
        "status": doc.get("status") or "idle",
        "battery": float(doc.get("battery") or 0.0),
        "position": [float(coords[0]), float(coords[1])],
        "heading_deg": float(doc.get("heading_deg") or 0.0),
        "current_mission_id": doc.get("current_mission_id"),
        "last_seen": doc.get("last_seen"),
        "payload_temp_c": doc.get("payload_temp_c"),
    }


def _translate_envelope(collection: str, doc: dict) -> dict | None:
    """Translate (collection, doc) into the frontend ``{kind, doc}`` envelope.

    Returns ``None`` when there's no client-side listener for the collection.
    """
    kind = _KIND_FOR_COLLECTION.get(collection)
    if not kind:
        return None
    shaped = _shape_drone(doc) if collection == "drones" else doc
    return {"kind": kind, "doc": shaped, "collection": collection}


def _serialise(doc: Any) -> Any:
    """Return a JSON-safe shallow copy of ``doc``."""
    from .routes._helpers import serialise

    return serialise(doc)


class CollectionWatcher:
    """Tail one collection and broadcast inserts to subscribers.

    Uses ``collection.watch()`` if available, else polls ``_id`` order.
    """

    def __init__(self, db: Any, collection: str, *, poll_interval: float = 0.5):
        self.db = db
        self.collection_name = collection
        self.poll_interval = poll_interval
        self._subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._seen_ids: set[Any] = set()

    async def subscribe(self) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(q)
        if self._task is None:
            self._task = asyncio.create_task(self._run())
        try:
            while True:
                evt = await q.get()
                if evt is None:
                    return
                yield evt
        finally:
            self._subscribers.discard(q)

    async def _broadcast(self, evt: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(evt)
            except Exception:
                pass

    async def _run(self) -> None:
        coll = self.db[self.collection_name]
        try:
            async for change in coll.watch(full_document="updateLookup"):
                if self._stop.is_set():
                    break
                doc = change.get("fullDocument") or {}
                op = change.get("operationType", "insert")
                await self._broadcast(
                    {"collection": self.collection_name, "op": op, "doc": _serialise(doc)}
                )
            return
        except Exception as exc:
            log.info(
                "change-stream unavailable for %s (%s) — falling back to polling",
                self.collection_name,
                exc.__class__.__name__,
            )

        # Seed the seen-set so we only emit new docs.
        try:
            existing = await coll.find({}, {"_id": 1}).to_list(length=10_000)
            self._seen_ids.update(d["_id"] for d in existing)
        except Exception:
            pass

        while not self._stop.is_set():
            try:
                cursor = coll.find({}, {"_id": 1})
                ids = {d["_id"] async for d in cursor}
                new_ids = ids - self._seen_ids
                for new_id in new_ids:
                    doc = await coll.find_one({"_id": new_id})
                    if doc is None:
                        continue
                    await self._broadcast(
                        {
                            "collection": self.collection_name,
                            "op": "insert",
                            "doc": _serialise(doc),
                        }
                    )
                self._seen_ids = ids
            except Exception as exc:
                log.warning("polling watch failed for %s: %s", self.collection_name, exc)
            await asyncio.sleep(self.poll_interval)

    async def aclose(self) -> None:
        self._stop.set()
        for q in list(self._subscribers):
            await q.put(None)
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass


class WatcherHub:
    """Per-app collection-watcher registry."""

    def __init__(self, db: Any, *, poll_interval: float = 0.5):
        self.db = db
        self.poll_interval = poll_interval
        self._watchers: dict[str, CollectionWatcher] = {}

    def get(self, collection: str) -> CollectionWatcher:
        if collection not in self._watchers:
            self._watchers[collection] = CollectionWatcher(
                self.db, collection, poll_interval=self.poll_interval
            )
        return self._watchers[collection]

    async def aclose(self) -> None:
        for w in self._watchers.values():
            await w.aclose()


router = APIRouter()


@router.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket) -> None:
    """Multiplexed fan-out of every watched collection.

    The frontend dashboard subscribes here once instead of opening one
    socket per collection. Each event is wrapped with the source
    collection name so the client can route it.
    """
    await websocket.accept()
    hub: WatcherHub = websocket.app.state.watchers

    await websocket.send_json(
        {
            "type": "ready",
            "collections": list(WATCHED_COLLECTIONS),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )

    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1000)

    async def pump(name: str) -> None:
        watcher = hub.get(name)
        async for evt in watcher.subscribe():
            doc = evt.get("doc") or {}
            envelope = _translate_envelope(name, doc)
            if envelope is None:
                continue
            try:
                queue.put_nowait(envelope)
            except asyncio.QueueFull:
                pass

    pumps = [asyncio.create_task(pump(c)) for c in WATCHED_COLLECTIONS]
    try:
        while True:
            evt = await queue.get()
            await websocket.send_json(evt)
    except WebSocketDisconnect:
        return
    finally:
        for p in pumps:
            p.cancel()


@router.websocket("/ws/{collection}")
async def ws_collection(websocket: WebSocket, collection: str) -> None:
    """Stream inserts/updates from ``collection`` to the client.

    Only collections in ``WATCHED_COLLECTIONS`` are allowed.
    """
    if collection not in WATCHED_COLLECTIONS:
        await websocket.close(code=1003, reason=f"collection '{collection}' not watched")
        return

    await websocket.accept()
    hub: WatcherHub = websocket.app.state.watchers
    watcher = hub.get(collection)

    await websocket.send_json(
        {"type": "ready", "collection": collection, "ts": datetime.now(timezone.utc).isoformat()}
    )

    try:
        async for evt in watcher.subscribe():
            await websocket.send_json({"type": "event", **evt})
    except WebSocketDisconnect:
        return
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("ws %s closed with %s", collection, exc)
        try:
            await websocket.close(code=1011, reason=str(exc))
        except Exception:
            pass
