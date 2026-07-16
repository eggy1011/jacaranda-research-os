from __future__ import annotations

from dataclasses import dataclass

import pytest

from jacaranda_api.market_data.contracts import MarketDataResult
from jacaranda_api.market_data.errors import ProviderRoutingError
from jacaranda_api.market_data.models import (
    Market,
    MarketDataCapability,
    ProviderName,
    ProviderRequest,
)
from jacaranda_api.market_data.registry import MarketDataRouter, ProviderRegistry
from jacaranda_api.market_data.source_registry import SourceRegistry


@dataclass
class StubProvider:
    name: ProviderName
    markets: frozenset[Market]
    capabilities: frozenset[MarketDataCapability]
    last_request: ProviderRequest | None = None

    async def fetch(self, request: ProviderRequest, sources: SourceRegistry) -> MarketDataResult:
        self.last_request = request
        return MarketDataResult(
            provider=self.name,
            symbol=request.symbol,
            capability=request.capability,
            metrics=(),
            missing=(),
            source_registry=sources,
        )


def providers() -> tuple[StubProvider, StubProvider, StubProvider]:
    akshare = StubProvider(
        ProviderName.AKSHARE,
        frozenset({Market.CN_A}),
        frozenset({MarketDataCapability.QUOTE}),
    )
    fmp = StubProvider(
        ProviderName.FMP,
        frozenset({Market.US}),
        frozenset({MarketDataCapability.QUOTE}),
    )
    finnhub = StubProvider(
        ProviderName.FINNHUB,
        frozenset({Market.US}),
        frozenset({MarketDataCapability.QUOTE}),
    )
    return akshare, fmp, finnhub


@pytest.mark.anyio
async def test_router_is_deterministic_and_supports_explicit_provider() -> None:
    akshare, fmp, finnhub = providers()
    registry = (
        ProviderRegistry()
        .register(finnhub, priority=20)
        .register(akshare, priority=10)
        .register(fmp, priority=10)
    )
    router = MarketDataRouter(registry)

    default = await router.fetch(
        "AAPL", MarketDataCapability.QUOTE, SourceRegistry(), metric_id_start=7
    )
    preferred = await router.fetch(
        "AAPL",
        MarketDataCapability.QUOTE,
        SourceRegistry(),
        preferred_provider=ProviderName.FINNHUB,
    )
    cn = await router.fetch("600519.SS", MarketDataCapability.QUOTE, SourceRegistry())

    assert default.provider is ProviderName.FMP
    assert fmp.last_request is not None and fmp.last_request.metric_id_start == 7
    assert preferred.provider is ProviderName.FINNHUB
    assert cn.provider is ProviderName.AKSHARE


def test_registry_rejects_duplicates_and_missing_routes() -> None:
    _akshare, fmp, _finnhub = providers()
    registry = ProviderRegistry().register(fmp)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(fmp)

    from jacaranda_api.market_data.models import ProviderRequest
    from jacaranda_api.market_data.symbols import normalize_symbol

    request = ProviderRequest(
        symbol=normalize_symbol("AAPL"), capability=MarketDataCapability.FINANCIALS
    )
    with pytest.raises(ProviderRoutingError):
        registry.select(request)
    quote_request = request.model_copy(update={"capability": MarketDataCapability.QUOTE})
    with pytest.raises(ProviderRoutingError, match="preferred provider"):
        registry.select(quote_request, ProviderName.FINNHUB)
