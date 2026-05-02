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


@router.post("/search")
async def search_memory(req: MemoryQuery, db: Any = Depends(get_db)) -> list[dict]:
    cards = await vector_search(
        db=db,
        query=req.query,
        collection="mission_memory",
        k=req.k,
        idempotency_key=f"mem-search:{req.query[:32]}",
    )
    return [serialise(c) for c in cards]


@router.post("/reflect", status_code=201)
async def write_reflection_route(req: ReflectionWrite, db: Any = Depends(get_db)) -> dict:
    res = await write_reflection_helper(
        db,
        mission_id=req.mission_id,
        text=req.text,
        tags=req.tags,
    )
    return serialise(res)
