"""FastAPI app factory.

``create_app(db=...)`` returns a fully wired ASGI app. The factory is
db-agnostic so tests can pass a ``mongomock-motor`` handle and prod
gets a real Motor client.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .internal import router as internal_router
from .routes import (
    chat_router,
    deliveries_router,
    drones_router,
    facilities_router,
    livekit_router,
    memory_router,
    missions_router,
    nofly_router,
    reports_router,
    weather_router,
)
from .ws import WatcherHub
from .ws import router as ws_router

log = logging.getLogger(__name__)

DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def _cors_origins() -> list[str]:
    extra = os.getenv("DRONAN_CORS_ORIGINS", "")
    raw = [o.strip() for o in extra.split(",") if o.strip()]
    return list(DEFAULT_CORS_ORIGINS) + raw


def create_app(*, db: Any | None = None, watcher_poll_interval: float = 0.5) -> FastAPI:
    """Build and return the FastAPI application.

    ``db`` may be:
      * a Motor / mongomock-motor database handle → mounted directly.
      * ``None`` → built lazily on startup from ``MONGO_URI``.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if db is not None:
            app.state.db = db
        else:
            from ..db import get_db

            app.state.db = get_db()
        app.state.watchers = WatcherHub(
            app.state.db, poll_interval=watcher_poll_interval
        )
        # Strong references for fire-and-forget tasks (Python 3.12+ only
        # keeps weak refs to the running loop's tasks).
        app.state.background_tasks = set()
        try:
            yield
        finally:
            await app.state.watchers.aclose()
            for t in list(app.state.background_tasks):
                t.cancel()

    app = FastAPI(
        title="Dronan API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        # Spell out custom headers explicitly — some browsers reject the
        # wildcard when ``allow_credentials=True``.
        allow_headers=[
            "*",
            "Content-Type",
            "Authorization",
            "Idempotency-Key",
            "X-Requested-With",
        ],
        expose_headers=["*"],
    )

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict:
        return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}

    # REST routers — mounted at both root (backward compat) and /api
    # (frontend convention). `no-fly-zones` is the plural kebab-case alias
    # the frontend uses for the nofly router.
    from .routes._frontend_compat import router as frontend_compat_router

    for prefix in ("", "/api"):
        app.include_router(chat_router, prefix=prefix)
        app.include_router(missions_router, prefix=prefix)
        app.include_router(deliveries_router, prefix=prefix)
        app.include_router(drones_router, prefix=prefix)
        app.include_router(facilities_router, prefix=prefix)
        app.include_router(weather_router, prefix=prefix)
        app.include_router(nofly_router, prefix=prefix)
        app.include_router(memory_router, prefix=prefix)
        app.include_router(reports_router, prefix=prefix)
        app.include_router(livekit_router, prefix=prefix)
        app.include_router(frontend_compat_router, prefix=prefix)

    # Internal (Atlas Triggers) — only at root.
    app.include_router(internal_router)

    # WebSocket
    app.include_router(ws_router)

    return app


async def run_graph_in_background(*, db: Any, mission_id: str, request: str) -> None:
    """Helper for /chat to fire-and-forget the LangGraph mission run.

    Imported lazily to avoid a circular-import on startup; LangGraph + the
    agents layer pull in heavyweight deps that we don't want every API
    request to amortise.
    """
    try:
        from ..graph import build_graph
    except Exception as exc:
        log.warning("graph build skipped: %s", exc)
        return

    graph = build_graph(db=db)
    config = {"configurable": {"thread_id": mission_id}, "recursion_limit": 50}
    initial = {
        "operator_id": "system",
        "mission_id": mission_id,
        "request": request,
    }
    try:
        await graph.ainvoke(initial, config=config)
    except Exception as exc:
        log.warning("graph run for %s failed: %s", mission_id, exc)
