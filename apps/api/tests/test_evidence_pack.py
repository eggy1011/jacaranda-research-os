from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pytest

from jacaranda_api.market_data.adapters.akshare import AkshareMarketDataProvider
from jacaranda_api.market_data.clients.akshare_live import (
    AkshareLiveClient,
    _as_date,
    _as_number,
)
from jacaranda_api.market_data.errors import (
    ClientFailureKind,
    ExternalClientFailure,
    ProviderUnavailableError,
    SymbolNormalizationError,
)
from jacaranda_api.market_data.models import (
    Exchange,
    Market,
    MarketDataCapability,
    NormalizedSymbol,
    ProviderRequest,
)
from jacaranda_api.market_data.source_registry import SourceRegistry
from jacaranda_api.pipeline.cli_evidence import main as evidence_main
from jacaranda_api.pipeline.evidence import build_evidence_pack, resolve_a_share_symbol
from jacaranda_api.pipeline.mock_providers import FixtureAkshareClient


def fixed_clock() -> datetime:
    return datetime(2026, 7, 27, 9, 0, 0, tzinfo=UTC)


class StubClient:
    """Payload-level AkshareClient double for assembler tests."""

    def __init__(self, *, quote_value: float | None = 1710.5) -> None:
        self._quote_value = quote_value

    async def fetch_quote(self, symbol: str) -> Mapping[str, object]:
        assert symbol == "600519"
        return {
            "latest": self._quote_value,
            "trade_date": date(2026, 7, 24),
            "currency": "CNY",
        }

    async def fetch_financial_indicators(self, symbol: str) -> Mapping[str, object]:
        assert symbol == "600519"
        common = {"period": "FY2025", "as_of_date": date(2025, 12, 31)}
        return {
            "records": [
                {
                    "field": "total_revenue",
                    "name_zh": "营业总收入",
                    "name_en": "Total operating revenue",
                    "value": 147_694_000_000.0,
                    "unit": "CNY",
                    "currency": "CNY",
                    **common,
                },
                {
                    "field": "gross_margin",
                    "name_zh": "销售毛利率",
                    "name_en": "Gross margin",
                    "value": None,
                    "unit": "%",
                    "currency": None,
                    **common,
                },
            ]
        }

    async def fetch_company_profile(self, symbol: str) -> Mapping[str, object]:
        assert symbol == "600519"
        return {
            "name_zh": "贵州茅台酒股份有限公司",
            "name_en": None,
            "industry": "白酒",
            "listing_date": date(2001, 8, 27),
        }


class TestSymbolResolution:
    def test_bare_shanghai_code_gets_ss_suffix(self) -> None:
        symbol = resolve_a_share_symbol("600519")
        assert symbol.canonical == "600519.SS"
        assert symbol.exchange is Exchange.SSE

    def test_bare_shenzhen_code_gets_sz_suffix(self) -> None:
        assert resolve_a_share_symbol("000001").canonical == "000001.SZ"
        assert resolve_a_share_symbol("300750").canonical == "300750.SZ"

    def test_sh_suffix_normalises_to_ss(self) -> None:
        assert resolve_a_share_symbol("600519.SH").canonical == "600519.SS"

    def test_us_symbol_is_rejected(self) -> None:
        with pytest.raises(SymbolNormalizationError):
            resolve_a_share_symbol("AAPL")

    def test_garbage_is_rejected(self) -> None:
        with pytest.raises(SymbolNormalizationError):
            resolve_a_share_symbol("60051")


class TestNumberParsing:
    def test_plain_numbers_pass_through(self) -> None:
        assert _as_number(12.5) == 12.5
        assert _as_number(7) == 7.0

    def test_cn_scale_suffixes(self) -> None:
        assert _as_number("1476.94亿") == pytest.approx(147_694_000_000.0)
        assert _as_number("3.2万") == pytest.approx(32_000.0)

    def test_percent_and_comma_strings(self) -> None:
        assert _as_number("91.5%") == pytest.approx(91.5)
        assert _as_number("1,234.5") == pytest.approx(1234.5)

    def test_missing_markers_stay_missing(self) -> None:
        assert _as_number(None) is None
        assert _as_number("--") is None
        assert _as_number("") is None
        assert _as_number("n/a") is None
        assert _as_number(float("nan")) is None
        assert _as_number(True) is None

    def test_dates(self) -> None:
        assert _as_date("20010827") == date(2001, 8, 27)
        assert _as_date("2001-08-27") == date(2001, 8, 27)
        assert _as_date(date(2020, 1, 2)) == date(2020, 1, 2)
        assert _as_date(datetime(2020, 1, 2, 3, tzinfo=UTC)) == date(2020, 1, 2)
        assert _as_date("not a date") is None
        assert _as_date(None) is None


class FakeAkshareModule:
    def __init__(
        self,
        *,
        hist: pd.DataFrame | None = None,
        daily: pd.DataFrame | None = None,
        abstract: pd.DataFrame | None = None,
        info: pd.DataFrame | None = None,
        error: Exception | None = None,
    ) -> None:
        self._hist = hist
        self._daily = daily
        self._abstract = abstract
        self._info = info
        self._error = error

    def stock_zh_a_hist(self, **kwargs: Any) -> pd.DataFrame:
        if self._error is not None:
            raise self._error
        assert kwargs["symbol"] == "600519"
        assert self._hist is not None
        return self._hist

    def stock_zh_a_daily(self, **kwargs: Any) -> pd.DataFrame:
        assert kwargs["symbol"] == "sh600519"
        if self._daily is None:
            raise RuntimeError("fallback endpoint not stubbed")
        return self._daily

    def stock_financial_abstract(self, **kwargs: Any) -> pd.DataFrame:
        assert kwargs["symbol"] == "600519"
        assert self._abstract is not None
        return self._abstract

    def stock_profile_cninfo(self, **kwargs: Any) -> pd.DataFrame:
        assert kwargs["symbol"] == "600519"
        assert self._info is not None
        return self._info


def _hist_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {"日期": ["2026-07-23", "2026-07-24"], "收盘": [1700.0, 1710.5], "开盘": [1690.0, 1701.0]}
    )


def _abstract_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "选项": ["常用指标"] * 4,
            "指标": ["营业总收入", "归母净利润", "净资产收益率(ROE)", "资产负债率"],
            "20260331": [40_000_000_000.0, 21_000_000_000.0, 8.1, 17.2],
            "20251231": [147_694_000_000.0, 74_753_000_000.0, 34.7, None],
            "20241231": [130_000_000_000.0, 65_000_000_000.0, 33.1, 18.0],
        }
    )


def _info_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "公司名称": ["贵州茅台酒股份有限公司"],
            "英文名称": ["Kweichow Moutai Co., Ltd."],
            "所属行业": ["酒、饮料和精制茶制造业"],
            "上市日期": ["2001-08-27"],
            "法人代表": ["某人"],
        }
    )


class TestLiveClientParsing:
    @pytest.mark.anyio
    async def test_quote_uses_latest_row(self) -> None:
        client = AkshareLiveClient(FakeAkshareModule(hist=_hist_frame()))
        payload = await client.fetch_quote("600519")
        assert payload["latest"] == 1710.5
        assert payload["trade_date"] == date(2026, 7, 24)
        assert payload["currency"] == "CNY"

    @pytest.mark.anyio
    async def test_quote_empty_frame_fails_safely(self) -> None:
        client = AkshareLiveClient(FakeAkshareModule(hist=pd.DataFrame()))
        with pytest.raises(ExternalClientFailure):
            await client.fetch_quote("600519")

    @pytest.mark.anyio
    async def test_quote_falls_back_to_sina_daily(self) -> None:
        daily = pd.DataFrame(
            {"date": ["2026-07-23", "2026-07-24"], "close": [1299.0, 1305.6], "open": [1, 2]}
        )
        client = AkshareLiveClient(
            FakeAkshareModule(error=ConnectionError("eastmoney dropped"), daily=daily)
        )
        payload = await client.fetch_quote("600519")
        assert payload["latest"] == 1305.6
        assert payload["trade_date"] == date(2026, 7, 24)

    @pytest.mark.anyio
    async def test_sdk_exception_is_sanitised(self) -> None:
        client = AkshareLiveClient(
            FakeAkshareModule(error=RuntimeError("https://secret.example/?key=abc"))
        )
        with pytest.raises(ExternalClientFailure) as excinfo:
            await client.fetch_quote("600519")
        assert "secret" not in str(excinfo.value)

    @pytest.mark.anyio
    async def test_financials_pick_latest_annual_column(self) -> None:
        client = AkshareLiveClient(FakeAkshareModule(abstract=_abstract_frame()))
        payload = await client.fetch_financial_indicators("600519")
        record_list = cast(list[dict[str, Any]], payload["records"])
        records = {record["field"]: record for record in record_list}
        assert records["total_revenue"]["value"] == pytest.approx(147_694_000_000.0)
        assert records["total_revenue"]["period"] == "FY2025"
        assert records["total_revenue"]["as_of_date"] == date(2025, 12, 31)
        # matched via contains(): frame label is 净资产收益率(ROE)
        assert records["roe"]["value"] == pytest.approx(34.7)
        # present row, absent value for the chosen period -> missing, not zero
        assert records["debt_to_assets"]["value"] is None
        # row absent from the frame entirely -> missing
        assert records["gross_margin"]["value"] is None
        assert records["basic_eps"]["value"] is None

    @pytest.mark.anyio
    async def test_profile_parses_identity(self) -> None:
        client = AkshareLiveClient(FakeAkshareModule(info=_info_frame()))
        payload = await client.fetch_company_profile("600519")
        assert payload["name_zh"] == "贵州茅台酒股份有限公司"
        assert payload["name_en"] == "Kweichow Moutai Co., Ltd."
        assert payload["industry"] == "酒、饮料和精制茶制造业"
        assert payload["listing_date"] == date(2001, 8, 27)


class TestFinancialsAdapter:
    @pytest.mark.anyio
    async def test_multi_metric_result_with_missing(self) -> None:
        symbol = NormalizedSymbol(
            original="600519",
            canonical="600519.SS",
            provider_symbol="600519",
            market=Market.CN_A,
            exchange=Exchange.SSE,
        )
        provider = AkshareMarketDataProvider(StubClient(), clock=fixed_clock)
        result = await provider.fetch(
            ProviderRequest(
                symbol=symbol, capability=MarketDataCapability.FINANCIALS, metric_id_start=5
            ),
            SourceRegistry(),
        )
        assert [metric.metric_id for metric in result.metrics] == ["MET-005"]
        metric = result.metrics[0]
        assert metric.value == pytest.approx(147_694_000_000.0)
        assert metric.period == "FY2025"
        assert metric.source_id == "SRC-001"
        assert [item.field for item in result.missing] == ["gross_margin"]
        assert result.source_registry.contains("SRC-001")

    @pytest.mark.anyio
    async def test_sdk_failure_maps_to_typed_error(self) -> None:
        class Failing(StubClient):
            async def fetch_financial_indicators(self, symbol: str) -> Mapping[str, object]:
                raise ExternalClientFailure(ClientFailureKind.UNAVAILABLE)

        symbol = NormalizedSymbol(
            original="600519",
            canonical="600519.SS",
            provider_symbol="600519",
            market=Market.CN_A,
            exchange=Exchange.SSE,
        )
        provider = AkshareMarketDataProvider(Failing(), clock=fixed_clock)
        with pytest.raises(ProviderUnavailableError):
            await provider.fetch(
                ProviderRequest(symbol=symbol, capability=MarketDataCapability.FINANCIALS),
                SourceRegistry(),
            )


class TestEvidencePack:
    @pytest.mark.anyio
    async def test_full_pack_assembly(self) -> None:
        pack = await build_evidence_pack("600519", StubClient(), clock=fixed_clock)
        assert pack["schema_version"] == "0.1.0"
        assert pack["symbol"]["canonical"] == "600519.SS"
        assert pack["company"]["name_zh"] == "贵州茅台酒股份有限公司"
        assert pack["company"]["is_mock"] is False
        assert pack["company"]["listing_date"] == "2001-08-27"
        # three sources: quote, financials, profile — all resolvable and unique
        source_ids = [source["source_id"] for source in pack["sources"]]
        assert source_ids == ["SRC-001", "SRC-002", "SRC-003"]
        assert pack["company"]["source_id"] == "SRC-003"
        # metric ids are sequential across capabilities
        metric_ids = [metric["metric_id"] for metric in pack["metrics"]]
        assert metric_ids == ["MET-001", "MET-002"]
        # every metric carries full provenance
        for metric in pack["metrics"]:
            assert metric["source_id"] in source_ids
            assert metric["as_of_date"]
            assert metric["retrieved_at"]
            assert metric["unit"]
        # missing stays missing and is surfaced
        assert [item["field"] for item in pack["missing"]] == ["gross_margin"]
        assert any("english_company_name" in warning for warning in pack["warnings"])
        assert any("gross_margin" in warning for warning in pack["warnings"])

    @pytest.mark.anyio
    async def test_missing_quote_produces_warning(self) -> None:
        pack = await build_evidence_pack("600519", StubClient(quote_value=None), clock=fixed_clock)
        assert [metric["metric_id"] for metric in pack["metrics"]] == ["MET-001"]
        assert any("quote_unavailable" in warning for warning in pack["warnings"])

    @pytest.mark.anyio
    async def test_fixture_client_satisfies_protocol(self) -> None:
        fixture = FixtureAkshareClient()
        profile = await fixture.fetch_company_profile("600XXX")
        assert profile["name_zh"] == "示例智能制造股份有限公司"
        financials = await fixture.fetch_financial_indicators("600XXX")
        assert isinstance(financials["records"], list)
        with pytest.raises(ValueError, match="sentinel"):
            await fixture.fetch_company_profile("600519")


class TestEvidenceCli:
    def test_cli_writes_pack(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        out = tmp_path / "evidence"
        evidence_main(
            ["--symbol", "600519", "--output-dir", str(out)],
            client_factory=StubClient,
        )
        payload = json.loads((out / "evidence.json").read_text(encoding="utf-8"))
        assert payload["company"]["name_zh"] == "贵州茅台酒股份有限公司"
        captured = capsys.readouterr().out
        assert "evidence.json" in captured
        assert "missing: gross_margin" in captured
