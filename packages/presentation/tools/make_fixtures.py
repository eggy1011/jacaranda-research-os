#!/usr/bin/env python3
"""Regenerate presentation fixtures deterministically (fictional company only).

Outputs (committed):
  fixtures/mock-package.json          research package (validates against research-package.schema.json)
  fixtures/deck-all-layouts.zh-CN.json  every L01-L11 layout at least once
  fixtures/deck-sample.zh-CN.json     14-slide full Chinese sample deck
  fixtures/deck-sample.en-AU.json     14-slide full English sample deck (same MET/CLM/SRC IDs)
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "fixtures"
AS_OF = "2026-07-10"
RETR = "2026-07-10T09:00:00+08:00"

# ---------------------------------------------------------------- helpers ---

def lt(zh: str, en: str) -> dict:
    return {"zh_CN": zh, "en_AU": en}


def metric(mid: str, zh: str, en: str, value: float, unit: str, currency,
           period: str, as_of: str, src: str, locator: str,
           calc: dict | None = None) -> dict:
    m = {
        "metric_id": mid, "name": lt(zh, en), "value": value, "unit": unit,
        "currency": currency, "period": period, "as_of_date": as_of,
        "source_id": src, "source_url_or_document": locator, "retrieved_at": RETR,
        "computed_by": "deterministic_calc" if calc else "provider",
    }
    if calc:
        m["calculation"] = calc
    return m


def dn(mid: str, transform: str = "raw", decimals: int = 1, sign: bool = False) -> dict:
    d: dict = {"metric_id": mid, "display_transform": transform, "decimals": decimals}
    if sign:
        d["show_sign_colour"] = True
    return d


# ---------------------------------------------------------------- package ---

SOURCES = [
    {"source_id": "SRC-001", "type": "annual_report",
     "title": "示例智能制造2025年年度报告（虚构测试文件）", "publisher": "示例智能制造股份有限公司",
     "url_or_document": "upload://mock-annual-report-2025.pdf", "locator": "合并报表及经营讨论",
     "published_date": "2026-04-20", "retrieved_at": RETR,
     "reliability_tier": "primary", "language": "zh"},
    {"source_id": "SRC-002", "type": "market_data_api",
     "title": "Mock market data provider — daily close", "publisher": "MockData",
     "url_or_document": "provider://mockdata/quote/600XXX?as_of=2026-07-10",
     "locator": "close 2026-07-10", "published_date": "2026-07-10", "retrieved_at": RETR,
     "reliability_tier": "primary", "language": "en"},
    {"source_id": "SRC-003", "type": "regulator",
     "title": "《智能制造装备产业发展指导意见》（虚构政策文件）", "publisher": "示例部委",
     "url_or_document": "https://example.gov.mock/policy/2026-guidance", "locator": "第三节",
     "published_date": "2026-03-01", "retrieved_at": RETR,
     "reliability_tier": "primary", "language": "zh"},
    {"source_id": "SRC-004", "type": "third_party_research",
     "title": "Mock industry outlook: factory automation 2026-2030",
     "publisher": "Example Research Institute",
     "url_or_document": "https://example-research.mock/fa-2026", "locator": "Exhibit 4",
     "published_date": "2026-05-15", "retrieved_at": RETR,
     "reliability_tier": "secondary", "language": "en"},
    {"source_id": "SRC-005", "type": "third_party_research",
     "title": "Mock comparable-company dataset (fictional peers)",
     "publisher": "Example Research Institute",
     "url_or_document": "https://example-research.mock/comps-2026", "locator": "Table 2",
     "published_date": "2026-06-30", "retrieved_at": RETR,
     "reliability_tier": "secondary", "language": "en"},
]

AR = "upload://mock-annual-report-2025.pdf#p102"
MODEL = "internal://valuation-model"
COMPS = "https://example-research.mock/comps-2026#t2"

METRICS = [
    # revenue FY2022-2025
    metric("MET-001", "营业收入（2022财年）", "Revenue (FY2022)", 2.89e9, "CNY", "CNY", "FY2022", "2022-12-31", "SRC-001", AR),
    metric("MET-002", "营业收入（2023财年）", "Revenue (FY2023)", 3.26e9, "CNY", "CNY", "FY2023", "2023-12-31", "SRC-001", AR),
    metric("MET-003", "营业收入（2024财年）", "Revenue (FY2024)", 3.76e9, "CNY", "CNY", "FY2024", "2024-12-31", "SRC-001", AR),
    metric("MET-004", "营业收入（2025财年）", "Revenue (FY2025)", 4.52e9, "CNY", "CNY", "FY2025", "2025-12-31", "SRC-001", AR),
    # net profit FY2022-2025
    metric("MET-005", "归母净利润（2022财年）", "Net profit (FY2022)", 0.28e9, "CNY", "CNY", "FY2022", "2022-12-31", "SRC-001", AR),
    metric("MET-006", "归母净利润（2023财年）", "Net profit (FY2023)", 0.34e9, "CNY", "CNY", "FY2023", "2023-12-31", "SRC-001", AR),
    metric("MET-007", "归母净利润（2024财年）", "Net profit (FY2024)", 0.41e9, "CNY", "CNY", "FY2024", "2024-12-31", "SRC-001", AR),
    metric("MET-008", "归母净利润（2025财年）", "Net profit (FY2025)", 0.512e9, "CNY", "CNY", "FY2025", "2025-12-31", "SRC-001", AR),
    # derived
    metric("MET-009", "营业收入同比增速（2025财年）", "Revenue growth YoY (FY2025)", 20.2, "%", None,
           "FY2025", "2025-12-31", "SRC-001", AR,
           {"formula": "(MET-004 / MET-003 - 1) * 100", "input_metric_ids": ["MET-004", "MET-003"]}),
    metric("MET-010", "净利率（2025财年）", "Net margin (FY2025)", 11.3, "%", None,
           "FY2025", "2025-12-31", "SRC-001", AR,
           {"formula": "MET-008 / MET-004 * 100", "input_metric_ids": ["MET-008", "MET-004"]}),
    # segments FY2025 / FY2024
    metric("MET-011", "智能装备收入（2025财年）", "Intelligent equipment revenue (FY2025)", 2.71e9, "CNY", "CNY", "FY2025", "2025-12-31", "SRC-001", AR),
    metric("MET-012", "自动化部件收入（2025财年）", "Automation components revenue (FY2025)", 1.36e9, "CNY", "CNY", "FY2025", "2025-12-31", "SRC-001", AR),
    metric("MET-013", "服务收入（2025财年）", "Services revenue (FY2025)", 0.45e9, "CNY", "CNY", "FY2025", "2025-12-31", "SRC-001", AR),
    metric("MET-032", "智能装备收入（2024财年）", "Intelligent equipment revenue (FY2024)", 2.33e9, "CNY", "CNY", "FY2024", "2024-12-31", "SRC-001", AR),
    metric("MET-033", "自动化部件收入（2024财年）", "Automation components revenue (FY2024)", 1.05e9, "CNY", "CNY", "FY2024", "2024-12-31", "SRC-001", AR),
    metric("MET-034", "服务收入（2024财年）", "Services revenue (FY2024)", 0.38e9, "CNY", "CNY", "FY2024", "2024-12-31", "SRC-001", AR),
    # prices and valuation
    metric("MET-014", "收盘价", "Closing price", 28.40, "CNY/share", "CNY", "PIT", AS_OF, "SRC-002", "provider://mockdata/quote/600XXX?as_of=2026-07-10"),
    metric("MET-015", "目标价（基准情景）", "Target price (base case)", 34.00, "CNY/share", "CNY", "PIT", AS_OF, "SRC-001", MODEL + "/dcf-base",
           {"formula": "DCF base case per-share value (WACC per ASM-001)", "input_metric_ids": ["MET-004", "MET-008"]}),
    metric("MET-016", "DCF估值下限", "DCF valuation low", 29.50, "CNY/share", "CNY", "PIT", AS_OF, "SRC-001", MODEL + "/dcf-range",
           {"formula": "DCF sensitivity lower bound", "input_metric_ids": ["MET-004", "MET-008"]}),
    metric("MET-017", "DCF估值上限", "DCF valuation high", 38.00, "CNY/share", "CNY", "PIT", AS_OF, "SRC-001", MODEL + "/dcf-range",
           {"formula": "DCF sensitivity upper bound", "input_metric_ids": ["MET-004", "MET-008"]}),
    metric("MET-018", "可比公司PE估值下限", "Peer PE valuation low", 27.00, "CNY/share", "CNY", "PIT", AS_OF, "SRC-005", MODEL + "/pe-comps",
           {"formula": "peer PE 25th percentile x FY2025 EPS", "input_metric_ids": ["MET-008"]}),
    metric("MET-019", "可比公司PE估值上限", "Peer PE valuation high", 35.50, "CNY/share", "CNY", "PIT", AS_OF, "SRC-005", MODEL + "/pe-comps",
           {"formula": "peer PE 75th percentile x FY2025 EPS", "input_metric_ids": ["MET-008"]}),
    # FY2026E revenue bridge (internal model, deterministic)
    metric("MET-020", "销量贡献（2026财年预测）", "Volume contribution (FY2026E)", 0.45e9, "CNY", "CNY", "2026H1", "2026-07-10", "SRC-001", MODEL + "/bridge",
           {"formula": "volume-driven revenue delta", "input_metric_ids": ["MET-004"]}),
    metric("MET-021", "价格贡献（2026财年预测）", "Price contribution (FY2026E)", 0.18e9, "CNY", "CNY", "2026H1", "2026-07-10", "SRC-001", MODEL + "/bridge",
           {"formula": "price/mix revenue delta", "input_metric_ids": ["MET-004"]}),
    metric("MET-022", "客户流失影响（2026财年预测）", "Churn impact (FY2026E)", -0.12e9, "CNY", "CNY", "2026H1", "2026-07-10", "SRC-001", MODEL + "/bridge",
           {"formula": "churn revenue delta", "input_metric_ids": ["MET-004"]}),
    metric("MET-023", "营业收入（2026财年预测）", "Revenue (FY2026E)", 5.03e9, "CNY", "CNY", "2026H1", "2026-07-10", "SRC-001", MODEL + "/bridge",
           {"formula": "MET-004 + MET-020 + MET-021 + MET-022", "input_metric_ids": ["MET-004", "MET-020", "MET-021", "MET-022"]}),
    # comparable-company table (fictional peers)
    metric("MET-024", "市盈率（公司）", "PE (company)", 18.2, "x", None, "PIT", AS_OF, "SRC-005", COMPS),
    metric("MET-025", "市盈率（同业A）", "PE (Peer A)", 22.5, "x", None, "PIT", AS_OF, "SRC-005", COMPS),
    metric("MET-026", "市盈率（同业B）", "PE (Peer B)", 15.8, "x", None, "PIT", AS_OF, "SRC-005", COMPS),
    metric("MET-027", "市销率（公司）", "PS (company)", 2.1, "x", None, "PIT", AS_OF, "SRC-005", COMPS),
    metric("MET-028", "市销率（同业A）", "PS (Peer A)", 2.8, "x", None, "PIT", AS_OF, "SRC-005", COMPS),
    metric("MET-029", "市销率（同业B）", "PS (Peer B)", 1.6, "x", None, "PIT", AS_OF, "SRC-005", COMPS),
    metric("MET-030", "收入增速（同业A）", "Revenue growth (Peer A)", 12.5, "%", None, "FY2025", "2025-12-31", "SRC-005", COMPS),
    metric("MET-031", "收入增速（同业B）", "Revenue growth (Peer B)", 8.9, "%", None, "FY2025", "2025-12-31", "SRC-005", COMPS),
]

CLAIMS = [
    ("CLM-001", "fact",
     "公司2025财年营业收入与归母净利润均实现两位数增长，收入创历史新高。",
     "FY2025 revenue and net profit both grew at double-digit rates, with revenue at a record high.",
     {"source_ids": ["SRC-001"], "metric_ids": ["MET-004", "MET-008", "MET-009"], "confidence": 0.98}),
    ("CLM-002", "fact",
     "产业指导意见（虚构）提出支持智能制造装备国产替代。",
     "The (fictional) industry guidance supports domestic substitution in intelligent manufacturing equipment.",
     {"source_ids": ["SRC-003"], "confidence": 0.95}),
    ("CLM-003", "inference",
     "在政策支持和收入高增长背景下，公司有望继续扩大国内市场份额。",
     "With policy support and strong revenue growth, the company is likely to keep gaining domestic share.",
     {"based_on_claim_ids": ["CLM-001", "CLM-002"], "confidence": 0.7}),
    ("CLM-004", "opinion",
     "我们认为公司是国产替代的主要受益者之一，给予“增持”评级。",
     "We view the company as a key beneficiary of domestic substitution and assign an Accumulate rating.",
     {"based_on_claim_ids": ["CLM-003"], "confidence": 0.6}),
    ("CLM-005", "inference",
     "行业产能扩张较快，若下游资本开支放缓，公司增速可能明显低于我们的预测。",
     "Industry capacity is expanding quickly; if downstream capex slows, growth could fall well short of our forecast.",
     {"source_ids": ["SRC-004"], "confidence": 0.6, "is_counterevidence": True}),
    ("CLM-006", "inference",
     "同业价格竞争加剧可能压缩毛利率。",
     "Intensifying price competition among peers may compress gross margin.",
     {"source_ids": ["SRC-004"], "confidence": 0.65}),
    ("CLM-007", "inference",
     "产业政策方向若调整，相关补贴和订单支持可能减弱。",
     "A shift in industrial policy direction could weaken subsidy and order support.",
     {"based_on_claim_ids": ["CLM-002"], "confidence": 0.5}),
    ("CLM-008", "fact",
     "公司前五大客户收入占比较高（2025年年报，虚构数据）。",
     "Revenue concentration among the top five customers is high (FY2025 annual report, fictional data).",
     {"source_ids": ["SRC-001"], "confidence": 0.95}),
    ("CLM-009", "inference",
     "基准情景假设2026-2028年收入复合增速15%，对应DCF每股价值34.0元。",
     "Our base case assumes a 15% revenue CAGR over 2026-2028, implying a DCF value of CNY 34.0 per share.",
     {"metric_ids": ["MET-015"], "confidence": 0.6}),
    ("CLM-010", "inference",
     "WACC取9.5%，反映A股工业自动化板块的股权成本与公司较低的杠杆水平。",
     "We apply a 9.5% WACC, reflecting A-share industrial-automation equity costs and the company's low leverage.",
     {"source_ids": ["SRC-004"], "confidence": 0.6}),
    ("CLM-011", "inference",
     "公司计划于2026年四季度发布新一代控制系统，如期落地有望带来新订单。",
     "The company plans to launch its next-generation control system in Q4 2026; an on-time launch could drive new orders.",
     {"source_ids": ["SRC-001"], "confidence": 0.55}),
    ("CLM-012", "fact",
     "智能装备是最大收入分部，服务收入占比仍然较低（虚构数据）。",
     "Intelligent equipment is the largest segment while services remain a small share of revenue (fictional data).",
     {"source_ids": ["SRC-001"], "metric_ids": ["MET-011", "MET-012", "MET-013"], "confidence": 0.95}),
    ("CLM-013", "inference",
     "销量扩张是2026财年预测收入增长的主要驱动，价格贡献为正但幅度有限。",
     "Volume expansion drives the FY2026E revenue bridge, with a positive but modest price contribution.",
     {"metric_ids": ["MET-020", "MET-021", "MET-022", "MET-023"], "confidence": 0.6}),
    ("CLM-014", "inference",
     "公司估值低于同业A、高于同业B，增速溢价尚未完全反映在市盈率中。",
     "The company trades below Peer A and above Peer B; its growth premium is not fully reflected in the PE multiple.",
     {"metric_ids": ["MET-024", "MET-025", "MET-026"], "source_ids": ["SRC-005"], "confidence": 0.6}),
    ("CLM-015", "fact",
     "公司于2016年成立，2021年上市，2024年设立海外制造基地（虚构沿革）。",
     "The company was founded in 2016, listed in 2021 and opened an overseas manufacturing base in 2024 (fictional history).",
     {"source_ids": ["SRC-001"], "confidence": 0.95}),
    ("CLM-016", "fact",
     "公司位于产业链中游的自动化设备制造环节，上游为核心零部件，下游为制造业客户。",
     "The company operates midstream in automation-equipment manufacturing, with core components upstream and manufacturing customers downstream.",
     {"source_ids": ["SRC-001"], "confidence": 0.9}),
]


def build_package() -> dict:
    claims = []
    for cid, ctype, zh, en, extra in CLAIMS:
        c = {"claim_id": cid, "type": ctype, "text": lt(zh, en),
             "review_status": "verified", **extra}
        claims.append(c)
    return {
        "schema_version": "0.1.0",
        "package_id": "RPK-600XXX-2026-002",
        "status": "verified",
        "as_of_date": AS_OF,
        "created_at": "2026-07-17T10:00:00+10:00",
        "company": {
            "name": lt("示例智能制造股份有限公司", "Example Intelligent Manufacturing Co., Ltd."),
            "ticker": "600XXX", "exchange": "MOCK", "market": "CN-A",
            "reporting_currency": "CNY",
            "sector": lt("工业自动化设备", "Industrial automation equipment"),
            "is_mock": True,
            "market_specific": {"cn": {
                "industry_classification_sw": "机械设备-自动化设备",
                "share_classes": ["A"], "state_owned": False,
                "display_unit_convention": "亿元",
                "policy_context_claim_ids": ["CLM-002"],
            }},
        },
        "sources": SOURCES,
        "metrics": METRICS,
        "claims": claims,
        "sections": [
            {"section_id": "cover", "title": lt("封面", "Cover"), "claim_ids": []},
            {"section_id": "investment_thesis", "title": lt("投资摘要", "Investment thesis"),
             "claim_ids": ["CLM-004", "CLM-003", "CLM-005"],
             "key_metric_ids": ["MET-004", "MET-009", "MET-014", "MET-015"]},
            {"section_id": "company_snapshot", "title": lt("公司概览", "Company snapshot"),
             "claim_ids": ["CLM-001", "CLM-015"], "key_metric_ids": ["MET-004", "MET-008", "MET-010"]},
            {"section_id": "industry_value_chain", "title": lt("行业与产业链", "Industry and value chain"),
             "claim_ids": ["CLM-002", "CLM-016"]},
            {"section_id": "business_model_segments", "title": lt("商业模式与业务分部", "Business model and segments"),
             "claim_ids": ["CLM-012", "CLM-008"], "key_metric_ids": ["MET-011", "MET-012", "MET-013"]},
            {"section_id": "competition_moat", "title": lt("竞争格局与护城河", "Competition and moat"),
             "claim_ids": ["CLM-006", "CLM-014"]},
            {"section_id": "historical_financials", "title": lt("历史财务", "Historical financials"),
             "claim_ids": ["CLM-001"], "key_metric_ids": ["MET-001", "MET-002", "MET-003", "MET-004"]},
            {"section_id": "forecast_drivers", "title": lt("预测驱动", "Forecast drivers"),
             "claim_ids": ["CLM-013"], "key_metric_ids": ["MET-020", "MET-021", "MET-022", "MET-023"]},
            {"section_id": "valuation", "title": lt("估值", "Valuation"),
             "claim_ids": ["CLM-009", "CLM-010", "CLM-014"],
             "key_metric_ids": ["MET-015", "MET-016", "MET-017", "MET-018", "MET-019"]},
            {"section_id": "catalysts", "title": lt("催化剂", "Catalysts"), "claim_ids": ["CLM-011"]},
            {"section_id": "risks", "title": lt("风险", "Risks"),
             "claim_ids": ["CLM-005", "CLM-006", "CLM-007", "CLM-008"]},
            {"section_id": "conclusion_sources_disclaimer",
             "title": lt("结论、来源与免责声明", "Conclusion, sources and disclaimer"),
             "claim_ids": ["CLM-004", "CLM-005"]},
        ],
        "valuation": {
            "methods": [
                {"method": "dcf", "label": lt("现金流折现", "Discounted cash flow"),
                 "low": "MET-016", "high": "MET-017", "assumption_ids": ["ASM-001", "ASM-002"]},
                {"method": "pe_comps", "label": lt("可比公司PE", "Peer PE multiples"),
                 "low": "MET-018", "high": "MET-019"},
            ],
            "assumptions": [
                {"assumption_id": "ASM-001",
                 "name": lt("加权平均资本成本", "Weighted average cost of capital"),
                 "value_text": "WACC 9.5%", "rationale_claim_id": "CLM-010"},
                {"assumption_id": "ASM-002",
                 "name": lt("收入复合增速（2026-2028）", "Revenue CAGR (2026-2028)"),
                 "value_text": "revenue CAGR 15% (2026-2028)", "rationale_claim_id": "CLM-009"},
            ],
            "scenarios": {"base": {"narrative_claim_id": "CLM-009",
                                   "target_price_metric_id": "MET-015", "probability": 0.6}},
            "target_price_metric_id": "MET-015",
            "current_price_metric_id": "MET-014",
            "rating": "accumulate",
            "counterevidence_claim_ids": ["CLM-005"],
        },
        "catalysts": [
            {"catalyst_id": "CAT-001", "title": lt("新一代控制系统发布", "Next-generation control system launch"),
             "claim_id": "CLM-011", "timeframe": "3-12m", "expected_date": "2026-11-30",
             "direction": "positive"},
        ],
        "risks": [
            {"risk_id": "RSK-001", "title": lt("下游资本开支放缓", "Slowing downstream capital expenditure"),
             "claim_id": "CLM-005", "category": "industry", "severity": "high", "likelihood": "medium"},
            {"risk_id": "RSK-002", "title": lt("价格竞争压缩毛利率", "Price competition compressing margins"),
             "claim_id": "CLM-006", "category": "competition", "severity": "medium", "likelihood": "high"},
            {"risk_id": "RSK-003", "title": lt("产业政策变化", "Industrial policy shifts"),
             "claim_id": "CLM-007", "category": "policy_regulation", "severity": "medium", "likelihood": "low"},
            {"risk_id": "RSK-004", "title": lt("客户集中度较高", "High customer concentration"),
             "claim_id": "CLM-008", "category": "operations", "severity": "medium", "likelihood": "medium"},
        ],
        "quality": {
            "rubric_version": "0.1.0",
            "checks": [{"check_id": f"QC-{i:02d}", "result": "pass",
                        "details": "presentation fixture"} for i in range(1, 11)] +
                      [{"check_id": "QC-11", "result": "not_run",
                        "details": "overflow checked at render time by the template QA pass"}],
            "overall": "acceptable",
        },
        "disclaimer": {
            "text": lt("本报告由蓝楹会基于公开信息与AI辅助流程生成，仅供学习与研究用途，不构成任何投资建议。数据截至2026年7月10日。本样例使用虚构公司数据。",
                       "Produced by the Jacaranda Stock Market Society using public information and an AI-assisted workflow, for educational and research purposes only; not investment advice. Data as of 10 July 2026. This sample uses fictional company data."),
            "version": "0.1.0",
        },
        "generation_metadata": {
            "pipeline_version": "presentation-fixture",
            "llm_calls": [{"task": "fixture_only", "requested_model": "openrouter/free",
                           "returned_model": "n/a (handwritten fixture)"}],
            "notes": "Deterministic presentation fixture; all company data fictional.",
        },
    }


# ------------------------------------------------------------------- decks --

def footer(no: int, sources: list[str], page_no: bool = True) -> dict:
    return {"show_page_number": page_no, "data_as_of": AS_OF, "source_ids": sources,
            "show_disclaimer_ref": True}


def T(zh: str, en: str, lang: str) -> str:
    return zh if lang == "zh" else en


def sample_deck(lang: str) -> dict:
    z = lang == "zh"

    def t(zh_s, en_s):
        return zh_s if z else en_s

    money = "yi" if z else "billion"
    money_dec = 1 if z else 2
    unit_cny = t("单位：亿元人民币", "CNY bn")

    slides = []

    slides.append({
        "slide_no": 1, "layout": "L01_cover", "section_id": "cover",
        "title": t("示例智能制造（600XXX）研究报告",
                   "Example Intelligent Manufacturing (600XXX) equity research"),
        "kicker": t("国产替代进程中的自动化设备供应商",
                    "An automation-equipment supplier in the domestic-substitution cycle"),
        "blocks": [{"block_type": "cover_meta", "priority": 1, "cover_meta": {
            "company_line": t("示例智能制造股份有限公司 · 600XXX · 虚构示例",
                              "Example Intelligent Manufacturing Co., Ltd. · 600XXX · fictional example"),
            "rating_line": t("评级：增持 · 目标价：34.00元", "Rating: Accumulate · Target price: CNY 34.00"),
            "date_line": t("2026年7月17日", "17 Jul 2026"),
            "edition_line": t("中文完整版", "Full English edition"),
            "prepared_by": "Jacaranda Stock Market Society"}}],
        "footer": footer(1, [], page_no=False)})

    slides.append({
        "slide_no": 2, "layout": "L03_kpi_snapshot", "section_id": "investment_thesis",
        "title": t("投资摘要", "Investment thesis"),
        "blocks": [
            {"block_type": "kpi_cards", "priority": 1, "kpi_cards": [
                {"label": t("营业收入（亿元）", "Revenue (CNY bn)"), "number": dn("MET-004", money, money_dec),
                 "period_caption": t("2025财年", "FY2025")},
                {"label": t("收入增速", "Revenue growth"), "number": dn("MET-009", "percent", 1, sign=True),
                 "period_caption": t("2025财年，同比", "FY2025, YoY")},
                {"label": t("现价（元）", "Current price (CNY)"), "number": dn("MET-014", "raw", 2),
                 "period_caption": t("2026-07-10收盘", "Close, 10 Jul 2026")},
                {"label": t("目标价（元）", "Target price (CNY)"), "number": dn("MET-015", "raw", 2),
                 "period_caption": t("基准情景", "Base case")}]},
            {"block_type": "bullets", "priority": 2, "bullets": [
                {"text": t("政策支持叠加收入高增长，公司有望继续扩大国内市场份额。",
                           "Policy support and strong revenue growth position the company to keep gaining domestic share."),
                 "refs": [{"claim_id": "CLM-003"}], "claim_type": "inference"},
                {"text": t("我们认为公司是国产替代的主要受益者之一，给予“增持”评级。",
                           "We view the company as a key beneficiary of domestic substitution and assign an Accumulate rating."),
                 "refs": [{"claim_id": "CLM-004"}], "claim_type": "opinion"},
                {"text": t("反方观点：若下游资本开支放缓，增速可能明显低于预测。",
                           "Counterargument: growth could fall well short of forecast if downstream capex slows."),
                 "refs": [{"claim_id": "CLM-005"}], "claim_type": "inference"}]}],
        "footer": footer(2, ["SRC-001", "SRC-002", "SRC-004"])})

    slides.append({
        "slide_no": 3, "layout": "L03_kpi_snapshot", "section_id": "company_snapshot",
        "title": t("公司概览", "Company snapshot"),
        "blocks": [
            {"block_type": "kpi_cards", "priority": 1, "kpi_cards": [
                {"label": t("营业收入（亿元）", "Revenue (CNY bn)"), "number": dn("MET-004", money, money_dec),
                 "period_caption": t("2025财年", "FY2025")},
                {"label": t("归母净利润（亿元）", "Net profit (CNY bn)"), "number": dn("MET-008", money, money_dec),
                 "period_caption": t("2025财年", "FY2025")},
                {"label": t("净利率", "Net margin"), "number": dn("MET-010", "percent", 1),
                 "period_caption": t("2025财年", "FY2025")},
                {"label": t("最大分部收入（亿元）", "Largest segment (CNY bn)"), "number": dn("MET-011", money, money_dec),
                 "period_caption": t("智能装备，2025财年", "Intelligent equipment, FY2025")}]},
            {"block_type": "bullets", "priority": 2, "bullets": [
                {"text": t("收入与利润均实现两位数增长，收入创历史新高。",
                           "Revenue and profit both grew at double-digit rates, with revenue at a record high."),
                 "refs": [{"claim_id": "CLM-001"}], "claim_type": "fact"},
                {"text": t("公司位于产业链中游的自动化设备制造环节。",
                           "The company operates midstream in automation-equipment manufacturing."),
                 "refs": [{"claim_id": "CLM-016"}], "claim_type": "fact"}]}],
        "footer": footer(3, ["SRC-001"])})

    slides.append({
        "slide_no": 4, "layout": "L08_timeline", "section_id": "company_snapshot",
        "title": t("公司沿革", "Company history"),
        "blocks": [{"block_type": "timeline", "priority": 1, "timeline": [
            {"date": "2016", "label": t("公司成立", "Founded"),
             "description": t("聚焦工业自动化设备", "Focused on industrial automation equipment"),
             "refs": [{"claim_id": "CLM-015"}]},
            {"date": "2021", "label": t("上市", "Listed"),
             "description": t("登陆虚构交易所", "Listed on a fictional exchange"),
             "refs": [{"claim_id": "CLM-015"}]},
            {"date": "2024", "label": t("海外基地", "Overseas base"),
             "description": t("设立海外制造基地", "Opened an overseas manufacturing base"),
             "refs": [{"claim_id": "CLM-015"}]},
            {"date": "2026-11", "label": t("新控制系统", "New control system"),
             "description": t("计划发布新一代控制系统", "Next-generation control system planned"),
             "refs": [{"claim_id": "CLM-011"}], "is_future": True}]}],
        "footer": footer(4, ["SRC-001"])})

    slides.append({
        "slide_no": 5, "layout": "L07_value_chain", "section_id": "industry_value_chain",
        "title": t("产业链定位", "Value-chain position"),
        "blocks": [
            {"block_type": "flow", "priority": 1, "flow": [
                {"node_name": t("上游", "Upstream"),
                 "description": t("核心零部件与材料", "Core components and materials")},
                {"node_name": t("中游（公司）", "Midstream (company)"),
                 "description": t("自动化设备制造", "Automation-equipment manufacturing"),
                 "highlight": True},
                {"node_name": t("下游", "Downstream"),
                 "description": t("制造业客户", "Manufacturing customers")}]},
            {"block_type": "bullets", "priority": 2, "bullets": [
                {"text": t("产业指导意见支持智能制造装备国产替代。",
                           "Industry guidance supports domestic substitution in intelligent manufacturing equipment."),
                 "refs": [{"claim_id": "CLM-002"}], "claim_type": "fact"},
                {"text": t("政策若落地执行，有望改善公司所处中游环节的订单环境。",
                           "If implemented, the policy could improve midstream order conditions."),
                 "refs": [{"claim_id": "CLM-003"}], "claim_type": "inference"}]}],
        "footer": footer(5, ["SRC-001", "SRC-003"])})

    slides.append({
        "slide_no": 6, "layout": "L04_chart_commentary", "section_id": "business_model_segments",
        "title": t("业务分部结构", "Segment mix"),
        "blocks": [
            {"block_type": "chart", "priority": 1, "chart": {
                "chart_type": "stacked_bar",
                "title": t("分部收入（2024-2025财年）", "Segment revenue (FY2024-FY2025)"),
                "x_labels": ["FY2024", "FY2025"],
                "series": [
                    {"name": t("智能装备", "Intelligent equipment"),
                     "metric_ids": ["MET-032", "MET-011"], "display_transform": money},
                    {"name": t("自动化部件", "Automation components"),
                     "metric_ids": ["MET-033", "MET-012"], "display_transform": money},
                    {"name": t("服务", "Services"),
                     "metric_ids": ["MET-034", "MET-013"], "display_transform": money}],
                "unit_caption": unit_cny, "source_ids": ["SRC-001"]}},
            {"block_type": "bullets", "priority": 2, "bullets": [
                {"text": t("智能装备是最大收入分部，服务收入占比仍然较低。",
                           "Intelligent equipment is the largest segment; services remain a small share."),
                 "refs": [{"claim_id": "CLM-012"}], "claim_type": "fact"}]}],
        "footer": footer(6, ["SRC-001"])})

    slides.append({
        "slide_no": 7, "layout": "L06_comparison_cards", "section_id": "competition_moat",
        "title": t("竞争格局", "Competitive landscape"),
        "blocks": [{"block_type": "comparison_cards", "priority": 1, "comparison_cards": [
            {"entity_name": t("公司", "Company"),
             "numbers": [{"label": "PE", "number": dn("MET-024", "multiple", 1)},
                         {"label": t("收入增速", "Revenue growth"), "number": dn("MET-009", "percent", 1)}],
             "bullets": [{"text": t("增长快于同业，双位数收入增速。",
                                    "Faster growth than peers, with double-digit revenue growth."),
                          "refs": [{"claim_id": "CLM-001"}]}], "limited_data": False},
            {"entity_name": t("同业A（虚构）", "Peer A (fictional)"),
             "numbers": [{"label": "PE", "number": dn("MET-025", "multiple", 1)},
                         {"label": t("收入增速", "Revenue growth"), "number": dn("MET-030", "percent", 1)}],
             "bullets": [{"text": t("估值溢价较高。", "Trades at a premium multiple."),
                          "refs": [{"claim_id": "CLM-014"}]}], "limited_data": False},
            {"entity_name": t("同业B（虚构）", "Peer B (fictional)"),
             "numbers": [{"label": "PE", "number": dn("MET-026", "multiple", 1)},
                         {"label": t("收入增速", "Revenue growth"), "number": dn("MET-031", "percent", 1)}],
             "bullets": [{"text": t("增速与估值均低于公司。", "Slower growth and a lower multiple than the company."),
                          "refs": [{"claim_id": "CLM-014"}]}], "limited_data": False}]}],
        "footer": footer(7, ["SRC-005"])})

    slides.append({
        "slide_no": 8, "layout": "L05_financial_table", "section_id": "historical_financials",
        "title": t("历史财务", "Historical financials"),
        "blocks": [{"block_type": "table", "priority": 1, "table": {
            "columns": [t("指标", "Metric"), "FY2022", "FY2023", "FY2024", "FY2025"],
            "rows": [
                {"label": t("营业收入", "Revenue"),
                 "cells": [dn("MET-001", money, money_dec), dn("MET-002", money, money_dec),
                           dn("MET-003", money, money_dec), dn("MET-004", money, money_dec)]},
                {"label": t("归母净利润", "Net profit"),
                 "cells": [dn("MET-005", money, money_dec), dn("MET-006", money, money_dec),
                           dn("MET-007", money, money_dec), dn("MET-008", money, money_dec)]},
                {"label": t("收入同比增速", "Revenue growth"),
                 "cells": [None, None, None, dn("MET-009", "percent", 1, sign=True)]},
                {"label": t("净利率", "Net margin"),
                 "cells": [None, None, None, dn("MET-010", "percent", 1)]}],
            "unit_caption": unit_cny, "source_ids": ["SRC-001"]}}],
        "footer": footer(8, ["SRC-001"])})

    slides.append({
        "slide_no": 9, "layout": "L04_chart_commentary", "section_id": "historical_financials",
        "title": t("收入与利润趋势", "Revenue and profit trend"),
        "blocks": [
            {"block_type": "chart", "priority": 1, "chart": {
                "chart_type": "line",
                "title": t("营业收入与归母净利润（2022-2025财年）", "Revenue and net profit (FY2022-FY2025)"),
                "x_labels": ["FY2022", "FY2023", "FY2024", "FY2025"],
                "series": [
                    {"name": t("营业收入", "Revenue"),
                     "metric_ids": ["MET-001", "MET-002", "MET-003", "MET-004"],
                     "display_transform": money},
                    {"name": t("归母净利润", "Net profit"),
                     "metric_ids": ["MET-005", "MET-006", "MET-007", "MET-008"],
                     "display_transform": money}],
                "unit_caption": unit_cny, "source_ids": ["SRC-001"]}},
            {"block_type": "bullets", "priority": 2, "bullets": [
                {"text": t("收入与利润均保持逐年增长，增速在2025财年有所加快。",
                           "Revenue and profit have grown every year, with growth accelerating in FY2025."),
                 "refs": [{"claim_id": "CLM-001"}], "claim_type": "fact"}]}],
        "footer": footer(9, ["SRC-001"])})

    slides.append({
        "slide_no": 10, "layout": "L04_chart_commentary", "section_id": "forecast_drivers",
        "title": t("预测收入桥（2026财年）", "FY2026E revenue bridge"),
        "blocks": [
            {"block_type": "chart", "priority": 1, "chart": {
                "chart_type": "waterfall",
                "title": t("2026财年预测收入桥", "FY2026E revenue bridge"),
                "x_labels": [t("2025收入", "FY2025"), t("销量", "Volume"), t("价格", "Price"),
                             t("流失", "Churn"), t("2026E收入", "FY2026E")],
                "series": [{"name": t("收入桥", "Bridge"),
                            "metric_ids": ["MET-004", "MET-020", "MET-021", "MET-022", "MET-023"],
                            "display_transform": money}],
                "unit_caption": unit_cny, "source_ids": ["SRC-001"]}},
            {"block_type": "bullets", "priority": 2, "bullets": [
                {"text": t("销量扩张是预测增长的主要驱动，价格贡献为正但幅度有限。",
                           "Volume expansion drives forecast growth, with a positive but modest price contribution."),
                 "refs": [{"claim_id": "CLM-013"}], "claim_type": "inference"}]}],
        "footer": footer(10, ["SRC-001"])})

    slides.append({
        "slide_no": 11, "layout": "L05_financial_table", "section_id": "valuation",
        "title": t("可比公司", "Comparable companies"),
        "blocks": [
            {"block_type": "table", "priority": 1, "table": {
                "columns": [t("指标", "Metric"), t("公司", "Company"), t("同业A", "Peer A"),
                            t("同业B", "Peer B")],
                "rows": [
                    {"label": "PE", "cells": [dn("MET-024", "multiple", 1),
                                              dn("MET-025", "multiple", 1),
                                              dn("MET-026", "multiple", 1)]},
                    {"label": "PS", "cells": [dn("MET-027", "multiple", 1),
                                              dn("MET-028", "multiple", 1),
                                              dn("MET-029", "multiple", 1)]},
                    {"label": t("收入增速", "Revenue growth"),
                     "cells": [dn("MET-009", "percent", 1), dn("MET-030", "percent", 1),
                               dn("MET-031", "percent", 1)]}],
                "unit_caption": t("倍数为虚构数据", "Multiples are fictional"),
                "source_ids": ["SRC-005"]}},
            {"block_type": "bullets", "priority": 2, "bullets": [
                {"text": t("公司估值低于同业A、高于同业B，增速溢价尚未完全反映。",
                           "The company trades below Peer A and above Peer B; the growth premium is not fully priced."),
                 "refs": [{"claim_id": "CLM-014"}], "claim_type": "inference"}]}],
        "footer": footer(11, ["SRC-005"])})

    slides.append({
        "slide_no": 12, "layout": "L09_football_field", "section_id": "valuation",
        "title": t("估值区间与目标价", "Valuation range and target price"),
        "blocks": [{"block_type": "football_field", "priority": 1, "football_field": {
            "bars": [
                {"label": t("现金流折现", "Discounted cash flow"),
                 "low": dn("MET-016", "raw", 1), "high": dn("MET-017", "raw", 1)},
                {"label": t("可比公司PE", "Peer PE multiples"),
                 "low": dn("MET-018", "raw", 1), "high": dn("MET-019", "raw", 1)}],
            "current_price": dn("MET-014", "raw", 2),
            "target_price": dn("MET-015", "raw", 2),
            "assumption_lines": [
                {"text": t("WACC取9.5%，反映板块股权成本与公司低杠杆。",
                           "9.5% WACC, reflecting sector equity costs and low leverage."),
                 "refs": [{"assumption_id": "ASM-001"}, {"claim_id": "CLM-010"}]},
                {"text": t("基准情景：2026-2028年收入复合增速15%。",
                           "Base case: 15% revenue CAGR over 2026-2028."),
                 "refs": [{"claim_id": "CLM-009"}, {"assumption_id": "ASM-002"}]}],
            "source_ids": ["SRC-001", "SRC-005"]}}],
        "footer": footer(12, ["SRC-001", "SRC-005"])})

    slides.append({
        "slide_no": 13, "layout": "L10_catalysts_risks", "section_id": "risks",
        "title": t("催化剂与风险", "Catalysts and risks"),
        "blocks": [{"block_type": "paired_columns", "priority": 1, "paired_columns": {
            "left_title": t("催化剂", "Catalysts"),
            "right_title": t("风险", "Risks"),
            "left_items": [
                {"title": t("新一代控制系统发布", "Next-generation control system launch"),
                 "description": t("预计四季度发布，如期落地有望带来新订单。",
                                  "Planned for Q4; an on-time launch could drive new orders."),
                 "chip": "3-12m", "refs": [{"claim_id": "CLM-011"}]}],
            "right_items": [
                {"title": t("下游资本开支放缓", "Slowing downstream capex"),
                 "chip": "S:high L:medium", "refs": [{"claim_id": "CLM-005"}]},
                {"title": t("价格竞争压缩毛利率", "Price competition compressing margins"),
                 "chip": "S:medium L:high", "refs": [{"claim_id": "CLM-006"}]},
                {"title": t("产业政策变化", "Industrial policy shifts"),
                 "chip": "S:medium L:low", "refs": [{"claim_id": "CLM-007"}]},
                {"title": t("客户集中度较高", "High customer concentration"),
                 "chip": "S:medium L:medium", "refs": [{"claim_id": "CLM-008"}]}]}}],
        "footer": footer(13, ["SRC-001", "SRC-003", "SRC-004"])})

    slides.append({
        "slide_no": 14, "layout": "L11_conclusion_sources",
        "section_id": "conclusion_sources_disclaimer",
        "title": t("结论、来源与免责声明", "Conclusion, sources and disclaimer"),
        "blocks": [
            {"block_type": "text_panel", "priority": 1, "text_panel": {
                "text": t("我们给予“增持”评级，目标价34.00元。反方证据：行业产能扩张较快，若下游资本开支放缓，公司增速可能明显低于预测。",
                          "We assign an Accumulate rating with a CNY 34.00 target price. Counterevidence: industry capacity is expanding quickly, and growth could fall well short of forecast if downstream capex slows."),
                "refs": [{"claim_id": "CLM-004"}, {"claim_id": "CLM-005"}, {"metric_id": "MET-015"}],
                "style": "conclusion"}},
            {"block_type": "source_table", "priority": 1, "source_table": [
                {"source_id": s["source_id"], "title": s["title"], "publisher": s["publisher"],
                 "published_date": s.get("published_date", "—"),
                 "retrieved_at": RETR[:10]} for s in SOURCES]},
            {"block_type": "text_panel", "priority": 1, "text_panel": {
                "text": t("本报告由蓝楹会基于公开信息与AI辅助流程生成，仅供学习与研究用途，不构成任何投资建议。数据截至2026年7月10日。本样例使用虚构公司数据。",
                          "Produced by the Jacaranda Stock Market Society using public information and an AI-assisted workflow, for educational and research purposes only; not investment advice. Data as of 10 July 2026. This sample uses fictional company data."),
                "refs": [{"claim_id": "CLM-004"}], "style": "disclaimer"}}],
        "footer": {"show_page_number": True, "data_as_of": AS_OF,
                   "source_ids": [s["source_id"] for s in SOURCES],
                   "show_disclaimer_ref": False}})

    return {
        "schema_version": "0.1.0",
        "deck_id": f"DCK-600XXX-2026-002-{'ZH' if z else 'EN'}",
        "package_id": "RPK-600XXX-2026-002",
        "edition": "zh-CN" if z else "en-AU",
        "as_of_date": AS_OF,
        "theme": "jacaranda-brand",
        "slides": slides,
    }


def all_layouts_deck() -> dict:
    """zh-CN demo deck: every layout family at least once (adds L02 + donut demo)."""
    base = sample_deck("zh")
    divider = {
        "slide_no": 2, "layout": "L02_section_divider", "section_id": "investment_thesis",
        "title": "投资摘要", "kicker": "评级、目标价与核心逻辑",
        "blocks": [{"block_type": "text_panel", "priority": 9, "text_panel": {
            "text": "本节展示投资结论与关键指标。",
            "refs": [{"claim_id": "CLM-004"}], "style": "note"}}],
        "footer": {"show_page_number": True, "data_as_of": AS_OF, "source_ids": [],
                   "show_disclaimer_ref": True}}
    donut = {
        "slide_no": 3, "layout": "L04_chart_commentary", "section_id": "business_model_segments",
        "title": "收入构成（2025财年）",
        "blocks": [
            {"block_type": "chart", "priority": 1, "chart": {
                "chart_type": "donut", "title": "分部收入构成（2025财年）",
                "x_labels": ["智能装备", "自动化部件", "服务"],
                "series": [{"name": "收入构成",
                            "metric_ids": ["MET-011", "MET-012", "MET-013"],
                            "display_transform": "yi"}],
                "unit_caption": "单位：亿元人民币", "source_ids": ["SRC-001"]}},
            {"block_type": "bullets", "priority": 2, "bullets": [
                {"text": "智能装备是最大收入分部，服务收入占比仍然较低。",
                 "refs": [{"claim_id": "CLM-012"}], "claim_type": "fact"}]}],
        "footer": footer(3, ["SRC-001"])}
    slides = [base["slides"][0], divider, donut] + base["slides"][1:]
    for i, s in enumerate(slides, start=1):
        s = dict(s)
        s["slide_no"] = i
        slides[i - 1] = s
    return {**base, "deck_id": "DCK-600XXX-2026-002-TEMPLATE", "slides": slides}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pkg = build_package()
    (OUT / "mock-package.json").write_text(
        json.dumps(pkg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, deck in [("deck-sample.zh-CN.json", sample_deck("zh")),
                       ("deck-sample.en-AU.json", sample_deck("en")),
                       ("deck-all-layouts.zh-CN.json", all_layouts_deck())]:
        (OUT / name).write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
    print("fixtures written to", OUT)


if __name__ == "__main__":
    main()
