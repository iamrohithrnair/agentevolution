"""Bulk-seed the 44 118 historical emergency rows from
``backend/data/synthetic_emergencies.csv`` into ``synthetic_emergencies``.

Idempotency: each row is keyed on ``(ts, location_id, emergency_type)`` so
re-running yields zero modifications. Uses 1000-row bulk batches.

Run: ``uv run python -m backend.seeds.seed_synthetic_emergencies``
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from backend.dronan.bootstrap import SE_VALIDATOR, apply_validator

from ._common import bulk_upsert, run

CSV_PATH = Path(
    os.environ.get(
        "DRONAN_EMERGENCIES_CSV",
        str(
            Path(__file__).resolve().parent.parent
            / "data"
            / "synthetic_emergencies.csv"
        ),
    )
)
BATCH = int(os.environ.get("DRONAN_EMERGENCIES_BATCH", "1000"))


def _parse_iso(s: str) -> datetime:
    s = s.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # Tolerate `2025-01-01 00:05:24` (no T)
        return datetime.fromisoformat(s.replace(" ", "T")).replace(tzinfo=timezone.utc)


def _row_to_doc(row: dict[str, str]) -> dict[str, Any] | None:
    try:
        ts = _parse_iso(row["ts"])
    except (KeyError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    try:
        severity = int(row.get("severity", "1") or 1)
    except ValueError:
        severity = 1
    severity = max(1, min(5, severity))
    try:
        hour_of_day = int(row.get("hour_of_day", ts.hour))
    except ValueError:
        hour_of_day = ts.hour
    try:
        day_of_week = int(row.get("day_of_week", ts.weekday()))
    except ValueError:
        day_of_week = ts.weekday()
    try:
        lat = float(row.get("location_lat") or 0.0)
        lon = float(row.get("location_lon") or 0.0)
    except ValueError:
        lat = lon = 0.0
    try:
        temp = float(row.get("temperature_c") or 0.0)
    except ValueError:
        temp = 0.0
    return {
        "ts": ts,
        "location_id": (row.get("location_id") or "").strip() or "unknown",
        "location_lat": lat,
        "location_lon": lon,
        "emergency_type": (row.get("emergency_type") or "other").strip().lower(),
        "severity": severity,
        "temperature_c": temp,
        "weather_condition": (row.get("weather_condition") or "clear").strip().lower(),
        "is_holiday": (row.get("is_holiday") or "").strip().lower() in ("1", "true", "yes"),
        "is_event": (row.get("is_event") or "").strip().lower() in ("1", "true", "yes"),
        "hour_of_day": max(0, min(23, hour_of_day)),
        "day_of_week": max(0, min(6, day_of_week)),
    }


async def main(db: AsyncIOMotorDatabase) -> dict[str, int]:
    """Bulk-insert from CSV. Skips silently if the file is missing."""
    await apply_validator(db, "synthetic_emergencies", SE_VALIDATOR)

    if not CSV_PATH.is_file():
        print(f"synthetic_emergencies: csv not found at {CSV_PATH}; skipping")
        return {"upserted": 0, "modified": 0, "total": 0, "skipped": True}

    upserted = modified = 0
    batch: list[UpdateOne] = []
    with CSV_PATH.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            doc = _row_to_doc(row)
            if doc is None:
                continue
            batch.append(
                UpdateOne(
                    {
                        "ts": doc["ts"],
                        "location_id": doc["location_id"],
                        "emergency_type": doc["emergency_type"],
                    },
                    {"$set": doc},
                    upsert=True,
                )
            )
            if len(batch) >= BATCH:
                res = await bulk_upsert(db.synthetic_emergencies, batch)
                upserted += res["upserted"]
                modified += res["modified"]
                batch.clear()
        if batch:
            res = await bulk_upsert(db.synthetic_emergencies, batch)
            upserted += res["upserted"]
            modified += res["modified"]

    total = await db.synthetic_emergencies.count_documents({})
    print(
        f"synthetic_emergencies: upserted={upserted} modified={modified} total={total}"
    )
    return {"upserted": upserted, "modified": modified, "total": total}


if __name__ == "__main__":
    run(main)
