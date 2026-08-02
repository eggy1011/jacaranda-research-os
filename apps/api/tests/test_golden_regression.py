from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from jacaranda_api.pipeline.orchestrator import run_pipeline

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = Path(__file__).parent / "golden" / "mock-e2e.sha256.json"


def test_mock_pipeline_outputs_match_golden_digests(tmp_path: Path) -> None:
    """The closest a solo project gets to a second reviewer: the mock run is
    fully deterministic, so any unintended change to stage logic, schemas,
    fixtures or assembly shows up as a digest diff here."""
    artifacts = run_pipeline(ROOT, tmp_path / "run")
    expected = cast(
        dict[str, str],
        {
            key: value
            for key, value in json.loads(GOLDEN.read_text(encoding="utf-8")).items()
            if not key.startswith("_")
        },
    )
    assert artifacts.zh_package and artifacts.social_card_series and artifacts.card_manifest, (
        "verified mock run must produce the S8 social-card artifacts"
    )
    actual = {
        "research-package.json": _digest(artifacts.research_package),
        "slide-deck.zh-CN.json": _digest(artifacts.deck_json["zh-CN"]),
        "slide-deck.en-AU.json": _digest(artifacts.deck_json["en-AU"]),
        # S8 cards: the manifest hashes every card SVG, so this digest covers render determinism
        "research-package.zh.json": _digest(artifacts.zh_package),
        "social-card-series.json": _digest(artifacts.social_card_series),
        "cards/manifest.json": _digest(artifacts.card_manifest),
    }
    assert actual == expected, (
        "mock pipeline output changed; if intentional, update "
        "tests/golden/mock-e2e.sha256.json in the same PR"
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
