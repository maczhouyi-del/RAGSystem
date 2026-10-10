"""Real PostgreSQL accounting reads and worker checkpoints; no paid requests."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from ragagent.db.models import ExecutionEvent, Run
from ragagent.errors import ApplicationError
from ragagent.jobs import cancel_run
from ragagent.providers.chat import Usage, usage_record
from ragagent.worker import persist_usage, track_usage
from tests.integration.test_api import client as client
from tests.unit.test_run_metrics import measured

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "status", ["completed", "failed", "cancelled", "running", "insufficient_evidence"]
)
def test_persisted_metrics_are_run_specific_read_only_and_keep_missing_values(
    client, empty_db, status
):
    at = datetime(2026, 10, 10, tzinfo=UTC)
    result = {
        "usage": {"analyst": usage_record(measured())},
        "usage_scope": "current_attempt",
        "draft_report": "PRIVATE_SCIENTIFIC_TEXT",
        "api_key": "PRIVATE_SECRET",
    }
    run = Run(kind="research", status=status, result=result, request={}, created_at=at)
    other = Run(kind="rag", status="failed", result=None, request={})
    empty_db.add_all([run, other])
    empty_db.flush()
    empty_db.add_all(
        [
            ExecutionEvent(
                run_id=run.id, node="started", created_at=at + timedelta(seconds=3), payload={}
            ),
            ExecutionEvent(
                run_id=run.id,
                node="analysis",
                created_at=at + timedelta(seconds=5),
                payload={
                    "execution_timing": {"elapsed_seconds": 2, "basis": "node_interval"},
                    "private": "PRIVATE_EVENT",
                },
            ),
            ExecutionEvent(
                run_id=run.id,
                node="finished" if status != "running" else "reviewer",
                created_at=at + timedelta(seconds=8),
                payload={},
            ),
        ]
    )
    empty_db.flush()
    response = client.get(f"/api/runs/{run.id}/metrics")
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
    data = response.json()
    assert data["run_id"] == run.id and data["status"] == status
    assert data["known_estimate_usd"] == 0.012 and data["exact_provider_bill_usd"] is None
    assert data["input_tokens"]["known"] == 10 and data["output_tokens"]["known"] == 0
    assert data["phases"][0]["seconds"] == 2
    assert data["total_seconds"] == 8 if status != "running" else data["duration_live"]
    assert "PRIVATE" not in response.text
    empty_db.refresh(run)
    assert run.result == result and run.status == status
    assert empty_db.scalar(select(func.count()).select_from(ExecutionEvent)) == 3
    other_data = client.get(f"/api/runs/{other.id}/metrics").json()
    assert other_data["input_tokens"]["known"] is None and other_data["known_estimate_usd"] is None


def test_metrics_auth_missing_run_methods_and_uuid_boundary(client, empty_db):
    run = Run(kind="rag", request={})
    empty_db.add(run)
    empty_db.flush()
    assert (
        client.get(
            f"/api/runs/{run.id}/metrics", headers={"Authorization": "Bearer invalid"}
        ).status_code
        == 401
    )
    assert client.get("/api/runs/00000000-0000-4000-8000-000000000016/metrics").status_code == 404
    assert client.get("/api/runs/not-a-uuid/metrics").status_code == 422
    assert client.post(f"/api/runs/{run.id}/metrics").status_code == 405


def test_cancellation_can_enrich_only_previously_dispatched_charge(client, empty_db):
    run = Run(kind="rag", status="running", request={})
    empty_db.add(run)
    empty_db.flush()
    usage = Usage(configured_model="openai/DEMO", cost_basis="sdk_estimate")
    tracked = {"analyst": usage}
    usage.begin_call()
    persist_usage(empty_db, run, tracked)
    cancel_run(empty_db, run.id)
    before = client.get(f"/api/runs/{run.id}/metrics").json()
    assert before["status"] == "cancelled" and before["known_estimate_usd"] is None
    assert before["usages"][0]["in_flight_calls"] == 1
    usage.record_tokens(12, 3)
    usage.record_cost(0.2)
    with pytest.raises(ApplicationError, match="run_no_longer_active"):
        persist_usage(empty_db, run, tracked)
    after = client.get(f"/api/runs/{run.id}/metrics").json()
    assert after["status"] == "cancelled" and after["known_estimate_usd"] == 0.2
    assert after["input_tokens"]["known"] == 12 and after["usages"][0]["in_flight_calls"] == 0
    usage.begin_call()
    with pytest.raises(ApplicationError, match="run_no_longer_active"):
        persist_usage(empty_db, run, tracked)
    assert client.get(f"/api/runs/{run.id}/metrics").json()["usages"][0]["calls"] == 1


def test_per_run_reset_preserves_frozen_model_and_cost_basis(empty_db):
    run = Run(kind="rag", status="running", request={})
    empty_db.add(run)
    empty_db.flush()
    provider = SimpleNamespace(usage=measured())
    tracked = {}
    track_usage(empty_db, run, tracked, "analyst", provider)
    assert (
        provider.usage.configured_model == "openai/DEMO"
        and provider.usage.cost_basis == "sdk_estimate"
    )
    assert provider.usage.calls == 0 and provider.usage.prompt_tokens == 0
