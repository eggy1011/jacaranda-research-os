from __future__ import annotations

import argparse
from pathlib import Path

from jacaranda_api.e2e.orchestrator import run_pipeline


def repository_root() -> Path:
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
