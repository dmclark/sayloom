"""Prepare empty correction stores for independent mappings and v2 approvals.

Legacy writers remain representable until the separate API compatibility ticket.
No existing correction content is converted by this revision.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_personal_corrections_v2"
down_revision: str | None = "0006_confirmed_correction_batches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "personal_correction_entries",
    "personal_correction_aliases",
    "personal_correction_episodes",
    "personal_correction_episode_mappings",
    "personal_correction_events",
)
_EPISODE_COLUMNS = (
    "review_id",
    "source_kind",
    "application_instance_id",
    "authorization_generation",
    "passage_id",
    "draft_revision",
    "selection_start",
    "selection_end",
    "prepared_id",
    "prepared_generation",
    "confirmation_id",
    "applicability_context",
)
_MAPPING_COLUMNS = (
    "before_change_start",
    "before_change_end",
    "after_change_start",
    "after_change_end",
    "source_start",
    "source_end",
)


def _text(column: str, maximum: int) -> str:
    return (
        f"length({column}) BETWEEN 1 AND {maximum} AND "
        f"instr({column}, char(0)) = 0 AND "
        f"{column} NOT GLOB ('*[' || char(1) || '-' || char(31) || "
        "char(127) || '-' || char(159) || ']*')"
    )


def upgrade() -> None:
    connection = op.get_bind()
    # Acquire SQLite's writer reservation before checking, closing the check/DDL race.
    # No schema or data is changed by BEGIN IMMEDIATE.
    if not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    populated = [
        connection.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar_one()
        for table in _TABLES
    ]
    if any(populated):
        raise RuntimeError(
            "Personal Corrections upgrade refused: separately authorized "
            "correction-data handling is required"
        )

    with op.batch_alter_table("personal_correction_profiles") as batch:
        batch.add_column(
            sa.Column("authorization_generation", sa.Integer(), nullable=False, server_default="0")
        )
        batch.create_check_constraint("ck_pc_profiles_generation", "authorization_generation >= 0")

    with op.batch_alter_table("personal_correction_entries") as batch:
        batch.drop_constraint("uq_pc_entries_owner_key", type_="unique")
        batch.add_column(sa.Column("operation", sa.String(20), nullable=True))
        batch.add_column(sa.Column("reusable_before_text", sa.Text(), nullable=True))
        batch.add_column(sa.Column("before_key", sa.Text(), nullable=True))
        batch.create_check_constraint(
            "ck_pc_entries_mapping",
            "(operation IS NULL AND reusable_before_text IS NULL AND before_key IS NULL) OR "
            "(operation IS NOT NULL AND reusable_before_text IS NOT NULL "
            "AND before_key IS NOT NULL "
            "AND operation IN ('replacement', 'addition', 'removal') AND "
            f"{_text('reusable_before_text', 200)} AND length(before_key) > 0 AND "
            "instr(before_key, char(0)) = 0 AND "
            "before_key NOT GLOB ('*[' || char(1) || '-' || char(31) || "
            "char(127) || '-' || char(159) || ']*') AND length(intended_key) > 0)",
        )
    # COALESCE makes absent restrictions participate in uniqueness rather than SQLite's
    # NULL-distinct behavior. Nonempty restrictions compare exactly, not normalized.
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_pc_entries_mapping_identity ON personal_correction_entries "
            "(owner_id, operation, before_key, intended_key, coalesce(applicability_context, '')) "
            "WHERE operation IS NOT NULL"
        )
    )
    op.create_index(
        "uq_pc_entries_legacy_key",
        "personal_correction_entries",
        ["owner_id", "intended_key"],
        unique=True,
        sqlite_where=sa.text("operation IS NULL"),
    )

    with op.batch_alter_table("personal_correction_episodes") as batch:
        batch.drop_constraint("ck_pc_episodes_contract_version", type_="check")
        for name in _EPISODE_COLUMNS:
            kind = (
                sa.Integer()
                if name
                in {
                    "authorization_generation",
                    "draft_revision",
                    "selection_start",
                    "selection_end",
                    "prepared_generation",
                }
                else sa.Text()
            )
            batch.add_column(sa.Column(name, kind, nullable=True))
        batch.create_check_constraint(
            "ck_pc_episodes_contract_version",
            "correction_contract_version IN ('personal-correction-v1', 'personal-correction-v2')",
        )
        batch.create_check_constraint(
            "ck_pc_episodes_v2_binding",
            "correction_contract_version != 'personal-correction-v2' OR ("
            "source_mode = 'user_confirmed' AND prompt_version_id IS NULL AND "
            "review_id IS NOT NULL AND application_instance_id IS NOT NULL AND "
            f"{_text('review_id', 36)} AND {_text('application_instance_id', 36)} AND "
            "authorization_generation IS NOT NULL AND authorization_generation >= 0 AND "
            f"passage_id IS NOT NULL AND {_text('passage_id', 36)} AND "
            "draft_revision IS NOT NULL AND draft_revision >= 0 AND source_kind IS NOT NULL AND ("
            "(source_kind = 'original_selection' AND selection_start IS NOT NULL AND "
            "selection_end IS NOT NULL AND selection_start >= 0 AND "
            "selection_end > selection_start AND selection_end <= 100000 AND "
            "prepared_id IS NULL AND prepared_generation IS NULL AND confirmation_id IS NULL) OR "
            "(source_kind = 'manual_prepared' AND selection_start IS NULL AND "
            "selection_end IS NULL AND prepared_id IS NOT NULL AND "
            f"{_text('prepared_id', 36)} AND prepared_generation IS NOT NULL AND "
            "prepared_generation >= 0 AND confirmation_id IS NOT NULL AND "
            f"{_text('confirmation_id', 36)})))",
        )
        batch.create_check_constraint(
            "ck_pc_episodes_context",
            f"applicability_context IS NULL OR ({_text('applicability_context', 500)})",
        )

    with op.batch_alter_table("personal_correction_episode_mappings") as batch:
        batch.drop_constraint("ck_pc_episode_mappings_operation", type_="check")
        batch.create_check_constraint(
            "ck_pc_episode_mappings_operation",
            "operation IN ('replacement', 'addition', 'removal')",
        )
        for name in _MAPPING_COLUMNS:
            batch.add_column(sa.Column(name, sa.Integer(), nullable=True))
        batch.create_check_constraint(
            "ck_pc_mapping_spans",
            "(before_change_start IS NULL AND before_change_end IS NULL AND "
            "after_change_start IS NULL AND after_change_end IS NULL "
            "AND operation = 'replacement') OR "
            "(before_change_start IS NOT NULL AND before_change_end IS NOT NULL AND "
            "after_change_start IS NOT NULL AND after_change_end IS NOT NULL AND "
            "before_change_start >= 0 AND before_change_end >= before_change_start AND "
            "before_change_end <= length(observed_text) AND after_change_start >= 0 AND "
            "after_change_end >= after_change_start AND after_change_end <= length(intended_text) "
            "AND ((operation = 'replacement' AND before_change_end > before_change_start AND "
            "after_change_end > after_change_start) OR (operation = 'addition' AND "
            "before_change_end = before_change_start AND after_change_end > after_change_start) OR "
            "(operation = 'removal' AND before_change_end > before_change_start AND "
            "after_change_end = after_change_start)))",
        )
        batch.create_check_constraint(
            "ck_pc_mapping_source_range",
            "(source_start IS NULL AND source_end IS NULL) OR (source_start IS NOT NULL AND "
            "source_end IS NOT NULL AND source_start >= 0 AND source_end > source_start AND "
            "source_end <= 100000)",
        )

    # Approved values may be deleted by future privacy work, never rewritten in place.
    op.execute(
        sa.text(
            "CREATE TRIGGER pc_v2_episode_immutable BEFORE UPDATE ON personal_correction_episodes "
            "WHEN OLD.correction_contract_version = 'personal-correction-v2' OR "
            "NEW.correction_contract_version = 'personal-correction-v2' "
            "BEGIN SELECT RAISE(ABORT, 'immutable Personal Correction approval'); END"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER pc_v2_mapping_immutable BEFORE UPDATE ON "
            "personal_correction_episode_mappings WHEN EXISTS (SELECT 1 FROM "
            "personal_correction_episodes WHERE ((id = OLD.episode_id AND owner_id = OLD.owner_id) "
            "OR (id = NEW.episode_id AND owner_id = NEW.owner_id)) "
            "AND correction_contract_version = 'personal-correction-v2') "
            "BEGIN SELECT RAISE(ABORT, 'immutable Personal Correction approval'); END"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER pc_v2_mapping_binding BEFORE INSERT "
            "ON personal_correction_episode_mappings "
            "WHEN EXISTS (SELECT 1 FROM personal_correction_episodes WHERE id = NEW.episode_id "
            "AND owner_id = NEW.owner_id "
            "AND correction_contract_version = 'personal-correction-v2' "
            "AND (NEW.before_change_start IS NULL OR NEW.ordinal > 20 OR "
            "(source_kind = 'original_selection' AND NEW.source_start IS NULL) OR "
            "(source_kind = 'manual_prepared' AND NEW.source_start IS NOT NULL))) "
            "BEGIN SELECT RAISE(ABORT, 'invalid Personal Correction binding'); END"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    if not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    # Even replacement v2 mappings have independent identity/state the old schema loses.
    episode_metadata = " OR ".join(f"{name} IS NOT NULL" for name in _EPISODE_COLUMNS)
    mapping_metadata = " OR ".join(f"{name} IS NOT NULL" for name in _MAPPING_COLUMNS)
    incompatible = connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM personal_correction_entries "
            "WHERE operation IS NOT NULL) OR "
            "EXISTS (SELECT 1 FROM personal_correction_profiles "
            "WHERE authorization_generation != 0) OR "
            "EXISTS (SELECT 1 FROM personal_correction_episodes WHERE "
            f"correction_contract_version = 'personal-correction-v2' OR {episode_metadata}) OR "
            "EXISTS (SELECT 1 FROM personal_correction_episode_mappings WHERE "
            f"operation != 'replacement' OR {mapping_metadata})"
        )
    ).scalar_one()
    if incompatible:
        raise RuntimeError(
            "cannot downgrade: v2 Personal Corrections cannot be represented losslessly"
        )
    for trigger in ("pc_v2_mapping_binding", "pc_v2_mapping_immutable", "pc_v2_episode_immutable"):
        op.execute(sa.text(f"DROP TRIGGER {trigger}"))
    with op.batch_alter_table("personal_correction_episode_mappings") as batch:
        for name in (
            "ck_pc_mapping_spans",
            "ck_pc_mapping_source_range",
            "ck_pc_episode_mappings_operation",
        ):
            batch.drop_constraint(name, type_="check")
        for name in _MAPPING_COLUMNS:
            batch.drop_column(name)
        batch.create_check_constraint(
            "ck_pc_episode_mappings_operation", "operation = 'replacement'"
        )
    with op.batch_alter_table("personal_correction_episodes") as batch:
        for name in (
            "ck_pc_episodes_v2_binding",
            "ck_pc_episodes_context",
            "ck_pc_episodes_contract_version",
        ):
            batch.drop_constraint(name, type_="check")
        for name in _EPISODE_COLUMNS:
            batch.drop_column(name)
        batch.create_check_constraint(
            "ck_pc_episodes_contract_version",
            "correction_contract_version = 'personal-correction-v1'",
        )
    op.drop_index("uq_pc_entries_mapping_identity", table_name="personal_correction_entries")
    op.drop_index("uq_pc_entries_legacy_key", table_name="personal_correction_entries")
    with op.batch_alter_table("personal_correction_entries") as batch:
        batch.drop_constraint("ck_pc_entries_mapping", type_="check")
        for name in ("operation", "reusable_before_text", "before_key"):
            batch.drop_column(name)
        batch.create_unique_constraint("uq_pc_entries_owner_key", ["owner_id", "intended_key"])
    with op.batch_alter_table("personal_correction_profiles") as batch:
        batch.drop_constraint("ck_pc_profiles_generation", type_="check")
        batch.drop_column("authorization_generation")
