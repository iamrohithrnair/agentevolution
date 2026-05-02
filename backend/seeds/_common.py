"""Shared helpers for the seed scripts.

* Flat-earth projection from the legacy ``backend/facilities.py``.
* Deterministic embedding stub for offline / no-Voyage runs.
* CLI runner that picks a real Atlas client when one is configured and a
  mongomock client otherwise (so ``make seed`` works on a clean checkout).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import math
import os
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from backend.dronan.config import settings
from backend.dronan.db import make_async_client

_M_PER_DEG_LAT = 111_320
_M_PER_DEG_LON_AT_EQUATOR = 111_320


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def latlon_to_xy(
    lat: float, lon: float, ref_lat: float, ref_lon: float
) -> tuple[float, float]:
    """Original DroneFleet projection — preserved exactly."""
    x = (lat - ref_lat) * _M_PER_DEG_LAT
    y = (lon - ref_lon) * _M_PER_DEG_LON_AT_EQUATOR * math.cos(math.radians(ref_lat))
    return round(x, 1), round(y, 1)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def deterministic_embedding(text: str, dim: int = 1024) -> list[float]:
    """Cheap, deterministic, **offline** embedding.

    Used by seeds when ``VOYAGE_API_KEY`` is unset so the corpus still has
    valid 1024-dim vectors. SHA-256 of the text seeds a numpy RNG; the
    output is L2-normalised. Replaced by the real Voyage embedder in P2.
    """
    import numpy as np

    seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(dim).astype("float64")
    norm = float(np.linalg.norm(vec))
    if norm == 0:
        return [0.0] * dim
    return (vec / norm).tolist()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def _can_reach_real_atlas() -> bool:
    """True only when ``MONGODB_URI`` is set to a non-localhost URI."""
    uri = settings.mongodb_uri
    if not uri:
        return False
    if uri.startswith(("mongodb://localhost", "mongodb://127.0.0.1")):
        return False
    return True


async def _open_client() -> tuple[AsyncIOMotorClient, AsyncIOMotorDatabase]:
    """Return (client, db). Falls back to mongomock when Atlas isn't reachable
    and the env var ``DRONAN_SEED_REQUIRE_ATLAS`` is unset.
    """
    if _can_reach_real_atlas() or os.environ.get("DRONAN_SEED_REQUIRE_ATLAS"):
        client = make_async_client()
        return client, client[settings.mongodb_db]

    # Offline fallback for local development / CI.
    from mongomock_motor import AsyncMongoMockClient

    client = AsyncMongoMockClient()
    return client, client[settings.mongodb_db]


def run(seed_main: Callable[[AsyncIOMotorDatabase], Awaitable[object]]) -> None:
    """Standard CLI entry-point for every ``seed_*.py`` script."""
    parser = argparse.ArgumentParser(description=seed_main.__doc__ or "Seed script")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run against an in-memory mongomock database (no writes to Atlas).",
    )
    args = parser.parse_args()

    async def _go() -> None:
        if args.dry_run:
            from mongomock_motor import AsyncMongoMockClient

            client = AsyncMongoMockClient()
            db = client[settings.mongodb_db]
            await seed_main(db)
            client.close()
            return
        client, db = await _open_client()
        try:
            await seed_main(db)
        finally:
            client.close()

    asyncio.run(_go())


async def bulk_upsert(
    coll, ops: list, *, ordered: bool = False
) -> dict[str, int]:
    """Run a list of pymongo ``UpdateOne(upsert=True)`` ops with a fallback.

    pymongo>=4.15 adds a ``sort`` kwarg to ``UpdateOne`` that the current
    ``mongomock`` does not yet handle. When the bulk path fails with that
    ``TypeError`` we fall back to per-doc ``update_one`` calls so the seed
    scripts work uniformly against real Atlas, replica-set Mongo, and the
    in-memory mongomock used by unit tests.

    Returns ``{"upserted": int, "modified": int}``.
    """
    if not ops:
        return {"upserted": 0, "modified": 0}
    try:
        res = await coll.bulk_write(ops, ordered=ordered)
        return {"upserted": res.upserted_count, "modified": res.modified_count}
    except TypeError as exc:
        if "sort" not in str(exc):
            raise
        # mongomock fallback — apply each UpdateOne sequentially.
        upserted = modified = 0
        for op in ops:
            r = await coll.update_one(op._filter, op._doc, upsert=bool(op._upsert))
            if r.upserted_id is not None:
                upserted += 1
            else:
                modified += r.modified_count
        return {"upserted": upserted, "modified": modified}


__all__ = [
    "bulk_upsert",
    "deterministic_embedding",
    "latlon_to_xy",
    "run",
    "sha256_text",
    "utcnow",
]
