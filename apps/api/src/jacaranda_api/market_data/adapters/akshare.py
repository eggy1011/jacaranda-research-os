from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

from jacaranda_api.market_data.adapters.base import (
    Clock,
    MetricDraft,
    build_metrics_result,
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

    async def fetch_financial_indicators(self, symbol: str) -> Mapping[str, object]: ...

    async def fetch_company_profile(self, symbol: str) -> Mapping[str, object]: ...


class AkshareQuotePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latest: StrictFloat | StrictInt | None
    trade_date: date
    currency: Currency


class AkshareIndicatorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Annotated[str, Field(min_length=1)]
    name_zh: Annotated[str, Field(min_length=1)]
    name_en: Annotated[str, Field(min_length=1)]
    value: StrictFloat | StrictInt | None
    unit: Annotated[str, Field(min_length=1)]
    currency: Currency | None
    period: Annotated[
        str,
        Field(pattern=r"^(FY[0-9]{4}|[0-9]{4}(H1|H2|Q[1-4])|TTM[0-9]{4}Q[1-4]|PIT)$"),
    ]
    as_of_date: date


class AkshareFinancialsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: tuple[AkshareIndicatorRecord, ...]


class AkshareProfilePayload(BaseModel):
    """Company identity data; not a metric, consumed by the evidence assembler."""

    model_config = ConfigDict(extra="forbid")

    name_zh: Annotated[str, Field(min_length=1)]
    name_en: str | None = None
    industry: str | None = None
    listing_date: date | None = None


class AkshareMarketDataProvider:
    name = ProviderName.AKSHARE
    markets = frozenset({Market.CN_A})
    capabilities = frozenset({MarketDataCapability.QUOTE, MarketDataCapability.FINANCIALS})

    def __init__(self, client: AkshareClient, *, clock: Clock = utc_now) -> None:
        self._client = client
        self._clock = clock

    async def fetch(self, request: ProviderRequest, sources: SourceRegistry) -> MarketDataResult:
        require_capability(self.name, request, self.capabilities)
        if request.capability is MarketDataCapability.FINANCIALS:
            return await self._fetch_financials(request, sources)
        return await self._fetch_quote(request, sources)

    async def _fetch_quote(
        self, request: ProviderRequest, sources: SourceRegistry
    ) -> MarketDataResult:
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

    async def _fetch_financials(
        self, request: ProviderRequest, sources: SourceRegistry
    ) -> MarketDataResult:
        raw = await call_external(
            self.name, self._client.fetch_financial_indicators(request.symbol.provider_symbol)
        )
        payload = parse_payload(self.name, AkshareFinancialsPayload, raw)
        retrieved_at = self._clock()
        drafts = tuple(
            MetricDraft(
                field=record.field,
                name=LocalizedText(zh_CN=record.name_zh, en_AU=record.name_en),
                value=record.value,
                unit=record.unit,
                currency=record.currency,
                period=record.period,
                as_of_date=record.as_of_date,
            )
            for record in payload.records
        )
        return build_metrics_result(
            provider=self.name,
            request=request,
            registry=sources,
            source=source_draft(
                provider=self.name,
                request=request,
                retrieved_at=retrieved_at,
            ),
            drafts=drafts,
        )
