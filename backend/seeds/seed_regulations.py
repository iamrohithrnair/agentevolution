"""Seed UK CAA, FAA Part 107, and EASA Open A1/A2/A3 air-law profiles.

Each profile is written to ``regulations`` and a chunked, embedded copy is
written to ``mission_memory`` with ``kind:"regulation"`` so the Planner /
Replanner can cite it via ``$vectorSearch``.

Run: ``uv run python -m backend.seeds.seed_regulations``
"""

from __future__ import annotations

import re
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from backend.dronan.bootstrap import (
    MEMORY_VALIDATOR,
    REG_VALIDATOR,
    apply_validator,
)
from backend.dronan.config import get_settings

from ._common import bulk_upsert, deterministic_embedding, run, utcnow

PROFILES: list[dict[str, Any]] = [
    {
        "code": "UK_CAA",
        "country": "GB",
        "title": "UK CAA Article 16 / CAP 722 — Open Category",
        "version": "2024.10",
        "max_altitude_m": 120.0,
        "bvlos_allowed": False,
        "night_allowed": True,
        "over_people_allowed": False,
        "max_takeoff_mass_kg": 25.0,
        "notes_md": (
            "## Maximum altitude\nNo more than 120 m AGL.\n\n"
            "## Distance from people\nMaintain ≥ 50 m horizontal separation from "
            "uninvolved people for any drone above 250 g.\n\n"
            "## Night flight\nAllowed with anti-collision lighting.\n\n"
            "## BVLOS\nProhibited under Open Category — requires Specific Category "
            "authorisation.\n"
        ),
    },
    {
        "code": "FAA_PART_107",
        "country": "US",
        "title": "FAA Part 107 — Small UAS",
        "version": "2024.06",
        "max_altitude_m": 121.92,  # 400 ft
        "bvlos_allowed": False,
        "night_allowed": True,
        "over_people_allowed": True,
        "max_takeoff_mass_kg": 24.95,
        "notes_md": (
            "## Maximum altitude\nNo more than 400 ft AGL except within 400 ft "
            "of a structure.\n\n"
            "## Speed\nMax 100 mph (87 kt) ground speed.\n\n"
            "## Visual Line of Sight\nRequired unless waiver.\n\n"
            "## Night operations\nPermitted with anti-collision lighting visible "
            "for 3 statute miles.\n\n"
            "## Operations over people\nAllowed under Categories 1–4 subject to "
            "weight + parachute caveats.\n\n"
            "## Remote ID\nRequired for all UAS subject to FAA registration.\n"
        ),
    },
    {
        "code": "EASA_OPEN_A1",
        "country": "EU",
        "title": "EASA Open Category Subcategory A1",
        "version": "2024.01",
        "max_altitude_m": 120.0,
        "bvlos_allowed": False,
        "night_allowed": True,
        "over_people_allowed": True,
        "max_takeoff_mass_kg": 0.9,
        "notes_md": (
            "## Mass\nUp to 250 g (C0) or up to 900 g (C1).\n\n"
            "## Overflight\nMay fly over uninvolved people but not assemblies.\n\n"
            "## Altitude\n≤ 120 m AGL.\n"
        ),
    },
    {
        "code": "EASA_OPEN_A2",
        "country": "EU",
        "title": "EASA Open Category Subcategory A2",
        "version": "2024.01",
        "max_altitude_m": 120.0,
        "bvlos_allowed": False,
        "night_allowed": True,
        "over_people_allowed": False,
        "max_takeoff_mass_kg": 4.0,
        "notes_md": (
            "## Mass\nUp to 4 kg (C2 class).\n\n"
            "## Distance\nMin 30 m from uninvolved people (5 m in low-speed mode).\n\n"
            "## Pilot competence\nA2 CofC required.\n"
        ),
    },
    {
        "code": "EASA_OPEN_A3",
        "country": "EU",
        "title": "EASA Open Category Subcategory A3",
        "version": "2024.01",
        "max_altitude_m": 120.0,
        "bvlos_allowed": False,
        "night_allowed": True,
        "over_people_allowed": False,
        "max_takeoff_mass_kg": 25.0,
        "notes_md": (
            "## Mass\nUp to 25 kg (C2/C3/C4 + legacy).\n\n"
            "## Distance\nNo overflight of people; min 150 m from residential, "
            "commercial, industrial, or recreational areas.\n"
        ),
    },
]


_HEADING_RE = re.compile(r"^## (.+)$", re.M)


def _chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Yield (heading, body) chunks from a `## heading` markdown blob.

    A trivial chunker — sufficient for the short regulation profiles. The
    plan calls for ``voyage-context-3`` late chunking on bulkier corpora;
    that's deferred to phase 2 because it requires the Voyage client.
    """
    chunks: list[tuple[str, str]] = []
    current_heading: str | None = None
    current: list[str] = []
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            if current_heading is not None:
                chunks.append((current_heading, "\n".join(current).strip()))
            current_heading = m.group(1).strip()
            current = []
        else:
            current.append(line)
    if current_heading is not None:
        chunks.append((current_heading, "\n".join(current).strip()))
    return [(h, b) for h, b in chunks if b]


async def main(db: AsyncIOMotorDatabase) -> dict[str, int]:
    """Upsert regulation profiles + their embedded chunks into ``mission_memory``."""
    await apply_validator(db, "regulations", REG_VALIDATOR)
    await apply_validator(db, "mission_memory", MEMORY_VALIDATOR)

    reg_ops: list[UpdateOne] = []
    mem_ops: list[UpdateOne] = []

    for profile in PROFILES:
        reg_doc = {**profile, "effective_from": utcnow()}
        reg_ops.append(UpdateOne({"code": profile["code"]}, {"$set": reg_doc}, upsert=True))

        for heading, body in _chunk_markdown(profile["notes_md"]):
            text = f"{profile['title']} — {heading}\n\n{body}"
            embedding = deterministic_embedding(text, dim=get_settings().voyage_dim)
            mem_doc = {
                "kind": "regulation",
                "title": f"{profile['title']} — {heading}",
                "text": text,
                "embedding": embedding,
                "embedding_model": "deterministic-1024-v1",
                "metadata": {
                    "region": profile["country"],
                    "tags": ["regulation", profile["code"], heading.lower().replace(" ", "_")],
                },
                "source_collection": "regulations",
                "source_id": profile["code"],
                "created_at": utcnow(),
                "use_count": 0,
                "score_ema": 0.0,
            }
            mem_ops.append(
                UpdateOne(
                    {"source_collection": "regulations", "source_id": profile["code"], "title": mem_doc["title"]},
                    {"$set": mem_doc},
                    upsert=True,
                )
            )

    reg_res = await bulk_upsert(db.regulations, reg_ops)
    mem_res = await bulk_upsert(db.mission_memory, mem_ops)

    reg_total = await db.regulations.count_documents({})
    mem_total = await db.mission_memory.count_documents({"kind": "regulation"})
    print(
        f"regulations: upserted={reg_res['upserted']} "
        f"modified={reg_res['modified']} total={reg_total}"
    )
    print(
        f"mission_memory[regulation]: upserted={mem_res['upserted']} "
        f"modified={mem_res['modified']} total={mem_total}"
    )
    return {
        "regs_upserted": reg_res["upserted"],
        "regs_total": reg_total,
        "mem_upserted": mem_res["upserted"],
        "mem_total": mem_total,
    }


if __name__ == "__main__":
    run(main)
