"""Seed Drone1, Drone2, Drone3 at the Depot with full status fields.

Run: ``uv run python -m backend.seeds.seed_drones``
"""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from backend.dronan.bootstrap import DRONE_VALIDATOR, apply_validator

from ._common import bulk_upsert, run, utcnow

DEPOT_LON = -0.1278
DEPOT_LAT = 51.5074

DRONES: list[dict[str, Any]] = [
    {
        "_id": "Drone1",
        "model": "Skyhound-5",
        "status": "idle",
        "battery": 100.0,
        "max_payload_kg": 5.0,
        "cruise_speed_ms": 15.0,
        "current_location": "Depot",
        "position": {"type": "Point", "coordinates": [DEPOT_LON, DEPOT_LAT]},
        "alt_m": 0.0,
        "heading_deg": 0.0,
        "current_mission_id": None,
        "firmware": "1.2.3",
        "capabilities": ["cold_chain", "camera", "thermal"],
    },
    {
        "_id": "Drone2",
        "model": "Skyhound-5",
        "status": "idle",
        "battery": 100.0,
        "max_payload_kg": 5.0,
        "cruise_speed_ms": 15.0,
        "current_location": "Depot",
        "position": {"type": "Point", "coordinates": [DEPOT_LON, DEPOT_LAT]},
        "alt_m": 0.0,
        "heading_deg": 0.0,
        "current_mission_id": None,
        "firmware": "1.2.3",
        "capabilities": ["cold_chain", "camera"],
    },
    {
        "_id": "Drone3",
        "model": "Skyhound-5",
        "status": "idle",
        "battery": 100.0,
        "max_payload_kg": 7.5,
        "cruise_speed_ms": 14.0,
        "current_location": "Depot",
        "position": {"type": "Point", "coordinates": [DEPOT_LON, DEPOT_LAT]},
        "alt_m": 0.0,
        "heading_deg": 0.0,
        "current_mission_id": None,
        "firmware": "1.2.3",
        "capabilities": ["cold_chain", "camera", "thermal", "long_range"],
    },
]


async def main(db: AsyncIOMotorDatabase) -> dict[str, int]:
    """Idempotently upsert the demo fleet."""
    await apply_validator(db, "drones", DRONE_VALIDATOR)

    ops: list[UpdateOne] = []
    for d in DRONES:
        doc = {**d, "last_seen": utcnow()}
        ops.append(UpdateOne({"_id": d["_id"]}, {"$set": doc}, upsert=True))

    res = await bulk_upsert(db.drones, ops)
    total = await db.drones.count_documents({})
    print(
        f"drones: upserted={res['upserted']} "
        f"modified={res['modified']} total={total}"
    )
    return {**res, "total": total}


if __name__ == "__main__":
    run(main)
