from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from jacaranda_api.market_data.adapters.akshare import AkshareMarketDataProvider
from jacaranda_api.market_data.adapters.base import utc_now
from jacaranda_api.market_data.adapters.finnhub import FinnhubMarketDataProvider
from jacaranda_api.market_data.adapters.fmp import FmpMarketDataProvider
from jacaranda_api.market_data.adapters.sec import SecMarketDataProvider
from jacaranda_api.market_data.errors import (
    ClientFailureKind,
    ExternalClientFailure,
    MalformedProviderResponseError,
    ProviderAuthenticationError,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from jacaranda_api.market_data.models import (
    MarketDataCapability,
    ProviderName,
    ProviderRequest,
)
from jacaranda_api.market_data.source_registry import SourceRegistry
from jacaranda_api.market_data.symbols import normalize_symbol


class QuoteClient:
    def __init__(
        self,
        payload: Mapping[str, object] | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.payload = payload or {}
        self.failure = failure
        self.symbols: list[str] = []

    async def fetch_quote(self, symbol: str) -> Mapping[str, object]:
        self.symbols.append(symbol)
        if self.failure:
            raise self.failure
        return self.payload


class SecClientStub:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, MarketDataCapability]] = []

    async def fetch_company_fact(
        self, symbol: str, capability: MarketDataCapability
    ) -> Mapping[str, object]:
        self.calls.append((symbol, capability))
        return self.payload


def request(symbol: str, capability: MarketDataCapability) -> ProviderRequest:
    return ProviderRequest(symbol=normalize_symbol(symbol), capability=capability)


@pytest.mark.anyio
async def test_akshare_quote_preserves_provenance(
    load_market_fixture: Callable[[str], dict[str, object]], fixed_now: datetime
) -> None:
    client = QuoteClient(load_market_fixture("akshare_quote.json"))
    provider = AkshareMarketDataProvider(client, clock=lambda: fixed_now)

    result = await provider.fetch(
        request("600519.SS", MarketDataCapability.QUOTE), SourceRegistry()
    )

    assert client.symbols == ["600519"]
    assert result.provider is ProviderName.AKSHARE
    assert result.metrics[0].value == 123.45
    assert result.metrics[0].unit == "CNY/share"
    assert result.metrics[0].source_id == "SRC-001"
    assert result.metrics[0].retrieved_at == fixed_now
    assert result.source_registry.resolve("SRC-001").language == "zh"


@pytest.mark.anyio
async def test_fmp_and_finnhub_quotes_use_injected_clients(
    load_market_fixture: Callable[[str], dict[str, object]], fixed_now: datetime
) -> None:
    fmp_client = QuoteClient(load_market_fixture("fmp_quote.json"))
    finnhub_client = QuoteClient(load_market_fixture("finnhub_quote.json"))
    fmp = FmpMarketDataProvider(
        fmp_client, api_key=SecretStr("fixture-only"), clock=lambda: fixed_now
    )
    finnhub = FinnhubMarketDataProvider(
        finnhub_client, api_key=SecretStr("fixture-only"), clock=lambda: fixed_now
    )

    fmp_result = await fmp.fetch(request("AAPL", MarketDataCapability.QUOTE), SourceRegistry())
    finnhub_result = await finnhub.fetch(
        request("AAPL", MarketDataCapability.QUOTE), SourceRegistry()
    )

    assert fmp_result.metrics[0].value == 42.5
    assert fmp_result.source_registry.sources[0].publisher == "Financial Modeling Prep"
    assert finnhub_result.metrics[0].value == 42.5
    assert finnhub_result.metrics[0].as_of_date.isoformat() == "2026-07-16"
    assert finnhub_result.source_registry.sources[0].publisher == "Finnhub"


@pytest.mark.anyio
async def test_sec_fact_uses_filing_provenance(
    load_market_fixture: Callable[[str], dict[str, object]], fixed_now: datetime
) -> None:
    client = SecClientStub(load_market_fixture("sec_fact.json"))
    provider = SecMarketDataProvider(
        client,
        user_agent="Jacaranda Research fixture@example.invalid",
        clock=lambda: fixed_now,
    )

    result = await provider.fetch(
        request("AAPL", MarketDataCapability.FINANCIALS), SourceRegistry()
    )

    assert client.calls == [("AAPL", MarketDataCapability.FINANCIALS)]
    assert result.metrics[0].period == "FY2025"
    assert result.metrics[0].computed_by == "provider"
    assert result.source_registry.sources[0].source_type == "filing"
    assert result.source_registry.sources[0].published_date is not None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider", "setting", "capability"),
    [
        (
            FmpMarketDataProvider(QuoteClient(), api_key=None),
            "FMP_API_KEY",
            MarketDataCapability.QUOTE,
        ),
        (
            FinnhubMarketDataProvider(QuoteClient(), api_key=SecretStr("")),
            "FINNHUB_API_KEY",
            MarketDataCapability.QUOTE,
        ),
        (
            SecMarketDataProvider(SecClientStub({}), user_agent=" "),
            "SEC_USER_AGENT",
            MarketDataCapability.FINANCIALS,
        ),
    ],
)
async def test_missing_configuration_is_safe_and_typed(
    provider: object, setting: str, capability: MarketDataCapability
) -> None:
    with pytest.raises(ProviderConfigurationError) as caught:
        await provider.fetch(  # type: ignore[attr-defined]
            request("AAPL", capability), SourceRegistry()
        )

    assert caught.value.retryable is False
    assert setting in str(caught.value)
    assert "fixture-only" not in str(caught.value)


@pytest.mark.anyio
async def test_explicit_missing_value_is_not_fabricated(fixed_now: datetime) -> None:
    provider = AkshareMarketDataProvider(
        QuoteClient({"latest": None, "trade_date": "2026-07-16", "currency": "CNY"}),
        clock=lambda: fixed_now,
    )

    result = await provider.fetch(
        request("000001.SZ", MarketDataCapability.QUOTE), SourceRegistry()
    )

    assert result.metrics == ()
    assert result.missing[0].field == "closing_price"
    assert result.missing[0].reason == "not_available"
    assert len(result.source_registry.sources) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"latest": "123.45", "trade_date": "2026-07-16", "currency": "CNY"},
        {"latest": 123.45, "trade_date": "not-a-date", "currency": "CNY"},
        {"latest": 123.45, "trade_date": "2026-07-16"},
        {"latest": 123.45, "trade_date": "2026-07-16", "currency": "CNY", "extra": 1},
    ],
)
async def test_malformed_upstream_data_fails_without_coercion(
    payload: dict[str, object], fixed_now: datetime
) -> None:
    provider = AkshareMarketDataProvider(QuoteClient(payload), clock=lambda: fixed_now)
    with pytest.raises(MalformedProviderResponseError) as caught:
        await provider.fetch(request("600519.SS", MarketDataCapability.QUOTE), SourceRegistry())
    assert caught.value.retryable is False


@pytest.mark.anyio
async def test_invalid_finnhub_timestamp_is_malformed(fixed_now: datetime) -> None:
    provider = FinnhubMarketDataProvider(
        QuoteClient({"c": 42.5, "t": 999999999999999999, "currency": "USD"}),
        api_key=SecretStr("fixture-only"),
        clock=lambda: fixed_now,
    )
    with pytest.raises(MalformedProviderResponseError):
        await provider.fetch(request("AAPL", MarketDataCapability.QUOTE), SourceRegistry())


@pytest.mark.anyio
async def test_currency_mismatch_is_malformed(fixed_now: datetime) -> None:
    provider = FmpMarketDataProvider(
        QuoteClient({"price": 42.5, "as_of_date": "2026-07-16", "currency": "CNY"}),
        api_key=SecretStr("fixture-only"),
        clock=lambda: fixed_now,
    )
    with pytest.raises(MalformedProviderResponseError):
        await provider.fetch(request("AAPL", MarketDataCapability.QUOTE), SourceRegistry())


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("failure", "error_type", "retryable"),
    [
        (
            ExternalClientFailure(ClientFailureKind.AUTHENTICATION),
            ProviderAuthenticationError,
            False,
        ),
        (ExternalClientFailure(ClientFailureKind.RATE_LIMIT), ProviderRateLimitError, True),
        (ExternalClientFailure(ClientFailureKind.UNAVAILABLE), ProviderUnavailableError, True),
        (RuntimeError("request?apikey=must-not-leak"), ProviderUnavailableError, True),
    ],
)
async def test_client_failures_are_sanitised_and_classified(
    failure: Exception,
    error_type: type[ProviderError],
    retryable: bool,
) -> None:
    provider = FmpMarketDataProvider(
        QuoteClient(failure=failure), api_key=SecretStr("fixture-only")
    )
    with pytest.raises(error_type) as caught:
        await provider.fetch(request("AAPL", MarketDataCapability.QUOTE), SourceRegistry())

    assert caught.value.retryable is retryable
    assert "must-not-leak" not in str(caught.value)


@pytest.mark.anyio
async def test_direct_adapter_call_rejects_unsupported_capability() -> None:
    provider = AkshareMarketDataProvider(QuoteClient())
    with pytest.raises(ProviderCapabilityError):
        await provider.fetch(
            request("600519.SS", MarketDataCapability.FINANCIALS), SourceRegistry()
        )


def test_fixture_clock_is_timezone_aware(fixed_now: datetime) -> None:
    assert fixed_now.tzinfo is UTC
    assert utc_now().tzinfo is UTC
