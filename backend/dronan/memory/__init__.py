"""Memory module — wraps the vector tools with mission-aware helpers.

Higher-level entry points:
    - ``recall(db, query, *, k, filter_query)`` — vector search over mission_memory
    - ``write_reflection(db, mission_id, text, ...)`` — persist a reflection card
    - ``find_peers(db, capability_text, *, k)`` — peer discovery over agent_skills
"""

from __future__ import annotations

from typing import Any

from backend.dronan.tools.memory import (
    embed_and_store,
    summarise_for_planner,
    vector_search,
)

__all__ = [
    "find_peers",
    "recall",
    "summarise_for_planner",
    "write_reflection",
]


async def recall(
    db: Any,
    query: str,
    *,
    k: int = 5,
    filter_query: dict | None = None,
) -> list[dict]:
    """Recall ``mission_memory`` cards relevant to ``query``."""
    return await vector_search(
        db=db,
        query=query,
        collection="mission_memory",
        k=k,
        filter_query=filter_query,
    )


async def write_reflection(
    db: Any,
    *,
    mission_id: str,
    text: str,
    title: str | None = None,
    metadata: dict | None = None,
    tags: list[str] | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Persist a reflection card linked to ``mission_id``.

    ``tags`` are folded into ``metadata['tags']`` (deduped) so the underlying
    ``embed_and_store`` schema doesn't need to change. ``idempotency_key`` is
    forwarded to the ``@mongo_tool`` wrapper around ``embed_and_store`` so
    repeated reflection writes for the same mission short-circuit.
    """
    md = dict(metadata or {})
    md.setdefault("mission_id", mission_id)
    if tags:
        existing = list(md.get("tags") or [])
        merged = list(dict.fromkeys([*existing, *tags]))
        md["tags"] = merged

    kwargs: dict[str, Any] = {
        "db": db,
        "text": text,
        "kind": "reflection",
        "title": title,
        "metadata": md,
        "source_collection": "missions",
        "source_id": mission_id,
    }
    if idempotency_key is not None:
        kwargs["idempotency_key"] = idempotency_key
    return await embed_and_store(**kwargs)


async def find_peers(
    db: Any,
    capability_text: str,
    *,
    k: int = 3,
) -> list[dict]:
    """Discover peer agents whose capability matches ``capability_text``."""
    return await vector_search(
        db=db,
        query=capability_text,
        collection="agent_skills",
        k=k,
    )
