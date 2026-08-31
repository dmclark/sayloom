"""Create evaluation cases, per-case consent, and safe attempts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_evaluation_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("contract_version", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("source_category", sa.String(16), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("provider_output", sa.Text(), nullable=False),
        sa.Column("expected_cleanup", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("provider_output_sha256", sa.String(64), nullable=False),
        sa.Column("expected_cleanup_sha256", sa.String(64), nullable=False),
        sa.Column("prompt_version_id", sa.String(128), nullable=False),
        sa.Column("prompt_content_sha256", sa.String(64), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("cleanup_schema_version", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(128), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cleanup_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("original_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "contract_version = 'cleanup-evaluation-corpus-v1'",
            name="ck_evaluation_cases_contract",
        ),
        sa.CheckConstraint(
            "purpose = 'polished-cleanup-evaluation-only'",
            name="ck_evaluation_cases_purpose",
        ),
        sa.CheckConstraint(
            "source_category IN ('dictation', 'typed', 'pasted', 'unknown')",
            name="ck_evaluation_cases_source_category",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_evaluation_cases_revision"),
        sa.CheckConstraint(
            "length(source_sha256) = 64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_evaluation_cases_source_hash",
        ),
        sa.CheckConstraint(
            "length(provider_output_sha256) = 64 "
            "AND provider_output_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_evaluation_cases_provider_output_hash",
        ),
        sa.CheckConstraint(
            "length(expected_cleanup_sha256) = 64 "
            "AND expected_cleanup_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_evaluation_cases_expected_cleanup_hash",
        ),
        sa.CheckConstraint(
            "length(prompt_content_sha256) = 64 "
            "AND prompt_content_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_evaluation_cases_prompt_hash",
        ),
        sa.CheckConstraint(
            "expires_at <= original_expires_at", name="ck_evaluation_cases_shortened_expiry"
        ),
    )
    op.create_table(
        "evaluation_consents",
        sa.Column(
            "case_id",
            sa.String(36),
            sa.ForeignKey("evaluation_cases.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version = 'cleanup-evaluation-consent-v1'",
            name="ck_evaluation_consents_version",
        ),
        sa.CheckConstraint(
            "scope = 'polished-cleanup-evaluation-only'",
            name="ck_evaluation_consents_scope",
        ),
    )
    op.create_table(
        "evaluation_attempts",
        sa.Column(
            "case_id",
            sa.String(36),
            sa.ForeignKey("evaluation_cases.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("route_index", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(128), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("failure_class", sa.String(64)),
        sa.Column("provider_code", sa.String(128)),
        sa.Column("http_status", sa.Integer()),
        sa.Column("retry_after_seconds", sa.Integer()),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("cost_usd_micros", sa.Integer()),
        sa.Column("pricing_snapshot_id", sa.String(128)),
        sa.CheckConstraint("route_index >= 0", name="ck_evaluation_attempts_route_index"),
        sa.CheckConstraint(
            "outcome IN ('success', 'failure')", name="ck_evaluation_attempts_outcome"
        ),
        sa.CheckConstraint("elapsed_ms >= 0", name="ck_evaluation_attempts_elapsed"),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_evaluation_attempts_input_tokens",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_evaluation_attempts_output_tokens",
        ),
        sa.CheckConstraint(
            "retry_after_seconds IS NULL OR retry_after_seconds >= 0",
            name="ck_evaluation_attempts_retry_after",
        ),
        sa.CheckConstraint(
            "cost_usd_micros IS NULL OR cost_usd_micros >= 0",
            name="ck_evaluation_attempts_cost",
        ),
        sa.CheckConstraint(
            "(cost_usd_micros IS NULL AND pricing_snapshot_id IS NULL) OR "
            "(cost_usd_micros IS NOT NULL AND pricing_snapshot_id IS NOT NULL)",
            name="ck_evaluation_attempts_cost_snapshot",
        ),
    )


def downgrade() -> None:
    op.drop_table("evaluation_attempts")
    op.drop_table("evaluation_consents")
    op.drop_table("evaluation_cases")
