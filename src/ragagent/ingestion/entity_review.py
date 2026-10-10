"""Per-source manual decisions; shared entity names never change globally."""

from datetime import UTC, datetime
from unicodedata import category

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ragagent.db.models import (
    Chunk,
    ChunkAnnotationReview,
    ChunkEntity,
    Dataset,
    Entity,
    EntityMention,
    Method,
    Metric,
    Paper,
    Run,
)
from ragagent.deletion.guards import guard_sources
from ragagent.domain.entities import MentionCreate, MentionPatch
from ragagent.domain.privacy import reject_credentials
from ragagent.errors import ApplicationError
from ragagent.ingestion.entity_service import source_hash


def locked_source(db: Session, pid: str, cid: str) -> Chunk:
    guard_sources(db, {"paper_id": pid})
    paper = db.scalar(
        select(Paper)
        .where(Paper.id == pid)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if paper is None:
        raise ApplicationError("paper_not_found")
    active = db.scalar(
        select(Run.id)
        .where(
            Run.kind == "entity_annotation",
            Run.request["paper_id"].as_string() == pid,
            Run.status.in_(("queued", "running")),
        )
        .limit(1)
    )
    if active:
        raise ApplicationError("annotation_busy")
    chunk = db.scalar(
        select(Chunk)
        .where(Chunk.id == cid, Chunk.paper_id == pid)
        .execution_options(populate_existing=True)
    )
    if chunk is None:
        raise ApplicationError("chunk_not_found")
    return chunk


def exact_name(chunk: Chunk, start: int, end: int, digest: str) -> str:
    if source_hash(chunk.content) != digest:
        raise ApplicationError("annotation_source_changed")
    if not 0 <= start < end <= len(chunk.content):
        raise ApplicationError("entity_span_invalid")
    name = chunk.content[start:end]
    if (
        not name
        or name != name.strip()
        or len(name) > 256
        or any(category(c) == "Cc" for c in name)
    ):
        raise ApplicationError("entity_name_invalid")
    try:
        reject_credentials(name)
    except ValueError:
        raise ApplicationError("entity_name_invalid") from None
    return name


def require_review(db: Session, chunk: Chunk) -> None:
    record = db.get(ChunkAnnotationReview, chunk.id)
    if record is None:
        record = ChunkAnnotationReview(
            chunk_id=chunk.id, content_sha256=source_hash(chunk.content), status="needs_review"
        )
        db.add(record)
    digest = source_hash(chunk.content)
    if record.content_sha256 != digest:
        record.extractor_version = None
        record.run_id = None
    record.content_sha256 = digest
    record.status = "needs_review"
    record.updated_at = datetime.now(UTC)


def manual_mention(db: Session, chunk: Chunk, request: MentionCreate) -> EntityMention:
    name = exact_name(chunk, request.span_start, request.span_end, request.expected_content_sha256)
    existing = db.scalar(
        select(EntityMention).where(
            EntityMention.chunk_id == chunk.id,
            EntityMention.entity_type == request.entity_type,
            EntityMention.name == name,
            EntityMention.span_start == request.span_start,
            EntityMention.span_end == request.span_end,
            EntityMention.content_sha256 == request.expected_content_sha256,
        )
    )
    if existing:
        return existing
    value = EntityMention(
        chunk_id=chunk.id,
        name=name,
        entity_type=request.entity_type,
        span_start=request.span_start,
        span_end=request.span_end,
        content_sha256=request.expected_content_sha256,
        state="proposed",
        origin="manual-source-v1",
    )
    db.add(value)
    require_review(db, chunk)
    db.flush()
    return value


def detach_owned_link(db: Session, value: EntityMention) -> None:
    if not value.owns_link or value.entity_id is None:
        return
    # Preserve other confirmed occurrences and pre-existing legacy links. When
    # an owned link is shared, transfer ownership rather than removing it.
    other = db.scalar(
        select(EntityMention)
        .where(
            EntityMention.chunk_id == value.chunk_id,
            EntityMention.entity_id == value.entity_id,
            EntityMention.state == "confirmed",
            EntityMention.id != value.id,
        )
        .order_by(EntityMention.id)
        .limit(1)
    )
    if other:
        other.owns_link = True
    else:
        db.execute(
            delete(ChunkEntity).where(
                ChunkEntity.chunk_id == value.chunk_id, ChunkEntity.entity_id == value.entity_id
            )
        )
    value.owns_link = False


def confirm_link(db: Session, value: EntityMention) -> None:
    # Stable per-paper occurrence mutation under Paper lock; independent papers
    # converge on shared exact names using the existing unique constraint.
    eid = db.scalar(
        insert(Entity)
        .values(name=value.name, entity_type=value.entity_type)
        .on_conflict_do_nothing(index_elements=[Entity.name, Entity.entity_type])
        .returning(Entity.id)
    )
    if eid is None:
        eid = db.scalar(
            select(Entity.id).where(
                Entity.name == value.name, Entity.entity_type == value.entity_type
            )
        )
    if eid is None:
        raise ApplicationError("entity_changed_retry")
    subtype = {"dataset": Dataset, "method": Method, "metric": Metric}[value.entity_type]
    db.execute(
        insert(subtype).values(entity_id=eid).on_conflict_do_nothing(index_elements=["entity_id"])
    )
    inserted = db.scalar(
        insert(ChunkEntity)
        .values(chunk_id=value.chunk_id, entity_id=eid)
        .on_conflict_do_nothing(index_elements=[ChunkEntity.chunk_id, ChunkEntity.entity_id])
        .returning(ChunkEntity.chunk_id)
    )
    value.entity_id = eid
    value.owns_link = inserted is not None


def decide(db: Session, chunk: Chunk, value: EntityMention, request: MentionPatch) -> EntityMention:
    if value.version != request.expected_version:
        raise ApplicationError("entity_version_conflict")
    if source_hash(chunk.content) != request.expected_content_sha256:
        raise ApplicationError("annotation_source_changed")
    if request.action != "reject":
        if value.content_sha256 != request.expected_content_sha256:
            raise ApplicationError("annotation_source_changed")
        if (
            exact_name(chunk, value.span_start, value.span_end, request.expected_content_sha256)
            != value.name
        ):
            raise ApplicationError("entity_source_mismatch")
    if (
        request.action in {"confirm", "reject"}
        and value.state == {"confirm": "confirmed", "reject": "rejected"}[request.action]
    ):
        return value
    detach_owned_link(db, value)
    value.entity_id = None
    if request.action == "correct":
        assert (
            request.span_start is not None
            and request.span_end is not None
            and request.entity_type is not None
        )
        value.name = exact_name(
            chunk, request.span_start, request.span_end, request.expected_content_sha256
        )
        value.span_start, value.span_end, value.entity_type = (
            request.span_start,
            request.span_end,
            request.entity_type,
        )
        value.alias_group = None
        value.origin = "manual-correction-v1"
        value.state = "proposed"
    elif request.action == "confirm":
        confirm_link(db, value)
        value.state = "confirmed"
    else:
        value.state = "rejected"
    value.version += 1
    value.updated_at = datetime.now(UTC)
    require_review(db, chunk)
    db.flush()
    return value
