#!/usr/bin/env python3
"""Unit tests for the PR #25 review fixes (plain asserts, offline, fictional data only).

Run: python3 packages/presentation/tests/run_tests.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

PRES = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRES))
sys.path.insert(0, str(PRES / "tools"))

from template.deck import (  # noqa: E402
    TemplateRenderError,
    UnsupportedEditionError,
    build_deck,
)

FIX = PRES / "fixtures"
PKG = json.loads((FIX / "mock-package.json").read_text(encoding="utf-8"))
BASE = json.loads((FIX / "deck-sample.zh-CN.json").read_text(encoding="utf-8"))
TMP = Path(tempfile.mkdtemp(prefix="jacaranda-tests-"))

passed = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    global passed
    assert condition, f"{name}: {detail}"
    passed += 1
    print("PASS", name)


def deep(obj):
    return json.loads(json.dumps(obj, ensure_ascii=False))


# ---- Fix 1: overflow report carries block id + action + reason -------------

def test_overflow_report_contract() -> None:
    deck = deep(BASE)
    thesis = deep(deck["slides"][1])          # L03 kpi_cards + bullets
    table = deep(deck["slides"][7]["blocks"][0])   # big financial table (priority 1)
    bullets = deep(deck["slides"][1]["blocks"][1])  # bullets block
    # Overstuff one slide far beyond the content area to trigger the policy.
    table["priority"] = 1
    filler1 = deep(bullets); filler1["priority"] = 5
    filler2 = deep(bullets); filler2["priority"] = 7
    thesis["blocks"] = [thesis["blocks"][0], bullets, table, deep(table), filler1, filler2]
    deck["slides"] = [deck["slides"][0], thesis] + deck["slides"][2:]
    report = build_deck(deck, PKG, TMP / "overflow-case.pptx")
    issues = [i for i in report["issues"] if i["code"] == "block_overflow"]
    ok("overflow: report fails", report["status"] == "fail")
    ok("overflow: block_overflow events present", len(issues) >= 2, str(len(issues)))
    for issue in issues:
        for key in ("slide_no", "block", "action_taken", "reason", "priority",
                    "retryable", "layout", "code"):
            ok(f"overflow: field {key}", key in issue, json.dumps(issue))
        break  # field check on the first entry is representative
    actions = {i["action_taken"] for i in issues}
    ok("overflow: low-priority blocks dropped", "dropped_block" in actions, str(actions))
    ok("overflow: priority-1 failure action reported",
       any(i["action_taken"] in ("failed", "rendered_with_overflow") and i["priority"] == 1
           for i in issues),
       str(issues))
    ok("overflow: block ids traceable",
       all(i["block"].startswith("blocks[") for i in issues), str(actions))
    ok("overflow: retry/drop consumable",
       all(isinstance(i["retryable"], bool) and i["reason"] for i in issues))


# ---- Fix 2: cover_meta located by block type -------------------------------

def test_cover_meta_lookup() -> None:
    deck = deep(BASE)
    cover = deck["slides"][0]
    meta_block = deep(cover["blocks"][0])
    note = {"block_type": "text_panel", "priority": 9,
            "text_panel": {"text": "封面附注（虚构）", "refs": [{"claim_id": "CLM-004"}],
                           "style": "note"}}
    # cover_meta NOT first: must still render
    cover["blocks"] = [note, meta_block]
    report = build_deck(deck, PKG, TMP / "cover-reordered.pptx")
    ok("cover: renders with cover_meta not first", report["slide_count"] == len(deck["slides"]))

    missing = deep(BASE)
    missing["slides"][0]["blocks"] = [note]
    try:
        build_deck(missing, PKG, TMP / "cover-missing.pptx")
        ok("cover: missing cover_meta raises", False)
    except TemplateRenderError as e:
        ok("cover: missing cover_meta raises", e.code == "cover_meta_missing", e.code)

    dup = deep(BASE)
    dup["slides"][0]["blocks"] = [meta_block, deep(meta_block)]
    try:
        build_deck(dup, PKG, TMP / "cover-dup.pptx")
        ok("cover: duplicate cover_meta raises", False)
    except TemplateRenderError as e:
        ok("cover: duplicate cover_meta raises", e.code == "cover_meta_duplicate", e.code)


# ---- Fix 3: bilingual-summary fails fast -----------------------------------

def test_bilingual_summary_rejected() -> None:
    deck = deep(BASE)
    deck["edition"] = "bilingual-summary"
    try:
        build_deck(deck, PKG, TMP / "summary.pptx")
        ok("edition: bilingual-summary rejected", False)
    except UnsupportedEditionError as e:
        ok("edition: bilingual-summary rejected", e.code == "unsupported_edition", e.code)
        ok("edition: error names the edition", "bilingual-summary" in str(e))
    ok("edition: no file produced", not (TMP / "summary.pptx").exists())


# ---- Fix 4: LibreOffice discovery chain ------------------------------------

def test_soffice_discovery() -> None:
    import build_and_qa as bq

    fake = TMP / "fake-soffice"
    fake.write_text("#!/bin/sh\n")
    old_env = os.environ.get("SOFFICE_PATH")
    old_path = os.environ["PATH"]
    try:
        os.environ["SOFFICE_PATH"] = str(fake)
        ok("soffice: env var wins", bq.find_soffice() == str(fake))
        os.environ["SOFFICE_PATH"] = str(TMP / "does-not-exist")
        os.environ["PATH"] = str(TMP)  # empty of libreoffice/soffice
        result = bq.find_soffice()
        ok("soffice: invalid env falls through, never FileNotFoundError",
           result is None or result == bq.MACOS_SOFFICE, str(result))
        # PATH resolution beats the macOS fallback
        exe = TMP / "soffice"
        exe.write_text("#!/bin/sh\n")
        exe.chmod(0o755)
        del os.environ["SOFFICE_PATH"]
        ok("soffice: PATH lookup used", bq.find_soffice() == str(exe))
    finally:
        os.environ["PATH"] = old_path
        if old_env is None:
            os.environ.pop("SOFFICE_PATH", None)
        else:
            os.environ["SOFFICE_PATH"] = old_env


def main() -> int:
    test_overflow_report_contract()
    test_cover_meta_lookup()
    test_bilingual_summary_rejected()
    test_soffice_discovery()
    print(f"\nALL {passed} assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
