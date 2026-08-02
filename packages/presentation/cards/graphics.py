"""Card visuals: brand colour fields, abstract decorative motifs, and bound KPI surfaces.

Per the v2 decision (Q3) there are NO illustrations and no image-model output. Just as important:
nothing here may render a *data-like* mark (a bar whose height, a line whose slope, or a gauge
whose fill implies a quantity) unless that quantity is a validated metric. The card schema carries
no chart series yet, so the non-KPI visuals in this module are deliberately **decorative and
non-quantitative** — abstract brand shapes a viewer cannot misread as data. Actual figures appear
only in KPI stat tiles, which are bound to inline metric references.
"""

from __future__ import annotations

from .svg import Canvas
from .tokens import CARD_W, CardTokens


def brand_field(c: Canvas, t: CardTokens, *, y: float, h: float) -> None:
    """Abstract brand backdrop: soft concentric arcs, decorative only."""
    cx = CARD_W * 0.78
    cy = y + h * 0.42
    for i, r in enumerate((320, 244, 168, 96)):
        c.circle(cx, cy, r, t.light, opacity=0.16 + 0.05 * i)
    c.circle(cx, cy, 44, t.primary, opacity=0.22)


def accent_rule(c: Canvas, t: CardTokens, *, x: float, y: float, w: float = 96) -> None:
    c.rect(x, y, w, 8, t.primary, radius=4)


def motif_band(c: Canvas, t: CardTokens, *, x: float, y: float, w: float, h: float,
               variant: int = 0) -> None:
    """A decorative brand band for cards without KPI figures (drivers, latest_disclosure, closing).

    Intentionally symmetric and quantity-free: overlapping translucent rounded shapes, no axis, no
    data points, no proportional lengths. It fills the composition without implying a measurement.
    """
    c.rect(x, y, w, h, t.tint, radius=28)
    # two offset translucent discs + an accent bar — pure ornament, identical every render
    r = h * 0.44
    c.circle(x + w * 0.30, y + h * 0.5, r, t.light, opacity=0.45)
    c.circle(x + w * 0.62, y + h * 0.5, r * 0.82, t.primary, opacity=0.18)
    bar_w = w * (0.34 + 0.06 * (variant % 3))
    c.rect(x + w * 0.10, y + h * 0.5 - 6, bar_w, 12, t.primary, radius=6, opacity=0.55)


def stat_tile(c: Canvas, t: CardTokens, *, x: float, y: float, w: float, h: float,
              emphasis: bool = False) -> None:
    """Card surface for a KPI figure; the number and label are drawn by the layout."""
    c.rect(x, y, w, h, t.surface if not emphasis else t.tint, radius=24)
    if emphasis:
        c.rect(x, y, w, 8, t.primary, radius=4)
