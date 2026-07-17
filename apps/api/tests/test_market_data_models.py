from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource

from jacaranda_api.market_data.adapters.base import utc_now
from jacaranda_api.market_data.contracts import MarketDataResult
from jacaranda_api.market_data.models import (
    CanonicalMetric,
    CanonicalSource,
    Currency,
    LocalizedText,
    MarketDataCapability,
    MissingData,
    ProviderName,
    ProviderRequest,
    SourceDraft,
)
from jacaranda_api.market_data.source_registry import SourceRegistry
from jacaranda_api.market_data.symbols import normalize_symbol

NOW = datetime(2026, 7, 16, 8, 30, tzinfo=UTC)


def source_draft(locator: str = "AAPL") -> SourceDraft:
    return SourceDraft(
        source_type="market_data_api",
        title="Synthetic quote fixture",
        publisher="Fixture Provider",
        url_or_document="provider://fixture/quote/AAPL",
        locator=locator,
        retrieved_at=NOW,
        language="en",
    )


def metric(source_id: str = "SRC-001") -> CanonicalMetric:
    return CanonicalMetric(
        metric_id="MET-001",
        name=LocalizedText(zh_CN="收盘价", en_AU="Closing price"),
        value=42.5,
        unit="USD/share",
        currency=Currency.USD,
        period="PIT",
        as_of_date=date(2026, 7, 16),
        source_id=source_id,
        source_url_or_document="provider://fixture/quote/AAPL",
        retrieved_at=NOW,
    )


def test_source_registry_is_persistent_and_deduplicates() -> None:
    empty = SourceRegistry()
    first = empty.register(source_draft())
    duplicate = first.registry.register(source_draft())
    second = first.registry.register(
        source_draft(locator="AAPL/secondary").model_copy(
            update={"url_or_document": "provider://fixture/quote/AAPL/secondary"}
        )
    )

    assert empty.sources == ()
    assert first.source.source_id == "SRC-001"
    assert duplicate.registry is first.registry
    assert duplicate.source is first.source
    assert second.source.source_id == "SRC-002"
    assert second.registry.resolve("SRC-001") is first.source
    assert second.registry.contains("SRC-002")
    assert second.registry.contains("SRC-999") is False
    with pytest.raises(KeyError):
        second.registry.resolve("SRC-999")


def test_source_registry_distinguishes_retrieval_events() -> None:
    first = SourceRegistry().register(source_draft())
    later = first.registry.register(
        source_draft().model_copy(
            update={"retrieved_at": datetime(2026, 7, 17, 8, 30, tzinfo=UTC)}
        )
    )

    assert later.source.source_id == "SRC-002"
    assert later.registry.sources == (first.source, later.source)


def test_source_registry_rejects_duplicate_state_and_exhaustion() -> None:
    source = source_draft().with_id("SRC-001")
    with pytest.raises(ValueError, match="identifiers"):
        SourceRegistry((source, source.model_copy(update={"locator": "other"})))
    with pytest.raises(ValueError, match="identities"):
        SourceRegistry((source, source.model_copy(update={"source_id": "SRC-002"})))

    exhausted = SourceRegistry((source.model_copy(update={"source_id": "SRC-999"}),))
    with pytest.raises(ValueError, match="exhausted"):
        exhausted.register(
            source_draft(locator="new").model_copy(update={"url_or_document": "new"})
        )


def test_result_requires_all_metric_sources_to_resolve() -> None:
    registry = SourceRegistry().register(source_draft()).registry
    valid = MarketDataResult(
        provider=ProviderName.FMP,
        symbol=normalize_symbol("AAPL"),
        capability=MarketDataCapability.QUOTE,
        metrics=(metric(),),
        missing=(),
        source_registry=registry,
    )
    fragments = valid.as_research_fragments()

    sources = cast(list[dict[str, object]], fragments["sources"])
    metrics = cast(list[dict[str, object]], fragments["metrics"])
    assert sources[0]["type"] == "market_data_api"
    assert metrics[0]["computed_by"] == "provider"
    with pytest.raises(ValueError, match="SRC-002"):
        MarketDataResult(
            provider=ProviderName.FMP,
            symbol=normalize_symbol("AAPL"),
            capability=MarketDataCapability.QUOTE,
            metrics=(metric("SRC-002"),),
            missing=(),
            source_registry=registry,
        )


def test_models_reject_unsafe_or_noncanonical_values() -> None:
    with pytest.raises(ValidationError, match="currency"):
        CanonicalMetric.model_validate({**metric().model_dump(), "currency": None})
    with pytest.raises(ValidationError):
        CanonicalMetric.model_validate({**metric().model_dump(), "value": float("nan")})
    with pytest.raises(ValidationError, match="timezone"):
        SourceDraft.model_validate(
            {**source_draft().model_dump(), "retrieved_at": datetime(2026, 1, 1)}
        )
    with pytest.raises(ValidationError):
        MissingData(field="price", reason="fabricated", provider=ProviderName.FMP)  # type: ignore[arg-type]

    non_monetary = CanonicalMetric.model_validate(
        {**metric().model_dump(), "unit": "%", "currency": None}
    )
    assert non_monetary.currency is None


def test_provider_request_allocates_metric_ids() -> None:
    request = ProviderRequest(
        symbol=normalize_symbol("AAPL"),
        capability=MarketDataCapability.QUOTE,
        metric_id_start=998,
    )
    assert request.metric_id() == "MET-998"
    assert request.metric_id(1) == "MET-999"
    with pytest.raises(ValueError, match="exhausted"):
        request.metric_id(2)


def test_research_fragments_validate_against_claude_schema() -> None:
    retrieval_time = utc_now()
    registry_value = SourceRegistry().register(
        source_draft().model_copy(update={"retrieved_at": retrieval_time})
    ).registry
    source = registry_value.sources[0]
    metric_value = metric().model_copy(update={"retrieved_at": retrieval_time})
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "packages/research-schema/research-package.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    registry = Registry().with_resource(schema["$id"], Resource.from_contents(schema))
    source_validator = Draft202012Validator(
        {"$ref": f"{schema['$id']}#/properties/sources/items"}, registry=registry
    )
    metric_validator = Draft202012Validator(
        {"$ref": f"{schema['$id']}#/properties/metrics/items"}, registry=registry
    )

    assert not list(
        source_validator.iter_errors(
            source.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
    )
    assert not list(metric_validator.iter_errors(metric_value.model_dump(mode="json")))


def test_canonical_source_accepts_schema_alias() -> None:
    source = CanonicalSource.model_validate(
        {
            "source_id": "SRC-001",
            "type": "filing",
            "title": "Synthetic filing",
            "url_or_document": "provider://sec/filing/TEST",
            "retrieved_at": NOW,
            "reliability_tier": "primary",
        }
    )
    assert source.source_type == "filing"
