import pytest

from tests.scientific_oracles import scientific_payload_text


def test_source_digest_and_uuids_are_excluded_without_mutating_payload():
    item = {
        "paper": {
            "pdf_sha256": "500" + "0" * 61,
            "paper_id": "50000000-0000-4000-8000-000000000092",
            "title": "DEMO",
        },
        "quote": "120 participants.",
    }
    text = scientific_payload_text([item])
    assert "500" not in text and "120 participants." in text
    assert item["paper"]["pdf_sha256"].startswith("500")


@pytest.mark.parametrize("key", ["query", "quote", "text", "title", "source_literal", "pdf_sha256"])
def test_scientific_and_ordinary_fields_cannot_hide_bad_count(key):
    item = {"paper": {"pdf_sha256": "500" + "0" * 61}, key: "500 participants"}
    assert "500 participants" in scientific_payload_text(item)


@pytest.mark.parametrize("digest", ["500", "z" * 64, 500])
def test_malformed_paper_digest_is_rejected(digest):
    with pytest.raises(AssertionError):
        scientific_payload_text({"paper": {"pdf_sha256": digest}})


def test_uuid_in_ordinary_scientific_text_remains_observable():
    text = "50000000-0000-4000-8000-000000000092"
    assert text in scientific_payload_text({"quote": text})
