"""Facilities tools — search and lookup.

``search_facilities`` runs a 2dsphere ``$nearSphere`` query when given
coordinates, otherwise falls back to a regex on ``name``. ``get_facility``
fetches a single doc by name (the canonical ID).
"""

from __future__ import annotations

from typing import Any

from ._decorator import mongo_tool


@mongo_tool(side_effect_class="read", agent="FacilityAgent")
async def search_facilities(
    *,
    db: Any,
    near: tuple[float, float] | None = None,
    max_meters: float = 50_000,
    type_: str | None = None,
    capability: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """Search facilities by proximity, type, and required capability."""
    query: dict[str, Any] = {}
    if type_:
        query["type"] = type_
    if capability:
        query["capabilities"] = capability

    cursor = db.facilities.find(query).limit(limit)
    docs = await cursor.to_list(length=limit)

    if near is not None:
        lon, lat = near
        # Manual flat-earth ranking when the driver lacks $nearSphere
        # (mongomock). Real Atlas uses the 2dsphere index transparently.
        try:
            geo_query = {
                **query,
                "location": {
                    "$nearSphere": {
                        "$geometry": {"type": "Point", "coordinates": [lon, lat]},
                        "$maxDistance": max_meters,
                    }
                },
            }
            cursor = db.facilities.find(geo_query).limit(limit)
            geo_docs = await cursor.to_list(length=limit)
            if geo_docs:
                docs = geo_docs
        except Exception:  # pragma: no cover — mongomock fallback path
            def _dist2(d: dict) -> float:
                coords = d.get("location", {}).get("coordinates", [0, 0])
                return (coords[0] - lon) ** 2 + (coords[1] - lat) ** 2

            docs = sorted(docs, key=_dist2)

    # Strip embeddings / large fields the planner doesn't need
    return [
        {k: v for k, v in d.items() if k not in {"_id", "embedding"}}
        for d in docs
    ]


@mongo_tool(side_effect_class="read", agent="FacilityAgent")
async def get_facility(*, db: Any, name: str) -> dict | None:
    doc = await db.facilities.find_one({"name": name})
    if doc is None:
        return None
    return {k: v for k, v in doc.items() if k not in {"_id", "embedding"}}
