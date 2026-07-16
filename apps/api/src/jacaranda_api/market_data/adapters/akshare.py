from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt

from jacaranda_api.market_data.adapters.base import (
    Clock,
    build_result,
    call_external,
    parse_payload,
    require_capability,
    source_draft,
    utc_now,
)
from jacaranda_api.market_data.contracts import MarketDataResult
from jacaranda_api.market_data.models import (
    Currency,
    LocalizedText,
    Market,
    MarketDataCapability,
    ProviderName,
    ProviderRequest,
)
from jacaranda_api.market_data.source_registry import SourceRegistry


class AkshareClient(Protocol):
    async def fetch_quote(self, symbol: str) -> Mapping[str, object]: ...


class AkshareQuotePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latest: StrictFloat | StrictInt | None
    trade_date: date
    currency: Currency


class AkshareMarketDataProvider:
    name = ProviderName.AKSHARE
    markets = frozenset({Market.CN_A})
    capabilities = frozenset({MarketDataCapability.QUOTE})

    def __init__(self, client: AkshareClient, *, clock: Clock = utc_now) -> None:
        self._client = client
        self._clock = clock

    async def fetch(self, request: ProviderRequest, sources: SourceRegistry) -> MarketDataResult:
        require_capability(self.name, request, self.capabilities)
        raw = await call_external(
            self.name, self._client.fetch_quote(request.symbol.provider_symbol)
        )
        payload = parse_payload(self.name, AkshareQuotePayload, raw)
        retrieved_at = self._clock()
        return build_result(
            provider=self.name,
            request=request,
            registry=sources,
            source=source_draft(
                provider=self.name,
                request=request,
                retrieved_at=retrieved_at,
            ),
            value=payload.latest,
            metric_name=LocalizedText(zh_CN="收盘价", en_AU="Closing price"),
            unit="CNY/share",
            currency=payload.currency,
            period="PIT",
            as_of_date=payload.trade_date,
            missing_field="closing_price",
        )
