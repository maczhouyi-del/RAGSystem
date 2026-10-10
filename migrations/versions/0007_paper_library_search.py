"""Index stable library pages and literal substring searches.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index("ix_papers_created_id", "papers", ["created_at", "id"])
    op.create_index("ix_papers_year_id", "papers", ["year", "id"])
    op.create_index("ix_papers_status_created_id", "papers", ["status", "created_at", "id"])
    op.create_index("ix_paper_authors_author_paper", "paper_authors", ["author_id", "paper_id"])
    for table, column, name in [
        ("papers", "title", "ix_papers_title_trgm"),
        ("papers", "venue", "ix_papers_venue_trgm"),
        ("authors", "name", "ix_authors_name_trgm"),
    ]:
        # All identifiers are fixed source constants, never user input.
        op.execute(f"CREATE INDEX {name} ON {table} USING gin (lower({column}) gin_trgm_ops)")


def downgrade() -> None:
    for table, name in [
        ("authors", "ix_authors_name_trgm"),
        ("papers", "ix_papers_venue_trgm"),
        ("papers", "ix_papers_title_trgm"),
        ("paper_authors", "ix_paper_authors_author_paper"),
        ("papers", "ix_papers_status_created_id"),
        ("papers", "ix_papers_year_id"),
        ("papers", "ix_papers_created_id"),
    ]:
        op.drop_index(name, table_name=table)
    # pg_trgm may predate this migration or serve other tables. Never remove a
    # shared extension; rolling back removes only this task's seven indexes.
