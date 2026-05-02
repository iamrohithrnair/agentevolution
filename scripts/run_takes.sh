#!/usr/bin/env bash
# scripts/run_takes.sh — convenience wrapper around the canonical scenario runner.
#
# Used during rehearsal to produce the Take-1 / Take-2 / Take-3 trajectory
# offline (no LiveKit, no real LLM). Wraps ``python -m dronan.demo.runner``.
#
# Usage:
#   ./scripts/run_takes.sh                    # 3 takes (default)
#   N=5 ./scripts/run_takes.sh                # 5 takes
#   KEEP_MEMORY=1 ./scripts/run_takes.sh      # don't reset mission_memory tag at start

set -euo pipefail

N="${N:-3}"
KEEP_MEMORY="${KEEP_MEMORY:-0}"

if [[ "${KEEP_MEMORY}" != "1" ]]; then
  echo "run_takes: clearing mission_memory for the canonical scenario tag"
  uv run python -c "
import asyncio
from dronan.config import get_settings
from dronan.demo.scenario import CANONICAL_SCENARIO

async def _go():
    s = get_settings()
    if not s.mongodb_uri:
        print('skipping reset — MONGODB_URI not configured')
        return
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(s.mongodb_uri, serverSelectionTimeoutMS=5000)
    db = client[s.mongodb_db]
    res = await db.mission_memory.delete_many({'metadata.tag': CANONICAL_SCENARIO.tag})
    await db.experiments.delete_many({'scenario_id': CANONICAL_SCENARIO.id})
    client.close()
    print(f'cleared {res.deleted_count} mission_memory cards')

asyncio.run(_go())
"
fi

echo "run_takes: running ${N} takes…"
# Always pass --keep-memory through so the runner doesn't undo whatever
# decision the shell script made above (the runner used to unconditionally
# wipe mission_memory.metadata.tag, which silently neutralised KEEP_MEMORY=1).
RUNNER_ARGS=(-n "${N}" --keep-memory)
uv run python -m dronan.demo.runner "${RUNNER_ARGS[@]}"
