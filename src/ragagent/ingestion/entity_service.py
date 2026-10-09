"""Bounded, idempotent candidate generation in the existing durable worker."""

import hashlib
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ragagent.db.models import Chunk, ChunkAnnotationReview, EntityMention, Paper, Run
from ragagent.deletion.guards import guard_sources
from ragagent.domain.entities import EntityProposal
from ragagent.domain.privacy import reject_credentials
from ragagent.errors import ApplicationError
from ragagent.ingestion.entities import EntityExtractor, SourceLabelExtractor
from ragagent.jobs import ensure_running


def source_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def verify_proposal(chunk: Chunk, proposal: EntityProposal) -> None:
    if not 0 <= proposal.span_start < proposal.span_end <= len(chunk.content):
        raise ApplicationError("entity_span_invalid")
    if chunk.content[proposal.span_start : proposal.span_end] != proposal.name:
        raise ApplicationError("entity_source_mismatch")
    reject_credentials(proposal.name)


def propose_chunk(db: Session, chunk: Chunk, run_id: str, extractor: EntityExtractor) -> int:
    digest = source_hash(chunk.content)
    previous = db.get(ChunkAnnotationReview, chunk.id)
    if (
        previous
        and previous.content_sha256 == digest
        and previous.status in {"completed", "needs_review"}
        and previous.extractor_version == extractor.version
    ):
        return 0
    if len(chunk.content) > 50000:
        raise ApplicationError("annotation_chunk_too_large")
    proposals = extractor.extract(chunk.content)
    if len(proposals) > 100:
        raise ApplicationError("annotation_candidate_limit")
    for proposal in proposals:
        verify_proposal(chunk, proposal)
    count = 0
    for proposal in proposals:
        alias = (
            str(uuid5(NAMESPACE_URL, f"chunk-alias:{chunk.id}:{digest}:{proposal.alias_group}"))
            if proposal.alias_group
            else None
        )
        inserted = db.scalar(
            insert(EntityMention)
            .values(
                chunk_id=chunk.id,
                name=proposal.name,
                entity_type=proposal.entity_type,
                span_start=proposal.span_start,
                span_end=proposal.span_end,
                content_sha256=digest,
                state="proposed",
                origin=extractor.version,
                alias_group=alias,
                owns_link=False,
                version=1,
                updated_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(constraint="uq_entity_mentions_occurrence")
            .returning(EntityMention.id)
        )
        count += inserted is not None
    if previous is None:
        previous = ChunkAnnotationReview(
            chunk_id=chunk.id, content_sha256=digest, status="needs_review"
        )
        db.add(previous)
    # Human complete review of the identical text is not undone by local extraction.
    completed = previous.content_sha256 == digest and previous.status == "completed"
    previous.content_sha256 = digest
    previous.status = "completed" if completed and not count else "needs_review"
    previous.run_id = run_id
    previous.extractor_version = extractor.version
    previous.updated_at = datetime.now(UTC)
    db.flush()
    return count


def extract_paper(
    db: Session, run: Run, extractor: EntityExtractor | None = None
) -> dict[str, object]:
    extractor = extractor or SourceLabelExtractor()
    pid = str(run.request["paper_id"])
    created = processed = 0
    after: tuple[int, str] | None = None
    while True:
        # Short source publication transaction. No network or model call while locked.
        guard_sources(db, {"paper_id": pid})
        paper = db.scalar(
            select(Paper)
            .where(Paper.id == pid)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        ensure_running(db, run)
        if paper is None:
            raise ApplicationError("source_deleted")
        if paper.status != "indexed":
            raise ApplicationError("paper_not_indexed")
        query = select(Chunk).where(Chunk.paper_id == pid)
        if after:
            from sqlalchemy import tuple_

            query = query.where(tuple_(Chunk.ordinal, Chunk.id) > after)
        chunks = list(db.scalars(query.order_by(Chunk.ordinal, Chunk.id).limit(50)))
        if not chunks:
            db.commit()
            break
        for chunk in chunks:
            created += propose_chunk(db, chunk, run.id, extractor)
            processed += 1
        after = (chunks[-1].ordinal, chunks[-1].id)
        ensure_running(db, run)
        db.commit()
    return {
        "paper_id": pid,
        "engine": extractor.version,
        "created_candidates": created,
        "visited_chunks": processed,
        "model_calls": 0,
        "requires_human_review": True,
    }
