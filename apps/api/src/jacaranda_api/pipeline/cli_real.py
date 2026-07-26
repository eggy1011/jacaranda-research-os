from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx

from jacaranda_api.config import get_settings
from jacaranda_api.llm.catalog import PromptCatalog
from jacaranda_api.llm.contracts import LLMProvider
from jacaranda_api.llm.factory import build_llm_provider
from jacaranda_api.llm.http_client import HttpxOpenRouterHTTPClient
from jacaranda_api.market_data.adapters.akshare import AkshareClient
from jacaranda_api.pipeline.cli import repository_root
from jacaranda_api.pipeline.real_orchestrator import RealResearchOrchestrator


def _default_wiring(root: Path) -> tuple[LLMProvider, AkshareClient]:
    from jacaranda_api.market_data.clients.akshare_live import AkshareLiveClient

    settings = get_settings()
    http_client = HttpxOpenRouterHTTPClient(
        httpx.AsyncClient(timeout=httpx.Timeout(180.0)),
        base_url=settings.openrouter_base_url,
    )
    llm = build_llm_provider(settings, PromptCatalog(root), http_client)
    return llm, AkshareLiveClient()


def main(
    argv: Sequence[str] | None = None,
    *,
    wiring: Callable[[Path], tuple[LLMProvider, AkshareClient]] = _default_wiring,
) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the real S1-S7 research pipeline for an A-share company. "
            "Produces a draft research package plus bilingual PPTX; every stage "
            "is checkpointed so --resume continues an interrupted run."
        )
    )
    parser.add_argument("--symbol", required=True, help="A-share code, e.g. 600519 or 000001.SZ")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse completed stage checkpoints in the output directory",
    )
    args = parser.parse_args(argv)

    root = repository_root()
    llm, akshare_client = wiring(root)
    orchestrator = RealResearchOrchestrator(root, llm=llm, akshare_client=akshare_client)
    artifacts = asyncio.run(
        orchestrator.run(args.symbol, args.output_dir, resume=args.resume)
    )
    print(artifacts.manifest)
    print(artifacts.research_package)
    for edition, path in artifacts.pptx.items():
        print(f"{edition}: {path}")


if __name__ == "__main__":
    main()
