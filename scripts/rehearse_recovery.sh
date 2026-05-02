#!/usr/bin/env bash
# scripts/rehearse_recovery.sh — kill the LiveKit worker mid-mission and assert
# that a replacement worker resumes the LangGraph thread within 8 s (SM-5).
#
# This is the AT-8.1 acceptance test from prompts/12. It assumes:
#   1. ``make demo`` (or ``scripts/demo.sh``) is already running and healthy.
#   2. A canonical mission has been dispatched; the LiveKit worker is in the
#      middle of streaming narration and accepting voice commands.
#   3. ``langgraph-checkpoint-mongodb`` is wired to the supervisor so a fresh
#      worker can resume by ``thread_id`` (Session A's responsibility).
#
# The script measures **time-to-first-new-tool-call** after the kill: the
# wall-clock between SIGKILL and the next ``tool_call_log`` row written by the
# replacement worker for the same mission. SM-5 requires this to be ≤ 8 s.
#
# Usage:
#   T_KILL=90 ./scripts/rehearse_recovery.sh                   # default 90 s into the mission
#   MISSION_ID=mission-xyz ./scripts/rehearse_recovery.sh      # target a specific mission
#   ASSERT_RESUME_S=8 ./scripts/rehearse_recovery.sh           # SM-5 threshold (seconds)
#
# Side effects:
#   - ``kill -9`` on the process matched by ``LIVEKIT_PROCESS_PATTERN``.
#   - Restarts the worker in the background, logging to ``.logs/livekit.log``.
#   - Writes a JSON summary to ``.logs/rehearse_recovery.json``.

set -euo pipefail

# --------------------------------------------------------------------------- #
# Tunables
# --------------------------------------------------------------------------- #

T_KILL="${T_KILL:-90}"
ASSERT_RESUME_S="${ASSERT_RESUME_S:-8}"
LIVEKIT_PROCESS_PATTERN="${LIVEKIT_PROCESS_PATTERN:-dronan.voice.livekit_worker}"
SUMMARY_FILE="${SUMMARY_FILE:-.logs/rehearse_recovery.json}"
WORKER_LOG="${WORKER_LOG:-.logs/livekit.log}"
MAX_WAIT_S="${MAX_WAIT_S:-30}"

mkdir -p .logs .pids

# --------------------------------------------------------------------------- #
# Resolve the active mission_id
# --------------------------------------------------------------------------- #

if [[ -z "${MISSION_ID:-}" ]]; then
  MISSION_ID="$(uv run python -c "
import asyncio, sys
from dronan.config import get_settings
try:
    from motor.motor_asyncio import AsyncIOMotorClient
except ImportError:
    print('motor required to resolve mission_id; install with uv sync', file=sys.stderr)
    sys.exit(2)

async def _go():
    s = get_settings()
    if not s.mongodb_uri:
        print('MONGODB_URI not configured', file=sys.stderr)
        sys.exit(2)
    client = AsyncIOMotorClient(s.mongodb_uri, serverSelectionTimeoutMS=5000)
    db = client[s.mongodb_db]
    doc = await db.missions.find_one(
        {'status': {'\$in': ['in_transit', 'assigned', 'dispatched', 'planning']}},
        sort=[('created_at', -1)],
    )
    client.close()
    if not doc:
        print('no active mission found in any of in_transit/assigned/dispatched/planning', file=sys.stderr)
        sys.exit(2)
    print(doc['_id'])

asyncio.run(_go())
")"
fi

if [[ -z "${MISSION_ID}" ]]; then
  echo "fatal: could not resolve MISSION_ID" >&2
  exit 2
fi

echo "rehearse_recovery: mission_id=${MISSION_ID} t_kill=${T_KILL}s threshold=${ASSERT_RESUME_S}s"

# --------------------------------------------------------------------------- #
# Wait until T+kill seconds into the mission
# --------------------------------------------------------------------------- #

# T+kill is measured from "now" (script start), not from mission start, so
# the operator has reproducible control over when the kill fires during a
# rehearsal.
echo "rehearse_recovery: waiting ${T_KILL} s before SIGKILL…"
sleep "${T_KILL}"

# --------------------------------------------------------------------------- #
# Capture pre-kill tool-call high water mark
# --------------------------------------------------------------------------- #

LAST_TS_BEFORE="$(uv run python -c "
import asyncio
from dronan.config import get_settings
from motor.motor_asyncio import AsyncIOMotorClient

async def _go():
    s = get_settings()
    client = AsyncIOMotorClient(s.mongodb_uri, serverSelectionTimeoutMS=5000)
    db = client[s.mongodb_db]
    doc = await db.tool_call_log.find_one(
        {'mission_id': '${MISSION_ID}'}, sort=[('ts', -1)],
    )
    client.close()
    print(doc['ts'] if doc else 0.0)

asyncio.run(_go())
")"

echo "rehearse_recovery: last tool_call_log.ts before kill = ${LAST_TS_BEFORE}"

# --------------------------------------------------------------------------- #
# kill -9 the worker(s) matching the pattern
# --------------------------------------------------------------------------- #

# Use Python for portable sub-second epoch — BSD date(1) on macOS does not
# support the %N specifier and would emit a literal "1620000000.%N" that
# float() rejects downstream.
KILL_AT="$(uv run python -c "import time; print(f'{time.time():.6f}')")"
PIDS="$(pgrep -f "${LIVEKIT_PROCESS_PATTERN}" || true)"
if [[ -z "${PIDS}" ]]; then
  echo "fatal: no process matches '${LIVEKIT_PROCESS_PATTERN}'" >&2
  exit 3
fi

echo "rehearse_recovery: SIGKILL pids=${PIDS} at ts=${KILL_AT}"
# shellcheck disable=SC2086
kill -9 ${PIDS}

# --------------------------------------------------------------------------- #
# Restart the worker in the background
#
# Mirror demo.sh's voice-key gating so a text-mode rehearsal restarts the
# replacement worker with --text-mode (otherwise it would either fail to
# connect to LiveKit or SystemExit immediately when the [voice] extras are
# missing).
# --------------------------------------------------------------------------- #

VOICE_KEYS_PRESENT="$(uv run python -c "
from dronan.config import get_settings
print('1' if get_settings().voice_keys_present() else '0')
" 2>/dev/null || echo '0')"

if [[ "${VOICE_KEYS_PRESENT}" == "1" ]]; then
  RESTART_CMD=(uv run python -m dronan.voice.livekit_worker dev)
else
  echo "rehearse_recovery: voice keys absent → restarting worker in --text-mode"
  RESTART_CMD=(uv run python -m dronan.voice.livekit_worker dev --text-mode)
fi

echo "rehearse_recovery: restarting worker → ${WORKER_LOG}"
( "${RESTART_CMD[@]}" > "${WORKER_LOG}" 2>&1 & echo $! > .pids/livekit.pid )

# --------------------------------------------------------------------------- #
# Poll tool_call_log for the first new row after KILL_AT
# --------------------------------------------------------------------------- #

echo "rehearse_recovery: polling tool_call_log for new rows (max ${MAX_WAIT_S}s)…"

NEW_TS="$(uv run python -c "
import asyncio, time
from dronan.config import get_settings
from motor.motor_asyncio import AsyncIOMotorClient

KILL_AT = float('${KILL_AT}')
MAX_WAIT = float('${MAX_WAIT_S}')

async def _go():
    s = get_settings()
    client = AsyncIOMotorClient(s.mongodb_uri, serverSelectionTimeoutMS=5000)
    db = client[s.mongodb_db]
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        doc = await db.tool_call_log.find_one(
            {'mission_id': '${MISSION_ID}', 'ts': {'\$gt': KILL_AT}},
            sort=[('ts', 1)],
        )
        if doc:
            client.close()
            print(doc['ts'])
            return
        await asyncio.sleep(0.25)
    client.close()
    print('TIMEOUT')

asyncio.run(_go())
")"

# --------------------------------------------------------------------------- #
# Compute resume time, write summary, exit non-zero if SM-5 violated
# --------------------------------------------------------------------------- #

if [[ "${NEW_TS}" == "TIMEOUT" ]]; then
  echo "rehearse_recovery: FAIL — no new tool_call_log row within ${MAX_WAIT_S}s"
  cat <<EOF > "${SUMMARY_FILE}"
{
  "mission_id": "${MISSION_ID}",
  "kill_at": ${KILL_AT},
  "first_new_tool_call_at": null,
  "resume_seconds": null,
  "threshold_seconds": ${ASSERT_RESUME_S},
  "passed": false,
  "reason": "TIMEOUT after ${MAX_WAIT_S}s"
}
EOF
  exit 1
fi

RESUME_S="$(uv run python -c "print(float('${NEW_TS}') - float('${KILL_AT}'))")"
PASSED="false"
if uv run python -c "import sys; sys.exit(0 if float('${RESUME_S}') <= float('${ASSERT_RESUME_S}') else 1)"; then
  PASSED="true"
fi

cat <<EOF > "${SUMMARY_FILE}"
{
  "mission_id": "${MISSION_ID}",
  "kill_at": ${KILL_AT},
  "first_new_tool_call_at": ${NEW_TS},
  "resume_seconds": ${RESUME_S},
  "threshold_seconds": ${ASSERT_RESUME_S},
  "passed": ${PASSED}
}
EOF

if [[ "${PASSED}" == "true" ]]; then
  printf "rehearse_recovery: PASS — resumed in %.2fs (threshold ≤ %s s)\n" "${RESUME_S}" "${ASSERT_RESUME_S}"
  exit 0
else
  printf "rehearse_recovery: FAIL — resumed in %.2fs (> %s s)\n" "${RESUME_S}" "${ASSERT_RESUME_S}"
  exit 1
fi
