"""Compatibility routes for paths the frontend expects but the backend
didn't ship explicitly: ``/no-fly-zones``, ``/skills``,
``/skills/peer-search``, ``/analytics/self-evolution``,
``/simulate-weather``, ``/internal/inject-obstacle``.

Kept in one module so the canonical routers stay focused on their
domain and the shim can be deleted once the frontend and backend
converge on a single surface.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
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


def _to_skill(doc: dict) -> dict:
    """Shape an ``agent_skills`` doc into the frontend ``Skill`` contract."""
    tools = doc.get("tools") or []
    parameters: list[str] = []
    if isinstance(tools, list):
        for t in tools:
            if isinstance(t, str):
                parameters.append(t)
            elif isinstance(t, dict):
                name = t.get("name") or t.get("tool")
                if name:
                    parameters.append(str(name))
    return {
        "skill_id": str(doc.get("_id") or ""),
        "name": doc.get("agent") or doc.get("name") or "",
        "agent": doc.get("agent") or "",
        "summary": doc.get("capability_text") or doc.get("summary") or "",
        "parameters": parameters,
        "win_rate": float(doc.get("reliability_score", 0.0) or 0.0),
        "invocations": int(doc.get("invocations", 0) or 0),
        "score": float(doc.get("score", 0.0) or 0.0),
    }


@router.get("/skills")
async def list_skills(db: Any = Depends(get_db), limit: int = 50) -> list[dict]:
    cursor = db.agent_skills.find().sort("agent", 1).limit(max(1, min(limit, 200)))
    return [_to_skill(serialise(doc)) async for doc in cursor]


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
    return {
        "hits": [
            {**_to_skill(serialise(d)), "score": s} for s, d in scored[: max(1, req.k)]
        ]
    }


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


@router.get("/logs/flight")
async def logs_flight(
    db: Any = Depends(get_db),
    mission_id: str | None = None,
    drone_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """Recent flight log entries, newest first. Optional mission/drone filters."""
    q: dict = {}
    if mission_id:
        q["mission_id"] = mission_id
    if drone_id:
        q["drone_id"] = drone_id
    cursor = db.flight_logs.find(q).sort("ts", -1).limit(max(1, min(limit, 500)))
    return [serialise(doc) async for doc in cursor]


@router.get("/logs/audit")
async def logs_audit(
    db: Any = Depends(get_db),
    mission_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """Append-only audit trail. Optional mission filter."""
    q: dict = {}
    if mission_id:
        q["mission_id"] = mission_id
    cursor = db.audit_trail.find(q).sort("ts", -1).limit(max(1, min(limit, 500)))
    return [serialise(doc) async for doc in cursor]


@router.get("/logs/tool-calls")
async def logs_tool_calls(
    db: Any = Depends(get_db),
    limit: int = 200,
) -> list[dict]:
    """Recent tool invocations from tool_call_log."""
    cursor = (
        db.tool_call_log.find({}).sort("started_at", -1).limit(max(1, min(limit, 500)))
    )
    return [serialise(doc) async for doc in cursor]


@router.get("/agents/stream")
async def agents_stream(
    request: Request,
    kind: str = "all",
    db: Any = Depends(get_db),
) -> StreamingResponse:
    """SSE stream of recent agent activity.

    Tails ``mission_memory`` (filtered by ``kind`` when supplied) and
    ``flight_logs`` and emits one SSE event per insert. Polling-based so
    it works on engines without change streams (mongomock).
    """

    def _sse(event: str, data: Any) -> bytes:
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode("utf-8")

    async def gen():
        yield _sse("ready", {"kind": kind})

        last_mem = datetime.now(timezone.utc)
        last_log = datetime.now(timezone.utc)
        try:
            while True:
                if await request.is_disconnected():
                    break
                # Pull new mission_memory cards
                mem_q: dict = {"created_at": {"$gt": last_mem}}
                if kind and kind != "all":
                    mem_q["kind"] = kind
                async for doc in db.mission_memory.find(mem_q).sort("created_at", 1).limit(20):
                    last_mem = doc.get("created_at") or last_mem
                    yield _sse(
                        "memory",
                        {
                            "id": str(doc.get("_id")),
                            "kind": doc.get("kind"),
                            "title": doc.get("title"),
                            "text": doc.get("text"),
                        },
                    )
                # Pull new flight_logs
                log_q: dict = {"ts": {"$gt": last_log}}
                async for doc in db.flight_logs.find(log_q).sort("ts", 1).limit(20):
                    last_log = doc.get("ts") or last_log
                    yield _sse(
                        "log",
                        {
                            "mission_id": doc.get("mission_id"),
                            "drone_id": doc.get("drone_id"),
                            "event": doc.get("event"),
                            "ts": doc.get("ts"),
                        },
                    )
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
