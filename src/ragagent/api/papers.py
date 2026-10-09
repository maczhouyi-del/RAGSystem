import hashlib
from datetime import UTC, datetime
from typing import Annotated, NoReturn, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select, true
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ragagent.api.dependencies import get_db
from ragagent.api.queue import JobQueue, get_queue
from ragagent.api.schemas import (
    ArxivRequest,
    EntityAnnotation,
    PaperPage,
    PaperPatch,
    PaperResponse,
    RunResponse,
    UploadRunResponse,
)
from ragagent.db.dispatch import JobDispatch
from ragagent.db.models import (
    Author,
    Chunk,
    ChunkEntity,
    Entity,
    Paper,
    PaperAuthor,
    PaperCollection,
    PaperCollectionMember,
    PaperDeletion,
    Run,
    new_id,
)
from ragagent.deletion.guards import lifecycle_lock
from ragagent.domain.papers import OriginalPaperMetadata, PaperMetadataValues, PaperSearchQuery
from ragagent.domain.privacy import reject_credentials
from ragagent.jobs import dispatch_run
from ragagent.settings import get_settings

router = APIRouter(prefix="/api/papers", tags=["papers"])
DB = Annotated[Session, Depends(get_db)]
QueueDep = Annotated[JobQueue, Depends(get_queue)]


def enqueue(session: Session, queue: JobQueue, kind: str, request: dict[str, object]) -> Run:
    run = Run(kind=kind, request=request)
    session.add(run)
    session.flush()
    session.add(JobDispatch(run_id=run.id))
    session.commit()
    dispatch_run(session, queue, run.id)
    return run


def ingestion_run(session: Session, queue: JobQueue, paper_id: str) -> UploadRunResponse:
    run = session.scalar(
        select(Run)
        .where(Run.kind == "ingestion", Run.request["paper_id"].as_string() == paper_id)
        .order_by(Run.created_at.desc())
    )
    existing = (
        run if run is not None else enqueue(session, queue, "ingestion", {"paper_id": paper_id})
    )
    return UploadRunResponse(
        **RunResponse.model_validate(existing).model_dump(),
        paper_id=paper_id,
        reused_existing=True,
    )


def author_ids(session: Session, names: list[str]) -> dict[str, str]:
    result = {}
    # Stable insertion order avoids reciprocal waits when concurrent papers list
    # the same new authors in different orders. Output still follows paper order.
    for name in sorted(names):
        author_id = session.scalar(
            insert(Author)
            .values(name=name)
            .on_conflict_do_nothing(index_elements=[Author.name])
            .returning(Author.id)
        )
        if author_id is None:
            author_id = session.scalar(select(Author.id).where(Author.name == name))
        if author_id is None:
            raise HTTPException(409, "author_changed_retry")
        result[name] = author_id
    return result


def paper_response(session: Session, paper: Paper) -> PaperResponse:
    latest = session.scalar(
        select(Run.id)
        .where(Run.kind == "ingestion", Run.request["paper_id"].as_string() == paper.id)
        .order_by(Run.created_at.desc(), Run.id)
        .limit(1)
    )
    return paper_responses(session, [paper])[0].model_copy(
        update={"latest_ingestion_run_id": latest}
    )


def paper_responses(session: Session, items: list[Paper]) -> list[PaperResponse]:
    if not items:
        return []
    ids = [paper.id for paper in items]
    authors: dict[str, list[str]] = {}
    for paper_id, name in session.execute(
        select(PaperAuthor.paper_id, Author.name)
        .join(Author)
        .where(PaperAuthor.paper_id.in_(ids))
        .order_by(PaperAuthor.paper_id, PaperAuthor.position, Author.id)
    ):
        authors.setdefault(paper_id, []).append(name)
    counts = dict(
        session.execute(
            select(Chunk.paper_id, func.count())
            .where(Chunk.paper_id.in_(ids))
            .group_by(Chunk.paper_id)
        ).all()
    )
    return [
        PaperResponse(
            id=paper.id,
            title=paper.title,
            authors=authors.get(paper.id, []),
            year=paper.year,
            venue=paper.venue,
            arxiv_id=paper.arxiv_id,
            arxiv_family_id=paper.arxiv_family_id,
            arxiv_version=paper.arxiv_version,
            source_status=paper.source_status,
            status=paper.status,
            error_code=paper.error_code,
            chunk_count=counts.get(paper.id, 0),
            created_at=paper.created_at,
            original_metadata=OriginalPaperMetadata.model_validate(paper.original_metadata)
            if paper.original_metadata is not None
            else None,
            metadata_version=paper.metadata_version,
            overridden_fields=paper.overridden_fields,
        )
        for paper in items
    ]


@router.post("/upload", status_code=202)
async def upload(
    db: DB,
    queue: QueueDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(max_length=1000)] = "",
    authors: Annotated[str, Form(max_length=4000)] = "",
    year: Annotated[int | None, Form(ge=1000, le=2100)] = None,
    venue: Annotated[str | None, Form(max_length=256)] = None,
) -> UploadRunResponse:
    try:
        reject_credentials([title, authors, venue])
    except ValueError:
        raise HTTPException(422, "credential_content_not_allowed") from None
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    path = settings.data_dir / f"{new_id()}.pdf"
    digest, size, prefix = hashlib.sha256(), 0, b""
    try:
        with path.open("wb") as target:
            while part := await file.read(65536):
                prefix = (prefix + part)[:5]
                size += len(part)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, "pdf_too_large")
                digest.update(part)
                target.write(part)
        if prefix != b"%PDF-":
            raise HTTPException(422, "invalid_pdf")
        sha = digest.hexdigest()
        if any(len(name.strip()) > 256 for name in authors.split(";")):
            raise HTTPException(422, "author_name_too_long")
        lifecycle_lock(db)
        # Distinct pinned arXiv versions can have identical PDF bytes. A plain
        # upload reuses an indexed copy first, then an uploaded/most recent copy.
        duplicate = (
            select(Paper)
            .where(Paper.sha256 == sha)
            .order_by(
                (Paper.status == "indexed").desc(),
                Paper.arxiv_id.is_(None).desc(),
                Paper.created_at.desc(),
                Paper.id,
            )
            .limit(1)
        )
        existing = db.scalar(duplicate)
        if existing:
            path.unlink(missing_ok=True)
            return ingestion_run(db, queue, existing.id)
        names = list(dict.fromkeys(x.strip() for x in authors.split(";") if x.strip()))
        initial_title = (title.strip() or (file.filename or "").strip() or "Untitled")[:1000]
        try:
            original = OriginalPaperMetadata(
                kind="upload_user",
                captured_at=datetime.now(UTC),
                values=PaperMetadataValues(
                    title=initial_title, authors=names, year=year, venue=venue
                ),
                pdf_sha256=sha,
            ).model_dump(mode="json")
        except ValueError:
            raise HTTPException(422, "invalid_metadata") from None
        paper_id = db.scalar(
            insert(Paper)
            .values(
                title=initial_title,
                year=year,
                venue=venue,
                sha256=sha,
                original_path=str(path),
                original_metadata=original,
            )
            .on_conflict_do_nothing(
                index_elements=[Paper.sha256], index_where=Paper.arxiv_id.is_(None)
            )
            .returning(Paper.id)
        )
        if paper_id is None:
            existing = db.scalar(duplicate)
            if existing is None:
                raise HTTPException(409, "paper_changed_retry")
            path.unlink(missing_ok=True)
            return ingestion_run(db, queue, existing.id)
        ids = author_ids(db, names)
        for position, name in enumerate(names):
            db.add(PaperAuthor(paper_id=paper_id, author_id=ids[name], position=position))
        # Paper, author links, Run and dispatch intent become visible together.
        return UploadRunResponse(
            **RunResponse.model_validate(
                enqueue(db, queue, "ingestion", {"paper_id": paper_id})
            ).model_dump(),
            paper_id=paper_id,
            reused_existing=False,
        )
    except Exception:
        db.rollback()
        # Keep the original if the paper transaction was committed (e.g. queue outage).
        if not db.scalar(select(Paper.id).where(Paper.original_path == str(path))):
            path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.post("/arxiv", status_code=202)
def arxiv(request: ArxivRequest, db: DB, queue: QueueDep) -> RunResponse:
    lifecycle_lock(db)
    return RunResponse.model_validate(enqueue(db, queue, "arxiv", request.model_dump()))


@router.get("")
def papers(db: DB, limit: int = 50, offset: int = 0) -> list[PaperResponse]:
    if not 1 <= limit <= 200 or offset < 0:
        raise HTTPException(422, "invalid_pagination")
    return paper_responses(
        db,
        list(
            db.scalars(
                select(Paper)
                .order_by(Paper.created_at.desc(), Paper.id)
                .limit(limit)
                .offset(offset)
            )
        ),
    )


@router.get("/search")
def search_papers(
    db: DB, request: Request, query: Annotated[PaperSearchQuery, Query()]
) -> PaperPage:
    names = [key for key, _ in request.query_params.multi_items()]
    if len(names) != len(set(names)):
        raise HTTPException(422, "duplicate_search_parameter")
    statement = select(Paper.id)
    for text, column in [(query.title, Paper.title), (query.venue, Paper.venue)]:
        if text is not None:
            statement = statement.where(func.lower(column).contains(text.lower(), autoescape=True))
    if query.author is not None:
        statement = statement.where(
            select(PaperAuthor.paper_id)
            .join(Author)
            .where(
                PaperAuthor.paper_id == Paper.id,
                func.lower(Author.name).contains(query.author.lower(), autoescape=True),
            )
            .exists()
        )
    if query.year is not None:
        statement = statement.where(Paper.year == query.year)
    if query.status is not None:
        statement = statement.where(Paper.status == query.status)
    for collection_id, kind in [(query.group, "group"), (query.tag, "tag")]:
        if collection_id is not None:
            statement = statement.where(
                select(PaperCollectionMember.paper_id)
                .join(PaperCollection)
                .where(
                    PaperCollectionMember.paper_id == Paper.id,
                    PaperCollection.id == str(collection_id),
                    PaperCollection.kind == kind,
                )
                .exists()
            )
    matching = statement.cte("matching_papers")
    total = select(func.count().label("total")).select_from(matching).cte("matching_total")
    sort_column = Paper.created_at if query.sort == "created_at" else Paper.year
    order = (sort_column.asc() if query.direction == "asc" else sort_column.desc()).nulls_last()
    page = (
        select(Paper.id, sort_column.label("sort_value"))
        .join(matching, matching.c.id == Paper.id)
        .order_by(order, Paper.id)
        .limit(query.limit)
        .offset(query.offset)
        .cte("matching_page")
    )
    page_order = (
        page.c.sort_value.asc() if query.direction == "asc" else page.c.sort_value.desc()
    ).nulls_last()
    # Count and page IDs share one PostgreSQL statement snapshot, including an
    # empty/out-of-range page. EXISTS prevents duplicate rows from author joins.
    rows = db.execute(
        select(Paper, total.c.total)
        .select_from(total.outerjoin(page, true()).outerjoin(Paper, Paper.id == page.c.id))
        .order_by(page_order, page.c.id)
    ).all()
    return PaperPage(
        items=paper_responses(db, [paper for paper, _ in rows if paper is not None]),
        total=rows[0][1],
        limit=query.limit,
        offset=query.offset,
    )


@router.get("/{paper_id}")
def paper(paper_id: str, db: DB) -> PaperResponse:
    p = db.get(Paper, paper_id)
    if p is None:
        missing_paper(db, paper_id)
    return paper_response(db, p)


@router.get("/{paper_id}/pdf")
def original_pdf(paper_id: str, db: DB) -> FileResponse:
    p = db.get(Paper, paper_id)
    if p is None:
        missing_paper(db, paper_id)
    return FileResponse(
        p.original_path,
        media_type="application/pdf",
        filename=f"{p.id}.pdf",
        content_disposition_type="inline",
    )


@router.get("/{paper_id}/chunks")
def chunks(paper_id: str, db: DB, offset: int = 0, limit: int = 50) -> list[dict[str, object]]:
    if not 1 <= limit <= 200 or offset < 0:
        raise HTTPException(422, "invalid_pagination")
    if db.get(PaperDeletion, paper_id):
        raise HTTPException(410, "source_deleted")
    return [
        {
            "chunk_id": c.id,
            "section_id": c.section_id,
            "section_path": c.section_path,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "content": c.content,
            "element_type": c.element_type,
        }
        for c in db.scalars(
            select(Chunk)
            .where(Chunk.paper_id == paper_id)
            .order_by(Chunk.ordinal)
            .limit(limit)
            .offset(offset)
        )
    ]


@router.post("/{paper_id}/chunks/{chunk_id}/entities")
def annotate(
    paper_id: str, chunk_id: str, request: list[EntityAnnotation], db: DB
) -> dict[str, str]:
    from ragagent.domain.entities import EntityKind, MentionCreate, MentionPatch
    from ragagent.errors import ApplicationError
    from ragagent.ingestion.entity_review import decide, exact_name, locked_source, manual_mention
    from ragagent.ingestion.entity_service import source_hash

    try:
        chunk = locked_source(db, paper_id, chunk_id)
        digest = source_hash(chunk.content)
        spans = []
        # Existing manual route is still supported, but names must now occur
        # literally in this current chunk; never index an absent assertion.
        for annotation in request:
            start = chunk.content.find(annotation.name)
            if start < 0:
                raise ApplicationError("entity_source_mismatch")
            end = start + len(annotation.name)
            exact_name(chunk, start, end, digest)
            spans.append((annotation, start, end))
        for annotation, start, end in spans:
            if annotation.entity_type in {"dataset", "method", "metric"}:
                value = manual_mention(
                    db,
                    chunk,
                    MentionCreate(
                        entity_type=cast(EntityKind, annotation.entity_type),
                        span_start=start,
                        span_end=end,
                        expected_content_sha256=digest,
                    ),
                )
                decide(
                    db,
                    chunk,
                    value,
                    MentionPatch(
                        action="confirm",
                        expected_version=value.version,
                        expected_content_sha256=digest,
                    ),
                )
            else:
                eid = db.scalar(
                    insert(Entity)
                    .values(name=annotation.name, entity_type="other")
                    .on_conflict_do_nothing(index_elements=[Entity.name, Entity.entity_type])
                    .returning(Entity.id)
                )
                if eid is None:
                    eid = db.scalar(
                        select(Entity.id).where(
                            Entity.name == annotation.name, Entity.entity_type == "other"
                        )
                    )
                if eid is None:
                    raise ApplicationError("entity_changed_retry")
                db.execute(
                    insert(ChunkEntity)
                    .values(chunk_id=chunk.id, entity_id=eid)
                    .on_conflict_do_nothing(
                        index_elements=[ChunkEntity.chunk_id, ChunkEntity.entity_id]
                    )
                )
        db.commit()
        return {"status": "annotated"}
    except ApplicationError as exc:
        db.rollback()
        code = exc.code
        raise HTTPException(
            410
            if code == "source_deleted"
            else 404
            if code in {"paper_not_found", "chunk_not_found"}
            else 409,
            code,
        ) from None


@router.post("/{paper_id}/retry", status_code=202)
def retry_ingestion(paper_id: str, db: DB, queue: QueueDep) -> RunResponse:
    lifecycle_lock(db)
    paper = db.scalar(
        select(Paper)
        .where(Paper.id == paper_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if paper is None:
        missing_paper(db, paper_id)
    if paper.status not in {"failed", "queued"}:
        raise HTTPException(409, "paper_not_retryable")
    pending = db.scalar(
        select(Run)
        .where(
            Run.kind == "ingestion",
            Run.request["paper_id"].as_string() == paper.id,
            Run.status.in_(("queued", "running")),
        )
        .order_by(Run.created_at.desc(), Run.id)
        .limit(1)
    )
    if pending is not None:
        db.commit()
        if pending.status == "queued":
            dispatch_run(db, queue, pending.id)
        return RunResponse.model_validate(pending)
    paper.status, paper.error_code = "queued", None
    return RunResponse.model_validate(enqueue(db, queue, "ingestion", {"paper_id": paper.id}))


@router.patch("/{paper_id}")
def update_metadata(paper_id: str, request: PaperPatch, db: DB) -> PaperResponse:
    lifecycle_lock(db)
    paper = db.scalar(
        select(Paper)
        .where(Paper.id == paper_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if paper is None:
        missing_paper(db, paper_id)
    if request.expected_metadata_version is not None and (
        request.expected_metadata_version != paper.metadata_version
    ):
        raise HTTPException(409, "paper_metadata_conflict")
    if "title" in request.model_fields_set and request.title is None:
        raise HTTPException(422, "title_cannot_be_null")
    if "source_status" in request.model_fields_set and request.source_status is None:
        raise HTTPException(422, "source_status_cannot_be_null")
    changed: set[str] = set()
    for field in ["title", "year", "venue", "source_status"]:
        if field in request.model_fields_set:
            value = getattr(request, field)
            if value != getattr(paper, field):
                changed.add(field)
                setattr(paper, field, value)
    if "authors" in request.model_fields_set:
        names = list(dict.fromkeys(n.strip() for n in request.authors or []))
        if any(not n or len(n) > 256 for n in names):
            raise HTTPException(422, "invalid_author_name")
        current = list(
            db.scalars(
                select(Author.name)
                .join(PaperAuthor)
                .where(PaperAuthor.paper_id == paper.id)
                .order_by(PaperAuthor.position)
            )
        )
        if names != current:
            changed.add("authors")
            db.execute(delete(PaperAuthor).where(PaperAuthor.paper_id == paper.id))
            ids = author_ids(db, names)
            for position, name in enumerate(names):
                db.add(PaperAuthor(paper_id=paper.id, author_id=ids[name], position=position))
    if changed:
        paper.metadata_version += 1
        paper.overridden_fields = sorted(
            set(paper.overridden_fields) | (changed - {"source_status"})
        )
    db.commit()
    return paper_response(db, paper)


def missing_paper(db: Session, paper_id: str) -> NoReturn:
    if db.get(PaperDeletion, paper_id):
        raise HTTPException(410, "source_deleted")
    raise HTTPException(404, "paper_not_found")
