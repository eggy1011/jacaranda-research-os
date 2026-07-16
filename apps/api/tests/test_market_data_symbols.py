from __future__ import annotations

import pytest

from jacaranda_api.market_data.errors import SymbolNormalizationError
from jacaranda_api.market_data.models import Exchange, Market
from jacaranda_api.market_data.symbols import normalize_symbol


@pytest.mark.parametrize(
    ("raw", "canonical", "provider_symbol", "market", "exchange"),
    [
        ("600519.SS", "600519.SS", "600519", Market.CN_A, Exchange.SSE),
        ("600519.sh", "600519.SS", "600519", Market.CN_A, Exchange.SSE),
        ("000001.SZ", "000001.SZ", "000001", Market.CN_A, Exchange.SZSE),
        (" aapl ", "AAPL", "AAPL", Market.US, None),
        ("BRK.B", "BRK.B", "BRK.B", Market.US, None),
    ],
)
def test_symbol_normalization(
    raw: str,
    canonical: str,
    provider_symbol: str,
    market: Market,
    exchange: Exchange | None,
) -> None:
    symbol = normalize_symbol(raw)

    assert symbol.original == raw
    assert symbol.canonical == canonical
    assert symbol.provider_symbol == provider_symbol
    assert symbol.market is market
    assert symbol.exchange is exchange


@pytest.mark.parametrize("raw", ["", "600519", "600519.BJ", "AAPL$", "12345678901"])
def test_invalid_symbols_fail_explicitly(raw: str) -> None:
    with pytest.raises(SymbolNormalizationError) as caught:
        normalize_symbol(raw)

    assert caught.value.retryable is False
    assert caught.value.as_dict()["code"] == "invalid_symbol"
