import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import event

from local_text.admin import _alembic_config
from local_text.app import create_app
from local_text.config import Profile, Settings
from local_text.database import ApplicationDatabase
from local_text.personal_corrections import (
    PersonalCorrectionNotFoundError,
    PersonalCorrectionRevisionConflictError,
    PersonalCorrectionStore,
)

PREDECESSOR_REVISION = "0003_unified_preparation_default"
PERSONAL_CORRECTIONS_REVISION = "0005_personal_correction_approval"


def migrated_database(path: Path) -> ApplicationDatabase:
    database = ApplicationDatabase(path)
    command.upgrade(_alembic_config(database.url), "head")
    return database


def test_migration_creates_empty_owned_profile_schema_and_round_trips(tmp_path: Path) -> None:
    database = ApplicationDatabase(tmp_path / "personal-corrections.sqlite3")
    config = _alembic_config(database.url)
    command.upgrade(config, PREDECESSOR_REVISION)

    with sqlite3.connect(database.path) as connection:
        connection.execute(
            "INSERT INTO app_settings (key, value_json, updated_at) "
            "VALUES ('synthetic_setting', '\"preserved\"', CURRENT_TIMESTAMP)"
        )

    command.upgrade(config, "head")

    with sqlite3.connect(database.path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "personal_correction_profiles",
            "personal_correction_entries",
            "personal_correction_aliases",
        } <= tables
        assert connection.execute(
            "SELECT COUNT(*) FROM personal_correction_profiles"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT value_json FROM app_settings WHERE key = 'synthetic_setting'"
        ).fetchone() == ('"preserved"',)
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            PERSONAL_CORRECTIONS_REVISION,
        )

    command.downgrade(config, PREDECESSOR_REVISION)
    with sqlite3.connect(database.path) as connection:
        remaining = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "personal_correction_aliases" not in remaining
        assert "personal_correction_entries" not in remaining
        assert "personal_correction_profiles" not in remaining
        assert connection.execute(
            "SELECT value_json FROM app_settings WHERE key = 'synthetic_setting'"
        ).fetchone() == ('"preserved"',)

    command.upgrade(config, "head")
    with sqlite3.connect(database.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM personal_correction_profiles"
        ).fetchone() == (0,)


def test_migration_enforces_storage_checks_uniqueness_and_owned_alias_foreign_key(
    tmp_path: Path,
) -> None:
    database = migrated_database(tmp_path / "constraints.sqlite3")
    with sqlite3.connect(database.path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO personal_correction_profiles "
            "(owner_id, enabled, created_at, updated_at) "
            "VALUES ('local', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        entry_sql = (
            "INSERT INTO personal_correction_entries "
            "(id, owner_id, intended_term, intended_key, applicability_context, enabled, "
            "revision, created_at, updated_at) VALUES (?, 'local', ?, ?, NULL, 1, 1, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(entry_sql, ("too-long", "x" * 201, "too long"))
        connection.execute(entry_sql, ("owned-entry", "Synthetic term", "synthetic term"))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(entry_sql, ("duplicate-entry", "Other display", "synthetic term"))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO personal_correction_aliases "
                "(id, owner_id, entry_id, observed_alias, alias_key, created_at, updated_at) "
                "VALUES ('wrong-owner-alias', 'foreign', 'owned-entry', 'Alias', 'alias', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        indexes = {
            row[1]
            for row in connection.execute(
                "PRAGMA index_list('personal_correction_aliases')"
            )
        }
        assert "ix_pc_aliases_owner_key" in indexes


def test_migration_rejects_control_characters_but_preserves_unicode_via_direct_sql(
    tmp_path: Path,
) -> None:
    database = migrated_database(tmp_path / "text-constraints.sqlite3")
    with sqlite3.connect(database.path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO personal_correction_profiles "
            "(owner_id, enabled, created_at, updated_at) "
            "VALUES ('local', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        entry_sql = (
            "INSERT INTO personal_correction_entries "
            "(id, owner_id, intended_term, intended_key, applicability_context, enabled, "
            "revision, created_at, updated_at) VALUES (?, 'local', ?, ?, ?, 1, 1, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        alias_sql = (
            "INSERT INTO personal_correction_aliases "
            "(id, owner_id, entry_id, observed_alias, alias_key, created_at, updated_at) "
            "VALUES (?, 'local', 'unicode-entry', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )

        connection.execute(
            entry_sql,
            ("unicode-entry", "München 東京 😀", "münchen 東京 😀", "Café résumé"),
        )
        connection.execute(
            alias_sql,
            ("unicode-alias", "Mün chen 東京 😀", "mün chen 東京 😀"),
        )

        for index, control in enumerate(("\n", "\t", "\x1f")):
            invalid_entries = (
                (f"term-{index}", f"bad{control}term", f"term key {index}", None),
                (f"key-{index}", "Valid term", f"bad{control}key {index}", None),
                (
                    f"context-{index}",
                    "Valid context term",
                    f"context key {index}",
                    f"bad{control}context",
                ),
            )
            for values in invalid_entries:
                with pytest.raises(sqlite3.IntegrityError):
                    connection.execute(entry_sql, values)

            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    alias_sql,
                    (f"alias-display-{index}", f"bad{control}alias", f"alias key {index}"),
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    alias_sql,
                    (f"alias-key-{index}", "Valid alias", f"bad{control}alias key {index}"),
                )

        assert connection.execute(
            "SELECT intended_term, applicability_context FROM personal_correction_entries "
            "WHERE id = 'unicode-entry'"
        ).fetchone() == ("München 東京 😀", "Café résumé")


def test_populated_migration_downgrade_requires_admin_acknowledgement_and_reupgrades(
    tmp_path: Path,
) -> None:
    database = migrated_database(tmp_path / "populated-downgrade.sqlite3")
    PersonalCorrectionStore(database).set_profile_enabled(True)
    config = _alembic_config(database.url)

    with pytest.raises(RuntimeError, match="destructive.*acknowledgement"):
        command.downgrade(config, PREDECESSOR_REVISION)

    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0004_personal_corrections_foundation",
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM personal_correction_profiles"
        ).fetchone() == (1,)

    environment = {**os.environ, "LOCAL_TEXT_DATABASE_PATH": str(database.path)}
    acknowledged = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_text.admin",
            "migrate",
            "--downgrade-to",
            PREDECESSOR_REVISION,
            "--acknowledge-destructive-personal-corrections-downgrade",
        ],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert acknowledged.returncode == 0, acknowledged.stderr

    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            PREDECESSOR_REVISION,
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name LIKE 'personal_correction_%'"
        ).fetchone() == (0,)

    command.upgrade(config, "head")
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            PERSONAL_CORRECTIONS_REVISION,
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM personal_correction_profiles"
        ).fetchone() == (0,)


def test_startup_reports_predecessor_schema_without_migrating_or_seeding(tmp_path: Path) -> None:
    database = ApplicationDatabase(tmp_path / "predecessor.sqlite3")
    command.upgrade(_alembic_config(database.url), PREDECESSOR_REVISION)

    client = TestClient(
        create_app(Settings(Profile.DEVELOPMENT, database_path=database.path))
    )

    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "setup_required"
    assert response.json()["database"] == {
        "state": "mismatch",
        "current_revision": PREDECESSOR_REVISION,
        "expected_revision": PERSONAL_CORRECTIONS_REVISION,
    }
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            PREDECESSOR_REVISION,
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name LIKE 'personal_correction_%'"
        ).fetchone() == (0,)


def test_profile_exists_only_after_explicit_enablement_and_disable_preserves_it(
    tmp_path: Path,
) -> None:
    database = migrated_database(tmp_path / "profile.sqlite3")
    store = PersonalCorrectionStore(database)

    assert store.read().enabled is False
    assert store.set_profile_enabled(False).enabled is False
    with sqlite3.connect(database.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM personal_correction_profiles"
        ).fetchone() == (0,)

    assert store.set_profile_enabled(True).enabled is True
    assert store.set_profile_enabled(False).enabled is False
    with sqlite3.connect(database.path) as connection:
        assert connection.execute(
            "SELECT owner_id, enabled FROM personal_correction_profiles"
        ).fetchall() == [("local", 0)]


def test_entries_are_owner_scoped_normalized_and_disclose_ambiguous_aliases(
    tmp_path: Path,
) -> None:
    database = migrated_database(tmp_path / "entries.sqlite3")
    store = PersonalCorrectionStore(database)
    store.set_profile_enabled(True)

    first = store.create_entry(
        intended_term="Project Atlas",
        aliases=("At lass",),
        applicability_context="Synthetic project name",
    )
    second = store.create_entry(
        intended_term="Atlas Group",
        aliases=("  AT\u00a0 LASS ",),
        applicability_context=None,
    )

    profile = store.read()
    assert [entry.id for entry in profile.entries] == [first.id, second.id]
    assert profile.entries[0].aliases[0].ambiguous is True
    assert profile.entries[1].aliases[0].ambiguous is True
    assert profile.entries[0].revision == 1
    assert profile.entries[0].enabled is True

    with sqlite3.connect(database.path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO personal_correction_profiles "
            "(owner_id, enabled, created_at, updated_at) "
            "VALUES ('foreign', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO personal_correction_entries "
            "(id, owner_id, intended_term, intended_key, applicability_context, enabled, "
            "revision, created_at, updated_at) VALUES "
            "('foreign-entry', 'foreign', 'Foreign term', 'foreign term', NULL, 1, 1, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )

    assert [entry.id for entry in store.read().entries] == [first.id, second.id]
    with pytest.raises(PersonalCorrectionNotFoundError):
        store.update_entry(
            "foreign-entry",
            expected_revision=1,
            intended_term="Mutated",
            aliases=("Changed",),
            applicability_context=None,
            enabled=False,
        )


def test_entry_edits_are_revision_checked_and_replace_aliases_atomically(tmp_path: Path) -> None:
    store = PersonalCorrectionStore(migrated_database(tmp_path / "revision.sqlite3"))
    store.set_profile_enabled(True)
    created = store.create_entry(
        intended_term="Synthetic Name",
        aliases=("Sin thetic", "Synthetic name"),
        applicability_context="Synthetic context",
    )

    updated = store.update_entry(
        created.id,
        expected_revision=1,
        intended_term="Synthetic Name",
        aliases=("Sin theta",),
        applicability_context="",
        enabled=False,
    )

    assert updated.revision == 2
    assert updated.enabled is False
    assert updated.applicability_context is None
    assert [alias.observed_alias for alias in updated.aliases] == ["Sin theta"]
    with pytest.raises(PersonalCorrectionRevisionConflictError):
        store.update_entry(
            created.id,
            expected_revision=1,
            intended_term="Stale overwrite",
            aliases=("Stale",),
            applicability_context=None,
            enabled=True,
        )
    assert store.read().entries[0] == updated


def test_concurrent_entry_edits_atomically_reject_one_stale_revision(tmp_path: Path) -> None:
    database = migrated_database(tmp_path / "concurrent-revision.sqlite3")
    store = PersonalCorrectionStore(database)
    store.set_profile_enabled(True)
    created = store.create_entry(
        intended_term="Original term",
        aliases=("Original alias",),
        applicability_context=None,
    )
    writers_ready = Barrier(2)

    def synchronize_entry_updates(
        _connection, _cursor, statement: str, _parameters, _context, _executemany
    ) -> None:
        if statement.lstrip().upper().startswith("UPDATE PERSONAL_CORRECTION_ENTRIES"):
            writers_ready.wait(timeout=5)

    event.listen(database.engine, "before_cursor_execute", synchronize_entry_updates)

    def update(suffix: str) -> str:
        try:
            store.update_entry(
                created.id,
                expected_revision=1,
                intended_term=f"Term {suffix}",
                aliases=(f"Alias {suffix}",),
                applicability_context=None,
                enabled=True,
            )
        except PersonalCorrectionRevisionConflictError:
            return "conflict"
        return "success"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = sorted(executor.map(update, ("alpha", "beta")))
    finally:
        event.remove(database.engine, "before_cursor_execute", synchronize_entry_updates)

    assert outcomes == ["conflict", "success"]
    persisted = store.read().entries[0]
    assert persisted.revision == 2
    assert persisted.intended_term in {"Term alpha", "Term beta"}
    assert [alias.observed_alias for alias in persisted.aliases] in [
        ["Alias alpha"],
        ["Alias beta"],
    ]


def test_local_api_manages_profile_entries_and_returns_stale_conflicts(
    initialized_settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    empty = client.get("/api/personal-corrections")
    assert empty.status_code == 200
    assert empty.headers["cache-control"] == "no-store"
    assert empty.json() == {"enabled": False, "entries": []}
    owner_attempt = client.put(
        "/api/personal-corrections/profile", json={"enabled": True, "owner_id": "foreign"}
    )
    assert owner_attempt.status_code == 422
    assert "foreign" not in owner_attempt.text

    enabled = client.put("/api/personal-corrections/profile", json={"enabled": True})
    assert enabled.json() == {"enabled": True, "entries": []}
    first = client.post(
        "/api/personal-corrections/entries",
        json={
            "intended_term": "Project Atlas",
            "aliases": ["At lass"],
            "applicability_context": "Synthetic project name",
        },
    )
    assert first.status_code == 201
    assert first.json()["enabled"] is True
    second = client.post(
        "/api/personal-corrections/entries",
        json={
            "intended_term": "Atlas Group",
            "aliases": ["AT  LASS"],
            "applicability_context": None,
        },
    )
    assert second.status_code == 201

    populated = client.get("/api/personal-corrections").json()
    assert populated["entries"][0]["aliases"][0]["ambiguous"] is True
    assert populated["entries"][1]["aliases"][0]["ambiguous"] is True
    entry_id = first.json()["id"]
    update = {
        "expected_revision": 1,
        "intended_term": "Project Atlas",
        "aliases": ["At last"],
        "applicability_context": None,
        "enabled": False,
    }
    saved = client.put(f"/api/personal-corrections/entries/{entry_id}", json=update)
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2
    assert saved.json()["enabled"] is False

    stale = client.put(f"/api/personal-corrections/entries/{entry_id}", json=update)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_personal_correction_revision"
    assert client.delete(f"/api/personal-corrections/entries/{entry_id}").status_code == 405

    disabled = client.put("/api/personal-corrections/profile", json={"enabled": False})
    assert disabled.json()["enabled"] is False
    assert len(disabled.json()["entries"]) == 2


def test_personal_corrections_settings_surface_supports_empty_populated_and_narrow_states(
    initialized_settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    page = client.get("/").text
    script = client.get("/static/app.js").text
    stylesheet = client.get("/static/app.css").text

    assert 'aria-labelledby="personal-corrections-title"' in page
    assert 'id="personal-corrections-toggle"' in page
    assert 'id="personal-correction-form"' in page
    assert 'id="personal-correction-list"' in page
    assert "No corrections saved yet" in page
    assert 'fetch("/api/personal-corrections")' in script
    assert 'method: "POST"' in script
    assert "expected_revision: entry.revision" in script
    assert "This alias also appears under another intended term." in script
    assert ".personal-correction-card" in stylesheet
    narrow = stylesheet.split("@media (max-width: 540px)", maxsplit=1)[1]
    assert ".personal-correction-fields { grid-template-columns: 1fr;" in narrow
