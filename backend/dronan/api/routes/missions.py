"""``/missions`` — list, fetch, create-from-chat."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ...tools.route_planner import compute_route
from ..deps import get_db
from ._helpers import serialise, to_mission

router = APIRouter(prefix="/missions", tags=["missions"])


class DeliveryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    destination_id: str
    supply: str | dict | None = None
    payload_weight_kg: float | None = None
    priority: str | None = None
    cold_chain_required: bool | None = None


class MissionCreate(BaseModel):
    """Permissive — accepts both the canonical and frontend-style payloads."""

    model_config = ConfigDict(extra="ignore")

    # Canonical fields
    operator_id: str | None = None
    request: str | None = None
    depot: str = "Depot"
    stops: list[str] = Field(default_factory=list)
    # Frontend-style fields
    deliveries: list[DeliveryItem] = Field(default_factory=list)
    origin_id: str | None = None
    notes: str | None = None
    scenario: str | None = None

    @property
    def resolved_operator(self) -> str:
        return self.operator_id or "operator"

    @property
    def resolved_request(self) -> str:
        if self.request:
            return self.request
        if self.notes:
            return self.notes
        if self.deliveries:
            n = len(self.deliveries)
            dests = ", ".join(d.destination_id for d in self.deliveries[:3])
            more = "" if n <= 3 else f" +{n - 3} more"
            return f"Deliver {n} payload(s) to {dests}{more}".strip()
        return "operator dispatch"

    @property
    def resolved_stops(self) -> list[str]:
        if self.stops:
            return list(self.stops)
        return [d.destination_id for d in self.deliveries if d.destination_id]

    @property
    def resolved_depot(self) -> str:
        return self.origin_id or self.depot


async def _facility_positions(db: Any) -> dict[str, list[float]]:
    """name → [lon, lat] map for resolving mission waypoints to coordinates."""
    out: dict[str, list[float]] = {}
    cursor = db.facilities.find(
        {}, projection={"name": 1, "location.coordinates": 1, "_id": 1}
    )
    async for doc in cursor:
        coords = (doc.get("location") or {}).get("coordinates")
        if isinstance(coords, list) and len(coords) >= 2:
            pos = [float(coords[0]), float(coords[1])]
            if doc.get("name"):
                out[str(doc["name"])] = pos
            out[str(doc.get("_id"))] = pos
    return out


@router.get("")
async def list_missions(db: Any = Depends(get_db), limit: int = 25) -> list[dict]:
    positions = await _facility_positions(db)
    cursor = db.missions.find({}).sort("created_at", -1).limit(limit)
    return [to_mission(serialise(d), positions=positions) async for d in cursor]


@router.get("/{mission_id}")
async def get_mission(mission_id: str, db: Any = Depends(get_db)) -> dict:
    doc = await db.missions.find_one({"_id": mission_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"mission {mission_id} not found")
    positions = await _facility_positions(db)
    deliveries = [
        serialise(d) async for d in db.deliveries.find({"mission_id": mission_id}).limit(50)
    ]
    flight_logs = [
        serialise(d)
        async for d in db.flight_logs.find({"mission_id": mission_id})
        .sort("ts", -1)
        .limit(200)
    ]
    mission = to_mission(serialise(doc), positions=positions)
    # Keep mission's top-level fields too so legacy clients reading body["_id"]
    # still work; frontend reads body.mission / body.flight_logs.
    return {**mission, "mission": mission, "deliveries": deliveries, "flight_logs": flight_logs}


async def _next_mission_id(db: Any) -> str:
    """``MED-####`` id matching the missions $jsonSchema pattern."""
    last = await db.missions.find_one(
        {"_id": {"$regex": r"^MED-\d+$"}}, sort=[("_id", -1)]
    )
    n = 0
    if last and isinstance(last.get("_id"), str):
        try:
            n = int(last["_id"].split("-")[1])
        except (IndexError, ValueError):
            n = 0
    return f"MED-{n + 1:04d}"


@router.post("", status_code=201)
async def create_mission(payload: MissionCreate, db: Any = Depends(get_db)) -> dict:
    mission_id = await _next_mission_id(db)
    now = datetime.now(timezone.utc)
    stops = payload.resolved_stops
    depot = payload.resolved_depot

    plan = None
    if stops:
        try:
            plan = await compute_route(
                db=db,
                depot=depot,
                stops=stops,
                idempotency_key=f"plan:{mission_id}",
            )
        except Exception:
            # Don't 500 the mission creation if the planner fails — the
            # Replanner will retry asynchronously once the dispatcher picks
            # the mission up.
            plan = None

    delivery_ids: list[str] = []
    for d in payload.deliveries:
        del_id = f"D-{uuid.uuid4().hex[:8]}"
        await db.deliveries.insert_one(
            {
                "_id": del_id,
                "mission_id": mission_id,
                "destination_id": d.destination_id,
                "supply": d.supply or "unspecified",
                "payload_weight_kg": float(d.payload_weight_kg or 1.0),
                "priority": d.priority or "normal",
                "cold_chain_required": bool(d.cold_chain_required),
                "status": "pending",  # matches the deliveries $jsonSchema enum
                "requested_by": payload.resolved_operator,
                "requested_at": now,
                "created_at": now,
            }
        )
        delivery_ids.append(del_id)

    drone = await db.drones.find_one({"status": "idle"}) or await db.drones.find_one({})
    drone_id = (drone or {}).get("_id") or "Drone1"

    # planned_route satisfies the missions $jsonSchema (array, minItems 2).
    # Each entry is a node descriptor — first is depot, rest are stops.
    planned_route: list[dict] = [{"location": depot, "kind": "depot"}]
    for stop in stops:
        planned_route.append({"location": stop, "kind": "stop"})
    if len(planned_route) < 2:
        planned_route.append({"location": depot, "kind": "return"})

    doc = {
        "_id": mission_id,
        "operator_id": payload.resolved_operator,
        "request": payload.resolved_request,
        "depot": depot,
        "stops": stops,
        "delivery_ids": delivery_ids,
        "drone_id": drone_id,
        "status": "planned",
        "planned_route": planned_route,
        "plan": plan,
        "created_at": now,
        "updated_at": now,
    }
    await db.missions.insert_one(doc)

    # Frontend expects {mission_id, delivery_ids, drone_id, eta_seconds};
    # legacy callers got the full mission doc so we keep both fields.
    eta_s = (plan or {}).get("eta_s") if isinstance(plan, dict) else None
    return serialise(
        {
            "mission_id": mission_id,
            "delivery_ids": delivery_ids,
            "drone_id": drone_id,
            "eta_seconds": int(eta_s or 180),
            "mission": doc,
        }
    )
