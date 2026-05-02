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
    log_id = f"fl_{uuid.uuid4().hex[:10]}"
    await db.flight_logs.insert_one(
        {
            "_id": log_id,
            "id": log_id,  # frontend expects `id` directly
            "mission_id": mission_id,
            "drone_id": drone_id,
            "event": event,
            "ts": datetime.now(timezone.utc),
            **extra,
        }
    )


async def _agent_msg(
    db: Any,
    *,
    mission_id: str,
    kind: str,
    text: str,
    agent: str | None = None,
    meta: dict | None = None,
) -> None:
    """Insert an ``agent_messages`` row so the reasoning stream lights up."""
    msg_id = f"am_{uuid.uuid4().hex[:10]}"
    try:
        await db.agent_messages.insert_one(
            {
                "_id": msg_id,
                "id": msg_id,
                "ts": datetime.now(timezone.utc),
                "kind": kind,
                "mission_id": mission_id,
                "agent": agent or kind,
                "text": text,
                "meta": meta or {},
            }
        )
    except Exception as exc:
        log.debug("agent_messages insert failed: %s", exc)


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

        # ── Supervisor + specialists narrate via agent_messages ─────────
        await _agent_msg(
            db,
            mission_id=mission_id,
            kind="supervisor",
            agent="SupervisorAgent",
            text=f"Routing mission {mission_id} to the planner stack.",
        )
        await _agent_msg(
            db,
            mission_id=mission_id,
            kind="memory",
            agent="MemoryAgent",
            text="Pulled 3 relevant cards from mission_memory via Atlas Vector Search.",
        )
        await _agent_msg(
            db,
            mission_id=mission_id,
            kind="planner",
            agent="PlannerAgent",
            text=f"Planned {len(points) - 1} leg(s). Depot → {points[1][0] if len(points) > 1 else 'return'}.",
        )
        await _agent_msg(
            db,
            mission_id=mission_id,
            kind="geofence",
            agent="GeofenceAgent",
            text="Route cleared against 6 active no-fly polygons ($geoIntersects).",
        )
        await _agent_msg(
            db,
            mission_id=mission_id,
            kind="dispatch",
            agent="DispatchAgent",
            text=f"Handing control to {drone_id}. Takeoff imminent.",
        )

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
        rerouted = False
        reroute_at_step = max(3, steps_per_leg // 3)  # ~33% into the first leg

        for i in range(len(points) - 1):
            a_name, a_pos = points[i]
            b_name, b_pos = points[i + 1]
            heading = _bearing(a_pos, b_pos)
            for step in range(1, steps_per_leg + 1):
                t = step / steps_per_leg
                pos = _lerp(a_pos, b_pos, t)
                battery = max(10.0, battery - (90.0 / (steps_per_leg * max(1, len(points) - 1))))

                # Mid-flight reroute on the first leg — inject a dogleg so the
                # operator sees the planned path redraw with a waypoint shift.
                if not rerouted and i == 0 and step == reroute_at_step:
                    # Dogleg: perpendicular offset ~500m off the straight line.
                    dx = b_pos[0] - a_pos[0]
                    dy = b_pos[1] - a_pos[1]
                    # Normal vector rotated 90° (in degrees-on-earth space).
                    norm = max(1e-6, math.hypot(dx, dy))
                    nx, ny = -dy / norm, dx / norm
                    offset = 0.005  # ~500m in London latitude
                    dogleg = [pos[0] + nx * offset, pos[1] + ny * offset]
                    new_route = [
                        {"location": depot_name, "kind": "depot"},
                        {"location": "reroute_waypoint", "kind": "reroute"},
                    ]
                    # Keep remaining stops after the dogleg.
                    for j, (name, _) in enumerate(points[1:]):
                        kind = "stop" if j < len(points) - 2 else "return"
                        new_route.append({"location": name, "kind": kind})

                    await db.missions.update_one(
                        {"_id": mission_id},
                        {
                            "$set": {
                                "planned_route": new_route,
                                "updated_at": datetime.now(timezone.utc),
                            },
                            "$push": {
                                "reroutes": {
                                    "ts": datetime.now(timezone.utc),
                                    "reason": "weather_cell_detected",
                                    "waypoint": dogleg,
                                }
                            },
                        },
                    )
                    await _flight_log(
                        db,
                        mission_id=mission_id,
                        drone_id=drone_id,
                        event="rerouted",
                        reason="weather_cell_detected",
                        waypoint=dogleg,
                    )
                    await _agent_msg(
                        db,
                        mission_id=mission_id,
                        kind="weather",
                        agent="WeatherAgent",
                        text="Storm cell detected 800m ahead. Wind 14 m/s, gusting 19 m/s.",
                    )
                    await _agent_msg(
                        db,
                        mission_id=mission_id,
                        kind="replanner",
                        agent="ReplannerAgent",
                        text="Bending route 500m north to clear the gust corridor.",
                    )
                    await _narration(
                        db,
                        mission_id=mission_id,
                        text="Weather cell ahead. Rerouting 500 metres north.",
                    )

                    # Detour via the dogleg: from current pos to dogleg, then dogleg to b_pos.
                    b_pos = dogleg  # first leg now ends at dogleg
                    heading = _bearing(pos, b_pos)
                    rerouted = True

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

            # After first leg (if we rerouted), insert an extra mini-leg from
            # the dogleg back to the real destination so the drone finishes the
            # originally-planned arrival.
            if rerouted and i == 0 and len(points) > 1:
                real_b_name, real_b_pos = points[i + 1]
                if real_b_pos != b_pos:
                    dogleg_pos = b_pos
                    leg_heading = _bearing(dogleg_pos, real_b_pos)
                    mini_steps = max(4, steps_per_leg // 3)
                    for step in range(1, mini_steps + 1):
                        tt = step / mini_steps
                        pos = _lerp(dogleg_pos, real_b_pos, tt)
                        battery = max(10.0, battery - 1.0)
                        await _set_drone(
                            db,
                            drone_id,
                            position=pos,
                            heading=leg_heading,
                            battery=battery,
                        )
                        await _telemetry(
                            db,
                            mission_id=mission_id,
                            drone_id=drone_id,
                            position=pos,
                            battery=battery,
                            heading_deg=leg_heading,
                        )
                        await asyncio.sleep(step_seconds)
                    # Overwrite b_pos locally so the waypoint message below
                    # reports delivery at the real destination.
                    b_name, b_pos = real_b_name, real_b_pos
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
        await _agent_msg(
            db,
            mission_id=mission_id,
            kind="reflection",
            agent="ReflectionAgent",
            text=(
                f"Mission {mission_id} closed out on time. "
                f"Battery delta {100.0 - battery:.0f}%. Writing lesson to mission_memory."
            ),
        )
        # Write a reflection card so the Reflections feed updates live too.
        text = (
            f"{mission_id} delivered to {points[1][0] if len(points) > 1 else depot_name} "
            f"and returned in ~{int(step_seconds * steps_per_leg * (len(points) - 1))}s. "
            f"{'Rerouted once around a weather cell; ' if 'rerouted' in locals() and rerouted else ''}"
            "Battery envelope normal."
        )
        try:
            # Real embedding so $vectorSearch can actually recall this card
            # next time. Falls back to the deterministic stub if voyage is
            # unreachable.
            from dronan.embeddings.voyage import embed as _embed  # noqa: PLC0415
            from dronan.config import get_settings as _get_settings  # noqa: PLC0415

            vec = await _embed(text, db=db, dim=_get_settings().voyage_dim)
            model_name = _get_settings().voyage_model
        except Exception as exc:
            log.debug("voyage embed failed, using zero vector: %s", exc)
            vec = [0.0] * 1024
            model_name = "sim-placeholder"
        try:
            await db.mission_memory.insert_one(
                {
                    "_id": f"mm_{uuid.uuid4().hex[:10]}",
                    "kind": "reflection",
                    "title": f"{mission_id}: clean run",
                    "text": text,
                    "embedding": vec,
                    "embedding_model": model_name,
                    "source_collection": "missions",
                    "source_id": mission_id,
                    "created_at": now,
                }
            )
        except Exception as exc:
            log.debug("reflection insert skipped: %s", exc)
    except Exception as exc:
        log.exception("simulate_mission(%s) failed: %s", mission_id, exc)
        try:
            await db.missions.update_one(
                {"_id": mission_id},
                {"$set": {"status": "failed", "updated_at": datetime.now(timezone.utc)}},
            )
        except Exception:
            pass
