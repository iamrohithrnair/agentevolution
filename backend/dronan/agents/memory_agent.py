"""MemoryAgent — recall lessons + write reflections."""

from __future__ import annotations

from typing import Any

from ..tools.memory import vector_search
from ._base import agent_node


@agent_node("memory")
async def memory_node(state: dict, *, db: Any) -> dict:
    """Pull top-k mission_memory cards relevant to the current request."""
    query = state.get("request") or ""
    parsed = state.get("parsed_task") or {}
    if parsed.get("locations"):
        query = f"{query} {' '.join(parsed['locations'])}"

    if not query.strip() or db is None:
        return {"plan_step_log": [{"agent": "memory", "cards": 0}]}

    cards = await vector_search(
        db=db,
        query=query.strip(),
        collection="mission_memory",
        k=5,
        idempotency_key=f"mem:{state.get('mission_id', 'anon')}",
    )
    return {
        "plan_step_log": [{"agent": "memory", "cards": len(cards)}],
        "tool_calls": [{"tool": "vector_search", "agent": "memory", "n": len(cards)}],
    }
