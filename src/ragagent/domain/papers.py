"""Bounded paper-library searches; indexing state is separate from source status."""

from typing import Literal
from unicodedata import category
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, field_validator

from ragagent.domain.privacy import SensitiveInput


class UploadReceipt(BaseModel):
    """Source identity and byte-deduplication outcome, separate from indexing completion."""

    paper_id: str
    reused_existing: StrictBool


class PaperIngestionReference(BaseModel):
    """Read-only pointer to the latest existing ingestion Run, not a second job state."""

    latest_ingestion_run_id: str | None = None


class PaperSearchQuery(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=1000)
    author: str | None = Field(default=None, min_length=1, max_length=256)
    year: int | None = Field(default=None, ge=1000, le=2100)
    venue: str | None = Field(default=None, min_length=1, max_length=256)
    status: Literal["queued", "parsing", "indexing", "indexed", "failed"] | None = None
    group: UUID | None = None
    tag: UUID | None = None
    sort: Literal["created_at", "year"] = "created_at"
    direction: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=1000000)

    @field_validator("title", "author", "venue")
    @classmethod
    def nonblank_text(cls, value: str | None) -> str | None:
        if value is not None:
            if any(category(character) == "Cc" or character == "\ufffd" for character in value):
                raise ValueError("invalid_search_text")
            value = value.strip()
            if not value:
                raise ValueError("invalid_search_text")
        return value


class PaperMetadataValues(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    title: str
    authors: list[str]
    year: int | None
    venue: str | None


class OriginalPaperMetadata(SensitiveInput):
    """Captured import fields, never a fabricated original for legacy records."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["upload_user", "arxiv_atom"]
    captured_at: AwareDatetime
    values: PaperMetadataValues
    pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arxiv_id: str | None = None
    arxiv_family_id: str | None = None
    arxiv_version: int | None = None
    source_url: str | None = None
