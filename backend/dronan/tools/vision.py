"""Vision tools — obstacle detection + frame storage.

Real YOLO inference and GridFS frame storage land in P5 (when ``ultralytics``
ships with the worker image). For now we expose a stub that returns no
detections but keeps the call signature stable so agents and the API can
already wire it in.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ._decorator import mongo_tool


@mongo_tool(side_effect_class="read", agent="VisionAgent")
async def detect_obstacles(
    *,
    db: Any | None = None,
    frame_bytes: bytes | None = None,
    mission_id: str | None = None,
) -> dict:
    """Stub detector — returns ``{detections: [], model: "stub"}``.

    Real implementation runs ``ultralytics.YOLO("yolov8n.pt")`` against
    ``frame_bytes`` and persists the frame to GridFS.
    """
    return {
        "detections": [],
        "model": "stub",
        "frame_bytes_size": len(frame_bytes) if frame_bytes else 0,
        "mission_id": mission_id,
    }


@mongo_tool(side_effect_class="audit", agent="VisionAgent")
async def save_frame(
    *,
    db: Any,
    frame_bytes: bytes,
    mission_id: str,
    metadata: dict | None = None,
) -> dict:
    """Persist a frame into the GridFS ``frames`` bucket. Stubbed for P2."""
    now = datetime.now(timezone.utc)
    doc = {
        "mission_id": mission_id,
        "size": len(frame_bytes),
        "metadata": metadata or {},
        "created_at": now,
    }
    await db["frames.files"].insert_one(doc)
    return {"saved": True, "size": len(frame_bytes), "mission_id": mission_id, "ts": now}
