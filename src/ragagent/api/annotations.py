"""Read-only annotation coverage and original source; no model calls or writes."""

from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import and_, func, select
from sqlalchemy.sql.selectable import CTE

from ragagent.api.papers import DB, missing_paper
from ragagent.db.models import Chunk, ChunkAnnotationReview, ChunkEntity, Entity, Paper, Run
from ragagent.deletion.guards import lifecycle_lock
from ragagent.domain.annotations import (
    AnnotationCoverage,
    AnnotationCoverageRequest,
    AnnotationPageQuery,
    AnnotationSource,
    EntityOccurrence,
    PaperAnnotations,
    annotation_status,
)
from ragagent.domain.research import MetadataFilter
from ragagent.retrieval.filters import apply_filters

router = APIRouter(tags=["annotation visibility"])


def coverage_rows(filters: MetadataFilter) -> CTE:
    # PostgreSQL built-in SHA256 avoids trusting raw parser metadata or stale text.
    current = ChunkAnnotationReview.content_sha256 == func.encode(
        func.sha256(func.convert_to(Chunk.content, "UTF8")), "hex"
    )
    linked = select(ChunkEntity.chunk_id).where(ChunkEntity.chunk_id == Chunk.id).exists()
    statement = (
        select(
            Chunk.id.label("id"),
            and_(current, ChunkAnnotationReview.status == "completed").label("reviewed"),
            and_(current, ChunkAnnotationReview.status.in_(("queued", "processing"))).label(
                "active"
            ),
            and_(current, ChunkAnnotationReview.status == "failed").label("failed"),
            and_(current, ChunkAnnotationReview.status == "needs_review").label("needs_review"),
            linked.label("linked"),
        )
        .join(Paper, Paper.id == Chunk.paper_id)
        .outerjoin(ChunkAnnotationReview, ChunkAnnotationReview.chunk_id == Chunk.id)
        .where(Paper.status == "indexed", Paper.source_status.not_in(("withdrawn", "retracted")))
    )
    return apply_filters(statement, filters).cte()


def counts(rows: CTE, db: DB) -> dict[str, int]:
    result = (
        db.execute(
            select(
                func.count().label("total_chunks"),
                func.count().filter(rows.c.reviewed).label("reviewed_chunks"),
                func.count().filter(rows.c.linked).label("linked_chunks"),
                func.count().filter(rows.c.active).label("active_chunks"),
                func.count().filter(rows.c.failed).label("failed_chunks"),
                func.count().filter(rows.c.needs_review).label("needs_review_chunks"),
            ).select_from(rows)
        )
        .mappings()
        .one()
    )
    return dict(result)


@router.post("/api/annotations/coverage")
def filter_coverage(request: AnnotationCoverageRequest, db: DB) -> AnnotationCoverage:
    values = request.model_dump()
    entity_fields = ("entity_types", "datasets", "methods", "metrics")
    strict = any(values[key] for key in entity_fields)
    base = MetadataFilter.model_validate({**values, **{key: [] for key in entity_fields}})
    rows = coverage_rows(base)
    matched = coverage_rows(request)
    # One statement gives scoped totals and strict matches the same DB snapshot.
    result = (
        db.execute(
            select(
                func.count().label("total_chunks"),
                func.count().filter(rows.c.reviewed).label("reviewed_chunks"),
                func.count().filter(rows.c.linked).label("linked_chunks"),
                func.count().filter(rows.c.active).label("active_chunks"),
                func.count().filter(rows.c.failed).label("failed_chunks"),
                func.count().filter(rows.c.needs_review).label("needs_review_chunks"),
                select(func.count())
                .select_from(matched)
                .scalar_subquery()
                .label("matching_chunks"),
            ).select_from(rows)
        )
        .mappings()
        .one()
    )
    values = dict(result)
    return AnnotationCoverage(
        **values,
        strict=strict,
        complete=values["total_chunks"] > 0 and values["total_chunks"] == values["reviewed_chunks"],
    )


@router.get("/api/papers/{paper_id}/annotations")
def paper_annotations(
    paper_id: UUID, db: DB, request: Request, query: Annotated[AnnotationPageQuery, Query()]
) -> PaperAnnotations:
    lifecycle_lock(db)
    pid = str(paper_id)
    if db.get(Paper, pid) is None:
        missing_paper(db, pid)
    names = [key for key, _ in request.query_params.multi_items()]
    if len(names) != len(set(names)):
        raise HTTPException(422, "duplicate_search_parameter")
    # Per-paper visibility includes failed/nonindexed/withdrawn source chunks;
    # retrieval coverage above follows actual searchable source constraints.
    current = ChunkAnnotationReview.content_sha256 == func.encode(
        func.sha256(func.convert_to(Chunk.content, "UTF8")), "hex"
    )
    linked = select(ChunkEntity.chunk_id).where(ChunkEntity.chunk_id == Chunk.id).exists()
    inventory = (
        select(
            Chunk.id,
            and_(current, ChunkAnnotationReview.status == "completed").label("reviewed"),
            and_(current, ChunkAnnotationReview.status.in_(("queued", "processing"))).label(
                "active"
            ),
            and_(current, ChunkAnnotationReview.status == "failed").label("failed"),
            and_(current, ChunkAnnotationReview.status == "needs_review").label("needs_review"),
            linked.label("linked"),
        )
        .outerjoin(ChunkAnnotationReview, ChunkAnnotationReview.chunk_id == Chunk.id)
        .where(Chunk.paper_id == pid)
        .cte()
    )
    summary = counts(inventory, db)
    occurrences = (
        select(
            Entity.id.label("entity_id"),
            Entity.name,
            Entity.entity_type,
            Chunk.id.label("chunk_id"),
            Chunk.section_path,
            Chunk.page_start,
            Chunk.page_end,
        )
        .join(ChunkEntity, ChunkEntity.entity_id == Entity.id)
        .join(Chunk, Chunk.id == ChunkEntity.chunk_id)
        .where(Chunk.paper_id == pid)
    )
    total = db.scalar(select(func.count()).select_from(occurrences.subquery())) or 0
    items = (
        db.execute(
            occurrences.order_by(
                Chunk.ordinal, Chunk.id, Entity.entity_type, Entity.name, Entity.id
            )
            .offset(query.offset)
            .limit(query.limit)
        )
        .mappings()
        .all()
    )
    latest_run = db.scalar(
        select(Run)
        .where(Run.kind == "entity_annotation", Run.request["paper_id"].as_string() == pid)
        .order_by(Run.created_at.desc(), Run.id)
        .limit(1)
    )
    active_run = latest_run if latest_run and latest_run.status in {"queued", "running"} else None
    current_status = annotation_status(
        summary["total_chunks"],
        summary["reviewed_chunks"],
        summary["active_chunks"],
        summary["failed_chunks"],
        summary["linked_chunks"],
        summary["needs_review_chunks"],
    )
    if latest_run and latest_run.status == "failed" and current_status != "completed":
        current_status = "failed"
    return PaperAnnotations(
        active_run_id=active_run.id if active_run else None,
        active_run_status=cast(Literal["queued", "running"], active_run.status)
        if active_run
        else None,
        paper_id=pid,
        latest_annotation_run_id=latest_run.id if latest_run else None,
        latest_annotation_run_status=latest_run.status if latest_run else None,
        latest_annotation_run_error_code=latest_run.error_code if latest_run else None,
        status="processing" if active_run else current_status,
        **summary,
        items=[EntityOccurrence.model_validate(item) for item in items],
        total_occurrences=total,
        **query.model_dump(),
    )


@router.get("/api/papers/{paper_id}/chunks/{chunk_id}/source")
def source(paper_id: UUID, chunk_id: UUID, db: DB) -> AnnotationSource:
    from ragagent.ingestion.entity_service import source_hash

    lifecycle_lock(db)
    pid = str(paper_id)
    if db.get(Paper, pid) is None:
        missing_paper(db, pid)
    chunk = db.get(Chunk, str(chunk_id))
    if chunk is None or chunk.paper_id != pid:
        raise HTTPException(404, "chunk_not_found")
    return AnnotationSource(
        paper_id=pid,
        chunk_id=chunk.id,
        section_id=chunk.section_id,
        section_path=chunk.section_path,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        content=chunk.content,
        content_sha256=source_hash(chunk.content),
    )
