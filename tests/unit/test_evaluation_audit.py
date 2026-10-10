"""SYNTHETIC audit fixtures; no human gold, model requests or quality benchmark."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ragagent.domain.evaluation import GoldPaper, GoldSource, NumericTarget, ReviewedPair
from ragagent.domain.research import Claim
from ragagent.errors import EvaluationError
from ragagent.evaluation.artifacts import annotation_payload, canonical_hash, provider_snapshot
from ragagent.evaluation.audit import compare_artifacts, inspect_case, review_template, score_review
from ragagent.evaluation.schema import EvaluationCase, EvaluationDataset
from ragagent.providers.chat import MockProvider
from tests.unit.test_generation_evaluation import evidence


def artifact() -> dict:
    source = evidence()
    claim = Claim(claim_id="claim-1", text="SYNTHETIC result", evidence_ids=[source.evidence_id])
    return {
        "kind": "rag",
        "status": "completed",
        "manifest": {
            "dataset_hash": "d" * 64,
            "source_hash": "a" * 64,
            "label_source": "synthetic",
            "warning": "DEMO ONLY / NOT A BENCHMARK / NOT MANUALLY ANNOTATED",
            "model_configuration": {"agents": {"analyst": provider_snapshot(MockProvider([]))}},
            "workflow_configuration": {"max_iterations": 12},
            "retrieval_configuration": {"embedding_revision": "fixture"},
            "corpus_snapshot": {"availability": "available", "hash": "c" * 64},
        },
        "per_query": [
            {
                "id": "q1",
                "status": "completed",
                "evaluation_status": "completed",
                "actual_output": "SYNTHETIC: 120 participants.",
                "claims": [claim.model_dump()],
                "evidence": [source.model_dump(mode="json")],
                "gold_labels": {
                    "query": "MOCK numeric question",
                    "expected_refusal": False,
                    "numeric_targets": [
                        {
                            "name": "participants",
                            "value": "120",
                            "unit": "persons",
                            "conditions": {"cohort": "SYNTHETIC"},
                        }
                    ],
                },
                "metrics": {"citation_precision": 0.5, "latency_ms": 100.0, "cost": None},
            }
        ],
    }


def source_case() -> EvaluationCase:
    source = GoldSource(
        paper=GoldPaper(paper_id="p", pdf_sha256="b" * 64, reviewed_pages=[1]),
        chunk_id="c",
        page_start=1,
        page_end=1,
        span_start=0,
        span_end=4,
        quote="示例原文",
    )
    return EvaluationCase(
        id="q",
        query="SYNTHETIC ONLY",
        question_type="fact",
        expected_answer="SYNTHETIC",
        relevant_chunk_ids=["c"],
        relevant_paper_ids=["p"],
        required_aspects=["fixture"],
        gold_sources=[source],
        evaluation_dimensions=["cross_language", "table", "numeric"],
        numeric_targets=[
            NumericTarget(name="metric", value="12.5", unit="%", conditions={"split": "SYNTHETIC"})
        ],
    )


def test_source_gold_requires_complete_labels_and_numeric_context() -> None:
    case = source_case()
    dataset = EvaluationDataset(
        dataset_id="fixture",
        label_source="synthetic",
        description="NOT A BENCHMARK",
        annotation_format="source_v1",
        cases=[case],
    )
    dataset.generation_runnable()
    assert dataset.model_dump(mode="json")["cases"][0]["numeric_targets"][0]["value"] == "12.5"
    dataset.cases[0].numeric_targets = []
    with pytest.raises(ValueError, match="numeric_gold_requires"):
        dataset.runnable()
    case = source_case()
    case.relevant_chunk_ids.append("unlabeled")
    with pytest.raises(ValidationError, match="all_relevance_sources"):
        EvaluationDataset(
            dataset_id="fixture",
            label_source="synthetic",
            description="",
            annotation_format="source_v1",
            cases=[case],
        )


def test_human_source_gold_requires_aware_time_and_refusal_scope() -> None:
    case = source_case()
    case.annotated_by = "SYNTHETIC UNIT TEST, NOT A HUMAN ANNOTATOR"
    case.annotated_at = "not-a-time"
    with pytest.raises(ValidationError, match="aware_annotation_time"):
        EvaluationDataset(
            dataset_id="fixture",
            label_source="human",
            description="SYNTHETIC validator fixture",
            annotation_format="source_v1",
            cases=[case],
        )
    case.annotated_at = "2026-10-09T00:00:00Z"
    case.expected_refusal = True
    with pytest.raises(ValidationError, match="reviewed_scope_and_rationale"):
        EvaluationDataset(
            dataset_id="fixture",
            label_source="human",
            description="SYNTHETIC validator fixture",
            annotation_format="source_v1",
            cases=[case],
        )
    case.reviewed_papers = [case.gold_sources[0].paper]
    case.refusal_rationale = "SYNTHETIC refusal scope label"
    dataset = EvaluationDataset(
        dataset_id="fixture",
        label_source="human",
        description="SYNTHETIC validator fixture",
        annotation_format="source_v1",
        cases=[case],
    )
    dataset.generation_runnable()


def test_gold_span_shape_and_page_bounds_reject_typographical_huge_range() -> None:
    case = source_case()
    value = case.gold_sources[0].model_dump()
    value["page_end"] = 10**12
    with pytest.raises(ValidationError, match="pages_not_reviewed"):
        GoldSource.model_validate(value)
    value["page_end"] = 1
    value["span_end"] = 5
    with pytest.raises(ValidationError, match="span_invalid"):
        GoldSource.model_validate(value)


def test_unreviewed_values_remain_unmeasured_not_zero() -> None:
    report = artifact()
    scored = score_review(report, review_template(report))
    assert scored["reviewed_cases"] == 0 and scored["unreviewed_cases"] == 1
    assert scored["summary"] == {}
    assert all(value is None for value in scored["per_case"][0]["metrics"].values())
    assert scored["scientific_quality"] == "NOT MEASURED"


def completed_review(report: dict):
    review = review_template(report)
    item = review.cases[0]
    item.reviewed = True
    item.reviewed_by = "SYNTHETIC REVIEW FIXTURE"
    item.reviewed_at = datetime(2026, 10, 9, tzinfo=UTC)
    eid = report["per_query"][0]["claims"][0]["evidence_ids"][0]
    item.supported_pairs = [ReviewedPair(claim_id="claim-1", evidence_id=eid)]
    item.supported_claim_ids = ["claim-1"]
    item.numeric_correct = True
    return review


def test_manual_metrics_use_actual_claim_pairs_and_explicit_numeric_verdict() -> None:
    report = artifact()
    review = completed_review(report)
    result = score_review(report, review)
    assert result["summary"] == {
        "citation_precision": 1.0,
        "citation_coverage": 1.0,
        "claim_support_accuracy": 1.0,
        "numeric_accuracy": 1.0,
        "refusal_accuracy": None,
    }
    assert result["metric_case_counts"]["refusal_accuracy"] == 0
    assert result["assessment_type"].startswith("USER_SUPPLIED")
    assert result["scientific_quality"] == "NOT MEASURED"


@pytest.mark.parametrize(
    "mutation", ["answer", "inspection", "missing_case", "unknown_pair", "unsupported_claim"]
)
def test_review_cannot_score_changed_output_or_unknown_support(mutation: str) -> None:
    report = artifact()
    review = completed_review(report)
    if mutation == "answer":
        report["per_query"][0]["actual_output"] = "changed after review"
    elif mutation == "inspection":
        review.cases[0].observation["actual_output"] = "changed inspection"
    elif mutation == "missing_case":
        review.cases.clear()
    elif mutation == "unknown_pair":
        review.cases[0].supported_pairs[0].evidence_id = "unknown"
    else:
        review.cases[0].supported_pairs.clear()
    with pytest.raises(EvaluationError):
        score_review(report, review)


def test_human_verdict_cannot_make_unexpected_refusal_correct() -> None:
    report = artifact()
    row = report["per_query"][0]
    row.update(
        status="insufficient_evidence", claims=[], evidence=[], actual_output="SYNTHETIC refusal"
    )
    review = review_template(report)
    review.cases[0].reviewed = True
    review.cases[0].reviewed_by = "SYNTHETIC"
    review.cases[0].reviewed_at = datetime(2026, 10, 9, tzinfo=UTC)
    review.cases[0].refusal_correct = True
    with pytest.raises(EvaluationError, match="expected_actual_refusal"):
        score_review(report, review)
    review.cases[0].refusal_correct = False
    assert score_review(report, review)["summary"]["refusal_accuracy"] == 0.0


def test_paired_comparison_keeps_failures_unknown_cost_and_source_changes() -> None:
    before = artifact()
    before["per_query"].append(
        {
            **deepcopy(before["per_query"][0]),
            "id": "q2",
            "evaluation_status": "failed",
            "error_code": "fixture_failure",
        }
    )
    after = deepcopy(before)
    after["manifest"]["source_hash"] = "f" * 64
    after["per_query"][0]["metrics"]["citation_precision"] = 1.0
    after["per_query"][1]["evaluation_status"] = "completed"
    result = compare_artifacts(before, after)
    assert result["paired_cases"] == 1 and result["unpaired_cases"] == 1
    assert result["paired_mean_delta"]["citation_precision"] == 0.5
    assert result["paired_mean_delta"]["cost"] is None
    assert result["per_case"][1]["before"]["error_code"] == "fixture_failure"
    assert result["scientific_quality"] == "NOT MEASURED"
    before["per_query"][0]["evaluation_status"] = "failed"
    assert compare_artifacts(before, after)["paired_mean_delta"] == {}


@pytest.mark.parametrize(
    "changed",
    [
        "dataset_hash",
        "retrieval_configuration",
        "model_configuration",
        "corpus_snapshot",
        "source_hash",
        "label_source",
    ],
)
def test_comparison_rejects_different_or_unknown_input_identities(changed: str) -> None:
    before = artifact()
    after = deepcopy(before)
    after["manifest"][changed] = (
        {} if changed.endswith("configuration") or changed == "corpus_snapshot" else None
    )
    with pytest.raises(EvaluationError):
        compare_artifacts(before, after)


def test_failed_case_inspection_is_offline_and_conversation_ids_are_scoped() -> None:
    report = artifact()
    row = report["per_query"][0]
    row.update(evaluation_status="failed", error_code="fixture_failure", failure_stage="judge")
    inspected = inspect_case(report, "generation", "q1")
    assert inspected["observation"]["actual_output"] == row["actual_output"]
    assert inspected["replay_type"] == "OFFLINE_INSPECTION_NO_MODEL_CALL"
    report["kind"] = "conversation"
    report["per_conversation"] = [
        {"id": "a", "turns": [deepcopy(row)]},
        {"id": "b", "turns": [deepcopy(row)]},
    ]
    assert {case.scope for case in review_template(report).cases} == {
        "conversation/a",
        "conversation/b",
    }


def test_scripted_provider_remains_explicit_even_with_human_label_declaration() -> None:
    report = artifact()
    report["manifest"]["label_source"] = "human"
    assert provider_snapshot(MockProvider([]))["execution_type"] == "SCRIPTED"
    assert score_review(report, completed_review(report))["scientific_quality"] == "NOT MEASURED"


def test_review_requires_exact_evidence_and_detaches_nested_inspection() -> None:
    report = artifact()
    template = review_template(report)
    template.cases[0].observation["gold_labels"]["numeric_targets"][0]["value"] = "999"
    assert report["per_query"][0]["gold_labels"]["numeric_targets"][0]["value"] == "120"
    with pytest.raises(EvaluationError, match="observation_mismatch"):
        score_review(report, template)
    report["per_query"][0]["evidence"][0]["quote"] = "BROKEN EXACT QUOTE"
    with pytest.raises(EvaluationError, match="exact_evidence"):
        score_review(report, completed_review(report))


def test_legacy_dataset_hash_preserves_identity_without_empty_new_fields() -> None:
    case = EvaluationCase(
        id="q", query="SYNTHETIC", question_type="fact", expected_answer="fixture"
    )
    dataset = EvaluationDataset(
        dataset_id="fixture", label_source="synthetic", description="", cases=[case]
    )
    old = dataset.model_dump(mode="json")
    old.pop("annotation_format")
    for key in (
        "gold_sources",
        "reviewed_papers",
        "numeric_targets",
        "evaluation_dimensions",
        "refusal_rationale",
    ):
        old["cases"][0].pop(key)
    assert canonical_hash(annotation_payload(dataset.model_dump(mode="json"))) == canonical_hash(
        old
    )
    full = dataset.model_dump(mode="json")
    conversation = {**full, "cases": [{"id": "c", "turns": full["cases"]}]}
    expected = {**old, "cases": [{"id": "c", "turns": old["cases"]}]}
    assert canonical_hash(annotation_payload(conversation)) == canonical_hash(expected)
    assert "annotation_format" in full


def test_comparison_accepts_additive_execution_metadata_but_rejects_judge_changes() -> None:
    before = artifact()
    after = deepcopy(before)
    before["manifest"]["model_configuration"]["agents"]["analyst"].pop("execution_type")
    assert compare_artifacts(before, after)["paired_cases"] == 1
    after["manifest"]["judge"] = {"model": "different-judge"}
    with pytest.raises(EvaluationError, match="configuration_mismatch"):
        compare_artifacts(before, after)
