"""Human-declared scientific gold and reviews; never certify annotation quality."""

from decimal import Decimal
from typing import Any, Literal

from pydantic import AwareDatetime, ConfigDict, Field, model_validator

from ragagent.domain.privacy import SensitiveInput


class GoldPaper(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    paper_id: str = Field(min_length=1)
    pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arxiv_family_id: str | None = None
    arxiv_version: int | None = Field(default=None, ge=1)
    reviewed_pages: list[int] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def valid_pages(self) -> "GoldPaper":
        if any(page < 1 for page in self.reviewed_pages) or len(set(self.reviewed_pages)) != len(
            self.reviewed_pages
        ):
            raise ValueError("gold_reviewed_pages_invalid")
        if self.arxiv_version is not None and not self.arxiv_family_id:
            raise ValueError("gold_version_requires_family")
        return self


class GoldSource(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    paper: GoldPaper
    chunk_id: str = Field(min_length=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    span_start: int = Field(ge=0)
    span_end: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=20000)

    @model_validator(mode="after")
    def exact_label_shape(self) -> "GoldSource":
        if (
            self.page_end < self.page_start
            or self.span_end - self.span_start != len(self.quote)
            or not self.quote.strip()
        ):
            raise ValueError("gold_source_span_invalid")
        pages = set(self.paper.reviewed_pages)
        if self.page_end - self.page_start + 1 > len(pages) or not all(
            page in pages for page in range(self.page_start, self.page_end + 1)
        ):
            raise ValueError("gold_source_pages_not_reviewed")
        return self


class NumericTarget(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    value: Decimal = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=100)
    conditions: dict[str, str] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def explicit_conditions(self) -> "NumericTarget":
        if (
            not self.name.strip()
            or not self.unit.strip()
            or not all(key.strip() and value.strip() for key, value in self.conditions.items())
        ):
            raise ValueError("numeric_conditions_required")
        return self


class ReviewedPair(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    evidence_id: str


class ManualCaseReview(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    scope: str
    id: str
    observation: dict[str, Any]
    reviewed: bool = False
    reviewed_by: str | None = None
    reviewed_at: AwareDatetime | None = None
    supported_pairs: list[ReviewedPair] = Field(default_factory=list)
    supported_claim_ids: list[str] = Field(default_factory=list)
    numeric_correct: bool | None = None
    refusal_correct: bool | None = None
    notes: str = ""

    @model_validator(mode="after")
    def review_identity(self) -> "ManualCaseReview":
        if self.reviewed and (
            not self.reviewed_by or not self.reviewed_by.strip() or self.reviewed_at is None
        ):
            raise ValueError("manual_review_requires_identity_and_time")
        if not self.reviewed and (
            self.supported_pairs
            or self.supported_claim_ids
            or self.numeric_correct is not None
            or self.refusal_correct is not None
        ):
            raise ValueError("unreviewed_case_cannot_supply_verdicts")
        return self


class ManualReview(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: list[ManualCaseReview]
