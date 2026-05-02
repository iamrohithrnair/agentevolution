"""Common agent helpers — node decorator + skill registration."""

from __future__ import annotations

import inspect
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Awaitable, Callable, Iterable

from .state import MissionState, Route

log = logging.getLogger(__name__)

NodeFn = Callable[[MissionState, Any], Awaitable[dict[str, Any]]]


def agent_node(
    name: Route,
    *,
    record_route: bool = True,
) -> Callable[[Callable[..., Awaitable[dict[str, Any]]]], NodeFn]:
    """Wrap a node function so it always returns a state-update dict.

    The wrapper:
    1. Always appends ``name`` to ``route_history`` (unless ``record_route``).
    2. Stamps ``updated_at`` on every hop.
    3. Catches body exceptions and writes them onto ``errors`` rather than
       blowing up the graph; the supervisor decides whether to escalate.
    """

    def decorate(fn: Callable[..., Awaitable[dict[str, Any]]]) -> NodeFn:
        sig = inspect.signature(fn)
        # Allow nodes with signature (state) OR (state, db).
        wants_db = "db" in sig.parameters

        @wraps(fn)
        async def wrapper(state: MissionState, db: Any = None) -> dict[str, Any]:
            update: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
            if record_route:
                update["route_history"] = [name]
            try:
                if wants_db:
                    result = await fn(state, db=db)
                else:
                    result = await fn(state)
            except Exception as exc:
                # Programming-level wiring bugs are noisy on purpose so they
                # surface in CI/log aggregation. The graph still survives.
                log.exception("agent %s raised %s", name, exc.__class__.__name__)
                update["errors"] = [
                    {
                        "agent": name,
                        "error": str(exc),
                        "kind": exc.__class__.__name__,
                    }
                ]
                return update
            if result:
                update.update(result)
            return update

        wrapper.agent_name = name  # type: ignore[attr-defined]
        return wrapper

    return decorate


def all_route_names() -> Iterable[Route]:
    return (
        "supervisor",
        "interpreter",
        "memory",
        "planner",
        "weather",
        "geofence",
        "preflight",
        "dispatch",
        "vision",
        "replanner",
        "anomaly",
        "deconfliction",
        "payload",
        "narrator",
        "analyst",
        "reflection",
        "demand_forecast",
    )
