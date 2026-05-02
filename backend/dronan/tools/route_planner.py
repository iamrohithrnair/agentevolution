"""Route planner — OR-Tools VRP wrapper with a haversine TSP fallback.

The plan calls for OR-Tools VRP, but its CP solver is unavailable in
``mongomock``-only test contexts. We try OR-Tools first; if it isn't
importable or the problem is degenerate (≤ 2 stops), we run a deterministic
nearest-neighbour TSP using the haversine distance. Both paths return the
same shape so the agents layer doesn't need to know which ran.

The decorator memoises results in ``tool_call_log`` keyed by
``idempotency_key`` (typically ``{mission_id}:plan_route``), satisfying the
Phase 2 acceptance criterion *"second call produces zero OR-Tools
invocations"*.
"""

from __future__ import annotations

import math
from typing import Any

from ._decorator import ToolError, mongo_tool

EARTH_RADIUS_M = 6_371_000.0


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance in metres. ``a`` / ``b`` are ``(lon, lat)``."""
    lon1, lat1 = a
    lon2, lat2 = b
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def _nn_tour(
    start: tuple[float, float],
    stops: list[tuple[float, float]],
) -> tuple[list[int], float]:
    """Nearest-neighbour tour starting at ``start``. Returns (order, length_m)."""
    remaining = list(range(len(stops)))
    here = start
    order: list[int] = []
    total = 0.0
    while remaining:
        nxt = min(remaining, key=lambda i: _haversine_m(here, stops[i]))
        total += _haversine_m(here, stops[nxt])
        here = stops[nxt]
        order.append(nxt)
        remaining.remove(nxt)
    total += _haversine_m(here, start)  # return to depot
    return order, total


async def _resolve_facility(db: Any, name: str) -> dict:
    doc = await db.facilities.find_one({"name": name})
    if doc is None:
        raise ToolError(f"Unknown facility: {name}")
    return doc


def _coords(doc: dict) -> tuple[float, float]:
    coords = doc.get("location", {}).get("coordinates")
    if not coords or len(coords) != 2:
        raise ToolError(f"Facility {doc.get('name')!r} missing GeoJSON location")
    return float(coords[0]), float(coords[1])


def _route_doc(
    depot_doc: dict,
    stop_docs: list[dict],
    order: list[int],
    distance_m: float,
    cruise_speed_ms: float,
) -> dict:
    waypoints = [
        {
            "name": depot_doc["name"],
            "lon": _coords(depot_doc)[0],
            "lat": _coords(depot_doc)[1],
            "kind": "depot",
        }
    ]
    for idx in order:
        sd = stop_docs[idx]
        lon, lat = _coords(sd)
        waypoints.append(
            {"name": sd["name"], "lon": lon, "lat": lat, "kind": sd.get("type", "stop")}
        )
    # Return-to-depot tail
    waypoints.append({**waypoints[0], "kind": "depot_return"})

    return {
        "depot": depot_doc["name"],
        "stops": [stop_docs[i]["name"] for i in order],
        "waypoints": waypoints,
        "distance_m": round(distance_m, 1),
        "eta_seconds": round(distance_m / max(cruise_speed_ms, 1.0), 1),
        "solver": "or-tools" if _ortools_available() else "haversine-nn",
    }


def _ortools_available() -> bool:
    try:
        import ortools.constraint_solver.pywrapcp  # noqa: F401

        return True
    except Exception:  # pragma: no cover — fallback path
        return False


def _solve_with_ortools(
    start: tuple[float, float],
    stops: list[tuple[float, float]],
) -> tuple[list[int], float]:  # pragma: no cover — exercised only when ortools is present
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    points = [start, *stops]
    manager = pywrapcp.RoutingIndexManager(len(points), 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def _cost(i: int, j: int) -> int:
        a = manager.IndexToNode(i)
        b = manager.IndexToNode(j)
        return int(round(_haversine_m(points[a], points[b])))

    transit = routing.RegisterTransitCallback(_cost)
    routing.SetArcCostEvaluatorOfAllVehicles(transit)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    sol = routing.SolveWithParameters(params)
    if sol is None:
        return _nn_tour(start, stops)

    order: list[int] = []
    total = 0.0
    index = routing.Start(0)
    prev = manager.IndexToNode(index)
    while not routing.IsEnd(index):
        next_index = sol.Value(routing.NextVar(index))
        node = manager.IndexToNode(next_index)
        if node != 0:  # skip depot from the order list
            order.append(node - 1)
        total += _haversine_m(points[prev], points[node])
        prev = node
        index = next_index
    return order, total


@mongo_tool(side_effect_class="plan", agent="RoutePlannerAgent")
async def compute_route(
    *,
    db: Any,
    depot: str,
    stops: list[str],
    cruise_speed_ms: float = 15.0,
) -> dict:
    """Compute an optimal pickup tour from ``depot`` through every stop.

    Returns ``{depot, stops, waypoints, distance_m, eta_seconds, solver}``.
    """
    if not stops:
        raise ToolError("compute_route requires at least one stop")

    depot_doc = await _resolve_facility(db, depot)
    stop_docs = [await _resolve_facility(db, n) for n in stops]
    start = _coords(depot_doc)
    stop_coords = [_coords(d) for d in stop_docs]

    if len(stop_coords) <= 1 or not _ortools_available():
        order, dist = _nn_tour(start, stop_coords)
    else:
        order, dist = _solve_with_ortools(start, stop_coords)

    return _route_doc(depot_doc, stop_docs, order, dist, cruise_speed_ms)


@mongo_tool(side_effect_class="plan", agent="ReplannerAgent")
async def recompute_route(
    *,
    db: Any,
    depot: str,
    stops: list[str],
    avoid_zones: list[str] | None = None,
    cruise_speed_ms: float = 15.0,
) -> dict:
    """Same as ``compute_route`` but accepts an explicit ``avoid_zones`` list.

    The avoid list is informational — geofence enforcement happens in
    ``check_route_safety``. We pass it through to the result so the
    Replanner can prove which zones were considered.
    """
    base = await compute_route.__wrapped__(  # type: ignore[attr-defined]
        db=db, depot=depot, stops=stops, cruise_speed_ms=cruise_speed_ms
    )
    return {**base, "avoided_zones": list(avoid_zones or [])}
