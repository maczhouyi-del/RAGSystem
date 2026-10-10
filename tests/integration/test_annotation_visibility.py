"""Real PG partial annotation corpus, SYNTHETIC ONLY / NOT A BENCHMARK."""

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ragagent.db.models import Chunk, ChunkAnnotationReview, ChunkEntity, Paper, Section, new_id
from ragagent.domain.research import MetadataFilter, QueryPlan
from ragagent.retrieval.service import HybridRetriever
from tests.integration.test_api import client as client
from tests.integration.test_retrieval import Embedder, FixtureReranker, populate

pytestmark = pytest.mark.integration


def review(db: Session, chunk: Chunk, status: str = "completed") -> ChunkAnnotationReview:
    value = ChunkAnnotationReview(
        chunk_id=chunk.id,
        content_sha256=hashlib.sha256(chunk.content.encode()).hexdigest(),
        status=status,
    )
    db.add(value)
    db.flush()
    return value


def test_legacy_links_never_claim_complete_review(client: TestClient, empty_db: Session) -> None:
    pid, cid = populate(empty_db)
    result = client.get(f"/api/papers/{pid}/annotations").json()
    assert result["status"] == "partial" and result["reviewed_chunks"] == 0
    assert result["linked_chunks"] == 1 and result["total_occurrences"] == 3
    assert {item["entity_type"] for item in result["items"]} == {"dataset", "method", "metric"}
    other = empty_db.scalar(select(Paper).where(Paper.id != pid))
    assert other
    unprocessed = client.get(f"/api/papers/{other.id}/annotations").json()
    assert unprocessed["status"] == "unprocessed" and unprocessed["items"] == []
    source = client.get(f"/api/papers/{pid}/chunks/{cid}/source")
    assert source.status_code == 200
    chunk = empty_db.get(Chunk, cid)
    assert chunk and source.json()["content"] == chunk.content
    assert source.json()["section_id"] == chunk.section_id and source.json()["page_start"] == 1
    assert client.get(f"/api/papers/{other.id}/chunks/{cid}/source").status_code == 404


@pytest.mark.parametrize(
    "state,expected",
    [
        ("queued", "processing"),
        ("processing", "processing"),
        ("failed", "failed"),
        ("completed", "completed"),
    ],
)
def test_explicit_review_states_and_stale_hash(
    client: TestClient, empty_db: Session, state: str, expected: str
) -> None:
    pid, cid = populate(empty_db)
    chunk = empty_db.get(Chunk, cid)
    assert chunk
    record = review(empty_db, chunk, state)
    response = client.get(f"/api/papers/{pid}/annotations").json()
    assert response["status"] == expected
    record.content_sha256 = "0" * 64
    empty_db.flush()
    stale = client.get(f"/api/papers/{pid}/annotations").json()
    assert stale["status"] == "partial" and stale["reviewed_chunks"] == 0
    assert stale["active_chunks"] == stale["failed_chunks"] == 0


def test_complete_empty_links_is_explicit_review_not_absence(
    client: TestClient, empty_db: Session
) -> None:
    pid, cid = populate(empty_db)
    empty_db.execute(delete(ChunkEntity).where(ChunkEntity.chunk_id == cid))
    chunk = empty_db.get(Chunk, cid)
    assert chunk
    assert client.get(f"/api/papers/{pid}/annotations").json()["status"] == "unprocessed"
    review(empty_db, chunk)
    result = client.get(f"/api/papers/{pid}/annotations").json()
    assert (
        result["status"] == "completed" and result["items"] == [] and result["linked_chunks"] == 0
    )


async def test_scope_coverage_and_strict_vs_full_text(
    client: TestClient, empty_db: Session
) -> None:
    pid, cid = populate(empty_db)
    plain = client.post("/api/annotations/coverage", json={}).json()
    assert (
        plain["total_chunks"] == 2
        and plain["matching_chunks"] == 2
        and not plain["strict"]
        and not plain["complete"]
    )
    absent = client.post("/api/annotations/coverage", json={"datasets": ["training"]}).json()
    assert (
        absent["total_chunks"] == 2
        and absent["matching_chunks"] == 0
        and absent["strict"]
        and not absent["complete"]
    )
    selected = client.post(
        "/api/annotations/coverage",
        json={
            "paper_ids": [pid],
            "authors": ["Alice"],
            "datasets": ["SCIDOCS"],
            "sections": ["Methods"],
        },
    ).json()
    assert selected["total_chunks"] == selected["matching_chunks"] == 1
    impossible = client.post(
        "/api/annotations/coverage", json={"authors": ["Missing"], "datasets": ["SCIDOCS"]}
    ).json()
    assert (
        impossible["total_chunks"] == impossible["matching_chunks"] == 0
        and not impossible["complete"]
    )
    unknown_group = client.post(
        "/api/annotations/coverage", json={"group_ids": [new_id()], "datasets": ["SCIDOCS"]}
    ).json()
    assert unknown_group["total_chunks"] == 0
    retriever = HybridRetriever(empty_db, Embedder(), FixtureReranker())
    ordinary = await retriever.search(QueryPlan(queries=["training"], filters=MetadataFilter()))
    strict = await retriever.search(
        QueryPlan(queries=["training"], filters=MetadataFilter(datasets=["training"]))
    )
    assert ordinary.lexical and len(ordinary.dense) == 2
    assert not strict.lexical and not strict.dense
    chunk = empty_db.get(Chunk, cid)
    assert chunk
    review(empty_db, chunk)
    reviewed = client.post(
        "/api/annotations/coverage", json={"paper_ids": [pid], "datasets": ["SciDocs"]}
    ).json()
    assert reviewed["complete"] and reviewed["reviewed_chunks"] == 1


def test_paged_occurrences_source_eligibility_and_invalid_requests(
    client: TestClient, empty_db: Session
) -> None:
    pid, cid = populate(empty_db)
    first = client.get(f"/api/papers/{pid}/annotations?limit=1&offset=0").json()
    second = client.get(f"/api/papers/{pid}/annotations?limit=1&offset=1").json()
    assert first["total_occurrences"] == second["total_occurrences"] == 3
    assert first["items"][0]["entity_id"] != second["items"][0]["entity_id"]
    for query in ["limit=0", "limit=201", "offset=-1", "limit=1&limit=2", "url=http://other"]:
        assert client.get(f"/api/papers/{pid}/annotations?{query}").status_code == 422
    assert (
        client.post("/api/annotations/coverage", json={"full_text_fallback": True}).status_code
        == 422
    )
    assert client.get(f"/api/papers/{new_id()}/annotations").status_code == 404
    paper = empty_db.get(Paper, pid)
    assert paper
    paper.source_status = "withdrawn"
    empty_db.flush()
    assert client.get(f"/api/papers/{pid}/annotations").json()["total_chunks"] == 1
    assert (
        client.post("/api/annotations/coverage", json={"paper_ids": [pid]}).json()["total_chunks"]
        == 0
    )
    empty_db.delete(paper)
    empty_db.flush()
    assert client.get(f"/api/papers/{pid}/annotations").status_code == 404
    assert client.get(f"/api/papers/{pid}/chunks/{cid}/source").status_code == 404


def test_retired_paper_blocks_sources_and_cascades_reviews(
    client: TestClient, empty_db: Session
) -> None:
    from tests.integration.test_paper_metadata import upload

    uploaded = upload(client)
    paper = empty_db.get(Paper, uploaded["id"])
    assert paper
    pid = paper.id
    paper.status = "indexed"
    section = Section(paper_id=paper.id, title="Methods", path="Methods", ordinal=0)
    empty_db.add(section)
    empty_db.flush()
    chunk = Chunk(
        paper_id=paper.id,
        section_id=section.id,
        section_path="Methods",
        page_start=1,
        page_end=1,
        element_type="text",
        content="SYNTHETIC source",
        token_count=2,
        ordinal=0,
        embedding=[0.0] * 384,
    )
    empty_db.add(chunk)
    empty_db.flush()
    cid = chunk.id
    review(empty_db, chunk)
    assert client.get(f"/api/papers/{pid}/annotations").json()["status"] == "completed"
    response = client.request(
        "DELETE",
        f"/api/papers/{pid}",
        json={
            "confirm_paper_id": pid,
            "expected_metadata_version": 1,
            "scope": "current_library",
            "acknowledge_retained_copies": True,
        },
    )
    assert response.status_code == 202
    assert client.get(f"/api/papers/{pid}/annotations").status_code == 410
    assert client.get(f"/api/papers/{pid}/chunks/{cid}/source").status_code == 410
    assert not list(empty_db.scalars(select(ChunkAnnotationReview)))
