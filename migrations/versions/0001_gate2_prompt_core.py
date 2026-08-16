"""Create the durable prompt core."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_gate2_prompt_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("system_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "active_prompt",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "prompt_version_id",
            sa.Integer(),
            sa.ForeignKey("prompt_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_active_prompt_singleton"),
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=80), primary_key=True),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "seed_releases",
        sa.Column("release_id", sa.String(length=120), primary_key=True),
        sa.Column(
            "prompt_version_id",
            sa.Integer(),
            sa.ForeignKey("prompt_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "import_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("preview_digest", sa.String(length=64), nullable=False, unique=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_import_runs_singleton"),
    )
    op.execute(
        """CREATE TRIGGER prompt_versions_no_update
        BEFORE UPDATE ON prompt_versions
        BEGIN
          SELECT RAISE(ABORT, 'prompt versions are immutable');
        END"""
    )
    op.execute(
        """CREATE TRIGGER prompt_versions_no_delete
        BEFORE DELETE ON prompt_versions
        BEGIN
          SELECT RAISE(ABORT, 'prompt versions are immutable');
        END"""
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS prompt_versions_no_delete")
    op.execute("DROP TRIGGER IF EXISTS prompt_versions_no_update")
    op.drop_table("import_runs")
    op.drop_table("seed_releases")
    op.drop_table("app_settings")
    op.drop_table("active_prompt")
    op.drop_table("prompt_versions")
