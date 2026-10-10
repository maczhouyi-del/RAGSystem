"""DEMO ONLY; export bytes and source contracts, not scientific model quality."""

import csv
import io
import json
from pathlib import Path

import pytest

from ragagent.deletion.history import SourceIds, redact
from ragagent.domain.exports import EXPORT_TYPES, MAX_EXPORT_BYTES, export_run, spreadsheet
from tests.unit.test_reports import demo_report, report_demo

RUN_ID = "00000000-0000-4000-8000-000000000015"


def report_result():
    facts, sources, _, validation = report_demo()
    report = demo_report()
    return {
        "draft_report": report.markdown,
        "structured_report": report.model_dump(),
        "evidence_pool": [e.model_dump() for e in sources],
        "analysis_results": [{"claims": [c.model_dump() for c in facts]}],
        "review_result": {"decision": "PASS", "validation": validation.model_dump()},
    }


def test_markdown_exactly_matches_persisted_report_and_preserves_numbers():
    result = report_result()
    item = export_run(RUN_ID, "research", "completed", result, "report.md")
    assert item.content.decode() == result["draft_report"]
    assert "91.5" in item.content.decode() and "0.89" in item.content.decode()
    assert item.filename == f"ragagent-{RUN_ID}-report.md"


def test_csv_roundtrip_preserves_each_experiment_and_traceable_field():
    result = report_result()
    content = export_run(RUN_ID, "research", "completed", result, "comparison.csv").content
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    assert len(rows) == 2
    for actual, expected in zip(rows, result["structured_report"]["rows"], strict=True):
        for name, cell in expected["fields"].items():
            assert actual[name] == cell["text"]
            assert actual[name + "_state"] == cell["state"]
            assert actual[name + "_claim_ids"] == " ".join(cell["claim_ids"])
            assert actual[name + "_evidence_ids"] == " ".join(cell["evidence_ids"])
        assert actual["verification_status"] == "verified_at_execution"
    assert "single GPU" in rows[0]["conditions"] and "CPU" in rows[1]["conditions"]
    assert "test split" in rows[0]["split"] and "validation split" in rows[1]["split"]


def test_bibtex_missing_metadata_does_not_invent_year_author_doi_or_journal():
    text = export_run(
        RUN_ID, "research", "completed", report_result(), "references.bib"
    ).content.decode()
    assert text.count("@misc{") == 2
    assert (
        "author =" not in text
        and "year =" not in text
        and "doi =" not in text
        and "journal =" not in text
    )
    assert "DOI (not stored), authors, year, venue" in text
    for eid in demo_report().evidence_ids:
        assert eid in text


def test_bibtex_handles_unicode_long_titles_and_literal_author_names():
    result = report_result()
    paper = result["evidence_pool"][0]["paper"]
    paper.update(
        title="中文 {long} & 91.5 % # _ \\ " + "长标题" * 300,
        authors=["Group and Team", "王小明"],
        year=2024,
        venue="DEMO & Venue",
        arxiv_id="2501.01234v2",
    )
    text = export_run(RUN_ID, "research", "completed", result, "references.bib").content.decode()
    assert r"\{long\}" in text and r"\&" in text and r"\%" in text and "长标题" in text
    assert "{Group and Team} and {王小明}" in text
    assert "year = {2024}" in text and "eprint = {2501.01234v2}" in text
    assert "note = {Venue: DEMO" in text and "journal =" not in text
    # Escaped braces do not become structural entry delimiters.
    import re

    structural = re.sub(r"\\[{}]", "", text)
    assert structural.count("{") == structural.count("}")


def test_citation_manifest_preserves_exact_ids_pages_offsets_and_metadata():
    result = report_result()
    manifest = json.loads(
        export_run(RUN_ID, "research", "completed", result, "citations.json").content
    )
    assert (
        manifest["run_id"] == RUN_ID and manifest["verification_status"] == "verified_at_execution"
    )
    for ref, item in zip(manifest["references"], result["evidence_pool"], strict=True):
        for key in [
            "evidence_id",
            "chunk_id",
            "section_id",
            "section_path",
            "span_start",
            "span_end",
        ]:
            assert ref[key] == item[key]
        assert ref["paper"] == item["paper"]
        assert ref["source_availability"] == "snapshot_only"


@pytest.mark.parametrize("filename", list(EXPORT_TYPES))
def test_deleted_sources_export_only_as_unverifiable_history(filename):
    result = report_result()
    source = result["evidence_pool"][0]
    retired = redact(
        result, SourceIds(papers={source["paper"]["paper_id"]}, evidence={source["evidence_id"]})
    )
    item = export_run(RUN_ID, "research", "completed", retired, filename)
    if filename == "report.md":
        assert "当前不可验证" in item.content.decode()
        assert item.content.decode().endswith(result["draft_report"])
    elif filename == "comparison.csv":
        rows = list(csv.DictReader(io.StringIO(item.content.decode("utf-8-sig"))))
        assert all(r["verification_status"] == "historical_unverifiable" for r in rows)
        assert rows[0]["source_availability"] == "unavailable"
        assert "91.5" in rows[0]["result"]
    elif filename == "citations.json":
        manifest = json.loads(item.content)
        assert manifest["verification_status"] == "historical_unverifiable"
        assert manifest["references"][0]["source_availability"] == "unavailable"
    else:
        assert "% Source availability: unavailable" in item.content.decode()


@pytest.mark.parametrize("status", ["queued", "running", "failed", "cancelled"])
def test_unreleased_state_cannot_export_facts(status):
    with pytest.raises(ValueError, match="report_not_released"):
        export_run(RUN_ID, "research", status, report_result(), "report.md")


@pytest.mark.parametrize(
    "filename",
    ["../report.md", "report.exe", "report.md?path=/tmp", "..\\report.md", "/tmp/report.md"],
)
def test_fixed_export_names_reject_paths(filename):
    with pytest.raises(ValueError, match="export_format_not_supported"):
        export_run(RUN_ID, "research", "completed", report_result(), filename)


def test_invalid_run_id_cannot_become_a_download_filename():
    with pytest.raises(ValueError, match="export_run_id_invalid"):
        export_run("../escape", "research", "completed", report_result(), "report.md")


def test_legacy_report_and_unresolved_citations_keep_text_without_inventing_fields():
    eid = demo_report().evidence_ids[0]
    body = f"旧报告：-0.3 / 91.5 / 中文 [E:{eid}]"
    result = {"draft_report": body}
    rows = list(
        csv.DictReader(
            io.StringIO(
                export_run(
                    RUN_ID, "research", "completed", result, "comparison.csv"
                ).content.decode("utf-8-sig")
            )
        )
    )
    assert rows[0]["legacy_report"] == body and rows[0]["paper_id"] == ""
    assert rows[0]["result_state"] == "evidence_insufficient"
    assert rows[0]["evidence_ids"] == eid
    refs = json.loads(export_run(RUN_ID, "research", "completed", result, "citations.json").content)
    assert refs["verification_status"] == "legacy_review_unknown"
    assert refs["references"] == [
        {
            "evidence_id": eid,
            "source_availability": "unknown",
            "metadata_status": "missing_evidence_record",
        }
    ]


def test_rag_export_and_refusal_do_not_leak_unreviewed_analyst_facts():
    result = report_result()
    result["answer"] = result.pop("draft_report")
    result.pop("review_result")
    assert (
        export_run(RUN_ID, "rag", "completed", result, "report.md").content.decode()
        == result["answer"]
    )
    result["answer"] = "Insufficient evidence."
    rows = list(
        csv.DictReader(
            io.StringIO(
                export_run(
                    RUN_ID, "rag", "insufficient_evidence", result, "comparison.csv"
                ).content.decode("utf-8-sig")
            )
        )
    )
    assert "91.5" not in json.dumps(rows) and rows[0]["verification_status"] == "refusal"


def test_export_size_is_bounded():
    with pytest.raises(ValueError, match="export_too_large"):
        export_run(
            RUN_ID,
            "research",
            "completed",
            {"draft_report": "x" * (MAX_EXPORT_BYTES + 1)},
            "report.md",
        )


@pytest.mark.parametrize(
    "value", ['=HYPERLINK("https://example.org")', "+cmd", "@SUM(1,2)", "-2+3", "\t=1+1"]
)
def test_source_strings_cannot_become_spreadsheet_formulas(value):
    assert spreadsheet(value) == "'" + value


@pytest.mark.parametrize("value", ["-0.3", "+91.5", "0.89", "-1e-3", "91.5%", '中文, "引号"\n内容'])
def test_numeric_literals_and_quoted_unicode_are_preserved(value):
    assert spreadsheet(value) == value


def test_browser_fixture_contains_actual_export_bytes():
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures" / "report-exports.json").read_text()
    )
    assert fixture["result"] == report_result() and fixture["run_id"] == RUN_ID
    for name, text in fixture["artifacts"].items():
        assert (
            text.encode("utf-8")
            == export_run(RUN_ID, "research", "completed", report_result(), name).content
        )
