"""Boot-time agent registration + central registry.

``AGENTS`` is the dict every LangGraph node lookup goes through. Importing
this module side-effect-registers each node into the dict.
"""

from __future__ import annotations

from typing import Any

from .dispatch import dispatch_node
from .geofence import geofence_node
from .interpreter import interpreter_node
from .lightweight import (
    analyst_node,
    anomaly_node,
    deconfliction_node,
    demand_forecast_node,
    narrator_node,
    reflection_node,
    replanner_node,
    vision_node,
)
from .memory_agent import memory_node
from .payload import payload_node
from .planner import planner_node
from .preflight import preflight_node
from .state import Route
from .supervisor import supervisor_node
from .weather import weather_node

AGENTS: dict[Route, Any] = {
    "supervisor": supervisor_node,
    "interpreter": interpreter_node,
    "memory": memory_node,
    "planner": planner_node,
    "weather": weather_node,
    "geofence": geofence_node,
    "preflight": preflight_node,
    "dispatch": dispatch_node,
    "vision": vision_node,
    "replanner": replanner_node,
    "anomaly": anomaly_node,
    "deconfliction": deconfliction_node,
    "payload": payload_node,
    "narrator": narrator_node,
    "analyst": analyst_node,
    "reflection": reflection_node,
    "demand_forecast": demand_forecast_node,
}

# Specialists = everyone except the supervisor.
SPECIALISTS: tuple[Route, ...] = tuple(k for k in AGENTS if k != "supervisor")


async def register_all(db: Any) -> int:
    """Boot-time hook: ensure every agent has a row in ``agent_skills``.

    The seeds in P1 already populate ``agent_skills`` with embeddings; this
    helper is the runtime safety net — when the worker boots against a
    fresh database we make sure the table is seeded so the supervisor's
    vector-search routing has a corpus to query.
    """
    from ..embeddings import embed
    from datetime import datetime, timezone

    # Each capability_text is enriched with keyword synonyms so the offline
    # hashing-trick embedder can route on token overlap. The first sentence
    # is the human-readable description; the rest is a tag bag.
    capability_texts: dict[str, str] = {
        "supervisor": (
            "Decide the next specialist or terminate the mission. "
            "Tags: end terminate finish coordinator orchestrator handoff."
        ),
        "interpreter": (
            "Translate operator natural-language requests into structured tasks "
            "(locations, supplies, priorities, constraints). "
            "Tags: parse intent understand utterance speech text request."
        ),
        "memory": (
            "Recall lessons and prior reflections from mission memory and inject "
            "them into the supervisor's context. "
            "Tags: recall remember retrieve lessons history past similar prior."
        ),
        "planner": (
            "Build feasible drone routes using OR-Tools VRP with capacity, "
            "time-window, and battery dimensions. "
            "Tags: plan route tour compute solve VRP TSP path optimal stops "
            "depot itinerary trip schedule."
        ),
        "weather": (
            "Fetch wind precipitation visibility and classify each leg as "
            "flyable degraded or no-go. "
            "Tags: wind gust rain forecast precipitation visibility weather "
            "cloud storm metar safe along the route flight conditions."
        ),
        "geofence": (
            "Validate that no leg intersects a no-fly zone or temporary "
            "flight restriction via 2dsphere $geoIntersects. "
            "Tags: geofence no-fly nfz tfr airspace zone validate corridor "
            "intrusion violation cross intersect prohibited restricted."
        ),
        "preflight": (
            "Run hardware firmware and sensor checks before takeoff. "
            "Tags: pre-flight preflight checklist verify firmware "
            "takeoff inspection ready airworthy power-on initialise."
        ),
        "dispatch": (
            "Bind a drone to a mission and flip both into the flying state. "
            "Tags: dispatch send launch deploy fly flying takeoff release "
            "drone now go assign bind."
        ),
        "vision": (
            "Detect obstacles trees birds wires in the live camera frame "
            "using YOLO inference. "
            "Tags: vision camera frame detect obstacle tree bird wire image "
            "look approach see object visual."
        ),
        "replanner": (
            "Decide whether the in-flight plan needs to be re-solved given "
            "anomalies weather and geofence violations. "
            "Tags: replan reroute reschedule divert detour adjust modify "
            "in-flight."
        ),
        "anomaly": (
            "Inspect telemetry for battery sag GPS drift and signal loss. "
            "Tags: anomaly battery sag sagging drain glitch glitches gps "
            "drift signal loss telemetry investigate weird wrong fault."
        ),
        "deconfliction": (
            "Avoid in-flight conflicts with other nearby ongoing missions. "
            "Tags: deconflict deconfliction nearby conflict separate "
            "spacing other ongoing missions traffic separation."
        ),
        "payload": (
            "Build the manifest and predict cold-chain bag temperature "
            "breach risk with ice packs. "
            "Tags: payload manifest cold-chain bag temperature ice pack "
            "predict assemble cargo weight."
        ),
        "narrator": (
            "Produce one-line operator-facing narrations for each phase of "
            "the mission. "
            "Tags: narrate narrator story update voiceover commentary "
            "operator-facing announce."
        ),
        "analyst": (
            "Aggregate metrics across missions and generate post-flight "
            "reports. "
            "Tags: analyst analytics aggregate metrics report dashboard "
            "kpi count tally summary hour."
        ),
        "reflection": (
            "Write reflection cards back to mission memory for "
            "self-evolution. "
            "Tags: reflection reflect lesson learn post-flight write "
            "remember future improve."
        ),
        "demand_forecast": (
            "Forecast pending demand by destination and time horizon. "
            "Tags: demand forecast pending future predict supply-need "
            "destination horizon."
        ),
    }

    inserted = 0
    now = datetime.now(timezone.utc)
    for agent, text in capability_texts.items():
        existing = await db.agent_skills.find_one({"agent": agent})
        if existing is not None:
            continue
        vec = await embed(text, db=db, dim=1024)
        await db.agent_skills.insert_one(
            {
                "agent": agent,
                "capability_text": text,
                "embedding": vec,
                "embedding_model": "voyage-3-large",
                "tools": [],
                "created_at": now,
                "updated_at": now,
            }
        )
        inserted += 1
    return inserted
