from __future__ import annotations

from dataclasses import dataclass

from jacaranda_api.market_data.contracts import MarketDataProvider, MarketDataResult
from jacaranda_api.market_data.errors import ProviderRoutingError
from jacaranda_api.market_data.models import MarketDataCapability, ProviderName, ProviderRequest
from jacaranda_api.market_data.source_registry import SourceRegistry
from jacaranda_api.market_data.symbols import normalize_symbol


@dataclass(frozen=True, slots=True)
class ProviderRegistration:
    provider: MarketDataProvider
    priority: int


@dataclass(frozen=True, slots=True)
class ProviderRegistry:
    registrations: tuple[ProviderRegistration, ...] = ()

    def register(self, provider: MarketDataProvider, *, priority: int = 100) -> ProviderRegistry:
        if any(item.provider.name == provider.name for item in self.registrations):
            raise ValueError(f"provider already registered: {provider.name}")
        registrations = (
            *self.registrations,
            ProviderRegistration(provider=provider, priority=priority),
        )
        return ProviderRegistry(
            registrations=tuple(
                sorted(registrations, key=lambda item: (item.priority, item.provider.name))
            )
        )

    def select(
        self,
        request: ProviderRequest,
        preferred_provider: ProviderName | None = None,
    ) -> MarketDataProvider:
        candidates = [
            item.provider
            for item in self.registrations
            if request.symbol.market in item.provider.markets
            and request.capability in item.provider.capabilities
        ]
        if preferred_provider is not None:
            candidates = [
                provider for provider in candidates if provider.name == preferred_provider
            ]
            if not candidates:
                raise ProviderRoutingError(
                    "preferred provider cannot serve the requested capability"
                )
        if not candidates:
            raise ProviderRoutingError()
        return candidates[0]


@dataclass(frozen=True, slots=True)
class MarketDataRouter:
    registry: ProviderRegistry

    async def fetch(
        self,
        raw_symbol: str,
        capability: MarketDataCapability,
        sources: SourceRegistry,
        *,
        metric_id_start: int = 1,
        preferred_provider: ProviderName | None = None,
    ) -> MarketDataResult:
        request = ProviderRequest(
            symbol=normalize_symbol(raw_symbol),
            capability=capability,
            metric_id_start=metric_id_start,
        )
        provider = self.registry.select(request, preferred_provider)
        return await provider.fetch(request, sources)
