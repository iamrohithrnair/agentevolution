"""FastAPI dependency providers — db handle, app state."""

from __future__ import annotations

from typing import Any

from fastapi import Request


async def get_db(request: Request) -> Any:
    """Return the Motor database stored on ``app.state``.

    The factory ``create_app`` mounts either a real Motor client or a
    mongomock-motor fixture during tests.
    """
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise RuntimeError("app.state.db not configured")
    return db
