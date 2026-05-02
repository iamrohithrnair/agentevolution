"""Seed the 17 agent SkillCards so the Supervisor has peers to discover via vector
search at boot.

Run: ``uv run python -m backend.seeds.seed_agent_skills``
"""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from backend.dronan.bootstrap import SKILL_VALIDATOR, apply_validator
from backend.dronan.config import settings

from ._common import bulk_upsert, deterministic_embedding, run, utcnow

SKILLS: list[dict[str, Any]] = [
    {
        "agent": "SupervisorAgent",
        "capability_text": (
            "Routes operator requests to the right specialist by retrieving "
            "candidate peers via vector search over agent_skills, then calling "
            "them via LangGraph nodes."
        ),
        "side_effect_class": "plan",
        "tools": [],
    },
    {
        "agent": "InterpreterAgent",
        "capability_text": (
            "Parses natural-language operator utterances into structured "
            "MissionRequest payloads (origin, destination, payload, priority, "
            "constraints)."
        ),
        "side_effect_class": "read",
    },
    {
        "agent": "MemoryAgent",
        "capability_text": (
            "Performs adaptive RAG over mission_memory: rewrites queries, runs "
            "$vectorSearch, reranks with rerank-2.5, and summarises retrieved "
            "lessons under a token budget."
        ),
        "side_effect_class": "read",
    },
    {
        "agent": "RoutePlannerAgent",
        "capability_text": (
            "Plans an OR-Tools VRP route from depot through hospital waypoints, "
            "honouring battery, payload weight, no-fly zones, and operator "
            "corridor preferences. Writes plans to missions."
        ),
        "side_effect_class": "plan",
    },
    {
        "agent": "WeatherAgent",
        "capability_text": (
            "Fetches and aggregates weather observations per facility region, "
            "evaluates flyability gates (wind, visibility, precipitation), and "
            "blocks dispatch when thresholds are breached."
        ),
        "side_effect_class": "read",
    },
    {
        "agent": "GeofenceAgent",
        "capability_text": (
            "Validates a candidate route against no_fly_zones using "
            "$geoIntersects per route segment. Reports prohibited or restricted "
            "zone penetrations with severity."
        ),
        "side_effect_class": "read",
    },
    {
        "agent": "PreflightAgent",
        "capability_text": (
            "Runs the boot health check: 8 vector indexes READY, 17 skill "
            "cards present, drone fleet idle, and the LangGraph checkpointer "
            "reachable."
        ),
        "side_effect_class": "read",
    },
    {
        "agent": "PayloadAgent",
        "capability_text": (
            "Assembles cold-chain manifests, predicts cabin temperature drift "
            "from ambient and ice-pack count, and triggers re-route on "
            "predicted breaches."
        ),
        "side_effect_class": "plan",
    },
    {
        "agent": "DispatchAgent",
        "capability_text": (
            "Issues the actuator command that commits a drone to a mission "
            "(status flying, current_mission_id set, deliveries assigned). "
            "Idempotent via tool_call_log."
        ),
        "side_effect_class": "actuate",
    },
    {
        "agent": "VisionAgent",
        "capability_text": (
            "Detects obstacles in live frames using YOLO, persists frames into "
            "GridFS bucket frames, and emits Obstacle events into the mission "
            "document."
        ),
        "side_effect_class": "read",
    },
    {
        "agent": "ReplannerAgent",
        "capability_text": (
            "Recomputes a safe route mid-flight when weather, no-fly zones, or "
            "detected obstacles invalidate the current plan. Honours battery, "
            "payload weight, and operator corridor preferences."
        ),
        "side_effect_class": "plan",
    },
    {
        "agent": "AnomalyAgent",
        "capability_text": (
            "Watches telemetry for GPS drift, battery sag, and telemetry-loss "
            "patterns; raises anomalies that may trigger replanning or abort."
        ),
        "side_effect_class": "read",
    },
    {
        "agent": "DeconflictionAgent",
        "capability_text": (
            "Resolves right-of-way between sibling drones at merge nodes "
            "using altitude offsets and time staggering."
        ),
        "side_effect_class": "plan",
    },
    {
        "agent": "NarratorAgent",
        "capability_text": (
            "Produces concise voice narration for operators using "
            "ElevenLabs Turbo v2.5 from the live mission state."
        ),
        "side_effect_class": "read",
    },
    {
        "agent": "AnalystAgent",
        "capability_text": (
            "Aggregates per-mission and per-fleet metrics: distance, ETA, "
            "battery, reroutes, cold-chain breaches; renders them for the "
            "analytics dashboard."
        ),
        "side_effect_class": "read",
    },
    {
        "agent": "ReflectionAgent",
        "capability_text": (
            "After every mission completion, summarises what worked / what "
            "failed, embeds the lessons with Voyage, and writes ≥6 "
            "MissionMemory cards. Updates agent_skills reliability scores."
        ),
        "side_effect_class": "audit",
    },
    {
        "agent": "DemandForecastAgent",
        "capability_text": (
            "Builds 7-day emergency demand heat-maps from "
            "synthetic_emergencies and seeds preposition decisions."
        ),
        "side_effect_class": "read",
    },
]


async def main(db: AsyncIOMotorDatabase) -> dict[str, int]:
    """Idempotently register the 17 SkillCards. Real Voyage embeddings replace
    these stubs at agent boot in Phase 3.
    """
    await apply_validator(db, "agent_skills", SKILL_VALIDATOR)

    ops: list[UpdateOne] = []
    for s in SKILLS:
        embedding = deterministic_embedding(s["capability_text"], dim=settings.voyage_dim)
        doc = {
            **s,
            "embedding": embedding,
            "embedding_model": "deterministic-1024-v1",
            "tools": s.get("tools", []),
            "cost_estimate_gbp_per_call": 0.0,
            "avg_latency_ms": 0.0,
            "reliability_score": 1.0,
            "version": "1.0.0",
            "enabled": True,
            "updated_at": utcnow(),
        }
        ops.append(UpdateOne({"agent": s["agent"]}, {"$set": doc}, upsert=True))

    res = await bulk_upsert(db.agent_skills, ops)
    total = await db.agent_skills.count_documents({})
    print(
        f"agent_skills: upserted={res['upserted']} "
        f"modified={res['modified']} total={total}"
    )
    return {**res, "total": total}


if __name__ == "__main__":
    run(main)
