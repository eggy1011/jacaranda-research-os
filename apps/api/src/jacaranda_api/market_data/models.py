from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    model_validator,
)


class Market(StrEnum):
    CN_A = "CN-A"
    US = "US"


class Exchange(StrEnum):
    SSE = "SSE"
    SZSE = "SZSE"
    BSE = "BSE"
    NYSE = "NYSE"
    NASDAQ = "NASDAQ"
    AMEX = "AMEX"


class ProviderName(StrEnum):
    AKSHARE = "akshare"
    FMP = "fmp"
    FINNHUB = "finnhub"
    SEC = "sec"


class MarketDataCapability(StrEnum):
    QUOTE = "quote"
    FINANCIALS = "financials"
    FILINGS = "filings"


class Currency(StrEnum):
    CNY = "CNY"
    USD = "USD"
    HKD = "HKD"
    AUD = "AUD"
    EUR = "EUR"
    JPY = "JPY"
    GBP = "GBP"


def _require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieval timestamps must include a timezone")
    return value


AwareDatetime = Annotated[datetime, AfterValidator(_require_timezone)]


class LocalizedText(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    zh_CN: Annotated[str, Field(min_length=1)]
    en_AU: Annotated[str, Field(min_length=1)]


class NormalizedSymbol(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    original: Annotated[str, Field(min_length=1)]
    canonical: Annotated[str, Field(min_length=1)]
    provider_symbol: Annotated[str, Field(min_length=1)]
    market: Market
    exchange: Exchange | None = None


class CanonicalSource(BaseModel):
    """Research-package compatible provenance source."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    source_id: Annotated[str, Field(pattern=r"^SRC-[0-9]{3}$")]
    source_type: Literal["market_data_api", "filing"] = Field(alias="type")
    title: Annotated[str, Field(min_length=1)]
    publisher: str | None = None
    url_or_document: Annotated[str, Field(min_length=1)]
    locator: str | None = None
    published_date: date | None = None
    retrieved_at: AwareDatetime
    reliability_tier: Literal["primary"] = "primary"
    language: Literal["zh", "en", "other"] | None = None

    @property
    def identity(self) -> tuple[str, str | None, datetime]:
        return (
            self.url_or_document,
            self.locator,
            self.retrieved_at.astimezone(UTC),
        )


class SourceDraft(BaseModel):
    """Source data before the package-local SRC identifier is allocated."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: Literal["market_data_api", "filing"]
    title: Annotated[str, Field(min_length=1)]
    publisher: str | None = None
    url_or_document: Annotated[str, Field(min_length=1)]
    locator: str | None = None
    published_date: date | None = None
    retrieved_at: AwareDatetime
    reliability_tier: Literal["primary"] = "primary"
    language: Literal["zh", "en", "other"] | None = None

    @property
    def identity(self) -> tuple[str, str | None, datetime]:
        return (
            self.url_or_document,
            self.locator,
            self.retrieved_at.astimezone(UTC),
        )

    def with_id(self, source_id: str) -> CanonicalSource:
        return CanonicalSource(
            source_id=source_id,
            type=self.source_type,
            title=self.title,
            publisher=self.publisher,
            url_or_document=self.url_or_document,
            locator=self.locator,
            published_date=self.published_date,
            retrieved_at=self.retrieved_at,
            reliability_tier=self.reliability_tier,
            language=self.language,
        )


MetricValue = StrictFloat | StrictInt


class CanonicalMetric(BaseModel):
    """Numeric value in the exact canonical shape expected by the research package."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_id: Annotated[str, Field(pattern=r"^MET-[0-9]{3}$")]
    name: LocalizedText
    value: Annotated[MetricValue, Field(allow_inf_nan=False)]
    unit: Annotated[str, Field(min_length=1)]
    currency: Currency | None
    period: Annotated[
        str,
        Field(pattern=r"^(FY[0-9]{4}|[0-9]{4}(H1|H2|Q[1-4])|TTM[0-9]{4}Q[1-4]|PIT)$"),
    ]
    as_of_date: date
    source_id: Annotated[str, Field(pattern=r"^SRC-[0-9]{3}$")]
    source_url_or_document: Annotated[str, Field(min_length=1)]
    retrieved_at: AwareDatetime
    computed_by: Literal["provider"] = "provider"
    restated: bool = False

    @model_validator(mode="after")
    def require_currency_for_monetary_units(self) -> CanonicalMetric:
        for expected_currency in Currency:
            if self.unit == expected_currency.value or self.unit.startswith(
                f"{expected_currency.value}/"
            ):
                if self.currency is not expected_currency:
                    raise ValueError("monetary metric unit and currency must match")
                break
        return self


class MissingData(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: Annotated[str, Field(min_length=1)]
    reason: Literal["not_reported", "not_supported", "not_available"]
    provider: ProviderName


class ProviderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: NormalizedSymbol
    capability: MarketDataCapability
    metric_id_start: Annotated[int, Field(ge=1, le=999)] = 1

    def metric_id(self, offset: int = 0) -> str:
        value = self.metric_id_start + offset
        if value > 999:
            raise ValueError("metric identifier sequence exhausted")
        return f"MET-{value:03d}"
