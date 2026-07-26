from __future__ import annotations

import re
from datetime import UTC

from jacaranda_api.market_data.adapters.akshare import (
    AkshareClient,
    AkshareMarketDataProvider,
    AkshareProfilePayload,
)
from jacaranda_api.market_data.adapters.base import (
    Clock,
    call_external,
    parse_payload,
    utc_now,
)
from jacaranda_api.market_data.errors import SymbolNormalizationError
from jacaranda_api.market_data.models import (
    Market,
    MarketDataCapability,
    MissingData,
    NormalizedSymbol,
    ProviderName,
    ProviderRequest,
    SourceDraft,
)
from jacaranda_api.market_data.source_registry import SourceRegistry
from jacaranda_api.market_data.symbols import normalize_symbol
from jacaranda_api.pipeline.models import JsonDict

EVIDENCE_SCHEMA_VERSION = "0.1.0"

_BARE_A_SHARE = re.compile(r"^[0-9]{6}$")


def resolve_a_share_symbol(raw_symbol: str) -> NormalizedSymbol:
    """Normalise an A-share symbol, inferring the exchange suffix for bare 6-digit codes."""
    text = raw_symbol.strip().upper()
    if _BARE_A_SHARE.fullmatch(text):
        text = f"{text}.SS" if text.startswith("6") else f"{text}.SZ"
    symbol = normalize_symbol(text)
    if symbol.market is not Market.CN_A:
        raise SymbolNormalizationError()
    return symbol


async def build_evidence_pack(
    raw_symbol: str,
    client: AkshareClient,
    *,
    clock: Clock = utc_now,
) -> JsonDict:
    """Milestone-1 deliverable: real company identity, quote, financial indicators and
    official-source provenance in one traceable pack; absent values stay absent."""
    symbol = resolve_a_share_symbol(raw_symbol)
    provider = AkshareMarketDataProvider(client, clock=clock)
    registry = SourceRegistry()

    quote = await provider.fetch(
        ProviderRequest(
            symbol=symbol, capability=MarketDataCapability.QUOTE, metric_id_start=1
        ),
        registry,
    )
    registry = quote.source_registry
    financials = await provider.fetch(
        ProviderRequest(
            symbol=symbol,
            capability=MarketDataCapability.FINANCIALS,
            metric_id_start=1 + len(quote.metrics),
        ),
        registry,
    )
    registry = financials.source_registry

    profile_raw = await call_external(
        ProviderName.AKSHARE, client.fetch_company_profile(symbol.provider_symbol)
    )
    profile = parse_payload(ProviderName.AKSHARE, AkshareProfilePayload, profile_raw)
    profile_registration = registry.register(
        SourceDraft(
            source_type="market_data_api",
            title="AKShare company profile response",
            publisher="AKShare",
            url_or_document=f"provider://akshare/profile/{symbol.canonical}",
            locator=symbol.canonical,
            retrieved_at=clock(),
            reliability_tier="primary",
            language="zh",
        )
    )
    registry = profile_registration.registry

    metrics = [*quote.metrics, *financials.metrics]
    missing = [*quote.missing, *financials.missing]
    warnings = _warnings(
        profile_missing_name_en=profile.name_en is None,
        missing=missing,
        quote_missing=quote.missing,
    )

    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "generated_at": clock().astimezone(UTC).isoformat(),
        "symbol": {
            "original": symbol.original,
            "canonical": symbol.canonical,
            "provider_symbol": symbol.provider_symbol,
            "market": symbol.market.value,
            "exchange": symbol.exchange.value if symbol.exchange else None,
        },
        "company": {
            "name_zh": profile.name_zh,
            "name_en": profile.name_en,
            "industry": profile.industry,
            "listing_date": profile.listing_date.isoformat() if profile.listing_date else None,
            "source_id": profile_registration.source.source_id,
            "is_mock": False,
        },
        "sources": registry.as_research_sources(),
        "metrics": [metric.model_dump(mode="json", exclude_none=False) for metric in metrics],
        "missing": [item.model_dump(mode="json") for item in missing],
        "warnings": warnings,
    }


def _warnings(
    *,
    profile_missing_name_en: bool,
    missing: list[MissingData],
    quote_missing: tuple[MissingData, ...],
) -> list[str]:
    warnings: list[str] = []
    if profile_missing_name_en:
        warnings.append(
            "english_company_name_unavailable: AKShare provides no official English name; "
            "supply it manually before research approval"
        )
    if quote_missing:
        warnings.append("quote_unavailable: no closing price was reported for the latest session")
    reported_missing = [item for item in missing if item not in quote_missing]
    if reported_missing:
        fields = ", ".join(sorted(item.field for item in reported_missing))
        warnings.append(f"financial_indicators_missing: {fields}")
    return warnings
