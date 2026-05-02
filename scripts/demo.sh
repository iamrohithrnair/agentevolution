#!/usr/bin/env bash
# Orchestrates a cold-boot of the Dronan demo (Phase 8).
set -euo pipefail

mkdir -p .logs .pids

# Verify Atlas reachable
uv run python -c "from dronan.db import ping; import asyncio; asyncio.get_event_loop().run_until_complete(ping())"

# Start API + LiveKit worker + Next.js, all backgrounded
( make api     > .logs/api.log     2>&1 & echo $! > .pids/api.pid )
( make livekit > .logs/livekit.log 2>&1 & echo $! > .pids/livekit.pid )
( make web     > .logs/web.log     2>&1 & echo $! > .pids/web.pid )

# Wait until healthy
uv run python scripts/wait_healthy.py

# Open the dashboard
if command -v open >/dev/null 2>&1; then
  open "http://localhost:${WEB_PORT:-3000}/dashboard"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:${WEB_PORT:-3000}/dashboard"
fi

echo "Ready. Press Ctrl-C to tear down."
trap 'kill $(cat .pids/*.pid) 2>/dev/null || true' EXIT
wait
