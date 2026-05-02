"""Server-side SVG chart of ``actual_time_s`` per take.

Why server-side
---------------

The Next.js dashboard (``prompts/09-frontend.md``) renders the live chart
with Recharts. For the FastAPI ``/analytics/svg/<scenario_id>`` endpoint we
want a render that:

- works without any JS dependency (curl-friendly for screenshots in slides),
- renders identically in CI and during the demo,
- can be embedded in the pitch deck PDF without a browser.

So we hand-roll an SVG. No matplotlib / cairo / pillow — they are all heavy,
and an SVG line chart fits in ~80 lines of Python.

Output is a single ``<svg>`` element with a polyline of
``actual_time_s`` per take, axis labels, and a baseline annotation showing
"Take-3 < 90 % × Take-1" (SM-1) when satisfied.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from xml.sax.saxutils import escape as _xml_escape, quoteattr as _xml_quoteattr

# --------------------------------------------------------------------------- #

CHART_WIDTH = 640
CHART_HEIGHT = 360
PADDING_LEFT = 56
PADDING_RIGHT = 24
PADDING_TOP = 40
PADDING_BOTTOM = 56
LINE_COLOUR = "#0ea5e9"
TARGET_COLOUR = "#22c55e"
GRID_COLOUR = "#e2e8f0"
AXIS_COLOUR = "#475569"
TEXT_COLOUR = "#0f172a"


@dataclass
class ChartPoint:
    take: int
    actual_time_s: float


def _scale(value: float, low: float, high: float, out_low: float, out_high: float) -> float:
    if high == low:
        return out_low
    return out_low + (value - low) * (out_high - out_low) / (high - low)


def _fmt(v: float) -> str:
    return f"{v:.1f}"


def _attr(s: str) -> str:
    """Quote ``s`` for safe interpolation as an XML attribute value.

    ``xml.sax.saxutils.quoteattr`` returns the value *with* its surrounding
    quotes (so the f-string mustn't add its own).
    """
    return _xml_quoteattr(s)


def _text(s: str) -> str:
    """Escape ``s`` for safe interpolation as XML element text content."""
    return _xml_escape(s)


def render_actual_time_svg(
    points: Iterable[ChartPoint | dict],
    *,
    scenario_id: str = "airport_corridor_storm",
    title: str = "Actual time per take",
) -> str:
    """Return an SVG ``<svg>...</svg>`` string of ``actual_time_s`` per take.

    Accepts either :class:`ChartPoint` instances or plain ``{"take", "actual_time_s"}``
    dicts so the runner's ``TakeResult.__dict__`` can be passed directly.
    """
    pts: list[ChartPoint] = []
    for p in points:
        if isinstance(p, ChartPoint):
            pts.append(p)
        else:
            pts.append(ChartPoint(take=int(p["take"]), actual_time_s=float(p["actual_time_s"])))

    if not pts:
        return _empty_svg(title)

    pts.sort(key=lambda x: x.take)
    xs = [p.take for p in pts]
    ys = [p.actual_time_s for p in pts]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    # Pad y so the line doesn't sit on the axis
    y_lo = max(0.0, y_min - (y_max - y_min) * 0.15) if y_max != y_min else max(0.0, y_min - 5)
    y_hi = y_max + (y_max - y_min) * 0.15 if y_max != y_min else y_max + 5

    plot_left = PADDING_LEFT
    plot_right = CHART_WIDTH - PADDING_RIGHT
    plot_top = PADDING_TOP
    plot_bottom = CHART_HEIGHT - PADDING_BOTTOM

    def px(p: ChartPoint) -> tuple[float, float]:
        x = (
            _scale(p.take, x_min, x_max, plot_left, plot_right)
            if x_max != x_min
            else (plot_left + plot_right) / 2
        )
        y = _scale(p.actual_time_s, y_lo, y_hi, plot_bottom, plot_top)
        return x, y

    polyline_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (px(p) for p in pts))
    circles = "\n".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{LINE_COLOUR}" />'
        for x, y in (px(p) for p in pts)
    )
    point_labels = "\n".join(
        f'<text x="{x:.1f}" y="{y - 10:.1f}" text-anchor="middle" '
        f'font-family="ui-sans-serif, system-ui" font-size="11" fill="{TEXT_COLOUR}">{_fmt(p.actual_time_s)}s</text>'
        for p, (x, y) in zip(pts, (px(p) for p in pts), strict=False)
    )
    x_ticks = "\n".join(
        f'<text x="{_scale(t, x_min, x_max, plot_left, plot_right) if x_max != x_min else (plot_left + plot_right) / 2:.1f}" '
        f'y="{plot_bottom + 18}" text-anchor="middle" font-family="ui-sans-serif, system-ui" '
        f'font-size="11" fill="{AXIS_COLOUR}">Take {t}</text>'
        for t in xs
    )

    # Y-axis ticks at low / mid / high
    y_low_v, y_mid_v, y_hi_v = y_lo, (y_lo + y_hi) / 2, y_hi
    y_ticks_html = "\n".join(
        f'<text x="{plot_left - 8}" y="{_scale(v, y_lo, y_hi, plot_bottom, plot_top) + 4:.1f}" '
        f'text-anchor="end" font-family="ui-sans-serif, system-ui" font-size="11" '
        f'fill="{AXIS_COLOUR}">{_fmt(v)}s</text>'
        for v in (y_low_v, y_mid_v, y_hi_v)
    )

    # SM-1 annotation: highlight Take-3 < 90 % × Take-1 if satisfied.
    sm1_line = ""
    sm1_text = ""
    if len(pts) >= 3:
        # SM-1 is specifically Take-3 ÷ Take-1; not last-take ÷ first-take.
        # Locate by ``take`` field rather than positional index, since
        # the runner could in principle skip a take number.
        take_1 = next((p for p in pts if p.take == 1), pts[0])
        take_3 = next((p for p in pts if p.take == 3), pts[2])
        target = take_1.actual_time_s * 0.9
        target_y = _scale(target, y_lo, y_hi, plot_bottom, plot_top)
        sm1_line = (
            f'<line x1="{plot_left}" y1="{target_y:.1f}" x2="{plot_right}" y2="{target_y:.1f}" '
            f'stroke="{TARGET_COLOUR}" stroke-width="1.5" stroke-dasharray="6,4" />'
        )
        ratio = take_3.actual_time_s / take_1.actual_time_s if take_1.actual_time_s else 1.0
        passes = ratio < 0.9
        verdict = "PASS" if passes else "MISS"
        sm1_text = (
            f'<text x="{plot_right - 4}" y="{target_y - 6:.1f}" text-anchor="end" '
            f'font-family="ui-sans-serif, system-ui" font-size="11" fill="{TARGET_COLOUR}">'
            f"SM-1 target (90% × Take-1) — {verdict} ({ratio * 100:.1f}%)</text>"
        )

    # ``title`` and ``scenario_id`` are caller-supplied and the renderer is
    # exposed via the FastAPI ``/analytics/svg/<scenario_id>`` route, so we
    # have to assume both are attacker-influenced. Escape them as XML text
    # for element content and quote-attr them for any attribute use to
    # prevent SVG/XSS injection.
    title_attr = _attr(title)
    title_text = _text(title)
    scenario_text = _text(scenario_id)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}" width="{CHART_WIDTH}" height="{CHART_HEIGHT}" role="img" aria-label={title_attr}>
  <rect x="0" y="0" width="{CHART_WIDTH}" height="{CHART_HEIGHT}" fill="white" />
  <text x="{CHART_WIDTH / 2}" y="22" text-anchor="middle" font-family="ui-sans-serif, system-ui" font-size="14" font-weight="600" fill="{TEXT_COLOUR}">{title_text} · {scenario_text}</text>

  <g stroke="{GRID_COLOUR}" stroke-width="1">
    <line x1="{plot_left}" y1="{plot_top}" x2="{plot_right}" y2="{plot_top}" />
    <line x1="{plot_left}" y1="{(plot_top + plot_bottom) / 2}" x2="{plot_right}" y2="{(plot_top + plot_bottom) / 2}" />
    <line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" />
  </g>

  <line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" stroke="{AXIS_COLOUR}" stroke-width="1" />
  <line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" stroke="{AXIS_COLOUR}" stroke-width="1" />

  {sm1_line}

  <polyline fill="none" stroke="{LINE_COLOUR}" stroke-width="2.5" points="{polyline_pts}" />
  {circles}
  {point_labels}
  {x_ticks}
  {y_ticks_html}
  {sm1_text}

  <text x="{plot_left - 36}" y="{(plot_top + plot_bottom) / 2}" transform="rotate(-90 {plot_left - 36} {(plot_top + plot_bottom) / 2})" text-anchor="middle" font-family="ui-sans-serif, system-ui" font-size="12" fill="{AXIS_COLOUR}">actual_time_s</text>
</svg>"""


def _empty_svg(title: str) -> str:
    title_attr = _attr(title)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}" width="{CHART_WIDTH}" height="{CHART_HEIGHT}" role="img" aria-label={title_attr}>
  <rect x="0" y="0" width="{CHART_WIDTH}" height="{CHART_HEIGHT}" fill="white" />
  <text x="{CHART_WIDTH / 2}" y="{CHART_HEIGHT / 2}" text-anchor="middle" font-family="ui-sans-serif, system-ui" font-size="14" fill="{AXIS_COLOUR}">No takes recorded yet.</text>
</svg>"""
