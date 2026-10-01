"""Add the non-destructive Personal corrections profile foundation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_personal_corrections_foundation"
down_revision: str | None = "0003_unified_preparation_default"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DESTRUCTIVE_DOWNGRADE_ACKNOWLEDGEMENT = (
    "acknowledge_destructive_personal_corrections_downgrade"
)


def _reject_control_characters(column: str) -> str:
    return (
        f"instr({column}, char(0)) = 0 AND "
        f"{column} NOT GLOB ('*[' || char(1) || '-' || char(31) || "
        "char(127) || '-' || char(159) || ']*')"
    )


def upgrade() -> None:
    op.create_table(
        "personal_correction_profiles",
        sa.Column("owner_id", sa.String(length=20), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("owner_id = 'local'", name="ck_pc_profiles_local_owner"),
        sa.CheckConstraint("enabled IN (0, 1)", name="ck_pc_profiles_enabled"),
    )
    op.create_table(
        "personal_correction_entries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(length=20),
            sa.ForeignKey("personal_correction_profiles.owner_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("intended_term", sa.Text(), nullable=False),
        sa.Column("intended_key", sa.Text(), nullable=False),
        sa.Column("applicability_context", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(intended_term) BETWEEN 1 AND 200",
            name="ck_pc_entries_intended_term_length",
        ),
        sa.CheckConstraint(
            _reject_control_characters("intended_term"),
            name="ck_pc_entries_intended_term_controls",
        ),
        sa.CheckConstraint(
            _reject_control_characters("intended_key"),
            name="ck_pc_entries_intended_key_controls",
        ),
        sa.CheckConstraint(
            "applicability_context IS NULL OR "
            "(length(applicability_context) BETWEEN 1 AND 500 "
            f"AND {_reject_control_characters('applicability_context')})",
            name="ck_pc_entries_context",
        ),
        sa.CheckConstraint("enabled IN (0, 1)", name="ck_pc_entries_enabled"),
        sa.CheckConstraint("revision > 0", name="ck_pc_entries_revision"),
        sa.UniqueConstraint("owner_id", "intended_key", name="uq_pc_entries_owner_key"),
        sa.UniqueConstraint("id", "owner_id", name="uq_pc_entries_id_owner"),
    )
    op.create_index(
        "ix_pc_entries_owner_enabled", "personal_correction_entries", ["owner_id", "enabled"]
    )
    op.create_table(
        "personal_correction_aliases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=20), nullable=False),
        sa.Column("entry_id", sa.String(length=36), nullable=False),
        sa.Column("observed_alias", sa.Text(), nullable=False),
        sa.Column("alias_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id", "owner_id"],
            ["personal_correction_entries.id", "personal_correction_entries.owner_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "length(observed_alias) BETWEEN 1 AND 200",
            name="ck_pc_aliases_observed_alias_length",
        ),
        sa.CheckConstraint(
            _reject_control_characters("observed_alias"),
            name="ck_pc_aliases_observed_alias_controls",
        ),
        sa.CheckConstraint(
            _reject_control_characters("alias_key"),
            name="ck_pc_aliases_alias_key_controls",
        ),
        sa.UniqueConstraint(
            "owner_id", "entry_id", "alias_key", name="uq_pc_aliases_owner_entry_key"
        ),
    )
    op.create_index(
        "ix_pc_aliases_owner_key", "personal_correction_aliases", ["owner_id", "alias_key"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    row_count = connection.execute(
        sa.text(
            "SELECT "
            "(SELECT COUNT(*) FROM personal_correction_profiles) + "
            "(SELECT COUNT(*) FROM personal_correction_entries) + "
            "(SELECT COUNT(*) FROM personal_correction_aliases)"
        )
    ).scalar_one()
    acknowledged = bool(
        op.get_context().config.attributes.get(_DESTRUCTIVE_DOWNGRADE_ACKNOWLEDGEMENT)
    )
    if row_count and not acknowledged:
        raise RuntimeError(
            "destructive Personal corrections downgrade requires explicit acknowledgement "
            "after creating and verifying a private export"
        )
    op.drop_index("ix_pc_aliases_owner_key", table_name="personal_correction_aliases")
    op.drop_table("personal_correction_aliases")
    op.drop_index("ix_pc_entries_owner_enabled", table_name="personal_correction_entries")
    op.drop_table("personal_correction_entries")
    op.drop_table("personal_correction_profiles")
