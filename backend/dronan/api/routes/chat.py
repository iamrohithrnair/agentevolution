"""``/chat`` — operator chat ingress.

Persists the message into ``chat_history`` and forwards it through the
LangGraph mission graph in the background. The response returns the
mission_id so the UI can subscribe to ``/ws/missions``.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from ..deps import get_db
from ._helpers import serialise

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_id: str
    text: str
    run_graph: bool = False


@router.post("")
async def post_chat(turn: ChatTurn, db: Any = Depends(get_db)) -> dict:
    now = datetime.now(timezone.utc)
    mission_id = f"M-{uuid.uuid4().hex[:10]}"

    await db.chat_history.insert_one(
        {
            "operator_id": turn.operator_id,
            "mission_id": mission_id,
            "role": "operator",
            "text": turn.text,
            "ts": now,
        }
    )

    if turn.run_graph:
        # Schedule the graph asynchronously — the WS clients will pick
        # up the writes via change-streams.
        from ..main import run_graph_in_background

        asyncio.create_task(run_graph_in_background(db=db, mission_id=mission_id, request=turn.text))

    return serialise(
        {
            "mission_id": mission_id,
            "accepted_at": now,
            "ws": "/ws/missions",
        }
    )
