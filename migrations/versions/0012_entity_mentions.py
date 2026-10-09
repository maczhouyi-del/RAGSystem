"""Source spans for proposed/confirmed entities, pending human coverage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_annotation_review_status", "chunk_annotation_reviews")
    op.create_check_constraint(
        "ck_annotation_review_status",
        "chunk_annotation_reviews",
        "status IN ('queued', 'processing', 'needs_review', 'completed', 'failed')",
    )
    op.add_column("chunk_annotation_reviews", sa.Column("extractor_version", sa.String(64)))
    op.create_table(
        "entity_mentions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "chunk_id",
            sa.String(36),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("entities.id")),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("entity_type", sa.String(16), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=False),
        sa.Column("span_end", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("origin", sa.String(64), nullable=False),
        sa.Column("alias_group", sa.String(36)),
        sa.Column("owns_link", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('dataset', 'method', 'metric')", name="ck_entity_mentions_type"
        ),
        sa.CheckConstraint(
            "state IN ('proposed', 'confirmed', 'rejected')", name="ck_entity_mentions_state"
        ),
        sa.CheckConstraint(
            "span_start >= 0 AND span_end > span_start", name="ck_entity_mentions_span"
        ),
        sa.CheckConstraint("version >= 1", name="ck_entity_mentions_version"),
        sa.CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_entity_mentions_hash"),
        sa.UniqueConstraint(
            "chunk_id",
            "entity_type",
            "name",
            "span_start",
            "span_end",
            "content_sha256",
            name="uq_entity_mentions_occurrence",
        ),
    )
    op.create_index("ix_entity_mentions_chunk_id", "entity_mentions", ["chunk_id"])


def downgrade() -> None:
    db = op.get_bind()
    if db.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM entity_mentions) OR EXISTS "
            "(SELECT 1 FROM chunk_annotation_reviews "
            "WHERE status='needs_review' OR extractor_version IS NOT NULL)"
        )
    ):
        raise RuntimeError("entity_mentions_downgrade_requires_empty_workflow")
    op.drop_table("entity_mentions")
    op.drop_column("chunk_annotation_reviews", "extractor_version")
    op.drop_constraint("ck_annotation_review_status", "chunk_annotation_reviews")
    op.create_check_constraint(
        "ck_annotation_review_status",
        "chunk_annotation_reviews",
        "status IN ('queued', 'processing', 'completed', 'failed')",
    )
