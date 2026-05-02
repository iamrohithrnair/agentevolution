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
    # starter template at livekit-examples/agent-starter-python.
    from livekit.agents import function_tool  # type: ignore  # noqa: PLC0415
    from livekit.plugins import google as lk_google  # type: ignore  # noqa: PLC0415
    from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore  # noqa: PLC0415

    settings = get_settings()

    # Connect to the room first — required before we can read participants
    # or publish audio back. AUDIO_ONLY keeps bandwidth small.
    await job.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)  # type: ignore[union-attr]

    # One mongo client per job so the function tool can write missions.
    db_client = AsyncIOMotorClient(settings.mongodb_uri)  # type: ignore[misc]
    db = db_client[settings.mongodb_db]

    # ──────────────────────────────────────────────────────────────────
    # Mission Control agent with a real dispatch tool.
    # ──────────────────────────────────────────────────────────────────
    class MissionControl(Agent):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__(instructions=MISSION_CONTROL_SYSTEM)

        @function_tool  # type: ignore[misc]
        async def dispatch_mission(
            self,
            destination: str,
            supply: str = "blood",
            priority: str = "high",
        ) -> str:
            """Dispatch a medical-drone delivery to a hospital.

            Call this when the operator asks to deliver, send, or dispatch a
            supply to a named facility. Return a short spoken confirmation.

            Args:
                destination: Facility name (e.g. "Royal London", "King's
                    College Hospital", "Newham", "Whipps Cross"). Resolves
                    against the facilities collection.
                supply: Payload type. Common values: "blood", "insulin",
                    "defib", "antivenom", "organ". Defaults to "blood".
                priority: "low" | "normal" | "high" | "critical". Defaults
                    to "high" — use "critical" only when the operator says
                    so.
            """
            import uuid as _uuid  # noqa: PLC0415
            from datetime import datetime as _dt, timezone as _tz  # noqa: PLC0415

            from dronan.sim.mission_sim import simulate_mission  # noqa: PLC0415

            # Allocate a MED-#### id that matches the missions schema.
            last = await db.missions.find_one(
                {"_id": {"$regex": r"^MED-\d+$"}}, sort=[("_id", -1)]
            )
            n = 0
            if last and isinstance(last.get("_id"), str):
                try:
                    n = int(last["_id"].split("-")[1])
                except (IndexError, ValueError):
                    n = 0
            mission_id = f"MED-{n + 1:04d}"

            # Find a drone that can fly; fall back to Drone1.
            drone = await db.drones.find_one({"status": "idle"}) or {"_id": "Drone1"}
            drone_id = drone.get("_id", "Drone1")

            now = _dt.now(_tz.utc)
            depot = "Depot"
            stops = [destination]
            planned_route = [
                {"location": depot, "kind": "depot"},
                {"location": destination, "kind": "stop"},
                {"location": depot, "kind": "return"},
            ]
            await db.missions.insert_one(
                {
                    "_id": mission_id,
                    "operator_id": "voice-operator",
                    "request": f"Deliver {supply} to {destination}",
                    "depot": depot,
                    "stops": stops,
                    "delivery_ids": [],
                    "drone_id": drone_id,
                    "status": "planned",
                    "planned_route": planned_route,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            # Also write the delivery row so the logs page + audit trail
            # show the payload.
            del_id = f"D-{_uuid.uuid4().hex[:8]}"
            try:
                await db.deliveries.insert_one(
                    {
                        "_id": del_id,
                        "mission_id": mission_id,
                        "destination_id": destination,
                        "supply": supply,
                        "payload_weight_kg": 1.5,
                        "priority": priority if priority in ("low", "normal", "high", "critical") else "high",
                        "cold_chain_required": supply in ("blood", "insulin", "vaccine", "organ"),
                        "status": "pending",
                        "requested_by": "voice-operator",
                        "requested_at": now,
                        "created_at": now,
                    }
                )
            except Exception:
                pass

            # Fire the simulator so the drone actually moves and the UI
            # animates. Does not await — fire-and-forget task.
            asyncio.create_task(simulate_mission(db, mission_id))

            return (
                f"Mission {mission_id} dispatched. {drone_id} carrying "
                f"{supply} to {destination}. ETA about three minutes."
            )

        @function_tool  # type: ignore[misc]
        async def fleet_status(self) -> str:
            """Describe the fleet: how many drones, which are flying, battery ranges.

            Call this when the operator asks things like 'fleet status',
            'how many drones', 'are any drones in the air'.
            """
            total = 0
            flying = 0
            idle = 0
            batteries: list[float] = []
            async for d in db.drones.find({}):
                total += 1
                if d.get("status") in ("flying", "in_transit", "executing"):
                    flying += 1
                elif d.get("status") == "idle":
                    idle += 1
                b = d.get("battery")
                if isinstance(b, (int, float)):
                    batteries.append(float(b))
            if not batteries:
                return "No drones reporting right now."
            return (
                f"{total} drones. {flying} airborne, {idle} idle. "
                f"Battery range {min(batteries):.0f} to {max(batteries):.0f} percent."
            )

        @function_tool  # type: ignore[misc]
        async def active_missions(self) -> str:
            """List missions in flight right now.

            Call this when the operator asks 'what missions are running',
            'which missions are in the air', 'what's active'.
            """
            cursor = db.missions.find(
                {"status": {"$in": ["planned", "executing", "in_transit"]}}
            ).sort("created_at", -1).limit(10)
            rows = [doc async for doc in cursor]
            if not rows:
                return "No active missions. Fleet is idle."
            summaries = [
                f"{r['_id']} ({r.get('status')}) to {(r.get('stops') or ['unknown'])[0]}"
                for r in rows
            ]
            return f"{len(rows)} active mission(s): " + "; ".join(summaries) + "."

        @function_tool  # type: ignore[misc]
        async def mission_status(self, mission_id: str) -> str:
            """Get the current status of a specific mission by id.

            Args:
                mission_id: Full mission id like "MED-0012" or just the
                    numeric suffix like "12".
            """
            mid = mission_id.strip().upper()
            if not mid.startswith("MED-"):
                # Try to coerce "twelve" / "12" / "MED 12" into MED-####.
                digits = "".join(c for c in mid if c.isdigit())
                if digits:
                    mid = f"MED-{int(digits):04d}"
            doc = await db.missions.find_one({"_id": mid})
            if not doc:
                return f"Mission {mid} not found."
            status = doc.get("status", "unknown")
            drone = doc.get("drone_id", "unknown drone")
            stop = (doc.get("stops") or ["unknown"])[0]
            reroutes = len(doc.get("reroutes") or [])
            extra = f" with {reroutes} reroute{'s' if reroutes != 1 else ''}." if reroutes else "."
            return (
                f"Mission {mid} is {status}, flown by {drone}, destination "
                f"{stop}{extra}"
            )

        @function_tool  # type: ignore[misc]
        async def search_memory(self, query: str, limit: int = 3) -> str:
            """Recall past mission lessons related to a topic via Atlas Vector Search.

            Call this when the operator asks 'what have we learned about X',
            'any lessons on wind', 'pull up past issues with cold chain'.

            Args:
                query: What to search for. Free-text.
                limit: How many lessons to return (default 3, max 5).
            """
            limit = max(1, min(5, int(limit)))
            try:
                from dronan.tools.memory import vector_search  # noqa: PLC0415

                hits = await vector_search(
                    db=db,
                    query=query,
                    collection="mission_memory",
                    k=limit,
                    idempotency_key=f"voice-mem-{query[:24]}",
                )
            except Exception:
                hits = []
            # Fallback to a keyword scan if vector search is unavailable.
            if not hits:
                q_low = query.lower()
                hits = []
                async for doc in db.mission_memory.find(
                    {"kind": "reflection"}, projection={"embedding": 0, "embedding_model": 0}
                ).limit(20):
                    text = (doc.get("text") or doc.get("title") or "").lower()
                    if any(tok in text for tok in q_low.split() if len(tok) > 3):
                        hits.append(doc)
                    if len(hits) >= limit:
                        break
            if not hits:
                return f"No past lessons found for {query!r}."
            lines = [
                f"{i + 1}. {(h.get('text') or h.get('title') or '').split('.')[0][:160]}."
                for i, h in enumerate(hits[:limit])
            ]
            return f"Found {len(lines)} lesson(s) on {query!r}. " + " ".join(lines)

        @function_tool  # type: ignore[misc]
        async def write_reflection(self, text: str, mission_id: str = "") -> str:
            """Save an operator-provided lesson into mission_memory.

            Call this when the operator says 'remember that', 'note that',
            'write down', 'save this lesson'. The lesson shows up live on
            the Reflections page.

            Args:
                text: The lesson to record, in the operator's own words.
                mission_id: Optional mission id to tag the reflection with.
            """
            import uuid as _uuid  # noqa: PLC0415
            from datetime import datetime as _dt, timezone as _tz  # noqa: PLC0415

            now = _dt.now(_tz.utc)
            doc = {
                "_id": f"mm_{_uuid.uuid4().hex[:10]}",
                "kind": "reflection",
                "title": "Operator note",
                "text": text.strip(),
                "embedding": [0.0] * 1024,  # placeholder; real retriever rewrites on recall
                "embedding_model": "voice-placeholder",
                "source_collection": "voice",
                "source_id": mission_id or "voice-operator",
                "created_at": now,
            }
            try:
                await db.mission_memory.insert_one(doc)
            except Exception as exc:
                return f"Could not save the reflection: {exc}"
            return "Reflection saved. It's now in mission memory and on the Reflections page."

        @function_tool  # type: ignore[misc]
        async def simulate_weather(
            self, location: str = "homerton", severity: str = "high"
        ) -> str:
            """Inject a synthetic weather event to demo the replanner.

            Call when the operator says 'simulate a storm', 'inject bad weather',
            'make it rain over X'. The weather observation is written to
            MongoDB which triggers the Atlas change stream listeners.

            Args:
                location: Human name of the facility / area, defaults to "homerton".
                severity: "low" | "medium" | "high" | "extreme".
            """
            from datetime import datetime as _dt, timezone as _tz  # noqa: PLC0415

            sev = severity.lower() if severity.lower() in ("low", "medium", "high", "extreme") else "high"
            cls = {
                "low": "breezy",
                "medium": "marginal",
                "high": "no_go",
                "extreme": "grounded",
            }[sev]
            doc = {
                "location_id": location,
                "wind_kph": 25.0 if sev == "low" else 55.0,
                "precip_mm_h": 0.5 if sev == "low" else 10.0,
                "visibility_m": 10000 if sev == "low" else 2000,
                "classification": cls,
                "flyable": sev == "low",
                "ts": _dt.now(_tz.utc),
                "source": "voice-operator",
            }
            try:
                await db.weather_observations.insert_one(doc)
            except Exception as exc:
                return f"Could not inject weather: {exc}"
            return (
                f"Storm injected over {location} with severity {sev}. Replanner "
                "should react within a couple of seconds."
            )

        @function_tool  # type: ignore[misc]
        async def inject_obstacle(
            self, kind: str = "bird", mission_id: str = ""
        ) -> str:
            """Simulate an obstacle detection so the vision + replanner path fires.

            Call when the operator says 'drop an obstacle', 'inject a drone in
            the airspace', 'simulate a bird strike'.

            Args:
                kind: What kind of obstacle — 'bird', 'drone', 'tower', etc.
                mission_id: Optional mission id to associate the event with.
            """
            import uuid as _uuid  # noqa: PLC0415
            from datetime import datetime as _dt, timezone as _tz  # noqa: PLC0415

            log_id = f"fl_{_uuid.uuid4().hex[:10]}"
            doc = {
                "_id": log_id,
                "id": log_id,
                "mission_id": mission_id or "voice-demo",
                "drone_id": None,
                "event": "obstacle_detected",
                "kind": kind,
                "position": {"type": "Point", "coordinates": [-0.063, 51.519]},
                "ts": _dt.now(_tz.utc),
                "source": "voice-operator",
            }
            try:
                await db.flight_logs.insert_one(doc)
            except Exception as exc:
                return f"Could not log the obstacle: {exc}"
            return (
                f"Obstacle of kind {kind} logged. It's now on the Logs page and "
                "the vision agent will flag it in the reasoning stream."
            )

        @function_tool  # type: ignore[misc]
        async def list_facilities(self, limit: int = 5) -> str:
            """Name a handful of the facilities the fleet can deliver to.

            Call when the operator asks 'what hospitals can we fly to',
            'list destinations', 'where can I send the drone'.

            Args:
                limit: How many names to read back (default 5, max 10).
            """
            limit = max(1, min(10, int(limit)))
            cursor = db.facilities.find({"type": "hospital"}).limit(limit)
            names = [doc.get("name") async for doc in cursor if doc.get("name")]
            if not names:
                cursor = db.facilities.find({}).limit(limit)
                names = [doc.get("name") async for doc in cursor if doc.get("name")]
            if not names:
                return "No facilities are seeded in the database yet."
            return f"I can deliver to: {', '.join(names)}."

        @function_tool  # type: ignore[misc]
        async def list_no_fly_zones(self) -> str:
            """Name the active no-fly zones. Call when the operator asks about
            restricted airspace, TFRs, or no-fly polygons.
            """
            cursor = db.no_fly_zones.find({}).limit(10)
            names = [
                f"{doc.get('name', 'unnamed')} ({doc.get('severity', 'unknown')})"
                async for doc in cursor
            ]
            if not names:
                return "No no-fly zones are configured."
            return f"Active no-fly zones: {'; '.join(names)}."

        @function_tool  # type: ignore[misc]
        async def fleet_metrics(self, window_minutes: int = 60) -> str:
            """Summarise fleet performance over the last N minutes.

            Call when the operator asks 'how are we doing', 'any metrics',
            'mission throughput', 'what's the analytics look like'.

            Args:
                window_minutes: Lookback window. Default 60.
            """
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz  # noqa: PLC0415

            since = _dt.now(_tz.utc) - _td(minutes=max(1, int(window_minutes)))
            missions_total = await db.missions.count_documents({"created_at": {"$gte": since}})
            completed = await db.missions.count_documents(
                {"created_at": {"$gte": since}, "status": "completed"}
            )
            reroutes_cursor = db.missions.aggregate(
                [
                    {"$match": {"created_at": {"$gte": since}}},
                    {
                        "$group": {
                            "_id": None,
                            "reroutes": {"$sum": {"$size": {"$ifNull": ["$reroutes", []]}}},
                        }
                    },
                ]
            )
            reroutes_doc = await reroutes_cursor.to_list(length=1)
            reroutes = reroutes_doc[0].get("reroutes", 0) if reroutes_doc else 0
            reflections = await db.mission_memory.count_documents(
                {"kind": "reflection", "created_at": {"$gte": since}}
            )
            return (
                f"Last {window_minutes} minutes: {missions_total} missions launched, "
                f"{completed} completed, {reroutes} reroutes, "
                f"{reflections} new reflection{'s' if reflections != 1 else ''} written."
            )

    # Build the voice pipeline.
    google_llm = lk_google.LLM(  # type: ignore[union-attr]
        model=settings.llm_model or "gemini-3.1-flash-lite-preview",
        api_key=os.environ.get("GOOGLE_API_KEY", ""),
        temperature=0.3,
    )

    session = AgentSession(  # type: ignore[union-attr, call-arg]
        vad=make_vad(),
        stt=make_stt("en"),
        llm=google_llm,
        tts=make_tts("en"),
    )

    await session.start(room=job.room, agent=MissionControl())
    await session.say("Mission Control online. Standing by.")

    # Keep the session alive until the operator leaves the room.
    try:
        if hasattr(job, "wait_for_disconnect"):
            await job.wait_for_disconnect()
        else:
            await asyncio.Event().wait()
    finally:
        db_client.close()


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
