"""Add explicitly approved Personal correction episodes and recurrence events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_personal_correction_approval"
down_revision: str | None = "0004_personal_corrections_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DESTRUCTIVE_DOWNGRADE_ACKNOWLEDGEMENT = (
    "acknowledge_destructive_personal_corrections_downgrade"
)


def _valid_text(column: str, maximum: int) -> str:
    return (
        f"length({column}) BETWEEN 1 AND {maximum} AND "
        f"instr({column}, char(0)) = 0 AND "
        f"{column} NOT GLOB ('*[' || char(1) || '-' || char(31) || "
        "char(127) || '-' || char(159) || ']*')"
    )


def upgrade() -> None:
    op.create_index(
        "uq_pc_aliases_id_owner",
        "personal_correction_aliases",
        ["id", "owner_id"],
        unique=True,
    )
    op.create_table(
        "personal_correction_episodes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=20), nullable=False),
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("observed_sentence", sa.Text(), nullable=True),
        sa.Column("intended_sentence", sa.Text(), nullable=True),
        sa.Column("source_mode", sa.String(length=20), nullable=False),
        sa.Column("prompt_version_id", sa.Integer(), nullable=False),
        sa.Column("correction_contract_version", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["personal_correction_profiles.owner_id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint("length(approval_id) = 36", name="ck_pc_episodes_approval_id"),
        sa.CheckConstraint(
            f"observed_sentence IS NULL OR ({_valid_text('observed_sentence', 500)})",
            name="ck_pc_episodes_observed_sentence",
        ),
        sa.CheckConstraint(
            f"intended_sentence IS NULL OR ({_valid_text('intended_sentence', 500)})",
            name="ck_pc_episodes_intended_sentence",
        ),
        sa.CheckConstraint(
            "source_mode IN ('conservative', 'smart')", name="ck_pc_episodes_source_mode"
        ),
        sa.CheckConstraint("prompt_version_id > 0", name="ck_pc_episodes_prompt_version"),
        sa.CheckConstraint(
            "correction_contract_version = 'personal-correction-v1'",
            name="ck_pc_episodes_contract_version",
        ),
        sa.UniqueConstraint("owner_id", "approval_id", name="uq_pc_episodes_owner_approval"),
        sa.UniqueConstraint("id", "owner_id", name="uq_pc_episodes_id_owner"),
    )
    op.create_table(
        "personal_correction_episode_mappings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=20), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("observed_text", sa.Text(), nullable=False),
        sa.Column("intended_text", sa.Text(), nullable=False),
        sa.Column("entry_id", sa.String(length=36), nullable=False),
        sa.Column("alias_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["episode_id", "owner_id"],
            ["personal_correction_episodes.id", "personal_correction_episodes.owner_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id", "owner_id"],
            ["personal_correction_entries.id", "personal_correction_entries.owner_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["alias_id", "owner_id"],
            ["personal_correction_aliases.id", "personal_correction_aliases.owner_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("ordinal = 1", name="ck_pc_episode_mappings_ordinal"),
        sa.CheckConstraint("operation = 'replacement'", name="ck_pc_episode_mappings_operation"),
        sa.CheckConstraint(
            _valid_text("observed_text", 200), name="ck_pc_episode_mappings_observed_text"
        ),
        sa.CheckConstraint(
            _valid_text("intended_text", 200), name="ck_pc_episode_mappings_intended_text"
        ),
        sa.UniqueConstraint("owner_id", "episode_id", "ordinal", name="uq_pc_mapping_ordinal"),
    )
    op.create_table(
        "personal_correction_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.String(length=20), nullable=False),
        sa.Column("entry_id", sa.String(length=36), nullable=False),
        sa.Column("alias_id", sa.String(length=36), nullable=False),
        sa.Column("episode_id", sa.String(length=36), nullable=True),
        sa.Column("use_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id", "owner_id"],
            ["personal_correction_entries.id", "personal_correction_entries.owner_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["alias_id", "owner_id"],
            ["personal_correction_aliases.id", "personal_correction_aliases.owner_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["episode_id", "owner_id"],
            ["personal_correction_episodes.id", "personal_correction_episodes.owner_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("length(use_id) = 36", name="ck_pc_events_use_id"),
        sa.CheckConstraint(
            "event_type IN ('alias_observed', 'profile_supplied', 'intended_produced')",
            name="ck_pc_events_type",
        ),
        sa.UniqueConstraint(
            "owner_id",
            "use_id",
            "entry_id",
            "alias_id",
            "event_type",
            name="uq_pc_events_use_mapping_type",
        ),
    )
    op.create_index(
        "ix_pc_events_owner_entry_time",
        "personal_correction_events",
        ["owner_id", "entry_id", "occurred_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    row_count = connection.execute(
        sa.text(
            "SELECT (SELECT COUNT(*) FROM personal_correction_episodes) + "
            "(SELECT COUNT(*) FROM personal_correction_episode_mappings) + "
            "(SELECT COUNT(*) FROM personal_correction_events)"
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
    op.drop_index("ix_pc_events_owner_entry_time", table_name="personal_correction_events")
    op.drop_table("personal_correction_events")
    op.drop_table("personal_correction_episode_mappings")
    op.drop_table("personal_correction_episodes")
    op.drop_index("uq_pc_aliases_id_owner", table_name="personal_correction_aliases")
