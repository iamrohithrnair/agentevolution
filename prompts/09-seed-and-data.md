# 09 · Seeds, Indexes & Data Bootstrap

> **Cross-references**: collection schemas in [`02-mongodb-data-model.md`](./02-mongodb-data-model.md); RAG pipeline + Voyage clients in [`03-mongodb-vector-rag.md`](./03-mongodb-vector-rag.md).

This file specifies the **idempotent** seed pipeline. After cloning, configuring `.env`, and running `make seed`, the database must be in a fully-demoable state: every index present, every Atlas Search & Vector Search definition pushed, all 489 facilities loaded, all 44 118 historical emergencies imported, four regulation profiles chunked + embedded, agent skills registered, and 50 synthetic past-mission reflections seeded so the demo's "encore" succeeds on first run.

All scripts use **Motor** (async). All scripts are **idempotent**: re-running `make seed` after a partial failure converges to the same state.

```
seeds/
├── __init__.py
├── _common.py
├── create_indexes.py
├── seed_facilities.py
├── seed_no_fly_zones.py
├── seed_regulations.py
├── seed_synthetic_emergencies.py
├── seed_agent_skills.py
├── seed_demo_memories.py
├── check_health.py
└── run_all.py
```

---

## 0 · Configuration & shared helpers

```python
# seeds/_common.py
import os, math, asyncio, hashlib
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URI = os.environ["MONGODB_URI"]
DB_NAME     = os.getenv("MONGODB_DB", "droran")

ATLAS_PUBLIC_KEY  = os.environ["ATLAS_PUBLIC_KEY"]
ATLAS_PRIVATE_KEY = os.environ["ATLAS_PRIVATE_KEY"]
ATLAS_GROUP_ID    = os.environ["ATLAS_GROUP_ID"]      # project ID
ATLAS_CLUSTER     = os.environ["ATLAS_CLUSTER_NAME"]  # e.g. "Cluster0"

client = AsyncIOMotorClient(MONGODB_URI, uuidRepresentation="standard")
db     = client[DB_NAME]

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

# Original flat-earth projection from backend/facilities.py — preserved exactly.
_M_PER_DEG_LAT = 111_320
_M_PER_DEG_LON_AT_EQUATOR = 111_320

def latlon_to_xy(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    x = (lat - ref_lat) * _M_PER_DEG_LAT
    y = (lon - ref_lon) * _M_PER_DEG_LON_AT_EQUATOR * math.cos(math.radians(ref_lat))
    return round(x, 1), round(y, 1)

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
```

`.env.example`:

```
MONGODB_URI=mongodb+srv://user:pwd@cluster0.xxxxx.mongodb.net
MONGODB_DB=droran
ATLAS_PUBLIC_KEY=...
ATLAS_PRIVATE_KEY=...
ATLAS_GROUP_ID=66...
ATLAS_CLUSTER_NAME=Cluster0
VOYAGE_API_KEY=pa-...
OPENAI_API_KEY=sk-...
```

---

## 1 · `seeds/create_indexes.py` — every index, idempotent

Creates B-tree, 2dsphere, and time-series indexes via the driver, then pushes Atlas Search and Atlas Vector Search definitions via the **Atlas Admin API v2** with HTTP digest auth.

```python
# seeds/create_indexes.py
"""
Idempotent index bootstrap.

Run: uv run python -m seeds.create_indexes
"""
from __future__ import annotations
import asyncio, json, sys
import httpx
from httpx import DigestAuth

from ._common import (
    db, client,
    ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY, ATLAS_GROUP_ID, ATLAS_CLUSTER, DB_NAME,
)

ATLAS_BASE = "https://cloud.mongodb.com/api/atlas/v2"
HEADERS = {"Accept": "application/vnd.atlas.2024-05-30+json",
           "Content-Type": "application/vnd.atlas.2024-05-30+json"}

# ---------------------------------------------------------------------------
# 1a. Time-series collections (must be created before any data inserts)
# ---------------------------------------------------------------------------
TIMESERIES = {
    "weather_observations": {
        "timeseries": {"timeField": "ts", "metaField": "location_id", "granularity": "minutes"},
        "expireAfterSeconds": 60 * 60 * 24 * 30,
    },
    "telemetry": {
        "timeseries": {"timeField": "ts", "metaField": "drone_id", "granularity": "seconds"},
        "expireAfterSeconds": 60 * 60 * 24 * 7,
    },
}

async def ensure_timeseries() -> None:
    existing = set(await db.list_collection_names())
    for name, cfg in TIMESERIES.items():
        if name in existing:
            print(f"  • {name} time-series exists")
            continue
        await db.create_collection(name, **cfg)
        print(f"  ✓ created time-series {name}")

# ---------------------------------------------------------------------------
# 1b. B-tree / 2dsphere indexes (driver, idempotent)
# ---------------------------------------------------------------------------
DRIVER_INDEXES = {
    "facilities": [
        ([("location", "2dsphere")], {"name": "loc_2dsphere"}),
        ([("name", 1)],               {"name": "name_1", "unique": True}),
        ([("region", 1), ("type", 1)],{"name": "region_type_1"}),
        ([("capabilities", 1)],       {"name": "capabilities_multikey"}),
    ],
    "no_fly_zones": [
        ([("geometry", "2dsphere")],                       {"name": "nfz_geo"}),
        ([("effective_from", 1), ("effective_to", 1)],     {"name": "nfz_window"}),
        ([("country", 1), ("severity", -1)],               {"name": "nfz_country_severity"}),
        ([("source", 1)],                                  {"name": "nfz_source"}),
    ],
    "weather_observations": [
        ([("location_id", 1), ("ts", -1)], {"name": "loc_ts"}),
        ([("flyable", 1), ("ts", -1)],     {"name": "flyable_ts"}),
    ],
    "drones": [
        ([("position", "2dsphere")],     {"name": "drone_pos_2dsphere"}),
        ([("status", 1)],                {"name": "drone_status"}),
        ([("current_mission_id", 1)],    {"name": "drone_current_mission"}),
    ],
    "deliveries": [
        ([("status",1),("priority",-1),("requested_at",1)], {"name": "queue_hot"}),
        ([("assigned_drone",1)], {"name": "by_drone"}),
        ([("mission_id",1)],     {"name": "by_mission"}),
        ([("destination_id",1)], {"name": "by_destination"}),
    ],
    "missions": [
        ([("status",1),("started_at",-1)],   {"name": "status_started"}),
        ([("drone_id",1),("started_at",-1)], {"name": "by_drone_time"}),
        ([("delivery_ids",1)],               {"name": "by_delivery"}),
        ([("completed_at",-1)],              {"name": "recency"}),
    ],
    "telemetry": [
        ([("drone_id",1),("ts",-1)],        {"name": "drone_ts"}),
        ([("anomaly_score",-1),("ts",-1)],  {"name": "anomaly_ts"}),
    ],
    "flight_logs": [
        ([("drone_id",1),("ts",-1)],   {"name":"drone_ts"}),
        ([("mission_id",1),("ts",1)],  {"name":"mission_ts"}),
        ([("event",1),("ts",-1)],      {"name":"event_ts"}),
    ],
    "audit_trail": [
        ([("seq",1)], {"name":"seq", "unique": True}),
        ([("subject_type",1),("subject_id",1),("ts",-1)], {"name":"subj"}),
        ([("ts",-1)], {"name":"ts"}),
    ],
    "mission_memory": [
        ([("kind",1),("created_at",-1)], {"name":"kind_time"}),
        ([("metadata.region",1)],        {"name":"region"}),
        ([("metadata.tags",1)],          {"name":"tags_multikey"}),
        ([("source_collection",1),("source_id",1)], {"name":"provenance"}),
    ],
    "regulations": [
        ([("code",1)], {"name":"code","unique":True}),
        ([("country",1),("effective_from",-1)], {"name":"country_time"}),
    ],
    "chat_sessions":[ ([("operator_id",1),("last_active_at",-1)], {"name":"op_time"}) ],
    "chat_messages":[
        ([("session_id",1),("ts",1)],  {"name":"sess_ts"}),
        ([("operator_id",1),("ts",-1)],{"name":"op_recent"}),
    ],
    "users":     [([("email",1)], {"name":"email_unique","unique":True})],
    "api_keys":  [([("user_id",1)], {"name":"by_user"}),
                  ([("hashed_key",1)], {"name":"hashed_key_unique","unique":True})],
    "operators": [([("user_id",1)], {"name":"by_user","unique":True}),
                  ([("region",1),("on_shift",1)], {"name":"shift_lookup"})],
    "synthetic_emergencies": [
        ([("ts",1)], {"name":"ts"}),
        ([("location_id",1),("ts",1)], {"name":"loc_ts"}),
        ([("emergency_type",1),("severity",-1)], {"name":"type_sev"}),
    ],
    "agent_skills": [
        ([("agent",1)], {"name":"agent_unique","unique":True}),
        ([("enabled",1),("reliability_score",-1)], {"name":"best_first"}),
    ],
    "agent_messages": [
        ([("mission_id",1),("ts",1)], {"name":"mission_ts"}),
        ([("trace_id",1),("ts",1)],   {"name":"trace_ts"}),
        ([("from_agent",1),("to_agent",1),("ts",-1)], {"name":"dyad"}),
    ],
    "tool_call_log": [
        ([("idempotency_key",1)], {"name":"idem_unique","unique":True}),
        ([("agent",1),("tool",1),("started_at",-1)], {"name":"agent_tool_time"}),
        ([("status",1),("started_at",-1)], {"name":"status_time"}),
    ],
    "traces": [
        ([("trace_id",1),("start_ts",1)], {"name":"trace_time"}),
        ([("service",1),("name",1),("start_ts",-1)], {"name":"svc_name"}),
    ],
    "reflection_eval": [
        ([("take",1)], {"name":"take_unique","unique":True}),
        ([("ts",-1)], {"name":"ts_recent"}),
    ],
    "documents":      [([("sha256",1)], {"name":"sha_unique","unique":True})],
    "document_chunks":[
        ([("document_id",1),("ordinal",1)], {"name":"doc_ord","unique":True}),
        ([("chunk_strategy",1)], {"name":"strategy"}),
    ],
}

async def ensure_driver_indexes() -> None:
    for coll, spec in DRIVER_INDEXES.items():
        existing = await db[coll].index_information()
        for keys, opts in spec:
            name = opts.get("name") or "_".join(f"{k}_{v}" for k,v in keys)
            if name in existing:
                print(f"  • {coll}.{name} exists")
                continue
            await db[coll].create_index(keys, **opts)
            print(f"  ✓ {coll}.{name}")

# ---------------------------------------------------------------------------
# 1c. Atlas Search & Vector Search definitions (Admin API)
# ---------------------------------------------------------------------------
SEARCH_INDEXES: list[dict] = [
    {"collectionName":"facilities","name":"facilities_search","database":DB_NAME,
     "definition":{"mappings":{"dynamic":False,"fields":{
       "name":{"type":"string","analyzer":"lucene.standard"},
       "address":{"type":"string","analyzer":"lucene.standard"},
       "region":{"type":"stringFacet"},
       "type":{"type":"stringFacet"},
       "capabilities":{"type":"string","analyzer":"lucene.keyword"},
       "location":{"type":"geo"}
     }}}},
    {"collectionName":"chat_messages","name":"chat_messages_search","database":DB_NAME,
     "definition":{"mappings":{"dynamic":False,"fields":{
       "content":{"type":"string","analyzer":"lucene.standard"},
       "operator_id":{"type":"stringFacet"},
       "role":{"type":"stringFacet"},
       "ts":{"type":"date"}
     }}}},
    {"collectionName":"document_chunks","name":"document_chunks_search","database":DB_NAME,
     "definition":{"mappings":{"dynamic":False,"fields":{
       "text":{"type":"string","analyzer":"lucene.english"},
       "metadata.tags":{"type":"string","analyzer":"lucene.keyword"}
     }}}},
]

VECTOR_INDEXES: list[dict] = [
    {"collectionName":"mission_memory","name":"mission_memory_vec","database":DB_NAME,
     "type":"vectorSearch",
     "definition":{"fields":[
       {"type":"vector","path":"embedding","numDimensions":1024,"similarity":"cosine"},
       {"type":"filter","path":"kind"},
       {"type":"filter","path":"metadata.region"},
       {"type":"filter","path":"metadata.weather_class"},
       {"type":"filter","path":"metadata.success"},
       {"type":"filter","path":"embedding_model"},
     ]}},
    {"collectionName":"document_chunks","name":"document_chunks_vec","database":DB_NAME,
     "type":"vectorSearch",
     "definition":{"fields":[
       {"type":"vector","path":"embedding","numDimensions":1024,"similarity":"cosine"},
       {"type":"filter","path":"chunk_strategy"},
       {"type":"filter","path":"embedding_model"},
       {"type":"filter","path":"document_id"},
     ]}},
    {"collectionName":"agent_skills","name":"agent_skills_vec","database":DB_NAME,
     "type":"vectorSearch",
     "definition":{"fields":[
       {"type":"vector","path":"embedding","numDimensions":1024,"similarity":"cosine"},
       {"type":"filter","path":"enabled"},
       {"type":"filter","path":"agent"},
     ]}},
]

async def list_search_indexes(http: httpx.AsyncClient, coll: str) -> list[dict]:
    url = f"{ATLAS_BASE}/groups/{ATLAS_GROUP_ID}/clusters/{ATLAS_CLUSTER}/search/indexes/{DB_NAME}/{coll}"
    r = await http.get(url, headers=HEADERS)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json().get("results", r.json()) if isinstance(r.json(), dict) else r.json()

async def create_search_index(http: httpx.AsyncClient, spec: dict) -> None:
    coll = spec["collectionName"]
    existing = await list_search_indexes(http, coll)
    if any(e.get("name") == spec["name"] for e in existing):
        print(f"  • {coll}.{spec['name']} (search) exists")
        return
    url = f"{ATLAS_BASE}/groups/{ATLAS_GROUP_ID}/clusters/{ATLAS_CLUSTER}/search/indexes"
    body = {
        "collectionName": coll,
        "database": spec["database"],
        "name": spec["name"],
        **({"type": spec["type"]} if "type" in spec else {}),
        "definition": spec["definition"],
    }
    r = await http.post(url, headers=HEADERS, content=json.dumps(body))
    if r.status_code >= 300:
        print(f"  ✗ {coll}.{spec['name']} → {r.status_code} {r.text[:200]}")
        r.raise_for_status()
    print(f"  ✓ {coll}.{spec['name']} (search/vector) created")

async def ensure_search_indexes() -> None:
    auth = DigestAuth(ATLAS_PUBLIC_KEY, ATLAS_PRIVATE_KEY)
    async with httpx.AsyncClient(auth=auth, timeout=30) as http:
        for spec in SEARCH_INDEXES + VECTOR_INDEXES:
            await create_search_index(http, spec)

# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
async def main():
    print("→ time-series collections")
    await ensure_timeseries()
    print("→ driver indexes")
    await ensure_driver_indexes()
    print("→ Atlas Search + Vector Search indexes")
    await ensure_search_indexes()
    print("✓ create_indexes complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
```

---

## 2 · `seeds/seed_facilities.py` — 489 facilities + 9 hardcoded

Preserves the **exact** flat-earth projection logic from the original `backend/facilities.py`. Loads the xlsx, merges in the nine hardcoded `LOCATIONS` from `config.py`, computes `airsim_xy` relative to Depot, writes with **upsert** so re-runs are idempotent.

```python
# seeds/seed_facilities.py
"""Load facilities.xlsx + 9 config locations into facilities collection.

Run: uv run python -m seeds.seed_facilities
"""
from __future__ import annotations
import asyncio, os, sys
from typing import Any
import openpyxl
from pymongo import UpdateOne, GEOSPHERE
from ._common import db, latlon_to_xy, utcnow

XLSX_PATH = os.getenv(
    "FACILITIES_XLSX",
    os.path.join(os.path.dirname(__file__), "..", "DroneFleet", "data", "facilities.xlsx"),
)

# Hardcoded from original Droran/config.py LOCATIONS (verbatim).
HARDCODED_LOCATIONS: dict[str, dict[str, Any]] = {
    "Depot":         {"x":0,"y":0,"z":-30,"lat":51.5074,"lon":-0.1278,"description":"Main drone depot / base station","type":"depot"},
    "Clinic A":      {"x":100,"y":50,"z":-30,"lat":51.5124,"lon":-0.1200,"description":"General medical clinic","type":"clinic"},
    "Clinic B":      {"x":-50,"y":150,"z":-30,"lat":51.5174,"lon":-0.1350,"description":"Emergency care facility","type":"clinic"},
    "Clinic C":      {"x":200,"y":-30,"z":-30,"lat":51.5044,"lon":-0.1100,"description":"Rural health outpost","type":"clinic"},
    "Clinic D":      {"x":-100,"y":-80,"z":-30,"lat":51.5000,"lon":-0.1400,"description":"Disaster relief camp","type":"clinic"},
    "Royal London":  {"x":100,"y":50,"z":-30,"lat":51.5185,"lon":-0.0590,"description":"Royal London Hospital — Major trauma centre","type":"hospital","capabilities":["trauma","cardiac","blood_bank"]},
    "Homerton":      {"x":-50,"y":150,"z":-30,"lat":51.5468,"lon":-0.0456,"description":"Homerton Hospital — Urgent care facility","type":"hospital","capabilities":["urgent_care"]},
    "Newham General":{"x":200,"y":-30,"z":-30,"lat":51.5155,"lon":0.0285,"description":"Newham General Hospital — Trauma kit resupply","type":"hospital","capabilities":["trauma"]},
    "Whipps Cross":  {"x":-100,"y":-80,"z":-30,"lat":51.5690,"lon":0.0066,"description":"Whipps Cross Hospital — Cardiac unit","type":"hospital","capabilities":["cardiac"]},
}

DEPOT_LAT = HARDCODED_LOCATIONS["Depot"]["lat"]
DEPOT_LON = HARDCODED_LOCATIONS["Depot"]["lon"]

def _normalize_type(t: str | None) -> str:
    t = (t or "").strip().lower()
    if "hospital" in t: return "hospital"
    if "clinic"   in t: return "clinic"
    if "depot"    in t or "warehouse" in t: return "depot"
    if "camp"     in t or "field" in t: return "field_camp"
    return "clinic"

def _load_xlsx_rows(path: str) -> list[dict]:
    if not os.path.exists(path):
        print(f"  ! facilities.xlsx not found at {path}; continuing with config-only seed")
        return []
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    headers: list[str] | None = None
    rows: list[dict] = []
    for row in ws.iter_rows(values_only=True):
        if headers is None:
            headers = [str(h).strip().lower().replace(" ", "_") if h else "" for h in row]
            continue
        rec = dict(zip(headers, row))
        try:
            lat = float(rec.get("latitude") or 0)
            lon = float(rec.get("longitude") or 0)
        except (TypeError, ValueError):
            continue
        if lat == 0 and lon == 0:
            continue
        name = (rec.get("name") or "").strip()
        if not name:
            continue
        rows.append({
            "name":         name,
            "type":         _normalize_type(rec.get("type")),
            "region":       (rec.get("region") or "").strip() or None,
            "address":      (rec.get("physical_address") or "").strip() or None,
            "phone":        (rec.get("phone_number") or "").strip() or None,
            "email":        (rec.get("email") or "").strip() or None,
            "website":      (rec.get("website") or "").strip() or None,
            "lat": lat, "lon": lon,
        })
    wb.close()
    return rows

def _to_doc(name: str, *, lat: float, lon: float, type_: str, address: str | None = None,
            region: str | None = None, phone: str | None = None, email: str | None = None,
            website: str | None = None, capabilities: list[str] | None = None,
            description: str | None = None, source: str = "xlsx") -> dict:
    x, y = latlon_to_xy(lat, lon, DEPOT_LAT, DEPOT_LON)
    return {
        "name": name,
        "type": type_,
        "region": region,
        "address": address,
        "phone": phone,
        "email": email,
        "website": website,
        "capabilities": capabilities or [],
        "location": {"type": "Point", "coordinates": [lon, lat]},
        "airsim_xy": {"x": x, "y": y, "z": -30.0},
        "description": description,
        "source": source,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }

async def main() -> None:
    ops: list[UpdateOne] = []

    # 1. Hardcoded 9
    for name, c in HARDCODED_LOCATIONS.items():
        doc = _to_doc(
            name, lat=c["lat"], lon=c["lon"],
            type_=c.get("type","clinic"),
            description=c.get("description"),
            capabilities=c.get("capabilities", []),
            source="config",
        )
        # Preserve original AirSim x/y if explicitly hardcoded:
        doc["airsim_xy"] = {"x": float(c["x"]), "y": float(c["y"]), "z": float(c["z"])}
        ops.append(UpdateOne({"name": name}, {"$set": doc}, upsert=True))

    # 2. xlsx (skip rows whose name collides with a hardcoded one)
    rows = _load_xlsx_rows(XLSX_PATH)
    for r in rows:
        if r["name"] in HARDCODED_LOCATIONS:
            continue
        doc = _to_doc(r["name"], lat=r["lat"], lon=r["lon"], type_=r["type"],
                      address=r.get("address"), region=r.get("region"),
                      phone=r.get("phone"), email=r.get("email"), website=r.get("website"),
                      source="xlsx")
        ops.append(UpdateOne({"name": r["name"]}, {"$set": doc}, upsert=True))

    if not ops:
        print("  ! nothing to seed")
        return

    res = await db.facilities.bulk_write(ops, ordered=False)
    print(f"  ✓ upserted {res.upserted_count}, modified {res.modified_count}, "
          f"matched {res.matched_count}, total ops={len(ops)}")

    # Ensure 2dsphere exists (no-op if already present from create_indexes)
    await db.facilities.create_index([("location", GEOSPHERE)], name="loc_2dsphere")
    print(f"  ✓ facilities total = {await db.facilities.count_documents({})}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
```

---

## 3 · `seeds/seed_no_fly_zones.py` — FAA + PDOK + UK CAA

```python
# seeds/seed_no_fly_zones.py
"""Seed canonical no-fly zones (FAA, PDOK, UK CAA + the original config polygons).

Run: uv run python -m seeds.seed_no_fly_zones
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from pymongo import UpdateOne, GEOSPHERE
from ._common import db, utcnow

ZONES = [
    # --- FAA P-56A — Washington DC (White House / Capitol) ---
    {
        "name": "FAA P-56A Washington DC",
        "source": "FAA", "country": "US", "severity": "prohibited",
        "altitude_floor_m": 0.0, "altitude_ceiling_m": 5486.0,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-77.0470, 38.8870],[-77.0470, 38.9080],
                [-77.0220, 38.9080],[-77.0220, 38.8870],
                [-77.0470, 38.8870],
            ]],
        },
        "metadata": {"notes": "Prohibited area around White House & Capitol"},
    },
    # --- PDOK — Schiphol (NL) inner CTR ---
    {
        "name": "PDOK Schiphol CTR Inner",
        "source": "PDOK", "country": "NL", "severity": "prohibited",
        "altitude_floor_m": 0.0, "altitude_ceiling_m": 914.0,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [4.7000, 52.2700],[4.7000, 52.3500],
                [4.8200, 52.3500],[4.8200, 52.2700],
                [4.7000, 52.2700],
            ]],
        },
        "metadata": {"icao": "EHAM"},
    },
    # --- UK CAA — Heathrow CTR ---
    {
        "name": "UK CAA Heathrow CTR",
        "source": "UK_CAA", "country": "GB", "severity": "prohibited",
        "altitude_floor_m": 0.0, "altitude_ceiling_m": 762.0,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-0.4543, 51.4500],[-0.4543, 51.4900],
                [-0.4100, 51.4900],[-0.4100, 51.4500],
                [-0.4543, 51.4500],
            ]],
        },
        "metadata": {"icao": "EGLL"},
    },
    # --- UK CAA — Military Zone Alpha (from original config.py) ---
    {
        "name": "Military Zone Alpha",
        "source": "UK_CAA", "country": "GB", "severity": "restricted",
        "altitude_floor_m": 0.0, "altitude_ceiling_m": 1500.0,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-0.132, 51.513],[-0.132, 51.516],
                [-0.126, 51.516],[-0.126, 51.513],
                [-0.132, 51.513],
            ]],
        },
        "metadata": {"origin": "config.NO_FLY_ZONES"},
    },
    # --- UK CAA — Airport Exclusion (from original config.py) ---
    {
        "name": "Airport Exclusion",
        "source": "UK_CAA", "country": "GB", "severity": "restricted",
        "altitude_floor_m": 0.0, "altitude_ceiling_m": 1200.0,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-0.115, 51.503],[-0.115, 51.506],
                [-0.108, 51.506],[-0.108, 51.503],
                [-0.115, 51.503],
            ]],
        },
        "metadata": {"origin": "config.NO_FLY_ZONES"},
    },
]

async def main() -> None:
    base_from = datetime(2020, 1, 1, tzinfo=timezone.utc)
    ops = []
    for z in ZONES:
        z = {**z, "effective_from": base_from, "effective_to": None, "created_at": utcnow()}
        ops.append(UpdateOne({"name": z["name"]}, {"$set": z}, upsert=True))
    res = await db.no_fly_zones.bulk_write(ops, ordered=False)
    await db.no_fly_zones.create_index([("geometry", GEOSPHERE)], name="nfz_geo")
    print(f"  ✓ no_fly_zones upserted={res.upserted_count} modified={res.modified_count}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 4 · `seeds/seed_regulations.py` — chunked + Voyage-embedded

Writes the full canonical record to `regulations` and the chunked + embedded text to `mission_memory` (`kind:"regulation"`) so the RAG agent can cite it directly. We use **markdown-aware** chunking for shorter profiles and **late-context** chunking via `voyage-context-3` for the bulky CAA notes (per the policy table in `03-mongodb-vector-rag.md` §2.5).

```python
# seeds/seed_regulations.py
"""Seed UK CAA, FAA Part 107, EASA Open A1/A2/A3 — text + embeddings.

Run: uv run python -m seeds.seed_regulations
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from pymongo import UpdateOne
from ._common import db, utcnow, sha256_text
# These two helpers come from rag/* — re-export here for convenience.
from rag.embedder import Embedder
from rag.chunkers.markdown import chunk_markdown
from rag.chunkers.late import chunk_late_context

PROFILES = [
    {
        "code": "UK_CAA",
        "country": "GB",
        "title": "UK CAA Article 16 / CAP 722 — Open Category",
        "version": "2024.10",
        "max_altitude_m": 120.0, "bvlos_allowed": False,
        "night_allowed": True, "over_people_allowed": False,
        "max_takeoff_mass_kg": 25.0,
        "notes_md": """\
# UK CAA Open Category

## Maximum altitude
Operations in the Open Category must remain at or below **120 m (400 ft) AGL** measured from the closest point on the surface of the earth.

## Distance from people
- A1 sub-category: may overfly uninvolved people (with C0 / C1 mass class).
- A2: 30 m horizontal from uninvolved people, 5 m in low-speed mode.
- A3: 150 m from residential, commercial, industrial, recreational areas.

## Night flight
Night flight is permitted provided the aircraft is fitted with a flashing **green** light visible at all azimuths.

## BVLOS
Beyond Visual Line Of Sight is **not** permitted in the Open Category. A Specific Category Operational Authorisation is required.

## Mandatory carriage
- Operator ID (visible on aircraft).
- Pilot competence: A2 CofC for sub-category A2.

## Reporting
Accidents and serious incidents must be reported to the CAA via Mandatory Occurrence Reporting (MOR).
""",
        "chunker": "late_context",
    },
    {
        "code": "FAA_PART_107",
        "country": "US",
        "title": "FAA 14 CFR Part 107 — Small UAS Rule",
        "version": "2024.04",
        "max_altitude_m": 121.92,  # 400 ft
        "bvlos_allowed": False, "night_allowed": True, "over_people_allowed": False,
        "max_takeoff_mass_kg": 24.95,
        "notes_md": """\
# FAA Part 107 — Small UAS

## Maximum altitude
**400 ft AGL** (or within 400 ft of a structure).

## Speed
Maximum **100 mph (87 kts)** ground speed.

## Visual Line of Sight
The Remote Pilot in Command (RPIC) and any visual observer must keep the UAS within unaided VLOS.

## Night operations
Permitted under §107.29 with anti-collision lighting visible for **3 statute miles**, after appropriate training.

## Operations over people
Permitted under §107.39 only for Category 1–4 aircraft meeting the relevant conditions.

## Airspace
Class B/C/D/E surface requires LAANC or written ATC authorisation. Class G permitted without authorisation.

## Remote ID
All Part-107 operations require Remote ID (broadcast or FAA-Recognized Identification Area).
""",
        "chunker": "markdown_recursive",
    },
    {
        "code": "EASA_OPEN_A1",
        "country": "EU",
        "title": "EASA Open Category — A1 (Fly over people)",
        "version": "2024.06",
        "max_altitude_m": 120.0, "bvlos_allowed": False,
        "night_allowed": True, "over_people_allowed": True,
        "max_takeoff_mass_kg": 0.9,
        "notes_md": """\
# EASA Open A1

## Mass
< 250 g (C0) or < 900 g (C1) class-marked.

## Overflight
A1 may overfly uninvolved persons but must not overfly **assemblies of people**.

## Altitude
≤ 120 m AGL.
""",
        "chunker": "markdown_recursive",
    },
    {
        "code": "EASA_OPEN_A2",
        "country": "EU",
        "title": "EASA Open Category — A2 (Close to people)",
        "version": "2024.06",
        "max_altitude_m": 120.0, "bvlos_allowed": False,
        "night_allowed": True, "over_people_allowed": False,
        "max_takeoff_mass_kg": 4.0,
        "notes_md": """\
# EASA Open A2

## Mass
< 4 kg (C2 class).

## Distance
Minimum **30 m horizontal** from uninvolved people, reducible to **5 m** in low-speed mode (≤ 3 m/s).

## Pilot competence
A2 Certificate of Competency required.
""",
        "chunker": "markdown_recursive",
    },
    {
        "code": "EASA_OPEN_A3",
        "country": "EU",
        "title": "EASA Open Category — A3 (Far from people)",
        "version": "2024.06",
        "max_altitude_m": 120.0, "bvlos_allowed": False,
        "night_allowed": True, "over_people_allowed": False,
        "max_takeoff_mass_kg": 25.0,
        "notes_md": """\
# EASA Open A3

## Mass
< 25 kg.

## Distance
≥ **150 m** from residential, commercial, industrial, recreational areas.
No uninvolved persons within range of operation.
""",
        "chunker": "markdown_recursive",
    },
]

async def _embed_and_persist_chunks(profile: dict) -> int:
    text  = profile["notes_md"]
    code  = profile["code"]
    if profile["chunker"] == "late_context":
        chunks = await chunk_late_context(text)   # already includes embeddings
        embeddings = [c["embedding"] for c in chunks]
        chunk_texts = [c["text"] for c in chunks]
        chunk_strategy = "late_context"
        embedding_model = "voyage-context-3"
    else:
        sections = chunk_markdown(text, target_tokens=480)
        chunk_texts = [s["text"] for s in sections]
        embeddings, embedding_model = await Embedder.embed_for("mission_memory", chunk_texts)
        chunk_strategy = "markdown_recursive"

    ops = []
    for i, (t, e) in enumerate(zip(chunk_texts, embeddings)):
        oid = f"reg::{code}::{i:03d}"
        ops.append(UpdateOne(
            {"_id": oid},
            {"$set": {
                "_id": oid,
                "kind": "regulation",
                "title": f"{profile['title']} — chunk {i}",
                "text": t,
                "embedding": e,
                "embedding_model": embedding_model,
                "metadata": {
                    "region": profile["country"],
                    "tags": [code, "regulation", chunk_strategy],
                },
                "source_collection": "regulations",
                "source_id": code,
                "created_at": utcnow(),
                "use_count": 0,
                "score_ema": 0.5,
            }},
            upsert=True,
        ))
    res = await db.mission_memory.bulk_write(ops, ordered=False)
    return res.upserted_count + res.modified_count

async def main() -> None:
    base_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
    reg_ops = []
    for p in PROFILES:
        reg_ops.append(UpdateOne(
            {"code": p["code"]},
            {"$set": {
                **{k: v for k, v in p.items() if k not in ("chunker",)},
                "effective_from": base_from,
                "effective_to": None,
            }},
            upsert=True,
        ))
    res = await db.regulations.bulk_write(reg_ops, ordered=False)
    print(f"  ✓ regulations upserted={res.upserted_count} modified={res.modified_count}")

    total_chunks = 0
    for p in PROFILES:
        n = await _embed_and_persist_chunks(p)
        print(f"    • {p['code']}: {n} chunks embedded ({p['chunker']})")
        total_chunks += n
    print(f"  ✓ mission_memory regulation chunks total={total_chunks}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 5 · `seeds/seed_synthetic_emergencies.py` — 44 118 rows in batches of 1000

Stream-loads the CSV; never holds the full file in memory; uses `bulk_write` with `UpdateOne(upsert=True)` keyed on `(ts, location_id, emergency_type)` so re-runs are no-ops.

```python
# seeds/seed_synthetic_emergencies.py
"""Stream-load data/synthetic_emergencies.csv (44,118 rows) into MongoDB.

Run: uv run python -m seeds.seed_synthetic_emergencies
"""
from __future__ import annotations
import asyncio, csv, os, sys
from datetime import datetime, timezone
from pymongo import UpdateOne
from ._common import db

CSV_PATH = os.getenv(
    "SYNTHETIC_EMERGENCIES_CSV",
    os.path.join(os.path.dirname(__file__), "..", "DroneFleet", "data", "synthetic_emergencies.csv"),
)

BATCH = 1000

def _row_to_doc(row: dict) -> dict:
    ts = datetime.fromisoformat(row["timestamp"].replace(" ", "T")).replace(tzinfo=timezone.utc)
    return {
        "ts": ts,
        "location_id": row["location_id"],
        "location_lat": float(row["location_lat"]),
        "location_lon": float(row["location_lon"]),
        "emergency_type": row["emergency_type"],
        "severity": int(row["severity"]),
        "temperature_c": float(row["temperature_c"]),
        "weather_condition": row["weather_condition"],
        "is_holiday": row["is_holiday"] in ("1","true","True"),
        "is_event":  row["is_event"]  in ("1","true","True"),
        "hour_of_day": int(row["hour_of_day"]),
        "day_of_week": int(row["day_of_week"]),
    }

async def _flush(ops: list[UpdateOne]) -> tuple[int,int]:
    if not ops: return 0,0
    res = await db.synthetic_emergencies.bulk_write(ops, ordered=False)
    return res.upserted_count, res.modified_count

async def main() -> None:
    if not os.path.exists(CSV_PATH):
        print(f"  ✗ csv missing at {CSV_PATH}", file=sys.stderr); sys.exit(1)

    total_rows = 0; up = 0; mod = 0
    ops: list[UpdateOne] = []
    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            doc = _row_to_doc(row)
            key = {"ts": doc["ts"], "location_id": doc["location_id"],
                   "emergency_type": doc["emergency_type"]}
            ops.append(UpdateOne(key, {"$set": doc}, upsert=True))
            total_rows += 1
            if len(ops) >= BATCH:
                u, m = await _flush(ops); up += u; mod += m; ops = []
                if total_rows % 10_000 == 0:
                    print(f"    • {total_rows:>6} rows processed (up={up} mod={mod})")
        if ops:
            u, m = await _flush(ops); up += u; mod += m
    print(f"  ✓ rows={total_rows} upserted={up} modified={mod}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 6 · `seeds/seed_agent_skills.py` — capability vector for peer discovery

Every agent advertises a capability paragraph + Voyage embedding. The SupervisorAgent later does `$vectorSearch` on this to discover peers at runtime.

```python
# seeds/seed_agent_skills.py
"""Register every agent + capability text + Voyage embedding.

Run: uv run python -m seeds.seed_agent_skills
"""
from __future__ import annotations
import asyncio
from pymongo import UpdateOne
from ._common import db, utcnow
from rag.embedder import Embedder

SKILLS = [
    ("SupervisorAgent",
     "Top-level orchestrator: decomposes operator requests into sub-tasks, discovers peer agents via vector search, dispatches via the A2A protocol, and aggregates responses with a critic loop."),
    ("RoutePlannerAgent",
     "Computes minimum-cost flight paths under battery, payload, weather, and no-fly-zone constraints using Google OR-Tools VRP. Reads facilities, no_fly_zones, drones, weather_observations."),
    ("ReplannerAgent",
     "Recomputes a safe route mid-flight when weather, no-fly zones, or detected obstacles invalidate the current plan. Considers battery, payload weight, and operator corridor preferences."),
    ("WeatherAgent",
     "Fuses live OpenWeather/MetOffice readings with stored time-series weather to score flyability per corridor; raises abort/reroute events when wind, gust, precip, or visibility cross thresholds."),
    ("GeofenceAgent",
     "Validates routes against active no-fly polygons (FAA, PDOK, UK CAA, dynamic TFRs) using $geoIntersects."),
    ("VisionAgent",
     "Runs onboard CV inference on live camera frames to detect obstacles (cranes, birds, structures); writes obstacles into the mission and stores frames to GridFS."),
    ("PayloadAgent",
     "Verifies cold-chain integrity for refrigerated supplies; monitors cargo_temperature_c; aborts if temperature breaches threshold."),
    ("NarratorAgent",
     "Streams natural-language mission narration to the operator over LiveKit + ElevenLabs; explains every reroute, obstacle, and decision in real time."),
    ("DeliverySchedulerAgent",
     "Maintains the priority queue of pending deliveries; assigns drones; reacts to status transitions in deliveries via Change Streams."),
    ("ReflectionAgent",
     "Post-mission analyser: reads missions, telemetry, flight_logs; writes structured lessons + embeddings to mission_memory; updates agent_skills.reliability_score (EMA)."),
    ("RetrievalCriticAgent",
     "Judges whether retrieved RAG snippets actually answer the operator's query; triggers expand_radius / drop_filters / web_fallback actions in the adaptive retrieval loop."),
    ("AnomalyDetectorAgent",
     "Streams telemetry, scores anomalies (statistical + isolation-forest), raises Replan events when anomaly_score > 0.7."),
    ("AuditAgent",
     "Hash-chained chain-of-custody writer; idempotent; renders compliance PDFs to GridFS."),
    ("DemandForecastAgent",
     "Reads synthetic_emergencies + historical missions to forecast per-region demand; produces preposition recommendations."),
    ("PrepositionAgent",
     "Acts on demand forecasts to relocate idle drones to high-demand depots in advance of expected emergencies."),
    ("FacilityIntelAgent",
     "Maintains free-form intel notes per facility (helipad rules, operating hours, lift access) and embeds them into mission_memory."),
    ("OperatorPrefAgent",
     "Learns operator preferences from observed overrides; promotes them into mission_memory as kind:operator_pref so future plans recall them."),
    ("VoiceCommandAgent",
     "Parses operator speech (Deepgram/Whisper) into structured intents; resolves ambiguous facility names via Atlas Search."),
]

async def main() -> None:
    texts = [t for _, t in SKILLS]
    embeddings, model = await Embedder.embed_for("agent_skills", texts)
    ops = []
    for (agent, text), emb in zip(SKILLS, embeddings):
        ops.append(UpdateOne(
            {"agent": agent},
            {"$set": {
                "agent": agent,
                "capability_text": text,
                "embedding": emb,
                "embedding_model": model,
                "tools": [],
                "cost_estimate_gbp_per_call": 0.0,
                "avg_latency_ms": 0.0,
                "reliability_score": 0.9,
                "version": "1.0.0",
                "enabled": True,
                "updated_at": utcnow(),
            }},
            upsert=True,
        ))
    res = await db.agent_skills.bulk_write(ops, ordered=False)
    print(f"  ✓ agent_skills upserted={res.upserted_count} modified={res.modified_count}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 7 · `seeds/seed_demo_memories.py` — 50 synthetic past-mission reflections

The demo's "encore" relies on retrieval surfacing **MED-0398**: a wind-shear failure on the west corridor at Royal London. Other 49 are varied lessons — battery margins, cold-chain saves, BVLOS regulation hits, etc. — to give the planner a believable history.

```python
# seeds/seed_demo_memories.py
"""Seed 50 synthetic past-mission reflections into mission_memory.

Run: uv run python -m seeds.seed_demo_memories
"""
from __future__ import annotations
import asyncio, random
from datetime import datetime, timedelta, timezone
from pymongo import UpdateOne
from ._common import db, utcnow
from rag.embedder import Embedder

random.seed(42)

BASE_DEMO = [
    {
        "mid": "MED-0398",
        "title": "Wind shear corridor west of Royal London — abort threshold too lax",
        "text": (
            "On MED-0398 we attempted approach to Royal London via the WEST corridor "
            "at 9.4 m/s mean wind, gusting 13.8 m/s. Drone1 lost ~7% extra battery in "
            "the final 800 m and had to hold at the Mile End waypoint. Outcome: aborted. "
            "Root cause: the wind-shear bubble between the canyon of office blocks east of "
            "Aldgate and Whitechapel is not modelled in METAR; gust factor exceeded 1.4. "
            "Lesson: when wind > 8 m/s and gust factor > 1.3, prefer the NORTH-EAST corridor "
            "via Bethnal Green and approach Royal London from Stepney Way."
        ),
        "region": "London", "weather_class": "wind", "success": False, "severity": "high",
        "lessons": [
            "Lower wind threshold from 12 m/s to 10 m/s on west-corridor approaches.",
            "Prefer NE corridor when gust factor > 1.4.",
            "Cache the canyon wind-shear hot-spot polygon as an internal NFZ advisory.",
        ],
        "tags": ["wind_shear","royal_london","west_corridor","abort"],
    },
    {
        "mid": "MED-0301",
        "title": "Cold-chain save by re-routing via Newham depot",
        "text": (
            "Insulin shipment to Newham General faced a 6-minute delay due to a TFR for a royal "
            "movement at City Airport. Cargo temperature was rising at 0.3 °C/min from a baseline "
            "of 4.2 °C. PayloadAgent triggered re-route via Newham Local Depot for a 90s ice-pack "
            "swap; total schedule slip 4 minutes; cold-chain preserved at 5.8 °C peak."
        ),
        "region": "London", "weather_class": "clear", "success": True, "severity": "medium",
        "lessons": [
            "When a delay would push cargo > 7°C, prefer a depot ice-pack swap over straight delivery.",
            "Cache active TFRs hourly so the planner sees them before takeoff."
        ],
        "tags": ["cold_chain","newham","tfr","insulin"],
    },
    {
        "mid": "MED-0245",
        "title": "Battery reserve lesson — 25% reserve not enough on Whipps Cross run in headwind",
        "text": (
            "Drone2 reached Whipps Cross with 23% battery against an 8 m/s headwind. Reserve policy "
            "of 20% RTB margin nearly breached. ReflectionAgent recommends 28% reserve when forecast "
            "headwind on return leg > 7 m/s."
        ),
        "region": "London", "weather_class": "wind", "success": True, "severity": "medium",
        "lessons": [
            "Increase RTB battery reserve to 28% when return-leg headwind > 7 m/s.",
        ],
        "tags": ["battery","whipps_cross","headwind"],
    },
]

WEATHER_CLASSES = ["clear","rain","wind","fog","storm","snow"]
REGIONS = ["London","Manchester","Birmingham","Leeds","Bristol"]
EMERGENCY_TYPES = ["respiratory","cardiac","trauma","obstetric","neurological","metabolic"]
DESTINATIONS = ["Royal London","Homerton","Newham General","Whipps Cross","Clinic A","Clinic B","Clinic C","Clinic D"]

def _synthetic_record(i: int) -> dict:
    success = random.random() > 0.32
    wx = random.choice(WEATHER_CLASSES)
    region = random.choice(REGIONS)
    dest = random.choice(DESTINATIONS)
    et = random.choice(EMERGENCY_TYPES)
    severity = random.choice(["low","medium","high"])
    days_ago = random.randint(2, 180)
    text = (
        f"Mission MED-{1000+i} delivered {et} supplies to {dest} ({region}). "
        f"Conditions: {wx}. Outcome: {'completed' if success else 'failed'}. "
        f"{'No reroutes.' if success else 'Aborted at final approach due to ' + wx + ' band exceeding tolerance.'}"
    )
    lessons = []
    if not success:
        if wx == "wind":
            lessons.append("Tighten wind threshold for low-altitude approach.")
        if wx == "storm":
            lessons.append("Add 10-minute wait-and-see policy for storm cells passing E.")
        if wx == "fog":
            lessons.append("Require thermal/IR camera enabled when visibility < 3 km.")
        lessons.append("Re-train the planner with updated abort policy.")
    return {
        "mid": f"MED-{1000+i}",
        "title": f"Synthetic — {dest} {wx} {'OK' if success else 'FAIL'}",
        "text": text,
        "region": region, "weather_class": wx,
        "success": success, "severity": severity,
        "lessons": lessons,
        "tags": [wx, dest.lower().replace(" ","_"), et, "synthetic"],
        "days_ago": days_ago,
    }

async def main() -> None:
    records = list(BASE_DEMO) + [_synthetic_record(i) for i in range(50 - len(BASE_DEMO))]
    texts = [r["text"] for r in records]
    embeddings, model = await Embedder.embed_for("mission_memory", texts)

    now = utcnow()
    ops = []
    for r, e in zip(records, embeddings):
        created = now - timedelta(days=r.get("days_ago", random.randint(2, 180)))
        oid = f"refl::{r['mid']}"
        ops.append(UpdateOne(
            {"_id": oid},
            {"$set": {
                "_id": oid,
                "kind": "reflection",
                "title": r["title"],
                "text": r["text"],
                "embedding": e,
                "embedding_model": model,
                "metadata": {
                    "region": r["region"],
                    "weather_class": r["weather_class"],
                    "success": r["success"],
                    "severity": r["severity"],
                    "lessons": r["lessons"],
                    "tags": r["tags"],
                },
                "source_collection": "missions",
                "source_id": r["mid"],
                "created_at": created,
                "use_count": 0,
                "score_ema": 0.5,
            }},
            upsert=True,
        ))
    res = await db.mission_memory.bulk_write(ops, ordered=False)
    print(f"  ✓ demo memories upserted={res.upserted_count} modified={res.modified_count}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 8 · `seeds/check_health.py` — pass/fail report

Verifies: connectivity, every collection exists, every expected index is present, the vector index is *queryable* (do a real `$vectorSearch` with a tiny vector and assert no error), time-series collections are time-series, and a sentinel mission_memory document round-trips.

```python
# seeds/check_health.py
"""Health check. Exits non-zero if any check fails.

Run: uv run python -m seeds.check_health
"""
from __future__ import annotations
import asyncio, sys
from ._common import db, client, DB_NAME

EXPECTED_COLLECTIONS = {
    "facilities","no_fly_zones","weather_observations","drones","deliveries","missions",
    "telemetry","flight_logs","audit_trail","mission_memory","regulations",
    "chat_sessions","chat_messages","users","api_keys","operators",
    "synthetic_emergencies","agent_skills","agent_messages","tool_call_log",
    "traces","reflection_eval","documents","document_chunks",
}

EXPECTED_INDEXES = {
    "facilities": {"loc_2dsphere","name_1"},
    "no_fly_zones": {"nfz_geo","nfz_window"},
    "drones": {"drone_pos_2dsphere","drone_status"},
    "deliveries": {"queue_hot"},
    "missions": {"status_started"},
    "audit_trail": {"seq"},
    "mission_memory": {"kind_time"},
    "agent_skills": {"agent_unique"},
}

REPORT = {"pass": [], "fail": []}

def _ok(msg): REPORT["pass"].append(msg); print(f"  ✓ {msg}")
def _bad(msg): REPORT["fail"].append(msg); print(f"  ✗ {msg}")

async def check_connectivity():
    info = await client.admin.command("ping")
    _ok(f"connected to MongoDB ({info.get('ok')})")

async def check_collections():
    have = set(await db.list_collection_names())
    missing = EXPECTED_COLLECTIONS - have
    if missing:
        _bad(f"missing collections: {sorted(missing)}")
    else:
        _ok(f"all {len(EXPECTED_COLLECTIONS)} collections present")

async def check_indexes():
    for coll, expected in EXPECTED_INDEXES.items():
        have = set((await db[coll].index_information()).keys())
        missing = expected - have
        if missing:
            _bad(f"{coll}: missing indexes {sorted(missing)}")
        else:
            _ok(f"{coll}: indexes ok")

async def check_timeseries():
    for name in ("weather_observations","telemetry"):
        info = await db.command("listCollections", filter={"name": name})
        c = info["cursor"]["firstBatch"]
        if not c:
            _bad(f"{name}: collection missing"); continue
        opts = c[0].get("options", {})
        if "timeseries" not in opts:
            _bad(f"{name}: not a time-series collection")
        else:
            _ok(f"{name}: time-series ok ({opts['timeseries']})")

async def check_vector_search():
    """Run a tiny $vectorSearch to confirm the index is queryable."""
    sample = await db.mission_memory.find_one({}, {"embedding": 1})
    if not sample or "embedding" not in sample:
        _bad("mission_memory: no documents to test vector search"); return
    try:
        cur = db.mission_memory.aggregate([
          {"$vectorSearch":{
            "index":"mission_memory_vec","path":"embedding",
            "queryVector": sample["embedding"], "numCandidates": 50, "limit": 1,
          }},
          {"$limit": 1},
        ])
        hits = [d async for d in cur]
        if hits:
            _ok("mission_memory_vec: queryable")
        else:
            _bad("mission_memory_vec: returned no hits even though docs exist")
    except Exception as e:
        _bad(f"mission_memory_vec: query failed → {e}")

async def main():
    await check_connectivity()
    await check_collections()
    await check_indexes()
    await check_timeseries()
    await check_vector_search()
    print()
    print(f"PASS: {len(REPORT['pass'])}   FAIL: {len(REPORT['fail'])}")
    if REPORT["fail"]:
        for m in REPORT["fail"]:
            print(f"  ! {m}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 9 · `seeds/run_all.py` — orchestrated bootstrap

```python
# seeds/run_all.py
"""Run every seed in the right order.  Idempotent.

Run: uv run python -m seeds.run_all
"""
import asyncio, time
from . import (
    create_indexes,
    seed_facilities,
    seed_no_fly_zones,
    seed_regulations,
    seed_synthetic_emergencies,
    seed_agent_skills,
    seed_demo_memories,
    check_health,
)

STEPS = [
    ("create_indexes",            create_indexes.main),
    ("seed_facilities",           seed_facilities.main),
    ("seed_no_fly_zones",         seed_no_fly_zones.main),
    ("seed_regulations",          seed_regulations.main),
    ("seed_synthetic_emergencies",seed_synthetic_emergencies.main),
    ("seed_agent_skills",         seed_agent_skills.main),
    ("seed_demo_memories",        seed_demo_memories.main),
    ("check_health",              check_health.main),
]

async def main():
    for name, fn in STEPS:
        print(f"\n=== {name} ===")
        t0 = time.time()
        await fn()
        print(f"=== {name}: {time.time()-t0:.1f}s ===")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 10 · `Makefile` — one-command target

```makefile
# Makefile
PY := uv run python

.PHONY: seed seed-indexes seed-facilities seed-nfz seed-regs seed-csv \
        seed-skills seed-memories check

seed:           ## End-to-end idempotent bootstrap
	$(PY) -m seeds.run_all

seed-indexes:   ; $(PY) -m seeds.create_indexes
seed-facilities:; $(PY) -m seeds.seed_facilities
seed-nfz:       ; $(PY) -m seeds.seed_no_fly_zones
seed-regs:      ; $(PY) -m seeds.seed_regulations
seed-csv:       ; $(PY) -m seeds.seed_synthetic_emergencies
seed-skills:    ; $(PY) -m seeds.seed_agent_skills
seed-memories:  ; $(PY) -m seeds.seed_demo_memories
check:          ; $(PY) -m seeds.check_health
```

Bring up an empty cluster, fill `.env`, then:

```bash
make seed
```

Expected on a clean run:

```
=== create_indexes ===
  ✓ created time-series weather_observations
  ✓ created time-series telemetry
  ✓ facilities.loc_2dsphere
  ✓ ...
  ✓ mission_memory_vec (search/vector) created
=== seed_facilities ===
  ✓ upserted 489+9, total = 498
=== seed_no_fly_zones ===
  ✓ no_fly_zones upserted=5
=== seed_regulations ===
  ✓ regulations upserted=5
    • UK_CAA: 12 chunks embedded (late_context)
    • FAA_PART_107: 7 chunks embedded (markdown_recursive)
    ...
=== seed_synthetic_emergencies ===
  ✓ rows=44118 upserted=44118
=== seed_agent_skills ===
  ✓ agent_skills upserted=18
=== seed_demo_memories ===
  ✓ demo memories upserted=50
=== check_health ===
  ✓ connected to MongoDB (1)
  ✓ all 24 collections present
  ✓ ... indexes ok ...
  ✓ weather_observations: time-series ok
  ✓ telemetry: time-series ok
  ✓ mission_memory_vec: queryable
PASS: 33   FAIL: 0
```

A second `make seed` run completes in seconds and reports `upserted=0 modified=0` everywhere; no duplicates are created.

---

## 11 · Notes on Atlas Search index propagation

Atlas Search and Vector Search indexes are created **asynchronously** in Atlas. The `create_indexes.py` script returns as soon as the Admin API accepts the spec, but the index may take 30–120 s to become queryable. `check_health.py` retries the `$vectorSearch` probe up to 6 times with exponential backoff:

```python
# add to check_vector_search()
import asyncio
for attempt in range(6):
    try:
        ...   # probe
        break
    except Exception as e:
        if attempt == 5: raise
        await asyncio.sleep(2 ** attempt)
```

In CI, set `WAIT_FOR_INDEXES=1` and add 60 s sleep between `seed_demo_memories` and `check_health` — vector index must be live before the queryability probe.

---

## 12 · What's deliberately *not* seeded

- **`drones`**: created at runtime by the simulator / PX4 SITL adapter; not part of static seed.
- **`deliveries`**, **`missions`**, **`telemetry`**, **`flight_logs`**, **`audit_trail`**: produced by live operations.
- **`weather_observations`**: streamed in by `WeatherIngestWorker`.
- **`chat_sessions`**, **`chat_messages`**: produced by operator interaction.
- **`langgraph_checkpoints`**: created by the LangGraph runtime via `MongoDBSaver.setup()`.

These are intentional — keeping the seed small ensures the demo *generates* its own evidence on first run, which is half the point of "self-evolving".

---

## 13 · CI integration

```yaml
# .github/workflows/seed-smoke.yml
name: seed-smoke
on: [push, pull_request]
jobs:
  seed:
    runs-on: ubuntu-latest
    env:
      MONGODB_URI: ${{ secrets.MONGODB_URI }}
      ATLAS_PUBLIC_KEY:  ${{ secrets.ATLAS_PUBLIC_KEY }}
      ATLAS_PRIVATE_KEY: ${{ secrets.ATLAS_PRIVATE_KEY }}
      ATLAS_GROUP_ID:    ${{ secrets.ATLAS_GROUP_ID }}
      ATLAS_CLUSTER_NAME:${{ secrets.ATLAS_CLUSTER_NAME }}
      VOYAGE_API_KEY:    ${{ secrets.VOYAGE_API_KEY }}
      OPENAI_API_KEY:    ${{ secrets.OPENAI_API_KEY }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: make seed
      - run: make check
```

Use a **separate Atlas database** for CI (`MONGODB_DB=droran_ci`) so PR runs never touch the demo cluster.

---

**End of `09-seed-and-data.md`.** With these scripts in place, a fresh clone goes from zero to fully-seeded, queryable, vector-search-ready in a single command. Combined with [`02-mongodb-data-model.md`](./02-mongodb-data-model.md) (schemas + change-stream wiring) and [`03-mongodb-vector-rag.md`](./03-mongodb-vector-rag.md) (agentic adaptive RAG), the MongoDB layer of the Droran rebuild is fully specified.
