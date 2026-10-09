"""Metadata persistence and original isolation; SYNTHETIC ONLY, no parsing/model calls."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from ragagent.api.papers import update_metadata
from ragagent.api.schemas import PaperPatch
from ragagent.db.models import Chunk, Paper, Section, new_id
from ragagent.settings import get_settings
from tests.integration.test_api import client as client

pytestmark = pytest.mark.integration


def upload(client: TestClient) -> dict:
    response = client.post(
        "/api/papers/upload",
        files={"file": ("demo.pdf", b"%PDF-1.4 SYNTHETIC metadata fixture", "application/pdf")},
        data={
            "title": "Original DEMO",
            "authors": "Alice;Bob",
            "year": "2024",
            "venue": "Original venue DEMO",
        },
    )
    assert response.status_code == 202
    return client.get("/api/papers").json()[0]


def test_edit_persists_separately_from_original_and_preserves_pdf_and_chunks(
    client: TestClient, empty_db: Session
) -> None:
    original = upload(client)
    assert original["original_metadata"]["kind"] == "upload_user"
    assert original["original_metadata"]["values"]["authors"] == ["Alice", "Bob"]
    source = deepcopy(original["original_metadata"])
    paper = empty_db.get(Paper, original["id"])
    assert paper is not None
    pdf = Path(paper.original_path).read_bytes()
    path, checksum = paper.original_path, paper.sha256
    section = Section(paper_id=paper.id, title="DEMO", path="DEMO", ordinal=0)
    empty_db.add(section)
    empty_db.flush()
    chunk = Chunk(
        paper_id=paper.id,
        section_id=section.id,
        section_path="DEMO",
        page_start=2,
        page_end=2,
        element_type="text",
        content="SYNTHETIC original evidence",
        token_count=4,
        ordinal=0,
        embedding=[1.0] + [0.0] * (get_settings().embedding_dimension - 1),
    )
    empty_db.add(chunk)
    empty_db.commit()
    chunk_id, section_id = chunk.id, section.id
    changed = client.patch(
        f"/api/papers/{paper.id}",
        json={
            "title": "Corrected DEMO",
            "authors": ["Carol", "Carol", " Dave "],
            "year": 2025,
            "venue": "Corrected venue DEMO",
            "expected_metadata_version": 1,
        },
    )
    assert changed.status_code == 200
    result = changed.json()
    assert result["metadata_version"] == 2
    assert result["authors"] == ["Carol", "Dave"]
    assert result["original_metadata"] == source
    assert result["overridden_fields"] == ["authors", "title", "venue", "year"]
    assert client.get(f"/api/papers/{paper.id}").json() == result
    assert client.get("/api/papers/search", params={"title": "Corrected"}).json()["total"] == 1
    empty_db.expire_all()
    paper = empty_db.get(Paper, result["id"])
    chunk = empty_db.get(Chunk, chunk_id)
    assert paper is not None and chunk is not None
    assert (paper.original_path, paper.sha256) == (path, checksum)
    assert Path(path).read_bytes() == pdf
    assert (chunk.paper_id, chunk.section_id, chunk.content, chunk.page_start, chunk.page_end) == (
        paper.id,
        section_id,
        "SYNTHETIC original evidence",
        2,
        2,
    )
    assert list(chunk.embedding) == [1.0] + [0.0] * (get_settings().embedding_dimension - 1)
    assert client.get(f"/api/papers/{paper.id}/pdf").content == pdf
    stale = client.patch(
        f"/api/papers/{paper.id}", json={"title": "Stale overwrite", "expected_metadata_version": 1}
    )
    assert stale.status_code == 409 and stale.json()["error_code"] == "paper_metadata_conflict"
    assert client.get(f"/api/papers/{paper.id}").json() == result
    duplicate = upload(client)
    assert duplicate["id"] == paper.id and duplicate["original_metadata"] == source


@pytest.mark.parametrize(
    "field,value",
    [
        ("arxiv_version", 9),
        ("arxiv_id", "2408.09869v9"),
        ("sha256", "f" * 64),
        ("original_path", "/changed.pdf"),
        ("original_metadata", {}),
        ("metadata_version", 999),
    ],
)
def test_source_and_internal_fields_cannot_be_patched(
    client: TestClient, field: str, value: object
) -> None:
    original = upload(client)
    response = client.patch(
        f"/api/papers/{original['id']}", json={field: value, "expected_metadata_version": 1}
    )
    assert response.status_code == 422
    assert client.get(f"/api/papers/{original['id']}").json() == original


def test_legacy_original_stays_unknown_and_noop_does_not_invalidate_editors(
    client: TestClient, empty_db: Session
) -> None:
    paper = Paper(
        title="Legacy DEMO", sha256="e" * 64, original_path="SYNTHETIC", original_metadata=None
    )
    empty_db.add(paper)
    empty_db.commit()
    assert (
        empty_db.scalar(
            select(Paper.id).where(Paper.id == paper.id, Paper.original_metadata.is_(None))
        )
        == paper.id
    )
    initial = client.get(f"/api/papers/{paper.id}").json()
    assert initial["original_metadata"] is None and initial["metadata_version"] == 1
    noop = client.patch(
        f"/api/papers/{paper.id}", json={"title": paper.title, "expected_metadata_version": 1}
    )
    assert noop.status_code == 200 and noop.json() == initial
    changed = client.patch(
        f"/api/papers/{paper.id}",
        json={
            "title": "Edited legacy DEMO",
            "year": None,
            "venue": "",
            "authors": [],
            "expected_metadata_version": 1,
        },
    )
    assert changed.status_code == 200 and changed.json()["original_metadata"] is None
    assert changed.json()["metadata_version"] == 2
    assert changed.json()["overridden_fields"] == ["title"]
    # Compatibility: older callers may omit optimistic version checks. New UI
    # always supplies them; an omitted version cannot detect a stale client.
    assert client.patch(f"/api/papers/{paper.id}", json={"year": 2026}).status_code == 200


@pytest.mark.parametrize(
    "patch",
    [
        {"title": " "},
        {"title": None},
        {"authors": [" "]},
        {"authors": ["a" * 257]},
        {"year": 999},
        {"expected_metadata_version": 0},
    ],
)
def test_invalid_edits_leave_existing_metadata_intact(client: TestClient, patch: dict) -> None:
    original = upload(client)
    response = client.patch(f"/api/papers/{original['id']}", json=patch)
    assert response.status_code == 422
    assert client.get(f"/api/papers/{original['id']}").json() == original


def test_two_real_sessions_cannot_overwrite_the_same_metadata_version(
    job_sessions: sessionmaker[Session],
) -> None:
    pid = new_id()
    barrier = Barrier(2)
    with job_sessions() as db:
        db.add(
            Paper(
                id=pid,
                title="SYNTHETIC concurrent original",
                sha256=pid.replace("-", "") * 2,
                original_path="SYNTHETIC",
            )
        )
        db.commit()

    def edit(title: str) -> int:
        with job_sessions() as db:
            assert db.scalar(select(Paper.metadata_version).where(Paper.id == pid)) == 1
            barrier.wait(timeout=10)
            try:
                update_metadata(pid, PaperPatch(title=title, expected_metadata_version=1), db)
                return 200
            except HTTPException as failure:
                db.rollback()
                assert failure.detail == "paper_metadata_conflict"
                return failure.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(edit, ["SYNTHETIC editor A", "SYNTHETIC editor B"])) == [
                200,
                409,
            ]
        with job_sessions() as db:
            paper = db.get(Paper, pid)
            assert paper is not None and paper.metadata_version == 2
            assert paper.title in {"SYNTHETIC editor A", "SYNTHETIC editor B"}
            assert paper.original_metadata is None
    finally:
        with job_sessions() as db:
            db.execute(delete(Paper).where(Paper.id == pid))
            db.commit()
