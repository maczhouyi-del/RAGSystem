from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from ragagent.domain.documents import Element, ParsedDocument
from ragagent.domain.locations import PdfBox, PdfRegion, PdfUnavailableReason
from ragagent.errors import ParsingError


class Parser(Protocol):
    def parse(self, path: Path) -> ParsedDocument: ...


def pdf_regions(document: Any, item: Any, text: str, label: str, source_id: str) -> list[PdfRegion]:
    result = []
    provenance_items = getattr(item, "prov", None)
    provenance_items = provenance_items if isinstance(provenance_items, (list, tuple)) else []
    for provenance in provenance_items:
        page_no = getattr(provenance, "page_no", None)
        if type(page_no) is not int or page_no < 1:
            continue
        raw_span = getattr(provenance, "charspan", None)
        charspan: tuple[int, int] | None = (
            (raw_span[0], raw_span[1])
            if isinstance(raw_span, (list, tuple))
            and len(raw_span) == 2
            and all(type(n) is int and n >= 0 for n in raw_span)
            else None
        )
        mapped = (
            charspan is not None
            and 0 <= charspan[0] < charspan[1] <= len(text)
            and label != "table"
            and getattr(item, "orig", text) == text
        )
        box = getattr(provenance, "bbox", None)
        pages = getattr(document, "pages", None)
        page = pages.get(page_no) if isinstance(pages, dict) else None
        size = getattr(page, "size", None)
        bbox = None
        reason: PdfUnavailableReason = (
            "not_provided"
            if box is None
            else "missing_page_geometry"
            if size is None
            else "invalid_parser_region"
        )
        if box is not None and size is not None:
            origin = getattr(box, "coord_origin", None)
            origin = getattr(origin, "value", origin)
            try:
                if origin not in {"TOPLEFT", "BOTTOMLEFT"}:
                    raise ValueError("unknown_pdf_coordinate_origin")
                valid_origin: Literal["TOPLEFT", "BOTTOMLEFT"] = (
                    "TOPLEFT" if origin == "TOPLEFT" else "BOTTOMLEFT"
                )
                bbox = PdfBox(
                    left=box.l,
                    top=box.t,
                    right=box.r,
                    bottom=box.b,
                    page_width=size.width,
                    page_height=size.height,
                    coord_origin=valid_origin,
                )
            except (ValueError, AttributeError, TypeError):
                pass  # Optional geometry never makes the original text unusable.
        result.append(
            PdfRegion(
                source_id=source_id,
                page_no=page_no,
                bbox=bbox,
                parser_charspan=charspan,
                source_start=charspan[0] if mapped and charspan is not None else None,
                source_end=charspan[1] if mapped and charspan is not None else None,
                unavailable_reason=None if bbox else reason,
            )
        )
    return result or [PdfRegion(source_id=source_id)]


@dataclass(frozen=True)
class DoclingParser:
    # Explicit model-free validation/fallback option; standard layout parsing stays default.
    native_pdf: bool = False

    def parse(self, path: Path) -> ParsedDocument:
        # Lazy import: core tests do not install or download layout/OCR models.
        try:
            from docling.document_converter import DocumentConverter

            if self.native_pdf:
                from docling.datamodel.base_models import InputFormat
                from docling.document_converter import NativePdfFormatOption

                converter = DocumentConverter(
                    format_options={InputFormat.PDF: NativePdfFormatOption()}
                )
            else:
                converter = DocumentConverter()
            document = converter.convert(path).document
            elements: list[Element] = []
            headings: list[str] = []
            section_ids: list[str] = []
            heading_ordinal = 0
            for item, _level in document.iterate_items(traverse_pictures=True):
                label = str(getattr(item.label, "value", item.label))
                if label == "section_header":
                    depth = max(1, int(getattr(item, "level", 1)))
                    headings = headings[: depth - 1] + [item.text]
                    section_ids = section_ids[: depth - 1] + [f"heading:{heading_ordinal}"]
                    heading_ordinal += 1
                if label == "table":
                    text = item.export_to_markdown(doc=document)
                else:
                    text = getattr(item, "text", "")
                if not text.strip():
                    continue
                source_id = getattr(item, "self_ref", None) or f"element:{len(elements)}"
                regions = pdf_regions(document, item, text, label, source_id)
                pages = [region.page_no for region in regions if region.page_no is not None]
                elements.append(
                    Element(
                        section_path=headings or ["Preamble"],
                        section_ids=section_ids or ["preamble"],
                        page_start=min(pages) if pages else 1,
                        page_end=max(pages) if pages else 1,
                        page_location="available" if pages else "unavailable",
                        pdf_regions=regions,
                        element_type=label,
                        content=text,
                        source_id=source_id,
                        related_source_ids=[
                            ref.cref
                            for ref in getattr(item, "captions", [])
                            if hasattr(ref, "cref")
                        ],
                    )
                )
            if not elements:
                raise ParsingError("no_parseable_elements")
            return ParsedDocument(title=path.stem, elements=elements)
        except ParsingError:
            raise
        except Exception as exc:
            raise ParsingError("docling_conversion_failed") from exc
