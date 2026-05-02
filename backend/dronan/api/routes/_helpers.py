"""Shared serialization helpers for routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from bson import ObjectId
except ImportError:  # pragma: no cover — bson always available via pymongo
    ObjectId = None  # type: ignore[assignment]


def serialise(doc: Any) -> Any:
    """JSON-safe shallow copy.

    Stringifies datetimes / ObjectIds, recurses into dicts and lists, and
    leaves primitive types untouched.
    """
    if isinstance(doc, dict):
        return {k: serialise(v) for k, v in doc.items()}
    if isinstance(doc, list):
        return [serialise(v) for v in doc]
    if isinstance(doc, tuple):
        return [serialise(v) for v in doc]
    if isinstance(doc, datetime):
        return doc.isoformat()
    if ObjectId is not None and isinstance(doc, ObjectId):
        return str(doc)
    return doc


# ─────────────────────────────────────────────────────────────────────────────
#  Frontend-shape mappers — GeoJSON → LngLat tuple, _id → id, dt → epoch ms.
# ─────────────────────────────────────────────────────────────────────────────


def _to_lnglat(loc: Any) -> list[float] | None:
    """GeoJSON ``{type: "Point", coordinates: [lon, lat]}`` → ``[lon, lat]``."""
    if not isinstance(loc, dict):
        return None
    coords = loc.get("coordinates")
    if isinstance(coords, list) and len(coords) >= 2:
        return [float(coords[0]), float(coords[1])]
    return None


def _to_epoch_ms(value: Any) -> int | None:
    if hasattr(value, "timestamp"):
        return int(value.timestamp() * 1000)
    if isinstance(value, str):
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def to_facility(doc: dict) -> dict:
    """Shape a ``facilities`` doc into the frontend ``Facility`` contract.

    Keeps the raw doc accessible under ``raw`` so the mapped shape plus the
    legacy fields (``location``, ``airsim_xy``, ``capabilities``, …) coexist
    for backwards-compatible consumers.
    """
    position = _to_lnglat(doc.get("location")) or _to_lnglat(doc.get("position"))
    shaped = {
        "id": str(doc.get("_id") or doc.get("name") or ""),
        "name": doc.get("name") or str(doc.get("_id") or ""),
        "type": doc.get("type") or "hospital",
        "region": doc.get("region") or "",
        "address": doc.get("address") or "",
        "capabilities": list(doc.get("capabilities") or []),
        "position": position or [0.0, 0.0],
    }
    # Back-compat — existing tests + REST clients still read these.
    shaped["_id"] = shaped["id"]
    if doc.get("description"):
        shaped["description"] = doc["description"]
    return shaped


def to_drone(doc: dict) -> dict:
    """Shape a ``drones`` doc into the frontend ``Drone`` contract."""
    position = _to_lnglat(doc.get("position")) or [0.0, 0.0]
    shaped = {
        "id": str(doc.get("_id") or ""),
        "status": doc.get("status") or "idle",
        "battery": float(doc.get("battery", 0.0)),
        "position": position,
        "heading_deg": float(doc.get("heading_deg", 0.0)),
        "current_mission_id": doc.get("current_mission_id"),
        "last_seen": _to_epoch_ms(doc.get("last_seen")) or 0,
        "payload_temp_c": doc.get("payload_temp_c"),
        # Extra fields keep the legacy contract happy.
        "_id": str(doc.get("_id") or ""),
        "model": doc.get("model"),
        "firmware": doc.get("firmware"),
        "capabilities": list(doc.get("capabilities") or []),
        "current_location": doc.get("current_location"),
        "alt_m": doc.get("alt_m"),
        "max_payload_kg": doc.get("max_payload_kg"),
        "cruise_speed_ms": doc.get("cruise_speed_ms"),
    }
    return shaped


def to_mission(doc: dict, *, positions: dict[str, list[float]] | None = None) -> dict:
    """Shape a ``missions`` doc into the frontend ``Mission`` contract.

    Adds ``id``, ``origin_id``, ``eta_seconds``, ``reroutes``, and a
    ``route: Waypoint[]`` derived from ``planned_route``. ``positions`` is
    an optional facility-name → ``[lon, lat]`` map; when supplied, route
    waypoints get real coordinates instead of ``[0, 0]``. Legacy clients
    keep seeing ``_id`` so existing tests pass.
    """
    if not isinstance(doc, dict):
        return doc
    out = dict(doc)
    mid = str(doc.get("_id") or out.get("id") or "")
    out["id"] = mid
    if "_id" not in out:
        out["_id"] = mid
    for key in ("created_at", "updated_at", "started_at", "completed_at"):
        if key in out:
            ms = _to_epoch_ms(out[key])
            if ms is not None:
                out[key] = ms

    # Map fields the frontend Mission type expects.
    out.setdefault("origin_id", doc.get("depot") or "Depot")
    out.setdefault("delivery_ids", doc.get("delivery_ids") or [])
    out.setdefault("reroutes", doc.get("reroutes") or [])
    out.setdefault("drone_id", doc.get("drone_id") or "")

    plan = doc.get("plan") if isinstance(doc.get("plan"), dict) else None
    eta = (plan or {}).get("eta_s") if plan else None
    out.setdefault("eta_seconds", int(eta) if eta else 180)

    waypoints: list[dict] = []
    pos_map = positions or {}
    for node in doc.get("planned_route") or []:
        label = ""
        if isinstance(node, dict):
            label = str(node.get("location") or node.get("label") or "")
        elif isinstance(node, str):
            label = node
        position = pos_map.get(label) or [0.0, 0.0]
        waypoints.append({"position": position, "label": label})
    out["route"] = waypoints
    return out


def to_nofly(doc: dict) -> dict:
    """Shape a ``no_fly_zones`` doc into the frontend ``NoFlyZone`` contract."""
    geom = doc.get("geometry") or doc.get("location") or {}
    if not isinstance(geom, dict):
        geom = {}
    return {
        "id": str(doc.get("_id") or doc.get("name") or ""),
        "_id": str(doc.get("_id") or ""),
        "name": doc.get("name") or "",
        "country": doc.get("country") or "",
        "severity": doc.get("severity") or "medium",
        "geometry": {
            "type": geom.get("type", "Polygon"),
            "coordinates": geom.get("coordinates") or [],
        },
    }
