"""Minimal deterministic SVG builder for the knowledge cards.

Deliberately dependency-free: the SVG document is the canonical render artifact, so it must
be byte-reproducible on any machine. Attributes are emitted in a fixed order and floats are
rounded to a fixed precision — the same card series always produces identical bytes.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from .tokens import CARD_H, CARD_W


def _n(value: float) -> str:
    """Fixed-precision number: avoids platform float-repr drift in the output bytes."""
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _attrs(pairs: list[tuple[str, str]]) -> str:
    return "".join(f' {k}="{escape(str(v), {chr(34): "&quot;"})}"' for k, v in pairs if v != "")


class Canvas:
    """Accumulates SVG elements for one 1080x1920 card."""

    def __init__(self, background: str) -> None:
        self._parts: list[str] = []
        self._background = background

    # -- primitives -----------------------------------------------------------
    def rect(self, x: float, y: float, w: float, h: float, fill: str,
             *, radius: float = 0, opacity: float = 1.0) -> None:
        self._parts.append("<rect" + _attrs([
            ("x", _n(x)), ("y", _n(y)), ("width", _n(w)), ("height", _n(h)),
            ("rx", _n(radius) if radius else ""), ("fill", fill),
            ("opacity", _n(opacity) if opacity != 1.0 else ""),
        ]) + "/>")

    def circle(self, cx: float, cy: float, r: float, fill: str, *, opacity: float = 1.0) -> None:
        self._parts.append("<circle" + _attrs([
            ("cx", _n(cx)), ("cy", _n(cy)), ("r", _n(r)), ("fill", fill),
            ("opacity", _n(opacity) if opacity != 1.0 else ""),
        ]) + "/>")

    def line(self, x1: float, y1: float, x2: float, y2: float, stroke: str,
             *, width: float = 1, dash: str = "") -> None:
        self._parts.append("<line" + _attrs([
            ("x1", _n(x1)), ("y1", _n(y1)), ("x2", _n(x2)), ("y2", _n(y2)),
            ("stroke", stroke), ("stroke-width", _n(width)), ("stroke-dasharray", dash),
            ("stroke-linecap", "round"),
        ]) + "/>")

    def path(self, d: str, *, stroke: str = "none", fill: str = "none",
             width: float = 1, opacity: float = 1.0) -> None:
        self._parts.append("<path" + _attrs([
            ("d", d), ("fill", fill), ("stroke", stroke),
            ("stroke-width", _n(width) if stroke != "none" else ""),
            ("stroke-linejoin", "round"), ("stroke-linecap", "round"),
            ("opacity", _n(opacity) if opacity != 1.0 else ""),
        ]) + "/>")

    def text(self, x: float, y: float, content: str, *, fill: str, size: float,
             font: str, weight: str = "normal", anchor: str = "start",
             letter_spacing: float = 0) -> None:
        self._parts.append("<text" + _attrs([
            ("x", _n(x)), ("y", _n(y)), ("fill", fill), ("font-family", font),
            ("font-size", _n(size)), ("font-weight", weight if weight != "normal" else ""),
            ("text-anchor", anchor if anchor != "start" else ""),
            ("letter-spacing", _n(letter_spacing) if letter_spacing else ""),
        ]) + f">{escape(content)}</text>")

    # -- document -------------------------------------------------------------
    def to_svg(self) -> str:
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_W}" height="{CARD_H}" '
            f'viewBox="0 0 {CARD_W} {CARD_H}">'
        )
        bg = f'<rect x="0" y="0" width="{CARD_W}" height="{CARD_H}" fill="{self._background}"/>'
        return head + bg + "".join(self._parts) + "</svg>\n"


def est_width(text: str, size_pt: float) -> float:
    """Estimate rendered width in px. CJK glyphs are full-width, Latin roughly half.

    Mirrors the estimator in template/theme.py; used to keep footers and headings inside the
    card without needing a font engine at plan time.
    """
    units = sum(1.0 if ord(ch) >= 0x2E80 else 0.52 for ch in text)
    return units * size_pt


# Chinese typography rule (design-tokens.json): a line may not START with closing
# punctuation, and may not END with an opening bracket. Breaking this is the most visible
# way machine-set Chinese looks wrong, so the wrapper enforces it rather than trusting copy.
NO_LINE_START = "。，、；：）」』】〕》”’!%?,.:;)]}"
NO_LINE_END = "（「『【〔《“‘([{"


def wrap_cjk(text: str, max_chars: int, max_lines: int) -> list[str]:
    """Wrap Chinese copy by character count (CJK has no word spaces), obeying kinsoku rules.

    Overflow is truncated with an ellipsis rather than silently spilling outside the card — a
    card that cannot fit its copy is a planning bug, and ``qa_report`` reports it.
    """
    if max_chars < 2:
        raise ValueError("max_chars must be >= 2")
    lines: list[str] = []
    current = ""
    for ch in text:
        if len(current) >= max_chars:
            # never end a line on an opening bracket: carry it to the next line
            if current[-1] in NO_LINE_END:
                current, carry = current[:-1], current[-1]
            else:
                carry = ""
            lines.append(current)
            current = carry
            if len(lines) == max_lines:
                current = ""
                break
        if not current and ch in NO_LINE_START and lines:
            # pull trailing punctuation back onto the previous line instead of orphaning it
            lines[-1] += ch
            continue
        current += ch
    if current and len(lines) < max_lines:
        lines.append(current)
    consumed = sum(len(line) for line in lines)
    if consumed < len(text) and lines:
        last = lines[-1]
        lines[-1] = (last[: max_chars - 1] if len(last) >= max_chars else last) + "…"
    return lines
