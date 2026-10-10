"""PDF element regions are navigation hints, never character-level claim proof."""

from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    FiniteFloat,
    ValidationError,
    computed_field,
    field_validator,
    model_validator,
)

PageLocation = Literal["available", "unavailable"]
PdfUnavailableReason = Literal["not_provided", "invalid_parser_region", "missing_page_geometry"]


class PdfBox(BaseModel):
    left: FiniteFloat = Field(ge=0)
    top: FiniteFloat = Field(ge=0)
    right: FiniteFloat = Field(gt=0)
    bottom: FiniteFloat = Field(ge=0)
    page_width: FiniteFloat = Field(gt=0)
    page_height: FiniteFloat = Field(gt=0)
    coord_origin: Literal["TOPLEFT", "BOTTOMLEFT"]
    units: Literal["page_units"] = "page_units"

    @model_validator(mode="after")
    def valid_extent(self) -> "PdfBox":
        if not (
            self.left < self.right <= self.page_width
            and max(self.top, self.bottom) <= self.page_height
            and (
                self.top < self.bottom if self.coord_origin == "TOPLEFT" else self.bottom < self.top
            )
        ):
            raise ValueError("invalid_pdf_box")
        return self


class PdfRegion(BaseModel):
    source_id: str
    page_no: int | None = Field(default=None, ge=1)
    bbox: PdfBox | None = None
    # Docling charspan is local to a parsed item, not the PDF byte/text stream.
    parser_charspan: tuple[int, int] | None = None
    # Only populated when Docling text/orig agree and charspan fits Element.content.
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, gt=0)
    scope: Literal["element"] = "element"
    unavailable_reason: (
        Literal["not_provided", "invalid_parser_region", "missing_page_geometry"] | None
    ) = None

    @model_validator(mode="after")
    def valid_mapping(self) -> "PdfRegion":
        if (self.source_start is None) != (self.source_end is None) or (
            self.source_start is not None
            and self.source_end is not None
            and self.source_end <= self.source_start
        ):
            raise ValueError("invalid_region_source_span")
        if self.bbox is not None and self.page_no is None:
            raise ValueError("pdf_box_requires_page")
        if self.bbox is None and self.unavailable_reason is None:
            self.unavailable_reason = "not_provided"
        if self.bbox is not None:
            self.unavailable_reason = None
        return self

    @computed_field  # type: ignore[prop-decorator]  # Pydantic's documented mypy limitation.
    @property
    def status(self) -> Literal["available", "unavailable"]:
        return "available" if self.bbox is not None else "unavailable"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def text_mapping(self) -> Literal["parsed_element", "unavailable"]:
        return "parsed_element" if self.source_start is not None else "unavailable"


class LocatedSource(BaseModel):
    pdf_regions: list[PdfRegion] = Field(default_factory=list)

    @field_validator("page_location", mode="before", check_fields=False)
    @classmethod
    def optional_page(cls, value: Any) -> PageLocation:
        return "available" if value == "available" else "unavailable"

    @field_validator("pdf_regions", mode="before")
    @classmethod
    def optional_geometry(cls, values: Any) -> list[PdfRegion]:
        # Historical JSON or corrupt optional geometry must not suppress valid text.
        if not isinstance(values, list):
            return []
        result = []
        for raw in values:
            try:
                value = PdfRegion.model_validate(raw)
            except (ValidationError, TypeError):
                if not isinstance(raw, dict) or not isinstance(raw.get("source_id"), str):
                    continue
                page = raw.get("page_no")
                value = PdfRegion(
                    source_id=raw["source_id"],
                    page_no=page if type(page) is int and page >= 1 else None,
                    unavailable_reason="invalid_parser_region",
                )
            result.append(value)
        return result

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pdf_location(self) -> Literal["available", "partial", "unavailable"]:
        available = sum(region.bbox is not None for region in self.pdf_regions)
        return (
            "unavailable"
            if not available
            else "available"
            if available == len(self.pdf_regions)
            else "partial"
        )
