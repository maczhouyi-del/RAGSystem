"""Keep source tombstones and durable cleanup intent after library removal.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_deletions",
        sa.Column("paper_id", sa.String(36), primary_key=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        *[
            sa.Column(name, postgresql.JSONB(), nullable=False)
            for name in (
                "chunk_ids",
                "evidence_ids",
                "files",
                "cancelled_run_ids",
                "affected_evaluation_ids",
            )
        ],
        sa.Column("last_cleanup_run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False),
    )
    for name in ("chunk_ids", "evidence_ids"):
        op.create_index(
            f"ix_paper_deletions_{name}", "paper_deletions", [name], postgresql_using="gin"
        )
    op.create_index(
        "ix_paper_deletions_last_cleanup_run_id", "paper_deletions", ["last_cleanup_run_id"]
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM paper_deletions)")):
        raise RuntimeError("paper_deletion_downgrade_requires_empty_ledger")
    op.drop_table("paper_deletions")
