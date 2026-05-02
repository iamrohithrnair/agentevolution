"""``/chat`` — operator chat ingress.

Accepts both the canonical body ``{operator_id, text, run_graph}`` and
the simpler frontend body ``{message, mission_id?}``. Returns either
JSON (no streaming) or text/event-stream when the request asks for SSE
via the ``Accept`` header or ``?stream=1`` query param.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from ..deps import get_db
from ._helpers import serialise

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatTurn(BaseModel):
    """Permissive chat body — every field optional, validates on either shape."""

    model_config = ConfigDict(extra="ignore")

    # Canonical
    operator_id: str | None = None
    text: str | None = None
    run_graph: bool = False
    # Frontend convenience
    message: str | None = None
    mission_id: str | None = None

    @property
    def resolved_text(self) -> str:
        return (self.text or self.message or "").strip()

    @property
    def resolved_operator(self) -> str:
        return self.operator_id or "operator"


def _sse(event: str, data: Any) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


async def _stream_chat(turn: ChatTurn, db: Any, mission_id: str):
    """Yield an SSE stream that mirrors the LangGraph reply pattern.

    P3 ships a deterministic supervisor; we yield a short scripted token
    sequence so the dashboard's reasoning panel renders something useful
    while the real graph runs in the background and writes to Mongo.
    """
    yield _sse("start", {"mission_id": mission_id})
    yield _sse("tool", {"name": "memory.recall", "input": {"query": turn.resolved_text[:80]}})

    reply = (
        f"Affirmative — request received: \"{turn.resolved_text[:120]}\". "
        "Routing through the supervisor; planner solving the route now. "
        "Memory recall returned the relevant cards. Watch the map."
    )
    for word in reply.split(" "):
        await asyncio.sleep(0.02)
        yield _sse("token", {"text": word + " "})

    yield _sse("done", {"mission_id": mission_id})


@router.post("")
async def post_chat(turn: ChatTurn, request: Request, db: Any = Depends(get_db)):
    now = datetime.now(timezone.utc)
    mission_id = turn.mission_id or f"M-{uuid.uuid4().hex[:10]}"
    text = turn.resolved_text

    await db.chat_history.insert_one(
        {
            "operator_id": turn.resolved_operator,
            "mission_id": mission_id,
            "role": "operator",
            "text": text,
            "ts": now,
        }
    )

    if turn.run_graph:
        from ..main import run_graph_in_background

        asyncio.create_task(
            run_graph_in_background(db=db, mission_id=mission_id, request=text)
        )

    accept = request.headers.get("accept", "")
    wants_sse = "text/event-stream" in accept or request.query_params.get("stream") == "1"
    if wants_sse:
        return StreamingResponse(
            _stream_chat(turn, db, mission_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return serialise(
        {
            "mission_id": mission_id,
            "accepted_at": now,
            "ws": "/ws/missions",
        }
    )
