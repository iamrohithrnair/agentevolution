"""``/memory`` — semantic search over mission_memory + write reflection."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from ...tools.memory import vector_search
from ...memory import write_reflection as write_reflection_helper
from ..deps import get_db
from ._helpers import serialise

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    k: int = 5


class ReflectionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_id: str
    text: str
    tags: list[str] = []


def _to_memory_hit(doc: dict) -> dict:
    """Shape a mission_memory document into the ``MemoryHit`` contract the
    frontend expects: ``{id, kind, text, score, metadata, created_at}``.

    Strips heavy fields (``embedding``) and coerces ``created_at`` to epoch
    milliseconds.
    """
    created = doc.get("created_at")
    if hasattr(created, "timestamp"):
        created_ms = int(created.timestamp() * 1000)
    elif isinstance(created, (int, float)):
        created_ms = int(created)
    else:
        created_ms = 0
    metadata = {
        k: v
        for k, v in doc.items()
        if k
        not in {
            "_id",
            "kind",
            "text",
            "title",
            "embedding",
            "embedding_model",
            "created_at",
            "score",
        }
    }
    # Prefer _id, then a synthetic stable id from source_collection + source_id
    # (for vector_search hits that ship without the raw _id), then a hash of
    # the text as a last resort. Never empty.
    raw_id = str(doc.get("_id") or doc.get("id") or "")
    if not raw_id:
        src_col = doc.get("source_collection") or "mem"
        src_id = doc.get("source_id") or ""
        if src_id:
            raw_id = f"{src_col}:{src_id}"
        else:
            import hashlib as _h  # noqa: PLC0415

            raw_id = "mem:" + _h.sha1(
                (doc.get("text") or doc.get("title") or "").encode("utf-8")
            ).hexdigest()[:10]
    return {
        "id": raw_id,
        "kind": doc.get("kind", "reflection"),
        "text": doc.get("text") or doc.get("title") or "",
        "score": float(doc.get("score", 0.0)),
        "metadata": serialise(metadata),
        "created_at": created_ms,
    }


@router.get("/reflections")
async def list_reflections(
    db: Any = Depends(get_db),
    limit: int = 50,
) -> list[dict]:
    """Return the most recent ``kind:"reflection"`` cards from mission_memory."""
    cursor = (
        db.mission_memory.find(
            {"kind": "reflection"},
            projection={"embedding": 0, "embedding_model": 0},
        )
        .sort("created_at", -1)
        .limit(max(1, min(limit, 200)))
    )
    return [_to_memory_hit(doc) async for doc in cursor]


@router.post("/search")
async def search_memory(req: MemoryQuery, db: Any = Depends(get_db)) -> dict:
    cards = await vector_search(
        db=db,
        query=req.query,
        collection="mission_memory",
        k=req.k,
        idempotency_key=f"mem-search:{req.query[:32]}",
    )
    return {"hits": [_to_memory_hit(c) for c in cards]}


@router.post("/reflect", status_code=201)
async def write_reflection_route(req: ReflectionWrite, db: Any = Depends(get_db)) -> dict:
    res = await write_reflection_helper(
        db,
        mission_id=req.mission_id,
        text=req.text,
        tags=req.tags,
    )
    return serialise(res)
