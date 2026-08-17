import sqlite3
from pathlib import Path

import pytest
from conftest import initialize_database
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from local_text.database import ApplicationDatabase, SchemaState
from local_text.prompt_store import PromptStore
from local_text.prompts import DEFAULT_SYSTEM_PROMPT


def test_schema_check_is_read_only_and_reports_each_noncurrent_state(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.sqlite3"
    missing = ApplicationDatabase(missing_path).schema_status()
    assert missing.state is SchemaState.MISSING
    assert not missing_path.exists()

    uninitialized_path = tmp_path / "uninitialized.sqlite3"
    sqlite3.connect(uninitialized_path).close()
    uninitialized = ApplicationDatabase(uninitialized_path).schema_status()
    assert uninitialized.state is SchemaState.UNINITIALIZED

    mismatch_path = tmp_path / "mismatch.sqlite3"
    with sqlite3.connect(mismatch_path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('obsolete_revision')")
    mismatch = ApplicationDatabase(mismatch_path).schema_status()
    assert mismatch.state is SchemaState.MISMATCH
    assert mismatch.current_revision == "obsolete_revision"


def test_seed_is_deterministic_and_idempotent(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "local-text.sqlite3")
    store = PromptStore(database)

    assert store.seed_default() is False
    history, active_id = store.history()

    assert len(history) == 1
    assert history[0].id == active_id
    assert history[0].version == 1
    assert history[0].source == "seed"
    assert history[0].system_text == DEFAULT_SYSTEM_PROMPT
    assert store.cleanup_enabled_by_default() is True


def test_prompt_versions_are_immutable_and_activation_selects_an_exact_version(
    tmp_path: Path,
) -> None:
    database = initialize_database(tmp_path / "local-text.sqlite3")
    store = PromptStore(database)
    seeded = store.active()
    custom = store.create(
        title="Synthetic custom cleanup",
        system_text="Return synthetic cleaned text only.",
        activate=True,
    )

    assert custom.version == 2
    assert store.active().id == custom.id
    assert store.activate(seeded.id).id == seeded.id
    assert store.active().system_text == DEFAULT_SYSTEM_PROMPT

    with pytest.raises(DatabaseError, match="prompt versions are immutable"):
        with database.engine.begin() as connection:
            connection.execute(
                text("UPDATE prompt_versions SET title = 'mutated' WHERE id = :id"),
                {"id": custom.id},
            )

    history, active_id = store.history()
    assert [prompt.version for prompt in history] == [2, 1]
    assert active_id == seeded.id


def test_cleanup_setting_is_typed_and_durable(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "local-text.sqlite3")
    store = PromptStore(database)

    store.set_cleanup_enabled_by_default(False)

    assert PromptStore(ApplicationDatabase(database.path)).cleanup_enabled_by_default() is False
