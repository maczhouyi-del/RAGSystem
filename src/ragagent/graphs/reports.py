"""Deterministic synthesis of already reviewed facts, with no extra model call."""

import html
import re
from collections.abc import Sequence

from ragagent.domain.reports import (
    FIELD_LABELS,
    ReportCell,
    ReportField,
    ReportFieldName,
    ReportRow,
    ReportSection,
    StructuredReport,
    StudyObservation,
)
from ragagent.domain.research import CitationValidation, Claim, EvidenceRecord
from ragagent.retrieval.evidence import exact_span, render_claims


def display(value: str) -> str:
    """Escape untrusted Markdown while retaining source numbers and Unicode."""
    return re.sub(r"([\\`*_{}\[\]()#+.!|>-])", r"\\\1", html.escape(value)).replace("\n", " ")


def binding_errors(
    observations: list[StudyObservation], claims: list[Claim], evidence: list[EvidenceRecord]
) -> list[str]:
    by_claim = {c.claim_id: c for c in claims}
    by_evidence = {e.evidence_id: e for e in evidence if exact_span(e)}
    papers = {
        by_evidence[eid].paper.paper_id
        for c in claims
        for eid in c.evidence_ids
        if eid in by_evidence
    }
    errors: list[str] = []
    seen: set[str] = set()
    for row in observations:
        if row.row_id in seen or row.paper_id not in papers:
            errors.append("report_unknown_paper_or_duplicate_row")
        seen.add(row.row_id)
        for field in row.fields.values():
            sources = []
            for cid in field.claim_ids:
                claim = by_claim.get(cid)
                if claim is None:
                    errors.append("report_unknown_claim")
                    continue
                for eid in claim.evidence_ids:
                    item = by_evidence.get(eid)
                    if item is None or item.paper.paper_id != row.paper_id:
                        errors.append("report_cross_source_or_invalid_evidence")
                    else:
                        sources.append(item)
            if field.source_literal is not None and not any(
                field.source_literal in item.quote for item in sources
            ):
                errors.append("report_literal_not_in_cited_quote")
    return list(dict.fromkeys(errors))


def synthesize_report(
    question: str,
    claims: list[Claim],
    evidence: list[EvidenceRecord],
    validation: CitationValidation,
    observations: list[StudyObservation],
    categories: dict[str, Sequence[Claim]],
) -> StructuredReport:
    supported = {v.claim_id for v in validation.verdicts if v.supported and not v.contradiction}
    pairs = {(p.claim_id, p.evidence_id) for p in validation.supported_pairs}
    if (
        not validation.valid
        or (bool(observations) and not validation.report_bindings_verified)
        or not claims
        or len({c.claim_id for c in claims}) != len(claims)
        or any(
            c.claim_id not in supported or any((c.claim_id, e) not in pairs for e in c.evidence_ids)
            for c in claims
        )
        or binding_errors(observations, claims, evidence)
    ):
        raise ValueError("report_requires_verified_claims_and_bindings")
    by_claim = {c.claim_id: c for c in claims}
    cited_ids = list(dict.fromkeys(e for c in claims for e in c.evidence_ids))
    used = [e for e in evidence if e.evidence_id in cited_ids]
    papers = {e.paper.paper_id: e.paper for e in used}
    # Every cited paper appears even if the Analyst omitted its experiment rows.
    # These explicit gaps never infer columns from prose or original omission.
    represented = {row.paper_id for row in observations}
    row_ids = {row.row_id for row in observations}
    observations = list(observations)
    for pid in papers:
        if pid not in represented:
            row_id = f"unbound-{pid}"
            while row_id in row_ids:
                row_id += "-gap"
            row_ids.add(row_id)
            observations.append(StudyObservation(row_id=row_id, paper_id=pid))
    rows: list[ReportRow] = []
    for observation in observations:
        cells = {}
        for name in FIELD_LABELS:
            field = observation.fields.get(name, ReportField())
            selected = [by_claim[cid] for cid in field.claim_ids]
            text = render_claims(selected)
            if field.state == "explicit_not_reported":
                text = "原文明确未报告：" + text
            elif field.state == "evidence_insufficient":
                text = "证据不足（系统未检索到可验证字段，不代表原文未报告）"
            cells[name] = ReportCell(
                **field.model_dump(),
                text=text,
                evidence_ids=list(dict.fromkeys(e for c in selected for e in c.evidence_ids)),
            )
        rows.append(
            ReportRow(row_id=observation.row_id, paper_id=observation.paper_id, fields=cells)
        )

    limitations = [
        "结果不可直接作公平排名：未进行单位换算，数值和来源论断保持原样。",
        "相同字段或文字不能证明实验等价；需研究人员核查任务、指标定义与完整设置。",
        "范围仅包含本次引用的检索证据，不代表系统综述或原文全文已穷尽。",
    ]
    comparison_fields: tuple[ReportFieldName, ...] = (
        "dataset",
        "metric",
        "unit",
        "split",
        "conditions",
    )
    for name in comparison_fields:
        fields = [row.fields[name] for row in rows]
        if any(f.state != "reported" or f.source_literal is None for f in fields):
            limitations.append(f"{FIELD_LABELS[name]}：缺少完整可验证字段，无法确认可比性。")
        literals = {
            f.source_literal
            for f in fields
            if f.state == "reported" and f.source_literal is not None
        }
        if len(literals) > 1:
            limitations.append(
                f"{FIELD_LABELS[name]}：原文字段不同，不可无条件比较；差异保留在比较表中。"
            )

    section_specs = [
        ("question", "研究问题"),
        ("scope", "文献范围"),
        ("methods", "研究方法与分类"),
        ("datasets", "数据集和受试者"),
        ("conditions", "实验条件"),
        ("results", "结果对比"),
        ("findings", "发现与争议"),
        ("comparability", "实验可比性限制"),
        ("gaps", "证据缺口"),
        ("references", "参考来源"),
    ]
    assigned: set[str] = set()
    sections: list[ReportSection] = []
    field_sections: dict[str, tuple[ReportFieldName, ...]] = {
        "methods": ("method",),
        "datasets": ("dataset", "participants"),
        "conditions": ("conditions", "unit", "split"),
        "results": ("result", "metric"),
    }
    aspect_sections = {
        "methods": {"method", "methods", "方法"},
        "datasets": {"dataset", "datasets", "participants", "population", "数据集", "受试者"},
        "conditions": {"conditions", "unit", "split", "实验条件", "单位", "数据划分"},
        "results": {"metric", "metrics", "result", "results", "指标", "结果"},
    }
    # Explicit Analyst categories are reviewed Claims, never free-form labels.
    for key, title in section_specs:
        selected = list(categories.get(key, []))
        selected += [c for c in claims if c.aspect in aspect_sections.get(key, set())]
        for row in rows:
            for field_name in field_sections.get(key, ()):
                selected += [by_claim[cid] for cid in row.fields[field_name].claim_ids]
        if key == "findings":
            selected += [c for c in claims if c.claim_id not in assigned]
        ids = list(dict.fromkeys(c.claim_id for c in selected))
        assigned.update(ids)
        sections.append(ReportSection(key=key, title=title, claim_ids=ids))
    parts = ["# Research report"]
    for section in sections:
        parts.append(f"## {section.title}")
        if section.key == "question":
            parts.append("研究意图（用户问题，不作事实证据）：" + display(question))
        elif section.key == "scope":
            parts.append("本次已引用来源（文献元数据；不代表完整文献覆盖）：")
            parts.extend("- " + display(p.title) for p in papers.values())
        elif section.key == "results":
            parts.append("逐来源实验字段；数值不换算、不排序，各条件分别保留。")
            table_lines = [
                "| 来源 | " + " | ".join(FIELD_LABELS.values()) + " |",
                "| " + " | ".join(["---"] * (1 + len(FIELD_LABELS))) + " |",
            ]
            for row in rows:
                # Escape table separators/newlines in factual text; citations stay clickable.
                table_cells = [
                    re.sub(r"\s+", " ", row.fields[n].text).replace("|", "\\|")
                    for n in FIELD_LABELS
                ]
                table_lines.append(
                    "| "
                    + display(papers[row.paper_id].title)
                    + " | "
                    + " | ".join(table_cells)
                    + " |"
                )
            parts.append("\n".join(table_lines))
        elif section.key == "comparability":
            parts.extend("- " + note for note in limitations)
        elif section.key == "gaps":
            parts.extend(
                "- "
                + display(papers[row.paper_id].title)
                + " / "
                + FIELD_LABELS[name]
                + "："
                + row.fields[name].text
                for row in rows
                for name in FIELD_LABELS
                if row.fields[name].state != "reported"
            )
            if all(f.state == "reported" for row in rows for f in row.fields.values()):
                parts.append("所列字段已关联证据；检索以外是否存在证据缺口尚未评估。")
        elif section.key == "references":
            for item in used:
                page = (
                    f"p.{item.page_start}–{item.page_end}"
                    if item.page_location == "available"
                    else "页码未知"
                )
                parts.append(
                    f"- {display(item.paper.title)} · {display(item.section_path)} · {page} "
                    f"[E:{item.evidence_id}]"
                )
        if section.claim_ids:
            if section.key == "findings":
                parts.append("逐项保留发现和有引用支持的争议；不合并为无证据的共识结论。")
            parts.append(render_claims([by_claim[cid] for cid in section.claim_ids]))
        elif section.key in ("methods", "datasets", "conditions", "findings"):
            parts.append("证据不足：本次未取得该章节的已验证事实，不代表原文未报告。")
    markdown = "\n\n".join(parts)
    return StructuredReport(
        research_question=question,
        paper_ids=list(papers),
        sections=sections,
        rows=rows,
        comparability=limitations,
        evidence_ids=cited_ids,
        markdown=markdown,
    )
