from __future__ import annotations

from typing import Any

from jacaranda_api.pipeline.models import JsonDict


class DeterministicCalcError(ValueError):
    """A required input metric for a deterministic calculation is missing."""


def _find_metric(metrics: list[JsonDict], zh_name: str) -> JsonDict | None:
    for metric in metrics:
        name = metric.get("name")
        if isinstance(name, dict) and name.get("zh_CN") == zh_name:
            return metric
    return None


def _metric(
    *,
    metric_id: str,
    name_zh: str,
    name_en: str,
    value: float,
    unit: str,
    currency: str | None,
    period: str,
    as_of_date: str,
    source_id: str,
    source_url_or_document: str,
    retrieved_at: str,
    formula: str,
    input_metric_ids: list[str],
) -> JsonDict:
    return {
        "metric_id": metric_id,
        "name": {"zh_CN": name_zh, "en_AU": name_en},
        "value": value,
        "unit": unit,
        "currency": currency,
        "period": period,
        "as_of_date": as_of_date,
        "source_id": source_id,
        "source_url_or_document": source_url_or_document,
        "retrieved_at": retrieved_at,
        "computed_by": "deterministic_calc",
        "calculation": {"formula": formula, "input_metric_ids": input_metric_ids},
    }


class ValuationCalc:
    """Deterministic, auditable valuation inputs for S4 (D-004: code computes, LLM narrates).

    First-release method: a trailing-PE band. The anchor multiple is the company's
    own current trailing PE (closing price / latest annual EPS) and the band is a
    fixed ±15% around it. Every produced metric carries computed_by=deterministic_calc
    with its formula and input metric ids; nothing here is estimated by a model.
    """

    BAND = 0.15

    def compute(self, evidence: JsonDict, *, metric_id_start: int) -> JsonDict:
        metrics = list(evidence["metrics"])
        price = _find_metric(metrics, "收盘价")
        eps = _find_metric(metrics, "基本每股收益")
        if price is None or eps is None:
            raise DeterministicCalcError(
                "valuation requires both the closing price and basic EPS metrics"
            )
        price_value = float(price["value"])
        eps_value = float(eps["value"])
        if eps_value <= 0:
            raise DeterministicCalcError(
                "trailing-PE valuation is undefined for non-positive EPS"
            )
        pe = round(price_value / eps_value, 2)
        base_target = round(eps_value * pe, 2)
        low_target = round(base_target * (1 - self.BAND), 2)
        high_target = round(base_target * (1 + self.BAND), 2)

        def next_id(offset: int) -> str:
            return f"MET-{metric_id_start + offset:03d}"

        common: dict[str, Any] = {
            "source_id": price["source_id"],
            "source_url_or_document": price["source_url_or_document"],
            "retrieved_at": price["retrieved_at"],
            "as_of_date": price["as_of_date"],
        }
        pe_metric = _metric(
            metric_id=next_id(0),
            name_zh="市盈率（滚动）",
            name_en="Trailing PE",
            value=pe,
            unit="x",
            currency=None,
            period="PIT",
            formula="closing_price / basic_eps",
            input_metric_ids=[price["metric_id"], eps["metric_id"]],
            **common,
        )
        base_metric = _metric(
            metric_id=next_id(1),
            name_zh="目标价（基准情景）",
            name_en="Target price (base scenario)",
            value=base_target,
            unit="CNY/share",
            currency="CNY",
            period="PIT",
            formula="basic_eps * trailing_pe",
            input_metric_ids=[eps["metric_id"], pe_metric["metric_id"]],
            **common,
        )
        low_metric = _metric(
            metric_id=next_id(2),
            name_zh="估值区间下限",
            name_en="Valuation band low",
            value=low_target,
            unit="CNY/share",
            currency="CNY",
            period="PIT",
            formula=f"base_target * (1 - {self.BAND})",
            input_metric_ids=[base_metric["metric_id"]],
            **common,
        )
        high_metric = _metric(
            metric_id=next_id(3),
            name_zh="估值区间上限",
            name_en="Valuation band high",
            value=high_target,
            unit="CNY/share",
            currency="CNY",
            period="PIT",
            formula=f"base_target * (1 + {self.BAND})",
            input_metric_ids=[base_metric["metric_id"]],
            **common,
        )
        assumptions = [
            {
                "assumption_id": "ASM-001",
                "name": {"zh_CN": "市盈率锚", "en_AU": "PE anchor"},
                "value_text": f"trailing PE {pe}x (own current multiple)",
                "metric_id": pe_metric["metric_id"],
            },
            {
                "assumption_id": "ASM-002",
                "name": {"zh_CN": "估值区间宽度", "en_AU": "Valuation band width"},
                "value_text": f"±{int(self.BAND * 100)}% around the base target",
            },
        ]
        return {
            "metrics": [pe_metric, base_metric, low_metric, high_metric],
            "assumptions": assumptions,
            "method": {
                "method": "pe_comps",
                "label": {"zh_CN": "自身滚动市盈率区间", "en_AU": "Own trailing-PE band"},
                "low": low_metric["metric_id"],
                "high": high_metric["metric_id"],
                "assumption_ids": ["ASM-001", "ASM-002"],
            },
            "target_price_metric_id": base_metric["metric_id"],
            "current_price_metric_id": price["metric_id"],
            "scenario_metrics": {"base": base_metric["metric_id"]},
        }
