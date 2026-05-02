"""Seed canonical no-fly zones (FAA P-56A, PDOK, UK CAA) + a synthetic east-London TFR.

Run: ``uv run python -m backend.seeds.seed_no_fly_zones``
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from backend.dronan.bootstrap import NFZ_VALIDATOR, apply_validator

from ._common import bulk_upsert, run, utcnow

ZONES: list[dict[str, Any]] = [
    {
        "name": "FAA P-56A Washington DC",
        "source": "FAA",
        "country": "US",
        "severity": "prohibited",
        "altitude_floor_m": 0.0,
        "altitude_ceiling_m": 5486.0,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-77.0470, 38.8870], [-77.0470, 38.9080],
                [-77.0220, 38.9080], [-77.0220, 38.8870],
                [-77.0470, 38.8870],
            ]],
        },
        "metadata": {"notes": "Prohibited area around White House & Capitol"},
    },
    {
        "name": "PDOK Schiphol CTR Inner",
        "source": "PDOK",
        "country": "NL",
        "severity": "prohibited",
        "altitude_floor_m": 0.0,
        "altitude_ceiling_m": 914.0,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [4.7000, 52.2700], [4.7000, 52.3500],
                [4.8200, 52.3500], [4.8200, 52.2700],
                [4.7000, 52.2700],
            ]],
        },
        "metadata": {"icao": "EHAM"},
    },
    {
        "name": "UK CAA Heathrow CTR",
        "source": "UK_CAA",
        "country": "GB",
        "severity": "prohibited",
        "altitude_floor_m": 0.0,
        "altitude_ceiling_m": 762.0,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-0.4543, 51.4500], [-0.4543, 51.4900],
                [-0.4100, 51.4900], [-0.4100, 51.4500],
                [-0.4543, 51.4500],
            ]],
        },
        "metadata": {"icao": "EGLL"},
    },
    {
        "name": "Military Zone Alpha",
        "source": "UK_CAA",
        "country": "GB",
        "severity": "restricted",
        "altitude_floor_m": 0.0,
        "altitude_ceiling_m": 1500.0,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-0.132, 51.513], [-0.132, 51.516],
                [-0.126, 51.516], [-0.126, 51.513],
                [-0.132, 51.513],
            ]],
        },
        "metadata": {"origin": "config.NO_FLY_ZONES"},
    },
    {
        "name": "Airport Exclusion",
        "source": "UK_CAA",
        "country": "GB",
        "severity": "restricted",
        "altitude_floor_m": 0.0,
        "altitude_ceiling_m": 1200.0,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-0.115, 51.503], [-0.115, 51.506],
                [-0.108, 51.506], [-0.108, 51.503],
                [-0.115, 51.503],
            ]],
        },
        "metadata": {"origin": "config.NO_FLY_ZONES"},
    },
    {
        # Synthetic east-London TFR used by the demo Take-1/Take-3 scenario.
        "name": "TFR East London Demo",
        "source": "TFR",
        "country": "GB",
        "severity": "restricted",
        "altitude_floor_m": 0.0,
        "altitude_ceiling_m": 200.0,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-0.030, 51.515], [-0.030, 51.530],
                [0.005, 51.530], [0.005, 51.515],
                [-0.030, 51.515],
            ]],
        },
        "metadata": {"reason": "demo_tfr"},
    },
]


async def main(db: AsyncIOMotorDatabase) -> dict[str, int]:
    """Idempotently upsert the canonical NFZ corpus."""
    await apply_validator(db, "no_fly_zones", NFZ_VALIDATOR)

    base_from = datetime(2020, 1, 1, tzinfo=timezone.utc)
    ops: list[UpdateOne] = []
    for z in ZONES:
        doc = {
            **z,
            "effective_from": base_from,
            "effective_to": None,
            "created_at": utcnow(),
        }
        ops.append(UpdateOne({"name": z["name"]}, {"$set": doc}, upsert=True))

    res = await bulk_upsert(db.no_fly_zones, ops)
    total = await db.no_fly_zones.count_documents({})
    print(
        f"no_fly_zones: upserted={res['upserted']} "
        f"modified={res['modified']} total={total}"
    )
    return {**res, "total": total}


if __name__ == "__main__":
    run(main)
