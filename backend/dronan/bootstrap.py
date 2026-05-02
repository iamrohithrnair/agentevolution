"""Idempotent collection / validator / index bootstrap.

All `$jsonSchema` validators from `prompts/02-mongodb-data-model.md` and the
B-tree / 2dsphere / time-series index definitions from
`prompts/09-seed-and-data.md`. Tolerant of mongomock-motor (which silently
ignores `collMod` etc.) so unit tests can call ``ensure_indexes()`` against
an in-process database.
"""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import OperationFailure

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validators ($jsonSchema)
# ---------------------------------------------------------------------------
FACILITIES_VALIDATOR: dict[str, Any] = {
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
                        "minItems": 2,
                        "maxItems": 2,
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

NFZ_VALIDATOR: dict[str, Any] = {
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

DRONE_VALIDATOR: dict[str, Any] = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "status", "battery", "position"],
        "properties": {
            "_id": {"bsonType": "string"},
            "status": {
                "enum": [
                    "idle", "flying", "paused", "returning", "low_battery",
                    "charging", "fault", "offline",
                ]
            },
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

DELIVERY_VALIDATOR: dict[str, Any] = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "destination_id", "supply", "payload_weight_kg",
            "priority", "status", "requested_by", "requested_at",
        ],
        "properties": {
            "priority": {"enum": ["critical", "high", "normal", "low"]},
            "status": {"enum": [
                "pending", "assigned", "in_transit", "delivered", "failed", "cancelled"
            ]},
            "payload_weight_kg": {"bsonType": "double", "minimum": 0, "maximum": 25},
            "cold_chain_required": {"bsonType": "bool"},
        },
    }
}

MISSION_VALIDATOR: dict[str, Any] = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "drone_id", "status", "planned_route"],
        "properties": {
            "_id": {"bsonType": "string", "pattern": "^MED-[0-9]{4,}$"},
            "drone_id": {"bsonType": "string"},
            "status": {"enum": ["planned", "executing", "completed", "failed", "aborted"]},
            "planned_route": {"bsonType": "array", "minItems": 2},
        },
    }
}

MEMORY_VALIDATOR: dict[str, Any] = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["kind", "title", "text", "embedding", "embedding_model", "created_at"],
        "properties": {
            "kind": {"enum": [
                "reflection", "incident", "regulation",
                "facility_intel", "operator_pref", "skill",
            ]},
            # Allow 256 / 1024 / 2048 dims (Matryoshka)
            "embedding": {
                "bsonType": "array",
                "minItems": 256,
                "maxItems": 2048,
                "items": {"bsonType": "double"},
            },
            "embedding_model": {"bsonType": "string"},
            "use_count": {"bsonType": "int", "minimum": 0},
        },
    }
}

REG_VALIDATOR: dict[str, Any] = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["code", "country", "title", "version"],
        "properties": {
            "code": {"bsonType": "string"},
            "country": {"bsonType": "string"},
        },
    }
}

SE_VALIDATOR: dict[str, Any] = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["ts", "location_id", "emergency_type", "severity"],
        "properties": {
            "severity": {"bsonType": "int", "minimum": 1, "maximum": 5},
            "hour_of_day": {"bsonType": "int", "minimum": 0, "maximum": 23},
            "day_of_week": {"bsonType": "int", "minimum": 0, "maximum": 6},
        },
    }
}

SKILL_VALIDATOR: dict[str, Any] = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["agent", "capability_text", "embedding"],
        "properties": {
            "embedding": {"bsonType": "array", "minItems": 256, "maxItems": 2048},
            "reliability_score": {"bsonType": "double", "minimum": 0, "maximum": 1},
        },
    }
}

AM_VALIDATOR: dict[str, Any] = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["trace_id", "from_agent", "to_agent", "role", "ts"],
        "properties": {
            "role": {"enum": ["request", "response", "broadcast", "tool_call", "tool_result"]},
        },
    }
}

TC_VALIDATOR: dict[str, Any] = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["idempotency_key", "agent", "tool", "args_hash", "status"],
        "properties": {"status": {"enum": ["pending", "success", "error"]}},
    }
}

VALIDATORS: dict[str, dict[str, Any]] = {
    "facilities": FACILITIES_VALIDATOR,
    "no_fly_zones": NFZ_VALIDATOR,
    "drones": DRONE_VALIDATOR,
    "deliveries": DELIVERY_VALIDATOR,
    "missions": MISSION_VALIDATOR,
    "mission_memory": MEMORY_VALIDATOR,
    "regulations": REG_VALIDATOR,
    "synthetic_emergencies": SE_VALIDATOR,
    "agent_skills": SKILL_VALIDATOR,
    "agent_messages": AM_VALIDATOR,
    "tool_call_log": TC_VALIDATOR,
}

# ---------------------------------------------------------------------------
# Time-series collection definitions
# ---------------------------------------------------------------------------
TIMESERIES: dict[str, dict[str, Any]] = {
    "weather_observations": {
        "timeseries": {
            "timeField": "ts", "metaField": "location_id", "granularity": "minutes",
        },
        "expireAfterSeconds": 60 * 60 * 24 * 30,
    },
    "telemetry": {
        "timeseries": {
            "timeField": "ts", "metaField": "drone_id", "granularity": "seconds",
        },
        "expireAfterSeconds": 60 * 60 * 24 * 7,
    },
}


# ---------------------------------------------------------------------------
# Index definitions (driver-side)
# ---------------------------------------------------------------------------
DRIVER_INDEXES: dict[str, list[tuple[list, dict]]] = {
    "facilities": [
        ([("location", "2dsphere")], {"name": "loc_2dsphere"}),
        ([("name", 1)], {"name": "name_1", "unique": True}),
        ([("region", 1), ("type", 1)], {"name": "region_type_1"}),
        ([("capabilities", 1)], {"name": "capabilities_multikey"}),
    ],
    "no_fly_zones": [
        ([("geometry", "2dsphere")], {"name": "nfz_geo"}),
        ([("effective_from", 1), ("effective_to", 1)], {"name": "nfz_window"}),
        ([("country", 1), ("severity", -1)], {"name": "nfz_country_severity"}),
        ([("source", 1)], {"name": "nfz_source"}),
    ],
    "weather_observations": [
        ([("location_id", 1), ("ts", -1)], {"name": "loc_ts"}),
        ([("flyable", 1), ("ts", -1)], {"name": "flyable_ts"}),
    ],
    "drones": [
        ([("position", "2dsphere")], {"name": "drone_pos_2dsphere"}),
        ([("status", 1)], {"name": "drone_status"}),
        ([("current_mission_id", 1)], {"name": "drone_current_mission"}),
    ],
    "deliveries": [
        ([("status", 1), ("priority", -1), ("requested_at", 1)], {"name": "queue_hot"}),
        ([("assigned_drone", 1)], {"name": "by_drone"}),
        ([("mission_id", 1)], {"name": "by_mission"}),
        ([("destination_id", 1)], {"name": "by_destination"}),
    ],
    "missions": [
        ([("status", 1), ("started_at", -1)], {"name": "status_started"}),
        ([("drone_id", 1), ("started_at", -1)], {"name": "by_drone_time"}),
        ([("delivery_ids", 1)], {"name": "by_delivery"}),
        ([("completed_at", -1)], {"name": "recency"}),
    ],
    "telemetry": [
        ([("drone_id", 1), ("ts", -1)], {"name": "drone_ts"}),
        ([("anomaly_score", -1), ("ts", -1)], {"name": "anomaly_ts"}),
    ],
    "flight_logs": [
        ([("drone_id", 1), ("ts", -1)], {"name": "drone_ts"}),
        ([("mission_id", 1), ("ts", 1)], {"name": "mission_ts"}),
        ([("event", 1), ("ts", -1)], {"name": "event_ts"}),
    ],
    "audit_trail": [
        ([("seq", 1)], {"name": "seq", "unique": True}),
        ([("subject_type", 1), ("subject_id", 1), ("ts", -1)], {"name": "subj"}),
        ([("ts", -1)], {"name": "ts"}),
    ],
    "mission_memory": [
        ([("kind", 1), ("created_at", -1)], {"name": "kind_time"}),
        ([("metadata.region", 1)], {"name": "region"}),
        ([("metadata.tags", 1)], {"name": "tags_multikey"}),
        ([("source_collection", 1), ("source_id", 1)], {"name": "provenance"}),
    ],
    "regulations": [
        ([("code", 1)], {"name": "code", "unique": True}),
        ([("country", 1), ("effective_from", -1)], {"name": "country_time"}),
    ],
    "synthetic_emergencies": [
        ([("ts", 1)], {"name": "ts"}),
        ([("location_id", 1), ("ts", 1)], {"name": "loc_ts"}),
        ([("emergency_type", 1), ("severity", -1)], {"name": "type_sev"}),
    ],
    "agent_skills": [
        ([("agent", 1)], {"name": "agent_unique", "unique": True}),
        ([("enabled", 1), ("reliability_score", -1)], {"name": "best_first"}),
    ],
    "agent_messages": [
        ([("mission_id", 1), ("ts", 1)], {"name": "mission_ts"}),
        ([("trace_id", 1), ("ts", 1)], {"name": "trace_ts"}),
        ([("from_agent", 1), ("to_agent", 1), ("ts", -1)], {"name": "dyad"}),
    ],
    "tool_call_log": [
        ([("idempotency_key", 1)], {"name": "idem_unique", "unique": True}),
        ([("agent", 1), ("tool", 1), ("started_at", -1)], {"name": "agent_tool_time"}),
        ([("status", 1), ("started_at", -1)], {"name": "status_time"}),
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def apply_validator(
    db: AsyncIOMotorDatabase,
    name: str,
    validator: dict[str, Any],
    *,
    timeseries: dict[str, Any] | None = None,
) -> None:
    """Create the collection with the validator (if missing) or `collMod` it.

    On engines that don't implement `collMod` (mongomock), the failure is
    logged at debug level and the function returns without raising.
    """
    existing = await db.list_collection_names(filter={"name": name})
    if not existing:
        kwargs: dict[str, Any] = {}
        if timeseries:
            kwargs.update(timeseries)
        else:
            kwargs["validator"] = validator
            kwargs["validationLevel"] = "moderate"
        try:
            await db.create_collection(name, **kwargs)
        except (OperationFailure, NotImplementedError) as exc:
            # mongomock raises NotImplementedError for `validator`/`timeseries`
            # kwargs — fall back to a plain collection.
            log.debug("create_collection(%s) fell back to plain: %s", name, exc)
            try:
                await db.create_collection(name)
            except (OperationFailure, NotImplementedError):
                pass
        return

    try:
        await db.command(
            {"collMod": name, "validator": validator, "validationLevel": "moderate"}
        )
    except (OperationFailure, NotImplementedError) as exc:  # mongomock raises NotImplementedError
        log.debug("collMod(%s) skipped: %s", name, exc)


async def ensure_timeseries(db: AsyncIOMotorDatabase) -> None:
    """Create time-series collections if missing. Falls back to a regular
    collection when the engine doesn't support time-series (mongomock).
    """
    existing = set(await db.list_collection_names())
    for name, cfg in TIMESERIES.items():
        if name in existing:
            continue
        try:
            await db.create_collection(name, **cfg)
        except (OperationFailure, NotImplementedError, TypeError) as exc:
            log.debug("time-series %s fallback: %s", name, exc)
            try:
                await db.create_collection(name)
            except OperationFailure:
                pass


async def ensure_indexes(db: AsyncIOMotorDatabase) -> dict[str, list[str]]:
    """Create every B-tree / geo index. Returns a map of collection → index names."""
    created: dict[str, list[str]] = {}
    for coll, idx_specs in DRIVER_INDEXES.items():
        names: list[str] = []
        for keys, opts in idx_specs:
            try:
                name = await db[coll].create_index(keys, **opts)
                names.append(name)
            except OperationFailure as exc:  # pragma: no cover — defensive
                log.warning("create_index(%s, %s) failed: %s", coll, opts.get("name"), exc)
        created[coll] = names
    return created


async def apply_all_validators(db: AsyncIOMotorDatabase) -> None:
    """Apply every `$jsonSchema` validator from this module."""
    for name, validator in VALIDATORS.items():
        await apply_validator(db, name, validator)


async def bootstrap(db: AsyncIOMotorDatabase) -> None:
    """Full idempotent bootstrap: time-series → validators → driver indexes."""
    await ensure_timeseries(db)
    await apply_all_validators(db)
    await ensure_indexes(db)


__all__ = [
    "AM_VALIDATOR",
    "DELIVERY_VALIDATOR",
    "DRIVER_INDEXES",
    "DRONE_VALIDATOR",
    "FACILITIES_VALIDATOR",
    "MEMORY_VALIDATOR",
    "MISSION_VALIDATOR",
    "NFZ_VALIDATOR",
    "REG_VALIDATOR",
    "SE_VALIDATOR",
    "SKILL_VALIDATOR",
    "TC_VALIDATOR",
    "TIMESERIES",
    "VALIDATORS",
    "apply_all_validators",
    "apply_validator",
    "bootstrap",
    "ensure_indexes",
    "ensure_timeseries",
]
