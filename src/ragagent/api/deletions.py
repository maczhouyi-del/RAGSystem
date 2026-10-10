"""Confirmation and status/retry APIs for current-library removal."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from ragagent.api.papers import DB, QueueDep
from ragagent.db.models import Paper, PaperDeletion, Run
from ragagent.deletion.guards import lifecycle_lock
from ragagent.deletion.service import cleanup_run, preview, response, retire
from ragagent.domain.deletion import PaperDeleteRequest, PaperDeletionPreview, PaperDeletionResponse
from ragagent.errors import ApplicationError
from ragagent.jobs import dispatch_run

router = APIRouter(prefix="/api/papers", tags=["paper deletion"])


@router.get("/{paper_id}/deletion-preview")
def deletion_preview(paper_id: str, db: DB) -> PaperDeletionPreview:
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(
            410 if db.get(PaperDeletion, paper_id) else 404,
            "source_deleted" if db.get(PaperDeletion, paper_id) else "paper_not_found",
        )
    return preview(db, paper)


@router.delete("/{paper_id}", status_code=202)
def delete_paper(
    paper_id: str, request: PaperDeleteRequest, db: DB, queue: QueueDep
) -> PaperDeletionResponse:
    try:
        ledger = retire(db, paper_id, request)
        db.commit()
    except ApplicationError as exc:
        db.rollback()
        raise HTTPException(404 if exc.code == "paper_not_found" else 409, exc.code) from None
    dispatch_run(db, queue, ledger.last_cleanup_run_id)
    return response(db, ledger)


@router.get("/{paper_id}/deletion")
def deletion_status(paper_id: str, db: DB) -> PaperDeletionResponse:
    ledger = db.get(PaperDeletion, paper_id)
    if ledger is None:
        raise HTTPException(404, "paper_deletion_not_found")
    return response(db, ledger)


@router.post("/{paper_id}/deletion/retry", status_code=202)
def retry_cleanup(paper_id: str, db: DB, queue: QueueDep) -> PaperDeletionResponse:
    lifecycle_lock(db)
    ledger = db.scalar(
        select(PaperDeletion)
        .where(PaperDeletion.paper_id == paper_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if ledger is None:
        raise HTTPException(404, "paper_deletion_not_found")
    previous = db.get(Run, ledger.last_cleanup_run_id)
    assert previous is not None
    if previous.status in {"failed", "cancelled"}:
        ledger.last_cleanup_run_id = cleanup_run(db, paper_id).id
    db.commit()
    dispatch_run(db, queue, ledger.last_cleanup_run_id)
    return response(db, ledger)
