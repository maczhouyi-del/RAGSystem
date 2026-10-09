"""Real isolated PostgreSQL upgrade/guarded downgrade, no user database changes."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.mark.integration
def test_organization_migration_preserves_legacy_and_rejects_lossy_downgrade() -> None:
    source = os.environ.get("TEST_DATABASE_URL")
    if not source:
        pytest.skip("TEST_DATABASE_URL required")
    url = make_url(source)
    name = "ragagent_collection_migration_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    probe = create_engine(url.set(database=name), hide_parameters=True)
    root = Path(__file__).resolve().parents[2]
    environment = {
        **os.environ,
        "DATABASE_URL": url.set(database=name).render_as_string(hide_password=False),
    }

    def migrate(*args: str, success: bool = True) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=root,
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
        migrate("upgrade", "0009")
        with probe.begin() as db:
            db.execute(
                text(
                    "INSERT INTO papers (id,title,sha256,status,original_path,created_at) "
                    "VALUES ('legacy','DEMO',:sha,'queued','fixture.pdf',now())"
                ),
                {"sha": "d" * 64},
            )
        migrate("upgrade", "head")
        migrate("check")
        with probe.begin() as db:
            assert db.scalar(text("SELECT count(*) FROM paper_collections")) == 0
            assert db.scalar(text("SELECT title FROM papers WHERE id='legacy'")) == "DEMO"
            db.execute(
                text(
                    "INSERT INTO paper_collections (id,kind,name,name_key) "
                    "VALUES ('fixture','group','DEMO','demo')"
                )
            )
            db.execute(
                text(
                    "INSERT INTO paper_collection_members (paper_id,collection_id) "
                    "VALUES ('legacy','fixture')"
                )
            )
        assert "paper_collections_downgrade_requires_empty_organization" in migrate(
            "downgrade", "0009", success=False
        )
        with probe.begin() as db:
            assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0010"
            assert db.scalar(text("SELECT count(*) FROM paper_collection_members")) == 1
            assert (
                db.scalar(text("SELECT original_path FROM papers WHERE id='legacy'"))
                == "fixture.pdf"
            )
            db.execute(text("DELETE FROM paper_collections"))
            assert db.scalar(text("SELECT count(*) FROM paper_collection_members")) == 0
        migrate("downgrade", "0009")
        migrate("upgrade", "head")
        migrate("check")
        with probe.begin() as db:
            assert db.scalar(text("SELECT title FROM papers WHERE id='legacy'")) == "DEMO"
    finally:
        probe.dispose()
        with admin.connect() as db:
            db.execute(
                text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:name"),
                {"name": name},
            )
            db.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()
