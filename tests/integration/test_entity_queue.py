"""Actual PostgreSQL sessions and Redis/RQ; SYNTHETIC ONLY / NOT A BENCHMARK."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from rq import Queue, Worker
from sqlalchemy import delete, func, select

from ragagent import worker
from ragagent.api.entities import patch_mention, start
from ragagent.api.queue import RQQueue
from ragagent.db.dispatch import JobDispatch
from ragagent.db.models import Chunk, Dataset, Entity, EntityMention, Paper, Run, Section
from ragagent.domain.entities import AnnotationStart, MentionPatch
from ragagent.settings import get_settings


@pytest.mark.integration
def test_concurrent_start_one_outbox_real_rq_worker_and_optimistic_confirm(
    job_sessions, redis_connection, monkeypatch
):
    pid, sid, cid = (str(uuid4()) for _ in range(3))
    name = "entity-test-" + uuid4().hex
    monkeypatch.setenv("INGESTION_QUEUE", name)
    get_settings.cache_clear()
    monkeypatch.setattr(RQQueue, "connection", lambda self: redis_connection)
    monkeypatch.setattr(worker, "session_factory", lambda: job_sessions)

    def forbidden(*args, **kwargs):
        raise AssertionError("Local extraction must not instantiate models")

    for field in ["make_agents", "make_embedder", "make_reranker"]:
        monkeypatch.setattr(worker, field, forbidden)
    with job_sessions() as db:
        db.add(
            Paper(
                id=pid,
                title="DEMO queue",
                sha256=uuid4().hex * 2,
                original_path="fixture",
                status="indexed",
            )
        )
        db.flush()
        db.add(Section(id=sid, paper_id=pid, title="DEMO", path="DEMO", ordinal=0))
        db.flush()
        db.add(
            Chunk(
                id=cid,
                paper_id=pid,
                section_id=sid,
                section_path="DEMO",
                page_start=1,
                page_end=1,
                element_type="text",
                content="Dataset: DEMO" + uuid4().hex.upper() + ".",
                token_count=3,
                ordinal=0,
                embedding=[0.0] * 384,
            )
        )
        db.commit()
    queue = Queue(name, connection=redis_connection)
    barrier = Barrier(2)
    run_id = None
    rq_worker = None
    eid = None
    try:

        def submit(_):
            with job_sessions() as db:
                barrier.wait(timeout=10)
                return start(
                    UUID(pid),
                    AnnotationStart(
                        engine="source-labels-v1", acknowledge_candidates_require_review=True
                    ),
                    db,
                    RQQueue(),
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(submit, range(2)))
        assert receipts[0]["id"] == receipts[1]["id"]
        assert sorted(r["reused_existing"] for r in receipts) == [False, True]
        run_id = receipts[0]["id"]
        assert queue.count == 1
        with job_sessions() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(JobDispatch)
                    .where(JobDispatch.run_id == run_id)
                )
                == 1
            )
            assert db.get(Run, run_id).request["_queue_name"] == name
        rq_worker = Worker(
            [queue],
            connection=redis_connection,
            work_horse_killed_handler=worker.on_work_horse_killed,
        )
        rq_worker.work(burst=True, max_jobs=1, logging_level="WARNING")
        with job_sessions() as db:
            result = db.get(Run, run_id)
            assert result.status == "completed" and result.result["model_calls"] == 0
            candidate = db.scalar(select(EntityMention).where(EntityMention.chunk_id == cid))
            mid, digest = candidate.id, candidate.content_sha256
            assert candidate.state == "proposed"
        barrier = Barrier(2)

        def confirm(_):
            with job_sessions() as db:
                barrier.wait(timeout=10)
                try:
                    patch_mention(
                        UUID(pid),
                        UUID(mid),
                        MentionPatch(
                            action="confirm", expected_version=1, expected_content_sha256=digest
                        ),
                        db,
                    )
                    return 200
                except HTTPException as exc:
                    assert exc.detail == "entity_version_conflict"
                    return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(confirm, range(2))) == [200, 409]
        with job_sessions() as db:
            candidate = db.get(EntityMention, mid)
            assert candidate.state == "confirmed" and candidate.version == 2
            eid = candidate.entity_id
    finally:
        queue.delete(delete_jobs=True)
        keys = [queue.registry_cleaning_key]
        if rq_worker:
            keys.append(rq_worker.key)
        redis_connection.delete(*keys)
        with job_sessions() as db:
            if run_id:
                db.execute(delete(Run).where(Run.id == run_id))
            db.execute(delete(Paper).where(Paper.id == pid))
            if eid:
                db.execute(delete(Dataset).where(Dataset.entity_id == eid))
                db.execute(delete(Entity).where(Entity.id == eid))
            db.commit()
        get_settings.cache_clear()
