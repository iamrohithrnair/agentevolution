"""``/livekit/token`` — mints a JWT for the voice front-end.

When LiveKit is not configured (no env keys), returns 503 so the
front-end can fall back to text-only chat.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from ...config import get_settings

router = APIRouter(prefix="/livekit", tags=["livekit"])


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_id: str
    room: str = "dronan-ops"


@router.post("/token")
async def mint_token(req: TokenRequest) -> dict:
    settings = get_settings()
    if not (settings.livekit_api_key and settings.livekit_api_secret and settings.livekit_url):
        raise HTTPException(status_code=503, detail="livekit_not_configured")

    try:
        from livekit import api as lk  # type: ignore[import-not-found]
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="livekit_sdk_missing") from exc

    grants = lk.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
    grants = (
        grants.with_identity(req.operator_id)
        .with_name(req.operator_id)
        .with_grants(lk.VideoGrants(room_join=True, room=req.room))
    )
    return {
        "token": grants.to_jwt(),
        "url": settings.livekit_url,
        "room": req.room,
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }
