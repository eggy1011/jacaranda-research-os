from __future__ import annotations

import asyncio
import importlib
import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

from jacaranda_api.market_data.errors import ClientFailureKind, ExternalClientFailure

_CN_NUMBER = re.compile(r"^-?[0-9][0-9,]*(?:\.[0-9]+)?$")

# (field, zh row label to match, en name, unit, currency) — matched against the
# 指标 column of ak.stock_financial_abstract; absent rows become missing data.
_INDICATOR_SPECS: tuple[tuple[str, str, str, str, str | None], ...] = (
    ("total_revenue", "营业总收入", "Total operating revenue", "CNY", "CNY"),
    (
        "net_profit_attributable",
        "归母净利润",
        "Net profit attributable to shareholders",
        "CNY",
        "CNY",
    ),
    ("basic_eps", "基本每股收益", "Basic earnings per share", "CNY/share", "CNY"),
    ("roe", "净资产收益率", "Return on equity", "%", None),
    ("debt_to_assets", "资产负债率", "Debt-to-asset ratio", "%", None),
    ("gross_margin", "毛利率", "Gross margin", "%", None),
)


def default_akshare_module() -> Any:
    """Import the real AKShare SDK; only ever called outside tests/CI."""
    return importlib.import_module("akshare")


class AkshareLiveClient:
    """AkshareClient implementation over the synchronous AKShare SDK.

    The SDK object is injectable so unit tests can drive the parsing logic with
    recorded frames and never import (or hit) the real library.
    """

    def __init__(self, ak_module: Any | None = None) -> None:
        self._ak = ak_module if ak_module is not None else default_akshare_module()

    async def fetch_quote(self, symbol: str) -> Mapping[str, object]:
        return await asyncio.to_thread(self._quote_sync, symbol)

    async def fetch_financial_indicators(self, symbol: str) -> Mapping[str, object]:
        return await asyncio.to_thread(self._financials_sync, symbol)

    async def fetch_company_profile(self, symbol: str) -> Mapping[str, object]:
        return await asyncio.to_thread(self._profile_sync, symbol)

    def _quote_sync(self, symbol: str) -> Mapping[str, object]:
        end = datetime.now().date()
        start = end - timedelta(days=30)
        # Eastmoney first; its endpoint intermittently drops connections, so the
        # Sina daily endpoint is a same-shape fallback (both are AKShare surfaces).
        frame: Any = None
        date_column, close_column = "日期", "收盘"
        try:
            frame = self._call(
                self._ak.stock_zh_a_hist,
                symbol=symbol,
                period="daily",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="",
            )
        except ExternalClientFailure:
            frame = None
        if frame is None or len(frame) == 0:
            prefix = "sh" if symbol.startswith("6") else "sz"
            frame = self._call(
                self._ak.stock_zh_a_daily,
                symbol=f"{prefix}{symbol}",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
            date_column, close_column = "date", "close"
        if frame is None or len(frame) == 0:
            raise ExternalClientFailure(kind=ClientFailureKind.UNAVAILABLE)
        row = frame.iloc[-1]
        trade_date = _as_date(row[date_column])
        if trade_date is None:
            raise ExternalClientFailure(kind=ClientFailureKind.UNAVAILABLE)
        return {
            "latest": _as_number(row[close_column]),
            "trade_date": trade_date,
            "currency": "CNY",
        }

    def _financials_sync(self, symbol: str) -> Mapping[str, object]:
        frame = self._call(self._ak.stock_financial_abstract, symbol=symbol)
        if frame is None or len(frame) == 0:
            raise ExternalClientFailure(kind=ClientFailureKind.UNAVAILABLE)
        period_column = self._latest_annual_column(frame)
        year = period_column[:4]
        as_of = date(int(year), 12, 31)
        labels = {str(value): index for index, value in enumerate(frame["指标"].tolist())}
        records: list[Mapping[str, object]] = []
        for field, zh_label, en_name, unit, currency in _INDICATOR_SPECS:
            row_index = labels.get(zh_label)
            if row_index is None:
                row_index = next(
                    (index for label, index in labels.items() if zh_label in label), None
                )
            value = (
                _as_number(frame.iloc[row_index][period_column])
                if row_index is not None
                else None
            )
            records.append(
                {
                    "field": field,
                    "name_zh": zh_label,
                    "name_en": en_name,
                    "value": value,
                    "unit": unit,
                    "currency": currency,
                    "period": f"FY{year}",
                    "as_of_date": as_of,
                }
            )
        return {"records": records}

    def _profile_sync(self, symbol: str) -> Mapping[str, object]:
        frame = self._call(self._ak.stock_profile_cninfo, symbol=symbol)
        if frame is None or len(frame) == 0:
            raise ExternalClientFailure(kind=ClientFailureKind.UNAVAILABLE)
        row = frame.iloc[0]
        name = _as_text(row.get("公司名称"))
        if name is None:
            raise ExternalClientFailure(kind=ClientFailureKind.UNAVAILABLE)
        return {
            "name_zh": name,
            "name_en": _as_text(row.get("英文名称")),
            "industry": _as_text(row.get("所属行业")),
            "listing_date": _as_date(row.get("上市日期")),
        }

    @staticmethod
    def _latest_annual_column(frame: Any) -> str:
        annual = sorted(
            (
                str(column)
                for column in frame.columns
                if re.fullmatch(r"[0-9]{4}1231", str(column))
            ),
            reverse=True,
        )
        if not annual:
            raise ExternalClientFailure(kind=ClientFailureKind.UNAVAILABLE)
        return annual[0]

    @staticmethod
    def _call(func: Any, **kwargs: Any) -> Any:
        try:
            return func(**kwargs)
        except ExternalClientFailure:
            raise
        except Exception:
            # Never propagate SDK messages: they can embed request URLs.
            raise ExternalClientFailure(kind=ClientFailureKind.UNAVAILABLE) from None


def _as_number(value: Any) -> float | None:
    """Best-effort numeric parse; missing stays missing (never coerced to zero)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return None if number != number else number
    text = str(value).strip().replace("，", ",")
    if not text or text in {"-", "--", "nan", "NaN", "None"}:
        return None
    scale = 1.0
    if text.endswith("亿"):
        scale, text = 1e8, text[:-1]
    elif text.endswith("万"):
        scale, text = 1e4, text[:-1]
    elif text.endswith("%"):
        text = text[:-1]
    if not _CN_NUMBER.fullmatch(text):
        return None
    return float(text.replace(",", "")) * scale


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "-", "--"}:
        return None
    return text


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if re.fullmatch(r"[0-9]{8}", text):
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        return date(int(text[:4]), int(text[5:7]), int(text[8:10]))
    return None
