"""Bounded paper-library searches; indexing state is separate from source status."""

from typing import Literal
from unicodedata import category

from pydantic import ConfigDict, Field, field_validator

from ragagent.domain.privacy import SensitiveInput


class PaperSearchQuery(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=1000)
    author: str | None = Field(default=None, min_length=1, max_length=256)
    year: int | None = Field(default=None, ge=1000, le=2100)
    venue: str | None = Field(default=None, min_length=1, max_length=256)
    status: Literal["queued", "parsing", "indexing", "indexed", "failed"] | None = None
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
