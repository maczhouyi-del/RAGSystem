"""Real PostgreSQL library contracts. SYNTHETIC ONLY / NOT A BENCHMARK."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from ragagent.db.models import Author, Chunk, Paper, PaperAuthor, Section
from ragagent.settings import get_settings
from tests.integration.test_api import client as client

pytestmark = pytest.mark.integration


@pytest.fixture
def library(empty_db: Session) -> list[Paper]:
    authors = [
        Author(id="search-author-1", name="Alice DEMO"),
        Author(id="search-author-2", name="Alice Collaborator DEMO"),
    ]
    items = [
        Paper(
            id=f"search-{index:03}",
            title=f"SYNTHETIC Library {index:03}",
            year=2000 + index % 5,
            venue="Science DEMO" if index % 2 == 0 else "Conference DEMO",
            status="indexed" if index % 3 == 0 else "queued",
            created_at=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index // 3),
            sha256=f"{index:064x}",
            original_path="SYNTHETIC-NOT-A-REAL-PDF",
        )
        for index in range(210)
    ]
    for index, title in enumerate(
        ["100%_literal DEMO", "中文科学 DEMO", "No year DEMO", "No venue DEMO"], 210
    ):
        items.append(
            Paper(
                id=f"search-{index:03}",
                title=title,
                year=None,
                venue=None,
                status="failed",
                created_at=datetime(2024, 1, 1, tzinfo=UTC),
                sha256=f"{index:064x}",
                original_path="SYNTHETIC-NOT-A-REAL-PDF",
            )
        )
    empty_db.add_all([*authors, *items])
    empty_db.flush()
    empty_db.add_all(
        [
            PaperAuthor(paper_id=paper.id, author_id=author.id, position=position)
            for paper in items[:210]
            for position, author in enumerate(authors)
        ]
    )
    section = Section(
        id="search-section", paper_id=items[0].id, title="DEMO", path="DEMO", ordinal=0
    )
    empty_db.add(section)
    empty_db.flush()
    for ordinal in range(2):
        empty_db.add(
            Chunk(
                id=f"search-chunk-{ordinal}",
                paper_id=items[0].id,
                section_id=section.id,
                section_path="DEMO",
                page_start=1,
                page_end=1,
                element_type="text",
                content="SYNTHETIC ONLY",
                token_count=3,
                ordinal=ordinal,
                embedding=[1.0] + [0.0] * (get_settings().embedding_dimension - 1),
            )
        )
    empty_db.commit()
    return items


def result(client: TestClient, **parameters: object) -> dict:
    response = client.get("/api/papers/search", params=parameters)
    assert response.status_code == 200, response.text
    return response.json()


def test_full_library_pages_are_stable_counted_and_legacy_compatible(
    client: TestClient, library: list[Paper]
) -> None:
    expected = sorted(library, key=lambda paper: (-paper.created_at.timestamp(), paper.id))
    actual = []
    for offset in range(0, 250, 50):
        page = result(client, offset=offset)
        assert page["total"] == 214 and page["offset"] == offset and page["limit"] == 50
        assert page == result(client, offset=offset)
        ids = [paper["id"] for paper in page["items"]]
        legacy = client.get("/api/papers", params={"offset": offset, "limit": 50})
        assert legacy.status_code == 200 and isinstance(legacy.json(), list)
        assert [paper["id"] for paper in legacy.json()] == ids
        actual.extend(ids)
    assert actual == [paper.id for paper in expected]
    assert len(set(actual)) == 214
    assert result(client, offset=1000)["total"] == 214
    assert result(client, offset=1000)["items"] == []


def test_combined_filters_and_author_matches_do_not_duplicate_rows(
    client: TestClient, library: list[Paper]
) -> None:
    assert len(library) >= 200
    assert result(client, author="ALICE")["total"] == 210
    page = result(
        client,
        title="library",
        author="Alice",
        year=2000,
        venue="SCIENCE",
        status="indexed",
        limit=200,
    )
    expected = {
        paper.id
        for paper in library
        if paper.year == 2000 and paper.venue == "Science DEMO" and paper.status == "indexed"
    }
    assert page["total"] == len(expected) == 7
    assert {paper["id"] for paper in page["items"]} == expected
    assert len(page["items"]) == len(expected)
    assert result(client, status="failed")["total"] == 4
    assert result(client, title="library 209")["items"][0]["id"] == "search-209"
    assert result(client, title="科学")["total"] == 1
    assert result(client, title="%_")["total"] == 1
    assert result(client, title="no such paper")["items"] == []
    assert result(client, year=1999)["total"] == 0


@pytest.mark.parametrize("sort", ["created_at", "year"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sorting_with_ties_and_missing_years(
    client: TestClient, library: list[Paper], sort: str, direction: str
) -> None:
    def key(paper: Paper) -> tuple:
        value = paper.year if sort == "year" else paper.created_at.timestamp()
        return (
            value is None,
            (-value if direction == "desc" else value) if value is not None else 0,
            paper.id,
        )

    expected = sorted(library, key=key)
    actual = []
    for offset in (0, 100, 200):
        actual.extend(
            paper["id"]
            for paper in result(client, sort=sort, direction=direction, limit=100, offset=offset)[
                "items"
            ]
        )
    assert actual == [paper.id for paper in expected]


def test_page_serialization_batches_author_and_chunk_queries(
    client: TestClient, library: list[Paper], empty_db: Session
) -> None:
    statements = []
    connection = empty_db.connection()

    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith(("select", "with")):
            statements.append(statement)

    event.listen(connection, "before_cursor_execute", capture)
    try:
        page = result(client, limit=200, direction="asc")
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    assert len(page["items"]) == 200
    assert len(statements) == 3
    first = next(paper for paper in page["items"] if paper["id"] == "search-000")
    assert first["authors"] == ["Alice DEMO", "Alice Collaborator DEMO"]
    assert first["chunk_count"] == 2


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=201",
        "offset=-1",
        "offset=1000001",
        "year=999",
        "year=2101",
        "year=abc",
        "status=active",
        "sort=title",
        "direction=random",
        "title=",
        "author=%20",
        "venue=%0A",
        "venue=Science%0A",
        "venue=%7F",
        "title=%FF",
        "title=" + "a" * 1001,
        "unknown=x",
        "year=2000&year=2001",
        "title=sk-" + "SYNTHETIC" * 4,
    ],
)
def test_invalid_search_parameters_are_rejected(client: TestClient, query: str) -> None:
    response = client.get("/api/papers/search?" + query)
    assert response.status_code == 422
    assert "sk-SYNTHETIC" not in response.text
