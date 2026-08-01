"""Deterministic renderer: social-card-series + research package -> seven 9:16 cards.

Contract (v2):
  * exactly seven cards, fixed roles, 1080x1920 each;
  * every displayed number is resolved from a metric reference at its DECLARED transform and
    decimals — the renderer never rescales, rounds differently, or invents a figure;
  * every card carries a source line (cutoff + SRC ids); the closing card carries the caveat;
  * output is byte-reproducible, and each card is hashed into a manifest.

SVG is the canonical artifact because it is pure text and therefore identical on every
machine. PNG rasterisation is an optional backend (see ``rasterise``): it depends on locally
installed CJK fonts, so it is never allowed to be the source of truth for determinism.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from . import graphics as g
from .svg import NO_LINE_START, Canvas, est_width, wrap_cjk
from .tokens import CARD_H, CARD_W, CardTokens, format_number, load_tokens
from .validate import RENDERABLE_STATUS, validate_series

ROLE_KICKER = {
    "cover": "研究问题",
    "full_year": "完整年度",
    "driver_1": "核心驱动 ①",
    "driver_2": "核心驱动 ②",
    "profit_quality": "盈利与质量",
    "latest_quarter": "最新季度信号",
    "counter_conclusion": "反面证据与结论",
}
CLAIM_CHIP = {"fact": "事实", "inference": "推断", "opinion": "观点"}
DISCLAIMER = "仅供学习研究，不构成投资建议"


class CardRenderError(RuntimeError):
    """Raised when a series cannot be rendered — never rendered partially or silently."""


# --------------------------------------------------------------------------- numbers

def resolve_numbers(card: dict, metrics: dict) -> list[dict]:
    """Resolve each declared inline number. This is the ONLY path from data to pixels."""
    out = []
    for dn in card.get("inline_numbers", []):
        mid = dn["metric_id"]
        if mid not in metrics:
            raise CardRenderError(f"card {card['card_no']}: unknown metric {mid}")
        metric = metrics[mid]
        decimals = dn.get("decimals", 1)
        out.append({
            "metric_id": mid,
            "text": format_number(metric["value"], dn["display_transform"], decimals),
            "raw": metric["value"],
            "label": metric.get("name") if isinstance(metric.get("name"), str) else "",
            "signed": dn.get("show_sign_colour", False),
            "transform": dn["display_transform"],
        })
    return out


# --------------------------------------------------------------------------- chrome

def _wrap_by_width(segments: list[str], joiner: str, size: float, max_width: float) -> list[str]:
    """Greedily pack joiner-separated segments into lines no wider than max_width."""
    lines: list[str] = []
    current = ""
    for seg in segments:
        candidate = seg if not current else f"{current}{joiner}{seg}"
        if current and est_width(candidate, size) > max_width:
            lines.append(current)
            current = seg
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _footer_lines(source_ids: list[str], as_of: str, *, size: int, max_width: float) -> list[str]:
    """Source line (wrapped across as many lines as needed) followed by the disclaimer.

    The closing card carries the full source union, which can be wide; the source string is
    wrapped on SRC boundaries so it never runs off the card or into the disclaimer.
    """
    segments = [f"数据来源：{source_ids[0]}" if source_ids else "数据来源：—", *source_ids[1:]]
    segments.append(f"截止 {as_of}")
    lines = _wrap_by_width(segments, "、", size, max_width)
    # repair the separator before the cutoff clause: it reads " · 截止", not "、截止"
    lines = [ln.replace(f"、截止 {as_of}", f" · 截止 {as_of}") for ln in lines]
    lines.append(DISCLAIMER)
    return lines


def _footer(c: Canvas, t: CardTokens, *, as_of: str, source_ids: list[str],
            muted: str | None = None, rule: str | None = None) -> None:
    size = 24
    fill = muted or t.muted
    lines = _footer_lines(source_ids, as_of, size=size, max_width=t.content_width)
    base_y = CARD_H - 96
    top = base_y - (len(lines) - 1) * 34 - 44
    c.line(t.content_left, top, t.content_left + t.content_width, top,
           rule or t.light, width=2, dash="6 10")
    for i, line in enumerate(lines):
        c.text(t.content_left, base_y - (len(lines) - 1 - i) * 34, line,
               fill=fill, size=size, font=t.font_body)


def _header(c: Canvas, t: CardTokens, *, card_no: int, kicker: str, ticker: str) -> None:
    c.text(t.content_left, 88, f"{card_no:02d}/07", fill=t.primary, size=30,
           font=t.font_heading, weight="bold")
    c.text(t.content_left + t.content_width, 88, ticker, fill=t.muted, size=28,
           font=t.font_body, anchor="end")
    c.text(t.content_left, 148, kicker, fill=t.mid, size=26, font=t.font_body,
           letter_spacing=4)


def _hook(c: Canvas, t: CardTokens, hook: str, *, y: float, size: int = 62) -> float:
    lines = wrap_cjk(hook, max_chars=11, max_lines=3)
    for i, line in enumerate(lines):
        c.text(t.content_left, y + i * (size + 18), line, fill=t.dark, size=size,
               font=t.font_heading, weight="bold")
    end = y + len(lines) * (size + 18)
    g.accent_rule(c, t, x=t.content_left, y=end + 6)
    return end + 48


def _body(c: Canvas, t: CardTokens, body: str, *, y: float, max_lines: int = 4) -> float:
    lines = wrap_cjk(body, max_chars=20, max_lines=max_lines)
    for i, line in enumerate(lines):
        c.text(t.content_left, y + i * 46, line, fill=t.body_text, size=30, font=t.font_body)
    return y + len(lines) * 46


def _chip(c: Canvas, t: CardTokens, text: str, *, x: float, y: float,
          fill: str, colour: str) -> float:
    w = 40 + len(text) * 28
    c.rect(x, y, w, 56, fill, radius=28)
    c.text(x + w / 2, y + 38, text, fill=colour, size=27, font=t.font_body, anchor="middle")
    return x + w + 16


# --------------------------------------------------------------------------- layouts

def _draw_numbers_row(c: Canvas, t: CardTokens, nums: list[dict], *, y: float) -> float:
    """Up to three resolved figures as stat tiles; the middle one is emphasised."""
    if not nums:
        return y
    shown = nums[:3]
    gap = 24
    w = (t.content_width - gap * (len(shown) - 1)) / len(shown)
    h = 260
    for i, n in enumerate(shown):
        x = t.content_left + i * (w + gap)
        emph = len(shown) == 3 and i == 1
        g.stat_tile(c, t, x=x, y=y, w=w, h=h, emphasis=emph)
        colour = t.sign_colour(n["raw"]) if n["signed"] else t.dark
        size = 66 if len(n["text"]) <= 8 else 48
        c.text(x + w / 2, y + 150, n["text"], fill=colour, size=size,
               font=t.font_heading, weight="bold", anchor="middle")
        label = wrap_cjk(n["label"] or n["metric_id"], max_chars=10, max_lines=1)[0]
        c.text(x + w / 2, y + 210, label, fill=t.muted, size=26,
               font=t.font_body, anchor="middle")
    return y + h + 40


def _render_card(card: dict, t: CardTokens, *, ticker: str, as_of: str,
                 metrics: dict) -> str:
    c = Canvas(t.background)
    role = card["role"]
    nums = resolve_numbers(card, metrics)

    if role == "cover":
        c.rect(0, 0, CARD_W, CARD_H, t.dark)
        g.brand_field(c, t, y=CARD_H * 0.34, h=CARD_H * 0.42)
        c.text(t.content_left, 148, "JACARANDA RESEARCH", fill=t.light, size=26,
               font=t.font_body, letter_spacing=6)
        lines = wrap_cjk(card["hook"], max_chars=9, max_lines=3)
        for i, line in enumerate(lines):
            c.text(t.content_left, 460 + i * 108, line, fill=t.inverse, size=84,
                   font=t.font_heading, weight="bold")
        g.accent_rule(c, t, x=t.content_left, y=460 + len(lines) * 108 + 12, w=132)
        by = 460 + len(lines) * 108 + 96
        for i, line in enumerate(wrap_cjk(card["body"], max_chars=20, max_lines=3)):
            c.text(t.content_left, by + i * 48, line, fill=t.light, size=31, font=t.font_body)
        if nums:
            n = nums[0]
            c.text(t.content_left, CARD_H - 470, n["text"],
                   fill=t.inverse, size=132, font=t.font_heading, weight="bold")
            c.text(t.content_left, CARD_H - 410, n["label"] or n["metric_id"],
                   fill=t.light, size=28, font=t.font_body)
        c.text(t.content_left, CARD_H - 300, ticker, fill=t.inverse, size=40,
               font=t.font_heading, weight="bold")
        _footer(c, t, as_of=as_of, source_ids=card["source_ids"], muted=t.light, rule=t.mid)
        return c.to_svg()

    _header(c, t, card_no=card["card_no"], kicker=ROLE_KICKER[role], ticker=ticker)
    y = _hook(c, t, card["hook"], y=280)

    if role in ("full_year", "profit_quality"):
        y = _draw_numbers_row(c, t, nums, y=y)
        if role == "profit_quality" and nums:
            _chip(c, t, "计算值", x=t.content_left, y=y, fill=t.primary, colour=t.inverse)
            y += 76
    elif nums:
        # any other role that declares figures shows them as bound KPI tiles
        y = _draw_numbers_row(c, t, nums, y=y)
    else:
        # decorative brand band only — no data-like marks (see graphics.motif_band)
        g.motif_band(c, t, x=t.content_left, y=y, w=t.content_width, h=280,
                     variant=card["card_no"])
        y += 320

    y = _body(c, t, card["body"], y=y + 16)

    chip_x = t.content_left
    if card.get("claim_type"):
        chip_x = _chip(c, t, CLAIM_CHIP[card["claim_type"]], x=chip_x, y=y + 40,
                       fill=t.primary, colour=t.inverse)
    if card.get("audit_note"):
        _chip(c, t, card["audit_note"], x=chip_x, y=y + 40, fill=t.tint, colour=t.dark)
        y += 76
    if card.get("caveat"):
        cy = y + (128 if card.get("claim_type") else 60)
        c.rect(t.content_left, cy, t.content_width, 116, t.tint, radius=20)
        for i, line in enumerate(wrap_cjk(card["caveat"], max_chars=22, max_lines=2)):
            c.text(t.content_left + 32, cy + 50 + i * 40, line, fill=t.dark, size=28,
                   font=t.font_body)

    _footer(c, t, as_of=as_of, source_ids=card["source_ids"])
    return c.to_svg()


# --------------------------------------------------------------------------- entry points

def qa_report(svg: str, card: dict) -> list[dict]:
    """Geometry and typography QA on a rendered card.

    Mirrors the PPTX renderer's qa_check: catches text escaping the canvas, orphaned CJK
    punctuation at a line start, missing source/disclaimer chrome and unresolved placeholders.
    """
    import re

    issues: list[dict] = []

    def add(code: str, detail: str) -> None:
        issues.append({"card_no": card["card_no"], "role": card["role"],
                       "code": code, "detail": detail})

    for m in re.finditer(r'<(rect|circle|text)\b([^>]*)>', svg):
        a = dict(re.findall(r'([\w:-]+)="([^"]*)"', m.group(2)))
        if m.group(1) == "text":
            x, y = float(a.get("x", 0)), float(a.get("y", 0))
            if not (0 <= x <= CARD_W and 0 <= y <= CARD_H):
                add("out_of_bounds", f"text anchored at ({x:.0f},{y:.0f})")
        elif m.group(1) == "rect":
            x, y = float(a.get("x", 0)), float(a.get("y", 0))
            w, h = float(a.get("width", 0)), float(a.get("height", 0))
            if x < -1 or y < -1 or x + w > CARD_W + 1 or y + h > CARD_H + 1:
                add("out_of_bounds", f"rect {x:.0f},{y:.0f} {w:.0f}x{h:.0f}")

    texts = re.findall(r'<text[^>]*>([^<]*)</text>', svg)
    for t in texts:
        if t[:1] in NO_LINE_START:
            add("orphan_punctuation", f"line starts with {t[:1]!r}: {t[:16]!r}")
        if any(tok in t for tok in ("{{", "TODO", "PLACEHOLDER", "lorem")):
            add("placeholder", t[:40])
    joined = "".join(texts)
    if DISCLAIMER not in joined:
        add("missing_disclaimer", "card carries no disclaimer line")
    if "数据来源" not in joined:
        add("missing_source_line", "card carries no source line")
    return issues


def render_series(series: dict, package: dict, out_dir: Path, *,
                  require_status: frozenset[str] | None = RENDERABLE_STATUS) -> dict:
    """Render all seven cards to SVG and return a manifest with per-card sha256.

    The series is validated against its package first (schema + semantic + lifecycle) and the
    render is refused if anything fails — a fabricated figure, dangling id, wrong role order or a
    non-renderable package status never reaches pixels.
    """
    problems = validate_series(series, package, require_status=require_status)
    if problems:
        raise CardRenderError(
            "series failed validation (rendered nothing): " + "; ".join(problems[:8]))

    cards = series["cards"]
    t = load_tokens()
    metrics = {m["metric_id"]: m for m in package["metrics"]}
    ticker = package["company"]["ticker"]
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    qa_issues: list[dict] = []
    for card in cards:
        svg = _render_card(card, t, ticker=ticker, as_of=series["as_of_date"], metrics=metrics)
        qa_issues.extend(qa_report(svg, card))
        name = f"card-{card['card_no']:02d}-{card['role'].replace('_', '-')}.svg"
        path = out_dir / name
        path.write_text(svg, encoding="utf-8")
        entries.append({
            "card_no": card["card_no"],
            "role": card["role"],
            "file": name,
            "width": CARD_W,
            "height": CARD_H,
            "sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
        })

    if qa_issues:
        raise CardRenderError(
            "card QA failed (rendered no series): "
            + "; ".join(f"card {i['card_no']} {i['code']}: {i['detail']}" for i in qa_issues[:6]))

    manifest = {
        "series_id": series["series_id"],
        "package_id": series["package_id"],
        "locale": series["locale"],
        "as_of_date": series["as_of_date"],
        "style_version": series["style_version"],
        "card_count": len(entries),
        "canvas": {"width": CARD_W, "height": CARD_H, "aspect": "9:16"},
        "cards": entries,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


# Only these SVG->PNG backends may be invoked; each has a known, fixed argv below.
ALLOWED_RASTERISERS = ("resvg", "rsvg-convert", "cairosvg", "inkscape")


def find_rasteriser() -> str | None:
    """Locate an optional SVG->PNG backend from a fixed whitelist. Absent is fine.

    An operator may point ``JACARANDA_SVG_RASTERISER`` at a specific install, but only if its
    basename is one of the whitelisted tools — an arbitrary executable is never run.
    """
    override = os.environ.get("JACARANDA_SVG_RASTERISER")
    if override:
        if Path(override).name not in ALLOWED_RASTERISERS:
            return None
        if Path(override).is_file():
            return override
        return shutil.which(override)
    for candidate in ALLOWED_RASTERISERS:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def rasterise(svg_path: Path, png_path: Path) -> bool:
    """Best-effort 1080x1920 PNG. Returns False when no backend is installed.

    PNG output depends on locally installed CJK fonts, so it is a delivery convenience, never
    the determinism baseline — the manifest hashes the SVG.
    """
    tool = find_rasteriser()
    if not tool:
        return False
    name = Path(tool).name
    if name == "rsvg-convert":
        cmd = [tool, "-w", str(CARD_W), "-h", str(CARD_H), "-o", str(png_path), str(svg_path)]
    elif name == "resvg":
        cmd = [tool, "--width", str(CARD_W), "--height", str(CARD_H), str(svg_path), str(png_path)]
    elif name == "cairosvg":
        cmd = [tool, str(svg_path), "-o", str(png_path), "-W", str(CARD_W), "-H", str(CARD_H)]
    else:  # inkscape
        cmd = [tool, str(svg_path), "--export-type=png", f"--export-filename={png_path}",
               f"--export-width={CARD_W}", f"--export-height={CARD_H}"]
    try:
        # cmd is a fixed argv (no shell) built from a whitelisted tool name and integer sizes.
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)  # noqa: S603
    except (subprocess.SubprocessError, OSError):
        return False
    return png_path.exists()
