"""Collapse cleanup enablement and correction mode into one preparation default."""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_unified_preparation_default"
down_revision: str | None = "0002_target_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CLEANUP_ENABLED = "cleanup_enabled_by_default"
_CORRECTION_MODE = "default_correction_mode"
_PREPARATION_DEFAULT = "preparation_default"
_SUPPORTED_CORRECTION_MODES = {"conservative", "smart"}
_SUPPORTED_PREPARATION_DEFAULTS = {"off", *_SUPPORTED_CORRECTION_MODES}


def _settings(connection) -> dict[str, str]:
    rows = connection.execute(
        sa.text(
            "SELECT key, value_json FROM app_settings "
            "WHERE key IN (:cleanup, :correction, :preparation)"
        ),
        {
            "cleanup": _CLEANUP_ENABLED,
            "correction": _CORRECTION_MODE,
            "preparation": _PREPARATION_DEFAULT,
        },
    )
    return {key: value_json for key, value_json in rows}


def _decode(value_json: str, key: str):
    try:
        return json.loads(value_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{key} contains invalid JSON") from exc


def _write(connection, key: str, value: object) -> None:
    connection.execute(
        sa.text(
            "INSERT INTO app_settings (key, value_json, updated_at) "
            "VALUES (:key, :value_json, CURRENT_TIMESTAMP)"
        ),
        {"key": key, "value_json": json.dumps(value)},
    )


def upgrade() -> None:
    connection = op.get_bind()
    settings = _settings(connection)
    if _PREPARATION_DEFAULT in settings:
        raise ValueError("preparation_default already exists before migration")
    if not settings:
        return
    if _CLEANUP_ENABLED not in settings:
        raise ValueError("cleanup_enabled_by_default is required when a legacy mode exists")

    cleanup_enabled = _decode(settings[_CLEANUP_ENABLED], _CLEANUP_ENABLED)
    if type(cleanup_enabled) is not bool:
        raise ValueError("cleanup_enabled_by_default must be a boolean")

    correction_mode = "conservative"
    if _CORRECTION_MODE in settings:
        correction_mode = _decode(settings[_CORRECTION_MODE], _CORRECTION_MODE)
        if correction_mode not in _SUPPORTED_CORRECTION_MODES:
            raise ValueError("default_correction_mode must be conservative or smart")

    preparation_default = correction_mode if cleanup_enabled else "off"
    connection.execute(
        sa.text("DELETE FROM app_settings WHERE key IN (:cleanup, :correction)"),
        {"cleanup": _CLEANUP_ENABLED, "correction": _CORRECTION_MODE},
    )
    _write(connection, _PREPARATION_DEFAULT, preparation_default)


def downgrade() -> None:
    connection = op.get_bind()
    settings = _settings(connection)
    if _CLEANUP_ENABLED in settings or _CORRECTION_MODE in settings:
        raise ValueError("legacy preparation settings already exist before downgrade")
    if _PREPARATION_DEFAULT not in settings:
        return

    preparation_default = _decode(settings[_PREPARATION_DEFAULT], _PREPARATION_DEFAULT)
    if preparation_default not in _SUPPORTED_PREPARATION_DEFAULTS:
        raise ValueError("preparation_default must be off, conservative, or smart")

    connection.execute(
        sa.text("DELETE FROM app_settings WHERE key = :key"),
        {"key": _PREPARATION_DEFAULT},
    )
    _write(connection, _CLEANUP_ENABLED, preparation_default != "off")
    _write(
        connection,
        _CORRECTION_MODE,
        preparation_default if preparation_default != "off" else "conservative",
    )
