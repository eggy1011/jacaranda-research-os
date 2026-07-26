from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from jacaranda_api.market_data.adapters.akshare import AkshareClient
from jacaranda_api.pipeline.evidence import build_evidence_pack


def _default_client() -> AkshareClient:
    from jacaranda_api.market_data.clients.akshare_live import AkshareLiveClient

    return AkshareLiveClient()


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: Callable[[], AkshareClient] = _default_client,
) -> None:
    parser = argparse.ArgumentParser(
        description="Build a real A-share evidence pack (identity, quote, financials, sources)"
    )
    parser.add_argument("--symbol", required=True, help="A-share code, e.g. 600519 or 000001.SZ")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    output_dir: Path = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    pack = asyncio.run(build_evidence_pack(args.symbol, client_factory()))
    output_path = output_dir / "evidence.json"
    output_path.write_text(
        json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(output_path)
    print(f"company: {pack['company']['name_zh']} ({pack['symbol']['canonical']})")
    print(f"metrics: {len(pack['metrics'])}  sources: {len(pack['sources'])}")
    for item in pack["missing"]:
        print(f"missing: {item['field']} ({item['reason']})")
    for warning in pack["warnings"]:
        print(f"warning: {warning}")


if __name__ == "__main__":
    main()
