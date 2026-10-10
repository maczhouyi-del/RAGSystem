"""Local rules: SYNTHETIC ONLY / NOT A BENCHMARK / NOT MANUALLY ANNOTATED."""

import pytest
from pydantic import ValidationError

from ragagent.domain.entities import AnnotationStart, EntityProposal, MentionPatch
from ragagent.ingestion.entities import SourceLabelExtractor


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "Dataset: MNIST. Method: BERT. Metric: F1.",
            [("MNIST", "dataset"), ("BERT", "method"), ("F1", "metric")],
        ),
        (
            'dataset: "中文数据 集"; method: "Long scientific method".',
            [("中文数据 集", "dataset"), ("Long scientific method", "method")],
        ),
        ("We used the MNIST dataset and BERT method.", [("MNIST", "dataset"), ("BERT", "method")]),
        (
            "Dataset: MNIST\nMethod: BERT\nMetric: F1",
            [("MNIST", "dataset"), ("BERT", "method"), ("F1", "metric")],
        ),
        ("Public dataset and The method are unqualified descriptions.", []),
        ("There were 500 participants with 0.93 accuracy.", []),
        ("Dataset: Long Name With Spaces.", []),
        ('Dataset: "Long\tName".', []),
        ('dataset: "sk-' + "SYNTHETIC" * 4 + '".', []),
    ],
)
def test_source_only_proposals(text: str, expected: list[tuple[str, str]]) -> None:
    results = SourceLabelExtractor().extract(text)
    assert [(p.name, p.entity_type) for p in results] == expected
    assert all(text[p.span_start : p.span_end] == p.name for p in results)
    assert results == SourceLabelExtractor().extract(text)


def test_explicit_parenthetical_names_are_candidates_not_global_synonyms() -> None:
    text = 'Dataset: "Large Demo Corpus" (LDC).'
    values = SourceLabelExtractor().extract(text)
    assert [v.name for v in values] == ["Large Demo Corpus", "LDC"]
    assert values[0].alias_group == values[1].alias_group and values[0].alias_group
    assert all(text[v.span_start : v.span_end] == v.name for v in values)
    assert not SourceLabelExtractor().extract("LDC abbreviates a name that is not supplied.")


def test_candidate_bound_does_not_exceed_one_hundred() -> None:
    text = "\n".join(f'Dataset: "Demo {i}" (D{i})' for i in range(150))
    results = SourceLabelExtractor().extract(text)
    assert len(results) == 100
    assert all(text[v.span_start : v.span_end] == v.name for v in results)


@pytest.mark.parametrize("ack", [False, 1, "true"])
def test_start_requires_explicit_boolean_review_ack(ack: object) -> None:
    with pytest.raises(ValidationError):
        AnnotationStart(engine="source-labels-v1", acknowledge_candidates_require_review=ack)


def test_unknown_engine_and_unordered_or_ignored_source_edits_rejected() -> None:
    with pytest.raises(ValidationError):
        AnnotationStart(engine="paid-model", acknowledge_candidates_require_review=True)
    with pytest.raises(ValidationError):
        EntityProposal(name="DEMO", entity_type="dataset", span_start=4, span_end=3)
    with pytest.raises(ValidationError):
        MentionPatch(
            action="correct",
            expected_version=1,
            expected_content_sha256="a" * 64,
            span_start=0,
            span_end=4,
        )
    with pytest.raises(ValidationError):
        MentionPatch(
            action="confirm",
            expected_version=1,
            expected_content_sha256="a" * 64,
            entity_type="dataset",
        )
