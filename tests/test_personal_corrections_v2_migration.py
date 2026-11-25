"""Synthetic-only checks of the explicit empty-store v2 migration boundary."""

import sqlite3
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient

from local_text.admin import _alembic_config
from local_text.app import create_app
from local_text.config import Profile, Settings
from local_text.database import SCHEMA_REVISION, ApplicationDatabase
from local_text.prompt_store import PromptStore
from local_text.target_store import TargetStore

LEGACY = "0006_confirmed_correction_batches"
GUARDED = ("entries", "aliases", "episodes", "episode_mappings", "events")
NOW = "2026-11-25 12:00:00"


def insert(connection, suffix, **values):
    connection.execute(
        f"INSERT INTO personal_correction_{suffix} ({', '.join(values)}) "
        f"VALUES ({', '.join('?' for _ in values)})",
        tuple(values.values()),
    )


def snapshot(path):
    with sqlite3.connect(path) as connection:
        return list(connection.iterdump())


def legacy_database(path):
    database = ApplicationDatabase(path)
    command.upgrade(_alembic_config(database.url), LEGACY)
    PromptStore(database).seed_default()
    TargetStore(database).seed_defaults()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO app_settings VALUES ('synthetic-setting', '\"preserved\"', ?)", (NOW,)
        )
    return database


def profile(connection, enabled=0):
    insert(
        connection, "profiles", owner_id="local", enabled=enabled, created_at=NOW, updated_at=NOW
    )


def entry(connection, identity="entry", **changes):
    values = dict(
        id=identity,
        owner_id="local",
        intended_term="blue boat",
        intended_key="blue boat",
        applicability_context=None,
        enabled=0,
        revision=3,
        created_at=NOW,
        updated_at=NOW,
    )
    values.update(changes)
    insert(connection, "entries", **values)


def episode(connection, **changes):
    values = dict(
        id="episode",
        owner_id="local",
        approval_id=str(uuid4()),
        source_mode="user_confirmed",
        prompt_version_id=None,
        correction_contract_version="personal-correction-v2",
        created_at=NOW,
        review_id=str(uuid4()),
        application_instance_id=str(uuid4()),
        authorization_generation=0,
        passage_id=str(uuid4()),
        draft_revision=7,
        source_kind="original_selection",
        selection_start=13,
        selection_end=21,
        applicability_context="nautical context",
        observed_sentence="A blue boot.",
        intended_sentence="A blue boat.",
    )
    values.update(changes)
    insert(connection, "episodes", **values)


def mapping(connection, **changes):
    values = dict(
        id="mapping",
        owner_id="local",
        episode_id="episode",
        ordinal=1,
        operation="replacement",
        observed_text="blue boot",
        intended_text="blue boat",
        entry_id="entry",
        alias_id="alias",
        before_change_start=5,
        before_change_end=9,
        after_change_start=5,
        after_change_end=9,
        source_start=13,
        source_end=22,
    )
    values.update(changes)
    insert(connection, "episode_mappings", **values)


@pytest.mark.parametrize("enabled", [None, 0, 1])
def test_empty_upgrade_preserves_configuration_and_profile_and_round_trips(tmp_path, enabled):
    database = legacy_database(tmp_path / "empty.sqlite3")
    config = _alembic_config(database.url)
    with sqlite3.connect(database.path) as connection:
        if enabled is not None:
            profile(connection, enabled)
        unrelated = {
            table: connection.execute(f"SELECT * FROM {table}").fetchall()
            for table in (
                "prompt_versions",
                "active_prompt",
                "seed_releases",
                "targets",
                "app_settings",
            )
        }
    command.upgrade(config, "head")
    assert database.schema_status().ready
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        for table, rows in unrelated.items():
            assert connection.execute(f"SELECT * FROM {table}").fetchall() == rows
        assert connection.execute(
            "SELECT owner_id, enabled, authorization_generation, created_at, updated_at "
            "FROM personal_correction_profiles"
        ).fetchall() == ([] if enabled is None else [("local", enabled, 0, NOW, NOW)])
        for suffix in GUARDED:
            assert connection.execute(
                f"SELECT count(*) FROM personal_correction_{suffix}"
            ).fetchone() == (0,)
    command.downgrade(config, LEGACY)
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (LEGACY,)
        assert "authorization_generation" not in {
            row[1] for row in connection.execute("PRAGMA table_info(personal_correction_profiles)")
        }
        for table, rows in unrelated.items():
            assert connection.execute(f"SELECT * FROM {table}").fetchall() == rows
        assert connection.execute(
            "SELECT owner_id, enabled, created_at, updated_at FROM personal_correction_profiles"
        ).fetchall() == ([] if enabled is None else [("local", enabled, NOW, NOW)])
    command.upgrade(config, "head")
    assert database.schema_status().ready


@pytest.mark.parametrize("suffix", GUARDED)
def test_each_populated_table_refuses_without_changing_any_bytes(tmp_path, suffix):
    database = legacy_database(tmp_path / "refuse.sqlite3")
    with sqlite3.connect(database.path) as connection:
        # Deliberately orphaned fixtures isolate each guard, including corrupt legacy stores.
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (0,)
        if suffix == "entries":
            entry(connection)
        elif suffix == "aliases":
            insert(
                connection,
                suffix,
                id="alias",
                owner_id="local",
                entry_id="entry",
                observed_alias="synthetic private phrase",
                alias_key="synthetic private phrase",
                created_at=NOW,
                updated_at=NOW,
            )
        elif suffix == "episodes":
            insert(
                connection,
                suffix,
                id="episode",
                owner_id="local",
                approval_id=str(uuid4()),
                source_mode="user_confirmed",
                correction_contract_version="personal-correction-v1",
                observed_sentence="synthetic private phrase",
                created_at=NOW,
            )
        elif suffix == "episode_mappings":
            insert(
                connection,
                suffix,
                id="mapping",
                owner_id="local",
                episode_id="episode",
                ordinal=1,
                operation="replacement",
                observed_text="synthetic private phrase",
                intended_text="intended",
                entry_id="entry",
                alias_id="alias",
            )
        else:
            insert(
                connection,
                suffix,
                owner_id="local",
                entry_id="entry",
                alias_id="alias",
                use_id=str(uuid4()),
                event_type="alias_observed",
                occurred_at=NOW,
            )
    before = database.path.read_bytes()
    with pytest.raises(RuntimeError) as error:
        command.upgrade(_alembic_config(database.url), "head")
    assert str(error.value) == (
        "Personal Corrections upgrade refused: separately authorized correction-data handling "
        "is required"
    )
    assert database.path.read_bytes() == before
    assert database.schema_status().current_revision == LEGACY


@pytest.mark.parametrize("revision", [LEGACY, "head"])
def test_startup_only_reports_readiness_and_never_writes(tmp_path, revision):
    database = legacy_database(tmp_path / "startup.sqlite3")
    if revision == "head":
        command.upgrade(_alembic_config(database.url), "head")
    with sqlite3.connect(database.path) as connection:
        profile(connection)
        entry(connection)
    before = snapshot(database.path)
    with TestClient(
        create_app(Settings(Profile.DEVELOPMENT, database_path=database.path))
    ) as client:
        response = client.get("/health")
        assert response.status_code == (200 if revision == "head" else 503)
        assert response.json()["database"]["expected_revision"] == SCHEMA_REVISION
    assert snapshot(database.path) == before


@pytest.fixture
def v2_connection(tmp_path):
    database = legacy_database(tmp_path / "v2.sqlite3")
    command.upgrade(_alembic_config(database.url), "head")
    with sqlite3.connect(database.path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        profile(connection)
        yield connection


def test_independent_mapping_identity_and_disabled_state(v2_connection):
    c = v2_connection
    entry(c, operation="replacement", reusable_before_text="blue boot", before_key="blue boot")
    with pytest.raises(sqlite3.IntegrityError):
        entry(
            c,
            "duplicate",
            operation="replacement",
            reusable_before_text="BLUE BOOT",
            before_key="blue boot",
        )
    for identity, changes in (
        ("different-before", dict(reusable_before_text="blew boat", before_key="blew boat")),
        ("different-intended", dict(intended_term="blue coat", intended_key="blue coat")),
        ("restriction", dict(applicability_context="Nautical")),
        ("exact-restriction", dict(applicability_context="nautical")),
        ("operation", dict(operation="addition")),
    ):
        values = dict(
            operation="replacement", reusable_before_text="blue boot", before_key="blue boot"
        )
        values.update(changes)
        entry(c, identity, **values)
    assert (
        c.execute("SELECT enabled, revision FROM personal_correction_entries").fetchall()
        == [(0, 3)] * 6
    )


@pytest.mark.parametrize("kind", ["original_selection", "manual_prepared"])
def test_v2_approved_fields_are_immutable_and_owner_cascades_survive(v2_connection, kind):
    c = v2_connection
    entry(c, operation="replacement", reusable_before_text="blue boot", before_key="blue boot")
    insert(
        c,
        "aliases",
        id="alias",
        owner_id="local",
        entry_id="entry",
        observed_alias="blue boot",
        alias_key="blue boot",
        created_at=NOW,
        updated_at=NOW,
    )
    changes = (
        {}
        if kind == "original_selection"
        else dict(
            source_kind=kind,
            selection_start=None,
            selection_end=None,
            prepared_id=str(uuid4()),
            prepared_generation=4,
            confirmation_id=str(uuid4()),
        )
    )
    episode(c, **changes)
    mapping(c, **({} if kind == "original_selection" else dict(source_start=None, source_end=None)))
    insert(
        c,
        "events",
        owner_id="local",
        entry_id="entry",
        alias_id="alias",
        episode_id="episode",
        use_id=str(uuid4()),
        event_type="alias_observed",
        occurred_at=NOW,
    )
    for statement in (
        "UPDATE personal_correction_episodes SET applicability_context = 'changed'",
        "UPDATE personal_correction_episode_mappings SET observed_text = 'changed'",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            c.execute(statement)
    # Valid parent IDs with a different owner must still fail the composite FK.
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        mapping(c, id="foreign", owner_id="foreign", ordinal=2)
    assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    c.execute("DELETE FROM personal_correction_profiles WHERE owner_id = 'local'")
    for suffix in GUARDED:
        assert c.execute(f"SELECT count(*) FROM personal_correction_{suffix}").fetchone() == (0,)


@pytest.mark.parametrize(
    "changes",
    [
        dict(reusable_before_text="😀" * 201),
        dict(reusable_before_text="bad\ntext"),
        dict(applicability_context="x" * 501),
        dict(operation="unknown"),
        dict(before_key=None),
    ],
)
def test_v2_mapping_bounds_bypass_api(v2_connection, changes):
    values = dict(operation="replacement", reusable_before_text="😀" * 200, before_key="before")
    values.update(changes)
    with pytest.raises(sqlite3.IntegrityError):
        entry(v2_connection, **values)


def test_v2_unicode_bounds_and_approval_binding_validation(v2_connection):
    c = v2_connection
    entry(
        c,
        operation="replacement",
        reusable_before_text="😀" * 200,
        before_key="before",
        intended_term="🦊" * 200,
        applicability_context="x" * 500,
    )
    for changes in (
        dict(review_id=None),
        dict(application_instance_id="x" * 37),
        dict(authorization_generation=-1),
        dict(selection_end=100001),
        dict(source_kind="manual_prepared"),
        dict(observed_sentence="x" * 501),
        dict(applicability_context="bad\x00text"),
        dict(source_mode="smart", prompt_version_id=1),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            episode(c, **changes)
    episode(c, observed_sentence="😀" * 500)


def test_v2_operation_spans_and_source_ranges(v2_connection):
    c = v2_connection
    entry(c, operation="addition", reusable_before_text="blue boat", before_key="blue boat")
    insert(
        c,
        "aliases",
        id="alias",
        owner_id="local",
        entry_id="entry",
        observed_alias="blue boat",
        alias_key="blue boat",
        created_at=NOW,
        updated_at=NOW,
    )
    episode(c)
    # Nonempty reusable phrases retain an anchor; only the individual change is empty.
    mapping(
        c,
        operation="addition",
        observed_text="blue boat",
        intended_text="blue small boat",
        before_change_start=5,
        before_change_end=5,
        after_change_start=5,
        after_change_end=11,
    )
    mapping(
        c,
        id="removal",
        ordinal=2,
        operation="removal",
        observed_text="blue small boat",
        intended_text="blue boat",
        before_change_start=5,
        before_change_end=11,
        after_change_start=5,
        after_change_end=5,
    )
    for changes in (
        dict(before_change_start=None),
        dict(before_change_start=-1),
        dict(before_change_end=10),
        dict(after_change_end=10),
        dict(operation="addition"),
        dict(operation="removal"),
        dict(source_start=None, source_end=None),
        dict(source_end=100001),
        dict(source_end=13),
        dict(ordinal=21),
        dict(ordinal=0),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            mapping(c, id="invalid", ordinal=changes.pop("ordinal", 3), **changes)
    assert c.execute(
        "SELECT operation FROM personal_correction_episode_mappings ORDER BY ordinal"
    ).fetchall() == [("addition",), ("removal",)]


@pytest.mark.parametrize("state", ["mapping", "approval", "generation"])
def test_lossy_downgrade_refuses_before_changing_any_bytes(tmp_path, state):
    database = legacy_database(tmp_path / "downgrade.sqlite3")
    config = _alembic_config(database.url)
    command.upgrade(config, "head")
    with sqlite3.connect(database.path) as c:
        profile(c)
        if state == "mapping":
            entry(c, operation="removal", reusable_before_text="blue boot", before_key="blue boot")
        elif state == "approval":
            episode(c)
        else:
            c.execute("UPDATE personal_correction_profiles SET authorization_generation=1")
    before = database.path.read_bytes()
    config.attributes["acknowledge_destructive_personal_corrections_downgrade"] = True
    with pytest.raises(RuntimeError, match="cannot be represented losslessly"):
        command.downgrade(config, LEGACY)
    assert database.path.read_bytes() == before
    assert database.schema_status().ready
