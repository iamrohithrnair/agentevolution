"""Analytics tools — aggregations + (stubbed) PDF report.

The PDF generator becomes real in P5 when ``reportlab`` is wired in. P2
returns a JSON ``report`` doc the API can render directly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ._decorator import mongo_tool


@mongo_tool(side_effect_class="read", agent="AnalyticsAgent")
async def aggregate_metrics(
    *,
    db: Any,
    since_minutes: int = 60,
) -> dict:
    """Aggregate mission counts, average distance, and tool-call latency."""
    since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)

    mission_count = await db.missions.count_documents({"created_at": {"$gte": since}})
    delivery_count = await db.deliveries.count_documents({"created_at": {"$gte": since}})

    pipeline = [
        {"$match": {"started_at": {"$gte": since}, "status": "completed"}},
        {
            "$group": {
                "_id": "$tool",
                "count": {"$sum": 1},
                "avg_latency_ms": {
                    "$avg": {
                        "$divide": [
                            {"$subtract": ["$completed_at", "$started_at"]},
                            1,
                        ]
                    }
                },
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": 25},
    ]
    try:
        tools = await db.tool_call_log.aggregate(pipeline).to_list(length=25)
    except Exception:
        tools = []

    return {
        "since": since,
        "missions": mission_count,
        "deliveries": delivery_count,
        "tools": tools,
    }


@mongo_tool(side_effect_class="audit", agent="AnalyticsAgent")
async def generate_report(
    *,
    db: Any,
    since_minutes: int = 60,
    format_: str = "json",
) -> dict:
    """Stubbed report generator. Returns a JSON blob; PDF lands in P5."""
    metrics = await aggregate_metrics.__wrapped__(  # type: ignore[attr-defined]
        db=db, since_minutes=since_minutes
    )
    return {"format": format_, "metrics": metrics}
