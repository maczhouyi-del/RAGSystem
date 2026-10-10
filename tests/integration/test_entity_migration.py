"""Isolated real PostgreSQL coverage migration; no user database modifications."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError


@pytest.mark.integration
def test_entity_mentions_migration_preserves_legacy_and_guards_workflow() -> None:
    source = os.environ.get("TEST_DATABASE_URL")
    if not source:
        pytest.skip("TEST_DATABASE_URL required")
    url = make_url(source)
    name = "ragagent_entity_migration_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    probe = create_engine(url.set(database=name), hide_parameters=True)
    environment = {
        **os.environ,
        "DATABASE_URL": url.set(database=name).render_as_string(hide_password=False),
    }

    def migrate(*args: str, success: bool = True) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout + result.stderr
        assert (result.returncode == 0) == success, output
        return output

    with admin.connect() as db:
        db.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        migrate("upgrade", "0011")
        with probe.begin() as db:
            db.execute(
                text(
                    "INSERT INTO papers(id,title,sha256,status,original_path,created_at) "
                    "VALUES ('p','DEMO',:sha,'indexed','fixture',now())"
                ),
                {"sha": "d" * 64},
            )
            db.execute(
                text(
                    "INSERT INTO sections(id,paper_id,title,path,identity,ordinal) "
                    "VALUES ('s','p','Methods','Methods','s',0)"
                )
            )
            db.execute(
                text(
                    "INSERT INTO chunks(id,paper_id,section_id,section_path,page_start,page_end,"
                    "element_type,content,token_count,ordinal,metadata,embedding) "
                    "VALUES ('c','p','s','Methods',1,1,'text','DEMO',1,0,'{}',:vector)"
                ),
                {"vector": "[" + ",".join(["0"] * 384) + "]"},
            )
        with probe.begin() as db:
            db.execute(
                text("INSERT INTO entities(id,name,entity_type) VALUES ('e','DEMO','dataset')")
            )
            db.execute(text("INSERT INTO chunk_entities(chunk_id,entity_id) VALUES ('c','e')"))
            db.execute(
                text(
                    "INSERT INTO chunk_annotation_reviews"
                    "(chunk_id,content_sha256,status,updated_at) "
                    "VALUES ('c',:sha,'completed',now())"
                ),
                {"sha": "d" * 64},
            )
        migrate("upgrade", "head")
        migrate("check")
        with probe.begin() as db:
            assert db.scalar(text("SELECT content FROM chunks WHERE id='c'")) == "DEMO"
            assert db.scalar(text("SELECT count(*) FROM chunk_entities")) == 1
            assert db.scalar(text("SELECT extractor_version FROM chunk_annotation_reviews")) is None
            db.execute(
                text(
                    "INSERT INTO entity_mentions(id,chunk_id,name,entity_type,span_start,span_end,"
                    "content_sha256,state,origin,owns_link,version,updated_at) VALUES "
                    "('m','c','DEMO','dataset',0,4,:sha,'proposed','source-labels-v1',false,1,now())"
                ),
                {"sha": "d" * 64},
            )
        assert "entity_mentions_downgrade_requires_empty_workflow" in migrate(
            "downgrade", "0011", success=False
        )
        with probe.connect() as db:
            assert (
                db.scalar(text("SELECT version_num FROM alembic_version"))
                == ScriptDirectory.from_config(
                    Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
                ).get_current_head()
            )
        for assignment in [
            "state='invented'",
            "entity_type='invented'",
            "span_end=0",
            "version=0",
            "content_sha256='invalid'",
        ]:
            with pytest.raises(IntegrityError), probe.begin() as db:
                db.execute(text("UPDATE entity_mentions SET " + assignment))
        with probe.begin() as db:
            db.execute(text("DELETE FROM entity_mentions"))
            db.execute(text("UPDATE chunk_annotation_reviews SET status='needs_review'"))
        assert "entity_mentions_downgrade_requires_empty_workflow" in migrate(
            "downgrade", "0011", success=False
        )
        with probe.begin() as db:
            db.execute(
                text(
                    "UPDATE chunk_annotation_reviews SET status='completed',"
                    "extractor_version='source-labels-v1'"
                )
            )
        assert "entity_mentions_downgrade_requires_empty_workflow" in migrate(
            "downgrade", "0011", success=False
        )
        with probe.begin() as db:
            db.execute(text("UPDATE chunk_annotation_reviews SET extractor_version=NULL"))
        migrate("downgrade", "0011")
        migrate("upgrade", "head")
        migrate("check")
        with probe.begin() as db:
            assert db.scalar(text("SELECT original_path FROM papers WHERE id='p'")) == "fixture"
            assert db.scalar(text("SELECT count(*) FROM chunk_entities")) == 1
            db.execute(
                text(
                    "INSERT INTO entity_mentions(id,chunk_id,name,entity_type,span_start,span_end,"
                    "content_sha256,state,origin,owns_link,version,updated_at) VALUES "
                    "('m','c','DEMO','dataset',0,4,:sha,'proposed','source-labels-v1',false,1,now())"
                ),
                {"sha": "d" * 64},
            )
            db.execute(text("DELETE FROM chunks WHERE id='c'"))
            assert db.scalar(text("SELECT count(*) FROM entity_mentions")) == 0
            assert db.scalar(text("SELECT count(*) FROM chunk_annotation_reviews")) == 0
    finally:
        probe.dispose()
        with admin.connect() as db:
            db.execute(
                text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:name"),
                {"name": name},
            )
            db.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()
