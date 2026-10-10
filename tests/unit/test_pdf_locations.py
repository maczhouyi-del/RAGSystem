"""SYNTHETIC ONLY: geometry contracts, no model or network calls."""

from types import SimpleNamespace as NS

import pytest
from pydantic import ValidationError

from ragagent.domain.documents import Element, ParsedDocument
from ragagent.domain.locations import LocatedSource, PdfBox, PdfRegion
from ragagent.ingestion.chunker import StructureChunker
from ragagent.ingestion.parser import pdf_regions
from tests.unit.test_parser import parse_items


def box(**updates):
    return {
        "left": 10,
        "top": 20,
        "right": 100,
        "bottom": 40,
        "page_width": 612,
        "page_height": 792,
        "coord_origin": "TOPLEFT",
        **updates,
    }


@pytest.mark.parametrize(
    "updates",
    [
        {"left": -1},
        {"right": 613},
        {"top": 800},
        {"bottom": 10},
        {"page_width": 0},
        {"right": float("nan")},
        {"coord_origin": "UNKNOWN"},
        {"top": 20, "bottom": 40, "coord_origin": "BOTTOMLEFT"},
    ],
)
def test_invalid_pdf_box_is_never_a_valid_position(updates):
    with pytest.raises(ValidationError):
        PdfBox(**box(**updates))


def test_bottom_left_and_top_left_keep_raw_origin_and_page_units():
    for value in [box(), box(top=772, bottom=752, coord_origin="BOTTOMLEFT")]:
        region = PdfRegion(
            source_id="#/texts/0", page_no=1, bbox=PdfBox(**value), source_start=0, source_end=5
        )
        assert region.status == "available" and region.text_mapping == "parsed_element"
        assert region.bbox.model_dump() == {**value, "units": "page_units"}
        assert region.scope == "element"


@pytest.mark.parametrize(
    "raw",
    [
        None,
        42,
        [{"source_id": "#/texts/0", "page_no": 2, "bbox": box(right=1000)}],
        [{"source_id": "#/texts/0", "page_no": 0, "bbox": box()}],
    ],
)
def test_corrupt_optional_geometry_degrades_without_rejecting_source_text(raw):
    element = Element(
        section_path=["DEMO"],
        page_start=2,
        page_end=2,
        element_type="text",
        content="Still valid source text.",
        pdf_regions=raw,
    )
    assert element.content == "Still valid source text." and element.pdf_location == "unavailable"
    assert all(r.bbox is None for r in element.pdf_regions)


@pytest.mark.parametrize("provenance", [[], None, 42])
def test_missing_provenance_preserves_text_but_never_claims_page_one(monkeypatch, provenance):
    parsed = parse_items(
        monkeypatch,
        [
            NS(
                label="text",
                text="Original with no position.",
                self_ref="#/texts/0",
                prov=provenance,
            )
        ],
    )
    assert len(parsed.elements) == 1
    element = parsed.elements[0]
    assert element.page_location == "unavailable" and element.pdf_location == "unavailable"
    assert (
        element.pdf_regions[0].page_no is None and element.content == "Original with no position."
    )
    chunk = StructureChunker().chunk(parsed)[0]
    assert (
        chunk.page_location == "unavailable"
        and chunk.pdf_location == "unavailable"
        and chunk.content == element.content
    )


@pytest.mark.parametrize(
    "change",
    [
        {"charspan": (0, 0)},
        {"charspan": (0, 100)},
        {"orig": "Different serialized source"},
        {"label": "table"},
    ],
)
def test_unreliable_charspan_never_maps_markdown_or_normalized_text(change):
    item = NS(
        label="text",
        text="Exact source",
        orig="Exact source",
        prov=[
            NS(
                page_no=1,
                charspan=change.get("charspan", (0, 12)),
                bbox=NS(l=10, t=20, r=100, b=40, coord_origin="TOPLEFT"),
            )
        ],
    )
    item.orig = change.get("orig", item.orig)
    doc = NS(pages={1: NS(size=NS(width=612, height=792))})
    r = pdf_regions(doc, item, item.text, change.get("label", item.label), "#/texts/0")[0]
    assert r.status == "available" and r.text_mapping == "unavailable" and r.source_start is None


def test_multipage_table_header_caption_and_formula_keep_distinct_sources(monkeypatch):
    def prov(page, start=0, end=0):
        return NS(
            page_no=page,
            charspan=(start, end),
            bbox=NS(l=10, t=20, r=100, b=40, coord_origin="TOPLEFT"),
        )

    table = NS(
        label="table",
        self_ref="#/tables/0",
        captions=[NS(cref="#/texts/0")],
        prov=[prov(2), prov(3)],
        export_to_markdown=lambda doc: (
            "| Method | Score (%) |\n| --- | --- |\n" + "| Alpha | 91.5 |\n" * 8
        ),
    )
    caption = NS(
        label="caption",
        self_ref="#/texts/0",
        text="Table 1 DEMO",
        orig="Table 1 DEMO",
        prov=[prov(2, 0, 12)],
    )
    formula = NS(
        label="formula",
        self_ref="#/texts/1",
        text="L = x + y",
        orig="L = x + y",
        prov=[prov(3, 0, 9)],
    )
    parsed = parse_items(monkeypatch, [caption, table, formula])
    chunks = StructureChunker(target_tokens=20, overlap_tokens=0).chunk(parsed)
    tables = [c for c in chunks if c.element_type == "table"]
    assert len(tables) > 1
    for chunk in tables:
        assert chunk.page_start == 2 and chunk.page_end == 3
        assert {r.page_no for r in chunk.pdf_regions} == {2, 3}
        assert all(r.source_start is None and r.scope == "element" for r in chunk.pdf_regions)
        header, context = chunk.source_context
        assert header.source_id == "#/tables/0" and context.source_id == "#/texts/0"
        assert {r.page_no for r in context.pdf_regions} == {2}
        span = chunk.source_spans[0]
        assert parsed.elements[1].content[span.span_start : span.span_end] == chunk.content
    eq = next(c for c in chunks if c.element_type == "formula")
    assert eq.content == "L = x + y" and eq.source_spans[0].source_id == "#/texts/1"


def test_mixed_mapped_and_unmapped_sources_remain_explicitly_partial():
    doc = ParsedDocument(
        title="DEMO",
        elements=[
            Element(
                source_id="a",
                section_path=["DEMO"],
                page_start=1,
                page_end=1,
                element_type="text",
                content="Known source.",
                pdf_regions=[
                    PdfRegion(
                        source_id="a",
                        page_no=1,
                        bbox=PdfBox(**box()),
                        source_start=0,
                        source_end=13,
                    )
                ],
            ),
            Element(
                source_id="b",
                section_path=["DEMO"],
                page_start=1,
                page_end=1,
                page_location="unavailable",
                element_type="text",
                content="Unknown location.",
            ),
        ],
    )
    chunk = StructureChunker().chunk(doc)[0]
    assert chunk.pdf_location == "partial" and chunk.page_location == "unavailable"
    assert {r.source_id for r in chunk.pdf_regions} == {"a", "b"}


def test_locator_status_cannot_be_forged_by_historical_json():
    value = LocatedSource.model_validate(
        {
            "pdf_location": "available",
            "pdf_regions": [{"source_id": "a", "status": "available", "bbox": None}],
        }
    )
    assert value.pdf_location == "unavailable" and value.pdf_regions[0].status == "unavailable"


def test_deleted_snapshot_clears_primary_and_auxiliary_locations():
    from ragagent.deletion.history import SourceIds, redact

    value = {
        "paper_id": "gone",
        "quote": "PRIVATE SOURCE",
        "pdf_regions": [
            region
            for region in [PdfRegion(source_id="s", page_no=2, bbox=PdfBox(**box())).model_dump()]
        ],
        "pdf_location": "available",
        "page_location": "available",
        "source_context": [{"source_id": "s", "pdf_regions": [{"page_no": 2}]}],
    }
    result = redact(value, SourceIds(papers={"gone"}))
    assert result["quote"] == "" and result["pdf_regions"] == [] and result["source_context"] == []
    assert result["pdf_location"] == "unavailable" and result["page_location"] == "unavailable"
