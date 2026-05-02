"""Voice layer for Dronan.

Three modules:

- :mod:`dronan.voice.prompts` — system prompts for the Mission Control persona,
  narration templates keyed by ``flight_logs.event``, and signature prompts.
  No heavy imports; safe to load anywhere.
- :mod:`dronan.voice.narrator_stream` — async loop tailing ``flight_logs``
  Change Streams and pushing utterances through a ``speaker`` callable.
  Speaker is injected so tests can substitute a fake.
- :mod:`dronan.voice.livekit_worker` — the LiveKit Agents worker entry point.
  Imports ``livekit-agents`` (optional dep ``[voice]`` extra). When LiveKit
  is unavailable, the module still imports — only the ``main`` entrypoint
  raises. ``--text-mode`` skips LiveKit entirely.

Phase 6 of ``prompts/13-implementation-plan.md``. Acceptance test AT-6.1
lives at ``backend/tests/test_livekit_smoke.py``.
"""

from dronan.voice import narrator_stream, prompts

__all__ = ["narrator_stream", "prompts"]
