from __future__ import annotations

from typing import cast

from jacaranda_api.pipeline.models import JsonDict

SECTION_TITLES: tuple[tuple[str, str, str], ...] = (
    ("cover", "封面", "Cover"),
    ("investment_thesis", "投资摘要", "Investment thesis"),
    ("company_snapshot", "公司概览", "Company snapshot"),
    ("industry_value_chain", "行业与产业链", "Industry and value chain"),
    ("business_model_segments", "商业模式与业务分部", "Business model and segments"),
    ("competition_moat", "竞争格局与护城河", "Competition and moat"),
    ("historical_financials", "历史财务", "Historical financials"),
    ("forecast_drivers", "预测驱动", "Forecast drivers"),
    ("valuation", "估值", "Valuation"),
    ("catalysts", "催化剂", "Catalysts"),
    ("risks", "风险", "Risks"),
    ("conclusion_sources_disclaimer", "结论、来源与免责声明", "Conclusion, sources and disclaimer"),
)

SECTION_IDS = tuple(section_id for section_id, _, _ in SECTION_TITLES)


def build_evidence_chunks(evidence: JsonDict) -> list[JsonDict]:
    """Deterministic zh renderings of the evidence pack, one chunk per source.

    S1's anti-hallucination anchor requires every extracted candidate to quote a
    verbatim substring of a chunk, so the chunk text is authored by code from the
    already-provenanced provider data — never by a model.
    """
    sources = {source["source_id"]: source for source in evidence["sources"]}
    lines_by_source: dict[str, list[str]] = {source_id: [] for source_id in sources}

    company = evidence["company"]
    profile_source_id = company["source_id"]
    profile_lines = lines_by_source[profile_source_id]
    profile_lines.append(f"公司名称：{company['name_zh']}。")
    if company.get("name_en"):
        profile_lines.append(f"英文名称：{company['name_en']}。")
    if company.get("industry"):
        profile_lines.append(f"所属行业：{company['industry']}。")
    if company.get("listing_date"):
        profile_lines.append(f"上市日期：{company['listing_date']}。")

    for metric in evidence["metrics"]:
        unit = metric["unit"]
        period = metric["period"]
        value = metric["value"]
        name_zh = metric["name"]["zh_CN"]
        lines_by_source[metric["source_id"]].append(
            f"{name_zh}（{period}，截至{metric['as_of_date']}）：{value} {unit}。"
        )

    chunks: list[JsonDict] = []
    for source_id, lines in lines_by_source.items():
        if not lines:
            continue
        source = sources[source_id]
        chunks.append(
            {
                "source_id": source_id,
                "type": source["type"],
                "locator": source.get("locator", source_id),
                "published_date": source.get("published_date"),
                "retrieved_at": source["retrieved_at"],
                "url_or_document": source["url_or_document"],
                "language": source.get("language", "zh"),
                "text": "\n".join(lines),
            }
        )
    return chunks


def map_verified_candidates(
    s1: JsonDict, s2: JsonDict, *, next_claim_number: int
) -> tuple[list[JsonDict], int, list[str]]:
    """Assembler-owned CCLM→CLM promotion: verified candidate claims become
    package fact claims with sequential ids; everything else is dropped or held.

    Candidate metrics are NOT promoted here — provider metrics already exist in
    canonical form, so S1 metric candidates only corroborate them.
    """
    verdicts = {item["candidate_id"]: item["verdict"] for item in s2["verdicts"]}
    claims: list[JsonDict] = []
    held: list[str] = []
    number = next_claim_number
    for candidate in s1["candidate_claims"]:
        verdict = verdicts.get(candidate["candidate_id"], "needs_review")
        if verdict == "rejected":
            continue
        if verdict == "needs_review":
            held.append(candidate["candidate_id"])
            continue
        claims.append(
            {
                "claim_id": f"CLM-{number:03d}",
                "type": "fact",
                "text": {
                    "zh_CN": candidate["text_original_language"],
                    "en_AU": candidate["text_original_language"],
                },
                "review_status": "verified",
                "source_ids": list(candidate["source_ids"]),
            }
        )
        number += 1
    return claims, number, held


def build_sections(
    *,
    section_assignments: dict[str, list[str]],
    fact_claim_ids: list[str],
    rating_claim_id: str,
    counterevidence_claim_ids: list[str],
    scenario_claim_ids: list[str],
    catalyst_claim_ids: list[str],
    risk_claim_ids: list[str],
    key_metric_ids: dict[str, list[str]],
) -> list[JsonDict]:
    """The 12 canonical sections in report order, populated from stage outputs."""
    assigned: dict[str, list[str]] = {section_id: [] for section_id in SECTION_IDS}
    for section_id, claim_ids in section_assignments.items():
        if section_id in assigned:
            _extend_unique(assigned[section_id], claim_ids)

    _extend_unique(assigned["company_snapshot"], fact_claim_ids)
    _extend_unique(assigned["investment_thesis"], [rating_claim_id])
    _extend_unique(assigned["investment_thesis"], counterevidence_claim_ids)
    _extend_unique(assigned["valuation"], scenario_claim_ids)
    _extend_unique(assigned["catalysts"], catalyst_claim_ids)
    _extend_unique(assigned["risks"], risk_claim_ids)
    _extend_unique(assigned["risks"], counterevidence_claim_ids)
    _extend_unique(
        assigned["conclusion_sources_disclaimer"],
        [rating_claim_id, *counterevidence_claim_ids],
    )

    sections: list[JsonDict] = []
    for section_id, title_zh, title_en in SECTION_TITLES:
        section: JsonDict = {
            "section_id": section_id,
            "title": {"zh_CN": title_zh, "en_AU": title_en},
            "claim_ids": assigned[section_id],
        }
        metric_ids = key_metric_ids.get(section_id)
        if metric_ids:
            section["key_metric_ids"] = metric_ids
        sections.append(section)
    return sections


def _extend_unique(target: list[str], items: list[str]) -> None:
    for item in items:
        if item not in target:
            target.append(item)


def build_disclaimer(as_of_date: str) -> JsonDict:
    return {
        "text": {
            "zh_CN": (
                "本报告由蓝楹会基于公开信息与AI辅助流程生成，仅供学习与研究用途，"
                f"不构成任何投资建议。数据截至{as_of_date}。发布前需经人工审核确认。"
            ),
            "en_AU": (
                "Produced by the Jacaranda Stock Market Society using public information "
                "and an AI-assisted workflow, for educational and research purposes only; "
                f"not investment advice. Data as of {as_of_date}. "
                "Human review is required before publication."
            ),
        },
        "version": "0.1.0",
    }


def build_company_block(evidence: JsonDict) -> JsonDict:
    company = evidence["company"]
    symbol = evidence["symbol"]
    name_en = company.get("name_en") or company["name_zh"]
    block: JsonDict = {
        "name": {"zh_CN": company["name_zh"], "en_AU": name_en},
        "ticker": symbol["canonical"],
        "exchange": symbol["exchange"],
        "market": symbol["market"],
        "reporting_currency": "CNY",
        "is_mock": False,
    }
    if company.get("listing_date"):
        block["listing_date"] = company["listing_date"]
    if company.get("industry"):
        block["sector"] = {"zh_CN": company["industry"], "en_AU": company["industry"]}
    return block


def collect_section_assignments(s3_outputs: dict[str, JsonDict]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for output in s3_outputs.values():
        assignment = cast(dict[str, list[str]], output.get("section_assignment", {}))
        for section_id, claim_ids in assignment.items():
            _extend_unique(merged.setdefault(section_id, []), claim_ids)
    return merged
