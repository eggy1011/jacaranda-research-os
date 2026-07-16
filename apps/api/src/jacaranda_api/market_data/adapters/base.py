from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, date, datetime
from typing import Literal, TypeVar

from pydantic import BaseModel, SecretStr, ValidationError

from jacaranda_api.market_data.contracts import MarketDataResult
from jacaranda_api.market_data.errors import (
    ClientFailureKind,
    ExternalClientFailure,
    MalformedProviderResponseError,
    ProviderAuthenticationError,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from jacaranda_api.market_data.models import (
    CanonicalMetric,
    Currency,
    LocalizedText,
    MarketDataCapability,
    MissingData,
    ProviderName,
    ProviderRequest,
    SourceDraft,
)
from jacaranda_api.market_data.source_registry import SourceRegistry

Clock = Callable[[], datetime]
T = TypeVar("T")
PayloadT = TypeVar("PayloadT", bound=BaseModel)


def utc_now() -> datetime:
    return datetime.now(UTC)


def require_credential(provider: ProviderName, credential: SecretStr | None, setting: str) -> None:
    if credential is None or not credential.get_secret_value().strip():
        raise ProviderConfigurationError(provider.value, setting)


def require_text_setting(provider: ProviderName, value: str | None, setting: str) -> None:
    if value is None or not value.strip():
        raise ProviderConfigurationError(provider.value, setting)


def require_capability(
    provider: ProviderName,
    request: ProviderRequest,
    capabilities: frozenset[MarketDataCapability],
) -> None:
    if request.capability not in capabilities:
        raise ProviderCapabilityError(provider.value)


async def call_external(provider: ProviderName, operation: Awaitable[T]) -> T:
    try:
        return await operation
    except ExternalClientFailure as exc:
        if exc.kind is ClientFailureKind.AUTHENTICATION:
            raise ProviderAuthenticationError(provider.value) from None
        if exc.kind is ClientFailureKind.RATE_LIMIT:
            raise ProviderRateLimitError(provider.value) from None
        raise ProviderUnavailableError(provider.value) from None
    except Exception:
        # Never include the upstream exception: SDK messages can contain request URLs or keys.
        raise ProviderUnavailableError(provider.value) from None


def parse_payload(
    provider: ProviderName,
    payload_type: type[PayloadT],
    raw: Mapping[str, object],
) -> PayloadT:
    try:
        return payload_type.model_validate(raw)
    except (ValidationError, TypeError, ValueError):
        raise MalformedProviderResponseError(provider.value) from None


def build_result(
    *,
    provider: ProviderName,
    request: ProviderRequest,
    registry: SourceRegistry,
    source: SourceDraft,
    value: int | float | None,
    metric_name: LocalizedText,
    unit: str,
    currency: Currency | None,
    period: str,
    as_of_date: date,
    missing_field: str,
) -> MarketDataResult:
    registration = registry.register(source)
    if value is None:
        return MarketDataResult(
            provider=provider,
            symbol=request.symbol,
            capability=request.capability,
            metrics=(),
            missing=(
                MissingData(
                    field=missing_field,
                    reason="not_available",
                    provider=provider,
                ),
            ),
            source_registry=registration.registry,
        )

    try:
        metric = CanonicalMetric(
            metric_id=request.metric_id(),
            name=metric_name,
            value=value,
            unit=unit,
            currency=currency,
            period=period,
            as_of_date=as_of_date,
            source_id=registration.source.source_id,
            source_url_or_document=registration.source.url_or_document,
            retrieved_at=source.retrieved_at,
            computed_by="provider",
        )
    except (ValidationError, ValueError):
        raise MalformedProviderResponseError(provider.value) from None

    return MarketDataResult(
        provider=provider,
        symbol=request.symbol,
        capability=request.capability,
        metrics=(metric,),
        missing=(),
        source_registry=registration.registry,
    )


def source_draft(
    *,
    provider: ProviderName,
    request: ProviderRequest,
    retrieved_at: datetime,
    source_type: Literal["market_data_api", "filing"] = "market_data_api",
    url_or_document: str | None = None,
    published_date: date | None = None,
) -> SourceDraft:
    language: Literal["zh", "en"] = "zh" if request.symbol.market.value == "CN-A" else "en"
    publisher = {
        ProviderName.AKSHARE: "AKShare",
        ProviderName.FMP: "Financial Modeling Prep",
        ProviderName.FINNHUB: "Finnhub",
        ProviderName.SEC: "U.S. Securities and Exchange Commission",
    }[provider]
    return SourceDraft(
        source_type=source_type,
        title=f"{publisher} {request.capability.value} response",
        publisher=publisher,
        url_or_document=url_or_document
        or f"provider://{provider.value}/{request.capability.value}/{request.symbol.canonical}",
        locator=request.symbol.canonical,
        published_date=published_date,
        retrieved_at=retrieved_at,
        reliability_tier="primary",
        language=language,
    )
