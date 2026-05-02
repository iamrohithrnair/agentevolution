"""Preflight tool — boot-time health check.

Runs the assertions from ``prompts/13 §3`` (vector indexes ready, 17
SkillCards present, drone fleet idle, checkpointer reachable) so the
Supervisor can refuse to start a mission against a half-seeded cluster.
"""

from __future__ import annotations

from typing import Any

from ._decorator import mongo_tool


@mongo_tool(side_effect_class="read", agent="PreflightAgent")
async def run_preflight(*, db: Any) -> dict:
    """Return a structured report. ``ready=True`` means dispatch is permitted."""
    report: dict[str, Any] = {"ready": True, "checks": []}

    def _add(name: str, ok: bool, **detail: Any) -> None:
        report["checks"].append({"name": name, "ok": ok, **detail})
        if not ok:
            report["ready"] = False

    # Facilities present (≥ 9 hardcoded)
    fac_count = await db.facilities.count_documents({})
    _add("facilities_seeded", fac_count >= 9, count=fac_count)

    # Drone fleet idle
    drones = await db.drones.find({}, {"_id": 1, "status": 1}).to_list(length=100)
    idle = [d for d in drones if d.get("status") == "idle"]
    _add(
        "drones_idle",
        len(idle) >= 1,
        total=len(drones),
        idle=len(idle),
        ids=[d["_id"] for d in idle],
    )

    # 17 SkillCards present
    skill_count = await db.agent_skills.count_documents({})
    _add("agent_skills_seeded", skill_count >= 17, count=skill_count)

    # Mission memory has at least the 3 demo cards
    memory_count = await db.mission_memory.count_documents({"kind": "reflection"})
    _add("mission_memory_seeded", memory_count >= 3, count=memory_count)

    # No-fly zones present
    nfz_count = await db.no_fly_zones.count_documents({})
    _add("no_fly_zones_seeded", nfz_count >= 5, count=nfz_count)

    return report
