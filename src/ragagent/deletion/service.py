"""Atomic library retirement followed by recoverable Run/RQ cleanup."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ragagent.db.dispatch import JobDispatch
from ragagent.db.models import (
    Author,
    Chunk,
    ChunkEntity,
    Conversation,
    Dataset,
    Entity,
    EntityRelation,
    Evidence,
    ExecutionEvent,
    Message,
    Method,
    Metric,
    Paper,
    PaperAuthor,
    PaperDeletion,
    Run,
)
from ragagent.deletion.files import manifest_file, unlink_owned
from ragagent.deletion.guards import lifecycle_lock
from ragagent.deletion.history import SourceIds, redact, source_ids
from ragagent.domain.deletion import (
    CleanupFile,
    PaperDeleteRequest,
    PaperDeletionPreview,
    PaperDeletionResponse,
)
from ragagent.errors import ApplicationError
from ragagent.ingestion.arxiv import arxiv_identity
from ragagent.jobs import TERMINAL_STATUSES, ensure_running, locked_run, sync_assistant_message
from ragagent.settings import get_settings

RETAINED_COPIES = [
    "desktop_documents_cache",
    "external_pdf_reader",
    "downloaded_exports",
    "user_saved_files",
    "backups_and_sync",
    "external_provider_retention",
    "conversation_answer_prose",
]


def imports_for(session: Session, paper: Paper) -> list[Run]:
    result = []
    for run in session.scalars(
        select(Run)
        .where(
            Run.kind.in_(["ingestion", "arxiv", "entity_annotation"]),
            Run.status.in_(["queued", "running"]),
        )
        .order_by(Run.id)
    ):
        matches = run.request.get("paper_id") == paper.id
        if run.kind == "arxiv" and paper.arxiv_family_id:
            family, version = arxiv_identity(run.request["arxiv_id"])
            matches = (
                matches
                or family == paper.arxiv_family_id
                and version in {None, paper.arxiv_version}
            )
        if matches:
            result.append(run)
    return result


def preview(session: Session, paper: Paper) -> PaperDeletionPreview:
    chunk_ids = list(session.scalars(select(Chunk.id).where(Chunk.paper_id == paper.id)))
    return PaperDeletionPreview(
        paper_id=paper.id,
        metadata_version=paper.metadata_version,
        chunks=len(chunk_ids),
        evidence=len(
            list(session.scalars(select(Evidence.id).where(Evidence.chunk_id.in_(chunk_ids))))
        ),
        pending_imports=len(imports_for(session, paper)),
        retained_copies=RETAINED_COPIES,
    )


def cleanup_run(session: Session, paper_id: str) -> Run:
    run = Run(kind="paper_delete", request={"paper_id": paper_id})
    session.add(run)
    session.flush()
    session.add(JobDispatch(run_id=run.id))
    return run


def retire(session: Session, paper_id: str, request: PaperDeleteRequest) -> PaperDeletion:
    if request.confirm_paper_id != paper_id:
        raise ApplicationError("paper_deletion_confirmation_mismatch")
    lifecycle_lock(session, exclusive=True)
    previous = session.get(PaperDeletion, paper_id)
    if previous is not None:
        return previous
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise ApplicationError("paper_not_found")
    # All source publishers acquire the shared lifecycle lock before Run/Paper
    # locks. Deletion takes the exclusive lock first, then the same row order.
    pending = imports_for(session, paper)
    chunks = list(session.scalars(select(Chunk).where(Chunk.paper_id == paper_id)))
    ids = SourceIds(papers={paper_id}, chunks={c.id for c in chunks})
    entity_ids = set(
        session.scalars(select(ChunkEntity.entity_id).where(ChunkEntity.chunk_id.in_(ids.chunks)))
    )
    author_ids = set(
        session.scalars(select(PaperAuthor.author_id).where(PaperAuthor.paper_id == paper_id))
    )
    ids.evidence.update(
        session.scalars(select(Evidence.id).where(Evidence.chunk_id.in_(ids.chunks)))
    )
    ids.evidence.update(
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"chunk:{c.id}:0:{len(c.content)}")) for c in chunks
    )
    runs = list(session.scalars(select(Run).order_by(Run.conversation_id, Run.id)))
    events = list(session.scalars(select(ExecutionEvent).order_by(ExecutionEvent.id)))
    messages = list(session.scalars(select(Message).order_by(Message.conversation_id, Message.id)))

    # Some historical snapshots have a more precise evidence span than the
    # current Evidence table. Retain IDs only so those pairs cannot later revive.
    def collect(value: Any) -> None:
        if isinstance(value, list):
            for child in value:
                collect(child)
        elif isinstance(value, dict):
            local = {
                key: child
                for key, child in value.items()
                if key in {"paper", "paper_id", "chunk_id"}
            }
            if source_ids(local).intersects(ids) and isinstance(value.get("evidence_id"), str):
                ids.evidence.add(value["evidence_id"])
            for child in value.values():
                collect(child)

    for run in runs:
        collect(run.result)
        collect(run.request)
    for event in events:
        collect(event.payload)
    for message in messages:
        collect(message.metadata_json)
    affected = {r.id for r in runs if source_ids([r.request, r.result]).intersects(ids)}
    affected.update(e.run_id for e in events if source_ids(e.payload).intersects(ids))
    affected.update(
        m.run_id for m in messages if m.run_id and source_ids(m.metadata_json).intersects(ids)
    )
    # Legacy messages can outlive Runs. Lock affected conversations in stable
    # order before Runs and redact their citation metadata as well.
    conversation_ids = {
        m.conversation_id for m in messages if source_ids(m.metadata_json).intersects(ids)
    }
    conversation_ids.update(
        r.conversation_id for r in runs if r.conversation_id and r.id in affected
    )
    for conversation_id in sorted(conversation_ids):
        session.scalar(
            select(Conversation.id).where(Conversation.id == conversation_id).with_for_update()
        )
    pending_ids = {r.id for r in pending}
    for run in runs:
        if run.id in affected | pending_ids:
            current = locked_run(session, run.id)
            assert current is not None
    paper = session.scalar(
        select(Paper)
        .where(Paper.id == paper_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if paper is None:
        raise ApplicationError("paper_not_found")
    if paper.metadata_version != request.expected_metadata_version:
        raise ApplicationError("paper_metadata_conflict")
    cancelled = []
    for run in runs:
        if run.id not in affected | pending_ids:
            continue
        run.request = redact(run.request, ids)
        run.result = redact(run.result, ids)
        if run.status not in TERMINAL_STATUSES:
            run.status, run.error_code = "cancelled", "source_deleted"
            cancelled.append(run.id)
            sync_assistant_message(session, run)
            session.add(
                ExecutionEvent(
                    run_id=run.id, node="cancelled", payload={"error_code": "source_deleted"}
                )
            )
    for event in events:
        if event.run_id in affected:
            event.payload = redact(event.payload, ids)
    for message in messages:
        if message.run_id in affected or source_ids(message.metadata_json).intersects(ids):
            redacted_metadata = redact(message.metadata_json, ids)
            redacted_metadata["source_availability"] = "unavailable"
            redacted_metadata["source_unavailable_reason"] = "source_deleted"
            if redacted_metadata != message.metadata_json:
                message.metadata_json = redacted_metadata
                # Clients reject snapshots older than updated_at. Source-only
                # changes must advance that clock too, even without a Run.
                message.updated_at = max(
                    datetime.now(UTC), message.updated_at + timedelta(microseconds=1)
                )
    settings = get_settings()
    original = Path(paper.original_path)
    files = [
        manifest_file(settings.data_dir, original, "pdf", checksum=paper.sha256),
        manifest_file(settings.data_dir, original.with_suffix(".parsed.json"), "parsed"),
    ]
    other_paths = {
        str(Path(path).absolute())
        for path in session.scalars(select(Paper.original_path).where(Paper.id != paper_id))
    }
    for item in files:
        if str(original.absolute()) in other_paths:
            item.retained_reason = "shared_by_other_paper"
    evaluation_ids = [r.id for r in runs if r.id in affected and r.kind.startswith("eval_")]
    for run_id in evaluation_ids:
        for filename in ("results.json", "results.md", "results.json.tmp", "results.md.tmp"):
            files.append(
                manifest_file(
                    settings.data_dir,
                    settings.data_dir / "evaluations" / run_id / filename,
                    "evaluation",
                )
            )
    run = cleanup_run(session, paper_id)
    ledger = PaperDeletion(
        paper_id=paper_id,
        chunk_ids=sorted(ids.chunks),
        evidence_ids=sorted(ids.evidence),
        files=[item.model_dump() for item in files],
        cancelled_run_ids=cancelled,
        affected_evaluation_ids=evaluation_ids,
        last_cleanup_run_id=run.id,
    )
    session.add(ledger)
    session.delete(paper)
    session.flush()
    orphan_entities = list(
        session.scalars(
            select(Entity.id).where(
                Entity.id.in_(entity_ids),
                ~select(ChunkEntity.chunk_id).where(ChunkEntity.entity_id == Entity.id).exists(),
                ~select(EntityRelation.id)
                .where(
                    or_(
                        EntityRelation.source_id == Entity.id, EntityRelation.target_id == Entity.id
                    )
                )
                .exists(),
            )
        )
    )
    for subtype in (Dataset, Method, Metric):
        session.execute(delete(subtype).where(subtype.entity_id.in_(orphan_entities)))
    session.execute(delete(Entity).where(Entity.id.in_(orphan_entities)))
    session.execute(
        delete(Author).where(
            Author.id.in_(author_ids),
            ~select(PaperAuthor.paper_id).where(PaperAuthor.author_id == Author.id).exists(),
        )
    )
    return ledger


def response(session: Session, ledger: PaperDeletion) -> PaperDeletionResponse:
    run = session.get(Run, ledger.last_cleanup_run_id)
    assert run is not None
    return PaperDeletionResponse.model_validate(
        {
            "paper_id": ledger.paper_id,
            "cleanup_run_id": run.id,
            "cleanup_status": run.status,
            "error_code": run.error_code,
            "retained_copies": RETAINED_COPIES,
            "retained_managed_files": sorted(
                {item["retained_reason"] for item in ledger.files if item.get("retained_reason")}
            ),
        }
    )


def clean(session: Session, run: Run, cancel: Callable[[str], None]) -> None:
    lifecycle_lock(session)
    ensure_running(session, run)
    ledger = session.scalar(
        select(PaperDeletion)
        .where(PaperDeletion.paper_id == run.request["paper_id"])
        .with_for_update()
    )
    if ledger is None or ledger.last_cleanup_run_id != run.id:
        raise ApplicationError("cleanup_run_superseded")
    for run_id in ledger.cancelled_run_ids:
        try:
            cancel(run_id)
        except Exception:
            raise ApplicationError("cleanup_queue_unavailable") from None
    for value in ledger.files:
        unlink_owned(get_settings().data_dir, CleanupFile.model_validate(value))
    run.result = {
        "paper_id": ledger.paper_id,
        "library_removed": True,
        "managed_cleanup_completed": True,
    }
    run.status = "completed"
