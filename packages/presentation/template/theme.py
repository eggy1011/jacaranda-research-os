"""Jacaranda theme: design-token loading, colours, bilingual fonts, page geometry.

All styling flows from packages/presentation/design-tokens.json — no per-slide styling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pptx.dml.color import RGBColor
from pptx.util import Emu, Inches, Pt

TOKENS_PATH = Path(__file__).resolve().parents[1] / "design-tokens.json"

EMU_PER_IN = 914400


def _rgb(hex_str: str) -> RGBColor:
    return RGBColor.from_string(hex_str.lstrip("#"))


@dataclass(frozen=True)
class Fonts:
    latin_heading: str
    latin_body: str
    cjk_heading: str
    cjk_body: str
    numeric: str


@dataclass(frozen=True)
class Theme:
    tokens: dict

    # -- colours -------------------------------------------------------------
    @property
    def primary(self) -> RGBColor:
        return _rgb(self.tokens["color"]["brand"]["primary"]["value"])

    @property
    def dark(self) -> RGBColor:
        return _rgb(self.tokens["color"]["brand"]["dark"]["value"])

    @property
    def light(self) -> RGBColor:
        return _rgb(self.tokens["color"]["brand"]["light"]["value"])

    @property
    def tint(self) -> RGBColor:
        return _rgb(self.tokens["color"]["brand"]["tint"]["value"])

    @property
    def mid(self) -> RGBColor:
        return _rgb(self.tokens["color"]["brand"]["mid"]["value"])

    @property
    def background(self) -> RGBColor:
        return _rgb(self.tokens["color"]["brand"]["background"]["value"])

    @property
    def surface(self) -> RGBColor:
        return _rgb(self.tokens["color"]["brand"]["surface"]["value"])

    @property
    def body_text(self) -> RGBColor:
        return _rgb(self.tokens["color"]["text"]["body"]["value"])

    @property
    def muted(self) -> RGBColor:
        return _rgb(self.tokens["color"]["text"]["muted"]["value"])

    @property
    def inverse(self) -> RGBColor:
        return _rgb(self.tokens["color"]["text"]["inverse"]["value"])

    @property
    def positive(self) -> RGBColor:
        return _rgb(self.tokens["color"]["signal"]["positive"]["value"])

    @property
    def negative(self) -> RGBColor:
        return _rgb(self.tokens["color"]["signal"]["negative"]["value"])

    @property
    def gridline(self) -> RGBColor:
        return _rgb(self.tokens["chart"]["gridlines"]["color"])

    def series_color(self, index: int) -> RGBColor:
        order = self.tokens["color"]["chart_series"]["order"]
        return _rgb(order[index % len(order)])

    # -- typography ----------------------------------------------------------
    @property
    def fonts(self) -> Fonts:
        f = self.tokens["typography"]["font_family"]
        return Fonts(
            latin_heading=f["latin_heading"]["value"],
            latin_body=f["latin_body"]["value"],
            cjk_heading=f["cjk_heading"]["value"].split(" / ")[0],
            cjk_body=f["cjk_body"]["value"].split(" / ")[0],
            numeric=f["numeric"]["value"],
        )

    def size_pt(self, role: str, lang: str) -> int:
        return int(self.tokens["typography"]["scale_pt"][role]["zh" if lang == "zh" else "en"])

    def line_height(self, lang: str) -> float:
        lh = self.tokens["typography"]["line_height"]
        return float(lh["zh_body"] if lang == "zh" else lh["en_body"])

    # -- geometry ------------------------------------------------------------
    @property
    def page_w(self) -> Emu:
        return Inches(self.tokens["layout"]["slide"]["width_in"])

    @property
    def page_h(self) -> Emu:
        return Inches(self.tokens["layout"]["slide"]["height_in"])

    @property
    def margin(self) -> dict[str, Emu]:
        m = self.tokens["layout"]["margin_in"]
        return {k: Inches(v) for k, v in m.items()}

    @property
    def footer_h(self) -> Emu:
        return Inches(self.tokens["layout"]["footer_band_in"]["height"])

    @property
    def content_left(self) -> Emu:
        return self.margin["left"]

    @property
    def content_width(self) -> Emu:
        return Emu(self.page_w - self.margin["left"] - self.margin["right"])

    @property
    def content_top(self) -> Emu:
        return Inches(1.25)  # below header band (title + rule)

    @property
    def content_bottom(self) -> Emu:
        return Emu(self.page_h - self.margin["bottom"] - self.footer_h)

    @property
    def content_height(self) -> Emu:
        return Emu(self.content_bottom - self.content_top)


def load_theme() -> Theme:
    return Theme(tokens=json.loads(TOKENS_PATH.read_text(encoding="utf-8")))


# -- text helpers -------------------------------------------------------------

def set_run_font(run, theme: Theme, *, lang: str, role: str = "body",
                 size: int | None = None, color: RGBColor | None = None,
                 bold: bool = False, heading: bool = False) -> None:
    """Apply latin + east-asian typefaces so zh and en both render per tokens."""
    f = theme.fonts
    latin = f.latin_heading if heading else f.latin_body
    ea = f.cjk_heading if heading else f.cjk_body
    run.font.name = latin
    run.font.size = Pt(size if size is not None else theme.size_pt(role, lang))
    run.font.bold = bold
    run.font.color.rgb = color if color is not None else theme.body_text
    rPr = run._r.get_or_add_rPr()
    for tag in ("latin", "ea"):
        el = rPr.find(f"{{http://schemas.openxmlformats.org/drawingml/2006/main}}{tag}")
        if el is None:
            el = rPr.makeelement(
                f"{{http://schemas.openxmlformats.org/drawingml/2006/main}}{tag}", {})
            rPr.append(el)
        el.set("typeface", latin if tag == "latin" else ea)


def est_text_width_in(text: str, size_pt: float) -> float:
    """Conservative width estimate (inches) for overflow checking."""
    width_em = 0.0
    for ch in text:
        o = ord(ch)
        if o >= 0x2E80:          # CJK and fullwidth
            width_em += 1.02
        elif ch.isdigit():
            width_em += 0.52
        elif ch in " .,:;'|":
            width_em += 0.30
        elif ch.isupper():
            width_em += 0.68
        else:
            width_em += 0.50
    return width_em * size_pt / 72.0


def est_lines(text: str, size_pt: float, frame_w_in: float) -> int:
    usable = max(frame_w_in - 0.12, 0.3)  # minus text-frame insets
    return max(1, -(-int(est_text_width_in(text, size_pt) * 100) // int(usable * 100)))
