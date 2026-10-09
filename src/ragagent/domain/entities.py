"""Source-grounded proposals and explicit human review; not scientific facts."""

from typing import Literal
from unicodedata import category

from pydantic import ConfigDict, Field, StrictBool, field_validator, model_validator

from ragagent.domain.privacy import SensitiveInput

EntityKind = Literal["dataset", "method", "metric"]


class EntityProposal(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=256)
    entity_type: EntityKind
    span_start: int = Field(ge=0)
    span_end: int = Field(ge=1)
    alias_group: str | None = None

    @field_validator("name")
    @classmethod
    def visible_source_name(cls, value: str) -> str:
        if value != value.strip() or any(category(c) == "Cc" for c in value):
            raise ValueError("entity_name_invalid")
        return value

    @model_validator(mode="after")
    def ordered_span(self) -> "EntityProposal":
        if self.span_end <= self.span_start:
            raise ValueError("invalid_entity_span")
        return self


class AnnotationStart(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    engine: Literal["source-labels-v1"]
    acknowledge_candidates_require_review: StrictBool

    @field_validator("acknowledge_candidates_require_review")
    @classmethod
    def acknowledgment(cls, value: bool) -> bool:
        if not value:
            raise ValueError("candidate_review_acknowledgment_required")
        return value


class MentionCreate(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    entity_type: EntityKind
    span_start: int = Field(ge=0)
    span_end: int = Field(ge=1)
    expected_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def ordered_span(self) -> "MentionCreate":
        if self.span_end <= self.span_start:
            raise ValueError("invalid_entity_span")
        return self


class MentionPatch(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    action: Literal["confirm", "reject", "correct"]
    expected_version: int = Field(ge=1)
    expected_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entity_type: EntityKind | None = None
    span_start: int | None = Field(default=None, ge=0)
    span_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def explicit_action(self) -> "MentionPatch":
        supplied = (self.entity_type, self.span_start, self.span_end)
        if self.action == "correct":
            if any(value is None for value in supplied):
                raise ValueError("entity_correction_requires_source_span_and_type")
            if self.span_end is None or self.span_start is None or self.span_end <= self.span_start:
                raise ValueError("invalid_entity_span")
        elif any(value is not None for value in supplied):
            raise ValueError("unexpected_entity_correction")
        return self


class ChunkReview(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    expected_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    acknowledge_all_three_types_reviewed: StrictBool

    @field_validator("acknowledge_all_three_types_reviewed")
    @classmethod
    def acknowledgment(cls, value: bool) -> bool:
        if not value:
            raise ValueError("complete_review_acknowledgment_required")
        return value


class MentionListQuery(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=1000000)
    chunk_id: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )


class MentionResponse(SensitiveInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    chunk_id: str
    name: str
    entity_type: EntityKind
    span_start: int
    span_end: int
    content_sha256: str
    state: Literal["proposed", "confirmed", "rejected"]
    origin: str
    alias_group: str | None
    version: int
    current_source: bool = True


class EntityLinkDelete(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    expected_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    acknowledge_remove_link: StrictBool

    @field_validator("acknowledge_remove_link")
    @classmethod
    def acknowledgment(cls, value: bool) -> bool:
        if not value:
            raise ValueError("entity_link_removal_acknowledgment_required")
        return value
