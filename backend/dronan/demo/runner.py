"""Runner — invoke the canonical scenario N times against a clean ``missions``
slate while preserving ``mission_memory`` across takes.

Per ``prompts/13`` §7 the runner exists to *prove* SM-1 (Take-3 ≤ 90 % × Take-1)
and SM-2 (≥6 lessons per take) without LLM nondeterminism in the inputs.
We do that with a :class:`SimulatedSupervisor` that:

1. Retrieves the existing lesson cards for this scenario tag (in-Python
   cosine search over ``mission_memory`` — see :func:`retrieve_lessons_local`).
2. Computes ``actual_time_s = baseline - (n_lessons * seconds_saved_per_lesson)``
   plus a tiny seeded jitter, so the trajectory is monotonically decreasing
   but not constant.
3. Inserts ``min_lessons_per_take`` lesson cards into ``mission_memory`` so
   the next take retrieves them. Cards are deterministic per take.
4. Inserts the per-take aggregate into ``experiments``.

In production, swap :func:`build_simulated_invoke_mission` with a wrapper
around Session A's ``dronan.graph.build_supervisor(db).ainvoke``. The
contract — async ``invoke_mission(state) -> dict`` — is the integration
boundary; the runner's loop logic stays identical.

Pure-Python local retrieval also satisfies AT-7.2 (precision @ 5 ≥ 0.8) without
hitting Atlas Vector Search; ``backend/tests/test_memory_recall.py`` exercises
:func:`retrieve_lessons_local` against seeded lessons.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

from dronan.demo.scenario import CANONICAL_SCENARIO, Scenario

log = logging.getLogger("dronan.demo.runner")

# --------------------------------------------------------------------------- #
# Per-take result row (mirrors ``experiments`` doc shape in prompts/10 §11.1)
# --------------------------------------------------------------------------- #


@dataclass
class TakeResult:
    """One row in the ``experiments`` collection."""

    scenario_id: str
    take: int
    actual_time_s: float
    actual_distance_m: float
    reroute_count: int
    success: bool
    lessons_added: int
    lessons_used: int
    mission_id: str
    ts: float


InvokeMission = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


# --------------------------------------------------------------------------- #
# In-Python cosine retrieval (used by SimulatedSupervisor + AT-7.2 test)
# --------------------------------------------------------------------------- #


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    num = sum(x * y for x, y in zip(a, b, strict=False))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    if da == 0.0 or db == 0.0:
        return 0.0
    return num / (da * db)


async def retrieve_lessons_local(
    db: Any,
    *,
    query_embedding: list[float],
    k: int = 5,
    tag: str | None = None,
    region: str | None = None,
) -> list[dict[str, Any]]:
    """Top-K ``mission_memory`` retrieval by cosine similarity in Python.

    Used for offline rehearsal, the deterministic test path, and as a
    fallback when Atlas Vector Search is unreachable. The production path
    will live in Session A's ``dronan.tools.memory`` module and use the
    ``mission_memory_vec`` index — keep this signature aligned.

    Filters
    -------
    - ``metadata.deprecated != True``
    - ``tag == metadata.tag`` (when provided) — used to scope to one scenario.
    - ``metadata.region == region`` (when provided).
    """
    query: dict[str, Any] = {"metadata.deprecated": {"$ne": True}}
    if tag is not None:
        query["metadata.tag"] = tag
    if region is not None:
        query["metadata.region"] = region

    candidates: list[tuple[float, dict[str, Any]]] = []
    cursor = db.mission_memory.find(query)
    async for doc in cursor:
        emb = doc.get("embedding") or []
        if not isinstance(emb, list):
            continue
        candidates.append((_cosine(query_embedding, emb), doc))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [doc for _score, doc in candidates[:k]]


# --------------------------------------------------------------------------- #
# Simulated supervisor — the offline path for tests + rehearsals
# --------------------------------------------------------------------------- #


def _det_embedding(seed: str, dim: int = 16) -> list[float]:
    """Deterministic pseudo-random unit vector keyed by ``seed``.

    Lessons embedded with the same seed string land near each other in
    cosine space; lessons with different seeds are roughly orthogonal.
    Used by both the SimulatedSupervisor (for write-side embeddings) and
    the test (for query embeddings).
    """
    rng = random.Random(seed)
    raw = [rng.gauss(0.0, 1.0) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


class SimulatedSupervisor:
    """Deterministic stand-in for Session A's LangGraph supervisor.

    Encodes the rehearsal narrative from ``prompts/10`` §13:

    * Take-1: cold cluster, no lessons retrieved → ``baseline_actual_time_s``.
    * Take-N: lessons accumulated → time shrinks linearly with ``n_lessons``,
      capped at the ``min_lessons_per_take * seconds_saved_per_lesson`` floor.

    The supervisor also writes ≥ ``min_lessons_per_take`` lesson cards on
    every completed mission (SM-2). Card embeddings cluster around the
    scenario tag so retrieval picks them up on the next take.
    """

    def __init__(
        self,
        scenario: Scenario,
        *,
        seed: int = 42,
        embedding_dim: int = 16,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.scenario = scenario
        self.embedding_dim = embedding_dim
        self.clock = clock
        self._rng = random.Random(seed)

    def _query_embedding(self) -> list[float]:
        return _det_embedding(f"{self.scenario.tag}:query", self.embedding_dim)

    def _lesson_embedding(self, take: int, idx: int) -> list[float]:
        # Lessons cluster tightly around the query embedding for this scenario,
        # but each lesson has a tiny per-card jitter so order is stable.
        rng = random.Random(f"{self.scenario.tag}:t{take}:i{idx}")
        base = self._query_embedding()
        return [b + rng.gauss(0.0, 0.05) for b in base]

    async def invoke(self, state: dict[str, Any], db: Any) -> dict[str, Any]:
        """Run one simulated mission. Returns the post-mission state dict."""
        mission_id = state["mission_id"]
        take = int(state.get("take", 1))

        # 1. Retrieve relevant lessons
        retrieved = await retrieve_lessons_local(
            db,
            query_embedding=self._query_embedding(),
            k=5,
            tag=self.scenario.tag,
        )
        lessons_used = len(retrieved)

        # 2. Plan: time shrinks with retrieved lessons
        per_lesson = self.scenario.seconds_saved_per_lesson
        baseline = self.scenario.baseline_actual_time_s
        # Floor matches the class docstring: at most ``min_lessons_per_take``
        # lessons' worth of speedup. The earlier ``* 2`` made the floor
        # negative (240 - 6*2*24 = -48), letting actual_time_s drift below
        # zero on aggressive lesson counts.
        floor = baseline - (self.scenario.min_lessons_per_take * per_lesson)
        actual_time_s = max(floor, baseline - lessons_used * per_lesson)
        # Tiny jitter so each take's number isn't identical when lessons_used==0
        actual_time_s += self._rng.uniform(-1.5, 1.5)

        # Distance + reroute count: Take-1 reroutes once due to wind-shear;
        # later takes don't (because the planner avoids the corridor).
        reroute_count = 1 if lessons_used == 0 else 0
        actual_distance_m = 13_400.0 if reroute_count else 11_400.0

        # 3. Persist mission
        mission_doc = {
            "_id": mission_id,
            "scenario_id": self.scenario.id,
            "operator_id": state.get("operator_id", "demo"),
            "take": take,
            "status": "completed",
            "actual_time_s": actual_time_s,
            "actual_distance_m": actual_distance_m,
            "reroute_count": reroute_count,
            "weather_class": self.scenario.weather_class,
            "region": self.scenario.region,
            "ts_started": self.clock() - actual_time_s,
            "ts_completed": self.clock(),
            "lessons_used": [doc["_id"] for doc in retrieved],
        }
        await db.missions.insert_one(mission_doc)

        # 4. Write at least min_lessons_per_take lesson cards (SM-2)
        n_to_write = self.scenario.min_lessons_per_take
        kinds = [
            "corridor_avoidance",
            "weather_threshold",
            "operator_preference",
            "facility_quirk",
            "tool_failure_pattern",
            "agent_underperformance",
            "regulation_clarification",
            "payload_constraint",
        ]
        lesson_docs = []
        for i in range(n_to_write):
            kind = kinds[i % len(kinds)]
            lesson_id = f"lsn-{mission_id}-{kind}-{i}"
            summary = (
                f"[take={take} {kind}] Avoid Thames corridor 80-120m on SW winds >18kt"
                if kind == "corridor_avoidance"
                else f"[take={take} {kind}] heuristic learned from {mission_id}"
            )
            lesson_docs.append(
                {
                    "_id": lesson_id,
                    "kind": kind,
                    "summary": summary,
                    "embedding": self._lesson_embedding(take, i),
                    "embedding_model": "sim-v1",
                    "metadata": {
                        "mission_id": mission_id,
                        "tag": self.scenario.tag,
                        "region": self.scenario.region,
                        "weather_class": self.scenario.weather_class,
                        "severity": "advice",
                        "deprecated": False,
                        "retrieval_count": 0,
                        "usefulness_score": 0.5,
                        "evidence_message_ids": [f"msg-{mission_id}-evt-{i}"],
                    },
                    "created_at": self.clock(),
                }
            )
        if lesson_docs:
            await db.mission_memory.insert_many(lesson_docs)

        # 5. Audit messages — used by AT-7.2 evidence check downstream
        audit_msgs = []
        for i in range(n_to_write):
            audit_msgs.append(
                {
                    "_id": f"msg-{mission_id}-evt-{i}",
                    "mission_id": mission_id,
                    "from_agent": "supervisor",
                    "kind": "trace",
                    "ts": self.clock(),
                    "payload": {"step": i, "scenario_tag": self.scenario.tag},
                }
            )
        if audit_msgs:
            await db.agent_messages.insert_many(audit_msgs)

        return {
            "mission_id": mission_id,
            "take": take,
            "actual_time_s": actual_time_s,
            "actual_distance_m": actual_distance_m,
            "reroute_count": reroute_count,
            "success": True,
            "lessons_added": n_to_write,
            "lessons_used": lessons_used,
        }


def build_simulated_invoke_mission(
    scenario: Scenario,
    db: Any,
    *,
    seed: int = 42,
    clock: Callable[[], float] = time.time,
) -> InvokeMission:
    """Factory returning an ``InvokeMission`` callable backed by the simulator.

    Use this in tests and the offline rehearsal path. Production swaps in
    a wrapper around ``dronan.graph.build_supervisor(db).ainvoke``.
    """
    sup = SimulatedSupervisor(scenario, seed=seed, clock=clock)

    async def _invoke(state: dict[str, Any]) -> dict[str, Any]:
        return await sup.invoke(state, db)

    return _invoke


# --------------------------------------------------------------------------- #
# The take-loop runner
# --------------------------------------------------------------------------- #


async def run_takes(
    db: Any,
    *,
    n: int = 3,
    scenario: Scenario | None = None,
    invoke_mission: InvokeMission | None = None,
    operator_id: str = "demo",
    clock: Callable[[], float] = time.time,
    reset_missions_each_take: bool = True,
) -> list[TakeResult]:
    """Run ``scenario`` ``n`` times. Returns one :class:`TakeResult` per take.

    Side effects per take:

    1. Optionally clear ``missions`` for this ``scenario_id`` (default True;
       preserves ``mission_memory`` so lessons accumulate).
    2. Invoke ``invoke_mission`` with a fresh ``mission_id``.
    3. Read the resulting ``missions`` doc back to compute aggregates.
    4. Insert the aggregate row into ``experiments``.
    """
    scenario = scenario or CANONICAL_SCENARIO
    invoke_mission = invoke_mission or build_simulated_invoke_mission(scenario, db, clock=clock)

    results: list[TakeResult] = []
    for take in range(1, n + 1):
        if reset_missions_each_take:
            await db.missions.delete_many({"scenario_id": scenario.id})
            await db.agent_messages.delete_many({"mission_id": {"$regex": f"^take-{scenario.id}-"}})

        mission_id = f"take-{scenario.id}-{take}-{uuid.uuid4().hex[:8]}"
        state = {
            "mission_id": mission_id,
            "operator_id": operator_id,
            "scenario_id": scenario.id,
            "take": take,
            "request": scenario.request_text,
        }
        out = await invoke_mission(state)

        result = TakeResult(
            scenario_id=scenario.id,
            take=take,
            actual_time_s=float(out["actual_time_s"]),
            actual_distance_m=float(out["actual_distance_m"]),
            reroute_count=int(out["reroute_count"]),
            success=bool(out["success"]),
            lessons_added=int(out["lessons_added"]),
            lessons_used=int(out["lessons_used"]),
            mission_id=mission_id,
            ts=clock(),
        )
        results.append(result)
        await db.experiments.insert_one(asdict(result))
        log.info(
            "take=%d scenario=%s actual_time=%.1fs lessons_used=%d lessons_added=%d",
            take,
            scenario.id,
            result.actual_time_s,
            result.lessons_used,
            result.lessons_added,
        )

    return results


# --------------------------------------------------------------------------- #
# Convenience CLI: ``uv run python -m dronan.demo.runner``
# --------------------------------------------------------------------------- #


async def _main_async(n: int, *, keep_memory: bool = False) -> None:  # pragma: no cover — invoked manually
    try:
        from motor.motor_asyncio import AsyncIOMotorClient  # noqa: PLC0415
    except ImportError as e:
        raise SystemExit("motor required for the runner CLI") from e

    from dronan.config import get_settings  # noqa: PLC0415

    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_db]
    try:
        if not keep_memory:
            await db.mission_memory.delete_many({"metadata.tag": CANONICAL_SCENARIO.tag})
        results = await run_takes(db, n=n)
        for r in results:
            print(
                f"take={r.take:>2}  actual_time={r.actual_time_s:6.1f}s  "
                f"lessons_used={r.lessons_used}  lessons_added={r.lessons_added}"
            )
    finally:
        client.close()


def main() -> None:  # pragma: no cover — manual invocation only
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Run the canonical Dronan scenario N times.")
    parser.add_argument("-n", "--takes", type=int, default=3)
    parser.add_argument(
        "--keep-memory",
        action="store_true",
        help="Skip the pre-run mission_memory reset (so a previous take's lessons "
        "carry over). Mirrors the KEEP_MEMORY=1 env in scripts/run_takes.sh.",
    )
    args = parser.parse_args()
    asyncio.run(_main_async(args.takes, keep_memory=args.keep_memory))


if __name__ == "__main__":
    main()
