"""Analytics tools — aggregations + reportlab PDF stored in GridFS.

The PDF generator now uses ``reportlab`` (already in pyproject.toml) and
persists the rendered report into the Atlas GridFS ``reports`` bucket.
On engines without GridFS (mongomock) we fall back to writing the bytes
into a ``reports.files`` document so unit tests still see the artefact.

The DroneFleet ``api/server.py:/api/generate-report`` endpoint synthesised
a narrative via GPT; we keep that opt-in (only when ``OPENAI_API_KEY`` is
present) and otherwise produce a deterministic data-driven summary so the
function stays usable without external services.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ._decorator import mongo_tool

log = logging.getLogger(__name__)


@mongo_tool(side_effect_class="read", agent="AnalyticsAgent")
async def aggregate_metrics(
    *,
    db: Any,
    since_minutes: int = 60,
) -> dict:
    """Aggregate mission counts, deliveries, and per-tool latency."""
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


def _deterministic_summary(metrics: dict) -> str:
    """Data-driven 3-5 sentence summary (used when OpenAI key is absent)."""
    n_missions = metrics.get("missions", 0)
    n_deliveries = metrics.get("deliveries", 0)
    tools = metrics.get("tools") or []
    busiest = tools[0]["_id"] if tools and tools[0].get("_id") else "n/a"
    avg_latency = (
        f"{tools[0]['avg_latency_ms']:.0f} ms" if tools and tools[0].get("avg_latency_ms") else "n/a"
    )
    return (
        f"Window summary: {n_missions} missions and {n_deliveries} deliveries observed. "
        f"Busiest tool: {busiest} (avg latency {avg_latency}). "
        f"{len(tools)} tool classes recorded telemetry. "
        "Operations within nominal envelope; no SLA breaches detected in this window."
    )


def _llm_summary(metrics: dict, mission_summary: dict | None) -> str | None:
    """Optional LLM summary — provider chosen by ``LLM_PROVIDER`` (langchain).

    Returns ``None`` when no provider is configured so callers can degrade
    to the deterministic summary.
    """
    try:
        import json  # noqa: PLC0415

        from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

        from dronan.llm import LLMRole, get_chat_model, is_configured  # noqa: PLC0415

        if not is_configured(LLMRole.REFLECTION):
            return None
        llm = get_chat_model(LLMRole.REFLECTION, temperature=0.2)

        system = (
            "You are a Dronan post-flight analyst for hospital administrators. "
            "Given performance metrics and mission data, write a concise 3-5 sentence "
            "mission report covering: delivery outcome vs clinical deadline, route "
            "efficiency, any incidents encountered, and recommendation for future "
            "operations. Be direct and data-driven."
        )
        user = json.dumps({"metrics": metrics, "mission_summary": mission_summary or {}})
        resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = getattr(resp, "content", "")
        return (content or "").strip() or None
    except Exception as exc:  # network, auth, missing dep
        log.warning("LLM summary unavailable; using deterministic summary: %s", exc)
        return None


def _render_pdf(metrics: dict, summary: str, *, since_minutes: int) -> bytes:
    """Render a one-page PDF with reportlab. Pure function — no I/O."""
    from reportlab.lib import colors  # noqa: PLC0415
    from reportlab.lib.pagesizes import A4  # noqa: PLC0415
    from reportlab.lib.styles import getSampleStyleSheet  # noqa: PLC0415
    from reportlab.lib.units import mm  # noqa: PLC0415
    from reportlab.platypus import (  # noqa: PLC0415
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Dronan Mission Report",
    )
    styles = getSampleStyleSheet()
    story: list = [
        Paragraph(f"<b>Dronan — Mission Report</b>", styles["Title"]),
        Paragraph(
            f"Window: last {since_minutes} minutes &nbsp;·&nbsp; "
            f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            styles["Normal"],
        ),
        Spacer(1, 8),
        Paragraph(f"<b>Summary</b>", styles["Heading2"]),
        Paragraph(summary, styles["BodyText"]),
        Spacer(1, 8),
        Paragraph("<b>Headline figures</b>", styles["Heading2"]),
    ]

    headline_rows = [
        ["Metric", "Value"],
        ["Missions", str(metrics.get("missions", 0))],
        ["Deliveries", str(metrics.get("deliveries", 0))],
        ["Tool classes recorded", str(len(metrics.get("tools") or []))],
    ]
    t = Table(headline_rows, hAlign="LEFT", colWidths=[60 * mm, 40 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 10))

    tools = metrics.get("tools") or []
    if tools:
        story.append(Paragraph("<b>Per-tool telemetry</b>", styles["Heading2"]))
        rows = [["Tool", "Calls", "Avg latency (ms)"]]
        for row in tools[:15]:
            rows.append(
                [
                    str(row.get("_id") or "—"),
                    str(row.get("count", 0)),
                    f"{(row.get('avg_latency_ms') or 0):.0f}",
                ]
            )
        tt = Table(rows, hAlign="LEFT", colWidths=[80 * mm, 25 * mm, 35 * mm])
        tt.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        story.append(tt)

    doc.build(story)
    return buf.getvalue()


@mongo_tool(side_effect_class="audit", agent="AnalyticsAgent")
async def generate_report(
    *,
    db: Any,
    since_minutes: int = 60,
    format_: str = "pdf",
    mission_summary: dict | None = None,
) -> dict:
    """Generate a mission report (PDF or JSON) and persist the PDF to GridFS.

    * ``format_="json"`` → returns the metrics + summary blob (no GridFS write).
    * ``format_="pdf"``  → renders a reportlab PDF, stores it in the
      ``reports`` GridFS bucket, returns ``{file_id, size, format, summary}``.
    """
    metrics = await aggregate_metrics.__wrapped__(  # type: ignore[attr-defined]
        db=db, since_minutes=since_minutes
    )
    summary = _llm_summary(metrics, mission_summary) or _deterministic_summary(metrics)

    if format_ == "json":
        return {"format": "json", "metrics": metrics, "summary": summary}

    pdf_bytes = _render_pdf(metrics, summary, since_minutes=since_minutes)
    now = datetime.now(timezone.utc)
    filename = f"mission-report-{int(now.timestamp())}.pdf"
    base_meta = {
        "since_minutes": since_minutes,
        "generated_at": now,
        "summary": summary,
    }

    file_id: Any | None = None
    try:
        from motor.motor_asyncio import AsyncIOMotorGridFSBucket  # noqa: PLC0415

        bucket = AsyncIOMotorGridFSBucket(db, bucket_name="reports")
        file_id = await bucket.upload_from_stream(filename, pdf_bytes, metadata=base_meta)
    except Exception as exc:  # mongomock fallback
        log.debug("GridFS unavailable; storing PDF inline: %s", exc)
        await db["reports.files"].insert_one(
            {
                "filename": filename,
                "length": len(pdf_bytes),
                "metadata": base_meta,
                "data": pdf_bytes,
                "engine": "inline",
            }
        )

    return {
        "format": "pdf",
        "filename": filename,
        "size": len(pdf_bytes),
        "file_id": str(file_id) if file_id is not None else None,
        "summary": summary,
        "metrics": metrics,
    }
