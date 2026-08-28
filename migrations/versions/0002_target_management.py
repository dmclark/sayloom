"""Add durable Sayloom target definitions and operation errors."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_target_management"
down_revision: str | None = "0001_gate2_prompt_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "targets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("application_name", sa.String(length=80), nullable=False),
        sa.Column("application_bundle_id", sa.String(length=255), nullable=False),
        sa.Column("icon", sa.String(length=16), nullable=False),
        sa.Column("send_strategy", sa.String(length=30), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "target_operation_errors",
        sa.Column(
            "target_id",
            sa.String(length=36),
            sa.ForeignKey("targets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("operation", sa.String(length=30), primary_key=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("message", sa.String(length=300), nullable=False),
        sa.Column("retry_action", sa.String(length=300), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("target_operation_errors")
    op.drop_table("targets")
