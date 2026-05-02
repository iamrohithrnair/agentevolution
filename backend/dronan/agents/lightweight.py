"""Lightweight agents — vision / replanner / anomaly / deconfliction /
narrator / analyst / reflection / demand_forecast.

P3 ships these as deterministic shells that satisfy the LangGraph topology
(every node from the architecture diagram exists, every node returns a
state-update dict). The richer LLM-driven reasoning is a one-line swap in
each ``__call__`` and lands in P5.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..tools.analytics import aggregate_metrics
from ..tools.anomaly import inspect_telemetry
from ..tools.audit import record_signature
from ..memory import write_reflection
from ..tools.vision import detect_obstacles
from ._base import agent_node


@agent_node("vision")
async def vision_node(state: dict, *, db: Any) -> dict:
    res = await detect_obstacles(
        db=db,
        frame_bytes=b"",
        mission_id=state.get("mission_id"),
        idempotency_key=f"vis:{state.get('mission_id', 'anon')}",
    )
    return {
        "obstacles": res.get("detections") or [],
        "tool_calls": [{"tool": "detect_obstacles", "agent": "vision"}],
    }


@agent_node("anomaly")
async def anomaly_node(state: dict, *, db: Any) -> dict:
    mission_id = state.get("mission_id")
    if not mission_id:
        return {"anomalies": []}
    res = await inspect_telemetry(
        db=db,
        mission_id=mission_id,
        window_minutes=10,
        idempotency_key=f"anom:{mission_id}",
    )
    return {
        "anomalies": res.get("anomalies") or [],
        "tool_calls": [{"tool": "inspect_telemetry", "agent": "anomaly"}],
    }


@agent_node("deconfliction")
async def deconfliction_node(state: dict, *, db: Any) -> dict:
    """Stub — a real implementation would query nearby active missions."""
    nearby = await db.missions.count_documents({"status": "executing"})
    return {
        "plan_step_log": [{"agent": "deconfliction", "nearby_active": nearby}],
    }


@agent_node("replanner")
async def replanner_node(state: dict) -> dict:
    """Decide whether replanning is needed based on accumulated signals."""
    needs_replan = (
        bool(state.get("no_fly_violations"))
        or any(a.get("kind") == "battery_sag" for a in state.get("anomalies", []))
        or not (state.get("weather") or {}).get("flyable", True)
    )
    return {
        "plan_step_log": [{"agent": "replanner", "needs_replan": needs_replan}],
        "needs_replan": needs_replan,
    }


@agent_node("narrator")
async def narrator_node(state: dict, *, db: Any) -> dict:
    """Persist a one-line narration row keyed on mission_id."""
    line = (
        f"Mission {state.get('mission_id', '?')}: "
        f"{len(state.get('route_history', []))} hops, "
        f"errors={len(state.get('errors', []))}."
    )
    if db is not None:
        await db.narrations.insert_one(
            {
                "mission_id": state.get("mission_id"),
                "ts": datetime.now(timezone.utc),
                "line": line,
            }
        )
    return {"plan_step_log": [{"agent": "narrator", "line": line}]}


@agent_node("analyst")
async def analyst_node(state: dict, *, db: Any) -> dict:
    res = await aggregate_metrics(
        db=db,
        since_minutes=60,
        idempotency_key=f"analyst:{state.get('mission_id', 'anon')}",
    )
    return {
        "plan_step_log": [{"agent": "analyst", "missions": res.get("missions", 0)}],
        "tool_calls": [{"tool": "aggregate_metrics", "agent": "analyst"}],
    }


@agent_node("reflection")
async def reflection_node(state: dict, *, db: Any) -> dict:
    """Write a reflection card if we observed something noteworthy."""
    mission_id = state.get("mission_id")
    if not mission_id or db is None:
        return {"reflection": {"written": False}}

    if not (state.get("anomalies") or state.get("no_fly_violations") or state.get("errors")):
        return {"reflection": {"written": False}}

    text = (
        f"Mission {mission_id}: anomalies={len(state.get('anomalies', []))}, "
        f"violations={len(state.get('no_fly_violations', []))}, "
        f"errors={len(state.get('errors', []))}."
    )
    res = await write_reflection(
        db=db,
        mission_id=mission_id,
        text=text,
        tags=["mission_summary"],
        idempotency_key=f"refl:{mission_id}",
    )

    # Also stamp an audit signature for the post-flight chain of custody.
    await record_signature(
        db=db,
        mission_id=mission_id,
        step="reflection",
        payload={"summary": text},
        idempotency_key=f"sig:{mission_id}:reflection",
    )

    return {
        "reflection": {"written": True, "id": res.get("id")},
        "tool_calls": [{"tool": "write_reflection", "agent": "reflection"}],
    }


@agent_node("demand_forecast")
async def demand_forecast_node(state: dict, *, db: Any) -> dict:
    """Naïve forecast — count of pending deliveries grouped by destination."""
    if db is None:
        return {"plan_step_log": [{"agent": "demand_forecast", "pending": 0}]}
    pending = await db.deliveries.count_documents({"status": "pending"})
    horizon = datetime.now(timezone.utc) + timedelta(hours=4)
    return {
        "plan_step_log": [
            {
                "agent": "demand_forecast",
                "pending": pending,
                "horizon": horizon,
            }
        ]
    }
