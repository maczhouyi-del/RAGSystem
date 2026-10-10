"""Offline inspection, human review and paired comparisons of existing artifacts."""

import re
from collections.abc import Iterator
from copy import deepcopy
from math import isfinite
from typing import Any

from ragagent.domain.evaluation import ManualReview
from ragagent.domain.privacy import reject_credentials
from ragagent.domain.research import EvidenceRecord
from ragagent.errors import EvaluationError
from ragagent.evaluation.artifacts import canonical_hash
from ragagent.evaluation.metrics import average, ratio
from ragagent.retrieval.evidence import exact_span


def case_rows(report: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    if report.get("kind") == "conversation":
        for conversation in report.get("per_conversation", []):
            for row in conversation.get("turns", []):
                yield "conversation/" + conversation["id"], row
    elif isinstance(report.get("per_query"), dict):
        for mode, rows in report["per_query"].items():
            for row in rows:
                yield "retrieval/" + mode, row
    else:
        for row in report.get("per_query", []):
            yield "generation", row


def observations(report: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    reject_credentials(report)
    result = {}
    for scope, row in case_rows(report):
        key = (scope, row["id"])
        if key in result:
            raise EvaluationError("duplicate_artifact_case")
        result[key] = deepcopy(
            {
                name: row.get(name)
                for name in (
                    "gold_labels",
                    "original_query",
                    "actual_output",
                    "claims",
                    "evidence",
                    "ranking",
                    "status",
                    "evaluation_status",
                    "failure_stage",
                    "error_code",
                    "metrics",
                    "usage",
                    "workflow_latency_ms",
                )
            }
        )
    return result


def review_template(report: dict[str, Any]) -> ManualReview:
    return ManualReview.model_validate(
        {
            "artifact_hash": canonical_hash(report),
            "cases": [
                {"scope": scope, "id": case_id, "observation": row}
                for (scope, case_id), row in observations(report).items()
            ],
        }
    )


def inspect_case(report: dict[str, Any], scope: str, case_id: str) -> dict[str, Any]:
    row = observations(report).get((scope, case_id))
    if row is None:
        raise EvaluationError("artifact_case_not_found")
    return {
        "manifest": report["manifest"],
        "scope": scope,
        "id": case_id,
        "observation": row,
        "replay_type": "OFFLINE_INSPECTION_NO_MODEL_CALL",
    }


def score_review(report: dict[str, Any], review: ManualReview) -> dict[str, Any]:
    review = ManualReview.model_validate(review.model_dump(mode="json"))
    expected = observations(report)
    keys = [(row.scope, row.id) for row in review.cases]
    if (
        review.artifact_hash != canonical_hash(report)
        or set(keys) != set(expected)
        or len(keys) != len(set(keys))
    ):
        raise EvaluationError("review_artifact_or_cases_mismatch")
    rows: list[dict[str, Any]] = []
    for item in review.cases:
        row = expected[item.scope, item.id]
        if canonical_hash(item.observation) != canonical_hash(row):
            raise EvaluationError("review_observation_mismatch")
        metrics: dict[str, float | None] = {
            "citation_precision": None,
            "citation_coverage": None,
            "claim_support_accuracy": None,
            "numeric_accuracy": None,
            "refusal_accuracy": None,
        }
        if item.reviewed:
            if item.scope.startswith("retrieval/") and (
                item.numeric_correct is not None or item.refusal_correct is not None
            ):
                raise EvaluationError("retrieval_review_has_no_generation_verdict")
            claims = row.get("claims") or []
            claim_ids = {claim["claim_id"] for claim in claims}
            predicted = {
                (claim["claim_id"], eid) for claim in claims for eid in claim["evidence_ids"]
            }
            pairs = {(pair.claim_id, pair.evidence_id) for pair in item.supported_pairs}
            supported = set(item.supported_claim_ids)
            if not pairs.issubset(predicted) or not supported.issubset({cid for cid, _ in pairs}):
                raise EvaluationError("review_support_not_in_released_claims")
            exact = set()
            for raw in row.get("evidence") or []:
                try:
                    evidence = EvidenceRecord.model_validate(raw)
                except ValueError:
                    continue
                if exact_span(evidence):
                    exact.add(evidence.evidence_id)
            if any(eid not in exact for _, eid in pairs):
                raise EvaluationError("review_support_requires_exact_evidence")
            gold = row.get("gold_labels") or {}
            output = row.get("actual_output") or ""
            refused = (
                row.get("status") == "insufficient_evidence" and not claims and bool(output.strip())
            )
            expected_refusal = gold.get("expected_refusal") is True
            if item.numeric_correct is not None:
                if not gold.get("numeric_targets") or item.numeric_correct and not output.strip():
                    raise EvaluationError("numeric_review_requires_labels_and_output")
                metrics["numeric_accuracy"] = float(item.numeric_correct)
            if item.refusal_correct is not None:
                if (
                    not (expected_refusal or refused)
                    or item.refusal_correct
                    and not (expected_refusal and refused)
                ):
                    raise EvaluationError("refusal_review_requires_expected_actual_refusal")
                metrics["refusal_accuracy"] = float(item.refusal_correct)
            metrics.update(
                {
                    "citation_precision": ratio(len(pairs), len(predicted)),
                    "citation_coverage": ratio(len({cid for cid, _ in pairs}), len(claim_ids)),
                    "claim_support_accuracy": ratio(len(supported), len(claim_ids)),
                }
            )
        rows.append(
            {
                "scope": item.scope,
                "id": item.id,
                "reviewed": item.reviewed,
                "reviewed_by": item.reviewed_by,
                "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
                "notes": item.notes,
                "metrics": metrics,
                "original_evaluation_status": row.get("evaluation_status"),
            }
        )
    reviewed = [row for row in rows if row["reviewed"]]
    return {
        "assessment_type": "USER_SUPPLIED_HUMAN_REVIEW_NOT_INDEPENDENTLY_VERIFIED",
        "warning": report["manifest"]["warning"],
        "label_source": report["manifest"]["label_source"],
        "artifact_hash": review.artifact_hash,
        "original_evaluation_status": report.get("status"),
        "reviewed_cases": len(reviewed),
        "unreviewed_cases": len(rows) - len(reviewed),
        "per_case": rows,
        "summary": average(row["metrics"] for row in reviewed),
        "metric_case_counts": {
            name: sum(row["metrics"][name] is not None for row in reviewed)
            for name in (rows[0]["metrics"] if rows else {})
        },
        "numeric_rubric": "All labeled values, units and experimental conditions must be correct; "
        "human verdict only.",
        "scientific_quality": measurement_boundary(report) if reviewed else "NOT MEASURED",
    }


def compare_artifacts(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    previous, current = before["manifest"], after["manifest"]
    for field in (
        "dataset_hash",
        "label_source",
        "model_configuration",
        "workflow_configuration",
        "retrieval_configuration",
        "judge",
    ):
        old_configuration, new_configuration = previous.get(field), current.get(field)
        if field in ("model_configuration", "judge"):
            old_configuration = deepcopy(old_configuration)
            new_configuration = deepcopy(new_configuration)
            for configuration in (old_configuration, new_configuration):
                if configuration is not None:
                    configuration.pop("execution_type", None)
                for provider in (configuration or {}).get("agents", {}).values():
                    provider.pop("execution_type", None)
        if (field != "judge" and (field not in previous or field not in current)) or canonical_hash(
            old_configuration
        ) != canonical_hash(new_configuration):
            raise EvaluationError("comparison_dataset_or_configuration_mismatch")
    previous_corpus = previous.get("corpus_snapshot", {})
    current_corpus = current.get("corpus_snapshot", {})
    if (
        previous_corpus.get("availability") != "available"
        or current_corpus.get("availability") != "available"
        or not re.fullmatch(r"[0-9a-f]{64}", str(previous_corpus.get("hash", "")))
        or previous_corpus.get("hash") != current_corpus.get("hash")
    ):
        raise EvaluationError("comparison_requires_same_known_corpus")
    if not all(
        re.fullmatch(r"[0-9a-f]{64}", str(value))
        for value in (
            previous.get("source_hash"),
            current.get("source_hash"),
            previous.get("dataset_hash"),
        )
    ):
        raise EvaluationError("comparison_requires_source_identity")
    if before.get("kind") != after.get("kind") and {before.get("kind"), after.get("kind")} != {
        "rag",
        "multi_agent",
    }:
        raise EvaluationError("comparison_incompatible_workflows")
    left, right = observations(before), observations(after)
    pairs: list[dict[str, Any]] = []
    for scope, case_id in sorted(left.keys() | right.keys()):
        old, new = left.get((scope, case_id)), right.get((scope, case_id))
        paired = bool(
            old and new and old["evaluation_status"] == new["evaluation_status"] == "completed"
        )
        delta: dict[str, float | None] = {}
        if paired and old and new:
            a, b = old.get("metrics") or {}, new.get("metrics") or {}
            for name in a.keys() | b.keys():
                x, y = a.get(name), b.get(name)
                delta[name] = (
                    float(y - x)
                    if isinstance(x, (int, float))
                    and not isinstance(x, bool)
                    and isinstance(y, (int, float))
                    and not isinstance(y, bool)
                    and isfinite(x)
                    and isfinite(y)
                    else None
                )
        pairs.append(
            {
                "scope": scope,
                "id": case_id,
                "paired": paired,
                "before": old,
                "after": new,
                "metric_delta": delta,
            }
        )
    metric_names = {name for pair in pairs for name in pair["metric_delta"]}
    deltas = [
        {name: pair["metric_delta"].get(name) for name in metric_names}
        for pair in pairs
        if pair["paired"]
    ]
    return {
        "comparison_type": "PAIRED_SAME_DATASET_CORPUS_AND_CONFIGURATION",
        "before_manifest": previous,
        "after_manifest": current,
        "before_status": before.get("status"),
        "after_status": after.get("status"),
        "before_usage": before.get("usage"),
        "after_usage": after.get("usage"),
        "per_case": pairs,
        "paired_cases": len(deltas),
        "unpaired_cases": len(pairs) - len(deltas),
        "paired_mean_delta": average(deltas),
        "warning": "Paired successful cases only; failures and missing cases remain visible. "
        "Model judgments are not human correctness.",
        "scientific_quality": measurement_boundary(before),
    }


def measurement_boundary(report: dict[str, Any]) -> str:
    manifest = report["manifest"]
    agents = manifest.get("model_configuration", {}).get("agents", {})
    execution = [provider.get("execution_type", "UNKNOWN_ADAPTER") for provider in agents.values()]
    if manifest["label_source"] != "human" or any(
        value != "PROVIDER_ADAPTER" for value in execution
    ):
        return "NOT MEASURED"
    if report.get("kind") != "retrieval" and not execution:
        return "NOT MEASURED"
    return "USER_SUPPLIED_LABELS_OR_REVIEW_NOT_INDEPENDENTLY_VERIFIED"
