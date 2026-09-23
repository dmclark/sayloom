import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command

from local_text.admin import _alembic_config
from local_text.database import ApplicationDatabase


def predecessor_database(
    path: Path,
    *,
    cleanup_enabled: object = True,
    correction_mode: object = "conservative",
    include_cleanup: bool = True,
    include_mode: bool = True,
) -> ApplicationDatabase:
    database = ApplicationDatabase(path)
    command.upgrade(_alembic_config(database.url), "0002_target_management")
    settings = []
    if include_cleanup:
        settings.append(("cleanup_enabled_by_default", json.dumps(cleanup_enabled)))
    if include_mode:
        settings.append(("default_correction_mode", json.dumps(correction_mode)))
    settings.extend(
        [
            ("cleanup_route_order", '"gemini,openai"'),
            ("paid_data_acknowledgement", '"acknowledged"'),
        ]
    )
    with sqlite3.connect(path) as connection:
        connection.executemany(
            "INSERT INTO app_settings (key, value_json, updated_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            settings,
        )
    return database


def settings(path: Path) -> dict[str, object]:
    with sqlite3.connect(path) as connection:
        return {
            key: json.loads(value)
            for key, value in connection.execute("SELECT key, value_json FROM app_settings")
        }


@pytest.mark.parametrize(
    ("cleanup_enabled", "correction_mode", "include_mode", "expected"),
    [
        (False, "conservative", True, "off"),
        (False, "smart", True, "off"),
        (True, "conservative", True, "conservative"),
        (True, "smart", True, "smart"),
        (True, "conservative", False, "conservative"),
    ],
)
def test_migration_collapses_every_deterministic_legacy_pair_without_touching_routes(
    tmp_path: Path,
    cleanup_enabled: bool,
    correction_mode: str,
    include_mode: bool,
    expected: str,
) -> None:
    database = predecessor_database(
        tmp_path / "local-text.sqlite3",
        cleanup_enabled=cleanup_enabled,
        correction_mode=correction_mode,
        include_mode=include_mode,
    )

    command.upgrade(_alembic_config(database.url), "head")

    assert settings(database.path) == {
        "cleanup_route_order": "gemini,openai",
        "paid_data_acknowledgement": "acknowledged",
        "preparation_default": expected,
    }


@pytest.mark.parametrize(
    ("cleanup_enabled", "correction_mode", "include_cleanup"),
    [
        ("true", "conservative", True),
        (True, "polished", True),
        (True, "smart", False),
    ],
)
def test_migration_rejects_invalid_or_ambiguous_legacy_settings(
    tmp_path: Path,
    cleanup_enabled: object,
    correction_mode: object,
    include_cleanup: bool,
) -> None:
    database = predecessor_database(
        tmp_path / "local-text.sqlite3",
        cleanup_enabled=cleanup_enabled,
        correction_mode=correction_mode,
        include_cleanup=include_cleanup,
    )

    with pytest.raises(ValueError):
        command.upgrade(_alembic_config(database.url), "head")


@pytest.mark.parametrize("preparation_default", ["off", "conservative", "smart"])
def test_migration_downgrade_is_deterministic_and_reupgrade_restores_the_default(
    tmp_path: Path, preparation_default: str
) -> None:
    database = predecessor_database(tmp_path / "local-text.sqlite3")
    command.upgrade(_alembic_config(database.url), "head")
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            "UPDATE app_settings SET value_json = ? WHERE key = 'preparation_default'",
            (json.dumps(preparation_default),),
        )

    command.downgrade(_alembic_config(database.url), "0002_target_management")
    downgraded = settings(database.path)
    assert downgraded["cleanup_enabled_by_default"] is (preparation_default != "off")
    assert downgraded["default_correction_mode"] == (
        preparation_default if preparation_default != "off" else "conservative"
    )

    command.upgrade(_alembic_config(database.url), "head")
    assert settings(database.path)["preparation_default"] == preparation_default
