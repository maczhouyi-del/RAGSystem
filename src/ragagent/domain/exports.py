"""Read-only, bounded exports of persisted research products."""

import csv
import io
import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from ragagent.domain.reports import FIELD_LABELS
from ragagent.domain.research import EvidenceRecord
from ragagent.retrieval.evidence import parse_citations

EXPORT_TYPES = {
    "report.md": "text/markdown",
    "comparison.csv": "text/csv",
    "references.bib": "application/x-bibtex",
    "citations.json": "application/json",
}
MAX_EXPORT_BYTES = 8 * 1024 * 1024
GAP = "证据不足（未取得可验证字段，不代表原文未报告）"


@dataclass(frozen=True)
class Export:
    filename: str
    media_type: str
    content: bytes


def spreadsheet(value: str) -> str:
    """Preserve numeric literals; prevent source strings becoming spreadsheet formulas."""
    stripped = value.lstrip()
    if stripped.startswith(("=", "+", "-", "@")) and not re.fullmatch(
        r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?%?", stripped
    ):
        return "'" + value
    return value


def bibtex(value: str) -> str:
    substitutions = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "%": r"\%",
        "&": r"\&",
        "#": r"\#",
        "_": r"\_",
        "$": r"\$",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(substitutions.get(c, c) for c in " ".join(value.split()))


def _references(result: dict[str, Any], body: str) -> list[dict[str, Any]]:
    sources = result.get("evidence_pool", result.get("reranked_evidence", []))
    parsed: dict[str, tuple[EvidenceRecord, dict[str, Any]]] = {}
    if isinstance(sources, list):
        for raw in sources:
            try:
                item = EvidenceRecord.model_validate(raw)
            except ValidationError:
                continue  # A malformed legacy source is explicitly unresolved below.
            parsed.setdefault(item.evidence_id, (item, raw))
    references: list[dict[str, Any]] = []
    for eid in parse_citations(body):
        found = parsed.get(eid)
        if found is None:
            references.append(
                {
                    "evidence_id": eid,
                    "source_availability": "unknown",
                    "metadata_status": "missing_evidence_record",
                }
            )
            continue
        item, raw = found
        unavailable = raw.get("source_availability") == "unavailable"
        references.append(
            {
                "evidence_id": eid,
                "paper_id": item.paper.paper_id,
                "chunk_id": item.chunk_id,
                "section_id": item.section_id,
                "section_path": item.section_path,
                "page_start": item.page_start if item.page_location == "available" else None,
                "page_end": item.page_end if item.page_location == "available" else None,
                "page_location": item.page_location,
                "span_start": item.span_start,
                "span_end": item.span_end,
                "paper": item.paper.model_dump(),
                "source_availability": "unavailable" if unavailable else "snapshot_only",
                "metadata_status": "snapshot",
            }
        )
    return references


def _claims(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw = list(result.get("claims", [])) if isinstance(result.get("claims"), list) else []
    analyses = result.get("analysis_results", [])
    if not isinstance(analyses, list):
        analyses = []
    for analysis in analyses:
        if isinstance(analysis, dict):
            for key in ("claims", "methods", "datasets", "metrics", "contradictions"):
                if isinstance(analysis.get(key), list):
                    raw.extend(analysis[key])
    return [c for c in raw if isinstance(c, dict)]


def _comparison(
    result: dict[str, Any], references: list[dict[str, Any]], status: str, review: str, body: str
) -> str:
    output = io.StringIO(newline="")
    headers = [
        "paper_id",
        "paper_title",
        "row_id",
        "verification_status",
        "source_availability",
        "comparability",
    ]
    for name in FIELD_LABELS:
        headers += [name, name + "_state", name + "_claim_ids", name + "_evidence_ids"]
    headers += ["claims", "evidence_ids", "legacy_report"]
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\r\n")
    writer.writeheader()
    papers = {r["paper_id"]: r for r in references if "paper_id" in r}
    structured = result.get("structured_report")
    rows = (
        structured.get("rows", []) if isinstance(structured, dict) and status == "completed" else []
    )
    if not isinstance(rows, list):
        rows = []
    rows = [
        r
        for r in rows
        if isinstance(r, dict)
        and isinstance(r.get("paper_id"), str)
        and r.get("paper_id") in papers
    ]
    represented = {r["paper_id"] for r in rows}
    rows += [
        {"paper_id": pid, "row_id": "legacy-source", "fields": {}}
        for pid in papers
        if pid not in represented
    ]
    if not rows:
        papers[""] = {"paper": {"title": "元数据缺失"}, "source_availability": "unknown"}
        rows = [{"paper_id": "", "row_id": "legacy-report", "fields": {}}]
    claims = _claims(result) if status == "completed" else []
    for row in rows:
        pid = row["paper_id"]
        paper = papers[pid]
        eids = [r["evidence_id"] for r in references if not pid or r.get("paper_id") == pid]
        retained_claims = [
            c
            for c in claims
            if isinstance(c.get("evidence_ids"), list)
            and {e for e in c["evidence_ids"] if isinstance(e, str)} & set(eids)
        ]
        value = {
            "paper_id": pid,
            "paper_title": paper["paper"]["title"],
            "row_id": row.get("row_id", ""),
            "verification_status": review,
            "source_availability": paper["source_availability"],
            "comparability": "不可直接比较；单位、划分与完整设置需人工核查",
            "claims": "\n\n".join(
                c.get("text", "") for c in retained_claims if isinstance(c.get("text"), str)
            ),
            "evidence_ids": " ".join(eids),
            "legacy_report": body if not isinstance(structured, dict) else "",
        }
        fields = row.get("fields", {})
        if not isinstance(fields, dict):
            fields = {}
        for name in FIELD_LABELS:
            field = fields.get(name, {})
            if not isinstance(field, dict):
                field = {}
            text = field.get("text")
            state = field.get("state")
            value[name] = text if isinstance(text, str) else GAP
            value[name + "_state"] = (
                state
                if isinstance(state, str)
                and state in {"reported", "explicit_not_reported", "evidence_insufficient"}
                else "evidence_insufficient"
            )
            for key in ("claim_ids", "evidence_ids"):
                ids = field.get(key, [])
                value[name + "_" + key] = (
                    " ".join(i for i in ids if isinstance(i, str)) if isinstance(ids, list) else ""
                )
        writer.writerow({k: spreadsheet(str(v)) for k, v in value.items()})
    return output.getvalue()


def _bibliography(references: list[dict[str, Any]]) -> str:
    groups: dict[str, list[dict[str, Any]]] = {}
    missing = []
    for item in references:
        if "paper_id" in item:
            groups.setdefault(item["paper_id"], []).append(item)
        else:
            missing.append("% Missing source metadata for Evidence ID: " + item["evidence_id"])
    entries = list(missing)
    for index, items in enumerate(groups.values()):
        paper = items[0]["paper"]
        fields = {"title": paper["title"]}
        unknown = ["DOI (not stored)"]
        if paper.get("authors"):
            fields["author"] = " and ".join("{" + bibtex(a) + "}" for a in paper["authors"])
        else:
            unknown.append("authors")
        if isinstance(paper.get("year"), int) and 1000 <= paper["year"] <= 2100:
            fields["year"] = str(paper["year"])
        else:
            unknown.append("year")
        # Venue does not establish a journal/article type. Keep it as a note.
        if paper.get("venue"):
            fields["note"] = "Venue: " + paper["venue"]
        else:
            unknown.append("venue")
        if paper.get("arxiv_id"):
            fields["eprint"] = paper["arxiv_id"]
            fields["archivePrefix"] = "arXiv"
        lines = [
            "% Evidence IDs: " + " ".join(i["evidence_id"] for i in items),
            "% Source availability: " + items[0]["source_availability"],
            "% Metadata missing: " + (", ".join(unknown) or "none of authors/year/venue"),
            f"@misc{{ragagent_{index + 1},",
        ]
        lines += [
            f"  {key} = {{{value if key == 'author' else bibtex(value)}}},"
            for key, value in fields.items()
        ]
        entries.append("\n".join(lines + ["}"]))
    return "\n\n".join(entries) + "\n"


def export_run(
    run_id: str, kind: str, status: str, result: dict[str, Any], filename: str
) -> Export:
    try:
        run_id = str(UUID(run_id))
    except ValueError:
        raise ValueError("export_run_id_invalid") from None
    if filename not in EXPORT_TYPES:
        raise ValueError("export_format_not_supported")
    if kind not in {"research", "rag"} or status not in {"completed", "insufficient_evidence"}:
        raise ValueError("report_not_released")
    body = result.get("draft_report") if kind == "research" else result.get("answer")
    if not isinstance(body, str) or not body:
        raise ValueError("report_not_available")
    unavailable = result.get("source_availability") == "unavailable"
    review_result = result.get("review_result")
    if isinstance(review_result, dict):
        validation = (
            review_result.get("validation") if review_result.get("decision") == "PASS" else None
        )
    else:
        validation = result.get("citation_validation")
    review = (
        "historical_unverifiable"
        if unavailable
        else "verified_at_execution"
        if isinstance(validation, dict)
        and validation.get("valid") is True
        and status == "completed"
        else "refusal"
        if status == "insufficient_evidence"
        else "legacy_review_unknown"
    )
    references = _references(result, body)
    if filename == "report.md":
        content = (
            ("> 来源已删除，历史报告当前不可验证；正文保留供追溯。\n\n" if unavailable else "")
            + body
        ).encode("utf-8")
    elif filename == "comparison.csv":
        content = ("\ufeff" + _comparison(result, references, status, review, body)).encode("utf-8")
    elif filename == "references.bib":
        content = _bibliography(references).encode("utf-8")
    else:
        content = (
            json.dumps(
                {
                    "run_id": run_id,
                    "kind": kind,
                    "status": status,
                    "verification_status": review,
                    "references": references,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    if len(content) > MAX_EXPORT_BYTES:
        raise ValueError("export_too_large")
    return Export(
        filename=f"ragagent-{run_id}-{filename}", media_type=EXPORT_TYPES[filename], content=content
    )
