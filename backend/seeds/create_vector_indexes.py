"""Create the two Atlas Vector Search indexes required by the plan.

Per ``prompts/13 §3 Phase 1 — Data Model & Seeds``:

* ``mission_memory.mission_memory_vec`` — KNN on ``embedding`` (Voyage dim)
* ``agent_skills.agent_skills_vec``     — KNN on ``embedding`` (Voyage dim)

Uses the native MongoDB 8 ``createSearchIndexes`` command (no Atlas Admin
API call needed). Idempotent: if the index already exists with the same
definition we leave it alone; if it exists with a different dim we drop
and recreate so ``VOYAGE_DIM`` swaps cleanly.

Run: ``uv run python -m backend.seeds.create_vector_indexes``
"""

from __future__ import annotations

import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import OperationFailure

from backend.dronan.config import get_settings

from ._common import run

log = logging.getLogger(__name__)


def _vec_definition(dim: int, path: str = "embedding") -> dict:
    """KNN vector search index body (cosine)."""
    return {
        "fields": [
            {
                "type": "vector",
                "path": path,
                "numDimensions": dim,
                "similarity": "cosine",
            },
            {"type": "filter", "path": "kind"},
            {"type": "filter", "path": "agent"},
        ]
    }


async def _list_search_indexes(coll) -> list[dict]:
    try:
        cursor = coll.list_search_indexes()  # motor: not awaitable, it's a cursor
        return [idx async for idx in cursor]
    except OperationFailure as exc:  # mongomock, non-Atlas, etc.
        log.warning("list_search_indexes unavailable on %s: %s", coll.name, exc)
        return []


async def _ensure_vector_index(
    db: AsyncIOMotorDatabase,
    *,
    collection: str,
    index_name: str,
    dim: int,
) -> str:
    """Create or update the vector index. Returns its state."""
    coll = db[collection]
    existing = await _list_search_indexes(coll)
    match = next((i for i in existing if i.get("name") == index_name), None)
    wanted = _vec_definition(dim)

    if match:
        current = match.get("latestDefinition") or match.get("definition") or {}
        same = any(
            f.get("path") == "embedding" and f.get("numDimensions") == dim
            for f in (current.get("fields") or [])
        )
        if same:
            print(f"  {collection}.{index_name}: exists (dim={dim}, state={match.get('status')})")
            return match.get("status", "EXISTS")
        print(f"  {collection}.{index_name}: dim mismatch → dropping to recreate")
        await coll.drop_search_index(index_name)

    try:
        await coll.create_search_index(
            model={
                "name": index_name,
                "type": "vectorSearch",  # required — distinguishes from text Atlas Search
                "definition": wanted,
            }
        )
        print(f"  {collection}.{index_name}: CREATED (dim={dim}) — build takes 1–5 min")
        return "CREATING"
    except OperationFailure as exc:
        print(f"  {collection}.{index_name}: FAILED — {exc}")
        return "FAILED"


async def main(db: AsyncIOMotorDatabase) -> dict[str, str]:
    """Ensure both vector indexes exist. Returns {index_name: status}."""
    settings = get_settings()
    dim = int(settings.voyage_dim)

    # Make sure the collections actually exist before asking Atlas to index them.
    existing = set(await db.list_collection_names())
    for name in ("mission_memory", "agent_skills"):
        if name not in existing:
            await db.create_collection(name)

    print(f"creating vector indexes (dim={dim}):")
    results: dict[str, str] = {}
    results["mission_memory_vec"] = await _ensure_vector_index(
        db, collection="mission_memory", index_name="mission_memory_vec", dim=dim
    )
    results["agent_skills_vec"] = await _ensure_vector_index(
        db, collection="agent_skills", index_name="agent_skills_vec", dim=dim
    )
    return results


if __name__ == "__main__":
    asyncio.run(_cli_wrapper := run(main)) if False else run(main)
