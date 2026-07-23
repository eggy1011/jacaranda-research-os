from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from jacaranda_api.e2e.models import PresentationResult
from jacaranda_api.e2e.validation import load_json, validate_package


class PresentationFailure(RuntimeError):
    pass


class TemplatePresentationProvider:
    """Thin adapter over the Claude-owned, read-only editable-PPTX renderer."""

    def __init__(self, repository_root: Path) -> None:
        self._root = repository_root.resolve()

    def render(
        self,
        deck: dict[str, Any],
        package: dict[str, Any],
        output_path: Path,
    ) -> PresentationResult:
        validate_package(self._root, package)
        schema = load_json(self._root / "packages/research-schema/slide-deck.schema.json")
        Draft202012Validator(schema).validate(deck)
        if deck["package_id"] != package["package_id"] or deck["edition"] not in {
            "zh-CN",
            "en-AU",
        }:
            raise PresentationFailure("deck identity is not renderable for this verified package")
        package_root = self._root / "packages/presentation"
        path_text = str(package_root)
        inserted = path_text not in sys.path
        if inserted:
            sys.path.insert(0, path_text)
        try:
            module = importlib.import_module("template.deck")
            report = module.build_deck(deck, package, output_path)
        finally:
            if inserted:
                sys.path.remove(path_text)
        if report.get("status") != "pass" or report.get("issues"):
            raise PresentationFailure(f"presentation QA failed for {deck['edition']}")
        return PresentationResult(
            edition=deck["edition"],
            pptx_path=output_path,
            overflow_report=dict(report),
        )
