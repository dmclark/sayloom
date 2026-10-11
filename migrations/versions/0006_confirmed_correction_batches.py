"""Allow manually confirmed correction episodes with multiple replacements."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_confirmed_correction_batches"
down_revision: str | None = "0005_personal_correction_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("personal_correction_episodes") as batch:
        batch.drop_constraint("ck_pc_episodes_source_mode", type_="check")
        batch.drop_constraint("ck_pc_episodes_prompt_version", type_="check")
        batch.alter_column("prompt_version_id", existing_type=sa.Integer(), nullable=True)
        batch.create_check_constraint(
            "ck_pc_episodes_provenance",
            "(source_mode = 'user_confirmed' AND prompt_version_id IS NULL) OR "
            "(source_mode IN ('conservative', 'smart') AND "
            "prompt_version_id IS NOT NULL AND prompt_version_id > 0)",
        )
    with op.batch_alter_table("personal_correction_episode_mappings") as batch:
        batch.drop_constraint("ck_pc_episode_mappings_ordinal", type_="check")
        batch.create_check_constraint("ck_pc_episode_mappings_ordinal", "ordinal > 0")


def downgrade() -> None:
    connection = op.get_bind()
    incompatible = connection.execute(
        sa.text(
            "SELECT (SELECT COUNT(*) FROM personal_correction_episodes "
            "WHERE source_mode = 'user_confirmed') + "
            "(SELECT COUNT(*) FROM personal_correction_episode_mappings WHERE ordinal > 1)"
        )
    ).scalar_one()
    if incompatible:
        raise RuntimeError("cannot downgrade while confirmed or multi-mapping episodes exist")
    with op.batch_alter_table("personal_correction_episode_mappings") as batch:
        batch.drop_constraint("ck_pc_episode_mappings_ordinal", type_="check")
        batch.create_check_constraint("ck_pc_episode_mappings_ordinal", "ordinal = 1")
    with op.batch_alter_table("personal_correction_episodes") as batch:
        batch.drop_constraint("ck_pc_episodes_provenance", type_="check")
        batch.alter_column("prompt_version_id", existing_type=sa.Integer(), nullable=False)
        batch.create_check_constraint(
            "ck_pc_episodes_source_mode", "source_mode IN ('conservative', 'smart')"
        )
        batch.create_check_constraint("ck_pc_episodes_prompt_version", "prompt_version_id > 0")
