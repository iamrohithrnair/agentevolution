"""Embedding helpers (Voyage AI + offline deterministic fallback).

Public surface:
    - ``embed(text, *, dim=...)`` — single-string embedding
    - ``embed_batch(texts, *, dim=...)`` — batched embeddings
    - ``cache_get(text, *, dim, model)`` / ``cache_put(...)`` — embedding_cache I/O
"""

from __future__ import annotations

from .voyage import (
    cache_get,
    cache_put,
    deterministic_embedding,
    embed,
    embed_batch,
)

__all__ = [
    "cache_get",
    "cache_put",
    "deterministic_embedding",
    "embed",
    "embed_batch",
]
