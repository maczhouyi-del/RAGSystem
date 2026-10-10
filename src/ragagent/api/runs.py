import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, select

from ragagent.api.papers import DB, QueueDep, enqueue
from ragagent.api.schemas import QueryRequest, ResearchRequest, RunResponse
from ragagent.db.models import ExecutionEvent, Message, Run
from ragagent.db.session import session_factory
from ragagent.domain.exports import export_run
from ragagent.domain.run_metrics import RunMetrics, run_metrics
from ragagent.jobs import TERMINAL_STATUSES, cancel_run

router = APIRouter(tags=["runs"])


@router.get("/api/runs/{run_id}/metrics")
def metrics(run_id: UUID, db: DB) -> RunMetrics:
    # Project accounting only: historical scientific result/event bodies stay unloaded.
    record = db.execute(
        select(
            Run.id,
            Run.kind,
            Run.status,
            Run.error_code,
            Run.created_at,
            Run.result["usage"],
            Run.result["usage_scope"],
        ).where(Run.id == str(run_id))
    ).first()
    if record is None:
        raise HTTPException(404, "run_not_found")
    timings = db.execute(
        select(
            ExecutionEvent.node,
            ExecutionEvent.created_at,
            ExecutionEvent.payload["execution_timing"],
        )
        .where(ExecutionEvent.run_id == str(run_id))
        .order_by(ExecutionEvent.id)
    ).all()
    return run_metrics(
        run_id=record[0],
        kind=record[1],
        status=record[2],
        error_code=record[3],
        created_at=record[4],
        usage=record[5],
        usage_scope=record[6],
        events=[(row[0], row[1], row[2]) for row in timings],
    )


@router.get("/api/runs/{run_id}/exports/{filename}")
def export(run_id: str, filename: str, db: DB) -> Response:
    try:
        UUID(run_id)
    except ValueError:
        raise HTTPException(404, "run_not_found") from None
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run_not_found")
    result = dict(run.result or {})
    body_key = "draft_report" if run.kind == "research" else "answer"
    if not result.get(body_key) and run.status in {"completed", "insufficient_evidence"}:
        message = db.scalar(
            select(Message)
            .where(Message.run_id == run.id, Message.role == "assistant")
            .order_by(Message.ordinal.desc())
            .limit(1)
        )
        if message and message.content:
            result[body_key] = message.content
            if message.metadata_json.get("source_availability") == "unavailable":
                result["source_availability"] = "unavailable"
    try:
        artifact = export_run(run.id, run.kind, run.status, result, filename)
    except ValueError as exc:
        code = str(exc)
        raise HTTPException(
            413 if code == "export_too_large" else 409 if code.startswith("report_") else 404, code
        ) from None
    return Response(
        artifact.content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/api/rag/query", status_code=202)
def rag(request: QueryRequest, db: DB, queue: QueueDep) -> RunResponse:
    return RunResponse.model_validate(enqueue(db, queue, "rag", request.model_dump()))


@router.post("/api/research", status_code=202)
def research(request: ResearchRequest, db: DB, queue: QueueDep) -> RunResponse:
    return RunResponse.model_validate(enqueue(db, queue, "research", request.model_dump()))


@router.get("/api/runs/{run_id}")
@router.get("/api/research/{run_id}")
@router.get("/api/rag/{run_id}")
def status(run_id: str, db: DB) -> RunResponse:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run_not_found")
    return RunResponse.model_validate(run)


@router.post("/api/runs/{run_id}/cancel")
def cancel(run_id: str, db: DB, queue: QueueDep) -> RunResponse:
    existing = db.get(Run, run_id)
    if existing is None:
        raise HTTPException(404, "run_not_found")
    if existing.kind not in {"rag", "research"}:
        raise HTTPException(409, "run_cancel_not_supported")
    run = cancel_run(db, run_id)
    if run is None:
        raise HTTPException(404, "run_not_found")
    stop = getattr(queue, "cancel", None)
    if run.status == "cancelled" and stop is not None:
        try:
            stop(run.id)
        except Exception:
            # Database ownership is already revoked; Redis failure cannot restore it.
            pass
    return RunResponse.model_validate(run)


async def stream_events(run_id: str, request: Request, cursor: int) -> AsyncIterator[str]:
    while not await request.is_disconnected():
        # Short-lived sessions do not hold a connection during SSE idle time.
        with session_factory()() as session:
            run = session.get(Run, run_id)
            if run is None:
                return
            terminal = run.status in TERMINAL_STATUSES
            # The worker commits its terminal state and final event together. Read
            # the state first, then drain through this stable terminal event watermark.
            watermark = (
                session.scalar(
                    select(func.max(ExecutionEvent.id)).where(ExecutionEvent.run_id == run_id)
                )
                or 0
                if terminal
                else None
            )
            statement = (
                select(ExecutionEvent)
                .where(ExecutionEvent.run_id == run_id, ExecutionEvent.id > cursor)
                .order_by(ExecutionEvent.id)
                .limit(100)
            )
            if watermark is not None:
                statement = statement.where(ExecutionEvent.id <= watermark)
            events = list(session.scalars(statement))
            batch = []
            for event in events:
                cursor = event.id
                payload = json.dumps(
                    {
                        "node": event.node,
                        "payload": event.payload,
                        "time": event.created_at.isoformat(),
                    }
                )
                batch.append(f"id: {event.id}\nevent: execution\ndata: {payload}\n\n")
            done = watermark is not None and cursor >= watermark
            final = RunResponse.model_validate(run).model_dump_json() if done else None
        for message in batch:
            yield message
        if final is not None:
            yield f"event: done\ndata: {final}\n\n"
            return
        if terminal and events:
            continue  # Drain a completed run without idle delay between replay pages.
        yield ": heartbeat\n\n"
        await asyncio.sleep(1)


@router.get("/api/runs/{run_id}/events")
@router.get("/api/research/{run_id}/events")
@router.get("/api/rag/{run_id}/events")
def events(
    run_id: str,
    request: Request,
    db: DB,
    after: int = 0,
    last_event_id: str | None = Header(default=None),
) -> StreamingResponse:
    if db.get(Run, run_id) is None:
        raise HTTPException(404, "run_not_found")
    try:
        cursor = int(last_event_id) if last_event_id else after
    except ValueError:
        raise HTTPException(422, "invalid_event_cursor") from None
    if cursor < 0:
        raise HTTPException(422, "invalid_event_cursor")
    db.rollback()  # Release the request session connection before the long-lived stream.
    return StreamingResponse(
        stream_events(run_id, request, cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
