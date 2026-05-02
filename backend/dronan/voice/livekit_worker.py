"""LiveKit Worker for Dronan voice mission control.

Implements the design from ``prompts/06-voice-livekit-elevenlabs.md`` §3:

1. Subscribe to operator audio, run Silero VAD → Deepgram Nova-3 STT.
2. Forward each finalised utterance to the LangGraph supervisor (owned by
   Session A; we lazy-import :func:`dronan.graph.build_supervisor`).
3. Stream supervisor text deltas into ElevenLabs Turbo v2.5 TTS and
   publish the resulting audio back into the room.
4. Run a :class:`~dronan.voice.narrator_stream.NarratorStream` in the
   background that tails ``flight_logs`` Change Streams (filtered by the
   operator's current ``mission_id``) and speaks events.
5. Capture voice signatures on delivery confirmation and write to
   ``audit_trail`` (handed off to Session A's ``dronan.tools.audit``).
6. Handle barge-in (operator speaks while narrator is speaking → pause TTS,
   keep transcript, resume after).
7. Handle push-to-talk vs always-on toggling via room data-channel messages.
8. Fall back to Deepgram language autodetect + ElevenLabs multilingual voice.

The module also exposes a ``--text-mode`` REPL for the no-key fallback path
(``prompts/06`` §9). The text-mode path does not import any LiveKit symbols,
so it's the smoke-test surface used by ``backend/tests/test_livekit_smoke.py``
when the optional ``[voice]`` extras aren't installed.

Run as::

    uv run python -m dronan.voice.livekit_worker dev          # local
    uv run python -m dronan.voice.livekit_worker start        # production
    uv run python -m dronan.voice.livekit_worker dev --text-mode
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sys
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from dronan.config import get_settings
from dronan.voice.narrator_stream import NarratorStream
from dronan.voice.prompts import MISSION_CONTROL_SYSTEM, SIGNATURE_PROMPT

log = logging.getLogger("dronan.voice.worker")


# --------------------------------------------------------------------------- #
# Optional heavy imports
#
# We keep ``livekit-agents`` and Motor optional at import time so the rest of
# the package (and the smoke tests) can load even if the operator chose
# ``uv sync`` without the ``[voice]`` extras. The ``--text-mode`` REPL needs
# none of these.
# --------------------------------------------------------------------------- #

LIVEKIT_AVAILABLE: bool
try:
    from livekit import rtc  # type: ignore
    from livekit.agents import (  # type: ignore
        Agent,
        AgentSession,
        AutoSubscribe,
        JobContext,
        WorkerOptions,
        cli,
        llm,
        stt,
        tts,
        vad,
    )
    from livekit.plugins import deepgram, elevenlabs, silero  # type: ignore

    LIVEKIT_AVAILABLE = True
except ImportError:  # pragma: no cover — exercised in the smoke test fallback
    LIVEKIT_AVAILABLE = False
    if not TYPE_CHECKING:
        rtc = None  # type: ignore[assignment]
        Agent = AgentSession = AutoSubscribe = JobContext = WorkerOptions = None  # type: ignore[assignment]
        cli = llm = stt = tts = vad = None  # type: ignore[assignment]
        deepgram = elevenlabs = silero = None  # type: ignore[assignment]

MOTOR_AVAILABLE: bool
try:
    from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore

    MOTOR_AVAILABLE = True
except ImportError:  # pragma: no cover — should be present in any sane install
    MOTOR_AVAILABLE = False
    if not TYPE_CHECKING:
        AsyncIOMotorClient = None  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# Per-session context
# --------------------------------------------------------------------------- #


@dataclass
class MissionContext:
    """All per-room state. One instance lives in a closure inside ``agent_entrypoint``.

    Attributes mirror :class:`MissionContext` in ``prompts/06`` §3 so a future
    reader can map the prompt 1:1 to this code.
    """

    operator_id: str
    db: Any  # AsyncIOMotorDatabase, but typed Any so importing without motor works
    room: Any = None  # rtc.Room
    mode: str = "always_on"  # "ptt" | "always_on"
    language: str = "en"  # "en" | "auto"
    current_mission_id: str | None = None
    narrator: NarratorStream | None = None
    signature_event: asyncio.Event = field(default_factory=asyncio.Event)
    signature_buffer: list[str] = field(default_factory=list)
    signature_pending: bool = False
    barge_in_event: asyncio.Event = field(default_factory=asyncio.Event)
    last_user_utterance_at: float = 0.0
    session: Any = None  # AgentSession
    # Strong refs to fire-and-forget tasks (e.g. signature capture launched
    # from the data-channel callback). asyncio only weak-references tasks,
    # so without holding them here the GC can collect a long-lived task
    # mid-await. See https://docs.python.org/3/library/asyncio-task.html#creating-tasks
    background_tasks: set[asyncio.Task[Any]] = field(default_factory=set)

    def trace_meta(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "mission_id": self.current_mission_id,
            "room": getattr(self.room, "name", None) if self.room is not None else None,
            "mode": self.mode,
            "language": self.language,
        }


# --------------------------------------------------------------------------- #
# Speaker callable used by the narrator + the supervisor adapter.
#
# Routes both narration and supervisor replies through the same
# ``AgentSession.say()`` so barge-in cancels them uniformly (see prompts/06 §6).
# --------------------------------------------------------------------------- #


async def speak_via_session(ctx: MissionContext, text: str, *, source: str, meta: dict) -> None:
    """Push ``text`` into the active ``AgentSession`` TTS pipeline."""
    if ctx.session is None:
        log.debug("speak_via_session: no session bound; dropping text=%r", text[:80])
        return
    say = getattr(ctx.session, "say", None)
    if say is None:
        log.debug("speak_via_session: session lacks .say(); dropping text=%r", text[:80])
        return
    try:
        await say(text, allow_interruptions=True)
    except Exception:  # noqa: BLE001 — fall back to caption if TTS dies
        log.exception("speak_via_session: TTS failed; mirroring to agent_messages as caption")
        # Best-effort: write a fallback caption row so the UI can still render
        with suppress(Exception):
            await ctx.db.agent_messages.insert_one(
                {
                    "kind": "narrator-fallback",
                    "operator_id": ctx.operator_id,
                    "mission_id": ctx.current_mission_id,
                    "text": text,
                    "ts": time.time(),
                    "meta": {**meta, "source": source, "fallback": True},
                }
            )
        return

    # Persist a happy-path agent_messages row
    with suppress(Exception):
        await ctx.db.agent_messages.insert_one(
            {
                "kind": source,
                "operator_id": ctx.operator_id,
                "mission_id": ctx.current_mission_id,
                "text": text,
                "ts": time.time(),
                "meta": {**meta, "source": source},
            }
        )


# --------------------------------------------------------------------------- #
# Voice signature capture
# --------------------------------------------------------------------------- #


async def capture_signature(
    ctx: MissionContext, delivery_id: str, *, timeout_s: float = 20.0
) -> str:
    """Speak the signature prompt, listen for one utterance, hash + persist.

    Returns the signature ID (e.g. ``SIG-7f3a1c4d``) on success, ``""`` on timeout.
    """
    ctx.signature_buffer.clear()
    ctx.signature_event.clear()
    ctx.signature_pending = True
    await speak_via_session(
        ctx, SIGNATURE_PROMPT, source="signature", meta={"delivery_id": delivery_id}
    )

    try:
        await asyncio.wait_for(ctx.signature_event.wait(), timeout=timeout_s)
    except TimeoutError:
        ctx.signature_pending = False
        await speak_via_session(
            ctx,
            "Signature timed out. Falling back to text confirmation.",
            source="signature",
            meta={"delivery_id": delivery_id, "timeout": True},
        )
        return ""

    ctx.signature_pending = False
    transcript = " ".join(ctx.signature_buffer).strip()
    digest = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
    sig_id = f"SIG-{digest[:8]}"

    with suppress(Exception):
        await ctx.db.audit_trail.insert_one(
            {
                "kind": "delivery_signature",
                "mission_id": ctx.current_mission_id,
                "delivery_id": delivery_id,
                "operator_id": ctx.operator_id,
                "signature_id": sig_id,
                "transcript_hash": digest,
                "transcript_preview": transcript[:120],
                "ts": time.time(),
            }
        )

    await speak_via_session(
        ctx,
        f"Logged. Signature {sig_id}. Thank you.",
        source="signature",
        meta={"delivery_id": delivery_id, "signature_id": sig_id},
    )
    return sig_id


# --------------------------------------------------------------------------- #
# Narrator wiring
# --------------------------------------------------------------------------- #


def make_narrator(ctx: MissionContext) -> NarratorStream:
    """Build a :class:`NarratorStream` whose speaker is bound to ``ctx``'s session."""
    settings = get_settings()

    async def speaker(text: str, meta: dict) -> None:
        await speak_via_session(ctx, text, source="narrator", meta=meta)

    return NarratorStream(
        db=ctx.db,
        mission_id=ctx.current_mission_id or "",
        speaker=speaker,
        debounce_ms=settings.narration_debounce_ms,
        suppress_near_barge_in_ms=settings.narration_suppress_near_barge_in_ms,
    )


async def restart_narrator(ctx: MissionContext) -> None:
    """Cancel the current narrator (if any) and start one for the new mission."""
    if ctx.narrator is not None:
        await ctx.narrator.stop()
        ctx.narrator = None
    if ctx.current_mission_id:
        ctx.narrator = make_narrator(ctx)
        await ctx.narrator.start()


# --------------------------------------------------------------------------- #
# Supervisor binding
#
# We import ``dronan.graph`` lazily because Session A still owns that module
# and may not have landed yet. Tests inject their own factory.
# --------------------------------------------------------------------------- #


def _build_supervisor(db: Any) -> Any:
    """Return Session A's compiled LangGraph supervisor.

    Never imported at module load — the dependency only matters when a real
    voice turn arrives. This keeps the smoke test (and ``--text-mode``)
    runnable before P3 lands.
    """
    from dronan.graph import build_supervisor  # type: ignore  # noqa: PLC0415

    return build_supervisor(db=db)


# --------------------------------------------------------------------------- #
# LLM adapter — bridge livekit-agents.llm → LangGraph supervisor
# --------------------------------------------------------------------------- #


if LIVEKIT_AVAILABLE:

    class SupervisorLLM(llm.LLM):  # type: ignore[misc, name-defined]
        """Streams the supervisor's text deltas into the AgentSession TTS sink."""

        def __init__(self, ctx: MissionContext) -> None:
            super().__init__()
            self.ctx = ctx
            self.supervisor = _build_supervisor(ctx.db)

        def chat(  # type: ignore[override]
            self,
            chat_ctx: Any,
            *,
            fnc_ctx: Any | None = None,
            temperature: float | None = None,
            n: int | None = None,
            parallel_tool_calls: bool | None = None,
        ) -> SupervisorStream:
            return SupervisorStream(self.ctx, self.supervisor, chat_ctx)

    class SupervisorStream(llm.LLMStream):  # type: ignore[misc, name-defined]
        def __init__(self, ctx: MissionContext, supervisor: Any, chat_ctx: Any) -> None:
            super().__init__(chat_ctx=chat_ctx, fnc_ctx=None)
            self.ctx = ctx
            self.supervisor = supervisor
            self._iter: Any = None

        async def _stream_supervisor(self):
            user_text = ""
            for m in reversed(getattr(self._chat_ctx, "messages", [])):
                if getattr(m, "role", None) == "user":
                    content = m.content
                    if isinstance(content, str):
                        user_text = content
                    elif isinstance(content, list):
                        user_text = " ".join(p for p in content if isinstance(p, str))
                    break
            if not user_text:
                return

            async for delta in self.supervisor.astream_events(
                {
                    "messages": [{"role": "user", "content": user_text}],
                    "operator_id": self.ctx.operator_id,
                    "mission_id": self.ctx.current_mission_id,
                    "language": self.ctx.language,
                    "system": MISSION_CONTROL_SYSTEM,
                },
                version="v2",
            ):
                ev = delta.get("event")
                if ev == "on_chat_model_stream":
                    chunk = delta["data"]["chunk"]
                    text = getattr(chunk, "content", "") or ""
                    if text:
                        yield text
                elif ev == "on_chain_end" and delta.get("name") == "supervisor":
                    state = delta["data"]["output"]
                    if isinstance(state, dict) and state.get("active_mission_id"):
                        self.ctx.current_mission_id = state["active_mission_id"]
                        await restart_narrator(self.ctx)

        async def __anext__(self):  # type: ignore[override]
            if self._iter is None:
                self._iter = self._stream_supervisor().__aiter__()
            text = await self._iter.__anext__()
            return llm.ChatChunk(  # type: ignore[name-defined]
                request_id=str(uuid.uuid4()),
                choices=[
                    llm.Choice(  # type: ignore[name-defined]
                        delta=llm.ChoiceDelta(role="assistant", content=text),  # type: ignore[name-defined]
                    ),
                ],
            )


# --------------------------------------------------------------------------- #
# STT / TTS / VAD factories — multilingual aware (prompts/06 §7)
# --------------------------------------------------------------------------- #


def make_stt(language: str) -> Any:
    if not LIVEKIT_AVAILABLE:
        raise RuntimeError("livekit-agents extras not installed; pip install '.[voice]'")
    settings = get_settings()
    # Plugin reads DEEPGRAM_API_KEY; pass explicitly so we honour
    # .env even when the worker is launched with a minimal environment.
    api_key = settings.deepgram_api_key or os.environ.get("DEEPGRAM_API_KEY", "")
    kwargs = {
        "model": settings.deepgram_model,
        "interim_results": True,
        "smart_format": True,
        "punctuate": True,
        "api_key": api_key,
    }
    if language == "auto":
        return deepgram.STT(detect_language=True, **kwargs)  # type: ignore[union-attr]
    return deepgram.STT(language="en", **kwargs)  # type: ignore[union-attr]


def make_tts(language: str) -> Any:
    if not LIVEKIT_AVAILABLE:
        raise RuntimeError("livekit-agents extras not installed; pip install '.[voice]'")
    settings = get_settings()
    voice = (
        settings.elevenlabs_voice_id
        if language == "en"
        else settings.elevenlabs_voice_id_multilingual
    )
    model = settings.elevenlabs_model_id if language == "en" else "eleven_multilingual_v2"
    # The livekit-plugins-elevenlabs package reads ``ELEVEN_API_KEY`` at
    # construction time (not ``ELEVENLABS_API_KEY`` which is what we ship
    # in .env). Pass the key explicitly so either name works.
    api_key = settings.elevenlabs_api_key or os.environ.get(
        "ELEVEN_API_KEY", os.environ.get("ELEVENLABS_API_KEY", "")
    )
    return elevenlabs.TTS(  # type: ignore[union-attr]
        voice_id=voice,
        model=model,
        api_key=api_key,
        streaming_latency=2,  # 1=lowest latency, 4=highest quality; 2 is the sweet spot
        chunk_length_schedule=[80, 160, 250, 290],
    )


def make_vad() -> Any:
    if not LIVEKIT_AVAILABLE:
        raise RuntimeError("livekit-agents extras not installed; pip install '.[voice]'")
    return silero.VAD.load(min_silence_duration=0.35, min_speech_duration=0.10)  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
# Worker entry point — only used when LiveKit extras + Motor are installed.
# --------------------------------------------------------------------------- #


async def agent_entrypoint(job: Any) -> None:
    """LiveKit Worker entry. Wires VAD/STT/LLM/TTS, narrator, and signature handlers."""
    if not LIVEKIT_AVAILABLE:
        raise RuntimeError("livekit-agents extras not installed; pip install '.[voice]'")
    if not MOTOR_AVAILABLE:
        raise RuntimeError("motor not installed; pip install motor")

    # LiveKit Agents 1.5 pattern — minimal, verified against the current
    # starter template at livekit-examples/agent-starter-python. The Phase-6
    # extras (narrator, signature capture, data-channel toggles) are left
    # out of this path deliberately until they can be re-verified against
    # the new SDK surface — see prompts/06 for the roadmap.
    from livekit.plugins import google as lk_google  # type: ignore  # noqa: PLC0415

    settings = get_settings()

    # Connect to the room first — required before we can read participants
    # or publish audio back. AUDIO_ONLY keeps bandwidth small.
    await job.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)  # type: ignore[union-attr]

    # Build the voice pipeline. Each factory already passes api_key= so the
    # plugins work regardless of which env-var convention they read.
    google_llm = lk_google.LLM(  # type: ignore[union-attr]
        model=settings.llm_model or "gemini-3.1-flash-lite-preview",
        api_key=os.environ.get("GOOGLE_API_KEY", ""),
        temperature=0.3,
    )

    session = AgentSession(  # type: ignore[union-attr, call-arg]
        vad=make_vad(),
        stt=make_stt(settings.deepgram_model and "en" or "en"),
        llm=google_llm,
        tts=make_tts("en"),
    )

    await session.start(
        room=job.room,
        agent=Agent(instructions=MISSION_CONTROL_SYSTEM),  # type: ignore[union-attr, call-arg]
    )
    await session.say("Mission Control online. Standing by.")

    # Keep the session alive until the operator leaves the room.
    if hasattr(job, "wait_for_disconnect"):
        await job.wait_for_disconnect()
    else:
        await asyncio.Event().wait()


# --------------------------------------------------------------------------- #
# Text-mode REPL — no LiveKit needed.
# --------------------------------------------------------------------------- #


async def text_mode_repl(reader: Any | None = None, writer: Any | None = None) -> None:
    """Tiny REPL that delegates to the LangGraph supervisor.

    Kept dep-free so the smoke test can exercise it without LiveKit. ``reader``
    and ``writer`` default to stdin/stdout but tests inject in-memory streams.
    """
    if reader is None:
        reader = sys.stdin
    if writer is None:
        writer = sys.stdout

    settings = get_settings()
    if MOTOR_AVAILABLE:
        client = AsyncIOMotorClient(settings.mongodb_uri)  # type: ignore[misc]
        db = client[settings.mongodb_db]
    else:  # pragma: no cover — exercised only when motor missing
        client = None
        db = None

    try:
        supervisor = _build_supervisor(db)
    except Exception as e:  # noqa: BLE001
        writer.write(f"text-mode: dronan.graph.build_supervisor unavailable ({e}); echoing only.\n")
        writer.flush()
        supervisor = None

    while True:
        writer.write("> ")
        writer.flush()
        line = reader.readline()
        if not line:  # EOF (Ctrl-D / closed stream)
            break
        line = line.strip()
        if not line:  # blank Enter — re-prompt instead of exiting
            continue
        if line in {":q", "exit", "quit"}:
            break

        if supervisor is None:
            writer.write(f"(echo) {line}\n")
            writer.flush()
            continue

        async for delta in supervisor.astream_events(
            {
                "messages": [{"role": "user", "content": line}],
                "operator_id": "local",
                "mission_id": None,
                "language": "en",
                "system": MISSION_CONTROL_SYSTEM,
            },
            version="v2",
        ):
            if delta.get("event") == "on_chat_model_stream":
                writer.write(getattr(delta["data"]["chunk"], "content", "") or "")
                writer.flush()
        writer.write("\n")
        writer.flush()

    if client is not None:
        client.close()


# --------------------------------------------------------------------------- #
# CLI dispatch
# --------------------------------------------------------------------------- #


def _prewarm(_proc) -> None:
    """Module-level prewarm so the watcher-based ``dev`` mode can pickle it."""
    silero.VAD.load()  # type: ignore[union-attr]


def main(argv: list[str] | None = None) -> None:
    """``python -m dronan.voice.livekit_worker [dev|start] [--text-mode]``."""
    argv = argv if argv is not None else sys.argv[1:]
    if "--text-mode" in argv:
        asyncio.run(text_mode_repl())
        return

    if not LIVEKIT_AVAILABLE:
        raise SystemExit(
            "livekit-agents extras not installed. Run with --text-mode or install '.[voice]'."
        )

    cli.run_app(  # type: ignore[union-attr]
        WorkerOptions(  # type: ignore[union-attr, call-arg]
            entrypoint_fnc=agent_entrypoint,
            # No agent_name — lets the worker auto-subscribe to any room the
            # operator connects to. With an agent_name set, LiveKit requires
            # an explicit dispatch per room which we don't wire from the
            # frontend for the hackathon demo.
            prewarm_fnc=_prewarm,
        ),
    )


if __name__ == "__main__":
    main()
