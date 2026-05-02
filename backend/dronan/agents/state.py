"""``MissionState`` — the LangGraph TypedDict every node reads/writes.

Verbatim from ``prompts/04-langchain-agents.md §1.1``. The reducer
annotations are what let parallel nodes (Anomaly + Vision + Weather +
Decon) write concurrently without last-writer-wins clobbering.
"""

from __future__ import annotations

from datetime import datetime
from operator import add
from typing import Annotated, Any, Literal, TypedDict

Route = Literal[
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
    "__end__",
]


class MissionState(TypedDict, total=False):
    """LangGraph state channel."""

    operator_id: str
    mission_id: str  # == LangGraph thread_id
    request: str
    parsed_task: dict[str, Any]
    route: Route
    last_routed_to: Route
    needs_replan: bool
    altitude_m: float
    route_history: Annotated[list[Route], add]
    live_telemetry: dict[str, Any]
    weather: dict[str, Any]
    no_fly_violations: list[dict[str, Any]]
    payload_status: dict[str, Any]
    plan: dict[str, Any]
    anomalies: Annotated[list[dict[str, Any]], add]
    obstacles: Annotated[list[dict[str, Any]], add]
    reflection: dict[str, Any]
    errors: Annotated[list[dict[str, Any]], add]
    plan_step_log: Annotated[list[dict[str, Any]], add]
    tool_calls: Annotated[list[dict[str, Any]], add]
    context_budget_tokens: int
    started_at: datetime
    updated_at: datetime
    # Operator-controllable knobs
    depot: str
    stops: list[str]
    drone_id: str
    delivery_ids: list[str]
