"""Actual PostgreSQL persistence and retrieval; SYNTHETIC ONLY / NOT A BENCHMARK."""

from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
from sqlalchemy import select

from ragagent.db.models import Chunk, Paper
from ragagent.domain.documents import Element, ParsedDocument
from ragagent.domain.locations import PdfBox, PdfRegion
from ragagent.domain.research import EvidenceRecord, MetadataFilter, QueryPlan
from ragagent.ingestion.chunker import StructureChunker
from ragagent.ingestion.service import ingest
from ragagent.retrieval.evidence import evidence_payload, exact_span
from ragagent.retrieval.service import HybridRetriever, record
from tests.integration.test_api import client as client
from tests.integration.test_ingestion import DocumentParser
from tests.integration.test_retrieval import Embedder, FixtureReranker

pytestmark = pytest.mark.integration


def region(source, page):
    return PdfRegion(
        source_id=source,
        page_no=page,
        bbox=PdfBox(
            left=20,
            top=30,
            right=100,
            bottom=70,
            page_width=612,
            page_height=792,
            coord_origin="TOPLEFT",
        ),
    )


async def test_source_regions_survive_ingestion_retrieval_and_citation_without_id_change(
    client, empty_db, tmp_path
):
    paper = Paper(
        title="DEMO source",
        sha256="d" * 64,
        original_path=str(tmp_path / "source.pdf"),
        arxiv_id="2401.01234v2",
        arxiv_family_id="2401.01234",
        arxiv_version=2,
    )
    empty_db.add(paper)
    empty_db.flush()
    doc = ParsedDocument(
        title="DEMO",
        elements=[
            Element(
                source_id="#/texts/0",
                section_path=["Methods"],
                page_start=2,
                page_end=2,
                element_type="caption",
                content="Table 1: DEMO scores (%).",
                pdf_regions=[region("#/texts/0", 2)],
            ),
            Element(
                source_id="#/tables/0",
                related_source_ids=["#/texts/0"],
                section_path=["Methods"],
                page_start=2,
                page_end=3,
                element_type="table",
                content=(
                    "| Method | score (%) |\n| --- | --- |\n| Alpha | 91.5 |\n| Beta | 92.0 |\n"
                ),
                pdf_regions=[region("#/tables/0", 2), region("#/tables/0", 3)],
            ),
            Element(
                source_id="#/texts/1",
                section_path=["Methods"],
                page_start=3,
                page_end=3,
                element_type="formula",
                content="L = x + y",
                pdf_regions=[region("#/texts/1", 3)],
            ),
        ],
    )
    await ingest(
        empty_db,
        paper,
        DocumentParser(doc),
        StructureChunker(target_tokens=20, overlap_tokens=0),
        Embedder(),
    )
    empty_db.commit()
    chunks = list(
        empty_db.scalars(select(Chunk).where(Chunk.paper_id == paper.id).order_by(Chunk.ordinal))
    )
    for chunk in chunks:
        assert chunk.metadata_json["source_location_version"] == 1
        evidence = record(chunk, paper, 1.0, "rerank", []).evidence
        assert evidence.evidence_id == str(
            uuid5(NAMESPACE_URL, f"chunk:{chunk.id}:0:{len(chunk.content)}")
        )
        assert evidence.pdf_location == "available" and exact_span(evidence)
        assert evidence.paper.arxiv_version == 2 and evidence.paper.pdf_sha256 == paper.sha256
        source = client.get(f"/api/papers/{paper.id}/chunks/{chunk.id}/source")
        assert source.status_code == 200 and source.json()["pdf_location"] == "available"
        assert source.json()["pdf_regions"] == [r.model_dump() for r in evidence.pdf_regions]
        snapshot = EvidenceRecord.model_validate_json(evidence.model_dump_json())
        assert (
            snapshot.evidence_id == evidence.evidence_id
            and snapshot.pdf_regions == evidence.pdf_regions
        )
        payload = evidence_payload(evidence)
        assert "pdf_regions" not in payload and "pdf_location" not in payload
        assert all("pdf_regions" not in span for span in payload["source_spans"])
        assert all("pdf_regions" not in context for context in payload["source_context"])
        if chunk.element_type == "table":
            assert {r.page_no for r in evidence.pdf_regions} == {2, 3}
            assert all(r.text_mapping == "unavailable" for r in evidence.pdf_regions)
            assert {c.source_id for c in evidence.source_context} == {"#/tables/0", "#/texts/0"}
    result = await HybridRetriever(empty_db, Embedder(), FixtureReranker()).search(
        QueryPlan(queries=["DEMO scores"], filters=MetadataFilter(paper_ids=[paper.id]))
    )
    assert (
        result.dense
        and result.lexical
        and all(e.pdf_location == "available" for e in result.evidence)
    )
    saved = ParsedDocument.model_validate_json(
        Path(paper.original_path).with_suffix(".parsed.json").read_text()
    )
    assert [e.content for e in saved.elements] == [e.content for e in doc.elements]


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {
            "page_location": "invented",
            "pdf_regions": [{"source_id": "bad", "page_no": 2, "bbox": {"left": "invalid"}}],
        },
    ],
)
async def test_old_index_and_invalid_optional_positions_keep_usable_evidence(
    empty_db, tmp_path, metadata
):
    paper = Paper(title="Legacy DEMO", sha256="f" * 64, original_path=str(tmp_path / "old.pdf"))
    empty_db.add(paper)
    empty_db.flush()
    doc = ParsedDocument(
        title="DEMO",
        elements=[
            Element(
                section_path=["Methods"],
                page_start=2,
                page_end=2,
                element_type="text",
                content="Exact DEMO source text.",
            )
        ],
    )
    await ingest(empty_db, paper, DocumentParser(doc), StructureChunker(), Embedder())
    chunk = empty_db.scalar(select(Chunk).where(Chunk.paper_id == paper.id))
    previous = record(chunk, paper, 1.0, "rerank", []).evidence
    # Persist a JSON-valid corrupt optional location; never weaken source-text checks.
    chunk.metadata_json = metadata
    empty_db.flush()
    evidence = record(chunk, paper, 1.0, "rerank", []).evidence
    assert (
        evidence.evidence_id == previous.evidence_id
        and evidence.quote == previous.quote
        and exact_span(evidence)
    )
    assert evidence.pdf_location == "unavailable"
    assert evidence.page_location == ("unavailable" if metadata else "available")
    result = await HybridRetriever(empty_db, Embedder(), FixtureReranker()).search(
        QueryPlan(queries=["DEMO source"], filters=MetadataFilter(paper_ids=[paper.id]))
    )
    assert result.evidence and all(exact_span(e) for e in result.evidence)
