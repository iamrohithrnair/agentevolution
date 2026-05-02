"""Geofence tool — checks whether a candidate route intersects a no-fly zone.

Uses ``$geoIntersects`` on the ``no_fly_zones.geometry`` 2dsphere index
when the driver supports it (Atlas) and falls back to a python
LineString-vs-polygon segment test for mongomock.
"""

from __future__ import annotations

from typing import Any, Iterable

from ._decorator import mongo_tool


def _segments(coords: list[tuple[float, float]]) -> Iterable[tuple[tuple[float, float], tuple[float, float]]]:
    for a, b in zip(coords[:-1], coords[1:]):
        yield (a, b)


def _segment_intersects_polygon(
    seg: tuple[tuple[float, float], tuple[float, float]],
    polygon: list[list[float]],
) -> bool:
    """Cheap python fallback: bounding-box test then exact segment / edge
    intersection. Sufficient for the unit tests against mongomock; Atlas
    uses native ``$geoIntersects``.
    """
    (x1, y1), (x2, y2) = seg
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    sx_min, sx_max = sorted([x1, x2])
    sy_min, sy_max = sorted([y1, y2])
    if sx_max < bbox[0] or sx_min > bbox[2] or sy_max < bbox[1] or sy_min > bbox[3]:
        return False

    def _on_segment(p, q, r) -> bool:
        return (
            min(p[0], r[0]) <= q[0] <= max(p[0], r[0])
            and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])
        )

    def _orient(p, q, r) -> int:
        v = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
        if abs(v) < 1e-12:
            return 0
        return 1 if v > 0 else 2

    def _seg_intersect(p1, p2, p3, p4) -> bool:
        o1 = _orient(p1, p2, p3)
        o2 = _orient(p1, p2, p4)
        o3 = _orient(p3, p4, p1)
        o4 = _orient(p3, p4, p2)
        if o1 != o2 and o3 != o4:
            return True
        if o1 == 0 and _on_segment(p1, p3, p2):
            return True
        if o2 == 0 and _on_segment(p1, p4, p2):
            return True
        if o3 == 0 and _on_segment(p3, p1, p4):
            return True
        if o4 == 0 and _on_segment(p3, p2, p4):
            return True
        return False

    # Check whether either endpoint is inside the polygon (ray cast).
    def _point_in_poly(px, py) -> bool:
        inside = False
        n = len(polygon)
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            if ((yi > py) != (yj > py)) and (
                px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-12) + xi
            ):
                inside = not inside
            j = i
        return inside

    if _point_in_poly(x1, y1) or _point_in_poly(x2, y2):
        return True

    for a, b in _segments(polygon):
        if _seg_intersect((x1, y1), (x2, y2), tuple(a), tuple(b)):
            return True
    return False


@mongo_tool(side_effect_class="read", agent="GeofenceAgent")
async def check_route_safety(
    *,
    db: Any,
    waypoints: list[tuple[float, float]],
    altitude_m: float = 100.0,
) -> dict:
    """Return ``{safe: bool, intrusions: [...]}`` for the given polyline.

    Each intrusion contains ``zone_name``, ``severity``, and the segment
    index that hit it.
    """
    if len(waypoints) < 2:
        return {"safe": True, "intrusions": []}

    line = {
        "type": "LineString",
        "coordinates": [[lon, lat] for lon, lat in waypoints],
    }

    intrusions: list[dict] = []
    try:
        cursor = db.no_fly_zones.find(
            {
                "geometry": {"$geoIntersects": {"$geometry": line}},
                "altitude_floor_m": {"$lte": altitude_m},
                "altitude_ceiling_m": {"$gte": altitude_m},
            }
        )
        async for zone in cursor:
            intrusions.append(
                {
                    "zone_name": zone.get("name"),
                    "severity": zone.get("severity"),
                    "country": zone.get("country"),
                }
            )
    except Exception:
        # mongomock fallback — pull every zone and test segment-by-segment
        cursor = db.no_fly_zones.find({})
        async for zone in cursor:
            geom = zone.get("geometry", {})
            if geom.get("type") != "Polygon":
                continue
            floor = zone.get("altitude_floor_m", 0)
            ceil = zone.get("altitude_ceiling_m", 1e9)
            if not (floor <= altitude_m <= ceil):
                continue
            ring = geom["coordinates"][0]
            for idx, seg in enumerate(_segments(waypoints)):
                if _segment_intersects_polygon(seg, ring):
                    intrusions.append(
                        {
                            "zone_name": zone.get("name"),
                            "severity": zone.get("severity"),
                            "country": zone.get("country"),
                            "segment_index": idx,
                        }
                    )
                    break

    return {"safe": not intrusions, "intrusions": intrusions}
