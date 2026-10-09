"""Real PostgreSQL/Redis/file lifecycle; SYNTHETIC ONLY, no paid/model/network calls."""

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Headers
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from rq.job import Job
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ragagent import worker
from ragagent.api.queue import RQQueue
from ragagent.db.models import (
    Author,
    Chunk,
    ChunkEntity,
    Conversation,
    Entity,
    EntityRelation,
    Evidence,
    ExecutionEvent,
    Message,
    Paper,
    PaperAuthor,
    PaperDeletion,
    Run,
    Section,
    new_id,
)
from ragagent.deletion.service import clean, retire
from ragagent.domain.research import MetadataFilter, QueryPlan
from ragagent.errors import ApplicationError
from ragagent.jobs import claim_run, finish_run
from ragagent.retrieval.service import HybridRetriever
from ragagent.settings import get_settings
from tests.integration.test_api import RecordingQueue
from tests.integration.test_paper_metadata import upload
from tests.integration.test_retrieval import Embedder, FixtureReranker

pytestmark = pytest.mark.integration


@pytest.fixture
def client(
    empty_db: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, auth_headers: Headers
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    from ragagent.api import runs
    from ragagent.api.app import app
    from ragagent.api.dependencies import get_db
    from ragagent.api.queue import get_queue

    @contextmanager
    def scope():
        yield empty_db

    monkeypatch.setattr(runs, "session_factory", lambda: scope)
    monkeypatch.setattr("ragagent.api.dispatcher.reconcile", lambda: None)
    app.dependency_overrides[get_db] = lambda: empty_db
    app.dependency_overrides[get_queue] = RecordingQueue
    with TestClient(app, headers=auth_headers) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def confirmation(paper_id: str, version: int = 1) -> dict[str, Any]:
    return {
        "confirm_paper_id": paper_id,
        "expected_metadata_version": version,
        "scope": "current_library",
        "acknowledge_retained_copies": True,
    }


def seed_chunk(db: Session, paper_id: str, text: str) -> Chunk:
    section = Section(paper_id=paper_id, title="DEMO", path="DEMO", ordinal=0)
    db.add(section)
    db.flush()
    chunk = Chunk(
        paper_id=paper_id,
        section_id=section.id,
        section_path="DEMO",
        page_start=1,
        page_end=1,
        element_type="text",
        content=text,
        token_count=6,
        ordinal=0,
        embedding=[1.0] + [0.0] * (get_settings().embedding_dimension - 1),
    )
    db.add(chunk)
    db.flush()
    return chunk


def cleanup(db: Session, run_id: str, cancel: Any = lambda run_id: None) -> None:
    run = claim_run(db, run_id)
    assert run is not None
    clean(db, run, cancel)
    finish_run(db, run)


def test_preview_confirmation_and_stale_version_do_not_remove_data(
    client: TestClient, empty_db: Session
) -> None:
    paper = upload(client)
    pid = paper["id"]
    assert client.get(f"/api/papers/{pid}/deletion-preview").json()["pending_imports"] == 1
    assert client.get(f"/api/papers/{pid}").json() == paper
    for body, status in [
        ({}, 422),
        ({**confirmation(pid), "confirm_paper_id": new_id()}, 409),
        ({**confirmation(pid), "scope": "all_copies"}, 422),
        ({**confirmation(pid), "expected_metadata_version": 2}, 409),
    ]:
        response = client.request("DELETE", f"/api/papers/{pid}", json=body)
        assert response.status_code == status
        assert client.get(f"/api/papers/{pid}").json() == paper
        assert empty_db.scalar(select(func.count()).select_from(PaperDeletion)) == 0
    assert (
        client.patch(
            f"/api/papers/{pid}", json={"title": "New title", "expected_metadata_version": 1}
        ).status_code
        == 200
    )
    response = client.request("DELETE", f"/api/papers/{pid}", json=confirmation(pid))
    assert response.status_code == 409
    assert response.json()["error_code"] == "paper_metadata_conflict"
    assert empty_db.scalar(select(func.count()).select_from(PaperDeletion)) == 0


async def test_atomic_removal_redacts_history_preserves_other_sources_and_cleans_files(
    client: TestClient, empty_db: Session
) -> None:
    first = upload(client)
    pid = first["id"]
    paper = empty_db.get(Paper, pid)
    assert paper is not None
    original = Path(paper.original_path)
    parsed = original.with_suffix(".parsed.json")
    parsed.write_text("PRIVATE_PARSE", encoding="utf-8")
    paper.status, paper.embedding_model = "indexed", "test:384"
    chunk = seed_chunk(empty_db, pid, "PRIVATE_SOURCE contrastive training")
    other = Paper(
        title="Other DEMO",
        sha256="9" * 64,
        original_path=str(original.parent / "other.pdf"),
        status="indexed",
        embedding_model="test:384",
    )
    Path(other.original_path).write_bytes(b"%PDF-1.4 OTHER DEMO")
    empty_db.add(other)
    empty_db.flush()
    other_chunk = seed_chunk(empty_db, other.id, "KEEP_SOURCE contrastive training")
    author = empty_db.scalar(select(Author).where(Author.name == "Alice"))
    assert author is not None
    empty_db.add(PaperAuthor(paper_id=other.id, author_id=author.id, position=0))
    entity = Entity(name="Shared DEMO", entity_type="method")
    orphan = Entity(name="Only deleted source DEMO", entity_type="dataset")
    empty_db.add(entity)
    empty_db.add(orphan)
    empty_db.flush()
    orphan_id = orphan.id
    empty_db.add_all(
        [
            ChunkEntity(chunk_id=chunk.id, entity_id=entity.id),
            ChunkEntity(chunk_id=chunk.id, entity_id=orphan.id),
            ChunkEntity(chunk_id=other_chunk.id, entity_id=entity.id),
            EntityRelation(
                source_id=entity.id, target_id=entity.id, chunk_id=chunk.id, relation="demo"
            ),
        ]
    )
    eid, keep_eid = new_id(), new_id()
    empty_db.add(
        Evidence(id=eid, chunk_id=chunk.id, span_start=0, span_end=14, quote="PRIVATE_SOURCE")
    )
    old = {
        "evidence_id": eid,
        "paper": {"paper_id": pid, "title": "Original DEMO"},
        "chunk_id": chunk.id,
        "quote": "PRIVATE_SOURCE",
        "content": "PRIVATE_SOURCE",
        "source_context": [{"text": "PRIVATE_CONTEXT"}],
        "source_spans": [{"page": 1}],
    }
    keep = {
        "evidence_id": keep_eid,
        "paper": {"paper_id": other.id},
        "chunk_id": other_chunk.id,
        "quote": "KEEP_SOURCE",
        "content": "KEEP_SOURCE",
    }
    conversation = Conversation(title="Keep conversation", mode="rag")
    empty_db.add(conversation)
    empty_db.flush()
    historical = Run(
        kind="rag",
        status="completed",
        conversation_id=conversation.id,
        request={"query": "Historical question"},
        result={
            "answer": "Historical answer stays.",
            "evidence": [old, keep],
            "citation_validation": {
                "valid": True,
                "supported_pairs": [
                    {"claim_id": "old", "evidence_id": eid},
                    {"claim_id": "keep", "evidence_id": keep_eid},
                ],
            },
        },
    )
    evaluation = Run(
        kind="eval_rag",
        status="completed",
        request={
            "dataset": {
                "cases": [
                    {
                        "relevant_paper_ids": [pid],
                        "expected_answer": "PRIVATE_GOLD",
                        "gold_sources": [old],
                    }
                ]
            }
        },
        result={"evidence": [old]},
    )
    unaffected = Run(
        kind="rag",
        status="completed",
        request={"query": "Other question"},
        result={"evidence": [keep], "citation_validation": {"valid": True}},
    )
    empty_db.add_all([historical, evaluation, unaffected])
    empty_db.flush()
    message = Message(
        conversation_id=conversation.id,
        run_id=historical.id,
        role="assistant",
        ordinal=0,
        status="completed",
        content="Historical answer stays.",
        metadata_json={
            "presentation": {
                "citation_refs": [
                    {"evidence_id": eid, "paper_id": pid},
                    {"evidence_id": keep_eid, "paper_id": other.id},
                ],
                "limitations": [],
            }
        },
    )
    legacy_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        ordinal=1,
        status="completed",
        content="Legacy message stays",
        metadata_json={
            "presentation": {
                "citation_refs": [{"paper_id": pid, "evidence_id": eid}],
                "limitations": [],
            }
        },
    )
    empty_db.add(legacy_message)
    empty_db.add_all(
        [
            message,
            ExecutionEvent(
                run_id=historical.id, node="retrieval", payload={"evidence": [old, keep]}
            ),
        ]
    )
    directory = get_settings().data_dir / "evaluations" / evaluation.id
    directory.mkdir(parents=True)
    (directory / "results.json").write_text(json.dumps({"evidence": [old]}), encoding="utf-8")
    (directory / "results.md").write_text("PRIVATE_SOURCE", encoding="utf-8")
    protected_file = directory / "user-notes.md"
    protected_file.write_text("KEEP_USER_FILE", encoding="utf-8")
    empty_db.commit()
    chunk_id, section_id, other_id, message_id, conv_id, historical_id, eval_id, unaffected_id = (
        chunk.id,
        chunk.section_id,
        other.id,
        message.id,
        conversation.id,
        historical.id,
        evaluation.id,
        unaffected.id,
    )
    deleted = client.request("DELETE", f"/api/papers/{pid}", json=confirmation(pid))
    assert deleted.status_code == 202
    value = deleted.json()
    assert value["library_removed"] is True and value["cleanup_status"] == "queued"
    assert "desktop_documents_cache" in value["retained_copies"]
    for suffix in ("", "/pdf", "/chunks", "/deletion-preview"):
        response = client.get(f"/api/papers/{pid}{suffix}")
        assert response.status_code == 410 and response.json()["error_code"] == "source_deleted"
    assert client.post(f"/api/papers/{pid}/retry").status_code == 410
    assert client.patch(f"/api/papers/{pid}", json={"title": "Revive"}).status_code == 410
    assert client.get(f"/api/evaluations/{eval_id}/results.json").status_code == 410
    empty_db.expire_all()
    assert empty_db.get(Chunk, chunk_id) is None and empty_db.get(Section, section_id) is None
    assert (
        empty_db.get(Evidence, eid) is None
        and empty_db.scalar(select(func.count()).select_from(EntityRelation)) == 0
    )
    assert empty_db.get(ChunkEntity, (other_chunk.id, entity.id)) is not None
    assert empty_db.get(Entity, orphan_id) is None
    assert (
        legacy_message.metadata_json["presentation"]["citation_refs"][0]["source_availability"]
        == "unavailable"
    )
    assert (
        empty_db.get(Entity, entity.id) is not None and empty_db.get(Author, author.id) is not None
    )
    result = client.get(f"/api/runs/{historical_id}").json()
    assert (
        result["status"] == "completed"
        and result["result"]["citation_validation"]["valid"] is False
    )
    assert result["result"]["evidence"][0]["source_availability"] == "unavailable"
    assert result["result"]["evidence"][1] == keep
    assert "PRIVATE_SOURCE" not in json.dumps(result)
    assert "PRIVATE_SOURCE" not in client.get(f"/api/runs/{historical_id}/events").text
    evaluation = empty_db.get(Run, eval_id)
    assert evaluation is not None and "PRIVATE_GOLD" not in json.dumps(evaluation.request)
    preserved = empty_db.get(Run, unaffected_id)
    assert preserved is not None and preserved.result == unaffected.result
    retained_message = empty_db.get(Message, message_id)
    assert retained_message is not None and retained_message.content == "Historical answer stays."
    assert (
        retained_message.metadata_json["presentation"]["citation_refs"][0]["source_availability"]
        == "unavailable"
    )
    assert empty_db.get(Conversation, conv_id) is not None
    retriever = HybridRetriever(empty_db, Embedder(), FixtureReranker())
    assert not (
        await retriever.search(
            QueryPlan(queries=["contrastive"], filters=MetadataFilter(paper_ids=[pid]))
        )
    ).evidence
    surviving = await retriever.search(
        QueryPlan(queries=["contrastive"], filters=MetadataFilter(paper_ids=[other_id]))
    )
    assert surviving.evidence and {e.paper.paper_id for e in surviving.evidence} == {other_id}
    cleanup(empty_db, value["cleanup_run_id"])
    assert (
        not original.exists() and not parsed.exists() and not (directory / "results.json").exists()
    )
    assert (
        not (directory / "results.md").exists() and protected_file.read_text() == "KEEP_USER_FILE"
    )
    assert Path(other.original_path).exists()
    assert client.get(f"/api/papers/{pid}/deletion").json()["cleanup_status"] == "completed"
    repeated = client.request("DELETE", f"/api/papers/{pid}", json=confirmation(pid)).json()
    assert repeated["cleanup_run_id"] == value["cleanup_run_id"]


def test_database_rollback_keeps_library_files_and_import_ownership(
    client: TestClient, empty_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ragagent.api import deletions

    first = upload(client)
    paper = empty_db.get(Paper, first["id"])
    assert paper is not None
    path = Path(paper.original_path)
    run = empty_db.scalar(select(Run).where(Run.kind == "ingestion"))
    assert run is not None
    before = client.get(f"/api/runs/{run.id}").json()

    def injected(*args: Any, **kwargs: Any) -> PaperDeletion:
        retire(*args, **kwargs)
        raise ApplicationError("synthetic_transaction_failure")

    monkeypatch.setattr(deletions, "retire", injected)
    response = client.request("DELETE", f"/api/papers/{paper.id}", json=confirmation(paper.id))
    assert response.status_code == 409
    assert client.get(f"/api/papers/{paper.id}").json() == first
    assert path.exists() and empty_db.scalar(select(func.count()).select_from(PaperDeletion)) == 0
    assert client.get(f"/api/runs/{run.id}").json() == before


async def test_partial_file_failure_retries_new_run_without_restoring_paper(
    client: TestClient, empty_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ragagent.deletion import service

    first = upload(client)
    paper = empty_db.get(Paper, first["id"])
    assert paper is not None
    pid, original = paper.id, Path(paper.original_path)
    parsed = original.with_suffix(".parsed.json")
    parsed.write_text("SYNTHETIC parsed", encoding="utf-8")
    deleted = client.request("DELETE", f"/api/papers/{pid}", json=confirmation(pid)).json()
    actual_unlink = service.unlink_owned

    def fail_parsed(root: Path, item: Any) -> None:
        if item.role == "parsed":
            raise ApplicationError("cleanup_file_unavailable")
        actual_unlink(root, item)

    @contextmanager
    def scope():
        yield empty_db

    monkeypatch.setattr(worker, "session_factory", lambda: scope)
    monkeypatch.setattr(RQQueue, "cancel", lambda self, run_id: None)
    monkeypatch.setattr(service, "unlink_owned", fail_parsed)
    with pytest.raises(ApplicationError, match="cleanup_file_unavailable"):
        await worker.execute_async(deleted["cleanup_run_id"])
    assert not original.exists() and parsed.exists()
    status = client.get(f"/api/papers/{pid}/deletion").json()
    assert status["cleanup_status"] == "failed" and status["library_removed"] is True
    assert client.get(f"/api/papers/{pid}").status_code == 410
    retry = client.post(f"/api/papers/{pid}/deletion/retry").json()
    assert retry["cleanup_run_id"] != deleted["cleanup_run_id"]
    monkeypatch.setattr(service, "unlink_owned", actual_unlink)
    await worker.execute_async(retry["cleanup_run_id"])
    assert (
        not parsed.exists()
        and client.get(f"/api/papers/{pid}/deletion").json()["cleanup_status"] == "completed"
    )
    assert client.get(f"/api/runs/{deleted['cleanup_run_id']}").json()["status"] == "failed"


async def test_real_redis_cancellation_isolated_and_outage_keeps_retirement(
    client: TestClient, empty_db: Session, redis_connection: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = upload(client)
    pid = first["id"]
    original_run = empty_db.scalar(select(Run).where(Run.kind == "ingestion"))
    assert original_run is not None
    other = Run(kind="ingestion", request={"paper_id": "other-paper"})
    empty_db.add(other)
    empty_db.commit()
    queue = RQQueue()
    monkeypatch.setattr(RQQueue, "connection", lambda self: redis_connection)
    name = "deletion-test-" + new_id()
    queue.submit_for_run(original_run.id, name, 60)
    queue.submit_for_run(other.id, name, 60)

    @contextmanager
    def scope():
        yield empty_db

    monkeypatch.setattr(worker, "session_factory", lambda: scope)
    try:
        deleted = client.request("DELETE", f"/api/papers/{pid}", json=confirmation(pid)).json()
        assert client.get(f"/api/runs/{original_run.id}").json()["status"] == "cancelled"
        assert queue.status(original_run.id) == "queued"

        def unavailable(self: RQQueue) -> Redis:
            raise RedisConnectionError("PRIVATE_CONNECTION_DETAILS")

        monkeypatch.setattr(RQQueue, "connection", unavailable)
        with pytest.raises(ApplicationError, match="cleanup_queue_unavailable"):
            await worker.execute_async(deleted["cleanup_run_id"])
        assert client.get(f"/api/papers/{pid}").status_code == 410
        assert (
            "PRIVATE_CONNECTION_DETAILS"
            not in client.get(f"/api/runs/{deleted['cleanup_run_id']}").text
        )
        monkeypatch.setattr(RQQueue, "connection", lambda self: redis_connection)
        retry = client.post(f"/api/papers/{pid}/deletion/retry").json()
        await worker.execute_async(retry["cleanup_run_id"])
        assert queue.status(original_run.id) == "canceled"
        assert queue.status(other.id) == "queued"
        assert client.get(f"/api/runs/{other.id}").json()["status"] == "queued"
    finally:
        for run_id in (original_run.id, other.id):
            Job.fetch(run_id, connection=redis_connection).delete()


def test_shared_registered_file_retained_and_user_can_reimport_fresh_id(
    client: TestClient, empty_db: Session
) -> None:
    first = upload(client)
    paper = empty_db.get(Paper, first["id"])
    assert paper is not None
    path = Path(paper.original_path)
    other = Paper(
        title="Other source version DEMO",
        original_path=paper.original_path,
        sha256=paper.sha256,
        arxiv_id="2408.09869v2",
        arxiv_family_id="2408.09869",
        arxiv_version=2,
    )
    empty_db.add(other)
    empty_db.commit()
    deleted = client.request(
        "DELETE", f"/api/papers/{paper.id}", json=confirmation(paper.id)
    ).json()
    assert deleted["retained_managed_files"] == ["shared_by_other_paper"]
    cleanup(empty_db, deleted["cleanup_run_id"])
    assert path.exists() and client.get(f"/api/papers/{other.id}/pdf").content == path.read_bytes()
    # Removing the other copy then reuploading is explicit, with a fresh ID.
    removed_other = client.request(
        "DELETE", f"/api/papers/{other.id}", json=confirmation(other.id)
    ).json()
    cleanup(empty_db, removed_other["cleanup_run_id"])
    reimport = upload(client)
    assert reimport["id"] not in {paper.id, other.id}
    assert client.get(f"/api/papers/{paper.id}/pdf").status_code == 410


@pytest.mark.parametrize(
    "payload",
    [
        {"paper_id": "DELETED_ID"},
        {"chunk_id": "DELETED_CHUNK"},
        {"supported_pairs": [{"evidence_id": "DELETED_EVIDENCE"}]},
    ],
)
def test_late_event_and_final_result_cannot_republish_deleted_source(
    client: TestClient, empty_db: Session, payload: dict[str, Any]
) -> None:
    first = upload(client)
    chunk = seed_chunk(empty_db, first["id"], "PRIVATE_SOURCE")
    evidence_id = new_id()
    empty_db.add(
        Evidence(
            id=evidence_id, chunk_id=chunk.id, span_start=0, span_end=14, quote="PRIVATE_SOURCE"
        )
    )
    empty_db.commit()
    transformed = json.loads(
        json.dumps(payload)
        .replace("DELETED_ID", first["id"])
        .replace("DELETED_CHUNK", chunk.id)
        .replace("DELETED_EVIDENCE", evidence_id)
    )
    client.request("DELETE", f"/api/papers/{first['id']}", json=confirmation(first["id"]))
    run = Run(kind="rag", status="running", request={"query": "Keep independent run"})
    empty_db.add(run)
    empty_db.commit()
    with pytest.raises(ApplicationError, match="source_deleted"):
        worker.event(empty_db, run, "late", transformed)
    empty_db.rollback()
    run.result, run.status = {"answer": "PRIVATE_LATE", **transformed}, "completed"
    with pytest.raises(ApplicationError, match="source_deleted"):
        finish_run(empty_db, run)
    empty_db.rollback()
    empty_db.expire_all()
    assert empty_db.get(Run, run.id).status == "running"
    assert (
        empty_db.scalar(
            select(func.count()).select_from(ExecutionEvent).where(ExecutionEvent.run_id == run.id)
        )
        == 0
    )
