from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from jacaranda_api.market_data.models import (
    CanonicalMetric,
    Market,
    MarketDataCapability,
    MissingData,
    NormalizedSymbol,
    ProviderName,
    ProviderRequest,
)
from jacaranda_api.market_data.source_registry import SourceRegistry


@dataclass(frozen=True, slots=True)
class MarketDataResult:
    provider: ProviderName
    symbol: NormalizedSymbol
    capability: MarketDataCapability
    metrics: tuple[CanonicalMetric, ...]
    missing: tuple[MissingData, ...]
    source_registry: SourceRegistry

    def __post_init__(self) -> None:
        self.source_registry.assert_resolves(self.metrics)

    def as_research_fragments(self) -> dict[str, object]:
        return {
            "sources": self.source_registry.as_research_sources(),
            "metrics": [
                metric.model_dump(mode="json", exclude_none=False) for metric in self.metrics
            ],
        }


@runtime_checkable
class MarketDataProvider(Protocol):
    name: ProviderName
    markets: frozenset[Market]
    capabilities: frozenset[MarketDataCapability]

    async def fetch(self, request: ProviderRequest, sources: SourceRegistry) -> MarketDataResult:
        """Fetch one capability without mutating the caller's source registry."""
        ...
