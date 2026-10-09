"""Organization CRUD and idempotent individual membership; no ingestion jobs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import delete, func, select, true
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from ragagent.api.papers import DB, missing_paper
from ragagent.db.models import Paper, PaperCollection, PaperCollectionMember
from ragagent.deletion.guards import lifecycle_lock
from ragagent.domain.collections import (
    CollectionCreate,
    CollectionDelete,
    CollectionListQuery,
    CollectionPage,
    CollectionPatch,
    CollectionResponse,
    name_key,
)

router = APIRouter(tags=["paper organization"])


def collection_response(db: DB, collection: PaperCollection) -> CollectionResponse:
    count = db.scalar(
        select(func.count())
        .select_from(PaperCollectionMember)
        .where(PaperCollectionMember.collection_id == collection.id)
    )
    return CollectionResponse(
        id=collection.id,
        kind=collection.kind,
        name=collection.name,
        version=collection.version,
        paper_count=count or 0,
    )


def locked_collection(db: DB, collection_id: str) -> PaperCollection:
    collection = db.scalar(
        select(PaperCollection)
        .where(PaperCollection.id == collection_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if collection is None:
        raise HTTPException(404, "collection_not_found")
    return collection


def commit_name(db: DB) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "collection_name_conflict") from None


@router.get("/api/collections")
def list_collections(
    db: DB, request: Request, query: Annotated[CollectionListQuery, Query()]
) -> CollectionPage:
    names = [key for key, _ in request.query_params.multi_items()]
    if len(names) != len(set(names)):
        raise HTTPException(422, "duplicate_search_parameter")
    total = select(func.count().label("total")).select_from(PaperCollection).cte("collection_total")
    page = (
        select(PaperCollection)
        .order_by(PaperCollection.kind, PaperCollection.name_key, PaperCollection.id)
        .limit(query.limit)
        .offset(query.offset)
        .cte("collection_page")
    )
    counts = (
        select(PaperCollectionMember.collection_id, func.count().label("paper_count"))
        .group_by(PaperCollectionMember.collection_id)
        .cte("collection_counts")
    )
    rows = (
        db.execute(
            select(page, total.c.total, func.coalesce(counts.c.paper_count, 0).label("paper_count"))
            .select_from(
                total.outerjoin(page, true()).outerjoin(counts, counts.c.collection_id == page.c.id)
            )
            .order_by(page.c.kind, page.c.name_key, page.c.id)
        )
        .mappings()
        .all()
    )
    return CollectionPage(
        items=[CollectionResponse.model_validate(row) for row in rows if row["id"] is not None],
        total=rows[0]["total"],
        limit=query.limit,
        offset=query.offset,
    )


@router.post("/api/collections", status_code=201)
def create_collection(body: CollectionCreate, db: DB) -> CollectionResponse:
    collection = PaperCollection(kind=body.kind, name=body.name, name_key=name_key(body.name))
    db.add(collection)
    commit_name(db)
    return collection_response(db, collection)


@router.get("/api/collections/{collection_id}")
def read_collection(collection_id: UUID, db: DB) -> CollectionResponse:
    collection = db.get(PaperCollection, str(collection_id))
    if collection is None:
        raise HTTPException(404, "collection_not_found")
    return collection_response(db, collection)


@router.patch("/api/collections/{collection_id}")
def rename_collection(collection_id: UUID, body: CollectionPatch, db: DB) -> CollectionResponse:
    collection = locked_collection(db, str(collection_id))
    if collection.version != body.expected_version:
        raise HTTPException(409, "collection_version_conflict")
    if collection.name != body.name:
        collection.name, collection.name_key = body.name, name_key(body.name)
        collection.version += 1
    commit_name(db)
    return collection_response(db, collection)


@router.delete("/api/collections/{collection_id}", status_code=204)
def delete_collection(collection_id: UUID, body: CollectionDelete, db: DB) -> Response:
    if collection_id != body.confirm_collection_id:
        raise HTTPException(409, "collection_confirmation_mismatch")
    collection = locked_collection(db, str(collection_id))
    if collection.version != body.expected_version:
        raise HTTPException(409, "collection_version_conflict")
    db.delete(collection)
    db.commit()
    return Response(status_code=204)


@router.get("/api/papers/{paper_id}/collections")
def paper_collections(paper_id: UUID, db: DB) -> list[CollectionResponse]:
    pid = str(paper_id)
    if db.get(Paper, pid) is None:
        missing_paper(db, pid)
    # One membership read, not a fetch for every label or all paper contents.
    counts = (
        select(PaperCollectionMember.collection_id, func.count().label("paper_count"))
        .group_by(PaperCollectionMember.collection_id)
        .subquery()
    )
    rows = db.execute(
        select(PaperCollection, counts.c.paper_count)
        .join(PaperCollectionMember)
        .join(counts, counts.c.collection_id == PaperCollection.id)
        .where(PaperCollectionMember.paper_id == pid)
        .order_by(PaperCollection.kind, PaperCollection.name_key, PaperCollection.id)
    )
    return [
        CollectionResponse(id=c.id, kind=c.kind, name=c.name, version=c.version, paper_count=count)
        for c, count in rows
    ]


def membership_paper(db: DB, paper_id: str) -> None:
    lifecycle_lock(db)
    if db.scalar(select(Paper.id).where(Paper.id == paper_id).with_for_update()) is None:
        missing_paper(db, paper_id)


@router.put("/api/papers/{paper_id}/collections/{collection_id}", status_code=204)
def add_member(paper_id: UUID, collection_id: UUID, db: DB) -> Response:
    membership_paper(db, str(paper_id))
    locked_collection(db, str(collection_id))
    db.execute(
        insert(PaperCollectionMember)
        .values(paper_id=str(paper_id), collection_id=str(collection_id))
        .on_conflict_do_nothing()
    )
    db.commit()
    return Response(status_code=204)


@router.delete("/api/papers/{paper_id}/collections/{collection_id}", status_code=204)
def remove_member(paper_id: UUID, collection_id: UUID, db: DB) -> Response:
    membership_paper(db, str(paper_id))
    locked_collection(db, str(collection_id))
    db.execute(
        delete(PaperCollectionMember).where(
            PaperCollectionMember.paper_id == str(paper_id),
            PaperCollectionMember.collection_id == str(collection_id),
        )
    )
    db.commit()
    return Response(status_code=204)
