from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ragagent.domain.papers import OriginalPaperMetadata, PaperIngestionReference, UploadReceipt
from ragagent.domain.privacy import SensitiveInput
from ragagent.domain.research import MetadataFilter, SearchResult
from ragagent.ingestion.arxiv import ARXIV_ID


class QueryRequest(SensitiveInput):
    query: str = Field(min_length=1, max_length=10000)
    filters: MetadataFilter = Field(default_factory=MetadataFilter)


class SearchResponse(SearchResult):
    usage: dict[str, dict[str, Any]]
    usage_scope: Literal["current_request"] = "current_request"


class ResearchRequest(SensitiveInput):
    research_question: str = Field(min_length=1, max_length=10000)
    filters: MetadataFilter = Field(default_factory=MetadataFilter)


class ArxivRequest(BaseModel):
    arxiv_id: str = Field(pattern="^" + ARXIV_ID.pattern + "$")


class RunResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    kind: str
    status: str
    trace_id: str
    error_code: str | None = None
    result: dict[str, Any] | None = None
    created_at: datetime


class UploadRunResponse(RunResponse, UploadReceipt):
    pass


class PaperResponse(PaperIngestionReference):
    id: str
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    arxiv_id: str | None
    arxiv_family_id: str | None = None
    arxiv_version: int | None = None
    source_status: Literal["unknown", "active", "withdrawn", "retracted"] = "unknown"
    status: str
    error_code: str | None
    chunk_count: int
    created_at: datetime | None = None
    original_metadata: OriginalPaperMetadata | None = None
    metadata_version: int = 1
    overridden_fields: list[str] = Field(default_factory=list)


class PaperPage(BaseModel):
    items: list[PaperResponse]
    total: int
    limit: int
    offset: int


class EntityAnnotation(SensitiveInput):
    name: str = Field(min_length=1, max_length=256)
    entity_type: str = Field(pattern="^(dataset|method|metric|other)$")


class HealthResult(BaseModel):
    ok: bool


class ProviderTest(BaseModel):
    agent: str = Field(pattern="^(supervisor|retriever|analyst|reviewer)$")


class PaperPatch(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=1000)
    authors: list[str] | None = Field(default=None, max_length=100)
    year: int | None = Field(default=None, ge=1000, le=2100)
    venue: str | None = Field(default=None, max_length=256)
    source_status: Literal["unknown", "active", "withdrawn", "retracted"] | None = None
    expected_metadata_version: int | None = Field(default=None, ge=1)

    @field_validator("title", "venue")
    @classmethod
    def normalize_metadata_text(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value and info.field_name == "title":
            raise ValueError("title_cannot_be_blank")
        return value or None

    @field_validator("authors")
    @classmethod
    def normalize_authors(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        names = list(dict.fromkeys(name.strip() for name in value))
        if any(not name or len(name) > 256 for name in names):
            raise ValueError("invalid_author_name")
        return names
