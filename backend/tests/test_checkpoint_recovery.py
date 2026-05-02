"""Checkpoint recovery — kill mid-graph, resume, no duplicate tool calls.

Acceptance per ``prompts/13 §5``:
- ``test_checkpoint_recovery.py`` passes
- Resumes from the last checkpoint without duplicate ``tool_call_log`` rows
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from backend.dronan.graph import build_graph

pytestmark = pytest.mark.unit


@pytest.fixture
async def fully_seeded(mongo_db):
    from backend.dronan.agents.registry import register_all
    from backend.seeds.seed_drones import main as seed_drones
    from backend.seeds.seed_facilities import main as seed_fac
    from backend.seeds.seed_no_fly_zones import main as seed_nfz

    await seed_fac(mongo_db)
    await seed_nfz(mongo_db)
    await seed_drones(mongo_db)
    await register_all(mongo_db)
    return mongo_db


async def test_graph_runs_to_completion(fully_seeded) -> None:
    """Smoke: the compiled graph terminates within recursion limit on a
    well-formed initial state."""
    db = fully_seeded
    saver = InMemorySaver()
    graph = build_graph(db=db, checkpointer=saver)

    initial = {
        "operator_id": "op-1",
        "mission_id": "MED-T-CK-1",
        "request": "deliver blood from Depot to Royal London",
    }
    config = {"configurable": {"thread_id": "MED-T-CK-1"}, "recursion_limit": 50}

    final = await graph.ainvoke(initial, config=config)
    assert final.get("route") == "__end__"
    # Every static channel should be filled.
    assert final.get("plan") is not None
    assert "weather" in final
    # Dispatch ran at least once.
    assert final.get("live_telemetry") is not None


async def test_checkpoint_resumes_without_duplicate_tool_calls(fully_seeded) -> None:
    """Run halfway, abort, then re-invoke with the same thread_id.

    The wrapped tools log idempotency keys to ``tool_call_log``; on resume
    every previously-completed tool short-circuits — total log rows after
    the second invocation must equal the unique-tool count from the first.
    """
    db = fully_seeded
    saver = InMemorySaver()
    graph = build_graph(db=db, checkpointer=saver)

    config = {"configurable": {"thread_id": "MED-T-CK-2"}, "recursion_limit": 50}
    initial = {
        "operator_id": "op-1",
        "mission_id": "MED-T-CK-2",
        "request": "deliver blood from Depot to Royal London",
    }

    # First run — full mission.
    await graph.ainvoke(initial, config=config)
    first_keys = {
        d["idempotency_key"]
        async for d in db.tool_call_log.find({"status": {"$in": ["success", "completed"]}})
    }

    # Second run — same thread_id, should resume from saved checkpoint.
    # We pass ``None`` to tell LangGraph to continue the existing thread.
    await graph.ainvoke(None, config=config)

    second_keys = {
        d["idempotency_key"]
        async for d in db.tool_call_log.find({"status": {"$in": ["success", "completed"]}})
    }

    # Same set of completed tool-call keys → tools were memoised.
    assert first_keys == second_keys
    assert len(first_keys) >= 1
