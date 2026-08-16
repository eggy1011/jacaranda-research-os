from __future__ import annotations

import argparse
import os
from pathlib import Path

from jacaranda_api.pipeline.orchestrator import run_pipeline


def repository_root() -> Path:
    """Locate the tree holding PROJECT_BRIEF.md, packages/ and assets/brand.

    In development the source tree is walked upwards from this file. Once the
    package is pip-installed (Docker), the code lives in site-packages while the
    data lives at a copied path with no common ancestor, so an explicit
    REPOSITORY_ROOT override is required. A misconfigured override is a loud
    error, never a silent fall back to the upward search.
    """
    override = os.getenv("REPOSITORY_ROOT")
    if override:
        root = Path(override)
        if (root / "PROJECT_BRIEF.md").is_file():
            return root
        raise RuntimeError(
            f"REPOSITORY_ROOT={override!r} does not contain PROJECT_BRIEF.md"
        )
    for parent in Path(__file__).resolve().parents:
        if (parent / "PROJECT_BRIEF.md").is_file():
            return parent
    raise RuntimeError("repository root not found")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the socket-blocked Issue #26 mock slice")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    artifacts = run_pipeline(repository_root(), args.output_dir)
    print(artifacts.manifest)


if __name__ == "__main__":
    main()
