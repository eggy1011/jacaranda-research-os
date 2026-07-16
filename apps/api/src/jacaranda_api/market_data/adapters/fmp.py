from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, SecretStr, StrictFloat, StrictInt

from jacaranda_api.market_data.adapters.base import (
    Clock,
    build_result,
    call_external,
    parse_payload,
    require_capability,
    require_credential,
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


class FmpClient(Protocol):
    async def fetch_quote(self, symbol: str) -> Mapping[str, object]: ...


class FmpQuotePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: StrictFloat | StrictInt | None
    as_of_date: date
    currency: Currency


class FmpMarketDataProvider:
    name = ProviderName.FMP
    markets = frozenset({Market.US})
    capabilities = frozenset({MarketDataCapability.QUOTE})

    def __init__(
        self,
        client: FmpClient,
        *,
        api_key: SecretStr | None,
        clock: Clock = utc_now,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._clock = clock

    async def fetch(self, request: ProviderRequest, sources: SourceRegistry) -> MarketDataResult:
        require_capability(self.name, request, self.capabilities)
        require_credential(self.name, self._api_key, "FMP_API_KEY")
        raw = await call_external(
            self.name, self._client.fetch_quote(request.symbol.provider_symbol)
        )
        payload = parse_payload(self.name, FmpQuotePayload, raw)
        retrieved_at = self._clock()
        return build_result(
            provider=self.name,
            request=request,
            registry=sources,
            source=source_draft(provider=self.name, request=request, retrieved_at=retrieved_at),
            value=payload.price,
            metric_name=LocalizedText(zh_CN="收盘价", en_AU="Closing price"),
            unit="USD/share",
            currency=payload.currency,
            period="PIT",
            as_of_date=payload.as_of_date,
            missing_field="closing_price",
        )
