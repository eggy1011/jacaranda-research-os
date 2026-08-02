"""S8 social-card generation: project the verified package to zh, validate, and render.

Cards are only produced from a verified/approved package. The bilingual research package is
projected to a Chinese-monolingual view (the v2 card flow is zh-only), then the model-planned
seven-card series is validated and rendered by the deterministic code renderer in
``packages/presentation/cards`` — the single enforcement point for the no-fabrication invariant.
"""

from __future__ import annotations

import copy
import importlib
import sys
from pathlib import Path
from typing import Any

JsonDict = dict[str, Any]
LOCALE = "zh-CN"


class SocialCardFailure(RuntimeError):
    """Raised when a card series cannot be produced — never rendered partially or silently."""


def project_zh_package(package: JsonDict) -> JsonDict:
    """Collapse the bilingual package to its Chinese-monolingual projection for the card flow.

    Every ``{"zh_CN", "en_AU"}`` localized text becomes its Chinese string; ids, values, periods,
    provenance and status are unchanged, and a ``locale`` discriminator is added.
    """
    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            if set(value) == {"zh_CN", "en_AU"} and isinstance(value.get("zh_CN"), str):
                return value["zh_CN"]
            return {key: walk(item) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        return value

    zh = walk(copy.deepcopy(package))
    zh["locale"] = LOCALE
    return zh


def render_social_cards(
    repository_root: Path, series: JsonDict, package: JsonDict, output_dir: Path
) -> tuple[JsonDict, JsonDict]:
    """Validate the series against the zh package and render it. Returns (manifest, zh_package).

    Raises ``SocialCardFailure`` if the series is not renderable, so an invalid or fabricated plan
    never reaches pixels.
    """
    zh_package = project_zh_package(package)
    package_root = str((repository_root / "packages" / "presentation").resolve())
    inserted = package_root not in sys.path
    if inserted:
        sys.path.insert(0, package_root)
    try:
        validate = importlib.import_module("cards.validate")
        cards = importlib.import_module("cards")
        issues = validate.validate_series(series, zh_package)
        if issues:
            raise SocialCardFailure(
                "social card series failed validation: " + "; ".join(issues[:8])
            )
        try:
            manifest = cards.render_series(series, zh_package, output_dir)
        except cards.CardRenderError as exc:  # QA (geometry/overflow) failure
            raise SocialCardFailure(str(exc)) from exc
    finally:
        if inserted:
            sys.path.remove(package_root)
    return manifest, zh_package
