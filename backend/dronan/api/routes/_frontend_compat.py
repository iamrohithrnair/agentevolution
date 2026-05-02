"""Compatibility routes for paths the frontend expects but the backend
didn't ship explicitly: ``/no-fly-zones``, ``/skills``,
``/skills/peer-search``, ``/analytics/self-evolution``,
``/simulate-weather``, ``/internal/inject-obstacle``.

Kept in one module so the canonical routers stay focused on their
domain and the shim can be deleted once the frontend and backend
converge on a single surface.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from ..deps import get_db
from ._helpers import serialise, to_nofly

router = APIRouter(tags=["frontend-compat"])


# ─────────────────────────────────────────────────────────────────────────────
#  Aliases
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/no-fly-zones")
async def list_no_fly_zones(db: Any = Depends(get_db), active: bool = True) -> list[dict]:
    q: dict = {}
    if active:
        now = datetime.now(timezone.utc)
        q = {
            "$or": [
                {"active_from": {"$exists": False}},
                {"active_from": {"$lte": now}},
            ],
            "$and": [
                {
                    "$or": [
                        {"active_to": {"$exists": False}},
                        {"active_to": {"$gte": now}},
                    ]
                }
            ],
        }
    cursor = db.no_fly_zones.find(q).limit(200)
    return [to_nofly(serialise(doc)) async for doc in cursor]


# ─────────────────────────────────────────────────────────────────────────────
#  Skills (pulls from agent_skills)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/skills")
async def list_skills(db: Any = Depends(get_db), limit: int = 50) -> list[dict]:
    cursor = db.agent_skills.find().sort("agent", 1).limit(max(1, min(limit, 200)))
    return [serialise(doc) async for doc in cursor]


class PeerSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    k: int = 5


@router.post("/skills/peer-search")
async def peer_search_skills(req: PeerSearchRequest, db: Any = Depends(get_db)) -> dict:
    """Cheap keyword overlap — real vector hit lands once agents register
    embeddings on the agent_skills_vec index at boot."""
    q = req.query.lower()
    cursor = db.agent_skills.find()
    scored: list[tuple[float, dict]] = []
    async for doc in cursor:
        blob = " ".join(
            [
                str(doc.get("agent", "")),
                str(doc.get("description", "")),
                " ".join(doc.get("tags") or []),
            ]
        ).lower()
        score = sum(1 for token in q.split() if token in blob) / max(1, len(q.split()))
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda t: t[0], reverse=True)
    return {"hits": [serialise(d) for _, d in scored[: max(1, req.k)]]}


# ─────────────────────────────────────────────────────────────────────────────
#  Self-evolution analytics
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/analytics/self-evolution")
async def self_evolution_series(db: Any = Depends(get_db)) -> list[dict]:
    """Return the ``experiments`` series so the frontend can plot takes."""
    try:
        cursor = db.experiments.find().sort("take", 1).limit(50)
        docs = [serialise(doc) async for doc in cursor]
        if docs:
            return docs
    except Exception:
        pass
    return []


# ─────────────────────────────────────────────────────────────────────────────
#  Demo affordances
# ─────────────────────────────────────────────────────────────────────────────


class SimulateWeatherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id: str
    severity: str = "medium"


@router.post("/simulate-weather")
async def simulate_weather(req: SimulateWeatherRequest, db: Any = Depends(get_db)) -> dict:
    """Inject a synthetic weather observation so Atlas Triggers + the UI
    react as if a storm has rolled in."""
    cls = {
        "low": "breezy",
        "medium": "marginal",
        "high": "no_go",
        "extreme": "grounded",
    }.get(req.severity, "marginal")
    doc = {
        "location_id": req.location_id,
        "wind_kph": 25.0 if req.severity == "low" else 55.0,
        "precip_mm_h": 0.5 if req.severity == "low" else 10.0,
        "visibility_m": 10000 if req.severity == "low" else 2000,
        "classification": cls,
        "flyable": req.severity == "low",
        "ts": datetime.now(timezone.utc),
        "source": "simulate-weather",
    }
    await db.weather_observations.insert_one(doc)
    return {"ok": True, "classification": cls, "severity": req.severity}


class InjectObstacleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    lat: float
    lon: float


@router.post("/internal/inject-obstacle")
async def inject_obstacle(req: InjectObstacleRequest, db: Any = Depends(get_db)) -> dict:
    """Insert a flight_log entry marking a new obstacle near (lat, lon)."""
    doc = {
        "mission_id": "demo",
        "drone_id": None,
        "event": "obstacle_detected",
        "kind": req.kind,
        "position": {"type": "Point", "coordinates": [req.lon, req.lat]},
        "ts": datetime.now(timezone.utc),
        "source": "demo.inject-obstacle",
    }
    await db.flight_logs.insert_one(doc)
    return {"ok": True, "logged": True}
