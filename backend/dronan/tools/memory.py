"""Memory tools — vector recall over ``mission_memory`` and ``agent_skills``.

The retrievers prefer Atlas ``$vectorSearch`` and fall back to a
deterministic cosine-similarity scan when the driver doesn't support it
(mongomock). Results carry a ``source`` field so the planner can audit
which collection / pipeline produced them.
"""

from __future__ import annotations

import math
from typing import Any

from backend.dronan.embeddings import embed
from backend.dronan.config import get_settings

from ._decorator import ToolError, mongo_tool

DEFAULT_K = 5
DEFAULT_NUM_CANDIDATES = 100


def _cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n])) or 1.0
    nb = math.sqrt(sum(x * x for x in b[:n])) or 1.0
    return dot / (na * nb)


async def _atlas_vector_search(
    db: Any,
    *,
    coll: str,
    index: str,
    field: str,
    query_vec: list[float],
    k: int,
    filter_query: dict | None,
) -> list[dict] | None:
    """Try Atlas ``$vectorSearch``. Returns ``None`` when unsupported."""
    pipeline: list[dict] = [
        {
            "$vectorSearch": {
                "index": index,
                "path": field,
                "queryVector": query_vec,
                "numCandidates": DEFAULT_NUM_CANDIDATES,
                "limit": k,
            }
        }
    ]
    if filter_query:
        pipeline[0]["$vectorSearch"]["filter"] = filter_query
    pipeline.append({"$set": {"score": {"$meta": "vectorSearchScore"}}})
    try:
        cursor = db[coll].aggregate(pipeline)
        return await cursor.to_list(length=k)
    except Exception:
        return None


async def _python_cosine_topk(
    db: Any,
    *,
    coll: str,
    field: str,
    query_vec: list[float],
    k: int,
    filter_query: dict | None,
) -> list[dict]:
    """Fallback: scan-and-rank in python. O(N) — fine for the seeded corpora."""
    cursor = db[coll].find(filter_query or {})
    docs = await cursor.to_list(length=10_000)
    scored: list[tuple[float, dict]] = []
    for d in docs:
        vec = d.get(field)
        if not isinstance(vec, list) or not vec:
            continue
        scored.append((_cosine(query_vec, vec), d))
    scored.sort(key=lambda t: t[0], reverse=True)
    out: list[dict] = []
    for score, d in scored[:k]:
        out.append({**d, "score": score})
    return out


@mongo_tool(side_effect_class="read", agent="MemoryAgent")
async def vector_search(
    *,
    db: Any,
    query: str,
    collection: str = "mission_memory",
    k: int = DEFAULT_K,
    filter_query: dict | None = None,
    index_name: str | None = None,
    field: str = "embedding",
) -> list[dict]:
    """Embed ``query`` and return top-``k`` similar docs.

    ``collection`` ∈ {"mission_memory", "agent_skills"} (others allowed).
    """
    if not query:
        raise ToolError("vector_search query must be non-empty")

    settings = get_settings()
    query_vec = await embed(query, db=db, dim=settings.voyage_dim)

    index = index_name or (
        "mission_memory_vec"
        if collection == "mission_memory"
        else "agent_skills_vec"
        if collection == "agent_skills"
        else f"{collection}_vec"
    )

    atlas_hits = await _atlas_vector_search(
        db,
        coll=collection,
        index=index,
        field=field,
        query_vec=query_vec,
        k=k,
        filter_query=filter_query,
    )

    docs = atlas_hits if atlas_hits is not None else await _python_cosine_topk(
        db,
        coll=collection,
        field=field,
        query_vec=query_vec,
        k=k,
        filter_query=filter_query,
    )

    # Strip the embedding so the planner doesn't have to look at 1024 floats.
    return [
        {
            **{kk: vv for kk, vv in d.items() if kk not in {"embedding", "_id"}},
            "score": d.get("score"),
            "source": collection,
        }
        for d in docs
    ]


@mongo_tool(side_effect_class="audit", agent="ReflectionAgent")
async def embed_and_store(
    *,
    db: Any,
    text: str,
    kind: str,
    title: str | None = None,
    metadata: dict | None = None,
    source_collection: str | None = None,
    source_id: str | None = None,
) -> dict:
    """Embed ``text`` and upsert a ``mission_memory`` card. Returns the inserted doc."""
    if not text or not kind:
        raise ToolError("embed_and_store requires `text` and `kind`")

    from datetime import datetime, timezone

    settings = get_settings()
    vec = await embed(text, db=db, dim=settings.voyage_dim)

    doc = {
        "kind": kind,
        "title": title or text[:80],
        "text": text,
        "embedding": vec,
        "embedding_model": settings.voyage_model,
        "metadata": metadata or {},
        "source_collection": source_collection,
        "source_id": source_id,
        "created_at": datetime.now(timezone.utc),
        "use_count": 0,
        "score_ema": 0.0,
    }
    filt = {
        "kind": kind,
        "source_collection": source_collection,
        "source_id": source_id,
        "title": doc["title"],
    }
    res = await db.mission_memory.update_one(
        filt,
        {"$set": doc},
        upsert=True,
    )
    # Surface the persisted ``_id`` so callers (notably ``reflection_node``)
    # can reference the card. ``upserted_id`` only exists on insert; on
    # update we have to look it up.
    if res.upserted_id is not None:
        doc_id = res.upserted_id
    else:
        existing = await db.mission_memory.find_one(filt, projection={"_id": 1})
        doc_id = existing.get("_id") if existing else None
    return {
        "inserted": bool(res.upserted_id),
        "id": str(doc_id) if doc_id is not None else None,
        "kind": kind,
        "title": doc["title"],
        "source_collection": source_collection,
        "source_id": source_id,
    }


@mongo_tool(side_effect_class="read", agent="MemoryAgent")
async def summarise_for_planner(
    *,
    db: Any,
    cards: list[dict],
    max_tokens: int = 600,
) -> str:
    """Compose a compact bullet summary from `vector_search` hits.

    No LLM call here — that lives in the agent layer. We just produce a
    deterministic, token-bounded markdown blob the Supervisor can splice
    into a prompt.
    """
    bullets: list[str] = []
    chars_left = max_tokens * 4  # cheap token estimate
    for c in cards:
        title = c.get("title") or c.get("text", "")[:60]
        meta = c.get("metadata", {}) or {}
        tags = meta.get("tags") or []
        score = c.get("score")
        score_repr = f"{score:.3f}" if isinstance(score, (int, float)) else "n/a"
        line = f"- **{title}** [{c.get('source')}, score={score_repr}]"
        if tags:
            line += f" tags={','.join(tags[:3])}"
        if chars_left - len(line) < 0:
            break
        bullets.append(line)
        chars_left -= len(line)
    return "\n".join(bullets) or "(no relevant memory)"
