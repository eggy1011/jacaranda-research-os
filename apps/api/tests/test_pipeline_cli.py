from __future__ import annotations

from pathlib import Path

import pytest

from jacaranda_api.pipeline.cli import repository_root

ROOT = Path(__file__).resolve().parents[3]


def test_repository_root_walks_up_without_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Development form: no override, discover the root by walking up the source tree."""
    monkeypatch.delenv("REPOSITORY_ROOT", raising=False)
    assert repository_root() == ROOT


def test_repository_root_uses_valid_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Installed form: an override pointing at a tree with PROJECT_BRIEF.md wins."""
    (tmp_path / "PROJECT_BRIEF.md").write_text("# stub brief\n", encoding="utf-8")
    monkeypatch.setenv("REPOSITORY_ROOT", str(tmp_path))
    assert repository_root() == tmp_path


def test_repository_root_rejects_override_without_brief(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A misconfigured override is a loud error, not a silent fall back to the search."""
    monkeypatch.setenv("REPOSITORY_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError, match="PROJECT_BRIEF"):
        repository_root()
