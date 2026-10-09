"""Deletion safety controls; SYNTHETIC ONLY, no network/database/models."""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from ragagent.deletion.files import allowed_parts, manifest_file, unlink_owned
from ragagent.deletion.history import UNAVAILABLE, SourceIds, redact, source_ids
from ragagent.domain.deletion import CleanupFile, PaperDeleteRequest
from ragagent.errors import ApplicationError


def test_history_redacts_attributed_text_and_preserves_other_source_and_prose() -> None:
    deleted = SourceIds(papers={"removed"}, chunks={"old-chunk"}, evidence={"old-evidence"})
    old = {
        "paper": {"paper_id": "removed"},
        "chunk_id": "old-chunk",
        "evidence_id": "old-evidence",
        "content": "PRIVATE_SOURCE",
        "quote": "PRIVATE_SOURCE",
        "source_context": [{"text": "PRIVATE_CONTEXT"}],
        "source_spans": [{"page": 1}],
    }
    other = {
        "paper": {"paper_id": "other"},
        "evidence_id": "other-evidence",
        "quote": "KEEP_SOURCE",
    }
    value = {
        "status": "completed",
        "answer": "Historical answer stays.",
        "evidence": [old, other],
        "citation_validation": {
            "valid": True,
            "supported_pairs": [
                {"claim_id": "a", "evidence_id": "old-evidence"},
                {"claim_id": "b", "evidence_id": "other-evidence"},
            ],
        },
        "usage": {"known_cost": 1.0},
    }
    result = redact(value, deleted)
    assert result["status"] == "completed" and result["answer"] == value["answer"]
    assert result["evidence"][0]["quote"] == result["evidence"][0]["content"] == ""
    assert result["evidence"][0]["source_context"] == result["evidence"][0]["source_spans"] == []
    assert result["evidence"][0]["source_availability"] == "unavailable"
    assert result["evidence"][1] == other
    assert result["citation_validation"]["valid"] is False
    assert result["historical_citation_validation_valid"] is True
    assert result["citation_validation"]["supported_pairs"] == [
        {"claim_id": "b", "evidence_id": "other-evidence"}
    ]
    assert UNAVAILABLE in result["limitations"] and result["usage"] == value["usage"]
    assert value["evidence"][0]["quote"] == "PRIVATE_SOURCE"
    assert "PRIVATE_SOURCE" not in str(result) and "PRIVATE_CONTEXT" not in str(result)
    assert source_ids(result).intersects(deleted)


def test_research_validation_and_repeated_removal_keep_historical_verdict() -> None:
    value = {
        "draft_report": "Historical prose",
        "evidence_pool": [{"paper_id": "old", "evidence_id": "e1", "quote": "PRIVATE_SOURCE"}],
        "review_result": {
            "decision": "PASS",
            "validation": {"valid": True, "supported_pairs": [{"evidence_id": "e1"}]},
        },
    }
    deleted = SourceIds(papers={"old"}, evidence={"e1"})
    result = redact(value, deleted)
    validation = result["review_result"]["validation"]
    assert validation["valid"] is False and validation["historical_valid"] is True
    assert validation["supported_pairs"] == []
    assert result["review_result"]["decision"] == "PASS"
    assert result["source_availability"] == "unavailable" and UNAVAILABLE in result["limitations"]
    assert redact(result, deleted)["review_result"]["validation"]["historical_valid"] is True


@pytest.mark.parametrize("ack", [False, 1, "true", None])
def test_confirmation_requires_boolean_true(ack: object) -> None:
    with pytest.raises(ValidationError):
        PaperDeleteRequest.model_validate(
            {
                "confirm_paper_id": "paper",
                "expected_metadata_version": 1,
                "scope": "current_library",
                "acknowledge_retained_copies": ack,
            }
        )


@pytest.mark.parametrize(
    "role,path",
    [
        ("pdf", "../user.pdf"),
        ("pdf", "/tmp/user.pdf"),
        ("pdf", "other/user.pdf"),
        ("parsed", "user.json"),
        ("evaluation", "evaluations/not-a-run/results.json"),
        ("evaluation", "evaluations/00000000-0000-0000-0000-000000000000/user.pdf"),
    ],
)
def test_cleanup_rejects_non_allowlisted_paths(role: str, path: str) -> None:
    with pytest.raises(ApplicationError, match="cleanup_unsafe_path"):
        allowed_parts(CleanupFile.model_validate({"role": role, "relative_path": path}))


def test_owned_cleanup_is_missing_safe_and_refuses_replacements(tmp_path: Path) -> None:
    path = tmp_path / "owned.pdf"
    path.write_bytes(b"SYNTHETIC OLD")
    item = manifest_file(tmp_path, path, "pdf")
    path.write_bytes(b"SYNTHETIC REPLACEMENT")
    with pytest.raises(ApplicationError, match="cleanup_file_changed"):
        unlink_owned(tmp_path, item)
    assert path.read_bytes() == b"SYNTHETIC REPLACEMENT"
    path.write_bytes(b"SYNTHETIC OLD")
    unlink_owned(tmp_path, item)
    unlink_owned(tmp_path, item)
    assert not path.exists()


def test_cleanup_never_follows_file_or_directory_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    outside = tmp_path / "user.pdf"
    outside.write_bytes(b"SYNTHETIC USER FILE")
    link = root / "owned.pdf"
    link.symlink_to(outside)
    item = CleanupFile(
        role="pdf",
        relative_path="owned.pdf",
        sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
    )
    with pytest.raises(ApplicationError, match="cleanup_file_unavailable"):
        unlink_owned(root, item)
    assert outside.read_bytes() == b"SYNTHETIC USER FILE" and link.is_symlink()
    root_link = tmp_path / "root-link"
    root_link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ApplicationError, match="cleanup_unsafe_path"):
        unlink_owned(root_link, item)


def test_external_registered_paths_are_explicitly_retained(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    outside = tmp_path / "user.pdf"
    outside.write_bytes(b"SYNTHETIC USER FILE")
    item = manifest_file(root, outside, "pdf")
    assert item.relative_path is None and item.retained_reason == "unmanaged_path"
    unlink_owned(root, item)
    assert outside.exists()
