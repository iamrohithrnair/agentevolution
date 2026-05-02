"""``@mongo_tool`` — idempotent wrapper that writes ``tool_call_log``.

Each decorated coroutine takes a ``db`` keyword argument plus its own
domain payload. The wrapper:

1. Computes a stable idempotency key from ``args_hash`` + an explicit
   ``idempotency_key`` (when supplied). When the same key reappears with
   a ``status="completed"`` row in ``tool_call_log``, the cached result
   is returned without re-running the body.
2. Inserts a ``status="pending"`` row before the body runs, then updates
   it to ``"completed"`` (with the result and result_hash) or ``"failed"``
   (with the error string) on exit.
3. Adds the tool to ``tool_registry`` for Supervisor introspection.

The wrapper is intentionally framework-agnostic — agents can call the
function directly, and we wrap it as a LangChain ``@tool`` only inside the
agents layer (P3) so that the unit tests in P2 don't drag in LangChain.

See ``prompts/01-architecture.md §8.1`` for the spec.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

log = logging.getLogger(__name__)


class ToolError(RuntimeError):
    """Raised by tools to mark a recoverable failure (logged + surfaced)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):  # pydantic models
        return obj.model_dump()
    return repr(obj)


def sha256_hex(payload: Any) -> str:
    """Stable SHA-256 over a JSON-serialisable payload."""
    blob = json.dumps(payload, sort_keys=True, default=_json_default).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def make_idempotency_key(
    *,
    tool: str,
    args_hash: str,
    explicit: str | None = None,
) -> str:
    """Compose ``{tool}:{idempotency_key | args_hash}``.

    Mission flows that need cross-restart determinism pass an explicit key
    (e.g. ``MED-0421:plan_route``). One-off calls fall back to the args
    hash so tools remain memoised within a single process.
    """
    suffix = explicit or args_hash
    return f"{tool}:{suffix}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
F = TypeVar("F", bound=Callable[..., Awaitable[Any]])

# Module-level registry the Supervisor uses for peer discovery.
tool_registry: dict[str, Callable[..., Awaitable[Any]]] = {}


# ---------------------------------------------------------------------------
# The decorator itself
# ---------------------------------------------------------------------------
def mongo_tool(
    fn: F | None = None,
    *,
    name: str | None = None,
    side_effect_class: str = "read",
    agent: str | None = None,
) -> F | Callable[[F], F]:
    """Wrap an async tool body so calls are idempotent and audited.

    Required keyword args of the wrapped function:
        - ``db``: an ``AsyncIOMotorDatabase`` instance
        - any tool-specific payload

    Optional keyword args:
        - ``idempotency_key``: explicit, mission-stable key
        - ``trace_id``, ``mission_id``, ``agent``: stamped on every log row
    """

    def _decorate(inner: F) -> F:
        tool_name = name or inner.__name__

        @wraps(inner)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            db = kwargs.get("db")
            if db is None:
                # Allow naked calls (no DB → no idempotency log). Useful for
                # tests that focus on body behaviour. Pop decorator-only
                # kwargs so they don't end up at ``inner`` unless declared.
                inner_params = inspect.signature(inner).parameters
                for k in ("idempotency_key", "trace_id", "mission_id", "agent"):
                    if k in kwargs and k not in inner_params:
                        kwargs.pop(k)
                return await inner(*args, **kwargs)

            explicit_key = kwargs.pop("idempotency_key", None)
            # ``trace_id`` / ``mission_id`` / ``agent`` are stamped on the log
            # row. We only pop them when the wrapped function does NOT declare
            # them itself — otherwise the inner body needs them.
            inner_params = inspect.signature(inner).parameters
            trace_id = (
                kwargs.pop("trace_id", None)
                if "trace_id" not in inner_params
                else kwargs.get("trace_id")
            )
            mission_id = (
                kwargs.get("mission_id")
                if "mission_id" in inner_params
                else kwargs.pop("mission_id", None)
            )
            agent_name = (
                kwargs.pop("agent", agent)
                if "agent" not in inner_params
                else kwargs.get("agent", agent)
            )

            # Strip db before hashing so the same call across processes hits
            # the same idempotency key.
            log_args = {k: v for k, v in kwargs.items() if k != "db"}
            args_hash = sha256_hex({"args": list(args), "kwargs": log_args})
            key = make_idempotency_key(
                tool=tool_name, args_hash=args_hash, explicit=explicit_key
            )

            # The Atlas validator on ``tool_call_log`` uses {pending, success,
            # error}. Older code wrote {pending, completed, failed}; accept
            # both on read so historical rows still short-circuit.
            existing = await db.tool_call_log.find_one(
                {"idempotency_key": key, "status": {"$in": ["success", "completed"]}}
            )
            if existing is not None:
                return existing.get("result")

            try:
                await db.tool_call_log.update_one(
                    {"idempotency_key": key},
                    {
                        "$setOnInsert": {
                            "idempotency_key": key,
                            "tool": tool_name,
                            "agent": agent_name,
                            "side_effect_class": side_effect_class,
                            "args_hash": args_hash,
                            "status": "pending",
                            "started_at": _utcnow(),
                            "trace_id": trace_id,
                            "mission_id": mission_id,
                        }
                    },
                    upsert=True,
                )
            except Exception as exc:  # pragma: no cover — defensive
                log.warning("tool_call_log insert failed for %s: %s", key, exc)

            try:
                result = await inner(*args, **kwargs)
            except Exception as exc:
                await db.tool_call_log.update_one(
                    {"idempotency_key": key},
                    {
                        "$set": {
                            "status": "error",  # matches the tool_call_log enum
                            "error": str(exc),
                            "completed_at": _utcnow(),
                        }
                    },
                )
                raise

            await db.tool_call_log.update_one(
                {"idempotency_key": key},
                {
                    "$set": {
                        "status": "success",  # matches the tool_call_log enum
                        "completed_at": _utcnow(),
                        "result": result,
                        "result_hash": sha256_hex(result),
                    }
                },
            )
            return result

        wrapper.__wrapped__ = inner  # type: ignore[attr-defined]
        wrapper._tool_name = tool_name  # type: ignore[attr-defined]
        wrapper._side_effect_class = side_effect_class  # type: ignore[attr-defined]
        wrapper._agent = agent  # type: ignore[attr-defined]

        if not inspect.iscoroutinefunction(inner):
            raise TypeError(f"{tool_name} must be `async def`")
        tool_registry[tool_name] = wrapper  # type: ignore[assignment]
        return wrapper  # type: ignore[return-value]

    if fn is not None:
        return _decorate(fn)
    return _decorate
