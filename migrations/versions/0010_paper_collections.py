"""Organize existing papers without copying source or scientific evidence.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_collections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint("kind IN ('group', 'tag')", name="ck_paper_collections_kind"),
        sa.CheckConstraint("version >= 1", name="ck_paper_collections_version"),
        sa.UniqueConstraint("kind", "name_key", name="uq_paper_collections_kind_name"),
    )
    op.create_table(
        "paper_collection_members",
        sa.Column(
            "paper_id",
            sa.String(36),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "collection_id",
            sa.String(36),
            sa.ForeignKey("paper_collections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_collection_members_collection_paper",
        "paper_collection_members",
        ["collection_id", "paper_id"],
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM paper_collections)")):
        raise RuntimeError("paper_collections_downgrade_requires_empty_organization")
    op.drop_table("paper_collection_members")
    op.drop_table("paper_collections")
