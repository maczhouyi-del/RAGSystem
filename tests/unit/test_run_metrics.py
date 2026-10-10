"""Synthetic accounting contracts; no real provider billing or scientific benchmark."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from ragagent.domain.run_metrics import run_metrics, usage_metric
from ragagent.evaluation.artifacts import usage_delta, usage_snapshot
from ragagent.providers.chat import Usage, usage_record

START = datetime(2026, 10, 10, tzinfo=UTC)


def summarize(usage=None, status="completed", events=None, **kwargs):
    return run_metrics(
        "00000000-0000-4000-8000-000000000016",
        "research",
        status,
        kwargs.pop("error_code", None),
        START,
        usage,
        "current_attempt",
        events or [],
        now=START + timedelta(seconds=20),
        **kwargs,
    )


def measured():
    usage = Usage(configured_model="openai/DEMO", cost_basis="sdk_estimate")
    usage.begin_call()
    usage.record_tokens(10, 0)
    usage.record_identity("DEMO-returned")
    usage.record_cost(0.012)
    return usage


def test_known_zero_is_distinct_from_missing_tokens_and_no_call():
    known = summarize({"analyst": usage_record(measured()), "reviewer": usage_record(Usage())})
    assert known.input_tokens.known == 10 and known.input_tokens.complete
    assert known.output_tokens.known == 0 and known.output_tokens.complete
    assert known.known_estimate_usd == 0.012 and known.estimate_complete
    assert known.exact_provider_bill_usd is None
    assert known.usages[1].input_tokens.known is None
    assert known.usages[0].configured_model == "openai/DEMO"
    assert known.usages[0].returned_models == ["DEMO-returned"]
    missing = summarize({"analyst": usage_record(Usage())})
    assert missing.input_tokens.known is None and missing.known_estimate_usd is None


def test_partial_failed_pending_and_old_usage_never_claim_complete():
    usage = measured()
    usage.begin_call()
    usage.record_cost(None)
    usage.begin_call()
    result = summarize({"analyst": usage_record(usage)}, status="cancelled")
    assert result.input_tokens.known == 10 and not result.input_tokens.complete
    assert result.known_estimate_usd == 0.012 and not result.estimate_complete
    assert result.usages[0].unknown_cost_calls == 2
    assert result.usages[0].in_flight_calls == 1
    assert result.retryable and result.additional_charges_possible
    old = summarize({"analyst": {"prompt_tokens": 7, "completion_tokens": 0, "cost": 0}})
    assert old.input_tokens.known == 7 and not old.input_tokens.complete
    assert old.output_tokens.known is None and old.known_estimate_usd is None


@pytest.mark.parametrize("value", [None, [], "legacy", 0, {"analyst": None}])
def test_missing_usage_is_unknown_without_crash(value):
    result = summarize(value)
    assert result.input_tokens.known is None and result.known_estimate_usd is None
    assert result.execution_seconds is None and result.total_seconds is None


@pytest.mark.parametrize("value", [True, -1, "7", 3.5, float("nan"), float("inf"), {}])
def test_malformed_usage_is_not_numeric(value):
    row = usage_metric(
        "analyst",
        {
            "calls": value,
            "prompt_tokens": value,
            "known_cost": value,
            "cost": value,
            "cost_basis": [],
            "provider_models": [],
        },
    )
    assert row.calls is None and row.input_tokens.known is None
    # Positive fractional cost is valid even when it is not a valid token count.
    assert row.known_amount_usd == (3.5 if value == 3.5 else None)
    assert not row.amount_complete


def test_phases_repeated_nodes_missing_intervals_and_monotonic_bounds():
    result = summarize(
        events=[
            ("started", START + timedelta(seconds=3), None),
            (
                "retriever",
                START + timedelta(seconds=5),
                {"elapsed_seconds": 2, "basis": "node_interval"},
            ),
            (
                "reviewer",
                START + timedelta(seconds=8),
                {"elapsed_seconds": 3, "basis": "node_interval"},
            ),
            (
                "retriever",
                START + timedelta(seconds=9),
                {"elapsed_seconds": 1, "basis": "node_interval"},
            ),
            ("reviewer", START + timedelta(seconds=10), None),
            ("finished", START + timedelta(seconds=12), None),
        ]
    )
    assert (result.queue_seconds, result.execution_seconds, result.total_seconds) == (3, 9, 12)
    assert result.phases[0].seconds == 3 and result.phases[0].measured_intervals == 2
    assert result.phases[1].seconds is None and result.phases[1].measured_intervals == 1
    backwards = summarize(
        events=[
            ("started", START - timedelta(seconds=1), None),
            ("failed", START - timedelta(seconds=2), None),
        ]
    )
    assert backwards.queue_seconds is None and backwards.execution_seconds is None
    assert backwards.total_seconds is None


def test_live_duration_and_local_amount_do_not_become_remote_bill():
    result = summarize(status="queued")
    assert result.duration_live and result.total_seconds == 20 and result.queue_seconds == 20
    usage = Usage(configured_model="DEMO-local", cost_basis="local_service")
    usage.begin_call()
    usage.record_cost(0)
    local = summarize({"embedding": usage_record(usage)})
    assert local.usages[0].known_amount_usd == 0
    assert local.input_tokens.known is None and local.known_estimate_usd is None
    assert local.exact_provider_bill_usd is None and not local.additional_charges_possible


def test_untrusted_metadata_and_raw_errors_are_excluded():
    result = summarize(
        {
            "private_role": {"configured_model": "PRIVATE"},
            "analyst": {
                "configured_model": "https://user:password@example.org",
                "provider_models": ["sk-PRIVATE", "DEMO"],
                "api_key": "PRIVATE_SECRET",
                "system_fingerprints": ["PRIVATE_FINGERPRINT"],
            },
        },
        error_code="PRIVATE provider error sk-SECRET",
    )
    text = result.model_dump_json()
    assert "PRIVATE" not in text and "password" not in text and result.error_code is None
    assert result.usages[0].configured_model is None and result.usages[0].returned_models == [
        "DEMO"
    ]


def test_evaluation_delta_retains_token_completeness_and_amount_basis():
    provider = SimpleNamespace(usage=Usage(configured_model="DEMO", cost_basis="sdk_estimate"))
    previous = usage_snapshot(provider)
    provider.usage.begin_call()
    provider.usage.record_tokens(10, None)
    provider.usage.record_cost(0.2)
    delta = usage_delta(previous, usage_snapshot(provider))
    assert delta["prompt_token_reports"] == 1 and delta["completion_token_reports"] == 0
    assert delta["configured_model"] == "DEMO" and delta["cost_basis"] == "sdk_estimate"
    row = usage_metric("analyst", delta)
    assert row.input_tokens.complete and row.output_tokens.known is None


@pytest.mark.parametrize(
    "status", ["completed", "failed", "cancelled", "insufficient_evidence", "running"]
)
def test_retryability_tracks_actual_terminal_state(status):
    result = summarize(status=status)
    assert result.retryable == (status in {"failed", "cancelled", "insufficient_evidence"})


def test_inconsistent_report_count_cannot_turn_an_unmeasured_zero_into_usage():
    row = usage_metric("analyst", {"calls": 1, "prompt_tokens": 0, "prompt_token_reports": 2})
    assert row.input_tokens.known is None and row.input_tokens.reported_calls is None
    assert not row.input_tokens.complete
