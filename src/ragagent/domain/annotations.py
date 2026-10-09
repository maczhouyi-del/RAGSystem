"""Annotation coverage is an engineering state, never extraction accuracy."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ragagent.domain.privacy import SensitiveInput
from ragagent.domain.research import MetadataFilter

AnnotationStatus = Literal["unprocessed", "processing", "partial", "completed", "failed"]


def annotation_status(
    total: int, completed: int, active: int, failed: int, linked: int
) -> AnnotationStatus:
    if active:
        return "processing"
    if failed:
        return "failed"
    if total > 0 and completed == total:
        return "completed"
    if completed or linked:
        return "partial"
    return "unprocessed"


class AnnotationPageQuery(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=1000000)


class AnnotationCoverageRequest(MetadataFilter, SensitiveInput):
    model_config = ConfigDict(extra="forbid")


class AnnotationCoverage(BaseModel):
    total_chunks: int
    reviewed_chunks: int
    linked_chunks: int
    active_chunks: int
    failed_chunks: int
    matching_chunks: int
    strict: bool
    complete: bool


class EntityOccurrence(BaseModel):
    entity_id: str
    name: str
    entity_type: str
    chunk_id: str
    section_path: str
    page_start: int
    page_end: int


class PaperAnnotations(BaseModel):
    paper_id: str
    status: AnnotationStatus
    total_chunks: int
    reviewed_chunks: int
    linked_chunks: int
    active_chunks: int
    failed_chunks: int
    items: list[EntityOccurrence]
    total_occurrences: int
    limit: int
    offset: int


class AnnotationSource(BaseModel):
    paper_id: str
    chunk_id: str
    section_id: str
    section_path: str
    page_start: int
    page_end: int
    content: str
