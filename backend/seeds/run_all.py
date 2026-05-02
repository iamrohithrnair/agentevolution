"""Run every seed script against the configured database in order.

Run: ``uv run python -m backend.seeds.run_all``
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from . import (
    create_indexes,
    create_vector_indexes,
    seed_agent_skills,
    seed_demo_memory,
    seed_drones,
    seed_facilities,
    seed_no_fly_zones,
    seed_regulations,
    seed_synthetic_emergencies,
)
from ._common import run


async def main(db: AsyncIOMotorDatabase) -> None:
    """Run every seed script. Order matters for the index/validator tests."""
    print("==> create_indexes"); await create_indexes.main(db)
    print("==> create_vector_indexes"); await create_vector_indexes.main(db)
    print("==> seed_facilities"); await seed_facilities.main(db)
    print("==> seed_no_fly_zones"); await seed_no_fly_zones.main(db)
    print("==> seed_regulations"); await seed_regulations.main(db)
    print("==> seed_drones"); await seed_drones.main(db)
    print("==> seed_demo_memory"); await seed_demo_memory.main(db)
    print("==> seed_agent_skills"); await seed_agent_skills.main(db)
    print("==> seed_synthetic_emergencies"); await seed_synthetic_emergencies.main(db)
    print("done.")


if __name__ == "__main__":
    run(main)
