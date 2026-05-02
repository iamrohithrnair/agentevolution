"""AT-7.1 — self-evolution: Take-3 mission time ≤ 90 % × Take-1 (SM-1).

Runs the canonical scenario three times against an in-memory mongomock_motor
database with the deterministic :class:`SimulatedSupervisor`. The simulator
encodes the rehearsal narrative from ``prompts/10`` §13.1: lessons accumulate
across takes, the planner avoids the high-wind corridor on Take-2/3, and
mission time shrinks by ``seconds_saved_per_lesson`` per retrieved lesson.

These assertions are the contract the runner must preserve. When Session A's
real ``dronan.graph.build_supervisor`` ships, swap the simulator for a wrapper
around it (see :func:`dronan.demo.runner.build_simulated_invoke_mission`); the
tests should still pass without edits.
"""

from __future__ import annotations

import pytest

from dronan.demo.charts import render_actual_time_svg
from dronan.demo.runner import run_takes
from dronan.demo.scenario import CANONICAL_SCENARIO


@pytest.mark.asyncio
async def test_take_3_is_at_least_10_percent_faster_than_take_1(mongomock_db):
    """SM-1: Take-3 mission time ≤ 90 % × Take-1."""
    results = await run_takes(mongomock_db, n=3)
    assert len(results) == 3, results

    take1, _take2, take3 = results
    ratio = take3.actual_time_s / take1.actual_time_s
    assert ratio < 0.90, (
        f"SM-1 violated: take3={take3.actual_time_s:.1f}s, take1={take1.actual_time_s:.1f}s, "
        f"ratio={ratio:.3f}"
    )

    # Also verify the experiments collection holds the same numbers
    experiments = await mongomock_db.experiments.find({}).to_list(length=10)
    by_take = {e["take"]: e for e in experiments}
    assert set(by_take) == {1, 2, 3}, by_take.keys()
    assert by_take[3]["actual_time_s"] < by_take[1]["actual_time_s"] * 0.90


@pytest.mark.asyncio
async def test_each_take_writes_at_least_six_lessons(mongomock_db):
    """SM-2: ≥6 cards written to mission_memory per take."""
    results = await run_takes(mongomock_db, n=3)
    for r in results:
        assert r.lessons_added >= CANONICAL_SCENARIO.min_lessons_per_take, r

    total_lessons = await mongomock_db.mission_memory.count_documents(
        {"metadata.tag": CANONICAL_SCENARIO.tag}
    )
    assert total_lessons >= 3 * CANONICAL_SCENARIO.min_lessons_per_take


@pytest.mark.asyncio
async def test_lesson_retrieval_grows_across_takes(mongomock_db):
    """Take-2 and Take-3 should retrieve lessons accumulated in earlier takes.

    This guards against a regression where the runner clears mission_memory
    between takes (``reset_missions_each_take`` should *not* affect lessons).
    """
    results = await run_takes(mongomock_db, n=3)
    assert results[0].lessons_used == 0, "Take-1 should retrieve nothing"
    assert results[1].lessons_used > 0, "Take-2 should retrieve lessons from Take-1"
    assert results[2].lessons_used >= results[1].lessons_used, (
        "Take-3 retrieval should grow monotonically"
    )


@pytest.mark.asyncio
async def test_take_1_reroutes_take_3_does_not(mongomock_db):
    """The narrative from prompts/10 §13.1: lessons make the planner avoid the
    Thames corridor on Take-3, removing the wind-shear-triggered reroute."""
    results = await run_takes(mongomock_db, n=3)
    assert results[0].reroute_count >= 1, "Take-1 should be forced to reroute"
    assert results[2].reroute_count == 0, "Take-3 should avoid the reroute"


@pytest.mark.asyncio
async def test_chart_renders_after_three_takes(mongomock_db):
    """The /analytics SVG chart must render with valid SVG markup."""
    results = await run_takes(mongomock_db, n=3)
    svg = render_actual_time_svg([r.__dict__ for r in results])
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert "polyline" in svg
    # Each take's actual_time_s should be in the rendered text-labels
    for r in results:
        assert f"{r.actual_time_s:.1f}s" in svg


@pytest.mark.asyncio
async def test_chart_handles_empty_takes():
    svg = render_actual_time_svg([])
    assert svg.startswith("<svg")
    assert "No takes recorded yet" in svg


@pytest.mark.asyncio
async def test_runner_preserves_mission_memory_across_takes(mongomock_db):
    """Between takes the runner must clear ``missions`` but never
    ``mission_memory`` — that's the whole evolution mechanism."""
    await run_takes(mongomock_db, n=2)
    n_before = await mongomock_db.mission_memory.count_documents(
        {"metadata.tag": CANONICAL_SCENARIO.tag}
    )
    assert n_before >= 2 * CANONICAL_SCENARIO.min_lessons_per_take

    # Run a third take; mission_memory count should grow, not reset.
    await run_takes(mongomock_db, n=1)
    n_after = await mongomock_db.mission_memory.count_documents(
        {"metadata.tag": CANONICAL_SCENARIO.tag}
    )
    assert n_after > n_before, (n_before, n_after)
