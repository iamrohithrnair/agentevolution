"""Smoke test for Phase 6 — LiveKit voice loop (AT-6.1).

The full prompt-spec smoke (``prompts/06`` §11) feeds a fixture WAV through a
real LiveKit room and asserts a TTS chunk arrives within 1.5 s. That's an
integration test — it needs LiveKit Cloud, Deepgram, ElevenLabs, and a
real Atlas. CI doesn't have those keys, so this file does the next best thing:

1. Asserts the worker module imports cleanly with the optional ``[voice]``
   extras absent (the failure mode we ship to demo laptops without keys).
2. Asserts ``--text-mode`` REPL functions without LiveKit and without
   Session A's ``dronan.graph`` (the cross-session integration boundary).
3. Drives :class:`~dronan.voice.narrator_stream.NarratorStream` end-to-end
   against an in-memory motor mock and asserts:

   - The fake speaker is invoked with the rendered narration text.
   - Same-kind events within the debounce window are coalesced.
   - Barge-in suppresses narration scheduled within the suppression window.

The integration variant of this test (``test_livekit_smoke_live.py``) is
gated on ``@pytest.mark.live_voice`` and excluded from CI by default; run
manually before each demo rehearsal per ``prompts/13`` §10 (Phase 8 exit
criteria AT-8.1 / AT-8.2).
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Awaitable, Callable

import pytest

# --------------------------------------------------------------------------- #
# 1. Module-import smoke
# --------------------------------------------------------------------------- #


def test_voice_module_imports_without_livekit():
    """The package must load even when ``livekit-agents`` isn't installed."""
    from dronan import voice  # noqa: F401
    from dronan.voice import livekit_worker, narrator_stream, prompts  # noqa: F401

    assert hasattr(livekit_worker, "main")
    assert hasattr(livekit_worker, "agent_entrypoint")
    assert callable(livekit_worker.text_mode_repl)
    # The CLI flag must work even if LiveKit is missing
    assert isinstance(livekit_worker.LIVEKIT_AVAILABLE, bool)


def test_mission_control_prompt_is_terse():
    """The system prompt should be under 500 words (TTS budget concern)."""
    from dronan.voice.prompts import MISSION_CONTROL_SYSTEM

    assert len(MISSION_CONTROL_SYSTEM.split()) < 500
    assert "Mission Control" in MISSION_CONTROL_SYSTEM


def test_narration_templates_cover_demo_events():
    """Every event named in ``prompts/06`` §5 must have a template."""
    from dronan.voice.prompts import NARRATION_TEMPLATES

    required = {
        "takeoff",
        "waypoint_reached",
        "obstacle",
        "reroute",
        "delivered",
        "battery_low",
        "weather_alert",
        "no_fly_violation",
        "anomaly",
        "landed",
    }
    assert required <= set(NARRATION_TEMPLATES.keys())


def test_render_narration_handles_missing_keys():
    from dronan.voice.prompts import render_narration

    # Happy path
    assert render_narration("takeoff", {"drone": "Drone 1", "from_": "Depot"}) == (
        "Drone 1 is wheels up from Depot."
    )
    # Missing keys → fall back to message
    assert render_narration("takeoff", {"drone": "Drone 1", "message": "fallback"}) == "fallback"
    # Missing keys, no message → readable default
    rendered = render_narration("anomaly", {})
    assert rendered is not None and "Anomaly" in rendered
    # Unknown event → None (silent drop)
    assert render_narration("unknown", {}) is None


# --------------------------------------------------------------------------- #
# 2. Text-mode REPL fallback (no LiveKit, no Session A graph)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_text_mode_repl_echoes_when_graph_missing(monkeypatch):
    """Without ``dronan.graph`` and Mongo, REPL must echo input cleanly."""
    from dronan.voice import livekit_worker

    # Force the supervisor builder to raise — same path as 'graph not landed'
    def _raise(_db):
        raise ImportError("dronan.graph not yet implemented")

    monkeypatch.setattr(livekit_worker, "_build_supervisor", _raise)
    monkeypatch.setattr(livekit_worker, "MOTOR_AVAILABLE", False)

    reader = io.StringIO("dispatch blood now\n:q\n")
    writer = io.StringIO()
    await livekit_worker.text_mode_repl(reader=reader, writer=writer)

    output = writer.getvalue()
    assert "(echo) dispatch blood now" in output
    assert "supervisor" not in output.lower() or "unavailable" in output.lower()


# --------------------------------------------------------------------------- #
# 3. Narrator stream behaviour (the meat of the AT-6.1 smoke)
# --------------------------------------------------------------------------- #


class _Clock:
    """Manually-advanced clock so tests are deterministic."""

    def __init__(self) -> None:
        self.now: float = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _make_speaker() -> tuple[list[tuple[str, dict]], Callable[[str, dict], Awaitable[None]]]:
    calls: list[tuple[str, dict]] = []

    async def speaker(text: str, meta: dict) -> None:
        calls.append((text, meta))

    return calls, speaker


@pytest.mark.asyncio
async def test_narrator_handle_event_renders_takeoff(mongomock_db):
    """Happy path: a takeoff doc renders + speaker is invoked once."""
    from dronan.voice.narrator_stream import NarratorStream

    calls, speaker = _make_speaker()
    n = NarratorStream(
        db=mongomock_db,
        mission_id="m1",
        speaker=speaker,
        clock=_Clock(),
    )

    spoken = await n.handle_event(
        {
            "event": "takeoff",
            "mission_id": "m1",
            "payload": {"drone": "Drone 1", "from_": "Depot"},
        }
    )

    assert spoken is True
    assert calls == [("Drone 1 is wheels up from Depot.", {"event": "takeoff", "mission_id": "m1"})]


@pytest.mark.asyncio
async def test_narrator_debounces_repeated_same_kind(mongomock_db):
    """Two ``waypoint_reached`` events fired within 600 ms collapse to one."""
    from dronan.voice.narrator_stream import NarratorStream

    clock = _Clock()
    calls, speaker = _make_speaker()
    n = NarratorStream(
        db=mongomock_db,
        mission_id="m1",
        speaker=speaker,
        debounce_ms=600,
        clock=clock,
    )

    doc = {
        "event": "waypoint_reached",
        "mission_id": "m1",
        "payload": {"drone": "Drone 2", "place": "Royal London"},
    }

    assert await n.handle_event(doc) is True
    clock.advance(0.300)  # 300 ms — inside the 600 ms debounce
    assert await n.handle_event(doc) is False
    clock.advance(0.400)  # cumulative 700 ms — outside the window
    assert await n.handle_event(doc) is True

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_narrator_suppresses_narration_during_barge_in(mongomock_db):
    """While the operator is speaking, narrations within the window are dropped."""
    from dronan.voice.narrator_stream import NarratorStream

    clock = _Clock()
    calls, speaker = _make_speaker()
    n = NarratorStream(
        db=mongomock_db,
        mission_id="m1",
        speaker=speaker,
        debounce_ms=0,  # isolate the barge-in suppression behaviour
        suppress_near_barge_in_ms=250,
        clock=clock,
    )

    n.note_user_started_speaking()
    clock.advance(0.100)  # 100 ms after operator started — suppressed
    spoken = await n.handle_event(
        {"event": "obstacle", "mission_id": "m1", "payload": {"drone": "Drone 3", "alt": 90}}
    )
    assert spoken is False
    assert calls == []

    clock.advance(0.200)  # cumulative 300 ms — outside the window
    n.note_user_stopped_speaking()
    spoken = await n.handle_event(
        {"event": "obstacle", "mission_id": "m1", "payload": {"drone": "Drone 3", "alt": 90}}
    )
    assert spoken is True
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_narrator_barge_in_does_not_consume_debounce_window(mongomock_db):
    """Regression: a barge-in-suppressed event must not lock out the next
    same-kind event from being narrated within the debounce window. SM-6.

    Sequence:
      1. Operator starts speaking → barge-in.
      2. ``takeoff`` fires 100 ms later → suppressed (returns False).
      3. Operator stops; ``takeoff`` fires again 200 ms after that.
      4. The second ``takeoff`` MUST be spoken — the suppressed first call
         should not have consumed the debounce slot.
    """
    from dronan.voice.narrator_stream import NarratorStream

    clock = _Clock()
    calls, speaker = _make_speaker()
    n = NarratorStream(
        db=mongomock_db,
        mission_id="m1",
        speaker=speaker,
        debounce_ms=600,
        suppress_near_barge_in_ms=250,
        clock=clock,
    )

    n.note_user_started_speaking()
    clock.advance(0.100)
    doc = {"event": "takeoff", "mission_id": "m1", "payload": {"drone": "Drone 1"}}
    assert await n.handle_event(doc) is False  # suppressed
    assert calls == []

    n.note_user_stopped_speaking()
    clock.advance(0.200)  # 300 ms total — well inside the 600 ms debounce
    assert await n.handle_event(doc) is True  # must speak, not be debounced
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_narrator_unknown_event_silently_dropped(mongomock_db):
    from dronan.voice.narrator_stream import NarratorStream

    calls, speaker = _make_speaker()
    n = NarratorStream(db=mongomock_db, mission_id="m1", speaker=speaker, clock=_Clock())

    # 'fizzbuzz' isn't in NARRATION_TEMPLATES; should silently drop.
    assert await n.handle_event({"event": "fizzbuzz", "mission_id": "m1", "payload": {}}) is False
    assert calls == []


@pytest.mark.asyncio
async def test_narrator_speaker_exception_does_not_kill_stream(mongomock_db):
    """A flaky TTS must not propagate; subsequent events still render."""
    from dronan.voice.narrator_stream import NarratorStream

    state = {"calls": 0}

    async def speaker(text: str, meta: dict) -> None:
        state["calls"] += 1
        if state["calls"] == 1:
            raise RuntimeError("ElevenLabs 502")

    n = NarratorStream(db=mongomock_db, mission_id="m1", speaker=speaker, clock=_Clock())

    # First call raises inside speaker → handle_event returns False but doesn't propagate
    spoken = await n.handle_event(
        {"event": "takeoff", "mission_id": "m1", "payload": {"drone": "Drone 1", "from_": "Depot"}}
    )
    assert spoken is False

    # Second call is a different kind so debounce doesn't fire; it should succeed
    spoken = await n.handle_event(
        {
            "event": "delivered",
            "mission_id": "m1",
            "payload": {"place": "Clinic D", "temp": 4},
        }
    )
    assert spoken is True
    assert state["calls"] == 2


# --------------------------------------------------------------------------- #
# 4. End-to-end: producer + consumer loops + change-stream-shaped feed.
#
# We don't actually exercise mongomock's change_stream (it's unimplemented for
# in-memory mocks), so we drive the queue directly via handle_event after
# proving start/stop is idempotent.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_narrator_start_stop_idempotent(mongomock_db):
    from dronan.voice.narrator_stream import NarratorStream

    _, speaker = _make_speaker()
    n = NarratorStream(db=mongomock_db, mission_id="m1", speaker=speaker, clock=_Clock())

    # start() + immediate stop() should not raise even though mongomock has
    # no change stream implementation
    await n.start()
    # Yield a tick so the producer has a chance to attempt watch() and back off
    await asyncio.sleep(0)
    await n.stop()
    # Second stop is a no-op
    await n.stop()
