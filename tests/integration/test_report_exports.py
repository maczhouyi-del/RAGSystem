"""Real PostgreSQL/API exports; synthetic reports and no provider/queue calls."""

import csv
import io

import pytest
from sqlalchemy import func, select

from ragagent.db.models import Conversation, ExecutionEvent, Message, Run
from ragagent.deletion.history import SourceIds, redact
from ragagent.domain.exports import EXPORT_TYPES, export_run
from tests.integration.test_api import client as client
from tests.unit.test_exports import report_result

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("filename", list(EXPORT_TYPES))
def test_pg_exports_match_persisted_products_without_mutation(client, empty_db, filename):
    result = report_result()
    run = Run(
        kind="research", status="completed", result=result, request={"research_question": "DEMO"}
    )
    empty_db.add(run)
    empty_db.flush()
    before_events = empty_db.scalar(select(func.count()).select_from(ExecutionEvent))
    response = client.get(f"/api/runs/{run.id}/exports/{filename}")
    assert response.status_code == 200
    assert response.content == export_run(run.id, run.kind, run.status, result, filename).content
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="ragagent-{run.id}-{filename}"'
    )
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    empty_db.refresh(run)
    assert run.result == result and run.status == "completed"
    assert empty_db.scalar(select(func.count()).select_from(ExecutionEvent)) == before_events
    assert empty_db.scalar(select(func.count()).select_from(Run)) == 1


@pytest.mark.parametrize("kind", ["rag", "research"])
def test_legacy_visible_message_exports_without_rewriting_run(client, empty_db, kind):
    conversation = Conversation(mode=kind, title="DEMO old report")
    empty_db.add(conversation)
    empty_db.flush()
    run = Run(
        kind=kind, status="completed", result=None, conversation_id=conversation.id, request={}
    )
    empty_db.add(run)
    empty_db.flush()
    body = "旧报告科研数字 -0.3 / 91.5 %；条件 CPU。"
    empty_db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=body,
            ordinal=0,
            run_id=run.id,
            status="completed",
        )
    )
    empty_db.flush()
    response = client.get(f"/api/runs/{run.id}/exports/report.md")
    assert response.status_code == 200 and response.text == body
    csv_response = client.get(f"/api/runs/{run.id}/exports/comparison.csv")
    rows = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
    assert (
        rows[0]["legacy_report"] == body
        and rows[0]["verification_status"] == "legacy_review_unknown"
    )
    empty_db.refresh(run)
    assert run.result is None


def test_retired_source_exports_mark_history_without_restoring_source_text(client, empty_db):
    result = report_result()
    item = result["evidence_pool"][0]
    retired = redact(
        result, SourceIds(papers={item["paper"]["paper_id"]}, evidence={item["evidence_id"]})
    )
    run = Run(kind="research", status="completed", result=retired, request={})
    empty_db.add(run)
    empty_db.flush()
    response = client.get(f"/api/runs/{run.id}/exports/citations.json")
    assert response.status_code == 200
    data = response.json()
    assert data["verification_status"] == "historical_unverifiable"
    assert data["references"][0]["source_availability"] == "unavailable"
    empty_db.refresh(run)
    assert run.result["evidence_pool"][0]["quote"] == ""
    assert (
        run.result["structured_report"]["rows"][0]["fields"]["participants"]["source_literal"]
        is None
    )


@pytest.mark.parametrize("status", ["queued", "running", "failed", "cancelled"])
def test_api_does_not_export_unreleased_drafts(client, empty_db, status):
    run = Run(kind="research", status=status, result=report_result(), request={})
    empty_db.add(run)
    empty_db.flush()
    response = client.get(f"/api/runs/{run.id}/exports/report.md")
    assert response.status_code == 409 and response.json()["error_code"] == "report_not_released"
    assert "91.5" not in response.text


def test_export_names_auth_and_paths_cannot_become_filesystem_access(client, empty_db):
    run = Run(kind="research", status="completed", result=report_result(), request={})
    empty_db.add(run)
    empty_db.flush()
    for filename in ["report.exe", "..%5Creport.md", "%2e%2e%2freport.md"]:
        assert client.get(f"/api/runs/{run.id}/exports/{filename}").status_code == 404
    assert client.get("/api/runs/not-a-uuid/exports/report.md").status_code == 404
    assert (
        client.get(
            f"/api/runs/{run.id}/exports/report.md", headers={"Authorization": "Bearer invalid"}
        ).status_code
        == 401
    )
    assert client.post(f"/api/runs/{run.id}/exports/report.md").status_code == 405
