"""Report fields reference claims; they never supply independent scientific prose."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ReportFieldName = Literal[
    "method", "dataset", "participants", "conditions", "metric", "result", "unit", "split"
]

FIELD_LABELS: dict[ReportFieldName, str] = {
    "method": "方法",
    "dataset": "数据集",
    "participants": "受试者",
    "conditions": "实验条件",
    "metric": "指标",
    "result": "结果",
    "unit": "单位",
    "split": "数据划分",
}


class ReportField(BaseModel):
    state: Literal["reported", "explicit_not_reported", "evidence_insufficient"] = (
        "evidence_insufficient"
    )
    claim_ids: list[str] = Field(default_factory=list, max_length=96)
    # Optional exact source literal used only for conservative difference detection.
    source_literal: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def supported_field(self) -> "ReportField":
        if len(set(self.claim_ids)) != len(self.claim_ids):
            raise ValueError("duplicate_report_claim")
        if self.state == "evidence_insufficient":
            if self.claim_ids or self.source_literal is not None:
                raise ValueError("insufficient_field_cannot_supply_facts")
        elif not self.claim_ids:
            raise ValueError("reported_field_requires_claims")
        if self.state == "explicit_not_reported" and self.source_literal is None:
            raise ValueError("explicit_absence_requires_source_literal")
        return self


class StudyObservation(BaseModel):
    """One source's experiment; several rows may belong to the same paper."""

    row_id: str = Field(min_length=1, max_length=200)
    paper_id: str
    fields: dict[ReportFieldName, ReportField] = Field(default_factory=dict)


class ReportCell(ReportField):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class ReportRow(BaseModel):
    row_id: str
    paper_id: str
    fields: dict[ReportFieldName, ReportCell]


class ReportSection(BaseModel):
    key: str
    title: str
    claim_ids: list[str] = Field(default_factory=list)


class StructuredReport(BaseModel):
    schema_version: Literal[1] = 1
    research_question: str
    paper_ids: list[str]
    sections: list[ReportSection]
    rows: list[ReportRow]
    comparability: list[str]
    # Always conditional: matching strings do not establish experimental equivalence.
    comparison_status: Literal["not_directly_comparable"] = "not_directly_comparable"
    evidence_ids: list[str]
    markdown: str
