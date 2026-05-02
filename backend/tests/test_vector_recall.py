"""Vector recall over ``mission_memory`` and ``agent_skills``."""

from __future__ import annotations

import pytest

from backend.dronan.embeddings.voyage import (
    cache_get,
    cache_put,
    deterministic_embedding,
    embed,
)
from backend.dronan.memory import find_peers, recall, write_reflection

pytestmark = pytest.mark.unit


@pytest.fixture
async def seeded(mongo_db):
    from backend.seeds.seed_agent_skills import main as seed_skills
    from backend.seeds.seed_demo_memory import main as seed_memory

    await seed_memory(mongo_db)
    await seed_skills(mongo_db)
    return mongo_db


def test_deterministic_embedding_l2_normalised() -> None:
    vec = deterministic_embedding("hello world", dim=1024)
    norm = sum(x * x for x in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-6
    # Same text → same vector
    again = deterministic_embedding("hello world", dim=1024)
    assert vec == again


async def test_embedding_cache_round_trip(mongo_db) -> None:
    text = "voyage-cache-test"
    assert await cache_get(mongo_db, text) is None
    vec = deterministic_embedding(text, dim=1024)
    await cache_put(mongo_db, text, vec)
    cached = await cache_get(mongo_db, text)
    assert cached == vec


async def test_embed_uses_cache(mongo_db) -> None:
    text = "memoised-text"
    v1 = await embed(text, db=mongo_db)
    v2 = await embed(text, db=mongo_db)
    assert v1 == v2
    # The cache row should exist now.
    cached = await cache_get(mongo_db, text)
    assert cached == v1


async def test_recall_returns_seeded_card(seeded) -> None:
    cards = await recall(seeded, "wind shear west of Royal London", k=3)
    assert cards
    titles = " ".join(c.get("title", "") for c in cards)
    assert "Wind shear" in titles or "wind" in titles.lower()
    # Score is propagated.
    assert cards[0].get("score") is not None


async def test_find_peers_returns_supervisor_for_routing_query(seeded) -> None:
    peers = await find_peers(seeded, "route to a hospital with a payload", k=3)
    assert peers
    agents = [p.get("agent") for p in peers]
    assert any(
        a in {"RoutePlannerAgent", "ReplannerAgent", "SupervisorAgent"}
        for a in agents
    )


async def test_summarise_for_planner_handles_missing_score(mongo_db) -> None:
    from backend.dronan.tools.memory import summarise_for_planner

    cards = [
        {"title": "no score card", "source": "mission_memory", "metadata": {}},
        {"title": "scored card", "source": "agent_skills", "score": 0.87, "metadata": {}},
    ]
    out = await summarise_for_planner(
        db=mongo_db, cards=cards, idempotency_key="sfp-1"
    )
    assert "no score card" in out
    assert "score=n/a" in out
    assert "score=0.870" in out


async def test_write_reflection_inserts_card(seeded) -> None:
    res = await write_reflection(
        seeded,
        mission_id="MED-TEST-1",
        text="The southern corridor is the right alternate when the eastern one closes.",
        title="Southern corridor preference",
    )
    assert res["inserted"] is True
    found = await seeded.mission_memory.find_one(
        {"source_collection": "missions", "source_id": "MED-TEST-1"}
    )
    assert found is not None
    assert found["kind"] == "reflection"
