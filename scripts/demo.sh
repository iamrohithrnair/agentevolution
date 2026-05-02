#!/usr/bin/env bash
# scripts/demo.sh — orchestrates a cold-boot of the Dronan demo (Phase 8).
#
# Boots, in order:
#   1. Atlas reachability check (fail fast).
#   2. FastAPI backend (``make api``).
#   3. LiveKit voice worker — or the ``--text-mode`` REPL when voice keys
#      aren't set (``LIVEKIT_URL`` / ``DEEPGRAM_API_KEY`` / ``ELEVENLABS_API_KEY``
#      missing). The text-mode fallback keeps the demo runnable on a stripped
#      install with no third-party voice creds.
#   4. Next.js dashboard (``make web``).
#   5. Polls until API + frontend are healthy (``scripts/wait_healthy.py``).
#   6. Opens the browser to ``/dashboard``.
#
# Cold-boot SLA: ≤ 60 s on a fresh laptop (AT-8.2). Most of the budget is the
# Next.js first compile + uv resolving the wheel cache.

set -euo pipefail

mkdir -p .logs .pids

# --------------------------------------------------------------------------- #
# 1. Atlas reachability — fail fast if the cluster is unreachable.
# --------------------------------------------------------------------------- #

uv run python -c "
import asyncio
from dronan.db import ping
asyncio.get_event_loop().run_until_complete(ping())
"

# --------------------------------------------------------------------------- #
# 2-4. Background services. Each writes to .logs/<svc>.log and .pids/<svc>.pid.
# --------------------------------------------------------------------------- #

start_bg() {
  local name="$1"
  local cmd="$2"
  ( eval "${cmd}" > ".logs/${name}.log" 2>&1 & echo $! > ".pids/${name}.pid" )
  echo "demo: ${name} started (pid=$(cat ".pids/${name}.pid"))"
}

start_bg api 'make api'

# Voice worker selection: real LiveKit if we have all three keys, text-mode
# REPL otherwise. The fallback path lets us rehearse on aeroplane wifi.
VOICE_KEYS_PRESENT="$(uv run python -c "
from dronan.config import get_settings
print('1' if get_settings().voice_keys_present() else '0')
" 2>/dev/null || echo '0')"

if [[ "${VOICE_KEYS_PRESENT}" == "1" ]]; then
  echo "demo: voice keys present → starting LiveKit worker"
  start_bg livekit 'make livekit'
else
  echo "demo: voice keys absent → starting text-mode REPL fallback"
  start_bg livekit 'uv run python -m dronan.voice.livekit_worker dev --text-mode'
fi

start_bg web 'make web'

# --------------------------------------------------------------------------- #
# 5. Wait until healthy.
# --------------------------------------------------------------------------- #

uv run python scripts/wait_healthy.py

# --------------------------------------------------------------------------- #
# 6. Open the dashboard.
# --------------------------------------------------------------------------- #

DASHBOARD_URL="http://localhost:${WEB_PORT:-3000}/dashboard"
if command -v open >/dev/null 2>&1; then
  open "${DASHBOARD_URL}"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "${DASHBOARD_URL}"
else
  echo "demo: open ${DASHBOARD_URL} in your browser"
fi

echo "demo: ready (text-mode=$([[ "${VOICE_KEYS_PRESENT}" == "1" ]] && echo "no" || echo "yes")). Press Ctrl-C to tear down."
trap 'kill $(cat .pids/*.pid 2>/dev/null) 2>/dev/null || true' EXIT
wait
