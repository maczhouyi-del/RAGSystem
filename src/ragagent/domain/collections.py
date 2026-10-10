"""User organization labels are retrieval scope, never scientific evidence."""

from typing import Literal
from unicodedata import category, normalize
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ragagent.domain.privacy import SensitiveInput

CollectionKind = Literal["group", "tag"]


def collection_ids(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(UUID(value)) for value in values))


def name_key(name: str) -> str:
    return normalize("NFKC", name).casefold()


class CollectionName(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = normalize("NFC", value.strip())
        if not value or len(value) > 80 or any(category(c) == "Cc" or c == "\ufffd" for c in value):
            raise ValueError("invalid_collection_name")
        return value


class CollectionCreate(CollectionName):
    kind: CollectionKind


class CollectionPatch(CollectionName):
    expected_version: int = Field(ge=1)


class CollectionDelete(SensitiveInput):
    model_config = ConfigDict(extra="forbid")
    confirm_collection_id: UUID
    expected_version: int = Field(ge=1)


class CollectionResponse(BaseModel):
    id: str
    kind: CollectionKind
    name: str
    version: int
    paper_count: int


class CollectionPage(BaseModel):
    items: list[CollectionResponse]
    total: int
    limit: int
    offset: int


class CollectionListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=200, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=1000000)
