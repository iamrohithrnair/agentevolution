"""Voyage AI embedding wrapper with `embedding_cache` (SHA-256 keyed).

When ``VOYAGE_API_KEY`` is unset, we fall back to a deterministic offline
stub so the test suite stays hermetic. The stub matches the prompt
specification: SHA-256 of the text seeds a numpy RNG, output is L2-normalised.
This is the same algorithm used by the Phase 1 seeds (kept in lock-step so
seeded vectors are stable across re-runs).
"""

from __future__ import annotations

import hashlib
import logging
from typing import Iterable, Sequence

import numpy as np

from backend.dronan.config import get_settings

log = logging.getLogger(__name__)

# Voyage's voyage-3-large supports Matryoshka truncation at 256 / 1024 / 2048
ALLOWED_DIMS = (256, 1024, 2048)


def _hash_key(text: str, *, model: str, dim: int) -> str:
    raw = f"{model}|{dim}|{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def deterministic_embedding(text: str, *, dim: int = 1024) -> list[float]:
    """Offline deterministic embedding (L2-normalised)."""
    seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(dim).astype("float64")
    norm = float(np.linalg.norm(vec))
    if norm == 0:
        return [0.0] * dim
    return (vec / norm).tolist()


# ---------------------------------------------------------------------------
# embedding_cache (SHA-256 keyed)
# ---------------------------------------------------------------------------
async def cache_get(
    db,
    text: str,
    *,
    model: str | None = None,
    dim: int | None = None,
) -> list[float] | None:
    """Return a cached embedding or ``None``."""
    settings = get_settings()
    model = model or settings.voyage_model
    dim = dim or settings.voyage_dim
    key = _hash_key(text, model=model, dim=dim)
    doc = await db.embedding_cache.find_one({"_id": key})
    if doc is None:
        return None
    return doc.get("embedding")


async def cache_put(
    db,
    text: str,
    embedding: Sequence[float],
    *,
    model: str | None = None,
    dim: int | None = None,
) -> None:
    """Idempotent upsert into ``embedding_cache``."""
    settings = get_settings()
    model = model or settings.voyage_model
    dim = dim or settings.voyage_dim
    key = _hash_key(text, model=model, dim=dim)
    await db.embedding_cache.update_one(
        {"_id": key},
        {
            "$setOnInsert": {
                "_id": key,
                "model": model,
                "dim": dim,
                "embedding": list(embedding),
                "text_preview": text[:200],
            }
        },
        upsert=True,
    )


# ---------------------------------------------------------------------------
# Voyage client (lazy)
# ---------------------------------------------------------------------------
_voyage_client = None


def _get_voyage_client():
    """Lazily build a Voyage client. Returns ``None`` when offline."""
    global _voyage_client
    if _voyage_client is not None:
        return _voyage_client
    settings = get_settings()
    if not settings.voyage_api_key:
        return None
    try:
        import voyageai

        _voyage_client = voyageai.Client(api_key=settings.voyage_api_key)
        return _voyage_client
    except Exception as exc:  # pragma: no cover — only fires when voyageai installed weirdly
        log.warning("voyage import failed; falling back to deterministic stub: %s", exc)
        return None


async def embed(
    text: str,
    *,
    db=None,
    dim: int | None = None,
    model: str | None = None,
    input_type: str = "document",
) -> list[float]:
    """Embed a single string. Hits ``embedding_cache`` when ``db`` provided."""
    settings = get_settings()
    model = model or settings.voyage_model
    dim = dim or settings.voyage_dim
    if dim not in ALLOWED_DIMS:
        raise ValueError(
            f"dim={dim} not in Matryoshka set {ALLOWED_DIMS}"
        )

    if db is not None:
        cached = await cache_get(db, text, model=model, dim=dim)
        if cached is not None:
            return cached

    client = _get_voyage_client()
    if client is None:
        vec = deterministic_embedding(text, dim=dim)
    else:  # pragma: no cover — exercised only when VOYAGE_API_KEY present
        # Voyage SDK is sync; run in thread to avoid blocking loop.
        import asyncio

        def _call() -> list[float]:
            r = client.embed(
                [text],
                model=model,
                input_type=input_type,
                output_dimension=dim,
            )
            return r.embeddings[0]

        vec = await asyncio.to_thread(_call)

    if db is not None:
        await cache_put(db, text, vec, model=model, dim=dim)
    return vec


async def embed_batch(
    texts: Iterable[str],
    *,
    db=None,
    dim: int | None = None,
    model: str | None = None,
    input_type: str = "document",
) -> list[list[float]]:
    """Embed many strings (uses cache per-text when ``db`` is provided)."""
    out: list[list[float]] = []
    for t in texts:
        out.append(
            await embed(t, db=db, dim=dim, model=model, input_type=input_type)
        )
    return out
