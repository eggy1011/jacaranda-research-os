#!/usr/bin/env python3
"""Offline tests for the 9:16 knowledge-card renderer (plain asserts, fictional data only).

Run standalone:  python3 packages/presentation/cards/tests/run_tests.py
Also invoked by packages/presentation/tests/run_tests.py so CI exercises it.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path

PRES = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PRES.parent))  # so `presentation.cards` imports

from presentation.cards import (  # noqa: E402
    CARD_H,
    CARD_W,
    format_number,
    render_series,
)
from presentation.cards.render import (  # noqa: E402
    CardRenderError,
    find_rasteriser,
    qa_report,
    rasterise,
    resolve_numbers,
)
from presentation.cards.svg import NO_LINE_START, wrap_cjk  # noqa: E402
from presentation.cards.tokens import ROLE_ORDER  # noqa: E402
from presentation.cards.validate import validate_series  # noqa: E402

SCHEMA_EX = PRES.parent / "research-schema" / "examples"
SERIES = json.loads((SCHEMA_EX / "example-social-card-series.zh-CN.json").read_text("utf-8"))
# The series is compiled from the Chinese-monolingual package and cites it directly (ids match);
# no in-memory alignment is needed.
PKG = json.loads((SCHEMA_EX / "example-research-package.zh.json").read_text("utf-8"))

passed = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    global passed
    assert condition, f"{name}: {detail}"
    passed += 1
    print("PASS", name)


def _render(dir_name: str) -> dict:
    out = Path(tempfile.mkdtemp(prefix=f"jac-cards-{dir_name}-"))
    return render_series(SERIES, PKG, out), out


# ---- structure ------------------------------------------------------------

def test_seven_fixed_cards() -> None:
    m, out = _render("struct")
    ok("card: seven cards rendered", m["card_count"] == 7, str(m["card_count"]))
    ok("card: fixed role order", [c["role"] for c in m["cards"]] == ROLE_ORDER)
    ok("card: canvas is 9:16 1080x1920",
       m["canvas"] == {"width": 1080, "height": 1920, "aspect": "9:16"})
    for e in m["cards"]:
        svg = (out / e["file"]).read_text("utf-8")
        ok(f"card {e['card_no']}: svg dimensions",
           f'width="{CARD_W}"' in svg and f'height="{CARD_H}"' in svg)


# ---- determinism ----------------------------------------------------------

def test_deterministic() -> None:
    (m1, d1), (m2, d2) = _render("det-a"), _render("det-b")
    ok("card: manifest hashes identical across runs",
       [c["sha256"] for c in m1["cards"]] == [c["sha256"] for c in m2["cards"]])
    for a, b in zip(m1["cards"], m2["cards"], strict=True):
        ok(f"card {a['card_no']}: svg bytes identical",
           (d1 / a["file"]).read_bytes() == (d2 / b["file"]).read_bytes())


# ---- number binding -------------------------------------------------------

def test_number_binding() -> None:
    ok("format: yi transform", format_number(4_520_000_000, "yi", 1) == "45.2亿")
    ok("format: percent transform", format_number(20.2, "percent", 1) == "20.2%")
    ok("format: yi two decimals", format_number(512_000_000, "yi", 2) == "5.12亿")
    ok("format: raw thousands separator", format_number(1361.76, "raw", 2) == "1,361.76")

    metrics = {mm["metric_id"]: mm for mm in PKG["metrics"]}
    full_year = next(c for c in SERIES["cards"] if c["role"] == "full_year")
    nums = resolve_numbers(full_year, metrics)
    texts = {n["text"] for n in nums}
    ok("card: full_year resolves declared numbers",
       {"45.2亿", "5.12亿", "20.2%"} <= texts, str(texts))

    m, out = _render("nums")
    svg2 = (out / "card-02-full-year.svg").read_text("utf-8")
    ok("card: resolved number appears in svg", "45.2亿" in svg2 and "20.2%" in svg2)

    bad = {"card_no": 1, "role": "cover", "hook": "x", "body": "y", "source_ids": ["SRC-001"],
           "status": "preview_ready", "inline_numbers": [{"metric_id": "MET-404",
                                                          "display_transform": "raw"}]}
    try:
        resolve_numbers(bad, metrics)
        ok("card: unknown metric rejected", False, "no error raised")
    except CardRenderError:
        ok("card: unknown metric rejected", True)


# ---- typography / QA ------------------------------------------------------

def test_kinsoku_wrapping() -> None:
    lines = wrap_cjk("全年营收 45.2 亿、净利 5.12 亿", max_chars=8, max_lines=3)
    ok("wrap: no line starts with closing punctuation",
       all(line[:1] not in NO_LINE_START for line in lines), str(lines))
    filled = wrap_cjk("字" * 50, max_chars=8, max_lines=3)
    ok("wrap: respects max_lines", len(filled) == 3)
    ok("wrap: truncates with ellipsis", filled[-1].endswith("…"))


def test_qa_gate() -> None:
    _, out = _render("qa")  # a clean render must produce no QA issues (else render_series raises)
    ok("qa: clean series renders without raising", (out / "manifest.json").exists())

    good_svg = (out / "card-07-counter-conclusion.svg").read_text("utf-8")
    ok("qa: closing card has stacked source union",
       "SRC-001" in good_svg and "SRC-004" in good_svg and "不构成投资建议" in good_svg)

    card = SERIES["cards"][0]
    missing_footer = '<svg width="1080" height="1920"><text x="10" y="10">仅供学习研究</text></svg>'
    issues = qa_report(missing_footer, card)
    ok("qa: flags missing source line", any(i["code"] == "missing_source_line" for i in issues))
    oob = '<svg><text x="20" y="9000">数据来源 仅供学习研究，不构成投资建议</text></svg>'
    ok("qa: flags out-of-bounds text",
       any(i["code"] == "out_of_bounds" for i in qa_report(oob, card)))
    orphan = ('<svg><text x="20" y="20">，orphan</text>'
              '<text x="20" y="40">数据来源 不构成投资建议</text></svg>')
    ok("qa: flags orphaned line-start punctuation",
       any(i["code"] == "orphan_punctuation" for i in qa_report(orphan, card)))


# ---- rasteriser -----------------------------------------------------------

def test_raster_optional() -> None:
    if find_rasteriser() is None:
        _, out = _render("raster")
        got = rasterise(out / "card-01-cover.svg", out / "card-01-cover.png")
        ok("raster: absent backend degrades gracefully", got is False)
    else:
        ok("raster: backend present (skipped negative check)", True)


def _mutate(fn):
    s = copy.deepcopy(SERIES)
    p = copy.deepcopy(PKG)
    fn(s, p)
    return validate_series(s, p)


def test_runtime_validation() -> None:
    ok("validate: clean series passes", validate_series(SERIES, PKG) == [])

    cases = {
        "fabricated number": lambda s, p: s["cards"][1].update(body="全年营收 999 亿元。"),
        "sign flip": lambda s, p: s["cards"][1].update(body="营收同比 -20.2%。"),
        "unit swap": lambda s, p: s["cards"][4].update(hook="增速 20.2 倍是算出来的"),
        "undated latest_disclosure": lambda s, p: s["cards"][5].update(
            hook="回顾一下", body="经营稳健。"),
        "stale latest_disclosure period": lambda s, p: s["cards"][5].update(
            hook="最新披露 2024Q1", body="平稳。", audit_note="未审计"),
        "text decimals mismatch": lambda s, p: s["cards"][4].update(hook="增速 20.20% 是算出来的"),
        "closing not counterevidence": lambda s, p: (
            s["cards"][6].update(claim_refs=["CLM-002"], claim_type="fact")),
        "closing missing full sources": lambda s, p: s["cards"][6].update(source_ids=["SRC-001"]),
        "draft package not renderable": lambda s, p: p.update(status="draft"),
        "mock never approved": lambda s, p: p.update(status="approved"),
        "over-long hook truncates": lambda s, p: s["cards"][1].update(hook="字" * 40),
        "dangling metric": lambda s, p: s["cards"][0]["inline_numbers"].append(
            {"metric_id": "MET-404", "display_transform": "raw"}),
        "duplicate source": lambda s, p: s["cards"][0].update(source_ids=["SRC-001", "SRC-001"]),
        "wrong role order": lambda s, p: s["cards"].reverse(),
        # second Codex review: semantic boundaries reachable by real input
        "future latest_disclosure period": lambda s, p: s["cards"][5].update(
            hook="展望 2027Q4", body="新品放量。", audit_note="预告"),
        "amount metric as percent": lambda s, p: s["cards"][1]["inline_numbers"].append(
            {"metric_id": "MET-001", "display_transform": "percent", "decimals": 1}),
        "driver with no refs": lambda s, p: s["cards"][2].update(claim_refs=[], metric_refs=[]),
        "cover with no refs": lambda s, p: s["cards"][0].update(claim_refs=[], metric_refs=[]),
        "package not zh locale": lambda s, p: p.update(locale="en-AU"),
        "series as_of mismatch": lambda s, p: s.update(as_of_date="2025-01-01"),
    }
    for name, fn in cases.items():
        ok(f"validate: rejects {name}", bool(_mutate(fn)))

    # a positive sign on a positive metric is allowed (must not be a false positive)
    ok("validate: '+' on positive value allowed",
       _mutate(lambda s, p: s["cards"][1].update(body="营收同比 +20.2%，稳。")) == [])


def test_render_fail_closed() -> None:
    s = copy.deepcopy(SERIES)
    s["cards"][1]["body"] = "全年营收 999 亿元。"
    try:
        render_series(s, PKG, Path(tempfile.mkdtemp()))
        ok("render: refuses a fabricated series", False, "rendered anyway")
    except CardRenderError:
        ok("render: refuses a fabricated series", True)


def test_rasteriser_whitelist() -> None:
    import os

    from presentation.cards.render import find_rasteriser
    saved = os.environ.get("JACARANDA_SVG_RASTERISER")
    try:
        os.environ["JACARANDA_SVG_RASTERISER"] = "some/path/resvg"  # a path override is rejected
        ok("raster: path override rejected", find_rasteriser() is None)
        os.environ["JACARANDA_SVG_RASTERISER"] = "definitely-not-a-tool"
        ok("raster: non-whitelisted name rejected", find_rasteriser() is None)
    finally:
        if saved is None:
            os.environ.pop("JACARANDA_SVG_RASTERISER", None)
        else:
            os.environ["JACARANDA_SVG_RASTERISER"] = saved


def main() -> int:
    test_seven_fixed_cards()
    test_deterministic()
    test_number_binding()
    test_kinsoku_wrapping()
    test_qa_gate()
    test_raster_optional()
    test_rasteriser_whitelist()
    test_runtime_validation()
    test_render_fail_closed()
    print(f"\nALL {passed} card-renderer assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
