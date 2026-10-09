"""Source IDs, not prose matching, determine which structured snapshots to redact."""

from dataclasses import dataclass, field
from typing import Any

UNAVAILABLE = "来源已删除；相关历史引用当前不可验证。回答正文保留，不代表来源仍可用。"


@dataclass
class SourceIds:
    papers: set[str] = field(default_factory=set)
    chunks: set[str] = field(default_factory=set)
    evidence: set[str] = field(default_factory=set)

    def intersects(self, other: "SourceIds") -> bool:
        return bool(
            self.papers & other.papers
            or self.chunks & other.chunks
            or self.evidence & other.evidence
        )


def source_ids(value: Any) -> SourceIds:
    result = SourceIds()

    def visit(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, dict):
            for key, child in item.items():
                target = (
                    result.papers
                    if key in {"paper_id", "paper_ids", "relevant_paper_ids"}
                    else result.chunks
                    if key in {"chunk_id", "chunk_ids", "relevant_chunk_ids"}
                    else result.evidence
                    if key in {"evidence_id", "evidence_ids"}
                    else None
                )
                if target is not None:
                    if isinstance(child, str):
                        target.add(child)
                    elif isinstance(child, list):
                        target.update(v for v in child if isinstance(v, str))
                visit(child)

    visit(value)
    return result


def redact(value: Any, deleted: SourceIds) -> Any:
    """Keep historical prose/status/usage; remove attributed source and gold text."""
    if isinstance(value, list):
        return [redact(item, deleted) for item in value]
    if not isinstance(value, dict):
        return value
    direct = {
        key: child
        for key, child in value.items()
        if key
        in {
            "paper_id",
            "paper_ids",
            "relevant_paper_ids",
            "chunk_id",
            "chunk_ids",
            "relevant_chunk_ids",
            "evidence_id",
            "evidence_ids",
            "paper",
        }
    }
    affected = source_ids(direct).intersects(deleted)
    result = {key: redact(child, deleted) for key, child in value.items()}
    if affected:
        for key in ("quote", "content", "expected_answer"):
            if key in result:
                result[key] = ""
        for key in ("source_context", "source_spans", "required_aspects", "numeric_targets"):
            if key in result:
                result[key] = []
        result["source_availability"] = "unavailable"
        result["source_unavailable_reason"] = "source_deleted"
    if source_ids(value).intersects(deleted):
        result["source_availability"] = "unavailable"
        for key in ("citation_validation", "validation"):
            validation = result.get(key)
            if isinstance(validation, dict):
                validation.setdefault("historical_valid", value[key].get("valid"))
                validation["valid"] = False
                validation["source_unavailable_reason"] = "source_deleted"
                if isinstance(validation.get("supported_pairs"), list):
                    validation["supported_pairs"] = [
                        pair
                        for pair in validation["supported_pairs"]
                        if not source_ids(pair).intersects(deleted)
                    ]
                if key == "citation_validation":
                    result.setdefault(
                        "historical_citation_validation_valid", value[key].get("valid")
                    )
        if any(
            key in result
            for key in (
                "answer",
                "draft_report",
                "citation_validation",
                "review_result",
                "citation_refs",
                "evidence",
            )
        ):
            limits = result.get("limitations", [])
            result["limitations"] = (
                list(dict.fromkeys([*limits, UNAVAILABLE]))
                if isinstance(limits, list)
                else [UNAVAILABLE]
            )
    return result
