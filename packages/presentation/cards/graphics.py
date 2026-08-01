"""Pure-graphical card visuals: brand colour fields, abstract shapes and code-drawn data.

Per the v2 decision (Q3) there are NO illustrations and no image-model output — every mark is
a deterministic SVG primitive derived from design tokens. Nothing here invents a number: all
values arrive already resolved from a metric reference at its declared transform.
"""

from __future__ import annotations

from .svg import Canvas
from .tokens import CardTokens


def brand_field(c: Canvas, t: CardTokens, *, y: float, h: float) -> None:
    """Abstract brand backdrop: soft concentric arcs, suggesting growth without depicting."""
    cx = 1080 * 0.78
    cy = y + h * 0.42
    for i, r in enumerate((320, 244, 168, 96)):
        c.circle(cx, cy, r, t.light, opacity=0.16 + 0.05 * i)
    c.circle(cx, cy, 44, t.primary, opacity=0.22)


def accent_rule(c: Canvas, t: CardTokens, *, x: float, y: float, w: float = 96) -> None:
    c.rect(x, y, w, 8, t.primary, radius=4)


def sparkline(c: Canvas, t: CardTokens, values: list[float], *,
              x: float, y: float, w: float, h: float) -> None:
    """Trend line over already-resolved values. Shape only — no axis numbers are printed,
    so the chart can never introduce a number that QC-01 did not bind."""
    if len(values) < 2:
        return
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = w / (len(values) - 1)
    pts = [(x + i * step, y + h - (v - lo) / span * h) for i, v in enumerate(values)]

    area = f"M {pts[0][0]:.2f} {pts[0][1]:.2f} " + " ".join(
        f"L {px:.2f} {py:.2f}" for px, py in pts[1:]
    ) + f" L {pts[-1][0]:.2f} {y + h:.2f} L {pts[0][0]:.2f} {y + h:.2f} Z"
    c.path(area, fill=t.light, opacity=0.35)
    trend = "M " + " L ".join(f"{px:.2f} {py:.2f}" for px, py in pts)
    c.path(trend, stroke=t.primary, width=6)
    for px, py in pts:
        c.circle(px, py, 9, t.surface)
        c.circle(px, py, 5, t.primary)


def bar_pair(c: Canvas, t: CardTokens, left: float, right: float, *,
             x: float, y: float, w: float, h: float) -> None:
    """Two-bar comparison (driver cards). Bars are proportional; labels are drawn by the layout."""
    peak = max(abs(left), abs(right)) or 1.0
    gap = 40
    bw = (w - gap) / 2
    for i, value in enumerate((left, right)):
        bh = max(12.0, abs(value) / peak * h)
        bx = x + i * (bw + gap)
        c.rect(bx, y + h - bh, bw, bh, t.series(i), radius=12)


def ring(c: Canvas, t: CardTokens, fraction: float, *, cx: float, cy: float, r: float) -> None:
    """Ring gauge for a share/margin already resolved as a percentage (0..1)."""
    import math

    frac = max(0.0, min(1.0, fraction))
    c.circle(cx, cy, r, t.tint)
    c.circle(cx, cy, r * 0.72, t.background)
    if frac <= 0:
        return
    start = -math.pi / 2
    end = start + 2 * math.pi * frac
    steps = max(2, int(frac * 72))
    outer, inner = r, r * 0.72
    pts_out = [
        (cx + outer * math.cos(start + (end - start) * i / steps),
         cy + outer * math.sin(start + (end - start) * i / steps))
        for i in range(steps + 1)
    ]
    pts_in = [
        (cx + inner * math.cos(start + (end - start) * i / steps),
         cy + inner * math.sin(start + (end - start) * i / steps))
        for i in range(steps, -1, -1)
    ]
    d = ("M " + " L ".join(f"{px:.2f} {py:.2f}" for px, py in pts_out + pts_in) + " Z")
    c.path(d, fill=t.primary)


def stat_tile(c: Canvas, t: CardTokens, *, x: float, y: float, w: float, h: float,
              emphasis: bool = False) -> None:
    """Card surface for a KPI figure; the number and label are drawn by the layout."""
    c.rect(x, y, w, h, t.surface if not emphasis else t.tint, radius=24)
    if emphasis:
        c.rect(x, y, w, 8, t.primary, radius=4)
