"""Create / verify every Mongo index defined in ``backend.dronan.bootstrap``.

Run: ``uv run python -m backend.seeds.create_indexes``

The script is idempotent: re-running it just re-asserts the indexes, returning
the same names.
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from backend.dronan.bootstrap import bootstrap

from ._common import run


async def main(db: AsyncIOMotorDatabase) -> dict[str, list[str]]:
    """Create timeseries collections, validators, and B-tree / geo indexes."""
    await bootstrap(db)
    summary: dict[str, list[str]] = {}
    for coll in await db.list_collection_names():
        idx = await db[coll].index_information()
        summary[coll] = sorted(idx.keys())
    print("indexes:")
    for k, v in sorted(summary.items()):
        print(f"  {k}: {v}")
    return summary


if __name__ == "__main__":
    run(main)
