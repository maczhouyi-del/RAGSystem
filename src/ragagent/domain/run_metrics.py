"""Read-only presentation of persisted accounting. Unknown is distinct from zero."""

import math
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel


class TokenMetric(BaseModel):
    known: int | None = None
    complete: bool = False
    reported_calls: int | None = None


class ModelUsage(BaseModel):
    role: str
    configured_model: str | None = None
    returned_models: list[str] = []
    calls: int | None = None
    in_flight_calls: int | None = None
    input_tokens: TokenMetric
    output_tokens: TokenMetric
    cost_basis: Literal["sdk_estimate", "local_service", "unknown"] = "unknown"
    known_amount_usd: float | None = None
    amount_complete: bool = False
    unknown_cost_calls: int | None = None


class PhaseTiming(BaseModel):
    phase: str
    seconds: float | None = None
    completed_intervals: int
    measured_intervals: int
    basis: Literal["node_interval"] = "node_interval"


class RunMetrics(BaseModel):
    run_id: str
    kind: str
    status: str
    error_code: str | None = None
    retryable: bool
    usage_scope: str | None = None
    usages: list[ModelUsage]
    input_tokens: TokenMetric
    output_tokens: TokenMetric
    known_estimate_usd: float | None = None
    estimate_complete: bool = False
    exact_provider_bill_usd: None = None
    total_seconds: float | None = None
    execution_seconds: float | None = None
    queue_seconds: float | None = None
    duration_live: bool = False
    phases: list[PhaseTiming]
    additional_charges_possible: bool = True


PHASES = frozenset(
    {
        "plan",
        "retrieve",
        "answer",
        "verify",
        "expand",
        "refuse",
        "analyze",
        "synthesize",
        "review",
        "revise",
        "finish",
        "stop",
        "supervise",
        "supervisor",
        "retriever",
        "analysis",
        "synthesis",
        "reviewer",
    }
)
ROLES = frozenset(
    {"supervisor", "retriever", "analyst", "reviewer", "embedding", "reranker", "judge"}
)
TERMINAL = frozenset({"completed", "failed", "cancelled", "insufficient_evidence"})


def count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def amount(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            number = float(value)
        except OverflowError:
            return None
        if math.isfinite(number) and number >= 0:
            return number
    return None


def model_name(value: Any) -> str | None:
    # Do not forward endpoints, credential-like strings or arbitrary metadata.
    if (
        isinstance(value, str)
        and 0 < len(value) <= 256
        and "://" not in value
        and not re.search(r"[\x00-\x1f\x7f]|(?i:bearer\s|sk-)", value)
    ):
        return value
    return None


def token_metric(record: dict[str, Any], field: str, calls: int | None) -> TokenMetric:
    reports = count(record.get(f"{field}_token_reports"))
    value = count(record.get(f"{field}_tokens"))
    valid_reports = (
        reports if reports is not None and calls is not None and reports <= calls else None
    )
    # Older positive counters are known subtotals; older/default zero is unmeasured.
    known = (
        value
        if value is not None and (valid_reports is not None and valid_reports > 0 or value > 0)
        else None
    )
    return TokenMetric(
        known=known,
        reported_calls=valid_reports,
        complete=known is not None and calls is not None and calls > 0 and valid_reports == calls,
    )


def usage_metric(role: str, record: dict[str, Any]) -> ModelUsage:
    calls = count(record.get("calls"))
    pending = count(record.get("in_flight_calls"))
    unknown = count(record.get("unknown_cost_calls"))
    basis: Literal["sdk_estimate", "local_service", "unknown"] = "unknown"
    if record.get("cost_basis") == "sdk_estimate":
        basis = "sdk_estimate"
    elif record.get("cost_basis") == "local_service":
        basis = "local_service"
    known = amount(record.get("known_cost"))
    # A default zero with no accounted call or a missing cost is not a measured price.
    if known == 0 and not (
        calls and unknown == 0 and pending == 0 and amount(record.get("cost")) == 0
    ):
        known = None
    returned = record.get("provider_models")
    return ModelUsage(
        role=role,
        configured_model=model_name(record.get("configured_model")),
        returned_models=list(dict.fromkeys(name for v in returned if (name := model_name(v))))
        if isinstance(returned, list)
        else [],
        calls=calls,
        in_flight_calls=pending,
        unknown_cost_calls=unknown,
        input_tokens=token_metric(record, "prompt", calls),
        output_tokens=token_metric(record, "completion", calls),
        cost_basis=basis,
        known_amount_usd=known,
        amount_complete=bool(calls)
        and pending == 0
        and unknown == 0
        and known is not None
        and amount(record.get("cost")) == known,
    )


def total_tokens(usages: list[ModelUsage], field: str) -> TokenMetric:
    items = [getattr(row, field) for row in usages if row.calls != 0]
    values = [item.known for item in items if item.known is not None]
    return TokenMetric(
        known=sum(values) if values else None,
        complete=bool(items) and all(item.complete for item in items),
    )


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def seconds(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    delta = (aware(end) - aware(start)).total_seconds()
    return delta if delta >= 0 else None


def run_metrics(
    run_id: str,
    kind: str,
    status: str,
    error_code: Any,
    created_at: datetime,
    usage: Any,
    usage_scope: Any,
    events: list[tuple[str, datetime, Any]],
    now: datetime | None = None,
) -> RunMetrics:
    """No provider access, state changes, source text or invented historical timing."""
    records = usage if isinstance(usage, dict) else {}
    usages = [
        usage_metric(role, record)
        for role, record in records.items()
        if role in ROLES and isinstance(record, dict)
    ]
    started = next((at for node, at, _ in events if node == "started"), None)
    finished = next(
        (at for node, at, _ in reversed(events) if node in {"finished", "failed", "cancelled"}),
        None,
    )
    live = status in {"queued", "running"}
    end = (now or datetime.now(UTC)) if live else finished
    phases: dict[str, list[float | None]] = {}
    for node, _, timing in events:
        if node in PHASES:
            value = (
                amount(timing.get("elapsed_seconds"))
                if isinstance(timing, dict) and timing.get("basis") == "node_interval"
                else None
            )
            phases.setdefault(node, []).append(value)
    estimates = [
        row.known_amount_usd
        for row in usages
        if row.cost_basis == "sdk_estimate" and row.known_amount_usd is not None
    ]
    # Local service charges can be zero, but they are not remote price estimates.
    return RunMetrics(
        run_id=run_id,
        kind=kind,
        status=status,
        error_code=error_code
        if isinstance(error_code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,100}", error_code)
        else None,
        retryable=kind in {"rag", "research"}
        and status in {"failed", "cancelled", "insufficient_evidence"},
        usage_scope=usage_scope if usage_scope == "current_attempt" else None,
        usages=usages,
        input_tokens=total_tokens(usages, "input_tokens"),
        output_tokens=total_tokens(usages, "output_tokens"),
        known_estimate_usd=amount(sum(estimates)) if estimates else None,
        estimate_complete=bool(estimates)
        and all(
            row.amount_complete and row.cost_basis in {"sdk_estimate", "local_service"}
            for row in usages
            if row.calls != 0
        ),
        total_seconds=seconds(created_at, end),
        execution_seconds=seconds(started, end),
        queue_seconds=seconds(created_at, started or (end if status == "queued" else None)),
        duration_live=live,
        phases=[
            PhaseTiming(
                phase=node,
                seconds=sum(v for v in values if v is not None)
                if all(v is not None for v in values)
                else None,
                completed_intervals=len(values),
                measured_intervals=sum(v is not None for v in values),
            )
            for node, values in phases.items()
        ],
        additional_charges_possible=any(row.cost_basis != "local_service" for row in usages)
        or not usages,
    )
