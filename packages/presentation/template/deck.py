"""Deck assembly: validated slide-deck JSON + research package -> editable PPTX.

Also runs the overflow/geometry QA pass and emits a machine-readable report.
"""

from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu

from .blocks import Resolver
from .layouts import build_slide
from .theme import Theme, load_theme

IN = 914400


def _edition_lang(edition: str) -> str:
    return "zh" if edition.startswith("zh") else "en"


def build_deck(deck_json: dict, package_json: dict, out_path: Path,
               theme: Theme | None = None) -> dict:
    """Build the PPTX and return the machine-readable QA/overflow report."""
    theme = theme or load_theme()
    lang = _edition_lang(deck_json["edition"])
    res = Resolver(package_json)
    prs = Presentation()
    prs.slide_width = theme.page_w
    prs.slide_height = theme.page_h
    for slide_spec in deck_json["slides"]:
        build_slide(prs, theme, res, lang, deck_json, slide_spec)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out_path)
    report = qa_check(out_path, deck_json, theme)
    return report


def qa_check(pptx_path: Path, deck_json: dict, theme: Theme | None = None) -> dict:
    """Geometry + placeholder QA on the produced file (reopened from disk)."""
    theme = theme or load_theme()
    prs = Presentation(str(pptx_path))
    issues: list[dict] = []
    page_w, page_h = prs.slide_width, prs.slide_height

    def walk_shapes(shapes):
        for shape in shapes:
            yield shape
            if shape.shape_type == 6:  # group
                yield from walk_shapes(shape.shapes)

    for idx, slide in enumerate(prs.slides, start=1):
        spec = deck_json["slides"][idx - 1]
        for shape in walk_shapes(slide.shapes):
            left = shape.left if shape.left is not None else 0
            top = shape.top if shape.top is not None else 0
            width = shape.width or 0
            height = shape.height or 0
            if left < 0 or top < 0 or left + width > page_w + Emu(int(0.02 * IN)) \
                    or top + height > page_h + Emu(int(0.02 * IN)):
                issues.append({
                    "code": "shape_out_of_bounds", "slide_no": idx,
                    "layout": spec["layout"], "shape": shape.shape_id,
                    "retryable": False,
                    "detail": f"{shape.shape_type} at ({left/IN:.2f},{top/IN:.2f}) "
                              f"size ({width/IN:.2f}x{height/IN:.2f})in",
                })
            if shape.has_text_frame:
                text = shape.text_frame.text
                # NB: bare "XXX" is not scanned — fictional tickers use it (600XXX)
                for token in ("{{", "}}", "TODO", "PLACEHOLDER", "lorem"):
                    if token in text:
                        issues.append({
                            "code": "unresolved_placeholder", "slide_no": idx,
                            "layout": spec["layout"], "shape": shape.shape_id,
                            "retryable": False, "detail": f"token {token!r}",
                        })
    return {
        "pptx": pptx_path.name,
        "edition": deck_json["edition"],
        "slide_count": len(prs.slides),
        "page_size_in": [round(page_w / IN, 3), round(page_h / IN, 3)],
        "issues": issues,
        "status": "pass" if not issues else "fail",
    }


def build_from_files(deck_path: Path, package_path: Path, out_path: Path) -> dict:
    deck_json = json.loads(deck_path.read_text(encoding="utf-8"))
    package_json = json.loads(package_path.read_text(encoding="utf-8"))
    return build_deck(deck_json, package_json, out_path)
