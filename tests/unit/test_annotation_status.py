"""Coverage states are not scientific extraction benchmarks."""

import pytest
from pydantic import ValidationError

from ragagent.domain.annotations import AnnotationCoverageRequest, annotation_status


@pytest.mark.parametrize(
    "counts,expected",
    [
        ((0, 0, 0, 0, 0), "unprocessed"),
        ((2, 0, 0, 0, 0), "unprocessed"),
        ((2, 0, 0, 0, 2), "partial"),
        ((2, 1, 0, 0, 0), "partial"),
        ((2, 2, 0, 0, 0), "completed"),
        ((2, 1, 1, 0, 1), "processing"),
        ((2, 1, 0, 1, 1), "failed"),
        ((2, 0, 1, 1, 0), "processing"),
    ],
)
def test_truthful_status(counts: tuple[int, int, int, int, int], expected: str) -> None:
    assert annotation_status(*counts) == expected


def test_coverage_request_rejects_unrecognized_semantics() -> None:
    with pytest.raises(ValidationError):
        AnnotationCoverageRequest(datasets=["DEMO"], full_text_fallback=True)
