"""Add review annotations and fixed benchmark holds."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_evaluation_lifecycle"
down_revision: str | None = "0001_evaluation_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_annotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "case_id",
            sa.String(36),
            sa.ForeignKey("evaluation_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("protocol_tag", sa.String(128), nullable=False),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("source_start", sa.Integer(), nullable=False),
        sa.Column("source_end", sa.Integer(), nullable=False),
        sa.Column("acceptable_values_json", sa.Text(), nullable=False),
        sa.CheckConstraint("source_start >= 0", name="ck_evaluation_annotations_source_start"),
        sa.CheckConstraint(
            "source_end >= source_start", name="ck_evaluation_annotations_source_end"
        ),
    )
    op.create_table(
        "benchmark_holds",
        sa.Column(
            "case_id",
            sa.String(36),
            sa.ForeignKey("evaluation_cases.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("benchmark_id", sa.String(128), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("release_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("case_id", name="uq_benchmark_holds_case"),
    )


def downgrade() -> None:
    op.drop_table("benchmark_holds")
    op.drop_table("evaluation_annotations")
