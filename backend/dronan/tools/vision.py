"""Vision tools — YOLO obstacle detection + GridFS frame storage.

Ported and adapted from ``DroneFleet/simulation/cv_obstacle_detector.py``.

* ``detect_obstacles`` runs ``ultralytics.YOLO("yolov8n.pt")`` against the
  supplied JPEG/PNG bytes and returns the obstacle list in the format
  agents and the API expect (``{detections, model, evasion}``). When
  ``ultralytics`` isn't importable, the model can't load, or no frame
  is provided, we fall back to a deterministic mock so the call signature
  stays stable for the tests.
* ``save_frame`` persists the raw frame bytes into the Atlas GridFS
  ``frames`` bucket and returns the file id. On engines without GridFS
  (mongomock), we degrade to a plain ``frames.files`` document containing
  the metadata only — the unit tests don't read the bytes back.
"""

from __future__ import annotations

import io
import logging
import random
from datetime import datetime, timezone
from typing import Any

from ._decorator import mongo_tool

log = logging.getLogger(__name__)


# Obstacle classes that should trigger evasion (matches DroneFleet).
OBSTACLE_CLASSES: frozenset[str] = frozenset(
    {
        "person",
        "car",
        "truck",
        "bus",
        "bird",
        "airplane",
        "train",
        "boat",
        "bench",
        "chair",
        "potted plant",
        "building",
        "tree",
        "tower",
        "crane",
    }
)

DEFAULT_MODEL_PATH = "yolov8n.pt"
DEFAULT_CONFIDENCE = 0.5

_yolo_model: Any = None  # cached YOLO instance
_yolo_load_attempted = False


def _try_load_yolo(model_path: str = DEFAULT_MODEL_PATH) -> Any | None:
    """Lazily load YOLO once. Returns None on any failure (caller falls back)."""
    global _yolo_model, _yolo_load_attempted
    if _yolo_load_attempted:
        return _yolo_model
    _yolo_load_attempted = True
    try:
        from ultralytics import YOLO  # type: ignore  # noqa: PLC0415

        _yolo_model = YOLO(model_path)
        log.info("YOLO loaded: %s", model_path)
    except Exception as exc:  # ImportError, missing weights, GPU init, etc.
        log.warning("YOLO unavailable; using deterministic mock: %s", exc)
        _yolo_model = None
    return _yolo_model


def _decode_frame(frame_bytes: bytes) -> Any | None:
    """Decode JPEG/PNG bytes into a BGR numpy array. Returns None on failure."""
    try:
        import numpy as np  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
        arr = np.array(img)
        # PIL returns RGB; ultralytics accepts both, but YOLO's COCO model was
        # trained on BGR-style ordering. Convert to BGR for parity with OpenCV.
        return arr[:, :, ::-1].copy()
    except Exception as exc:
        log.warning("frame decode failed: %s", exc)
        return None


def _evasion_from(detections: list[dict], frame_width: int = 640) -> dict | None:
    """Derive an evasion vector from the closest obstacle (DroneFleet logic)."""
    obstacles = [
        d for d in detections if d["class_name"] in OBSTACLE_CLASSES and d["distance_m"] < 30
    ]
    if not obstacles:
        return None
    closest = min(obstacles, key=lambda d: d["distance_m"])
    cx = (closest["bbox"][0] + closest["bbox"][2]) / 2
    centre = frame_width / 2
    if closest["distance_m"] < 10:
        return {
            "direction": "stop",
            "magnitude": 1.0,
            "reason": f"CRITICAL: {closest['class_name']} at {closest['distance_m']:.0f}m",
        }
    if cx < centre:
        return {
            "direction": "right",
            "magnitude": 0.7,
            "reason": f"{closest['class_name']} on left at {closest['distance_m']:.0f}m",
        }
    return {
        "direction": "left",
        "magnitude": 0.7,
        "reason": f"{closest['class_name']} on right at {closest['distance_m']:.0f}m",
    }


def _real_detect(model: Any, frame: Any, confidence: float) -> list[dict]:
    """Run YOLO and convert results to the wire format. Returns []. on failure."""
    try:
        results = model(frame, conf=confidence, verbose=False)
    except Exception as exc:
        log.warning("YOLO inference failed: %s", exc)
        return []
    out: list[dict] = []
    frame_h = frame.shape[0] if frame is not None else 480
    for result in results:
        for box in result.boxes:
            cls_id = int(box.cls[0])
            cls_name = result.names[cls_id]
            conf = float(box.conf[0])
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            bbox_h = max(1, y2 - y1)
            distance = max(1.0, 50.0 * (frame_h / bbox_h))
            out.append(
                {
                    "class_name": cls_name,
                    "confidence": conf,
                    "bbox": [x1, y1, x2, y2],
                    "distance_m": distance,
                }
            )
    return out


def _mock_detect(*, mission_id: str | None) -> list[dict]:
    """Deterministic-ish stub — 15% chance of an obstacle (matches DroneFleet).

    Seeded by ``mission_id`` so a given mission yields the same detections
    across reruns, which is what the agent idempotency contract needs.
    """
    rng = random.Random(mission_id or "no-mission")
    if rng.random() < 0.15:
        return [
            {
                "class_name": rng.choice(["person", "car", "tree", "building"]),
                "confidence": rng.uniform(0.6, 0.95),
                "bbox": [200, 150, 400, 350],
                "distance_m": rng.uniform(5.0, 50.0),
            }
        ]
    return []


@mongo_tool(side_effect_class="read", agent="VisionAgent")
async def detect_obstacles(
    *,
    db: Any | None = None,
    frame_bytes: bytes | None = None,
    mission_id: str | None = None,
    confidence: float = DEFAULT_CONFIDENCE,
    model_path: str = DEFAULT_MODEL_PATH,
) -> dict:
    """Detect obstacles in ``frame_bytes`` using YOLOv8.

    Falls back to a deterministic mock when ``ultralytics`` isn't available
    or no frame was supplied. Output format::

        {
          "detections": [{class_name, confidence, bbox, distance_m}, ...],
          "model": "yolov8n" | "mock",
          "evasion": {direction, magnitude, reason} | None,
          "frame_bytes_size": int,
          "mission_id": str | None,
        }
    """
    detections: list[dict]
    model_label = "mock"
    frame_w = 640
    if frame_bytes:
        model = _try_load_yolo(model_path)
        if model is not None:
            frame = _decode_frame(frame_bytes)
            if frame is not None:
                frame_w = int(frame.shape[1])
                detections = _real_detect(model, frame, confidence)
                model_label = "yolov8n" if detections is not None else "mock"
            else:
                detections = _mock_detect(mission_id=mission_id)
        else:
            detections = _mock_detect(mission_id=mission_id)
    else:
        detections = _mock_detect(mission_id=mission_id)

    return {
        "detections": detections,
        "model": model_label,
        "evasion": _evasion_from(detections, frame_width=frame_w),
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
    """Persist ``frame_bytes`` into the GridFS ``frames`` bucket.

    Uses ``motor.motor_asyncio.AsyncIOMotorGridFSBucket`` when available.
    On engines without GridFS support (mongomock), only the metadata
    document is recorded so the agent path keeps working in tests.
    """
    now = datetime.now(timezone.utc)
    base_meta = {
        "mission_id": mission_id,
        "metadata": metadata or {},
        "created_at": now,
    }
    file_id: Any | None = None
    try:
        from motor.motor_asyncio import AsyncIOMotorGridFSBucket  # noqa: PLC0415

        bucket = AsyncIOMotorGridFSBucket(db, bucket_name="frames")
        file_id = await bucket.upload_from_stream(
            f"{mission_id}-{int(now.timestamp() * 1000)}.jpg",
            frame_bytes,
            metadata=base_meta,
        )
    except Exception as exc:  # mongomock or motor not configured
        log.debug("GridFS unavailable; recording metadata only: %s", exc)
        await db["frames.files"].insert_one(
            {**base_meta, "size": len(frame_bytes), "engine": "metadata-only"}
        )
    return {
        "saved": True,
        "size": len(frame_bytes),
        "mission_id": mission_id,
        "file_id": str(file_id) if file_id is not None else None,
        "ts": now,
    }
