# 02 · MongoDB Data Model — Droran Agentic Rebuild

> **Cross-references**: see [`03-mongodb-vector-rag.md`](./03-mongodb-vector-rag.md) for retrieval over `mission_memory`/`documents`/`document_chunks`, and [`09-seed-and-data.md`](./09-seed-and-data.md) for index-creation and seed scripts.

This file is the **canonical data-model spec**. Implement every collection exactly as specified. All driver code is **Motor** (`motor.motor_asyncio.AsyncIOMotorClient`). Every collection has:

1. A **Pydantic v2** model (validated at the API boundary).
2. A **`$jsonSchema` validator** applied at collection creation time (defence in depth).
3. **Index commands** (PyMongo syntax for B-tree/2dsphere/time-series; raw JSON for Atlas Search and Atlas Vector Search definitions — these are pushed via the Atlas Admin API in [`09-seed-and-data.md`](./09-seed-and-data.md)).
4. A **rationale paragraph**.
5. An **example document**.
6. **Producers / consumers** (which agents read or write).
7. **Change Stream** subscriptions (which background workers / WebSocket fanouts watch the collection).

Database name is `droran`. All timestamps are stored as BSON `Date` (UTC). All IDs are either ObjectId or stable string slugs (`"Drone1"`, `"UK_CAA_120"`); we mark which.

---

## 0 · Conventions

```python
# common.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional
from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]

class MongoModel(BaseModel):
    """Base for every persisted document."""
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str, datetime: lambda d: d.isoformat()},
        extra="forbid",
    )
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

GeoPoint = dict  # {"type":"Point","coordinates":[lon,lat]}
GeoPolygon = dict  # {"type":"Polygon","coordinates":[[[lon,lat], ...]]}
```

```python
# db.py
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URI = os.environ["MONGODB_URI"]
DB_NAME = os.getenv("MONGODB_DB", "droran")

client = AsyncIOMotorClient(MONGODB_URI, uuidRepresentation="standard")
db = client[DB_NAME]
```

A reusable validator-application helper:

```python
# bootstrap.py
async def apply_validator(name: str, validator: dict, *, time_series: dict | None = None) -> None:
    existing = await db.list_collection_names(filter={"name": name})
    if not existing:
        kwargs: dict = {"validator": validator, "validationLevel": "moderate"}
        if time_series:
            kwargs["timeseries"] = time_series
        await db.create_collection(name, **kwargs)
    else:
        await db.command({
            "collMod": name,
            "validator": validator,
            "validationLevel": "moderate",
        })
```

All Change Streams use the resume-token pattern:

```python
# stream.py
async def watch(coll, pipeline=None, *, resume_token=None):
    async with coll.watch(pipeline or [], resume_after=resume_token,
                          full_document="updateLookup") as cur:
        async for change in cur:
            yield change
```

---

## 1 · `facilities`

**Why it exists.** Hospitals, clinics, and depots are the *destinations* and *origins* of every mission. The original repo loaded them from `data/facilities.xlsx` (489 rows) plus 9 hardcoded `LOCATIONS` from `config.py`. We persist them with both **lat/lon** (GeoJSON) and the **AirSim x/y/z** projection (preserving the exact flat-earth math from `backend/facilities.py`) so the simulator and the real planner stay numerically identical. Atlas Search powers fuzzy lookup ("Royal London" → "Royal London Hospital — Major trauma centre"); the 2dsphere index powers `$geoNear` for "what's the nearest dialysis-capable clinic?".

### Pydantic v2

```python
from typing import Literal
from pydantic import Field

class AirsimXY(BaseModel):
    x: float
    y: float
    z: float = -30.0

class Facility(MongoModel):
    name: str
    type: Literal["hospital", "clinic", "depot", "warehouse", "field_camp"]
    region: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    beds: Optional[int] = None
    capabilities: list[str] = Field(default_factory=list)  # ["trauma","cardiac","cold_chain"]
    location: GeoPoint                                      # {"type":"Point","coordinates":[lon,lat]}
    airsim_xy: AirsimXY
    description: Optional[str] = None
    source: Literal["xlsx", "config", "manual", "import"] = "xlsx"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
```

### `$jsonSchema` validator

```python
FACILITIES_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["name", "type", "location", "airsim_xy", "created_at"],
        "properties": {
            "name": {"bsonType": "string", "minLength": 1, "maxLength": 200},
            "type": {"enum": ["hospital", "clinic", "depot", "warehouse", "field_camp"]},
            "region": {"bsonType": ["string", "null"]},
            "address": {"bsonType": ["string", "null"], "maxLength": 500},
            "phone": {"bsonType": ["string", "null"]},
            "email": {"bsonType": ["string", "null"]},
            "website": {"bsonType": ["string", "null"]},
            "beds": {"bsonType": ["int", "null"], "minimum": 0},
            "capabilities": {"bsonType": "array", "items": {"bsonType": "string"}},
            "location": {
                "bsonType": "object",
                "required": ["type", "coordinates"],
                "properties": {
                    "type": {"enum": ["Point"]},
                    "coordinates": {
                        "bsonType": "array",
                        "minItems": 2, "maxItems": 2,
                        "items": {"bsonType": "double"},
                    },
                },
            },
            "airsim_xy": {
                "bsonType": "object",
                "required": ["x", "y", "z"],
                "properties": {
                    "x": {"bsonType": "double"},
                    "y": {"bsonType": "double"},
                    "z": {"bsonType": "double"},
                },
            },
            "source": {"enum": ["xlsx", "config", "manual", "import"]},
            "created_at": {"bsonType": "date"},
            "updated_at": {"bsonType": "date"},
        },
    }
}

await apply_validator("facilities", FACILITIES_VALIDATOR)
```

### Indexes

```python
await db.facilities.create_index([("location", "2dsphere")], name="loc_2dsphere")
await db.facilities.create_index([("name", 1)], name="name_1", unique=True)
await db.facilities.create_index([("region", 1), ("type", 1)], name="region_type_1")
await db.facilities.create_index([("capabilities", 1)], name="capabilities_multikey")
```

Atlas Search index (JSON, applied via Admin API — see [`09-seed-and-data.md`](./09-seed-and-data.md)):

```json
{
  "name": "facilities_search",
  "collectionName": "facilities",
  "database": "droran",
  "mappings": {
    "dynamic": false,
    "fields": {
      "name":         { "type": "string", "analyzer": "lucene.standard" },
      "address":      { "type": "string", "analyzer": "lucene.standard" },
      "region":       { "type": "stringFacet" },
      "type":         { "type": "stringFacet" },
      "capabilities": { "type": "string", "analyzer": "lucene.keyword" },
      "location":     { "type": "geo" }
    }
  },
  "synonyms": [
    { "name": "uk_hospital_synonyms", "source": { "collection": "search_synonyms" }, "analyzer": "lucene.standard" }
  ]
}
```

### Example document

```json
{
  "_id": {"$oid": "65a6b1f23c1d4e0001a3b001"},
  "name": "Royal London",
  "type": "hospital",
  "region": "London",
  "address": "Whitechapel Road, London E1 1FR",
  "phone": "+44 20 7377 7000",
  "beds": 845,
  "capabilities": ["trauma", "cardiac", "cold_chain", "blood_bank"],
  "location": {"type": "Point", "coordinates": [-0.0590, 51.5185]},
  "airsim_xy": {"x": 1235.4, "y": 4778.2, "z": -30.0},
  "description": "Royal London Hospital — Major trauma centre",
  "source": "config",
  "created_at": {"$date": "2026-05-01T10:00:00Z"},
  "updated_at": {"$date": "2026-05-01T10:00:00Z"}
}
```

### Producers / consumers
- **Writers**: `seeds/seed_facilities.py`, `OperatorAdminAPI`.
- **Readers**: `RoutePlannerAgent` (nearest depot, `$geoNear`), `FacilityIntelAgent` (Atlas Search lookup), `DeliverySchedulerAgent`, `FrontendMapAPI`.

### Change Stream
- `BroadcastWorker` watches `facilities` to push live map markers into the React dashboard; pipeline `[{"$match": {"operationType": {"$in": ["insert", "update", "delete"]}}}]`.

---

## 2 · `no_fly_zones`

**Why.** The original `simulation/backend/nofly_data.py` shipped FAA, PDOK, and UK CAA polygons. We promote them to first-class GeoJSON polygons with **time windows** so we can model dynamic TFRs (royal flights, accidents, weather TFRs). `2dsphere` lets the deconfliction agent run a single `$geoIntersects` query on the candidate route at plan time.

### Pydantic v2

```python
class NoFlyZone(MongoModel):
    name: str
    source: Literal["FAA", "PDOK", "UK_CAA", "EASA", "TFR", "INTERNAL"]
    country: str
    severity: Literal["advisory", "restricted", "prohibited"]
    altitude_floor_m: float = 0.0
    altitude_ceiling_m: float = 120.0
    geometry: GeoPolygon
    effective_from: datetime
    effective_to: Optional[datetime] = None       # None == open-ended
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
```

### Validator

```python
NFZ_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["name", "source", "country", "severity", "geometry", "effective_from"],
        "properties": {
            "name": {"bsonType": "string"},
            "source": {"enum": ["FAA", "PDOK", "UK_CAA", "EASA", "TFR", "INTERNAL"]},
            "country": {"bsonType": "string", "minLength": 2, "maxLength": 3},
            "severity": {"enum": ["advisory", "restricted", "prohibited"]},
            "altitude_floor_m": {"bsonType": "double", "minimum": 0},
            "altitude_ceiling_m": {"bsonType": "double", "minimum": 0},
            "geometry": {
                "bsonType": "object",
                "required": ["type", "coordinates"],
                "properties": {"type": {"enum": ["Polygon", "MultiPolygon"]}},
            },
            "effective_from": {"bsonType": "date"},
            "effective_to": {"bsonType": ["date", "null"]},
        },
    }
}
await apply_validator("no_fly_zones", NFZ_VALIDATOR)
```

### Indexes

```python
await db.no_fly_zones.create_index([("geometry", "2dsphere")], name="nfz_geo")
await db.no_fly_zones.create_index([("effective_from", 1), ("effective_to", 1)], name="nfz_window")
await db.no_fly_zones.create_index([("country", 1), ("severity", -1)], name="nfz_country_severity")
await db.no_fly_zones.create_index([("source", 1)], name="nfz_source")
```

### Example document

```json
{
  "name": "Heathrow CTR",
  "source": "UK_CAA",
  "country": "GB",
  "severity": "prohibited",
  "altitude_floor_m": 0.0,
  "altitude_ceiling_m": 762.0,
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[-0.4543, 51.4500],[-0.4543, 51.4900],[-0.4100, 51.4900],
                     [-0.4100, 51.4500],[-0.4543, 51.4500]]]
  },
  "effective_from": {"$date": "2020-01-01T00:00:00Z"},
  "effective_to": null,
  "metadata": {"icao": "EGLL", "class": "D"}
}
```

### Producers / consumers
- **Writers**: `seeds/seed_no_fly_zones.py`, `TFRIngestAgent` (subscribes to NOTAM feed), `Admin API`.
- **Readers**: `GeofenceAgent`, `RoutePlannerAgent`, `DeconflictionAgent`, `WeatherRerouteTrigger` (Atlas Trigger writes into this collection when a storm cell is reported).

### Change Stream
- `RouteInvalidatorWorker` watches inserts/updates whose `effective_from <= now <= effective_to` and re-checks all in-flight `missions` for new intersections; if any mission's `route` enters the new polygon it raises a `ReplanRequest` event into `agent_messages`.

---

## 3 · `weather_observations` (time-series)

**Why.** Per-location wind/precip/visibility readings drive abort and reroute decisions. We model it as a native **time-series collection** so Mongo handles bucketing internally — telemetry-style storage with B-tree on `(metaField, timeField)` for cheap range scans.

### Pydantic v2

```python
class WeatherObservation(BaseModel):
    ts: datetime
    location_id: str                  # facility name OR drone_id at last known cell
    wind_speed_ms: float
    gust_ms: Optional[float] = None
    precipitation_mm_h: float = 0.0
    visibility_m: Optional[float] = None
    temperature_c: Optional[float] = None
    pressure_hpa: Optional[float] = None
    condition: Optional[str] = None   # "clear","rain","snow","fog","storm"
    alerts: list[str] = Field(default_factory=list)
    flyable: bool = True
    source: Literal["openweather", "metoffice", "noaa", "synthetic"] = "openweather"
```

### Collection creation (time-series)

```python
TS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["ts", "location_id", "wind_speed_ms"],
        "properties": {
            "ts": {"bsonType": "date"},
            "location_id": {"bsonType": "string"},
            "wind_speed_ms": {"bsonType": "double", "minimum": 0},
            "flyable": {"bsonType": "bool"},
        },
    }
}

await db.create_collection(
    "weather_observations",
    timeseries={
        "timeField": "ts",
        "metaField": "location_id",
        "granularity": "minutes",
    },
    expireAfterSeconds=60 * 60 * 24 * 30,   # 30-day retention
)
await db.command({"collMod": "weather_observations", "validator": TS_VALIDATOR})
```

### Indexes

```python
# Mongo creates the (metaField, timeField) index automatically; add helpful compounds:
await db.weather_observations.create_index([("location_id", 1), ("ts", -1)], name="loc_ts")
await db.weather_observations.create_index([("flyable", 1), ("ts", -1)], name="flyable_ts")
```

### Example

```json
{
  "ts": {"$date": "2026-05-12T13:42:00Z"},
  "location_id": "Royal London",
  "wind_speed_ms": 9.3,
  "gust_ms": 12.1,
  "precipitation_mm_h": 0.4,
  "visibility_m": 9500,
  "temperature_c": 14.2,
  "condition": "rain",
  "alerts": [],
  "flyable": true,
  "source": "openweather"
}
```

### Producers / consumers
- **Writers**: `WeatherIngestWorker` (polls OpenWeather every 60 s for each unique facility region), `MetOfficeAdapter`.
- **Readers**: `WeatherAgent`, `RoutePlannerAgent`, `AbortPolicyEvaluator`, `FrontendWeatherAPI`, the Atlas Trigger in §**Atlas Trigger code** below.

### Change Stream
- The Atlas Trigger `weather_reroute` (see end of file) watches inserts where `flyable: false` and POSTs `/api/internal/reroute-trigger`.

---

## 4 · `drones`

**Why.** Operational state of every drone. `_id` is the human-readable name (`"Drone1"`) so that mission docs reference it cleanly. `position` is a GeoJSON Point so we can answer "any drone within 500 m of incident X?" in a single query.

### Pydantic v2

```python
DroneStatus = Literal["idle","flying","paused","returning","low_battery","charging","fault","offline"]

class Drone(MongoModel):
    id: str = Field(alias="_id")            # "Drone1"
    model: str = "Generic-X1"
    status: DroneStatus = "idle"
    battery: float = Field(ge=0, le=100)
    max_payload_kg: float = 5.0
    cruise_speed_ms: float = 15.0
    current_location: Optional[str] = "Depot"
    position: GeoPoint
    alt_m: float = 0.0
    heading_deg: float = 0.0
    current_mission_id: Optional[str] = None
    firmware: str = "1.0.0"
    last_seen: datetime = Field(default_factory=utcnow)
    capabilities: list[str] = Field(default_factory=lambda: ["cold_chain","camera"])
```

### Validator

```python
DRONE_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "status", "battery", "position"],
        "properties": {
            "_id": {"bsonType": "string"},
            "status": {"enum": ["idle","flying","paused","returning","low_battery",
                                "charging","fault","offline"]},
            "battery": {"bsonType": "double", "minimum": 0, "maximum": 100},
            "max_payload_kg": {"bsonType": "double", "minimum": 0},
            "position": {
                "bsonType": "object",
                "required": ["type", "coordinates"],
                "properties": {"type": {"enum": ["Point"]}},
            },
        },
    }
}
await apply_validator("drones", DRONE_VALIDATOR)
```

### Indexes

```python
await db.drones.create_index([("position", "2dsphere")], name="drone_pos_2dsphere")
await db.drones.create_index([("status", 1)], name="drone_status")
await db.drones.create_index([("current_mission_id", 1)], name="drone_current_mission")
```

### Example

```json
{
  "_id": "Drone1",
  "model": "Skyhound-5",
  "status": "flying",
  "battery": 67.4,
  "max_payload_kg": 5.0,
  "cruise_speed_ms": 15.0,
  "current_location": null,
  "position": {"type": "Point", "coordinates": [-0.103, 51.514]},
  "alt_m": 30.0,
  "heading_deg": 87.5,
  "current_mission_id": "MED-0421",
  "firmware": "1.2.3",
  "last_seen": {"$date": "2026-05-12T13:42:11Z"},
  "capabilities": ["cold_chain", "camera", "thermal"]
}
```

### Producers / consumers
- **Writers**: `DroneStateWorker` (telemetry → state aggregation), `MissionExecutor`, `ChargerAgent`.
- **Readers**: every agent. The map UI subscribes via the Change Stream below.

### Change Stream
- `DroneBroadcastWorker` watches all updates to `drones` and pushes deltas to all open WebSocket clients.

---

## 5 · `deliveries`

**Why.** The priority queue of medical orders. Recipient PII (`name`, `nhs_number`) is stored under **Queryable Encryption** so admins can equality-search it without ever decrypting at scale. The composite index `(status, priority, requested_at)` is the scheduler's hot read.

### Pydantic v2

```python
Priority = Literal["critical","high","normal","low"]
DeliveryStatus = Literal["pending","assigned","in_transit","delivered","failed","cancelled"]

class EncryptedRecipient(BaseModel):
    name: bytes        # Queryable Encryption ciphertext
    nhs_number: bytes
    contact: bytes

class Delivery(MongoModel):
    destination_id: str                    # facility _id
    supply: str                            # "blood_pack", etc.
    payload_weight_kg: float
    priority: Priority = "normal"
    time_window_minutes: Optional[int] = None
    status: DeliveryStatus = "pending"
    assigned_drone: Optional[str] = None
    mission_id: Optional[str] = None
    requested_by: str                      # user_id
    requested_at: datetime = Field(default_factory=utcnow)
    delivered_at: Optional[datetime] = None
    cold_chain_required: bool = False
    recipient: Optional[EncryptedRecipient] = None
    signature_id: Optional[str] = None     # links into audit_trail
```

### Validator

```python
DELIVERY_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["destination_id", "supply", "payload_weight_kg",
                     "priority", "status", "requested_by", "requested_at"],
        "properties": {
            "priority": {"enum": ["critical", "high", "normal", "low"]},
            "status":   {"enum": ["pending","assigned","in_transit",
                                  "delivered","failed","cancelled"]},
            "payload_weight_kg": {"bsonType": "double", "minimum": 0, "maximum": 25},
            "cold_chain_required": {"bsonType": "bool"},
        },
    }
}
await apply_validator("deliveries", DELIVERY_VALIDATOR)
```

### Indexes

```python
await db.deliveries.create_index(
    [("status", 1), ("priority", -1), ("requested_at", 1)],
    name="queue_hot",
)
await db.deliveries.create_index([("assigned_drone", 1)], name="by_drone")
await db.deliveries.create_index([("mission_id", 1)], name="by_mission")
await db.deliveries.create_index([("destination_id", 1)], name="by_destination")
await db.deliveries.create_index(
    [("requested_at", 1)],
    name="ttl_failed",
    expireAfterSeconds=60 * 60 * 24 * 90,
    partialFilterExpression={"status": "failed"},
)
```

Queryable Encryption schema (configured at client construction time):

```python
encrypted_fields_map = {
  "droran.deliveries": {
    "fields": [
      {"path": "recipient.name",       "bsonType": "string", "queries": [{"queryType": "equality"}]},
      {"path": "recipient.nhs_number", "bsonType": "string", "queries": [{"queryType": "equality"}]},
      {"path": "recipient.contact",    "bsonType": "string"},
    ]
  }
}
```

### Example

```json
{
  "_id": {"$oid": "65a6c0001234abcd56780001"},
  "destination_id": "65a6b1f23c1d4e0001a3b001",
  "supply": "blood_pack",
  "payload_weight_kg": 0.5,
  "priority": "critical",
  "time_window_minutes": 25,
  "status": "in_transit",
  "assigned_drone": "Drone1",
  "mission_id": "MED-0421",
  "requested_by": "op_42",
  "requested_at": {"$date": "2026-05-12T13:30:00Z"},
  "cold_chain_required": true,
  "signature_id": "SIG-00abc"
}
```

### Producers / consumers
- **Writers**: `IntakeAPI`, `VoiceCommandAgent`, `DeliverySchedulerAgent` (status transitions).
- **Readers**: `RoutePlannerAgent`, `SchedulerAgent`, audit pipeline.

### Change Stream
- `SchedulerAgent` watches inserts of `status:"pending"` to bump the planner.
- `AuditAgent` watches transitions to `delivered|failed` to write the chain-of-custody entry.

---

## 6 · `missions`

**Why.** A mission is a *plan-and-trace* document. We store **planned** vs **actual** routes side-by-side, plus the full reroute history, the obstacles the CV agent saw, and the weather events that interrupted us. This is the single object the ReflectionAgent reads to write a memory.

### Pydantic v2

```python
class RouteWaypoint(BaseModel):
    name: str
    lat: float
    lon: float
    alt_m: float = 30.0
    eta: Optional[datetime] = None
    arrived_at: Optional[datetime] = None

class Reroute(BaseModel):
    at: datetime
    reason: str                             # "weather_wind","nfz_dynamic","obstacle_cv","battery"
    from_wp: int                            # index into route
    to_wp: int
    new_segment: list[RouteWaypoint]
    triggered_by_agent: str

class Obstacle(BaseModel):
    at: datetime
    kind: str
    confidence: float
    bbox: Optional[list[float]] = None
    frame_gridfs_id: Optional[str] = None

class WeatherEvent(BaseModel):
    at: datetime
    location_id: str
    wind_speed_ms: float
    note: str

class Mission(MongoModel):
    id: str = Field(alias="_id")           # "MED-0421"
    delivery_ids: list[str] = Field(default_factory=list)
    drone_id: str
    status: Literal["planned","executing","completed","failed","aborted"] = "planned"
    planned_route: list[RouteWaypoint]
    actual_route: list[RouteWaypoint] = Field(default_factory=list)
    reroutes: list[Reroute] = Field(default_factory=list)
    obstacles: list[Obstacle] = Field(default_factory=list)
    weather_events: list[WeatherEvent] = Field(default_factory=list)
    failed_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_distance_m: float = 0.0
    actual_distance_m: float = 0.0
    estimated_battery_pct: float = 0.0
    actual_battery_pct: float = 0.0
    cost_estimate_gbp: float = 0.0
```

### Validator

```python
MISSION_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "drone_id", "status", "planned_route"],
        "properties": {
            "_id": {"bsonType": "string", "pattern": "^MED-[0-9]{4,}$"},
            "drone_id": {"bsonType": "string"},
            "status": {"enum": ["planned","executing","completed","failed","aborted"]},
            "planned_route": {"bsonType": "array", "minItems": 2},
        },
    }
}
await apply_validator("missions", MISSION_VALIDATOR)
```

### Indexes

```python
await db.missions.create_index([("status", 1), ("started_at", -1)], name="status_started")
await db.missions.create_index([("drone_id", 1), ("started_at", -1)], name="by_drone_time")
await db.missions.create_index([("delivery_ids", 1)], name="by_delivery")
await db.missions.create_index([("completed_at", -1)], name="recency")
```

### Example

```json
{
  "_id": "MED-0421",
  "delivery_ids": ["65a6c0001234abcd56780001"],
  "drone_id": "Drone1",
  "status": "executing",
  "planned_route": [
    {"name":"Depot","lat":51.5074,"lon":-0.1278,"alt_m":30},
    {"name":"Royal London","lat":51.5185,"lon":-0.0590,"alt_m":30}
  ],
  "actual_route": [
    {"name":"Depot","lat":51.5074,"lon":-0.1278,"arrived_at":{"$date":"2026-05-12T13:30:11Z"}}
  ],
  "reroutes": [],
  "obstacles": [],
  "weather_events": [
    {"at":{"$date":"2026-05-12T13:35:00Z"}, "location_id":"Royal London",
     "wind_speed_ms": 11.2, "note":"gust within tolerance"}
  ],
  "started_at": {"$date":"2026-05-12T13:30:00Z"},
  "estimated_distance_m": 4920,
  "estimated_battery_pct": 38.2
}
```

### Producers / consumers
- **Writers**: `RoutePlannerAgent`, `MissionExecutor`, `ReplannerAgent`, `VisionAgent` (obstacles), `WeatherAgent` (weather_events).
- **Readers**: `ReflectionAgent`, `NarratorAgent`, `OperatorDashboard`, `AuditAgent`.

### Change Stream
- `MissionBroadcastWorker` pushes status & reroute deltas to the UI.
- `ReflectionAgent` watches transitions to `completed|failed|aborted` and triggers memory generation.

---

## 7 · `telemetry` (time-series)

**Why.** Per-drone high-frequency state (10 Hz). Native time-series storage, retained 7 days. Used for live charts, anomaly detection, and to reconstruct missions deterministically.

### Pydantic v2

```python
class Telemetry(BaseModel):
    ts: datetime
    drone_id: str
    lat: float
    lon: float
    alt_m: float
    speed_ms: float
    heading_deg: float
    battery: float
    payload_kg: float
    motors_pct: list[float] = Field(default_factory=list)
    temperature_c: Optional[float] = None
    cargo_temperature_c: Optional[float] = None
    gps_fix: int = 3
    rssi_dbm: Optional[float] = None
    anomaly_score: Optional[float] = None
```

### Collection + validator

```python
TELEMETRY_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["ts", "drone_id", "lat", "lon", "battery"],
        "properties": {
            "ts": {"bsonType": "date"},
            "drone_id": {"bsonType": "string"},
            "battery": {"bsonType": "double", "minimum": 0, "maximum": 100},
        },
    }
}

await db.create_collection(
    "telemetry",
    timeseries={"timeField": "ts", "metaField": "drone_id", "granularity": "seconds"},
    expireAfterSeconds=60 * 60 * 24 * 7,
)
await db.command({"collMod": "telemetry", "validator": TELEMETRY_VALIDATOR})
await db.telemetry.create_index([("drone_id", 1), ("ts", -1)], name="drone_ts")
await db.telemetry.create_index([("anomaly_score", -1), ("ts", -1)], name="anomaly_ts")
```

### Example

```json
{
  "ts": {"$date":"2026-05-12T13:42:11.500Z"},
  "drone_id": "Drone1", "lat": 51.514, "lon": -0.103, "alt_m": 30.4,
  "speed_ms": 14.7, "heading_deg": 87.5, "battery": 67.4,
  "payload_kg": 0.5, "motors_pct": [62,63,61,64],
  "cargo_temperature_c": 4.1, "gps_fix": 3, "rssi_dbm": -68,
  "anomaly_score": 0.04
}
```

### Producers / consumers
- **Writers**: `DroneStateWorker` (from PX4 SITL/AirSim/mock).
- **Readers**: `AnomalyDetectorAgent`, `BatteryForecastAgent`, `TelemetryStreamWebSocket`, `MissionReconstructAgent`.

### Change Stream
- `AnomalyDetectorAgent` watches inserts; if `anomaly_score > 0.7` it raises a `Replan` event into `agent_messages`.

---

## 8 · `flight_logs`

**Why.** Append-only event log per drone. Lower-frequency than telemetry; captures discrete events (`takeoff`, `waypoint_reached`, `obstacle_detected`, `payload_dropped`). The audit pipeline reads this; the ReflectionAgent uses it to summarise *what actually happened*.

### Pydantic v2

```python
class FlightLog(MongoModel):
    drone_id: str
    mission_id: Optional[str] = None
    ts: datetime = Field(default_factory=utcnow)
    event: Literal["takeoff","waypoint_reached","reroute","obstacle_detected",
                   "payload_dropped","landing","emergency_land","fault"]
    payload: dict[str, Any] = Field(default_factory=dict)
```

### Validator + indexes

```python
LOG_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["drone_id", "ts", "event"],
        "properties": {
            "event": {"enum": ["takeoff","waypoint_reached","reroute","obstacle_detected",
                                "payload_dropped","landing","emergency_land","fault"]},
        },
    }
}
await apply_validator("flight_logs", LOG_VALIDATOR)
await db.flight_logs.create_index([("drone_id", 1), ("ts", -1)], name="drone_ts")
await db.flight_logs.create_index([("mission_id", 1), ("ts", 1)], name="mission_ts")
await db.flight_logs.create_index([("event", 1), ("ts", -1)], name="event_ts")
```

### Example

```json
{ "drone_id":"Drone1","mission_id":"MED-0421","ts":{"$date":"2026-05-12T13:34:02Z"},
  "event":"obstacle_detected",
  "payload":{"kind":"crane","confidence":0.91,"bbox":[120,80,260,230]} }
```

### Producers / consumers
- **Writers**: `MissionExecutor`, `VisionAgent`.
- **Readers**: `AuditAgent`, `ReflectionAgent`, `OperatorTimelineUI`.

### Change Stream
- `OperatorTimelineUI` (WebSocket) watches per `mission_id`.

---

## 9 · `audit_trail`

**Why.** Immutable chain-of-custody. Each entry contains a `prev_hash` (sha256 of the previous entry's canonical bytes) plus its own `hash`, forming a tamper-evident chain. The `signature_id` links to the recipient handover. NHS-grade compliance.

### Pydantic v2

```python
class AuditEntry(MongoModel):
    ts: datetime = Field(default_factory=utcnow)
    actor: str                            # agent or user_id
    action: str                           # "delivery.delivered", "mission.completed"
    subject_type: str                     # "delivery","mission","drone"
    subject_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    signature_id: Optional[str] = None
    prev_hash: str                        # 64-hex
    hash: str                             # 64-hex
    seq: int                              # strictly monotonic
```

### Validator + indexes

```python
AUDIT_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["ts","actor","action","subject_type","subject_id","prev_hash","hash","seq"],
        "properties": {
            "prev_hash": {"bsonType": "string", "pattern": "^[a-f0-9]{64}$"},
            "hash":      {"bsonType": "string", "pattern": "^[a-f0-9]{64}$"},
            "seq":       {"bsonType": "long", "minimum": 0},
        },
    }
}
await apply_validator("audit_trail", AUDIT_VALIDATOR)
await db.audit_trail.create_index([("seq", 1)], name="seq", unique=True)
await db.audit_trail.create_index([("subject_type", 1), ("subject_id", 1), ("ts", -1)], name="subj")
await db.audit_trail.create_index([("ts", -1)], name="ts")
```

Hash chain helper:

```python
import hashlib, json
async def append_audit(entry: dict) -> dict:
    prev = await db.audit_trail.find_one(sort=[("seq", -1)])
    seq = (prev["seq"] + 1) if prev else 0
    prev_hash = prev["hash"] if prev else "0" * 64
    canonical = json.dumps({**entry, "seq": seq, "prev_hash": prev_hash},
                            sort_keys=True, default=str).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    doc = {**entry, "seq": seq, "prev_hash": prev_hash, "hash": digest}
    await db.audit_trail.insert_one(doc)
    return doc
```

### Example

```json
{ "ts":{"$date":"2026-05-12T13:48:09Z"},"actor":"AuditAgent",
  "action":"delivery.delivered","subject_type":"delivery",
  "subject_id":"65a6c0001234abcd56780001","signature_id":"SIG-00abc",
  "payload":{"by":"nurse_rj42","temperature_c":4.2},
  "seq":4187,"prev_hash":"…","hash":"…" }
```

### Producers / consumers
- **Writers**: `AuditAgent` only (single writer; serialised by an in-process lock).
- **Readers**: `ComplianceReportRenderer` (PDF → GridFS), `AdminAPI`.

### Change Stream
- None — this collection is immutable.

---

## 10 · `mission_memory` ⭐

**Why.** The brain of the self-evolving system. Every reflection, incident, regulation chunk, facility intel note, operator preference, and learned skill becomes a 1024-dim Voyage embedding here, retrievable via `$vectorSearch` filtered by `kind`, `region`, `weather_class`, `success`. See [`03-mongodb-vector-rag.md`](./03-mongodb-vector-rag.md) for the full retrieval loop.

### Pydantic v2

```python
class MemoryMetadata(BaseModel):
    region: Optional[str] = None
    weather_class: Optional[Literal["clear","rain","snow","fog","storm","wind"]] = None
    success: Optional[bool] = None
    severity: Optional[str] = None
    lessons: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

class MissionMemory(MongoModel):
    kind: Literal["reflection","incident","regulation","facility_intel",
                  "operator_pref","skill"]
    title: str
    text: str                              # the chunk that was embedded
    embedding: list[float]                 # 1024-dim Voyage voyage-3-large
    embedding_model: str = "voyage-3-large"
    metadata: MemoryMetadata = Field(default_factory=MemoryMetadata)
    source_collection: Optional[str] = None     # provenance
    source_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    score_ema: float = 0.0                       # exponential-moving-average usefulness
```

### Validator

```python
MEMORY_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["kind", "title", "text", "embedding", "embedding_model", "created_at"],
        "properties": {
            "kind": {"enum": ["reflection","incident","regulation","facility_intel",
                              "operator_pref","skill"]},
            "embedding": {"bsonType": "array", "minItems": 256, "maxItems": 1024,
                          "items": {"bsonType": "double"}},
            "embedding_model": {"bsonType": "string"},
            "use_count": {"bsonType": "int", "minimum": 0},
        },
    }
}
await apply_validator("mission_memory", MEMORY_VALIDATOR)
await db.mission_memory.create_index([("kind", 1), ("created_at", -1)], name="kind_time")
await db.mission_memory.create_index([("metadata.region", 1)], name="region")
await db.mission_memory.create_index([("metadata.tags", 1)], name="tags_multikey")
await db.mission_memory.create_index([("source_collection", 1), ("source_id", 1)], name="provenance")
```

Atlas Vector Search index (JSON):

```json
{
  "name": "mission_memory_vec",
  "collectionName": "mission_memory",
  "database": "droran",
  "type": "vectorSearch",
  "fields": [
    { "type": "vector", "path": "embedding", "numDimensions": 1024, "similarity": "cosine" },
    { "type": "filter", "path": "kind" },
    { "type": "filter", "path": "metadata.region" },
    { "type": "filter", "path": "metadata.weather_class" },
    { "type": "filter", "path": "metadata.success" },
    { "type": "filter", "path": "embedding_model" }
  ]
}
```

### Example

```json
{
  "_id": {"$oid":"65a7e0c01234"},
  "kind":"reflection",
  "title":"Wind shear corridor west of Royal London — abort threshold too lax",
  "text":"On MED-0398 we attempted approach via the west corridor at 9.4 m/s gusting 13.8…",
  "embedding":[0.0123, -0.0456, ...],
  "embedding_model":"voyage-3-large",
  "metadata":{
    "region":"London",
    "weather_class":"wind",
    "success":false,
    "severity":"high",
    "lessons":[
      "Increase wind threshold from 12 to 10 m/s for west-corridor approaches.",
      "Prefer north-east corridor when gust factor > 1.4."
    ],
    "tags":["wind_shear","royal_london","west_corridor"]
  },
  "source_collection":"missions",
  "source_id":"MED-0398",
  "created_at":{"$date":"2026-04-30T22:02:00Z"},
  "use_count": 14,
  "score_ema": 0.81
}
```

### Producers / consumers
- **Writers**: `ReflectionAgent`, `seeds/seed_regulations.py`, `seeds/seed_demo_memories.py`, `FacilityIntelAgent`, `OperatorPrefAgent`, `RetrievalLearner`.
- **Readers**: `RoutePlannerAgent`, `ReplannerAgent`, `RetrievalCriticAgent`, `MultiSourceSynthesizer`, `NarratorAgent`.

### Change Stream
- `MemoryUseTracker` updates `last_used_at`, `use_count`, and `score_ema` after each retrieval session (called from `03-mongodb-vector-rag.md` § 6).

---

## 11 · `regulations`

**Why.** Per-country profiles drive what the planner is *allowed* to do (max altitude, BVLOS, night-flight). The chunked text is also embedded into `mission_memory` with `kind:"regulation"` so the RAG agent can quote the exact paragraph.

### Pydantic v2

```python
class Regulation(MongoModel):
    code: str                              # "UK_CAA","FAA_PART_107","EASA_OPEN_A1"
    country: str
    title: str
    version: str
    max_altitude_m: float
    bvlos_allowed: bool
    night_allowed: bool
    over_people_allowed: bool
    max_takeoff_mass_kg: float
    notes_md: str
    effective_from: datetime
    effective_to: Optional[datetime] = None
```

### Validator + indexes

```python
REG_VALIDATOR = {
    "$jsonSchema":{
        "bsonType":"object",
        "required":["code","country","title","version","max_altitude_m","effective_from"],
        "properties":{
            "code":{"bsonType":"string"},
            "country":{"bsonType":"string","minLength":2,"maxLength":3},
            "max_altitude_m":{"bsonType":"double","minimum":0,"maximum":1000},
        },
    }
}
await apply_validator("regulations", REG_VALIDATOR)
await db.regulations.create_index([("code",1)], name="code", unique=True)
await db.regulations.create_index([("country",1),("effective_from",-1)], name="country_time")
```

### Example

```json
{
  "code":"UK_CAA",
  "country":"GB",
  "title":"UK CAA Article 16 / CAP 722 — Open Category",
  "version":"2024.10",
  "max_altitude_m":120.0,
  "bvlos_allowed":false,
  "night_allowed":true,
  "over_people_allowed":false,
  "max_takeoff_mass_kg":25.0,
  "notes_md":"# UK CAA Open Category…",
  "effective_from":{"$date":"2024-10-01T00:00:00Z"}
}
```

### Producers / consumers
- **Writers**: `seeds/seed_regulations.py`, `RegUpdaterAgent` (manual / scheduled refresh).
- **Readers**: `RoutePlannerAgent`, `AirLawAgent`, `RetrievalCriticAgent`.

### Change Stream
- `EmbeddingRefreshWorker` watches updates and re-chunks/re-embeds into `mission_memory`.

---

## 12 · `chat_sessions` + `chat_messages`

**Why.** Per-operator conversation history. Backed by **LangChain `MongoDBChatMessageHistory`** keyed by `operator_id`. Atlas Search index over message text for "what did the operator ask yesterday?" recall.

### Pydantic v2

```python
class ChatSession(MongoModel):
    operator_id: str
    title: str
    started_at: datetime = Field(default_factory=utcnow)
    last_active_at: datetime = Field(default_factory=utcnow)
    mission_id: Optional[str] = None

class ChatMessage(MongoModel):
    session_id: str
    operator_id: str
    role: Literal["system","user","assistant","tool"]
    content: str
    name: Optional[str] = None             # tool name when role="tool"
    tool_call_id: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_ms: Optional[int] = None
    ts: datetime = Field(default_factory=utcnow)
```

### Validators + indexes

```python
CHAT_SESSION_VALIDATOR = {
    "$jsonSchema": {
        "bsonType":"object",
        "required":["operator_id","title","started_at"],
        "properties":{"operator_id":{"bsonType":"string"}}
    }
}
CHAT_MESSAGE_VALIDATOR = {
    "$jsonSchema":{
        "bsonType":"object",
        "required":["session_id","operator_id","role","content","ts"],
        "properties":{"role":{"enum":["system","user","assistant","tool"]}}
    }
}
await apply_validator("chat_sessions", CHAT_SESSION_VALIDATOR)
await apply_validator("chat_messages", CHAT_MESSAGE_VALIDATOR)

await db.chat_sessions.create_index([("operator_id",1),("last_active_at",-1)], name="op_time")
await db.chat_messages.create_index([("session_id",1),("ts",1)], name="sess_ts")
await db.chat_messages.create_index([("operator_id",1),("ts",-1)], name="op_recent")
```

Atlas Search index for message recall:

```json
{
  "name":"chat_messages_search",
  "collectionName":"chat_messages","database":"droran",
  "mappings":{
    "dynamic":false,
    "fields":{
      "content":{"type":"string","analyzer":"lucene.standard"},
      "operator_id":{"type":"stringFacet"},
      "role":{"type":"stringFacet"},
      "ts":{"type":"date"}
    }
  }
}
```

### Producers / consumers
- **Writers**: `LangGraph` runtime via `MongoDBChatMessageHistory`.
- **Readers**: `RecallAgent`, the operator UI history pane.

### Change Stream
- `OperatorUI` watches `chat_messages` filtered by `session_id` for live conversation streaming.

---

## 13 · `users` + `api_keys` + `operators`

**Why.** Auth (Atlas App Services-backed) plus an `operators` collection that holds **preferences** which are themselves promoted into `mission_memory` so the planner *recalls* "Operator 42 prefers north-east corridor at night" without an explicit prompt.

### Pydantic v2

```python
class User(MongoModel):
    email: str
    display_name: str
    auth_provider: Literal["atlas","google","github"] = "atlas"
    created_at: datetime = Field(default_factory=utcnow)
    roles: list[Literal["admin","operator","viewer","auditor"]] = Field(default_factory=list)

class ApiKey(MongoModel):
    user_id: str
    label: str
    hashed_key: str                            # sha256
    scopes: list[str]
    created_at: datetime = Field(default_factory=utcnow)
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

class OperatorPreferences(BaseModel):
    voice_alerts: bool = True
    preferred_corridors: list[str] = Field(default_factory=list)
    risk_tolerance: Literal["low","medium","high"] = "medium"
    locale: str = "en-GB"
    notification_phone: Optional[str] = None

class Operator(MongoModel):
    user_id: str
    callsign: str
    region: str
    on_shift: bool = False
    preferences: OperatorPreferences = Field(default_factory=OperatorPreferences)
    created_at: datetime = Field(default_factory=utcnow)
```

### Indexes

```python
await db.users.create_index([("email",1)], unique=True, name="email_unique")
await db.api_keys.create_index([("user_id",1)], name="by_user")
await db.api_keys.create_index([("hashed_key",1)], unique=True, name="hashed_key_unique")
await db.operators.create_index([("user_id",1)], unique=True, name="by_user")
await db.operators.create_index([("region",1),("on_shift",1)], name="shift_lookup")
```

### Example operator

```json
{
  "_id":{"$oid":"65a8…"},
  "user_id":"65a7…",
  "callsign":"MEDIC-ACTUAL",
  "region":"London",
  "on_shift":true,
  "preferences":{
    "voice_alerts":true,
    "preferred_corridors":["NE","E"],
    "risk_tolerance":"medium",
    "locale":"en-GB"
  }
}
```

### Producers / consumers
- **Writers**: `AuthAPI`, `OperatorAdminAPI`, `OperatorPrefAgent` (learns prefs from observed overrides).
- **Readers**: every agent (operator-aware planning).

### Change Stream
- `OperatorPrefAgent` watches `operators.preferences` updates; on change it re-embeds the preferences into `mission_memory` (`kind:"operator_pref"`).

---

## 14 · `synthetic_emergencies`

**Why.** 44 118 rows of historical demand from `data/synthetic_emergencies.csv`. Used by `DemandForecastAgent` to seed prepositioning and to evaluate the schedule under simulated load.

### Pydantic v2 (matches the CSV columns)

```python
class SyntheticEmergency(MongoModel):
    ts: datetime
    location_id: str
    location_lat: float
    location_lon: float
    emergency_type: Literal["respiratory","cardiac","trauma","obstetric",
                            "neurological","metabolic","pediatric","other"]
    severity: int                          # 1..5
    temperature_c: float
    weather_condition: str
    is_holiday: bool
    is_event: bool
    hour_of_day: int
    day_of_week: int                       # 0=Mon
```

### Validator + indexes

```python
SE_VALIDATOR = {
    "$jsonSchema":{
        "bsonType":"object",
        "required":["ts","location_id","emergency_type","severity"],
        "properties":{
            "severity":{"bsonType":"int","minimum":1,"maximum":5},
            "hour_of_day":{"bsonType":"int","minimum":0,"maximum":23},
            "day_of_week":{"bsonType":"int","minimum":0,"maximum":6},
        },
    }
}
await apply_validator("synthetic_emergencies", SE_VALIDATOR)
await db.synthetic_emergencies.create_index([("ts",1)], name="ts")
await db.synthetic_emergencies.create_index([("location_id",1),("ts",1)], name="loc_ts")
await db.synthetic_emergencies.create_index([("emergency_type",1),("severity",-1)], name="type_sev")
```

### Example

```json
{ "ts":{"$date":"2025-01-01T00:05:24Z"}, "location_id":"Clinic B",
  "location_lat":51.5174,"location_lon":-0.135, "emergency_type":"respiratory",
  "severity":1, "temperature_c":-0.9, "weather_condition":"snow",
  "is_holiday":true,"is_event":false,"hour_of_day":0,"day_of_week":2 }
```

### Producers / consumers
- **Writers**: `seeds/seed_synthetic_emergencies.py`.
- **Readers**: `DemandForecastAgent`, `PrepositionAgent`, `EvalHarness`.

### Change Stream
- None.

---

## 15 · `agent_skills` ⭐

**Why.** A registry where every agent advertises its capability as natural-language **`capability_text`** plus a Voyage embedding. The `SupervisorAgent` does **peer discovery** via `$vectorSearch` over this collection: "I need an agent that can plan a battery-aware reroute around a moving NFZ" → top-k skills → call them. `reliability_score` is updated by the ReflectionAgent.

### Pydantic v2

```python
class ToolSpec(BaseModel):
    name: str
    schema: dict                           # JSON Schema for the tool args
    description: str

class AgentSkill(MongoModel):
    agent: str                             # "RoutePlannerAgent"
    capability_text: str                   # one paragraph
    embedding: list[float]                 # 1024-dim voyage-3-large
    tools: list[ToolSpec] = Field(default_factory=list)
    cost_estimate_gbp_per_call: float = 0.0
    avg_latency_ms: float = 0.0
    reliability_score: float = 1.0         # 0..1, EMA from ReflectionAgent
    version: str = "1.0.0"
    enabled: bool = True
    updated_at: datetime = Field(default_factory=utcnow)
```

### Validator + indexes + Vector Search

```python
SKILL_VALIDATOR = {
    "$jsonSchema":{
        "bsonType":"object",
        "required":["agent","capability_text","embedding"],
        "properties":{
            "embedding":{"bsonType":"array","minItems":1024,"maxItems":1024},
            "reliability_score":{"bsonType":"double","minimum":0,"maximum":1},
        },
    }
}
await apply_validator("agent_skills", SKILL_VALIDATOR)
await db.agent_skills.create_index([("agent",1)], unique=True, name="agent_unique")
await db.agent_skills.create_index([("enabled",1),("reliability_score",-1)], name="best_first")
```

```json
{
  "name":"agent_skills_vec",
  "collectionName":"agent_skills","database":"droran",
  "type":"vectorSearch",
  "fields":[
    {"type":"vector","path":"embedding","numDimensions":1024,"similarity":"cosine"},
    {"type":"filter","path":"enabled"},
    {"type":"filter","path":"agent"}
  ]
}
```

### Example

```json
{
  "agent":"ReplannerAgent",
  "capability_text":"Recomputes a safe route mid-flight when weather, no-fly zones, or detected obstacles invalidate the current plan. Considers battery, payload weight, and operator corridor preferences.",
  "embedding":[…1024],
  "tools":[{"name":"replan","description":"Replan from current position","schema":{…}}],
  "cost_estimate_gbp_per_call":0.012,
  "avg_latency_ms":840,
  "reliability_score":0.93,
  "enabled":true
}
```

### Producers / consumers
- **Writers**: `seeds/seed_agent_skills.py`, `ReflectionAgent` (reliability EMA).
- **Readers**: `SupervisorAgent`, `RouterAgent`.

### Change Stream
- `SupervisorAgent` watches updates so capability changes (e.g. new tool added) are picked up live.

---

## 16 · `agent_messages`

**Why.** Append-only log of A2A (agent-to-agent) protocol messages. Powers the "explain the agent" UI and the offline post-mortems.

### Pydantic v2

```python
class AgentMessage(MongoModel):
    mission_id: Optional[str] = None
    trace_id: str
    span_id: Optional[str] = None
    from_agent: str
    to_agent: str
    role: Literal["request","response","broadcast","tool_call","tool_result"]
    content: dict[str, Any]                # structured payload
    context_doc_ids: list[str] = Field(default_factory=list)
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    latency_ms: Optional[int] = None
    ts: datetime = Field(default_factory=utcnow)
```

### Validator + indexes

```python
AM_VALIDATOR = {
    "$jsonSchema":{
        "bsonType":"object",
        "required":["trace_id","from_agent","to_agent","role","ts"],
        "properties":{"role":{"enum":["request","response","broadcast","tool_call","tool_result"]}},
    }
}
await apply_validator("agent_messages", AM_VALIDATOR)
await db.agent_messages.create_index([("mission_id",1),("ts",1)], name="mission_ts")
await db.agent_messages.create_index([("trace_id",1),("ts",1)], name="trace_ts")
await db.agent_messages.create_index([("from_agent",1),("to_agent",1),("ts",-1)], name="dyad")
```

### Example

```json
{ "mission_id":"MED-0421","trace_id":"trc_a91","span_id":"sp_1",
  "from_agent":"SupervisorAgent","to_agent":"RoutePlannerAgent",
  "role":"request",
  "content":{"task":"plan","origin":"Depot","dest":"Royal London","priority":"critical"},
  "context_doc_ids":["mem:#abc","reg:#UK_CAA"],"tokens_in":312,"tokens_out":0,
  "latency_ms":4,"ts":{"$date":"2026-05-12T13:30:00Z"} }
```

### Producers / consumers
- **Writers**: every agent (via the A2A bus).
- **Readers**: `ExplainAgentUI`, `Postmortem`, `CostAttribution`.

### Change Stream
- `ExplainAgentUI` (WebSocket) tails by `trace_id`.

---

## 17 · `tool_call_log`

**Why.** Crash-safe replay. Every tool call records an `idempotency_key` and `args_hash`; if the same call is retried after a crash, the executor returns the cached `result_hash` instead of re-executing (critical for actuator commands).

### Pydantic v2

```python
class ToolCallLog(MongoModel):
    idempotency_key: str                    # uuid4 from the caller
    agent: str
    tool: str
    args_hash: str                          # sha256
    args: dict[str, Any]
    status: Literal["pending","success","error"] = "pending"
    result_hash: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    attempt: int = 1
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
```

### Validator + indexes

```python
TC_VALIDATOR = {
    "$jsonSchema":{
        "bsonType":"object",
        "required":["idempotency_key","agent","tool","args_hash","status"],
        "properties":{"status":{"enum":["pending","success","error"]}}
    }
}
await apply_validator("tool_call_log", TC_VALIDATOR)
await db.tool_call_log.create_index([("idempotency_key",1)], unique=True, name="idem_unique")
await db.tool_call_log.create_index([("agent",1),("tool",1),("started_at",-1)], name="agent_tool_time")
await db.tool_call_log.create_index([("status",1),("started_at",-1)], name="status_time")
```

### Producers / consumers
- **Writers**: `ToolExecutor` (the only place tools run).
- **Readers**: `Postmortem`, retry/replay worker.

### Change Stream
- None (queried, not pushed).

---

## 18 · `langgraph_checkpoints`

**Why.** Managed by `langgraph-checkpoint-mongodb`. Don't touch the schema; just create the indexes the package expects so resume is fast.

### Setup

```python
from langgraph.checkpoint.mongodb import MongoDBSaver
checkpointer = MongoDBSaver(client=client, db_name=DB_NAME, collection_name="langgraph_checkpoints")
await checkpointer.setup()        # creates indexes idempotently
```

(The package creates a unique compound index on `(thread_id, checkpoint_id)`. Verify it exists in `seeds/check_health.py`.)

### Producers / consumers
- **Writers/readers**: LangGraph runtime only.

### Change Stream
- None.

---

## 19 · `traces`

**Why.** OTel-style spans for the "explain the agent" UI. Cheaper-to-query duplicate of what we'd send to Tempo, but stored alongside the data so demos work offline.

### Pydantic v2

```python
class Span(MongoModel):
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    name: str
    kind: Literal["server","client","internal","producer","consumer"] = "internal"
    service: str
    start_ts: datetime
    end_ts: datetime
    duration_ms: float
    status: Literal["OK","ERROR"] = "OK"
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
```

### Validator + indexes

```python
SPAN_VALIDATOR = {
    "$jsonSchema":{
        "bsonType":"object",
        "required":["trace_id","span_id","name","service","start_ts","end_ts"],
        "properties":{"status":{"enum":["OK","ERROR"]}}
    }
}
await apply_validator("traces", SPAN_VALIDATOR)
await db.traces.create_index([("trace_id",1),("start_ts",1)], name="trace_time")
await db.traces.create_index([("service",1),("name",1),("start_ts",-1)], name="svc_name")
await db.traces.create_index([("start_ts",1)], name="ttl",
                              expireAfterSeconds=60*60*24*14)
```

### Producers / consumers
- **Writers**: OTel exporter.
- **Readers**: `ExplainAgentUI`.

### Change Stream
- `ExplainAgentUI` tails `trace_id`.

---

## 20 · `reflection_eval`

**Why.** Powers the **self-evolution chart** in the demo. After every reflection cycle we record `take_n` metrics for a fixed scenario set; the UI plots `take_n` vs `take_(n-1)` to *visibly* show learning.

### Pydantic v2

```python
class ScenarioMetric(BaseModel):
    scenario_id: str                       # "wind_shear_west_corridor"
    success_rate: float
    avg_distance_m: float
    avg_battery_used_pct: float
    avg_replans: float
    sample_size: int

class ReflectionEval(MongoModel):
    take: int                              # monotonically incrementing
    ts: datetime = Field(default_factory=utcnow)
    metrics: list[ScenarioMetric]
    overall_success_rate: float
    notes: Optional[str] = None
```

### Validator + indexes

```python
RE_VALIDATOR = {
    "$jsonSchema":{
        "bsonType":"object",
        "required":["take","ts","metrics","overall_success_rate"],
        "properties":{"take":{"bsonType":"int","minimum":0}},
    }
}
await apply_validator("reflection_eval", RE_VALIDATOR)
await db.reflection_eval.create_index([("take",1)], unique=True, name="take_unique")
await db.reflection_eval.create_index([("ts",-1)], name="ts_recent")
```

### Example

```json
{ "take":7,"ts":{"$date":"2026-05-12T18:00:00Z"},
  "metrics":[
    {"scenario_id":"wind_shear_west_corridor","success_rate":0.82,
     "avg_distance_m":5120,"avg_battery_used_pct":42.1,"avg_replans":1.1,"sample_size":50}
  ],
  "overall_success_rate":0.86 }
```

### Producers / consumers
- **Writers**: `ReflectionAgent` nightly job.
- **Readers**: `EvolutionChartAPI`.

### Change Stream
- UI watches inserts to live-update the chart.

---

## 21 · `documents` + `document_chunks`

**Why.** General RAG corpus (operator manuals, NHS protocols, manufacturer sheets). Chunks live separately so we can re-chunk without losing the source. Embeddings live on the chunk. **See [`03-mongodb-vector-rag.md`](./03-mongodb-vector-rag.md) §2 for the chunking strategies and §3 for the Atlas Vector Search index.**

### Pydantic v2

```python
class Document(MongoModel):
    title: str
    source_url: Optional[str] = None
    source_type: Literal["pdf","markdown","html","docx"] = "markdown"
    gridfs_id: Optional[str] = None        # raw bytes
    sha256: str
    text: str                              # extracted plain text
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)

class DocumentChunk(MongoModel):
    document_id: str
    ordinal: int
    text: str
    token_count: int
    chunk_strategy: Literal["fixed_512","markdown_recursive","semantic","late_context"]
    embedding: list[float]                 # 1024-dim
    embedding_model: str = "voyage-3-large"
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### Validators + indexes

```python
DOC_VALIDATOR = {
    "$jsonSchema":{
        "bsonType":"object","required":["title","sha256","text"],
        "properties":{"sha256":{"bsonType":"string","pattern":"^[a-f0-9]{64}$"}}
    }
}
CHUNK_VALIDATOR = {
    "$jsonSchema":{
        "bsonType":"object",
        "required":["document_id","ordinal","text","token_count","chunk_strategy","embedding"],
        "properties":{
            "chunk_strategy":{"enum":["fixed_512","markdown_recursive","semantic","late_context"]},
            "embedding":{"bsonType":"array","minItems":256,"maxItems":1024},
        }
    }
}
await apply_validator("documents", DOC_VALIDATOR)
await apply_validator("document_chunks", CHUNK_VALIDATOR)
await db.documents.create_index([("sha256",1)], unique=True, name="sha_unique")
await db.document_chunks.create_index([("document_id",1),("ordinal",1)],
                                       unique=True, name="doc_ord")
await db.document_chunks.create_index([("chunk_strategy",1)], name="strategy")
```

```json
{
  "name":"document_chunks_vec",
  "collectionName":"document_chunks","database":"droran",
  "type":"vectorSearch",
  "fields":[
    {"type":"vector","path":"embedding","numDimensions":1024,"similarity":"cosine"},
    {"type":"filter","path":"chunk_strategy"},
    {"type":"filter","path":"embedding_model"},
    {"type":"filter","path":"document_id"}
  ]
}
```

```json
{
  "name":"document_chunks_search",
  "collectionName":"document_chunks","database":"droran",
  "mappings":{"dynamic":false,
    "fields":{
      "text":{"type":"string","analyzer":"lucene.english"},
      "metadata.tags":{"type":"string","analyzer":"lucene.keyword"}
    }}
}
```

### Producers / consumers
- **Writers**: `DocIngestAgent`, `seeds/seed_regulations.py`.
- **Readers**: `RAGRetriever`, `MultiSourceSynthesizer`.

### Change Stream
- `EmbeddingRefreshWorker` watches inserts/updates and (re)embeds chunks asynchronously.

---

## §  Atlas Search index definitions (single-source-of-truth JSON)

Push these via the Atlas Admin API in `seeds/create_indexes.py` (see [`09-seed-and-data.md`](./09-seed-and-data.md)).

```json
[
  {
    "name":"facilities_search","collectionName":"facilities","database":"droran",
    "mappings":{"dynamic":false,"fields":{
      "name":{"type":"string","analyzer":"lucene.standard"},
      "address":{"type":"string","analyzer":"lucene.standard"},
      "region":{"type":"stringFacet"},
      "type":{"type":"stringFacet"},
      "capabilities":{"type":"string","analyzer":"lucene.keyword"},
      "location":{"type":"geo"}
    }}
  },
  {
    "name":"chat_messages_search","collectionName":"chat_messages","database":"droran",
    "mappings":{"dynamic":false,"fields":{
      "content":{"type":"string","analyzer":"lucene.standard"},
      "operator_id":{"type":"stringFacet"},
      "role":{"type":"stringFacet"},
      "ts":{"type":"date"}
    }}
  },
  {
    "name":"document_chunks_search","collectionName":"document_chunks","database":"droran",
    "mappings":{"dynamic":false,"fields":{
      "text":{"type":"string","analyzer":"lucene.english"},
      "metadata.tags":{"type":"string","analyzer":"lucene.keyword"}
    }}
  }
]
```

## §  Atlas Vector Search index definitions

```json
[
  {
    "name":"mission_memory_vec","collectionName":"mission_memory","database":"droran",
    "type":"vectorSearch",
    "fields":[
      {"type":"vector","path":"embedding","numDimensions":1024,"similarity":"cosine"},
      {"type":"filter","path":"kind"},
      {"type":"filter","path":"metadata.region"},
      {"type":"filter","path":"metadata.weather_class"},
      {"type":"filter","path":"metadata.success"},
      {"type":"filter","path":"embedding_model"}
    ]
  },
  {
    "name":"document_chunks_vec","collectionName":"document_chunks","database":"droran",
    "type":"vectorSearch",
    "fields":[
      {"type":"vector","path":"embedding","numDimensions":1024,"similarity":"cosine"},
      {"type":"filter","path":"chunk_strategy"},
      {"type":"filter","path":"embedding_model"},
      {"type":"filter","path":"document_id"}
    ]
  },
  {
    "name":"agent_skills_vec","collectionName":"agent_skills","database":"droran",
    "type":"vectorSearch",
    "fields":[
      {"type":"vector","path":"embedding","numDimensions":1024,"similarity":"cosine"},
      {"type":"filter","path":"enabled"},
      {"type":"filter","path":"agent"}
    ]
  }
]
```

Use `numCandidates ≥ 10 × k` at query time (see RAG file).

## §  Atlas Trigger code — `functions/weather_reroute.js`

Trigger configuration:

```json
{
  "name":"weather_reroute",
  "type":"DATABASE",
  "config":{
    "operation_types":["INSERT"],
    "database":"droran",
    "collection":"weather_observations",
    "service_name":"mongodb-atlas",
    "match":{ "fullDocument.flyable": false },
    "full_document": true
  },
  "function_name":"weather_reroute"
}
```

Function body (`functions/weather_reroute.js`):

```javascript
exports = async function(changeEvent) {
  const obs = changeEvent.fullDocument;
  if (!obs || obs.flyable !== false) return;

  // 1. Find all in-flight missions whose route touches this location.
  const missions = context.services.get("mongodb-atlas")
    .db("droran").collection("missions");
  const affected = await missions.find({
    status: "executing",
    "planned_route.name": obs.location_id,
  }).toArray();

  if (affected.length === 0) return;

  // 2. Fan-out to backend reroute endpoint.
  const url = context.values.get("BACKEND_BASE_URL")
    + "/api/internal/reroute-trigger";
  const body = {
    reason: "weather",
    location_id: obs.location_id,
    wind_speed_ms: obs.wind_speed_ms,
    gust_ms: obs.gust_ms || null,
    mission_ids: affected.map(m => m._id),
    triggered_at: new Date(),
  };

  const resp = await context.http.post({
    url,
    headers: {
      "Content-Type": ["application/json"],
      "X-Internal-Token": [context.values.get("INTERNAL_API_TOKEN")]
    },
    body: JSON.stringify(body),
    encodeBodyAsJSON: true,
  });

  // 3. Persist a flight_log entry per affected mission for the audit trail.
  const logs = context.services.get("mongodb-atlas")
    .db("droran").collection("flight_logs");
  await logs.insertMany(affected.map(m => ({
    drone_id: m.drone_id,
    mission_id: m._id,
    ts: new Date(),
    event: "reroute",
    payload: {
      reason: "weather",
      location_id: obs.location_id,
      wind_speed_ms: obs.wind_speed_ms,
      backend_status: resp.statusCode,
    },
  })));

  return { ok: resp.statusCode < 400, count: affected.length };
};
```

The receiving Python endpoint (FastAPI):

```python
@app.post("/api/internal/reroute-trigger")
async def reroute_trigger(req: RerouteTriggerRequest, x_internal_token: str = Header(...)):
    if x_internal_token != settings.INTERNAL_API_TOKEN:
        raise HTTPException(401)
    for mid in req.mission_ids:
        await event_bus.publish("agent.replan_request", {
            "mission_id": mid, "reason": req.reason, "location_id": req.location_id,
            "wind_speed_ms": req.wind_speed_ms,
        })
    return {"queued": len(req.mission_ids)}
```

---

## §  Cross-collection invariants (enforced by background job `invariants.py`)

1. Every `delivery.mission_id` references a real `missions._id`.
2. Every `mission.drone_id` references a real `drones._id`.
3. `audit_trail.seq` is strictly monotonic and `prev_hash` matches the previous entry's `hash`.
4. For each `chunk_strategy` and `embedding_model` combination in `document_chunks`, the corresponding Atlas Vector Search index exists.
5. Every `agent_skill.embedding` has length **exactly 1024** (Voyage `voyage-3-large`).
6. Every `mission_memory.embedding_model` value is present in `agent_skills.metadata.compatible_models` for at least one retrieval agent.

The job runs every 30 minutes; failures are written to `agent_messages` with `from_agent="InvariantsWorker", role="broadcast"`.

---

## §  Change Stream wiring summary

| Collection | Watcher | Purpose |
|---|---|---|
| `facilities` | `MapBroadcastWorker` | Live map markers |
| `no_fly_zones` | `RouteInvalidatorWorker` | Re-validate in-flight routes |
| `weather_observations` | `weather_reroute` Atlas Trigger | Storm-driven reroute |
| `drones` | `DroneBroadcastWorker` | Live drone state to UI |
| `deliveries` | `SchedulerAgent`, `AuditAgent` | Queue updates + audit transitions |
| `missions` | `MissionBroadcastWorker`, `ReflectionAgent` | UI + post-mission learning |
| `telemetry` | `AnomalyDetectorAgent` | Real-time anomaly detection |
| `flight_logs` | `OperatorTimelineUI` | Live timeline |
| `mission_memory` | `MemoryUseTracker` | Update use_count / score_ema |
| `regulations` | `EmbeddingRefreshWorker` | Re-embed on update |
| `chat_messages` | `OperatorUI` | Live chat fanout |
| `operators` | `OperatorPrefAgent` | Promote prefs into memory |
| `agent_skills` | `SupervisorAgent` | Hot-swap capabilities |
| `agent_messages` | `ExplainAgentUI` | Live trace view |
| `traces` | `ExplainAgentUI` | Live spans |
| `reflection_eval` | `EvolutionChartAPI` | Self-evolution chart |
| `documents`, `document_chunks` | `EmbeddingRefreshWorker` | Async re-embed |

---

## §  Putting it together — `bootstrap_collections.py`

```python
import asyncio
from db import db
from bootstrap import apply_validator
# (import every *_VALIDATOR from the per-collection modules)

async def main():
    await apply_validator("facilities", FACILITIES_VALIDATOR)
    await apply_validator("no_fly_zones", NFZ_VALIDATOR)
    # weather_observations + telemetry are time-series — see §3 / §7
    await apply_validator("drones", DRONE_VALIDATOR)
    await apply_validator("deliveries", DELIVERY_VALIDATOR)
    await apply_validator("missions", MISSION_VALIDATOR)
    await apply_validator("flight_logs", LOG_VALIDATOR)
    await apply_validator("audit_trail", AUDIT_VALIDATOR)
    await apply_validator("mission_memory", MEMORY_VALIDATOR)
    await apply_validator("regulations", REG_VALIDATOR)
    await apply_validator("chat_sessions", CHAT_SESSION_VALIDATOR)
    await apply_validator("chat_messages", CHAT_MESSAGE_VALIDATOR)
    await apply_validator("synthetic_emergencies", SE_VALIDATOR)
    await apply_validator("agent_skills", SKILL_VALIDATOR)
    await apply_validator("agent_messages", AM_VALIDATOR)
    await apply_validator("tool_call_log", TC_VALIDATOR)
    await apply_validator("traces", SPAN_VALIDATOR)
    await apply_validator("reflection_eval", RE_VALIDATOR)
    await apply_validator("documents", DOC_VALIDATOR)
    await apply_validator("document_chunks", CHUNK_VALIDATOR)
    print("✓ all validators applied")

if __name__ == "__main__":
    asyncio.run(main())
```

Indexes are created by `seeds/create_indexes.py` (next file). Health check is `seeds/check_health.py`.

---

**End of `02-mongodb-data-model.md`.** Read [`03-mongodb-vector-rag.md`](./03-mongodb-vector-rag.md) next for the agentic-retrieval system that operates over `mission_memory`, `document_chunks`, `regulations`, and `facilities`. Then [`09-seed-and-data.md`](./09-seed-and-data.md) for the runnable seed scripts and `make seed` target.
