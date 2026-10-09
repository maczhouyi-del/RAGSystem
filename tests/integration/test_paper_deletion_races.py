"""Deterministic late-worker barriers with separate, committed PostgreSQL sessions."""

import asyncio
import hashlib
from pathlib import Path
from threading import Event, Thread
from time import monotonic, sleep

import pytest
from redis import Redis
from rq import Queue, Worker
from rq.job import Callback, JobStatus
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from ragagent import worker
from ragagent.api.queue import RQQueue
from ragagent.db.models import Chunk, Evidence, Paper, Run, new_id
from ragagent.deletion.service import clean, retire
from ragagent.domain.deletion import PaperDeleteRequest
from ragagent.domain.research import MetadataFilter, QueryPlan
from ragagent.errors import ApplicationError
from ragagent.jobs import claim_run, finish_run
from ragagent.retrieval.service import HybridRetriever
from ragagent.settings import get_settings
from tests.integration.test_ingestion import FixtureEmbedder, FixtureParser
from tests.integration.test_paper_deletion import confirmation, seed_chunk
from tests.integration.test_retrieval import Embedder, FixtureReranker

pytestmark = pytest.mark.integration


@pytest.fixture
def live(job_sessions: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    monkeypatch.setattr(worker, "session_factory", lambda: job_sessions)
    monkeypatch.setattr(worker, "make_embedder", lambda settings: FixtureEmbedder())
    monkeypatch.setattr(worker, "DoclingParser", FixtureParser)
    with job_sessions() as session:
        session.execute(text("TRUNCATE papers, entities, runs, conversations CASCADE"))
        session.commit()
    yield job_sessions
    with job_sessions() as session:
        session.execute(text("TRUNCATE papers, entities, runs, conversations CASCADE"))
        session.commit()


def paper_run(sessions: sessionmaker[Session], tmp_path: Path) -> tuple[str, str, Path]:
    path = tmp_path / f"{new_id()}.pdf"
    path.write_bytes(b"%PDF-1.4 SYNTHETIC LATE WORKER")
    with sessions() as session:
        paper = Paper(
            title="SYNTHETIC late ingestion",
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            original_path=str(path),
        )
        session.add(paper)
        session.flush()
        run = Run(kind="ingestion", request={"paper_id": paper.id})
        session.add(run)
        session.commit()
        return paper.id, run.id, path


@pytest.mark.parametrize("stage", ["parser", "embedding"])
async def test_late_ingestion_never_restores_rows_or_parsed_file(
    live: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    pid, run_id, original = paper_run(live, tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    thread_release = Event()
    loop = asyncio.get_running_loop()

    class Parser(FixtureParser):
        def parse(self, path: Path):
            if stage == "parser":
                loop.call_soon_threadsafe(entered.set)
                if not thread_release.wait(timeout=10):
                    raise AssertionError("test_parser_barrier_timeout")
            return super().parse(path)

    class Embedder(FixtureEmbedder):
        async def embed(self, texts: list[str]):
            if stage == "embedding":
                entered.set()
                await asyncio.wait_for(release.wait(), timeout=10)
            return await super().embed(texts)

    monkeypatch.setattr(worker, "DoclingParser", Parser)
    monkeypatch.setattr(worker, "make_embedder", lambda settings: Embedder())
    execution = asyncio.create_task(worker.execute_async(run_id))
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        with live() as deletion:
            retire(deletion, pid, PaperDeleteRequest.model_validate(confirmation(pid)))
            deletion.commit()
        release.set()
        thread_release.set()
        with pytest.raises(ApplicationError, match="source_deleted|run_no_longer_active"):
            await asyncio.wait_for(execution, timeout=10)
        with live() as check:
            assert check.get(Paper, pid) is None
            assert (
                check.scalar(select(func.count()).select_from(Chunk).where(Chunk.paper_id == pid))
                == 0
            )
            assert check.get(Run, run_id).status == "cancelled"
        assert not original.with_suffix(".parsed.json").exists()
    finally:
        release.set()
        thread_release.set()
        if not execution.done():
            await asyncio.wait_for(execution, timeout=10)


async def test_reranking_cached_candidates_are_rechecked_after_deletion(
    live: sessionmaker[Session], tmp_path: Path
) -> None:
    pid, _, _ = paper_run(live, tmp_path)
    with live() as session:
        paper = session.get(Paper, pid)
        paper.status, paper.embedding_model = "indexed", "test:384"
        seed_chunk(session, pid, "SYNTHETIC contrastive training")
        session.commit()
    entered, release = asyncio.Event(), asyncio.Event()

    class Reranker(FixtureReranker):
        async def rerank(self, query, candidates, top_k):
            assert candidates
            entered.set()
            await asyncio.wait_for(release.wait(), timeout=10)
            return await super().rerank(query, candidates, top_k)

    with live() as search_session:
        retriever = HybridRetriever(search_session, Embedder(), Reranker(), commit_results=True)
        execution = asyncio.create_task(
            retriever.search(
                QueryPlan(queries=["contrastive"], filters=MetadataFilter(paper_ids=[pid]))
            )
        )
        try:
            await asyncio.wait_for(entered.wait(), timeout=10)
            with live() as deletion:
                retire(deletion, pid, PaperDeleteRequest.model_validate(confirmation(pid)))
                deletion.commit()
            release.set()
            result = await asyncio.wait_for(execution, timeout=10)
            assert (
                not result.evidence and not result.dense and not result.lexical and not result.fused
            )
            with live() as check:
                assert check.scalar(select(func.count()).select_from(Evidence)) == 0
        finally:
            release.set()
            if not execution.done():
                await asyncio.wait_for(execution, timeout=10)


async def test_late_unversioned_arxiv_resolution_is_cancelled_other_version_kept(
    live: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ragagent.ingestion.arxiv import ArxivMetadata

    pid, _, _ = paper_run(live, tmp_path)
    with live() as session:
        paper = session.get(Paper, pid)
        paper.arxiv_id, paper.arxiv_family_id, paper.arxiv_version = "2408.09869v1", "2408.09869", 1
        run = Run(kind="arxiv", request={"arxiv_id": "2408.09869"})
        other = Run(kind="arxiv", request={"arxiv_id": "2408.09869v2"})
        session.add_all([run, other])
        session.commit()
        run_id, other_id = run.id, other.id
    entered, release = asyncio.Event(), asyncio.Event()
    downloaded: list[Path] = []

    async def download(arxiv_id, path, max_bytes):
        path.write_bytes(b"%PDF-1.4 SYNTHETIC LATE ARXIV")
        downloaded.append(path)
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=10)
        return ArxivMetadata(
            title="SYNTHETIC arxiv",
            authors=["DEMO"],
            year=2024,
            arxiv_id="2408.09869v1",
            arxiv_family_id="2408.09869",
            arxiv_version=1,
            source_url="https://arxiv.org/abs/2408.09869v1",
        )

    monkeypatch.setattr(worker, "download_arxiv", download)
    execution = asyncio.create_task(worker.execute_async(run_id))
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        with live() as deletion:
            retire(deletion, pid, PaperDeleteRequest.model_validate(confirmation(pid)))
            deletion.commit()
        release.set()
        with pytest.raises(ApplicationError, match="run_no_longer_active"):
            await asyncio.wait_for(execution, timeout=10)
        with live() as check:
            assert check.get(Run, run_id).status == "cancelled"
            assert check.get(Run, other_id).status == "queued"
            assert check.scalar(select(func.count()).select_from(Paper)) == 0
        assert downloaded and all(not path.exists() for path in downloaded)
    finally:
        release.set()
        if not execution.done():
            await asyncio.wait_for(execution, timeout=10)


def test_actual_started_redis_job_stops_without_reviving_cancelled_run(
    live: sessionmaker[Session],
    redis_connection: Redis,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid, run_id, original = paper_run(live, tmp_path)
    with live() as session:
        run = session.get(Run, run_id)
        run.status = "running"
        session.commit()
    monkeypatch.setattr(RQQueue, "connection", lambda self: redis_connection)
    queue = Queue("delete-running-" + new_id(), connection=redis_connection)
    job = queue.enqueue(
        "time.sleep",
        10,
        job_id=run_id,
        job_timeout=20,
        failure_ttl=60,
        on_stopped=Callback("ragagent.worker.on_stopped"),
    )
    other = queue.enqueue("time.sleep", 1, job_id=new_id(), job_timeout=20)
    errors: list[BaseException] = []

    def remove_started() -> None:
        try:
            deadline = monotonic() + 15
            while monotonic() < deadline:
                if job.get_status(refresh=True) == JobStatus.STARTED:
                    with live() as deletion:
                        ledger = retire(
                            deletion, pid, PaperDeleteRequest.model_validate(confirmation(pid))
                        )
                        deletion.commit()
                        cleanup_id = ledger.last_cleanup_run_id
                    with live() as deletion:
                        cleanup = claim_run(deletion, cleanup_id)
                        assert cleanup is not None
                        clean(deletion, cleanup, RQQueue().cancel)
                        finish_run(deletion, cleanup)
                    return
                sleep(0.02)
            raise AssertionError("test_job_did_not_start")
        except BaseException as exc:
            errors.append(exc)

    remover = Thread(target=remove_started)
    rq_worker = Worker([queue], connection=redis_connection)
    try:
        remover.start()
        rq_worker.work(burst=True, max_jobs=1, logging_level="WARNING")
        remover.join(timeout=16)
        assert not remover.is_alive() and not errors
        assert job.get_status(refresh=True) == JobStatus.STOPPED
        assert other.get_status(refresh=True) == JobStatus.QUEUED
        with live() as check:
            run = check.get(Run, run_id)
            assert run.status == "cancelled" and run.error_code == "source_deleted"
            assert check.get(Paper, pid) is None
        assert not original.exists()
    finally:
        remover.join(timeout=16)
        job.delete(remove_from_queue=True)
        other.delete(remove_from_queue=True)
        queue.delete(delete_jobs=True)
        redis_connection.delete(queue.registry_cleaning_key, rq_worker.key)


async def test_late_evaluation_checkpoint_cannot_restore_managed_artifacts(
    live: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ragagent.evaluation import retrieval
    from ragagent.evaluation.artifacts import write_results
    from ragagent.evaluation.schema import EvaluationCase, EvaluationDataset

    pid, _, _ = paper_run(live, tmp_path)
    with live() as session:
        paper = session.get(Paper, pid)
        paper.status, paper.embedding_model = "indexed", "test:384"
        seed_chunk(session, pid, "PRIVATE_EVAL_SOURCE")
        other = Paper(
            title="Other gold source DEMO",
            sha256="7" * 64,
            original_path="unmanaged-fixture",
            status="indexed",
            embedding_model="test:384",
        )
        session.add(other)
        session.flush()
        other_chunk = seed_chunk(session, other.id, "KEEP_OTHER_SOURCE")
        dataset = EvaluationDataset(
            dataset_id="SYNTHETIC ONLY",
            label_source="synthetic",
            description="SYNTHETIC ONLY / NOT A BENCHMARK",
            cases=[
                EvaluationCase(
                    id="q",
                    query="demo",
                    question_type="fact",
                    relevant_paper_ids=[other.id],
                    relevant_chunk_ids=[other_chunk.id],
                    expected_answer="PRIVATE_EVAL_GOLD",
                )
            ],
        )
        run = Run(kind="eval_retrieval", request={"dataset": dataset.model_dump(mode="json")})
        session.add(run)
        session.commit()
        run_id = run.id
    entered, release = asyncio.Event(), asyncio.Event()

    async def evaluation(dataset, search, session, settings, directory, **kwargs):
        payload = {
            "status": "completed",
            "evidence": [{"paper_id": pid, "quote": "PRIVATE_EVAL_SOURCE"}],
            "manifest": {
                "warning": "SYNTHETIC ONLY",
                "git_commit": "synthetic",
                "dataset_hash": "synthetic",
            },
        }
        write_results(directory, payload)
        entered.set()
        await asyncio.wait_for(release.wait(), timeout=10)
        write_results(directory, payload)
        return payload

    monkeypatch.setattr(retrieval, "evaluate_retrieval", evaluation)
    monkeypatch.setattr(worker, "make_reranker", lambda settings: FixtureReranker())
    execution = asyncio.create_task(worker.execute_async(run_id))
    directory = tmp_path / "evaluations" / run_id
    try:
        await asyncio.wait_for(entered.wait(), timeout=10)
        assert (directory / "results.json").exists()
        with live() as check:
            assert pid in check.get(Run, run_id).result["_source_references"]["paper_ids"]
        with live() as deletion:
            ledger = retire(deletion, pid, PaperDeleteRequest.model_validate(confirmation(pid)))
            deletion.commit()
            cleanup_id = ledger.last_cleanup_run_id
        with live() as deletion:
            cleanup = claim_run(deletion, cleanup_id)
            clean(deletion, cleanup, lambda _: None)
            finish_run(deletion, cleanup)
        assert not (directory / "results.json").exists()
        release.set()
        with pytest.raises(ApplicationError, match="source_deleted|run_no_longer_active"):
            await asyncio.wait_for(execution, timeout=10)
        assert not (directory / "results.json").exists() and not (directory / "results.md").exists()
        with live() as check:
            assert check.get(Run, run_id).status == "cancelled"
    finally:
        release.set()
        if not execution.done():
            await asyncio.wait_for(execution, timeout=10)
