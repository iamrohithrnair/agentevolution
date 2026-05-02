"""Specialist agents — each is a node function over MissionState.

Per ``prompts/04-langchain-agents.md`` we ship 17 agents plus a
SupervisorAgent. The body of each agent is intentionally LLM-free in
P3 — every routing/inference choice is a deterministic function of
state + tool output (or, in the SupervisorAgent's case, vector search
over ``agent_skills``). The LLM hookup is a one-line swap in the
agent's ``__call__`` and lives behind a flag in P5.
"""

from __future__ import annotations

from .registry import AGENTS, SPECIALISTS, register_all
from .state import MissionState, Route

__all__ = ["AGENTS", "MissionState", "Route", "SPECIALISTS", "register_all"]
