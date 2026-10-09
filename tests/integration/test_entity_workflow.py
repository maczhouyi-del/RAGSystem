"""Real PG current-source decisions; SYNTHETIC ONLY / NOT A BENCHMARK."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ragagent import worker
from ragagent.db.models import (
    Chunk,
    ChunkAnnotationReview,
    ChunkEntity,
    Entity,
    EntityMention,
    Paper,
    Run,
    Section,
)
from ragagent.domain.entities import EntityProposal
from ragagent.domain.research import MetadataFilter, QueryPlan
from ragagent.ingestion.entity_service import source_hash
from ragagent.retrieval.service import HybridRetriever
from tests.integration.test_api import client as client
from tests.integration.test_retrieval import Embedder, FixtureReranker


async def test_explicit_legacy_link_removal_is_local_and_repeat_safe(
    client, empty_db, corpus, monkeypatch
):
    pid, cid, other, other_cid = corpus
    entity = Entity(name="LEGACY UNVERIFIED", entity_type="dataset")
    empty_db.add(entity)
    empty_db.flush()
    eid = entity.id
    empty_db.add_all(
        [ChunkEntity(chunk_id=cid, entity_id=eid), ChunkEntity(chunk_id=other_cid, entity_id=eid)]
    )
    empty_db.commit()
    endpoint = f"/api/papers/{pid}/chunks/{cid}/entities/{eid}"
    digest = source_hash(empty_db.get(Chunk, cid).content)
    body = {"expected_content_sha256": digest, "acknowledge_remove_link": True}
    assert (
        client.request(
            "DELETE", endpoint, json={**body, "acknowledge_remove_link": False}
        ).status_code
        == 422
    )
    assert (
        client.request(
            "DELETE", endpoint, json={**body, "expected_content_sha256": "f" * 64}
        ).status_code
        == 409
    )
    assert client.request("DELETE", endpoint, json=body).status_code == 200
    assert client.get(f"/api/papers/{pid}/chunks/{cid}/entities").json() == []
    assert (
        client.get(f"/api/papers/{other}/chunks/{other_cid}/entities").json()[0]["entity_id"] == eid
    )
    assert empty_db.get(Entity, eid).name == "LEGACY UNVERIFIED"
    assert (
        client.post(
            f"/api/papers/{pid}/chunks/{cid}/annotation-review",
            json={"expected_content_sha256": digest, "acknowledge_all_three_types_reviewed": True},
        ).status_code
        == 200
    )
    assert client.request("DELETE", endpoint, json=body).status_code == 200
    assert empty_db.get(ChunkAnnotationReview, cid).status == "completed"


async def test_aliases_require_separate_confirmation_and_are_source_scoped(
    client, empty_db, corpus, monkeypatch
):
    pid, cid, other, _ = corpus
    for paper in [pid, other]:
        await execute(empty_db, monkeypatch, begin(client, paper)["id"])
    aliases = [v for v in values(client, pid) if v["alias_group"]]
    assert {v["name"] for v in aliases} == {"Large Demo Corpus", "LDC"}
    assert len({v["alias_group"] for v in aliases}) == 1
    assert (
        aliases[0]["alias_group"]
        != next(v for v in values(client, other) if v["alias_group"])["alias_group"]
    )
    decision(client, pid, next(v for v in aliases if v["name"] == "Large Demo Corpus"), "confirm")
    retriever = HybridRetriever(empty_db, Embedder(), FixtureReranker())
    assert not (
        await retriever.search(
            QueryPlan(queries=["dataset"], filters=MetadataFilter(datasets=["LDC"]))
        )
    ).dense
    decision(client, pid, next(v for v in aliases if v["name"] == "LDC"), "confirm")
    assert [
        v.evidence.chunk_id
        for v in (
            await retriever.search(
                QueryPlan(queries=["dataset"], filters=MetadataFilter(datasets=["LDC"]))
            )
        ).dense
    ] == [cid]


def test_manual_unicode_span_is_source_proven_and_duplicate_safe(client, empty_db, corpus):
    pid, cid, _, _ = corpus
    chunk = empty_db.get(Chunk, cid)
    chunk.content = "🧪 原文：科研数据集。"
    empty_db.commit()
    source = client.get(f"/api/papers/{pid}/chunks/{cid}/source").json()
    assert source["content_sha256"] == source_hash(chunk.content)
    start = chunk.content.index("科研数据集")
    body = {
        "entity_type": "dataset",
        "span_start": start,
        "span_end": start + len("科研数据集"),
        "expected_content_sha256": source["content_sha256"],
    }
    endpoint = f"/api/papers/{pid}/chunks/{cid}/entity-mentions"
    a = client.post(endpoint, json=body)
    assert a.status_code == 201 and a.json()["name"] == "科研数据集"
    b = client.post(endpoint, json=body)
    assert b.json()["id"] == a.json()["id"] and b.json()["state"] == "proposed"
    assert empty_db.scalar(select(func.count()).select_from(ChunkEntity)) == 0


async def test_retirement_cancels_annotation_and_cascades_mentions_without_reviving(
    client, empty_db, corpus, monkeypatch
):
    from ragagent.deletion.service import retire
    from ragagent.domain.deletion import PaperDeleteRequest
    from ragagent.errors import ApplicationError
    from ragagent.ingestion.entity_service import extract_paper
    from ragagent.jobs import claim_run

    pid, cid, other, _ = corpus
    await execute(empty_db, monkeypatch, begin(client, pid)["id"])
    chunk = empty_db.get(Chunk, cid)
    chunk.content += " Metric: ACC."
    empty_db.commit()
    rid = begin(client, pid)["id"]
    active = claim_run(empty_db, rid)
    assert active
    retire(
        empty_db,
        pid,
        PaperDeleteRequest(
            confirm_paper_id=pid,
            expected_metadata_version=1,
            scope="current_library",
            acknowledge_retained_copies=True,
        ),
    )
    empty_db.commit()
    assert empty_db.get(Run, rid).status == "cancelled"
    assert empty_db.scalar(select(func.count()).select_from(EntityMention)) == 0
    assert empty_db.get(ChunkAnnotationReview, cid) is None
    assert empty_db.get(Paper, other)
    with pytest.raises(ApplicationError, match="source_deleted"):
        extract_paper(empty_db, active)
    empty_db.rollback()
    assert client.get(f"/api/papers/{pid}/entity-mentions").status_code == 410


pytestmark = pytest.mark.integration


@pytest.fixture
def corpus(empty_db: Session) -> tuple[str, str, str, str]:
    ids = []
    for i in range(2):
        p = Paper(
            title=f"DEMO source {i}",
            sha256=str(i) * 64,
            original_path="fixture",
            status="indexed",
            embedding_model="test:384",
        )
        empty_db.add(p)
        empty_db.flush()
        s = Section(paper_id=p.id, title="Methods", path="Methods", ordinal=0)
        empty_db.add(s)
        empty_db.flush()
        c = Chunk(
            paper_id=p.id,
            section_id=s.id,
            section_path="Methods",
            page_start=1,
            page_end=1,
            element_type="text",
            content=(
                "Dataset: MNIST. Method: BERT. Metric: F1. "
                'Dataset: "Large Demo Corpus" (LDC). Correction: NewMNIST.'
            ),
            token_count=20,
            ordinal=0,
            embedding=[1.0] + [0.0] * 383,
        )
        empty_db.add(c)
        empty_db.flush()
        ids.extend([p.id, c.id])
    empty_db.commit()
    return tuple(ids)


def begin(client: TestClient, pid: str) -> dict:
    r = client.post(
        f"/api/papers/{pid}/annotation-runs",
        json={"engine": "source-labels-v1", "acknowledge_candidates_require_review": True},
    )
    assert r.status_code == 202, r.text
    return r.json()


async def execute(db: Session, monkeypatch: pytest.MonkeyPatch, rid: str) -> None:
    @contextmanager
    def scope() -> Iterator[Session]:
        yield db

    monkeypatch.setattr(worker, "session_factory", lambda: scope)

    def forbidden(*args, **kwargs):
        raise AssertionError("Local entity extraction must not instantiate any model")

    for field in ["make_agents", "make_embedder", "make_reranker"]:
        monkeypatch.setattr(worker, field, forbidden)
    await worker.execute_async(rid)


def values(client: TestClient, pid: str) -> list[dict]:
    r = client.get(f"/api/papers/{pid}/entity-mentions")
    assert r.status_code == 200, r.text
    return r.json()["items"]


def decision(client: TestClient, pid: str, value: dict, action: str, **changes) -> dict:
    r = client.patch(
        f"/api/papers/{pid}/entity-mentions/{value['id']}",
        json={
            "action": action,
            "expected_version": value["version"],
            "expected_content_sha256": value["content_sha256"],
            **changes,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_candidate_source_proof_confirmation_and_actual_strict_retrieval(
    client: TestClient,
    empty_db: Session,
    corpus: tuple[str, str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid, cid, other, _ = corpus
    original = empty_db.get(Chunk, cid).content
    receipt = begin(client, pid)
    assert receipt["model_calls"] == 0 and not receipt["reused_existing"]
    assert client.get(f"/api/papers/{pid}/annotations").json()["status"] == "processing"
    assert begin(client, pid)["id"] == receipt["id"]
    await execute(empty_db, monkeypatch, receipt["id"])
    result = empty_db.get(Run, receipt["id"])
    assert result and result.status == "completed" and result.result["model_calls"] == 0
    found = values(client, pid)
    assert len(found) == 5 and all(v["state"] == "proposed" and v["current_source"] for v in found)
    assert all(original[v["span_start"] : v["span_end"]] == v["name"] for v in found)
    assert empty_db.scalar(select(func.count()).select_from(ChunkEntity)) == 0
    assert client.get(f"/api/papers/{pid}/annotations").json()["status"] == "partial"
    retriever = HybridRetriever(empty_db, Embedder(), FixtureReranker())
    before = await retriever.search(
        QueryPlan(queries=["MNIST dataset"], filters=MetadataFilter(datasets=["MNIST"]))
    )
    assert not before.dense and not before.lexical
    confirmed = decision(client, pid, next(v for v in found if v["name"] == "MNIST"), "confirm")
    assert confirmed["state"] == "confirmed"
    after = await retriever.search(
        QueryPlan(
            queries=["MNIST dataset"], filters=MetadataFilter(paper_ids=[pid], datasets=["MNIST"])
        )
    )
    assert [v.evidence.chunk_id for v in after.dense] == [cid] and [
        v.evidence.chunk_id for v in after.lexical
    ] == [cid]
    assert not (
        await retriever.search(
            QueryPlan(
                queries=["MNIST"], filters=MetadataFilter(paper_ids=[other], datasets=["MNIST"])
            )
        )
    ).evidence
    assert begin(client, pid)["id"] == receipt["id"] and len(values(client, pid)) == 5
    assert empty_db.get(Chunk, cid).content == original


async def test_manual_correct_reject_and_shared_name_isolation(
    client: TestClient,
    empty_db: Session,
    corpus: tuple[str, str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, cid, second, second_cid = corpus
    for pid in [first, second]:
        await execute(empty_db, monkeypatch, begin(client, pid)["id"])
    a = decision(
        client, first, next(v for v in values(client, first) if v["name"] == "MNIST"), "confirm"
    )
    b = decision(
        client, second, next(v for v in values(client, second) if v["name"] == "MNIST"), "confirm"
    )
    text = empty_db.get(Chunk, cid).content
    start = text.index("NewMNIST")
    corrected = decision(
        client,
        first,
        a,
        "correct",
        entity_type="dataset",
        span_start=start,
        span_end=start + len("NewMNIST"),
    )
    assert corrected["state"] == "proposed" and corrected["name"] == "NewMNIST"
    confirmed = decision(client, first, corrected, "confirm")
    assert confirmed["state"] == "confirmed"
    other = next(v for v in values(client, second) if v["id"] == b["id"])
    assert other["name"] == "MNIST" and other["state"] == "confirmed"
    retriever = HybridRetriever(empty_db, Embedder(), FixtureReranker())
    result = await retriever.search(
        QueryPlan(queries=["MNIST"], filters=MetadataFilter(datasets=["MNIST"]))
    )
    assert [v.evidence.chunk_id for v in result.dense] == [second_cid]
    decision(client, first, confirmed, "reject")
    assert (
        empty_db.scalar(
            select(func.count()).select_from(ChunkEntity).where(ChunkEntity.chunk_id == cid)
        )
        == 0
    )
    assert (
        empty_db.scalar(
            select(func.count()).select_from(ChunkEntity).where(ChunkEntity.chunk_id == second_cid)
        )
        == 1
    )


async def test_complete_review_requires_resolved_candidates_and_explicit_ack(
    client: TestClient,
    empty_db: Session,
    corpus: tuple[str, str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid, cid, _, _ = corpus
    await execute(empty_db, monkeypatch, begin(client, pid)["id"])
    digest = source_hash(empty_db.get(Chunk, cid).content)
    endpoint = f"/api/papers/{pid}/chunks/{cid}/annotation-review"
    body = {"expected_content_sha256": digest, "acknowledge_all_three_types_reviewed": True}
    assert client.post(endpoint, json=body).status_code == 409
    assert (
        client.post(endpoint, json={**body, "acknowledge_all_three_types_reviewed": 1}).status_code
        == 422
    )
    for value in values(client, pid):
        decision(client, pid, value, "reject")
    assert client.post(endpoint, json=body).status_code == 200
    status = client.get(f"/api/papers/{pid}/annotations").json()
    assert (
        status["status"] == "completed"
        and status["reviewed_chunks"] == 1
        and status["linked_chunks"] == 0
    )
    assert not empty_db.scalar(select(func.count()).select_from(ChunkEntity))


async def test_versions_changed_source_invalid_span_and_other_paper_guard(
    client: TestClient,
    empty_db: Session,
    corpus: tuple[str, str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid, cid, other, _ = corpus
    await execute(empty_db, monkeypatch, begin(client, pid)["id"])
    value = next(v for v in values(client, pid) if v["name"] == "MNIST")
    confirmed = decision(client, pid, value, "confirm")
    body = {
        "action": "reject",
        "expected_version": value["version"],
        "expected_content_sha256": value["content_sha256"],
    }
    assert (
        client.patch(f"/api/papers/{pid}/entity-mentions/{value['id']}", json=body).status_code
        == 409
    )
    body["expected_version"] = confirmed["version"]
    assert (
        client.patch(f"/api/papers/{other}/entity-mentions/{value['id']}", json=body).status_code
        == 404
    )
    chunk = empty_db.get(Chunk, cid)
    chunk.content = "Changed current source: MNIST."
    empty_db.commit()
    assert (
        client.patch(f"/api/papers/{pid}/entity-mentions/{value['id']}", json=body).status_code
        == 409
    )
    stale = next(v for v in values(client, pid) if v["id"] == value["id"])
    assert not stale["current_source"]
    # Discarding a stale candidate is safe with an explicit current-source hash.
    body["expected_content_sha256"] = source_hash(chunk.content)
    assert (
        client.patch(f"/api/papers/{pid}/entity-mentions/{value['id']}", json=body).status_code
        == 200
    )
    assert not empty_db.scalar(select(func.count()).select_from(ChunkEntity))
    invalid = {
        "entity_type": "dataset",
        "span_start": 0,
        "span_end": 999,
        "expected_content_sha256": body["expected_content_sha256"],
    }
    assert (
        client.post(f"/api/papers/{pid}/chunks/{cid}/entity-mentions", json=invalid).status_code
        == 409
    )


async def test_duplicate_confirmed_mentions_keep_one_link_until_last_rejection(
    client: TestClient,
    empty_db: Session,
    corpus: tuple[str, str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid, cid, _, _ = corpus
    chunk = empty_db.get(Chunk, cid)
    chunk.content = "Dataset: MNIST. Dataset: MNIST."
    empty_db.flush()
    await execute(empty_db, monkeypatch, begin(client, pid)["id"])
    confirmed = [decision(client, pid, v, "confirm") for v in values(client, pid)]
    assert (
        len(confirmed) == 2 and empty_db.scalar(select(func.count()).select_from(ChunkEntity)) == 1
    )
    decision(client, pid, confirmed[0], "reject")
    assert empty_db.scalar(select(func.count()).select_from(ChunkEntity)) == 1
    decision(client, pid, confirmed[1], "reject")
    assert empty_db.scalar(select(func.count()).select_from(ChunkEntity)) == 0


def test_legacy_manual_route_now_requires_current_source_and_rolls_back_all(
    client: TestClient, empty_db: Session, corpus: tuple[str, str, str, str]
) -> None:
    pid, cid, _, _ = corpus
    endpoint = f"/api/papers/{pid}/chunks/{cid}/entities"
    assert (
        client.post(
            endpoint,
            json=[
                {"name": "MNIST", "entity_type": "dataset"},
                {"name": "GUESSED", "entity_type": "method"},
            ],
        ).status_code
        == 409
    )
    assert not list(empty_db.scalars(select(EntityMention))) and not list(
        empty_db.scalars(select(ChunkEntity))
    )
    assert (
        client.post(endpoint, json=[{"name": "MNIST", "entity_type": "dataset"}]).status_code == 200
    )
    result = values(client, pid)
    assert len(result) == 1 and result[0]["state"] == "confirmed"
    assert client.get(f"/api/papers/{pid}/annotations").json()["status"] == "partial"


async def test_extraction_failure_preserves_prior_source_and_retry_uses_new_run(
    client: TestClient,
    empty_db: Session,
    corpus: tuple[str, str, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ragagent.errors import ApplicationError
    from ragagent.ingestion import entity_service

    pid, cid, _, _ = corpus
    original = empty_db.get(Chunk, cid).content

    class InvalidFactory:
        version = "source-labels-v1"

        def extract(self, content: str) -> list[EntityProposal]:
            return [EntityProposal(name="GUESSED", entity_type="dataset", span_start=0, span_end=7)]

    original_factory = entity_service.SourceLabelExtractor
    monkeypatch.setattr(entity_service, "SourceLabelExtractor", InvalidFactory)
    receipt = begin(client, pid)
    with pytest.raises(ApplicationError, match="entity_source_mismatch"):
        await execute(empty_db, monkeypatch, receipt["id"])
    assert empty_db.get(Run, receipt["id"]).status == "failed"
    assert client.get(f"/api/papers/{pid}/annotations").json()["status"] == "failed"
    assert not values(client, pid) and empty_db.get(Chunk, cid).content == original
    monkeypatch.setattr(entity_service, "SourceLabelExtractor", original_factory)
    retry = begin(client, pid)
    assert retry["id"] != receipt["id"]
    await execute(empty_db, monkeypatch, retry["id"])
    assert empty_db.get(Run, receipt["id"]).status == "failed" and len(values(client, pid)) == 5


def test_all_new_read_queries_reject_unsupported_inputs(
    client: TestClient, corpus: tuple[str, str, str, str]
) -> None:
    pid, cid, _, _ = corpus
    for endpoint in ["entity-mentions", "annotation-chunks"]:
        for query in [
            "limit=0",
            "limit=201",
            "offset=-1",
            "limit=1&limit=2",
            "url=https://other.invalid",
        ]:
            assert client.get(f"/api/papers/{pid}/{endpoint}?{query}").status_code == 422
    assert client.get(f"/api/papers/{pid}/entity-mentions?chunk_id=wrong").status_code == 422
    assert (
        client.post(
            f"/api/papers/{pid}/annotation-runs",
            json={"engine": "paid-model", "acknowledge_candidates_require_review": True},
        ).status_code
        == 422
    )
