from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

from jacaranda_api.market_data.adapters.base import (
    Clock,
    build_result,
    call_external,
    parse_payload,
    require_capability,
    require_text_setting,
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


class SecClient(Protocol):
    async def fetch_company_fact(
        self, symbol: str, capability: MarketDataCapability
    ) -> Mapping[str, object]: ...


class SecFactPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: StrictFloat | StrictInt | None
    unit: Annotated[str, Field(min_length=1)]
    currency: Currency | None
    period: Annotated[
        str,
        Field(pattern=r"^(FY[0-9]{4}|[0-9]{4}(H1|H2|Q[1-4])|TTM[0-9]{4}Q[1-4]|PIT)$"),
    ]
    as_of_date: date
    filed_date: date
    source_url: Annotated[str, Field(min_length=1)]
    name_zh: Annotated[str, Field(min_length=1)]
    name_en: Annotated[str, Field(min_length=1)]


class SecMarketDataProvider:
    name = ProviderName.SEC
    markets = frozenset({Market.US})
    capabilities = frozenset({MarketDataCapability.FINANCIALS})

    def __init__(
        self,
        client: SecClient,
        *,
        user_agent: str | None,
        clock: Clock = utc_now,
    ) -> None:
        self._client = client
        self._user_agent = user_agent
        self._clock = clock

    async def fetch(self, request: ProviderRequest, sources: SourceRegistry) -> MarketDataResult:
        require_capability(self.name, request, self.capabilities)
        require_text_setting(self.name, self._user_agent, "SEC_USER_AGENT")
        raw = await call_external(
            self.name,
            self._client.fetch_company_fact(request.symbol.provider_symbol, request.capability),
        )
        payload = parse_payload(self.name, SecFactPayload, raw)
        retrieved_at = self._clock()
        return build_result(
            provider=self.name,
            request=request,
            registry=sources,
            source=source_draft(
                provider=self.name,
                request=request,
                retrieved_at=retrieved_at,
                source_type="filing",
                url_or_document=payload.source_url,
                published_date=payload.filed_date,
            ),
            value=payload.value,
            metric_name=LocalizedText(zh_CN=payload.name_zh, en_AU=payload.name_en),
            unit=payload.unit,
            currency=payload.currency,
            period=payload.period,
            as_of_date=payload.as_of_date,
            missing_field="company_fact",
        )
