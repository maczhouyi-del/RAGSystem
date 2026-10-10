"""Actual PG/API file reads; owned synthetic PDFs, no model calls or native GUI claims."""

import hashlib

import pytest

from ragagent.db.models import Chunk, Paper
from scripts.pdf_fixture import write_provenance_pdf
from tests.integration.test_api import client as client
from tests.integration.test_retrieval import populate

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({}, "available"),
        ({"page_location": "unavailable"}, "unavailable"),
        ({"page_location": None}, "unavailable"),
    ],
)
def test_annotation_reading_preserves_unknown_and_legacy_pages(
    client, empty_db, metadata, expected
):
    pid, cid = populate(empty_db)
    chunk = empty_db.get(Chunk, cid)
    chunk.metadata_json = metadata
    empty_db.flush()
    occurrences = client.get(f"/api/papers/{pid}/annotations").json()["items"]
    chunks = client.get(f"/api/papers/{pid}/annotation-chunks").json()["items"]
    source = client.get(f"/api/papers/{pid}/chunks/{cid}/source").json()
    assert occurrences and all(item["page_location"] == expected for item in occurrences)
    assert chunks[0]["page_location"] == source["page_location"] == expected
    assert source["content"] == chunk.content


def test_original_pdf_route_serves_exact_owned_paper_and_rejects_unknown(
    client, empty_db, tmp_path
):
    pid, _ = populate(empty_db)
    pdf = tmp_path / "source.pdf"
    write_provenance_pdf(pdf)
    paper = empty_db.get(Paper, pid)
    paper.original_path = str(pdf)
    paper.sha256 = hashlib.sha256(pdf.read_bytes()).hexdigest()
    empty_db.flush()
    response = client.get(f"/api/papers/{pid}/pdf")
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content == pdf.read_bytes()
    assert hashlib.sha256(response.content).hexdigest() == paper.sha256
    assert f"{pid}.pdf" in response.headers["content-disposition"]
    assert client.get("/api/papers/00000000-0000-0000-0000-000000000099/pdf").status_code == 404
