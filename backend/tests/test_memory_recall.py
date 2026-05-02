"""AT-7.2 — memory recall precision @ 5 ≥ 0.8 (SM-3).

We seed the ``mission_memory`` collection with a known mix of relevant and
distractor lesson cards, query with a query embedding that clusters near the
relevant cards, and assert that at least 4 of the top 5 hits are relevant.

We exercise :func:`dronan.demo.runner.retrieve_lessons_local` — the
in-Python cosine retrieval used by the simulator + offline rehearsal.
Production retrieval will live in Session A's ``dronan.tools.memory`` and
hit Atlas Vector Search; the contract (top-K by cosine, filtered by
``metadata.deprecated``, ``metadata.tag``, optionally ``metadata.region``)
is the same.
"""

from __future__ import annotations

import math
import random

import pytest

from dronan.demo.runner import _det_embedding, retrieve_lessons_local


def _jitter(base: list[float], sigma: float, seed: str) -> list[float]:
    rng = random.Random(seed)
    return [b + rng.gauss(0.0, sigma) for b in base]


async def _seed(db, *, tag: str, n_relevant: int, n_distractor: int, dim: int = 16):
    relevant_axis = _det_embedding(f"{tag}:rel", dim)
    distractor_axes = [_det_embedding(f"distractor:{i}", dim) for i in range(n_distractor)]

    docs: list[dict] = []
    for i in range(n_relevant):
        docs.append(
            {
                "_id": f"rel-{i}",
                "kind": "corridor_avoidance",
                "summary": f"relevant lesson {i}",
                "embedding": _jitter(relevant_axis, 0.05, f"{tag}:rel:{i}"),
                "metadata": {
                    "tag": tag,
                    "deprecated": False,
                    "region": "thames_estuary",
                },
            }
        )
    for i, axis in enumerate(distractor_axes):
        docs.append(
            {
                "_id": f"dis-{i}",
                "kind": "noise",
                "summary": f"distractor lesson {i}",
                "embedding": _jitter(axis, 0.1, f"distractor:{i}"),
                "metadata": {
                    "tag": tag,
                    "deprecated": False,
                    "region": "thames_estuary",
                },
            }
        )
    if docs:
        await db.mission_memory.insert_many(docs)
    return relevant_axis


@pytest.mark.asyncio
async def test_precision_at_5_is_at_least_zero_point_eight(mongomock_db):
    """SM-3: precision @ 5 ≥ 0.8 (i.e. ≥4 of top 5 relevant)."""
    tag = "test:p5:gold"
    relevant_axis = await _seed(mongomock_db, tag=tag, n_relevant=8, n_distractor=20)

    # Query right on the relevant axis.
    hits = await retrieve_lessons_local(mongomock_db, query_embedding=relevant_axis, k=5, tag=tag)
    assert len(hits) == 5, hits

    n_relevant = sum(1 for h in hits if h["_id"].startswith("rel-"))
    precision = n_relevant / 5
    assert precision >= 0.8, (
        f"precision@5 = {precision:.2f}; want ≥0.80; hits={[h['_id'] for h in hits]}"
    )


@pytest.mark.asyncio
async def test_deprecated_lessons_are_filtered(mongomock_db):
    """Deprecated lessons must never appear, even if cosine-similar."""
    tag = "test:deprecated"
    relevant_axis = _det_embedding(f"{tag}:rel")
    await mongomock_db.mission_memory.insert_many(
        [
            {
                "_id": "rel-1",
                "embedding": _jitter(relevant_axis, 0.01, "rel-1"),
                "metadata": {"tag": tag, "deprecated": True, "region": "any"},
            },
            {
                "_id": "rel-2",
                "embedding": _jitter(relevant_axis, 0.01, "rel-2"),
                "metadata": {"tag": tag, "deprecated": False, "region": "any"},
            },
        ]
    )

    hits = await retrieve_lessons_local(mongomock_db, query_embedding=relevant_axis, k=5, tag=tag)
    ids = [h["_id"] for h in hits]
    assert "rel-2" in ids
    assert "rel-1" not in ids, "deprecated lessons must be filtered out"


@pytest.mark.asyncio
async def test_tag_filter_scopes_retrieval(mongomock_db):
    """Two scenarios with overlapping embeddings should not contaminate each
    other when the caller passes ``tag=...``."""
    axis = _det_embedding("shared")
    await mongomock_db.mission_memory.insert_many(
        [
            {
                "_id": "a-1",
                "embedding": _jitter(axis, 0.01, "a-1"),
                "metadata": {"tag": "scenario:A", "deprecated": False},
            },
            {
                "_id": "b-1",
                "embedding": _jitter(axis, 0.01, "b-1"),
                "metadata": {"tag": "scenario:B", "deprecated": False},
            },
        ]
    )

    a_hits = await retrieve_lessons_local(mongomock_db, query_embedding=axis, k=5, tag="scenario:A")
    b_hits = await retrieve_lessons_local(mongomock_db, query_embedding=axis, k=5, tag="scenario:B")
    assert [h["_id"] for h in a_hits] == ["a-1"]
    assert [h["_id"] for h in b_hits] == ["b-1"]


@pytest.mark.asyncio
async def test_empty_db_returns_empty_list(mongomock_db):
    hits = await retrieve_lessons_local(
        mongomock_db, query_embedding=[1.0] * 16, k=5, tag="anything"
    )
    assert hits == []


@pytest.mark.asyncio
async def test_zero_norm_embedding_does_not_crash(mongomock_db):
    """Defensive: a corrupt zero-vector embedding should not raise."""
    axis = _det_embedding("ok")
    await mongomock_db.mission_memory.insert_many(
        [
            {
                "_id": "ok-1",
                "embedding": _jitter(axis, 0.01, "ok-1"),
                "metadata": {"tag": "t", "deprecated": False},
            },
            {
                "_id": "zero-1",
                "embedding": [0.0] * len(axis),
                "metadata": {"tag": "t", "deprecated": False},
            },
        ]
    )

    hits = await retrieve_lessons_local(mongomock_db, query_embedding=axis, k=5, tag="t")
    ids = [h["_id"] for h in hits]
    assert "ok-1" in ids
    # zero vector has cosine 0; appears with rank below ok-1
    if "zero-1" in ids:
        assert ids.index("ok-1") < ids.index("zero-1")


@pytest.mark.asyncio
async def test_cosine_implementation_matches_math(mongomock_db):
    """Sanity-check the in-test cosine matches manual numpy-style calc."""
    a = [1.0, 0.0, 0.0]
    b = [0.5, math.sqrt(0.75), 0.0]
    # cos = a·b / (|a||b|) = 0.5 / 1
    expected = 0.5
    await mongomock_db.mission_memory.insert_one(
        {"_id": "x", "embedding": b, "metadata": {"tag": "z", "deprecated": False}}
    )
    hits = await retrieve_lessons_local(mongomock_db, query_embedding=a, k=1, tag="z")
    assert hits[0]["_id"] == "x"
    # The function doesn't expose scores; we just check it returned the doc.
    # The cosine value is verified separately via _cosine().
    from dronan.demo.runner import _cosine  # noqa: PLC0415

    assert abs(_cosine(a, b) - expected) < 1e-9
