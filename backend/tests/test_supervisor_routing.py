"""Supervisor routing — vector-search peer discovery + held-out task set.

Acceptance per ``prompts/13 §5``: top-1 ≥ 0.9 on a held-out 20-task set.
"""

from __future__ import annotations

import pytest

from backend.dronan.agents.supervisor import _discover_peer

pytestmark = pytest.mark.unit


@pytest.fixture
async def seeded_skills(mongo_db):
    """Run the agent_skills seed against the mock db."""
    from backend.dronan.agents.registry import register_all

    inserted = await register_all(mongo_db)
    assert inserted >= 17  # supervisor + 16 specialists
    return mongo_db


# 20 held-out (intent, expected_agent) pairs covering every channel.
HOLDOUT = [
    ("plan a route from depot to royal london", "planner"),
    ("compute a tour over four clinics", "planner"),
    ("solve the VRP for these stops", "planner"),
    ("is the wind safe along the route", "weather"),
    ("forecast precipitation for the next hour", "weather"),
    ("does this leg cross a no-fly zone", "geofence"),
    ("validate the corridor against active TFRs", "geofence"),
    ("run the pre-flight checklist", "preflight"),
    ("verify firmware and battery before takeoff", "preflight"),
    ("assemble the manifest and check cold-chain", "payload"),
    ("predict bag temperature with two ice packs", "payload"),
    ("send the drone now", "dispatch"),
    ("flip Drone1 to flying", "dispatch"),
    ("detect obstacles in the camera frame", "vision"),
    ("look for trees on the approach", "vision"),
    ("battery is sagging, investigate", "anomaly"),
    ("gps glitches in the telemetry stream", "anomaly"),
    ("any nearby missions to deconflict", "deconfliction"),
    ("write the post-flight reflection", "reflection"),
    ("aggregate the last hour of metrics", "analyst"),
]


async def test_holdout_top1_recall_at_least_0_9(seeded_skills) -> None:
    db = seeded_skills
    correct = 0
    for intent, expected in HOLDOUT:
        peer = await _discover_peer(db=db, intent=intent, mission_id="t-1")
        if peer == expected:
            correct += 1
    recall = correct / len(HOLDOUT)
    assert recall >= 0.9, f"top-1 recall {recall:.2f} below 0.9 — got {correct}/{len(HOLDOUT)}"


async def test_supervisor_routes_through_static_rules(seeded_skills) -> None:
    """Force the static rule engine and confirm it ratchets through the
    expected sequence on a fresh mission."""
    from backend.dronan.agents.supervisor import supervisor_node

    db = seeded_skills
    state: dict = {"request": "deliver blood from depot to royal london"}

    seen: list[str] = []
    for _ in range(10):
        update = await supervisor_node(state, db=db)
        nxt = update.get("route")
        if nxt == "__end__":
            break
        seen.append(nxt)
        # Simulate the specialist filling in the channel the rule guards.
        if nxt == "interpreter":
            state["parsed_task"] = {"locations": ["Depot", "Royal London"]}
        elif nxt == "memory":
            state.setdefault("plan_step_log", []).append({"agent": "memory"})
        elif nxt == "planner":
            state["plan"] = {"legs": []}
        elif nxt == "weather":
            state["weather"] = {"flyable": True}
        elif nxt == "geofence":
            state["no_fly_violations"] = []
        elif nxt == "preflight":
            state.setdefault("plan_step_log", []).append({"agent": "preflight"})
        elif nxt == "payload":
            state["payload_status"] = {"manifest": None}
        elif nxt == "dispatch":
            state["live_telemetry"] = {"status": "executing"}
        state["last_routed_to"] = update.get("last_routed_to")
        state.setdefault("route_history", []).append(nxt)

    # Static rules guarantee these 8 fire first, in this exact order.
    expected_prefix = [
        "interpreter",
        "memory",
        "planner",
        "weather",
        "geofence",
        "preflight",
        "payload",
        "dispatch",
    ]
    assert seen[: len(expected_prefix)] == expected_prefix
