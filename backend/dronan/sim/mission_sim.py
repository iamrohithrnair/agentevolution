"""Background mission simulator.

Fills the gap the demo needs until the real flight loop lands: the
supervisor graph creates a ``missions`` doc in ``status=planned`` but
nothing moves the drone, flips the status, or emits flight logs. This
module spawns a coroutine that walks the drone along ``planned_route``,
inserts telemetry, flight-log, and narration events, and closes the
mission out as ``completed`` (or ``failed`` on error).

Triggered from ``api.routes.missions.create_mission``.
"""

from __future__ import annotations

import asyncio
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


async def _facility_position(db: Any, name_or_id: str) -> list[float] | None:
    doc = await db.facilities.find_one(
        {"$or": [{"_id": name_or_id}, {"name": name_or_id}]},
        {"location.coordinates": 1},
    )
    if not doc:
        return None
    coords = (doc.get("location") or {}).get("coordinates") or []
    if isinstance(coords, list) and len(coords) >= 2:
        return [float(coords[0]), float(coords[1])]
    return None


def _lerp(a: list[float], b: list[float], t: float) -> list[float]:
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]


def _bearing(a: list[float], b: list[float]) -> float:
    """Approximate bearing in degrees from a→b."""
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return (math.degrees(math.atan2(dx, dy)) + 360) % 360


async def _flight_log(db: Any, *, mission_id: str, drone_id: str, event: str, **extra) -> None:
    await db.flight_logs.insert_one(
        {
            "_id": f"fl_{uuid.uuid4().hex[:10]}",
            "mission_id": mission_id,
            "drone_id": drone_id,
            "event": event,
            "ts": datetime.now(timezone.utc),
            **extra,
        }
    )


async def _narration(db: Any, *, mission_id: str, text: str) -> None:
    try:
        await db.narrations.insert_one(
            {
                "_id": f"n_{uuid.uuid4().hex[:10]}",
                "mission_id": mission_id,
                "text": text,
                "ts": datetime.now(timezone.utc),
            }
        )
    except Exception:
        pass


async def _telemetry(db: Any, *, mission_id: str, drone_id: str, position: list[float], **extra) -> None:
    try:
        await db.telemetry.insert_one(
            {
                "mission_id": mission_id,
                "drone_id": drone_id,
                "ts": datetime.now(timezone.utc),
                "position": {"type": "Point", "coordinates": position},
                **extra,
            }
        )
    except Exception as exc:
        log.debug("telemetry insert failed: %s", exc)


async def _set_drone(
    db: Any,
    drone_id: str,
    *,
    position: list[float] | None = None,
    heading: float | None = None,
    battery: float | None = None,
    status: str | None = None,
    current_mission_id: str | None = ...,  # type: ignore[assignment]
) -> None:
    update: dict = {"last_seen": datetime.now(timezone.utc)}
    if position is not None:
        update["position"] = {"type": "Point", "coordinates": position}
    if heading is not None:
        update["heading_deg"] = float(heading)
    if battery is not None:
        update["battery"] = float(battery)
    if status is not None:
        update["status"] = status
    if current_mission_id is not ...:
        update["current_mission_id"] = current_mission_id
    await db.drones.update_one({"_id": drone_id}, {"$set": update})


async def simulate_mission(
    db: Any,
    mission_id: str,
    *,
    step_seconds: float = 0.8,
    steps_per_leg: int = 18,
) -> None:
    """Walk the drone through the mission's waypoints and close it out."""
    try:
        mission = await db.missions.find_one({"_id": mission_id})
        if mission is None:
            log.warning("simulate_mission: %s not found", mission_id)
            return
        drone_id = mission.get("drone_id") or "Drone1"
        depot_name = mission.get("depot") or "Depot"
        stops = mission.get("stops") or []

        # Resolve every leg's coordinates; drop unresolved stops rather than crash.
        points: list[tuple[str, list[float]]] = []
        depot_pos = await _facility_position(db, depot_name) or [-0.1278, 51.5074]
        points.append((depot_name, depot_pos))
        for s in stops:
            pos = await _facility_position(db, s)
            if pos:
                points.append((s, pos))
        points.append((depot_name, depot_pos))
        if len(points) < 2:
            return

        # ── Executing ────────────────────────────────────────────────────
        await db.missions.update_one(
            {"_id": mission_id},
            {
                "$set": {
                    "status": "executing",
                    "started_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        await _set_drone(
            db,
            drone_id,
            status="flying",
            current_mission_id=mission_id,
            position=points[0][1],
        )
        await _flight_log(db, mission_id=mission_id, drone_id=drone_id, event="takeoff")
        await _narration(
            db,
            mission_id=mission_id,
            text=f"Mission {mission_id} airborne. Departing {depot_name}.",
        )

        battery = 100.0
        for i in range(len(points) - 1):
            a_name, a_pos = points[i]
            b_name, b_pos = points[i + 1]
            heading = _bearing(a_pos, b_pos)
            for step in range(1, steps_per_leg + 1):
                t = step / steps_per_leg
                pos = _lerp(a_pos, b_pos, t)
                battery = max(10.0, battery - (90.0 / (steps_per_leg * max(1, len(points) - 1))))
                await _set_drone(
                    db,
                    drone_id,
                    position=pos,
                    heading=heading,
                    battery=battery,
                )
                await _telemetry(
                    db,
                    mission_id=mission_id,
                    drone_id=drone_id,
                    position=pos,
                    battery=battery,
                    heading_deg=heading,
                )
                await asyncio.sleep(step_seconds)
            # Waypoint reached
            if i == len(points) - 2 and b_name == depot_name:
                await _flight_log(
                    db, mission_id=mission_id, drone_id=drone_id, event="landed"
                )
            else:
                await _flight_log(
                    db,
                    mission_id=mission_id,
                    drone_id=drone_id,
                    event="delivered",
                    location=b_name,
                )
                await _narration(
                    db,
                    mission_id=mission_id,
                    text=f"Payload delivered at {b_name}.",
                )

        # ── Completed ────────────────────────────────────────────────────
        now = datetime.now(timezone.utc)
        await db.missions.update_one(
            {"_id": mission_id},
            {"$set": {"status": "completed", "completed_at": now, "updated_at": now}},
        )
        await db.deliveries.update_many(
            {"mission_id": mission_id},
            {"$set": {"status": "delivered", "completed_at": now}},
        )
        await _set_drone(
            db, drone_id, status="idle", current_mission_id=None, battery=battery
        )
        await _narration(
            db,
            mission_id=mission_id,
            text=f"Mission {mission_id} complete. Drone returned to {depot_name}.",
        )
    except Exception as exc:
        log.exception("simulate_mission(%s) failed: %s", mission_id, exc)
        try:
            await db.missions.update_one(
                {"_id": mission_id},
                {"$set": {"status": "failed", "updated_at": datetime.now(timezone.utc)}},
            )
        except Exception:
            pass
