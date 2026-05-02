# 07 · Backend — FastAPI + Motor + Change Streams + Atlas Triggers

> **Scope.** End-to-end blueprint for the Droran HTTP/WS/SSE backend. Async-first, Mongo-native, agent-aware. Every route, every middleware, every collection touched, every failure mode.
>
> **Cross-references.**
> - Mongo collections defined in [`02-mongodb-data-model.md`](./02-mongodb-data-model.md).
> - Tools (Mongo-backed Python functions exposed as `@tool`) live in [`03-tools-mcp.md`](./03-tools-mcp.md).
> - LangGraph supervisor + agent contracts in [`04-langchain-agents.md`](./04-langchain-agents.md).
> - Voice room mint endpoint shared with [`06-voice-livekit-elevenlabs.md`](./06-voice-livekit-elevenlabs.md).
> - Frontend client (the *only* UI consumer of these routes) in [`08-frontend-nextjs.md`](./08-frontend-nextjs.md).

---

## 0 · Goals & non-negotiables

1. **Async everywhere.** Motor for Mongo, `asyncio.Queue` for fan-out, no blocking I/O in route handlers.
2. **Mongo is the only state store.** No Redis, no in-process caches that would lie under reload. TTL collections replace Redis for rate-limit + idempotency.
3. **Real-time = Change Streams + WebSocket + SSE.** Polling is forbidden.
4. **Tracing is mandatory.** Every request gets a `trace_id`; spans are persisted to `traces`; the admin trace view replays the waterfall.
5. **Idempotent mutations.** Every `POST` that creates real-world side effects accepts `Idempotency-Key`.
6. **Service boundaries are explicit.** Atlas Triggers and other backends authenticate over HMAC, never JWT.

---

## 1 · Folder layout

```
src/dronan/
├── api/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app factory + lifespan
│   ├── deps.py                 # current_user, get_db, get_supervisor, …
│   ├── middleware/
│   │   ├── trace.py            # trace_id + span sink
│   │   ├── idempotency.py      # Idempotency-Key middleware
│   │   ├── ratelimit.py        # token-bucket TTL doc
│   │   └── hmac_service.py     # for /api/internal/*
│   ├── routes/
│   │   ├── chat.py             # POST /api/chat (SSE)
│   │   ├── missions.py         # CRUD + reroute + replay
│   │   ├── drones.py           # GET/recall
│   │   ├── facilities.py       # Atlas Search + geo
│   │   ├── nofly.py
│   │   ├── weather.py
│   │   ├── payload.py
│   │   ├── risk.py
│   │   ├── preflight.py
│   │   ├── delivery.py
│   │   ├── reports.py          # GridFS PDF
│   │   ├── livekit_token.py    # mints LiveKit JWTs
│   │   ├── memory.py           # vector search debug
│   │   ├── skills.py           # peer-search debug
│   │   ├── internal.py         # /api/internal/* (HMAC)
│   │   ├── admin.py            # /api/admin/trace/{trace_id}
│   │   └── health.py           # /api/health
│   ├── ws.py                   # /ws/missions/{id}, /ws/dashboard
│   └── sse.py                  # /api/agents/stream
├── change_streams.py           # one watcher per (collection, filter)
├── outbox.py                   # outbox dispatcher
├── tracing.py                  # open_span ctx manager
├── auth.py                     # JWT verifier, HMAC verifier
├── config.py
├── db.py                       # Motor client + Beanie/odm-free helpers
├── models/                     # Pydantic v2 request/response schemas
└── triggers/
    └── weather_reroute.js      # Atlas Function source
```

---

## 2 · App skeleton — `api/main.py`

```python
# src/dronan/api/main.py
from __future__ import annotations
import asyncio, logging, os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient

from droran.config import settings
from droran.graph import build_supervisor
from droran.change_streams import ChangeStreamHub
from droran.outbox import OutboxDispatcher
from droran.api.middleware.trace import TraceMiddleware
from droran.api.middleware.idempotency import IdempotencyMiddleware
from droran.api.middleware.ratelimit import RateLimitMiddleware
from droran.api.routes import (
    chat, missions, drones, facilities, nofly, weather, payload, risk,
    preflight, delivery, reports, livekit_token, memory, skills, internal,
    admin, health,
)
from droran.api import ws, sse

log = logging.getLogger("droran.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Mongo
    client = AsyncIOMotorClient(settings.MONGODB_URI, uuidRepresentation="standard")
    db = client[settings.MONGODB_DB]
    await db.command("ping")

    # ---- Voyage embeddings client
    from droran.embeddings import VoyageClient
    voyage = VoyageClient(api_key=settings.VOYAGE_API_KEY,
                          model=settings.EMBED_MODEL)

    # ---- LangGraph supervisor (compiled once, MongoDBSaver checkpoints)
    supervisor = build_supervisor(db=db, voyage=voyage)

    # ---- Change-stream hub + outbox dispatcher
    hub = ChangeStreamHub(db=db)
    outbox = OutboxDispatcher(db=db, hub=hub)
    await hub.start()
    await outbox.start()

    # ---- Resume any in-flight missions whose worker died mid-flight
    from droran.scheduler import resume_active_missions
    resume_task = asyncio.create_task(resume_active_missions(db, supervisor),
                                      name="resume_active_missions")

    # ---- expose to dependency injection
    app.state.db = db
    app.state.client = client
    app.state.voyage = voyage
    app.state.supervisor = supervisor
    app.state.hub = hub
    app.state.outbox = outbox

    log.info("droran.api ready")
    try:
        yield
    finally:
        resume_task.cancel()
        await hub.stop()
        await outbox.stop()
        client.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Droran API",
        version="2.0",
        lifespan=lifespan,
        default_response_class=JSONResponse,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TraceMiddleware)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # routers
    for r in (
        chat.router, missions.router, drones.router, facilities.router,
        nofly.router, weather.router, payload.router, risk.router,
        preflight.router, delivery.router, reports.router,
        livekit_token.router, memory.router, skills.router,
        internal.router, admin.router, health.router,
    ):
        app.include_router(r)

    app.include_router(ws.router)
    app.include_router(sse.router)

    return app


app = create_app()
```

### 2.1 `api/deps.py`

```python
# src/dronan/api/deps.py
from fastapi import Depends, Header, HTTPException, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from droran.auth import verify_jwt
from droran.models.user import User


def get_db(request: Request) -> AsyncIOMotorDatabase:
    return request.app.state.db


def get_supervisor(request: Request):
    return request.app.state.supervisor


def get_voyage(request: Request):
    return request.app.state.voyage


async def current_user(
    authorization: str = Header(...),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> User:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer")
    token = authorization.split(" ", 1)[1]
    payload = verify_jwt(token)
    doc = await db.users.find_one({"_id": payload["sub"]})
    if not doc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")
    return User.model_validate(doc)
```

---

## 3 · Route inventory

For each route: **path · method · request schema · response schema · what it does · agents/tools called · collections touched.** Models live in `models/` (Pydantic v2 strict).

### 3.1 `POST /api/chat` — text fallback into Supervisor (SSE streaming)

Schema:

```python
# models/chat.py
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    mission_id: str | None = None
    language: Literal["en","auto"] = "en"

# response: text/event-stream  (events: start, token, tool, done, error)
```

Behaviour: invokes `supervisor.astream_events(...)`, streams each `on_chat_model_stream` token as `event: token`, each tool call as `event: tool`, ends with `event: done`. Persists the user message and final response to `agent_messages`.

Agents: **SupervisorAgent** (and whatever it routes to).
Collections: `agent_messages`, `traces`. Indirectly anything the supervisor touches.

```python
# api/routes/chat.py
import json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from droran.api.deps import current_user, get_db, get_supervisor
from droran.tracing import open_span
from droran.models.chat import ChatRequest

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(req: ChatRequest, request: Request,
               user=Depends(current_user), db=Depends(get_db),
               supervisor=Depends(get_supervisor)):
    trace_id = request.state.trace_id

    async def gen():
        async with open_span(db, "chat.request",
                             meta={"operator_id": str(user.id),
                                   "trace_id": trace_id,
                                   "msg": req.message[:200]}):
            yield 'event: start\ndata: {}\n\n'
            async for ev in supervisor.astream_events({
                "messages": [{"role": "user", "content": req.message}],
                "operator_id": str(user.id),
                "mission_id": req.mission_id,
                "language": req.language,
                "trace_id": trace_id,
            }, version="v2"):
                kind = ev.get("event")
                if kind == "on_chat_model_stream":
                    text = getattr(ev["data"]["chunk"], "content", "") or ""
                    if text:
                        yield f'event: token\ndata: {json.dumps({"text": text})}\n\n'
                elif kind == "on_tool_start":
                    yield f'event: tool\ndata: {json.dumps({"name": ev["name"], "input": ev["data"].get("input")})}\n\n'
                elif kind == "on_tool_end":
                    yield f'event: tool_end\ndata: {json.dumps({"name": ev["name"]})}\n\n'
            yield 'event: done\ndata: {}\n\n'

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })
```

### 3.2 `POST /api/missions` — create batch deliveries → schedule → mission_id

```python
class DeliveryReq(BaseModel):
    destination_id: str
    supply: Literal["o_neg_blood","o_pos_blood","insulin","vaccine","defib","epi","narcan"]
    payload_weight_kg: float
    priority: Literal["high","normal","critical"] = "normal"
    cold_chain_required: bool = False

class CreateMissionReq(BaseModel):
    deliveries: list[DeliveryReq]
    requested_by: str | None = None
    notes: str | None = None

class CreateMissionRes(BaseModel):
    mission_id: str
    delivery_ids: list[str]
    drone_id: str
    eta_seconds: int
```

Calls `InterpreterAgent` (only if `notes` present), `PreflightAgent`, `PlannerAgent`, `DispatchAgent`. Writes `deliveries` (multi), `missions` (1), `flight_logs` (mission_created), `outbox` (broadcast).

### 3.3 `GET /api/missions/{id}` and `/api/missions/{id}/trace`

`GET /api/missions/{id}` returns the mission doc + nested deliveries + last 50 `flight_logs`.

`GET /api/missions/{id}/trace` returns the full `traces` waterfall scoped by `mission_id`, sorted by `started_at`.

```python
@router.get("/missions/{id}")
async def get_mission(id: str, db=Depends(get_db), _=Depends(current_user)):
    m = await db.missions.find_one({"_id": id})
    if not m:
        raise HTTPException(404)
    deliveries = await db.deliveries.find({"mission_id": id}).to_list(None)
    logs = await db.flight_logs.find({"mission_id": id}).sort("ts", -1).limit(50).to_list(None)
    return {"mission": m, "deliveries": deliveries, "flight_logs": logs}
```

### 3.4 `POST /api/missions/{id}/reroute` — manual reroute

```python
class RerouteReq(BaseModel):
    reason: str
    new_waypoints: list[tuple[float, float]] | None = None
    avoid_geometry: dict | None = None  # GeoJSON polygon
```

Calls `ReplannerAgent`. Writes `missions.reroutes[]`, `flight_logs(event="reroute")`, `outbox`.

### 3.5 `POST /api/internal/reroute-trigger` — Atlas Trigger callback (HMAC)

```python
class WeatherTriggerPayload(BaseModel):
    observation_id: str
    location_id: str
    severity: Literal["low","medium","high","extreme"]
    affected_mission_ids: list[str] = []
```

HMAC-verified by `hmac_service` middleware. For each mission, dispatches `ReplannerAgent`. Writes the same docs as §3.4.

### 3.6 `GET /api/drones` and `POST /api/drones/{id}/recall`

```python
class DroneOut(BaseModel):
    id: str
    status: str
    battery: float
    position: tuple[float, float]
    heading_deg: float
    current_mission_id: str | None
    last_seen: float

class RecallRes(BaseModel):
    drone_id: str
    mission_id: str | None
    eta_to_depot_seconds: int
```

Recall calls `ReplannerAgent` with target = home depot. Writes to `missions`, `flight_logs`, `outbox`.

### 3.7 `GET /api/facilities` — Atlas Search + geo

Query params: `q`, `near=lon,lat`, `radius_m`, `type`, `region`, `limit=50`.

```python
@router.get("/facilities")
async def list_facilities(q: str | None = None,
                          near: str | None = None,
                          radius_m: int = 5000,
                          type_: str | None = Query(None, alias="type"),
                          region: str | None = None,
                          limit: int = 50,
                          db=Depends(get_db)):
    pipeline = []
    if q:
        pipeline.append({"$search": {
            "index": "facilities_search",
            "compound": {"should": [
                {"text": {"path": "name",        "query": q, "score": {"boost": {"value": 4}}}},
                {"text": {"path": "address",     "query": q}},
                {"text": {"path": "capabilities","query": q}},
            ]}}})
    elif near:
        lon, lat = (float(x) for x in near.split(","))
        pipeline.append({"$geoNear": {
            "near": {"type": "Point", "coordinates": [lon, lat]},
            "distanceField": "distance_m",
            "maxDistance": radius_m,
            "spherical": True,
        }})
    match = {}
    if type_: match["type"] = type_
    if region: match["region"] = region
    if match: pipeline.append({"$match": match})
    pipeline.append({"$limit": limit})
    return await db.facilities.aggregate(pipeline).to_list(None)
```

### 3.8 `GET /api/no-fly-zones` — geo-filtered

Query params: `bbox=minLon,minLat,maxLon,maxLat`, `country`, `active=true`.

```python
@router.get("/no-fly-zones")
async def nfz(bbox: str | None = None, country: str | None = None,
              active: bool = True, db=Depends(get_db)):
    q: dict = {}
    if active:
        now = datetime.utcnow()
        q["effective_from"] = {"$lte": now}
        q["$or"] = [{"effective_to": None}, {"effective_to": {"$gte": now}}]
    if country: q["country"] = country
    if bbox:
        minLon, minLat, maxLon, maxLat = (float(x) for x in bbox.split(","))
        q["geometry"] = {"$geoIntersects": {"$geometry": {
            "type": "Polygon",
            "coordinates": [[[minLon,minLat],[maxLon,minLat],
                             [maxLon,maxLat],[minLon,maxLat],[minLon,minLat]]]
        }}}
    return await db.no_fly_zones.find(q).limit(500).to_list(None)
```

### 3.9 `GET /api/weather`, `POST /api/simulate-weather`, `POST /api/clear-weather`

`GET /api/weather?location_id=...&since=ts` → last 60 min of `weather_observations`.
`POST /api/simulate-weather` inserts a synthetic observation with `flyable=false` to drive the Atlas Trigger demo. `POST /api/clear-weather` inserts `flyable=true` (clears alerts).

```python
class SimulateWeatherReq(BaseModel):
    location_id: str
    severity: Literal["low","medium","high","extreme"] = "high"
    duration_s: int = 120
```

Touches `weather_observations` (time-series); the Atlas Trigger fires and POSTs back into `/api/internal/reroute-trigger`.

### 3.10 `POST /api/payload-status`

```python
class PayloadStatusReq(BaseModel):
    mission_id: str
    drone_id: str
    delivery_id: str
class PayloadStatusRes(BaseModel):
    temperature_c: float
    integrity: Literal["intact","degraded","compromised"]
    estimated_minutes_remaining: int
```

Calls `PayloadAgent` → reads latest `telemetry`, computes drift via the cold-chain model.

### 3.11 `POST /api/risk-score`

```python
class RiskReq(BaseModel):
    mission_id: str
class RiskRes(BaseModel):
    score: int  # 0..100
    factors: list[dict]   # [{name, weight, value}]
    recommendation: Literal["go","go_with_caution","abort"]
    contingency: str
```

Aggregation pipeline over weather, no-fly proximity, battery margin, payload sensitivity, operator history; returned by the `AnalystAgent`.

### 3.12 `POST /api/preflight`

```python
class PreflightReq(BaseModel):
    mission_id: str
class PreflightRes(BaseModel):
    passed: bool
    checks: list[dict]  # [{name, ok, detail}]
```

`PreflightAgent`; writes `flight_logs(event="preflight")`.

### 3.13 `POST /api/confirm-delivery`

```python
class ConfirmDeliveryReq(BaseModel):
    delivery_id: str
    recipient_name: str
    recipient_role: str
    signature_id: str | None = None  # if voice signature was captured by livekit_worker
    signature_text: str | None = None
class ConfirmDeliveryRes(BaseModel):
    delivery_id: str
    audit_id: str
```

Writes `deliveries.status="delivered"`, `audit_trail(kind="delivery_confirmed")`, `flight_logs(event="delivered")`.

### 3.14 `POST /api/reports/generate` and `GET /api/reports/{id}`

Generate PDF via `AnalystAgent` → write to GridFS bucket `mission_reports`, return `gridfs_id`.

```python
class GenerateReportReq(BaseModel):
    mission_id: str
class GenerateReportRes(BaseModel):
    gridfs_id: str
    bytes: int
    pages: int
```

```python
@router.get("/reports/{id}")
async def get_report(id: str, request: Request, _=Depends(current_user)):
    bucket = AsyncIOMotorGridFSBucket(request.app.state.db, bucket_name="mission_reports")
    grid_out = await bucket.open_download_stream(ObjectId(id))
    return StreamingResponse(grid_out, media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{id}.pdf"'})
```

### 3.15 `POST /api/livekit/token`

Already specified in [`06-voice-livekit-elevenlabs.md §2`](./06-voice-livekit-elevenlabs.md#2--token-mint-endpoint--apilivekittoken). Routed under `routes/livekit_token.py`.

### 3.16 `WS /ws/missions/{id}` — telemetry + flight_logs fanout

Subscribes the WS client to two change-stream filters via the `ChangeStreamHub`:

- `telemetry` filtered by `{mission_id}` — sends every doc.
- `flight_logs` filtered by `{mission_id}` — sends every doc.

Outbound payload:

```json
{ "kind": "telemetry" | "flight_log" | "mission_update" | "ack",
  "doc": { ... } }
```

Inbound: `{"kind":"ack","seq":N}` to acknowledge outbox messages (see §5).

```python
# api/ws.py (excerpt)
@router.websocket("/ws/missions/{mid}")
async def ws_mission(ws: WebSocket, mid: str):
    await ws.accept()
    db = ws.app.state.db
    hub = ws.app.state.hub
    user = await ws_authenticate(ws, db)         # parses ?token= or Sec-WebSocket-Protocol

    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=512)
    sub_t = hub.subscribe("telemetry",   {"mission_id": mid}, queue)
    sub_l = hub.subscribe("flight_logs", {"mission_id": mid}, queue)
    sub_m = hub.subscribe("missions",    {"_id": mid},        queue)

    async def receiver():
        async for raw in ws.iter_text():
            msg = json.loads(raw)
            if msg.get("kind") == "ack":
                await ws.app.state.outbox.ack(msg["id"])

    recv_task = asyncio.create_task(receiver())
    try:
        while True:
            doc = await queue.get()
            await ws.send_json(doc)
    except WebSocketDisconnect:
        pass
    finally:
        recv_task.cancel()
        for s in (sub_t, sub_l, sub_m):
            hub.unsubscribe(s)
```

### 3.17 `WS /ws/dashboard` — drones + active missions roll-up

Watches `drones` (any change) and `missions` filtered by `{status: {$in: ["assigned","in_transit"]}}`. Emits roll-ups on a 1 s tick to keep UI cheap when there are many drones.

### 3.18 `SSE /api/agents/stream` — live `agent_messages` tail

Used by the **Memory Inspector** and **Reflection Feed**. Query params: `kind`, `mission_id`, `operator_id`. Only documents matching the filter are streamed.

```python
# api/sse.py
@router.get("/api/agents/stream")
async def agents_stream(request: Request, kind: str | None = None,
                        mission_id: str | None = None,
                        operator_id: str | None = None,
                        user=Depends(current_user), db=Depends(get_db)):
    match = {}
    if kind: match["fullDocument.kind"] = kind
    if mission_id: match["fullDocument.mission_id"] = mission_id
    if operator_id: match["fullDocument.operator_id"] = operator_id

    async def gen():
        yield 'event: start\ndata: {}\n\n'
        async with db.agent_messages.watch(
            [{"$match": {"operationType": "insert", **match}}],
            full_document="updateLookup",
        ) as stream:
            async for change in stream:
                if await request.is_disconnected():
                    break
                doc = change["fullDocument"]
                doc["_id"] = str(doc["_id"])
                yield f'event: message\ndata: {json.dumps(doc, default=str)}\n\n'

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
```

### 3.19 `POST /api/memory/search` — debug Voyage + vector search

```python
class MemorySearchReq(BaseModel):
    query: str
    k: int = 5
    filters: dict[str, Any] | None = None
class MemorySearchRes(BaseModel):
    hits: list[dict]   # [{_id, kind, text, score, metadata}]
```

Embeds query with Voyage; runs `$vectorSearch` against `mission_memory_vec`. Logs the query+hits to `agent_messages(kind="memory_query")` so the Memory Inspector can show every retrieval.

### 3.20 `POST /api/skills/peer-search` — debug skill registry vector search

```python
class SkillSearchReq(BaseModel):
    query: str
    k: int = 5
class SkillSearchRes(BaseModel):
    hits: list[dict]   # [{skill_id, name, code_summary, score}]
```

`$vectorSearch` against `skills` collection's embedding index.

### 3.21 `GET /api/health`

```python
@router.get("/health")
async def health(request: Request):
    db = request.app.state.db
    out = {"mongo": False, "vector_index": False, "llm": False, "livekit": False, "voyage": False}
    try:
        await db.command("ping"); out["mongo"] = True
    except Exception: pass
    try:
        idx = await db.mission_memory.list_search_indexes().to_list(None)
        out["vector_index"] = any(i["name"] == "mission_memory_vec" for i in idx)
    except Exception: pass
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        await client.models.list()
        out["llm"] = True
    except Exception: pass
    try:
        from livekit import api as lkapi
        lk = lkapi.LiveKitAPI(settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        await lk.room.list_rooms(lkapi.ListRoomsRequest()); out["livekit"] = True; await lk.aclose()
    except Exception: pass
    try:
        out["voyage"] = await request.app.state.voyage.ping()
    except Exception: pass
    code = 200 if all(out.values()) else 503
    return JSONResponse(out, status_code=code)
```

---

## 4 · Change-Stream tail — `change_streams.py`

One process-wide hub. Key idea: open at most one `watch()` per `(collection, hash(filter))`; multiplex consumers via `asyncio.Queue` references. On reconnect, resume from the last known token; on token loss, restart from `now`.

```python
# src/dronan/change_streams.py
from __future__ import annotations
import asyncio, hashlib, json, logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from motor.motor_asyncio import AsyncIOMotorDatabase

log = logging.getLogger("droran.changestreams")


def _filter_key(coll: str, flt: dict[str, Any]) -> str:
    return f"{coll}:{hashlib.md5(json.dumps(flt, sort_keys=True).encode()).hexdigest()}"


@dataclass
class _Watcher:
    coll: str
    flt: dict[str, Any]
    queues: set[asyncio.Queue] = field(default_factory=set)
    task: asyncio.Task | None = None
    resume_token: dict | None = None
    refcount: int = 0


class ChangeStreamHub:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self._watchers: dict[str, _Watcher] = {}
        self._lock = asyncio.Lock()

    async def start(self): pass
    async def stop(self):
        for w in list(self._watchers.values()):
            if w.task: w.task.cancel()

    def subscribe(self, coll: str, flt: dict[str, Any], queue: asyncio.Queue) -> tuple[str, asyncio.Queue]:
        key = _filter_key(coll, flt)
        w = self._watchers.get(key)
        if not w:
            w = _Watcher(coll=coll, flt=flt)
            self._watchers[key] = w
            w.task = asyncio.create_task(self._run(w, key), name=f"cs:{key}")
        w.queues.add(queue)
        w.refcount += 1
        return key, queue

    def unsubscribe(self, sub: tuple[str, asyncio.Queue]):
        key, queue = sub
        w = self._watchers.get(key)
        if not w: return
        w.queues.discard(queue)
        w.refcount -= 1
        if w.refcount <= 0 and w.task:
            w.task.cancel()
            self._watchers.pop(key, None)

    async def _run(self, w: _Watcher, key: str):
        backoff = 1
        pipeline: list[dict] = [{"$match": {"operationType": {"$in": ["insert","update","replace"]}}}]
        # add per-field filters into the pipeline (require fullDocument)
        if w.flt:
            pipeline.append({"$match": {f"fullDocument.{k}": v for k, v in w.flt.items()}})
        while True:
            try:
                async with self.db[w.coll].watch(
                    pipeline, resume_after=w.resume_token,
                    full_document="updateLookup",
                ) as stream:
                    backoff = 1
                    async for change in stream:
                        w.resume_token = change.get("_id")
                        doc = change.get("fullDocument") or {}
                        msg = {"kind": w.coll.rstrip("s"), "doc": doc, "op": change["operationType"]}
                        for q in list(w.queues):
                            try: q.put_nowait(msg)
                            except asyncio.QueueFull:
                                # drop oldest
                                try: q.get_nowait()
                                except asyncio.QueueEmpty: pass
                                q.put_nowait(msg)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("changestream %s lost: %s; backoff %ss", key, e, backoff)
                # if token is dead, restart from now
                if "ResumeOfChangeStream" in str(e) or "BadValue" in str(e):
                    w.resume_token = None
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
```

---

## 5 · Outbox pattern — `outbox.py`

For business events (mission_created, mission_updated, delivery_confirmed) we *do not* rely on the consumer being subscribed at insert time. We write `outbox` rows with `{topic, payload, created_at, delivered_to:[], attempt:0}`. The dispatcher tails `outbox`, fans out to subscribers, and removes the row when **all** known subscribers have acked.

```python
# src/dronan/outbox.py
import asyncio, time
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from droran.change_streams import ChangeStreamHub


class OutboxDispatcher:
    def __init__(self, db: AsyncIOMotorDatabase, hub: ChangeStreamHub):
        self.db = db
        self.hub = hub
        self._task: asyncio.Task | None = None
        self._subs: dict[str, list[asyncio.Queue]] = {}    # topic -> [queue]
        self._pending: dict[str, asyncio.Event] = {}

    def subscribe(self, topic: str, queue: asyncio.Queue):
        self._subs.setdefault(topic, []).append(queue)

    def unsubscribe(self, topic: str, queue: asyncio.Queue):
        self._subs.get(topic, []).remove(queue) if queue in self._subs.get(topic, []) else None

    async def emit(self, topic: str, payload: dict):
        await self.db.outbox.insert_one({
            "_id": ObjectId(),
            "topic": topic, "payload": payload,
            "created_at": time.time(),
            "delivered_to": [],
            "attempt": 0,
        })

    async def ack(self, message_id: str):
        await self.db.outbox.delete_one({"_id": ObjectId(message_id)})

    async def start(self):
        self._task = asyncio.create_task(self._run(), name="outbox.dispatcher")

    async def stop(self):
        if self._task: self._task.cancel()

    async def _run(self):
        # Tail outbox change stream
        async with self.db.outbox.watch(
            [{"$match": {"operationType": "insert"}}], full_document="updateLookup"
        ) as stream:
            async for change in stream:
                doc = change["fullDocument"]
                topic = doc["topic"]
                msg = {"id": str(doc["_id"]), "topic": topic, "payload": doc["payload"]}
                for q in self._subs.get(topic, []):
                    try: q.put_nowait(msg)
                    except asyncio.QueueFull: pass
```

Routes that need to fan out simply call `await app.state.outbox.emit("mission.updated", {...})`. The WS handlers register their queues against the right topic on connect.

---

## 6 · Atlas Trigger function — `triggers/weather_reroute.js`

Configure as a **Database Trigger** on `droran.weather_observations`, on `insert`, full document. The function POSTs to `/api/internal/reroute-trigger` with an HMAC.

```javascript
// triggers/weather_reroute.js
exports = async function(changeEvent) {
  const doc = changeEvent.fullDocument;
  if (!doc || doc.flyable !== false) return { skipped: true };

  // Find affected in-transit missions whose route passes near this location
  const missions = context.services.get("mongodb-atlas").db("droran").collection("missions");
  const facilities = context.services.get("mongodb-atlas").db("droran").collection("facilities");

  const loc = await facilities.findOne({ _id: doc.location_id });
  if (!loc) return { skipped: "no facility" };
  const point = loc.location; // GeoJSON Point

  const affected = await missions.find({
    status: { $in: ["assigned","in_transit"] },
    "route_geometry": { $geoIntersects: { $geometry: {
      type: "Polygon",
      coordinates: [bufferAround(point, 4000)]    // 4 km buffer
    }}}
  }).toArray();

  const ids = affected.map(m => m._id.toString());
  if (ids.length === 0) return { affected: 0 };

  // HMAC sign
  const crypto = require("crypto");
  const secret = context.values.get("INTERNAL_HMAC_SECRET");
  const body = JSON.stringify({
    observation_id: doc._id.toString(),
    location_id: doc.location_id,
    severity: doc.severity || "high",
    affected_mission_ids: ids,
  });
  const sig = crypto.createHmac("sha256", secret).update(body).digest("hex");

  const resp = await context.http.post({
    url: context.values.get("API_BASE_URL") + "/api/internal/reroute-trigger",
    headers: {
      "Content-Type": ["application/json"],
      "X-Internal-Signature": [sig],
      "X-Internal-Timestamp": [Date.now().toString()],
    },
    body, encodeBodyAsJSON: false,
  });

  return { affected: ids.length, status: resp.statusCode };
};

function bufferAround(point, meters) {
  // crude square buffer in degrees (good enough for trigger fan-out)
  const [lon, lat] = point.coordinates;
  const dLat = meters / 111111;
  const dLon = meters / (111111 * Math.cos(lat * Math.PI / 180));
  return [
    [lon - dLon, lat - dLat],
    [lon + dLon, lat - dLat],
    [lon + dLon, lat + dLat],
    [lon - dLon, lat + dLat],
    [lon - dLon, lat - dLat],
  ];
}
```

Backend verification middleware (`middleware/hmac_service.py`):

```python
# api/middleware/hmac_service.py
import hmac, hashlib, time
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from droran.config import settings


class HMACServiceAuth(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/internal/"):
            return await call_next(request)
        sig = request.headers.get("X-Internal-Signature")
        ts = request.headers.get("X-Internal-Timestamp")
        if not sig or not ts:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing signature")
        if abs(time.time() * 1000 - int(ts)) > 60_000:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "stale signature")
        body = await request.body()
        expected = hmac.new(settings.INTERNAL_HMAC_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad signature")
        return await call_next(request)
```

(Wire this in `create_app()` before the JWT middleware.)

---

## 7 · Auth — JWT (frontend) + HMAC (services)

**Frontend → Backend.** NextAuth (see [`08-frontend-nextjs.md §9`](./08-frontend-nextjs.md#9-auth)) issues a JWT signed with `NEXTAUTH_SECRET`. The same secret is shared with FastAPI via `JWT_SECRET`. Verifier:

```python
# auth.py
import jwt
from fastapi import HTTPException, status
from droran.config import settings

ALGS = ["HS256"]


def verify_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=ALGS,
                          options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "expired token")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}")
```

Users live in `users` collection; FastAPI looks up by `sub` (the user's `_id`).

WS auth: token can be sent as the `?token=` query param or as the `Sec-WebSocket-Protocol: Bearer.<jwt>` header (the latter survives stricter proxies).

**Service → Service.** HMAC as shown in §6.

---

## 8 · Idempotency middleware

Clients send `Idempotency-Key: <uuid>` on any state-changing POST. We cache the first response and replay it for 24 h.

```python
# api/middleware/idempotency.py
import json, time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


SAFE = {"GET", "HEAD", "OPTIONS"}


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method in SAFE:
            return await call_next(request)
        key = request.headers.get("Idempotency-Key")
        if not key:
            return await call_next(request)
        db = request.app.state.db
        existing = await db.idempotency.find_one({"_id": key})
        if existing:
            return Response(content=existing["body"],
                            status_code=existing["status"],
                            media_type=existing["media_type"],
                            headers={"X-Idempotent-Replay": "1"})
        response = await call_next(request)
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        await db.idempotency.update_one(
            {"_id": key},
            {"$setOnInsert": {
                "body": body, "status": response.status_code,
                "media_type": response.media_type,
                "expires_at": time.time() + 86400,
            }}, upsert=True,
        )
        return Response(content=body, status_code=response.status_code,
                        media_type=response.media_type, headers=dict(response.headers))
```

`idempotency` collection has `{ _id: key, body, status, media_type, expires_at }` with TTL index `{expires_at:1}` `expireAfterSeconds: 0`.

---

## 9 · Rate limiting — token bucket in Mongo

Per-operator: 60 req/min normal, 600 req/min for `/ws/*` data acks (latter trivially below). Token bucket persisted as `{_id: operator_id, tokens, updated_at, ttl}`. TTL re-bumped on each update.

```python
# api/middleware/ratelimit.py
import time
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse


CAPACITY = 60
REFILL_PER_S = 1.0   # 60/min


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith(("/ws/", "/api/health", "/api/internal/")):
            return await call_next(request)
        ident = request.headers.get("X-Operator-Id") \
                or request.headers.get("Authorization", "anon")[:64]
        db = request.app.state.db
        now = time.time()
        doc = await db.rate_limit.find_one_and_update(
            {"_id": ident},
            [{"$set": {
                "tokens": {"$min": [CAPACITY, {"$add": [
                    {"$ifNull": ["$tokens", CAPACITY]},
                    {"$multiply": [REFILL_PER_S, {"$subtract": [now, {"$ifNull": ["$updated_at", now]}]}]}
                ]}]},
                "updated_at": now,
                "expires_at": now + 600,
            }}],
            upsert=True, return_document=True,
        )
        if doc["tokens"] < 1:
            return JSONResponse({"error": "rate_limited", "retry_after": 1},
                                status_code=429,
                                headers={"Retry-After": "1"})
        await db.rate_limit.update_one({"_id": ident}, {"$inc": {"tokens": -1}})
        return await call_next(request)
```

`rate_limit` has TTL index on `expires_at`.

---

## 10 · Observability — `tracing.py` + `/api/admin/trace/{trace_id}`

Every request gets a `trace_id`. Spans are persisted to `traces`. The admin route returns the full waterfall.

```python
# tracing.py
import contextlib, time, uuid
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


@contextlib.asynccontextmanager
async def open_span(db: AsyncIOMotorDatabase, name: str, *, parent: str | None = None,
                    meta: dict | None = None):
    sid = str(ObjectId())
    started = time.time()
    yield_target = {"id": sid, "started_at": started, "ended_at": None,
                    "name": name, "parent": parent, "meta": meta or {}}
    try:
        yield yield_target
    finally:
        yield_target["ended_at"] = time.time()
        yield_target["duration_ms"] = (yield_target["ended_at"] - started) * 1000
        await db.traces.insert_one(yield_target)
```

```python
# api/middleware/trace.py
import uuid
from starlette.middleware.base import BaseHTTPMiddleware


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        tid = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        request.state.trace_id = tid
        response = await call_next(request)
        response.headers["X-Trace-Id"] = tid
        return response
```

```python
# api/routes/admin.py
@router.get("/admin/trace/{trace_id}")
async def trace_detail(trace_id: str, db=Depends(get_db), _=Depends(current_admin)):
    spans = await db.traces.find({"meta.trace_id": trace_id}).sort("started_at", 1).to_list(None)
    return {"trace_id": trace_id, "span_count": len(spans), "spans": spans}
```

---

## 11 · Resume task — `scheduler.resume_active_missions`

On boot, find missions with `status in ["assigned","in_transit"]` and re-attach the simulator + agents. Avoids ghost flights after a deploy.

```python
# scheduler.py
async def resume_active_missions(db, supervisor):
    cursor = db.missions.find({"status": {"$in": ["assigned","in_transit"]}})
    async for m in cursor:
        # spawn the per-mission live loop (vision/anomaly/decon polling); see
        # 04-langchain-agents.md §7 for the exact StateGraph entry point
        from droran.simulator.runtime import attach_runtime
        asyncio.create_task(attach_runtime(db, supervisor, m), name=f"mission:{m['_id']}")
```

---

## 12 · Launch + production notes

Local:

```bash
uv run uvicorn droran.api.main:app \
    --reload --reload-dir src \
    --host 0.0.0.0 --port 8000 \
    --log-level info
```

Production:

```bash
uv run uvicorn droran.api.main:app \
    --host 0.0.0.0 --port 8000 \
    --workers 1 \                # IMPORTANT: 1 worker; multiple workers mean multiple change-stream cursors
    --proxy-headers --forwarded-allow-ips='*' \
    --timeout-keep-alive 75 \
    --backlog 2048 \
    --log-config logging.yaml
```

Notes:

- Run **a single uvicorn worker per node** because `ChangeStreamHub` and `OutboxDispatcher` keep in-process queues. Scale horizontally by running multiple nodes behind a sticky load balancer (cookie or header sticky on `X-Operator-Id`); each node maintains its own subscriptions.
- Run the LiveKit Worker as a **separate** process (see [`06-voice-livekit-elevenlabs.md §12`](./06-voice-livekit-elevenlabs.md#12--production-deployment-notes)).
- TTL collections (`idempotency`, `rate_limit`, `traces`) need indexes; create in `seeds/create_indexes.py`.
- Atlas Triggers must be deployed via `realm-cli push` or the App Services UI; CI script in `infra/realm/`.
- Health-check liveness: `/api/health` returns 503 if any subsystem is down; readiness: `/api/health?ready=1` only checks Mongo + LLM.

---

## 13 · Smoke tests

```bash
# tests/test_api_smoke.py
uv run pytest tests/test_api_smoke.py -v
```

Covers:

- `POST /api/missions` returns a `mission_id` and creates 1 `missions` + N `deliveries` docs.
- `WS /ws/missions/{id}` receives a `flight_log` within 500 ms of an insert.
- `POST /api/simulate-weather` causes a `flight_logs(event="reroute")` within 2 s (full Trigger loop in dev uses a local HTTPS tunnel).
- `POST /api/chat` streams at least 5 `event: token` chunks for a normal request.
- `GET /api/health` returns 200 once seeds are run.

---

## 14 · Definition of Done

You are done with the backend when:

1. `uv run uvicorn droran.api.main:app` boots cleanly with all subsystems green.
2. All routes in §3 return their documented schemas.
3. The Change Stream + outbox path is end-to-end: a route POST → outbox emit → WS client receives within 200 ms.
4. The Atlas Trigger fires in dev via `mongocli` or a local replay, and `/api/internal/reroute-trigger` causes a reroute on a live mission.
5. `tests/test_api_smoke.py` is green.
6. The frontend (file 08) can drive the entire demo from §8 of `REBUILD_PROMPT.md` against this backend with zero stubs.
