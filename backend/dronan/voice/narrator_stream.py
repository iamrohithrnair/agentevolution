"""Narrator stream — tail ``flight_logs`` Change Stream and speak events.

Design notes
------------

- **Speaker is injected.** The narrator does not know about LiveKit. It calls
  an async ``speaker(text, meta)`` callable that the worker wires to
  ``AgentSession.say(...)``. Tests pass a fake speaker that records calls.
- **Debounce.** A buggy simulator (or replanner mid-flight) can fire the same
  ``event`` repeatedly. We coalesce same-kind events fired within
  ``debounce_ms`` (default 600 ms — calibrated against the original
  ``simulation/backend/reasoning_stream.py`` cadence).
- **Barge-in suppression.** When the operator is mid-utterance, the worker sets
  ``barge_in_event``. Narrations enqueued during the suppression window are
  dropped, not queued, because the operator's question almost certainly *is*
  about the same event ("what was that?") and re-stating it is annoying.
- **Reconnect on resume-token loss.** Producer wraps ``watch()`` in a
  try/except with exponential backoff. If Atlas evicts our token (rare,
  oplog window exhaustion), we restart from "now" — losing replay capability
  is acceptable because the AnalystAgent re-derives state at end of mission
  from ``flight_logs``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from dronan.voice.prompts import render_narration

log = logging.getLogger("dronan.voice.narrator")


Speaker = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class NarratorState:
    """Per-mission state owned by :class:`NarratorStream`."""

    mission_id: str
    last_kind_at: dict[str, float] = field(default_factory=dict)
    last_user_utterance_at: float = 0.0
    barge_in_event: asyncio.Event = field(default_factory=asyncio.Event)


class NarratorStream:
    """Tail ``flight_logs`` for one mission and dispatch utterances to ``speaker``.

    Parameters
    ----------
    db
        Motor database handle (``AsyncIOMotorDatabase`` in prod, ``mongomock_motor``
        in tests). The narrator reads from ``db.flight_logs`` only.
    mission_id
        Filter the change stream to ``fullDocument.mission_id == mission_id``.
    speaker
        Async ``(text, meta) -> None`` callable. Returning is the only side
        effect the narrator cares about; failures are logged but don't kill
        the stream.
    debounce_ms
        Coalesce window for repeated same-kind events. Default 600 ms.
    suppress_near_barge_in_ms
        Drop narrations whose render time falls within this many ms after
        the operator started speaking. Default 250 ms.
    clock
        Returns a monotonically-increasing wall clock seconds. Override in
        tests with ``itertools.count`` or ``time_machine``.
    """

    def __init__(
        self,
        db: Any,
        mission_id: str,
        speaker: Speaker,
        *,
        debounce_ms: int = 600,
        suppress_near_barge_in_ms: int = 250,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db = db
        self.mission_id = mission_id
        self.speaker = speaker
        self.debounce_ms = debounce_ms
        self.suppress_near_barge_in_ms = suppress_near_barge_in_ms
        self.clock = clock
        self.state = NarratorState(mission_id=mission_id)
        self._task: asyncio.Task[None] | None = None
        self._producer: asyncio.Task[None] | None = None
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=128)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """Spawn the producer (change-stream tail) and consumer (speaker dispatch).

        Both run forever; cancel via :meth:`stop`.
        """
        if self._task is not None:
            return
        self._producer = asyncio.create_task(
            self._producer_loop(),
            name=f"narrator-cs:{self.mission_id}",
        )
        self._task = asyncio.create_task(
            self._consumer_loop(),
            name=f"narrator-sp:{self.mission_id}",
        )

    async def stop(self) -> None:
        """Cancel both tasks. Idempotent."""
        for t in (self._task, self._producer):
            if t is None or t.done():
                continue
            t.cancel()
            with suppress(asyncio.CancelledError):
                await t
        self._task = None
        self._producer = None

    # ------------------------------------------------------------------ #
    # Helpers used by the worker on barge-in
    # ------------------------------------------------------------------ #

    def note_user_started_speaking(self) -> None:
        self.state.barge_in_event.set()
        self.state.last_user_utterance_at = self.clock()

    def note_user_stopped_speaking(self) -> None:
        self.state.barge_in_event.clear()

    # ------------------------------------------------------------------ #
    # Direct event handler (used by tests + the API's /internal endpoints
    # which can short-circuit Mongo when emitting a synthetic event).
    # ------------------------------------------------------------------ #

    async def handle_event(self, doc: dict[str, Any]) -> bool:
        """Render and speak one ``flight_logs`` doc.

        Returns
        -------
        bool
            ``True`` if the speaker was invoked, ``False`` if the doc was
            silently dropped (debounce hit, barge-in suppression, or no
            template for the event kind).
        """
        kind = doc.get("event")
        if not kind:
            return False

        now = self.clock()

        # Debounce: drop if the same kind fired within the window
        if (now - self.state.last_kind_at.get(kind, 0.0)) * 1000 < self.debounce_ms:
            return False
        self.state.last_kind_at[kind] = now

        # Render through the templates module
        utterance = render_narration(kind, doc.get("payload", {}) or {})
        if utterance is None:
            return False

        # Barge-in suppression
        if self.state.barge_in_event.is_set():
            since_user_ms = (now - self.state.last_user_utterance_at) * 1000
            if since_user_ms < self.suppress_near_barge_in_ms:
                return False

        try:
            await self.speaker(utterance, {"event": kind, "mission_id": self.mission_id})
        except Exception:  # noqa: BLE001 — we never want a flaky TTS to kill the stream
            log.exception("narrator: speaker raised on event=%s", kind)
            return False
        return True

    # ------------------------------------------------------------------ #
    # Internal loops
    # ------------------------------------------------------------------ #

    async def _producer_loop(self) -> None:
        """Tail the Mongo change stream with backoff, push docs into the queue."""
        pipeline = [
            {
                "$match": {
                    "operationType": "insert",
                    "fullDocument.mission_id": self.mission_id,
                }
            },
        ]
        resume_token: dict[str, Any] | None = None
        backoff = 1.0
        while True:
            try:
                async with self.db.flight_logs.watch(
                    pipeline=pipeline,
                    resume_after=resume_token,
                    full_document="updateLookup",
                ) as stream:
                    backoff = 1.0
                    async for change in stream:
                        resume_token = change.get("_id")
                        full_doc = change.get("fullDocument") or {}
                        await self._queue.put(full_doc)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 — log + reconnect
                log.warning(
                    "narrator change-stream error: %s; reconnecting in %.1fs",
                    e,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    async def _consumer_loop(self) -> None:
        """Pop queued docs and run them through :meth:`handle_event`."""
        while True:
            doc = await self._queue.get()
            try:
                await self.handle_event(doc)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — never let one bad event kill the loop
                log.exception("narrator consumer error on doc=%s", doc)
