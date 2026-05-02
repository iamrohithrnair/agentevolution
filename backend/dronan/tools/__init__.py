"""Tools registry — every external side-effect goes through ``@mongo_tool``.

Importing this package registers the tool functions at import time so the
Supervisor can hand them to LangGraph nodes by name. The registry mirrors
``prompts/01-architecture.md §2`` (agent topology table).
"""

from __future__ import annotations

from ._decorator import (
    ToolError,
    make_idempotency_key,
    mongo_tool,
    sha256_hex,
    tool_registry,
)
from .analytics import aggregate_metrics, generate_report
from .anomaly import inspect_telemetry
from .audit import record_signature
from .drone_control import dispatch_mission, land_drone
from .facilities import get_facility, search_facilities
from .geofence import check_route_safety
from .memory import embed_and_store, summarise_for_planner, vector_search
from .payload import assemble_manifest, cold_chain_predict
from .preflight import run_preflight
from .route_planner import compute_route, recompute_route
from .vision import detect_obstacles, save_frame
from .weather import get_weather, simulate_weather_event

__all__ = [
    "ToolError",
    "aggregate_metrics",
    "assemble_manifest",
    "check_route_safety",
    "cold_chain_predict",
    "compute_route",
    "detect_obstacles",
    "dispatch_mission",
    "embed_and_store",
    "generate_report",
    "get_facility",
    "get_weather",
    "inspect_telemetry",
    "land_drone",
    "make_idempotency_key",
    "mongo_tool",
    "recompute_route",
    "record_signature",
    "run_preflight",
    "save_frame",
    "search_facilities",
    "sha256_hex",
    "simulate_weather_event",
    "summarise_for_planner",
    "tool_registry",
    "vector_search",
]
