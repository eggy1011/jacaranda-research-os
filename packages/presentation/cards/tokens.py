"""Framework-agnostic design tokens for the 9:16 knowledge cards.

The PPTX theme (``template/theme.py``) returns python-pptx types (RGBColor, Emu) and is
bound to a 16:9 landscape page, so it cannot be reused by a raster/vector card renderer.
This module reads the SAME ``design-tokens.json`` and exposes plain hex strings and pixel
geometry for a 1080x1920 portrait canvas — one source of truth, two consumers.
"""

from __future__ import annotations

import json
from pathlib import Path

TOKENS_PATH = Path(__file__).resolve().parents[1] / "design-tokens.json"

# Canonical card canvas (v2 contract): 9:16 portrait.
CARD_W = 1080
CARD_H = 1920

# The seven fixed card roles, in canonical order.
ROLE_ORDER = ["cover", "full_year", "driver_1", "driver_2",
              "profit_quality", "latest_quarter", "counter_conclusion"]

# Per-role character caps, shared by the renderer's wrapper and the validator's overflow check so
# over-limit copy is a planning failure rather than a silent ellipsis. Values are chars = the
# wrap width × the line budget for that field.
CARD_TEXT_CAPS = {
    "default": {"hook": 33, "body": 80, "caveat": 44},   # 11×3, 20×4, 22×2
    "cover": {"hook": 27, "body": 60, "caveat": 44},     # 9×3, 20×3
}

# Display transforms shared with the schemas. Values mirror slide-deck / social-card-series
# `display_transform` enums; the divisor converts a stored metric value into display units.
TRANSFORM_DIVISOR = {
    "raw": 1.0,
    "percent": 1.0,
    "multiple": 1.0,
    "thousand": 1e3,
    "wan": 1e4,
    "million": 1e6,
    "yi": 1e8,
    "billion": 1e9,
}
TRANSFORM_SUFFIX = {
    "raw": "",
    "percent": "%",
    "multiple": "x",
    "thousand": "千",
    "wan": "万",
    "million": "百万",
    "yi": "亿",
    "billion": "十亿",
}


class CardTokens:
    """Hex colours, font stacks and portrait geometry resolved from design-tokens.json."""

    def __init__(self, raw: dict) -> None:
        self._raw = raw

    # -- colour ---------------------------------------------------------------
    def _brand(self, key: str) -> str:
        return self._raw["color"]["brand"][key]["value"]

    @property
    def primary(self) -> str:
        return self._brand("primary")

    @property
    def dark(self) -> str:
        return self._brand("dark")

    @property
    def light(self) -> str:
        return self._brand("light")

    @property
    def tint(self) -> str:
        return self._brand("tint")

    @property
    def mid(self) -> str:
        return self._brand("mid")

    @property
    def background(self) -> str:
        return self._raw["color"]["brand"]["background_alt"]["value"]

    @property
    def surface(self) -> str:
        return self._brand("surface")

    @property
    def body_text(self) -> str:
        return self._raw["color"]["text"]["body"]["value"]

    @property
    def muted(self) -> str:
        return self._raw["color"]["text"]["muted"]["value"]

    @property
    def inverse(self) -> str:
        return self._raw["color"]["text"]["inverse"]["value"]

    @property
    def positive(self) -> str:
        return self._raw["color"]["signal"]["positive"]["value"]

    @property
    def negative(self) -> str:
        return self._raw["color"]["signal"]["negative"]["value"]

    @property
    def neutral(self) -> str:
        return self._raw["color"]["signal"]["neutral"]["value"]

    @property
    def gridline(self) -> str:
        return self._raw["chart"]["gridlines"]["color"]

    def series(self, index: int) -> str:
        order = self._raw["color"]["chart_series"]["order"]
        return order[index % len(order)]

    def sign_colour(self, value: float) -> str:
        if value > 0:
            return self.positive
        if value < 0:
            return self.negative
        return self.neutral

    # -- typography -----------------------------------------------------------
    @property
    def font_heading(self) -> str:
        # design-tokens stores "Source Han Serif SC / 思源宋体"; emit a CSS font stack so the
        # SVG resolves on any host, and the PNG backend can substitute a bundled face.
        fam = self._raw["typography"]["font_family"]["cjk_heading"]
        primary = fam["value"].split("/")[0].strip()
        return ", ".join([f"'{primary}'", *(f"'{f}'" for f in fam["fallback"])])

    @property
    def font_body(self) -> str:
        fam = self._raw["typography"]["font_family"]["cjk_body"]
        primary = fam["value"].split("/")[0].strip()
        return ", ".join([f"'{primary}'", *(f"'{f}'" for f in fam["fallback"])])

    # -- portrait geometry (px) ----------------------------------------------
    # The 16:9 inch margins in design-tokens do not transfer to a 9:16 social card, so the
    # card grid is defined here and kept proportional to the 1080px width.
    margin_x = 72
    margin_top = 96
    margin_bottom = 120

    @property
    def content_left(self) -> int:
        return self.margin_x

    @property
    def content_width(self) -> int:
        return CARD_W - 2 * self.margin_x

    @property
    def content_top(self) -> int:
        return self.margin_top

    @property
    def content_bottom(self) -> int:
        return CARD_H - self.margin_bottom


def load_tokens() -> CardTokens:
    return CardTokens(json.loads(TOKENS_PATH.read_text(encoding="utf-8")))


def format_number(value: float, transform: str, decimals: int = 1) -> str:
    """Render a metric value under a declared transform — the ONLY way a number reaches a card.

    Mirrors the validator's binding rule: value / divisor, rounded to `decimals`. No other
    rescaling is permitted, so what the card shows always equals what QC-01 verified.
    """
    if transform not in TRANSFORM_DIVISOR:
        raise ValueError(f"unknown display_transform: {transform}")
    scaled = value / TRANSFORM_DIVISOR[transform]
    text = f"{round(scaled, decimals):,.{decimals}f}"
    return f"{text}{TRANSFORM_SUFFIX[transform]}"
