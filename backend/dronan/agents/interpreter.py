"""InterpreterAgent — turn raw operator text into ``parsed_task``.

LLM-free: a pattern-matching parser keyed on the 9 facility names + a small
supply lexicon. Good enough to satisfy the supervisor-routing acceptance
tests and to drive the demo without LLM credentials.
"""

from __future__ import annotations

import re
from typing import Any

from ._base import agent_node

_FACILITIES = {
    "depot": "Depot",
    "clinic a": "Clinic A",
    "clinic b": "Clinic B",
    "clinic c": "Clinic C",
    "clinic d": "Clinic D",
    "royal london": "Royal London",
    "homerton": "Homerton",
    "newham general": "Newham General",
    "newham": "Newham General",
    "whipps cross": "Whipps Cross",
    "whipps": "Whipps Cross",
}

_SUPPLY = {
    "blood": ("blood", "critical"),
    "plasma": ("plasma", "critical"),
    "vaccine": ("vaccine", "high"),
    "vaccines": ("vaccine", "high"),
    "insulin": ("insulin", "high"),
    "medication": ("medication", "normal"),
    "medications": ("medication", "normal"),
    "supplies": ("supplies", "normal"),
}


def _extract_locations(text: str) -> list[str]:
    """Return canonical facility names found in ``text``, preserving order."""
    found: list[tuple[int, str]] = []
    seen_names: set[str] = set()
    lower = text.lower()
    # Greedy multi-word match first.
    for key in sorted(_FACILITIES, key=lambda k: -len(k)):
        for m in re.finditer(rf"\b{re.escape(key)}\b", lower):
            canonical = _FACILITIES[key]
            if canonical in seen_names:
                continue
            seen_names.add(canonical)
            found.append((m.start(), canonical))
    found.sort()
    return [c for _, c in found]


def _extract_supplies(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    lower = text.lower()
    for k, (canonical, _) in _SUPPLY.items():
        if re.search(rf"\b{k}\b", lower):
            out[canonical] = canonical
    return out


def _confidence(parsed: dict[str, Any]) -> float:
    """Naïve confidence: 0.5 base + 0.25 per non-empty channel."""
    score = 0.5
    if parsed.get("locations"):
        score += 0.25
    if parsed.get("supplies"):
        score += 0.25
    return min(score, 1.0)


@agent_node("interpreter")
async def interpreter_node(state: dict) -> dict:
    """Convert ``request`` → ``parsed_task``."""
    text = state.get("request", "")
    if not text:
        return {
            "parsed_task": {
                "locations": [],
                "supplies": {},
                "priorities": {},
                "confidence": 0.0,
            }
        }

    locations = _extract_locations(text)
    supplies = _extract_supplies(text)
    # Priority lookup
    priorities: dict[str, str] = {}
    for s in supplies:
        for k, (_, prio) in _SUPPLY.items():
            if _SUPPLY[k][0] == s:
                priorities[s] = prio
                break

    # Cold-chain ↔ blood/insulin/vaccine
    cold_chain = any(s in supplies for s in ("blood", "vaccine", "insulin"))

    parsed = {
        "locations": locations,
        "supplies": supplies,
        "priorities": priorities,
        "constraints": {"cold_chain_required": cold_chain},
        "confidence": 0.0,
    }
    parsed["confidence"] = _confidence(parsed)

    update: dict[str, Any] = {"parsed_task": parsed}
    if locations:
        update["depot"] = locations[0]
        update["stops"] = locations[1:] or ["Royal London"]
    return update
