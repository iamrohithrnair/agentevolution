"""Pre-seed three reflection cards so Take-1 of the demo has a recall surface.

Run: ``uv run python -m backend.seeds.seed_demo_memory``
"""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from backend.dronan.bootstrap import MEMORY_VALIDATOR, apply_validator
from backend.dronan.config import get_settings

from ._common import bulk_upsert, deterministic_embedding, run, utcnow


CARDS: list[dict[str, Any]] = [
    {
        "title": "Wind shear corridor west of Royal London — abort threshold too lax",
        "text": (
            "On MED-0398 we attempted approach via the west corridor at 9.4 m/s "
            "mean wind, gusting 13.8 m/s. Drone1 lost ~7% extra battery in the "
            "approach and was force-rerouted to Newham. Lesson: tighten the "
            "abort threshold to 10 m/s on west-corridor approaches; prefer the "
            "north-east corridor when gust factor exceeds 1.4."
        ),
        "metadata": {
            "region": "London",
            "weather_class": "wind",
            "success": False,
            "severity": "high",
            "lessons": [
                "Increase wind threshold from 12 to 10 m/s for west-corridor approaches.",
                "Prefer north-east corridor when gust factor > 1.4.",
            ],
            "tags": ["wind_shear", "royal_london", "west_corridor"],
        },
        "source_collection": "missions",
        "source_id": "MED-0398",
    },
    {
        "title": "Cold-chain drift on Newham → Whipps Cross blood pack handoff",
        "text": (
            "On MED-0411 the cold-chain bag temperature drifted from 4.1 °C to "
            "6.2 °C during the 9-minute Newham → Whipps Cross hop. Root cause: "
            "ice pack count was at the legal minimum and ambient was 24 °C. "
            "PayloadAgent must add a second ice pack when ambient > 22 °C even "
            "though the static minimum is satisfied."
        ),
        "metadata": {
            "region": "London",
            "weather_class": "clear",
            "success": False,
            "severity": "medium",
            "lessons": [
                "Add a second ice pack when ambient > 22 °C, regardless of static minimum.",
                "Lower the cold-chain alert threshold from 6.0 °C to 5.5 °C.",
            ],
            "tags": ["cold_chain", "blood_pack", "ambient_heat"],
        },
        "source_collection": "missions",
        "source_id": "MED-0411",
    },
    {
        "title": "TFR east London — preferred corridor swap",
        "text": (
            "On MED-0420 a synthetic TFR appeared over east London during "
            "approach. Replanner switched to the southern corridor in 1.8 s, "
            "saving 410 m vs the rerouter's first proposal. The southern "
            "corridor should be the **default** alternate when the eastern "
            "corridor is invalidated by a TFR or weather cell."
        ),
        "metadata": {
            "region": "London",
            "weather_class": "clear",
            "success": True,
            "severity": "low",
            "lessons": [
                "Default alternate corridor for eastern invalidation = southern.",
            ],
            "tags": ["tfr", "replanner", "southern_corridor"],
        },
        "source_collection": "missions",
        "source_id": "MED-0420",
    },
]


async def main(db: AsyncIOMotorDatabase) -> dict[str, int]:
    """Idempotently upsert the canonical demo memory cards."""
    await apply_validator(db, "mission_memory", MEMORY_VALIDATOR)

    ops: list[UpdateOne] = []
    for card in CARDS:
        embedding = deterministic_embedding(card["text"], dim=get_settings().voyage_dim)
        doc = {
            "kind": "reflection",
            "title": card["title"],
            "text": card["text"],
            "embedding": embedding,
            "embedding_model": "deterministic-1024-v1",
            "metadata": card["metadata"],
            "source_collection": card["source_collection"],
            "source_id": card["source_id"],
            "created_at": utcnow(),
            "use_count": 0,
            "score_ema": 0.0,
        }
        ops.append(
            UpdateOne(
                {
                    "kind": "reflection",
                    "source_collection": card["source_collection"],
                    "source_id": card["source_id"],
                },
                {"$set": doc},
                upsert=True,
            )
        )

    res = await bulk_upsert(db.mission_memory, ops)
    total = await db.mission_memory.count_documents({"kind": "reflection"})
    print(
        f"mission_memory[reflection]: upserted={res['upserted']} "
        f"modified={res['modified']} total={total}"
    )
    return {**res, "total": total}


if __name__ == "__main__":
    run(main)
