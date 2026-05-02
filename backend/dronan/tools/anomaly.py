"""Anomaly tools — telemetry inspection (battery sag, GPS drift, signal loss)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ._decorator import mongo_tool


@mongo_tool(side_effect_class="read", agent="AnomalyAgent")
async def inspect_telemetry(
    *,
    db: Any,
    mission_id: str,
    window_minutes: int = 5,
) -> dict:
    """Return a list of detected anomalies for ``mission_id`` within the window."""
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    cursor = db.telemetry.find(
        {"mission_id": mission_id, "ts": {"$gte": since}}
    ).sort("ts", 1)
    samples = await cursor.to_list(length=10_000)

    anomalies: list[dict] = []
    if not samples:
        return {"mission_id": mission_id, "samples": 0, "anomalies": []}

    # Battery sag — drop ≥ 8 % within the window
    bat_start = samples[0].get("battery_pct")
    bat_end = samples[-1].get("battery_pct")
    if (
        bat_start is not None
        and bat_end is not None
        and (bat_start - bat_end) >= 8.0
    ):
        anomalies.append(
            {
                "kind": "battery_sag",
                "drop_pct": round(bat_start - bat_end, 2),
                "from": bat_start,
                "to": bat_end,
            }
        )

    # GPS drift — any sample reporting hdop > 5
    bad_gps = [s for s in samples if s.get("hdop", 0) > 5]
    if bad_gps:
        anomalies.append({"kind": "gps_drift", "count": len(bad_gps)})

    # Signal loss — gaps > 10 s between samples
    for prev, curr in zip(samples[:-1], samples[1:]):
        delta = (curr["ts"] - prev["ts"]).total_seconds()
        if delta > 10:
            anomalies.append(
                {
                    "kind": "signal_loss",
                    "gap_s": round(delta, 1),
                    "ts": curr["ts"],
                }
            )
            break

    return {
        "mission_id": mission_id,
        "samples": len(samples),
        "anomalies": anomalies,
    }
