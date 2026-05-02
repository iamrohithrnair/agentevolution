# Dronan demo assets

This directory holds binary artefacts referenced by `docs/DEMO_SCRIPT.md`. The
binaries themselves are **not** committed — they are too large for the repo and
are recreated per-rehearsal.

## Required files

### `assets/demo-fallback.mp4`

A 90-second screen recording of a fully successful end-to-end demo, captured
during the T-24h rehearsal (see `docs/DEMO_SCRIPT.md` §6). Used as the on-stage
failover if the live demo derails.

**How to record (T-24h rehearsal):**

```bash
# 1. Boot a clean demo, make sure all eight Atlas Vector Search indexes are READY.
make demo

# 2. Start the screen recorder (e.g. macOS QuickTime "New Screen Recording")
#    targeting the Next.js dashboard tab at http://localhost:3000/dashboard.

# 3. Run the canonical scenario three times so the take-loop chart populates.
./scripts/run_takes.sh

# 4. Run the recovery rehearsal so the kill/resume is captured.
./scripts/rehearse_recovery.sh

# 5. Stop the recording, trim to 90 s, encode at 1080p H.264, save as
#    assets/demo-fallback.mp4.
```

The fallback video must include voice narration; if voice keys are unavailable
during the rehearsal, dub the narration in post using ElevenLabs Turbo v2.5
with the same `MISSION_CONTROL_SYSTEM` persona prompt from
`backend/dronan/voice/prompts.py`.

## Files that should never be committed

- `assets/demo-fallback.mp4` — too large, regenerated per rehearsal.
- `assets/dryrun-take*.mp4` — rehearsal recordings.
- `*.wav`, `*.flac`, `*.mov`, `*.m4a` — any raw recording assets.

These are excluded by the repo-root `.gitignore`.
