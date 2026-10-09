"""Real PostgreSQL organization isolation; SYNTHETIC ONLY / NOT A BENCHMARK."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from ragagent.api.collections import add_member
from ragagent.db.models import (
    Chunk,
    Evidence,
    Paper,
    PaperCollection,
    PaperCollectionMember,
    Run,
    new_id,
)
from ragagent.domain.research import MetadataFilter, QueryPlan
from ragagent.retrieval.service import HybridRetriever
from tests.integration.test_api import client as client
from tests.integration.test_paper_metadata import upload
from tests.integration.test_retrieval import Embedder, FixtureReranker, populate

pytestmark = pytest.mark.integration


def create(client: TestClient, name: str, kind: str = "group") -> dict:
    response = client.post("/api/collections", json={"name": name, "kind": kind})
    assert response.status_code == 201, response.text
    return response.json()


def link(client: TestClient, pid: str, cid: str) -> None:
    assert client.put(f"/api/papers/{pid}/collections/{cid}").status_code == 204


def confirmation(collection: dict) -> dict:
    return {"confirm_collection_id": collection["id"], "expected_version": collection["version"]}


def test_multiple_memberships_idempotent_operations_and_delete_preserve_sources(
    client: TestClient, empty_db: Session
) -> None:
    paper = upload(client)
    p = empty_db.get(Paper, paper["id"])
    assert p is not None
    original = client.get(f"/api/papers/{p.id}").json()
    original_bytes = Path(p.original_path).read_bytes()
    group = create(client, "Project A DEMO")
    other = create(client, "Project B DEMO")
    tag = create(client, "Reviewed DEMO", "tag")
    for c in [group, other, tag]:
        link(client, p.id, c["id"])
        link(client, p.id, c["id"])
    assert empty_db.scalar(select(func.count()).select_from(PaperCollectionMember)) == 3
    values = client.get(f"/api/papers/{p.id}/collections").json()
    assert {c["id"] for c in values} == {group["id"], other["id"], tag["id"]}
    assert all(c["paper_count"] == 1 for c in values)
    assert (
        client.get(f"/api/papers/search?group={group['id']}&tag={tag['id']}").json()["total"] == 1
    )
    renamed = client.patch(
        f"/api/collections/{group['id']}", json={"name": "Renamed DEMO", "expected_version": 1}
    )
    assert renamed.status_code == 200 and renamed.json()["version"] == 2
    assert (
        client.request(
            "DELETE", f"/api/collections/{group['id']}", json=confirmation(group)
        ).status_code
        == 409
    )
    assert (
        client.request(
            "DELETE", f"/api/collections/{group['id']}", json=confirmation(renamed.json())
        ).status_code
        == 204
    )
    # A saved/deleted scope is still restrictive; it never becomes all papers.
    assert client.get(f"/api/papers/search?group={group['id']}").json()["total"] == 0
    assert {c["id"] for c in client.get(f"/api/papers/{p.id}/collections").json()} == {
        other["id"],
        tag["id"],
    }
    assert client.get(f"/api/papers/{p.id}").json() == original
    assert Path(p.original_path).read_bytes() == original_bytes
    assert empty_db.scalar(select(func.count()).select_from(Run)) == 1
    path = f"/api/papers/{p.id}/collections/{tag['id']}"
    assert client.delete(path).status_code == 204 and client.delete(path).status_code == 204
    assert len(client.get(f"/api/papers/{p.id}/collections").json()) == 1


@pytest.mark.parametrize("name", ["project a", "ＰＲＯＪＥＣＴ Ａ"])
def test_normalized_unique_names_keep_other_kinds_and_original_names(
    client: TestClient, name: str
) -> None:
    group = create(client, "Project A")
    duplicate = client.post("/api/collections", json={"name": name, "kind": "group"})
    assert (
        duplicate.status_code == 409
        and duplicate.json()["error_code"] == "collection_name_conflict"
    )
    tag = create(client, name, "tag")
    assert tag["id"] != group["id"]
    assert client.get("/api/collections").json()["total"] == 2


def test_version_conflicts_invalid_mutations_and_unknown_scope_do_not_broaden(
    client: TestClient, empty_db: Session
) -> None:
    p = upload(client)
    group = create(client, "A")
    other = create(client, "B")
    link(client, p["id"], group["id"])
    for body, code in [
        ({"name": "B", "expected_version": 1}, "collection_name_conflict"),
        ({"name": "C", "expected_version": 2}, "collection_version_conflict"),
    ]:
        response = client.patch(f"/api/collections/{group['id']}", json=body)
        assert response.status_code == 409 and response.json()["error_code"] == code
    bad = {**confirmation(group), "confirm_collection_id": other["id"]}
    assert client.request("DELETE", f"/api/collections/{group['id']}", json=bad).status_code == 409
    assert client.delete(f"/api/collections/{group['id']}").status_code == 422
    assert client.put(f"/api/papers/{p['id']}/collections/{new_id()}").status_code == 404
    assert client.put(f"/api/papers/{new_id()}/collections/{group['id']}").status_code == 404
    assert client.get("/api/papers/search?group=invalid").status_code == 422
    assert client.get(f"/api/papers/search?tag={group['id']}").json()["total"] == 0
    assert client.get(f"/api/papers/search?group={new_id()}").json()["total"] == 0
    assert client.get("/api/papers/search").json()["total"] == 1
    assert empty_db.scalar(select(func.count()).select_from(PaperCollectionMember)) == 1


def test_paged_collections_counts_and_no_duplicate_or_unknown_query_parameters(
    client: TestClient,
) -> None:
    paper = upload(client)
    a = create(client, "A")
    create(client, "B")
    create(client, "C", "tag")
    link(client, paper["id"], a["id"])
    first = client.get("/api/collections?limit=2").json()
    second = client.get("/api/collections?limit=2&offset=2").json()
    assert first["total"] == second["total"] == 3
    assert [c["name"] for c in first["items"]] == ["A", "B"]
    assert first["items"][0]["paper_count"] == 1 and first["items"][1]["paper_count"] == 0
    assert [c["name"] for c in second["items"]] == ["C"]
    assert client.get("/api/collections?offset=99").json()["items"] == []
    for query in ["limit=0", "limit=201", "limit=2&limit=3", "url=http://example.com"]:
        assert client.get("/api/collections?" + query).status_code == 422


@pytest.mark.parametrize("scope", ["group", "tag", "both", "or", "missing", "wrong_kind"])
async def test_real_dense_and_lexical_organization_scope_and_legacy_filters(
    empty_db: Session, scope: str
) -> None:
    pid, cid = populate(empty_db)
    other = empty_db.scalar(select(Paper.id).where(Paper.id != pid))
    a, b, t = [
        PaperCollection(id=new_id(), kind=kind, name=name, name_key=name.lower())
        for kind, name in [("group", "A"), ("group", "B"), ("tag", "T")]
    ]
    empty_db.add_all([a, b, t])
    empty_db.flush()
    empty_db.add_all(
        [
            PaperCollectionMember(paper_id=pid, collection_id=a.id),
            PaperCollectionMember(paper_id=other, collection_id=b.id),
            PaperCollectionMember(paper_id=pid, collection_id=t.id),
        ]
    )
    empty_db.flush()
    filters = {
        "group": MetadataFilter(group_ids=[a.id]),
        "tag": MetadataFilter(tag_ids=[t.id]),
        "both": MetadataFilter(
            group_ids=[a.id, b.id],
            tag_ids=[t.id],
            authors=["alice"],
            year_start=2023,
            datasets=["SciDocs"],
        ),
        "or": MetadataFilter(group_ids=[a.id, b.id]),
        "missing": MetadataFilter(group_ids=[new_id()]),
        "wrong_kind": MetadataFilter(group_ids=[t.id]),
    }[scope]
    result = await HybridRetriever(empty_db, Embedder(), FixtureReranker()).search(
        QueryPlan(queries=["contrastive training"], filters=filters)
    )
    expected = (
        set() if scope in {"missing", "wrong_kind"} else {pid, other} if scope == "or" else {pid}
    )
    assert {c.evidence.paper.paper_id for c in result.dense} == expected
    assert {c.evidence.paper.paper_id for c in result.lexical} == expected
    assert {e.paper.paper_id for e in result.evidence} == expected
    if expected == {pid}:
        assert result.evidence[0].chunk_id == cid


async def test_rename_and_collection_delete_keep_exact_existing_evidence(
    client: TestClient, empty_db: Session
) -> None:
    pid, cid = populate(empty_db)
    empty_db.commit()
    group = create(client, "Evidence scope")
    link(client, pid, group["id"])
    retriever = HybridRetriever(empty_db, Embedder(), FixtureReranker())
    result = await retriever.search(
        QueryPlan(queries=["contrastive"], filters=MetadataFilter(group_ids=[group["id"]]))
    )
    snapshot = result.evidence[0].model_dump()
    stored = empty_db.get(Evidence, snapshot["evidence_id"])
    assert stored is not None
    saved = (
        stored.id,
        stored.chunk_id,
        stored.span_start,
        stored.span_end,
        stored.quote,
        stored.scores.copy(),
    )
    assert (
        client.patch(
            f"/api/collections/{group['id']}", json={"name": "Renamed", "expected_version": 1}
        ).status_code
        == 200
    )
    renamed = client.get("/api/collections").json()["items"][0]
    assert (
        client.request(
            "DELETE", f"/api/collections/{group['id']}", json=confirmation(renamed)
        ).status_code
        == 204
    )
    empty_db.expire_all()
    stored = empty_db.get(Evidence, snapshot["evidence_id"])
    assert (
        stored is not None
        and (
            stored.id,
            stored.chunk_id,
            stored.span_start,
            stored.span_end,
            stored.quote,
            stored.scores,
        )
        == saved
    )
    assert empty_db.get(Chunk, cid).content == snapshot["content"]
    absent = await retriever.search(
        QueryPlan(queries=["contrastive"], filters=MetadataFilter(group_ids=[group["id"]]))
    )
    assert not absent.dense and not absent.lexical and not absent.evidence
    original = await retriever.search(
        QueryPlan(queries=["contrastive"], filters=MetadataFilter(paper_ids=[pid]))
    )
    assert original.evidence[0].model_dump() == snapshot


def test_concurrent_duplicate_membership_creates_one_link_and_preserves_other_links(
    job_sessions: sessionmaker[Session],
) -> None:
    ids = [new_id(), new_id(), new_id()]
    with job_sessions() as db:
        db.add(
            Paper(
                id=ids[0],
                title="Organization concurrency",
                sha256=new_id().replace("-", "") * 2,
                original_path="fixture",
            )
        )
        db.add_all(
            [PaperCollection(id=ids[i], kind="group", name=ids[i], name_key=ids[i]) for i in [1, 2]]
        )
        db.commit()
    barrier = Barrier(2)
    try:

        def submit(_: int) -> None:
            with job_sessions() as db:
                barrier.wait(timeout=5)
                add_member(UUID(ids[0]), UUID(ids[1]), db)

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(submit, range(2)))
        with job_sessions() as db:
            add_member(UUID(ids[0]), UUID(ids[2]), db)
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(PaperCollectionMember)
                    .where(PaperCollectionMember.paper_id == ids[0])
                )
                == 2
            )
    finally:
        with job_sessions() as db:
            db.execute(delete(Paper).where(Paper.id == ids[0]))
            db.execute(delete(PaperCollection).where(PaperCollection.id.in_(ids[1:])))
            db.commit()


def test_paper_retirement_cascades_membership_but_keeps_other_papers_and_labels(
    client: TestClient, empty_db: Session
) -> None:
    paper = upload(client)
    group = create(client, "Retained group")
    link(client, paper["id"], group["id"])
    other = Paper(title="Other organization source", sha256="f" * 64, original_path="fixture")
    empty_db.add(other)
    empty_db.commit()
    link(client, other.id, group["id"])
    response = client.request(
        "DELETE",
        f"/api/papers/{paper['id']}",
        json={
            "confirm_paper_id": paper["id"],
            "expected_metadata_version": 1,
            "scope": "current_library",
            "acknowledge_retained_copies": True,
        },
    )
    assert response.status_code == 202
    assert client.get(f"/api/papers/{paper['id']}/collections").status_code == 410
    assert client.put(f"/api/papers/{paper['id']}/collections/{group['id']}").status_code == 410
    assert client.get(f"/api/collections/{group['id']}").json()["paper_count"] == 1
    assert client.get(f"/api/papers/{other.id}/collections").json()[0]["id"] == group["id"]
    assert empty_db.get(PaperCollection, group["id"]) is not None


def test_two_sessions_cannot_overwrite_same_collection_name_version(
    job_sessions: sessionmaker[Session],
) -> None:
    from fastapi import HTTPException

    from ragagent.api.collections import rename_collection
    from ragagent.domain.collections import CollectionPatch

    cid = new_id()
    with job_sessions() as db:
        db.add(PaperCollection(id=cid, kind="group", name=cid, name_key=cid))
        db.commit()
    barrier = Barrier(2)
    try:

        def submit(i: int) -> int:
            with job_sessions() as db:
                barrier.wait(timeout=5)
                try:
                    result = rename_collection(
                        UUID(cid), CollectionPatch(name=f"{cid}-{i}", expected_version=1), db
                    )
                    assert result.version == 2
                    return 200
                except HTTPException as failure:
                    db.rollback()
                    assert failure.detail == "collection_version_conflict"
                    return failure.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(submit, range(2))) == [200, 409]
        with job_sessions() as db:
            assert db.get(PaperCollection, cid).version == 2
    finally:
        with job_sessions() as db:
            db.execute(delete(PaperCollection).where(PaperCollection.id == cid))
            db.commit()
