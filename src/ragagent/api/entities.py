"""Explicit local candidate jobs and human source-span decisions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ragagent.api.papers import DB, QueueDep, enqueue, missing_paper
from ragagent.api.schemas import RunResponse
from ragagent.db.models import Chunk, ChunkAnnotationReview, EntityMention, Paper, Run
from ragagent.deletion.guards import lifecycle_lock
from ragagent.domain.annotations import AnnotationPageQuery
from ragagent.domain.entities import (
    AnnotationStart,
    ChunkReview,
    EntityLinkDelete,
    MentionCreate,
    MentionListQuery,
    MentionPatch,
    MentionResponse,
)
from ragagent.errors import ApplicationError
from ragagent.ingestion.entity_review import decide, locked_source, manual_mention
from ragagent.ingestion.entity_service import source_hash
from ragagent.jobs import dispatch_run

router = APIRouter(tags=["entity review"])


def safe_failure(db: DB, exc: ApplicationError) -> None:
    db.rollback()
    code = exc.code
    status = (
        410
        if code == "source_deleted"
        else 404
        if code in {"paper_not_found", "chunk_not_found", "entity_mention_not_found"}
        else 409
    )
    raise HTTPException(status, code) from None


def snapshot(value: EntityMention, chunk: Chunk) -> MentionResponse:
    return MentionResponse.model_validate(value).model_copy(
        update={"current_source": value.content_sha256 == source_hash(chunk.content)}
    )


@router.post("/api/papers/{paper_id}/annotation-runs", status_code=202)
def start(paper_id: UUID, request: AnnotationStart, db: DB, queue: QueueDep) -> dict[str, object]:
    pid = str(paper_id)
    lifecycle_lock(db)
    paper = db.scalar(
        select(Paper)
        .where(Paper.id == pid)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if paper is None:
        missing_paper(db, pid)
    if paper.status != "indexed":
        raise HTTPException(409, "paper_not_indexed")
    if db.scalar(select(Chunk.id).where(Chunk.paper_id == pid).limit(1)) is None:
        raise HTTPException(409, "annotation_no_source_chunks")
    pending = db.scalar(
        select(Run)
        .where(
            Run.kind == "entity_annotation",
            Run.request["paper_id"].as_string() == pid,
            Run.status.in_(("queued", "running")),
        )
        .order_by(Run.created_at.desc())
        .limit(1)
    )
    if pending:
        db.commit()
        if pending.status == "queued":
            dispatch_run(db, queue, pending.id)
        return {
            **RunResponse.model_validate(pending).model_dump(),
            "paper_id": pid,
            "reused_existing": True,
            "engine": request.engine,
            "model_calls": 0,
        }
    latest = db.scalar(
        select(Run)
        .where(Run.kind == "entity_annotation", Run.request["paper_id"].as_string() == pid)
        .order_by(Run.created_at.desc())
        .limit(1)
    )
    current = func.encode(func.sha256(func.convert_to(Chunk.content, "UTF8")), "hex")
    remaining = db.scalar(
        select(Chunk.id)
        .outerjoin(ChunkAnnotationReview, ChunkAnnotationReview.chunk_id == Chunk.id)
        .where(
            Chunk.paper_id == pid,
            (
                ChunkAnnotationReview.chunk_id.is_(None)
                | (ChunkAnnotationReview.content_sha256 != current)
                | ChunkAnnotationReview.extractor_version.is_(None)
                | (ChunkAnnotationReview.extractor_version != request.engine)
                | ChunkAnnotationReview.status.not_in(("needs_review", "completed"))
            ),
        )
        .limit(1)
    )
    if latest and latest.status == "completed" and remaining is None:
        return {
            **RunResponse.model_validate(latest).model_dump(),
            "paper_id": pid,
            "reused_existing": True,
            "engine": request.engine,
            "model_calls": 0,
        }
    run = enqueue(db, queue, "entity_annotation", {"paper_id": pid, "engine": request.engine})
    return {
        **RunResponse.model_validate(run).model_dump(),
        "paper_id": pid,
        "reused_existing": False,
        "engine": request.engine,
        "model_calls": 0,
    }


def validate_query(request: Request) -> None:
    names = [key for key, _ in request.query_params.multi_items()]
    if len(names) != len(set(names)):
        raise HTTPException(422, "duplicate_search_parameter")


@router.get("/api/papers/{paper_id}/entity-mentions")
def mentions(
    paper_id: UUID, db: DB, request: Request, query: Annotated[MentionListQuery, Query()]
) -> dict[str, object]:
    pid = str(paper_id)
    lifecycle_lock(db)
    if db.get(Paper, pid) is None:
        missing_paper(db, pid)
    validate_query(request)
    statement = (
        select(EntityMention, Chunk)
        .join(Chunk, Chunk.id == EntityMention.chunk_id)
        .where(Chunk.paper_id == pid)
    )
    if query.chunk_id:
        statement = statement.where(Chunk.id == query.chunk_id)
    count = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.execute(
        statement.order_by(Chunk.ordinal, Chunk.id, EntityMention.span_start, EntityMention.id)
        .offset(query.offset)
        .limit(query.limit)
    ).all()
    return {
        "items": [snapshot(value, chunk).model_dump() for value, chunk in rows],
        "total": count,
        "limit": query.limit,
        "offset": query.offset,
    }


@router.get("/api/papers/{paper_id}/annotation-chunks")
def review_chunks(
    paper_id: UUID, db: DB, request: Request, query: Annotated[AnnotationPageQuery, Query()]
) -> dict[str, object]:
    pid = str(paper_id)
    lifecycle_lock(db)
    if db.get(Paper, pid) is None:
        missing_paper(db, pid)
    validate_query(request)
    total = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.paper_id == pid)) or 0
    rows = db.execute(
        select(Chunk, ChunkAnnotationReview)
        .outerjoin(ChunkAnnotationReview, ChunkAnnotationReview.chunk_id == Chunk.id)
        .where(Chunk.paper_id == pid)
        .order_by(Chunk.ordinal, Chunk.id)
        .offset(query.offset)
        .limit(query.limit)
    ).all()
    items = []
    for chunk, review in rows:
        digest = source_hash(chunk.content)
        items.append(
            {
                "chunk_id": chunk.id,
                "section_path": chunk.section_path,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "content_sha256": digest,
                "status": review.status
                if review and review.content_sha256 == digest
                else "unprocessed",
            }
        )
    return {"items": items, "total": total, **query.model_dump()}


@router.post("/api/papers/{paper_id}/chunks/{chunk_id}/entity-mentions", status_code=201)
def create_mention(
    paper_id: UUID, chunk_id: UUID, request: MentionCreate, db: DB
) -> MentionResponse:
    try:
        chunk = locked_source(db, str(paper_id), str(chunk_id))
        value = manual_mention(db, chunk, request)
        response = snapshot(value, chunk)
        db.commit()
        return response
    except ApplicationError as exc:
        safe_failure(db, exc)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "entity_occurrence_conflict") from None
    raise AssertionError("unreachable")


@router.patch("/api/papers/{paper_id}/entity-mentions/{mention_id}")
def patch_mention(
    paper_id: UUID, mention_id: UUID, request: MentionPatch, db: DB
) -> MentionResponse:
    try:
        value = db.get(EntityMention, str(mention_id))
        if value is None:
            if db.get(Paper, str(paper_id)) is None:
                missing_paper(db, str(paper_id))
            raise ApplicationError("entity_mention_not_found")
        chunk = locked_source(db, str(paper_id), value.chunk_id)
        db.refresh(value)
        response = snapshot(decide(db, chunk, value, request), chunk)
        db.commit()
        return response
    except ApplicationError as exc:
        safe_failure(db, exc)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "entity_occurrence_conflict") from None
    raise AssertionError("unreachable")


@router.post("/api/papers/{paper_id}/chunks/{chunk_id}/annotation-review")
def complete_review(paper_id: UUID, chunk_id: UUID, request: ChunkReview, db: DB) -> dict[str, str]:
    try:
        chunk = locked_source(db, str(paper_id), str(chunk_id))
        if source_hash(chunk.content) != request.expected_content_sha256:
            raise ApplicationError("annotation_source_changed")
        pending = db.scalar(
            select(EntityMention.id)
            .where(
                EntityMention.chunk_id == chunk.id,
                EntityMention.state == "proposed",
                EntityMention.content_sha256 == request.expected_content_sha256,
            )
            .limit(1)
        )
        if pending:
            raise ApplicationError("annotation_unresolved_candidates")
        record = db.get(ChunkAnnotationReview, chunk.id)
        if record is None:
            record = ChunkAnnotationReview(
                chunk_id=chunk.id,
                content_sha256=request.expected_content_sha256,
                status="completed",
            )
            db.add(record)
        record.content_sha256, record.status = request.expected_content_sha256, "completed"
        from datetime import UTC, datetime

        record.updated_at = datetime.now(UTC)
        db.commit()
        return {"status": "completed"}
    except ApplicationError as exc:
        safe_failure(db, exc)
    raise AssertionError("unreachable")


@router.get("/api/papers/{paper_id}/chunks/{chunk_id}/entities")
def current_links(paper_id: UUID, chunk_id: UUID, db: DB) -> list[dict[str, object]]:
    from ragagent.db.models import ChunkEntity, Entity

    lifecycle_lock(db)
    if db.get(Paper, str(paper_id)) is None:
        missing_paper(db, str(paper_id))
    chunk = db.scalar(
        select(Chunk).where(Chunk.id == str(chunk_id), Chunk.paper_id == str(paper_id))
    )
    if chunk is None:
        raise HTTPException(404, "chunk_not_found")
    return [
        {"entity_id": e.id, "name": e.name, "entity_type": e.entity_type}
        for e in db.scalars(
            select(Entity)
            .join(ChunkEntity, ChunkEntity.entity_id == Entity.id)
            .where(ChunkEntity.chunk_id == chunk.id)
            .order_by(Entity.entity_type, Entity.name, Entity.id)
        )
    ]


@router.delete("/api/papers/{paper_id}/chunks/{chunk_id}/entities/{entity_id}")
def remove_link(
    paper_id: UUID, chunk_id: UUID, entity_id: UUID, request: EntityLinkDelete, db: DB
) -> dict[str, str]:
    from datetime import UTC, datetime

    from sqlalchemy import delete

    from ragagent.db.models import ChunkEntity
    from ragagent.ingestion.entity_review import require_review

    try:
        chunk = locked_source(db, str(paper_id), str(chunk_id))
        if source_hash(chunk.content) != request.expected_content_sha256:
            raise ApplicationError("annotation_source_changed")
        # Removing a source association never deletes the shared Entity or PDF.
        removed = db.scalar(
            delete(ChunkEntity)
            .where(ChunkEntity.chunk_id == chunk.id, ChunkEntity.entity_id == str(entity_id))
            .returning(ChunkEntity.chunk_id)
        )
        changed = False
        for value in db.scalars(
            select(EntityMention).where(
                EntityMention.chunk_id == chunk.id, EntityMention.entity_id == str(entity_id)
            )
        ):
            changed = True
            value.state, value.entity_id, value.owns_link = "rejected", None, False
            value.version += 1
            value.updated_at = datetime.now(UTC)
        if removed is not None or changed:
            require_review(db, chunk)
        db.commit()
        return {"status": "removed"}
    except ApplicationError as exc:
        safe_failure(db, exc)
    raise AssertionError("unreachable")
