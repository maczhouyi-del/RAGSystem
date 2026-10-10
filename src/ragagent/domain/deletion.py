"""Explicit current-library removal; independent copies are outside this scope."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator


class PaperDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_paper_id: str = Field(min_length=1, max_length=36)
    expected_metadata_version: StrictInt = Field(ge=1)
    scope: Literal["current_library"]
    acknowledge_retained_copies: Literal[True]

    @field_validator("acknowledge_retained_copies", mode="before")
    @classmethod
    def explicit_acknowledgement(cls, value: object) -> object:
        if value is not True:
            raise ValueError("explicit_acknowledgement_required")
        return value


class CleanupFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["pdf", "parsed", "evaluation"]
    relative_path: str | None
    sha256: str | None = None
    retained_reason: Literal["unmanaged_path", "shared_by_other_paper"] | None = None


class PaperDeletionPreview(BaseModel):
    paper_id: str
    metadata_version: int
    chunks: int
    evidence: int
    pending_imports: int
    scope: Literal["current_library"] = "current_library"
    retained_copies: list[str]


class PaperDeletionResponse(BaseModel):
    paper_id: str
    library_removed: StrictBool = True
    cleanup_run_id: str
    cleanup_status: Literal["queued", "running", "completed", "failed", "cancelled"]
    error_code: str | None
    retained_copies: list[str]
    retained_managed_files: list[str]
