"""Preserve import metadata and detect stale edits without rewriting originals.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("papers", sa.Column("original_metadata", postgresql.JSONB(), nullable=True))
    op.add_column(
        "papers", sa.Column("metadata_version", sa.Integer(), server_default="1", nullable=False)
    )
    op.add_column(
        "papers",
        sa.Column(
            "overridden_fields",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint("ck_papers_metadata_version", "papers", "metadata_version >= 1")
    # Legacy records keep NULL original metadata: current titles may already
    # contain corrections, so they cannot be labeled official import snapshots.


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM papers WHERE original_metadata IS NOT NULL "
            "OR metadata_version <> 1 OR overridden_fields <> '[]'::jsonb)"
        )
    ):
        raise RuntimeError("metadata_provenance_downgrade_requires_pristine_records")
    op.drop_constraint("ck_papers_metadata_version", "papers", type_="check")
    op.drop_column("papers", "overridden_fields")
    op.drop_column("papers", "metadata_version")
    op.drop_column("papers", "original_metadata")
