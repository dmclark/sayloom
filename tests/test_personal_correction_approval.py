import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import event

from local_text.admin import _alembic_config
from local_text.app import create_app
from local_text.database import ApplicationDatabase
from local_text.personal_corrections import PersonalCorrectionStore

APPROVAL_TABLES = (
    "personal_correction_profiles",
    "personal_correction_entries",
    "personal_correction_aliases",
    "personal_correction_episodes",
    "personal_correction_episode_mappings",
    "personal_correction_events",
)


def approval_request(prompt_version_id: int, approval_id: str | None = None) -> dict[str, object]:
    return {
        "approval_id": approval_id or str(uuid4()),
        "source_mode": "conservative",
        "prompt_version_id": prompt_version_id,
        "correction_contract_version": "personal-correction-v1",
        "observed_sentence": "Please send the umber parcel.",
        "intended_sentence": "Please send the amber parcel.",
        "applicability_context": "A synthetic parcel color.",
        "mapping": {
            "operation": "replacement",
            "observed_text": "umber",
            "intended_text": "amber",
        },
    }


def row_counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in APPROVAL_TABLES
        }


def test_approval_creates_complete_episode_then_normalized_retry_and_recurrence_reuse(
    initialized_settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    prompt_id = client.get("/api/config").json()["active_prompt_version_id"]
    first_request = approval_request(prompt_id)

    first = client.post("/api/personal-corrections/episodes", json=first_request)
    assert first.status_code == 201
    assert first.headers["cache-control"] == "no-store"
    result = first.json()
    assert result["approval_id"] == first_request["approval_id"]
    assert result["mapping"] == {
        "ordinal": 1,
        "operation": "replacement",
        "observed_text": "umber",
        "intended_text": "amber",
    }
    assert result["correction"]["intended_term"] == "amber"
    assert result["correction"]["aliases"][0]["observed_alias"] == "umber"
    assert row_counts(Path(initialized_settings.database_path)) == {
        "personal_correction_profiles": 1,
        "personal_correction_entries": 1,
        "personal_correction_aliases": 1,
        "personal_correction_episodes": 1,
        "personal_correction_episode_mappings": 1,
        "personal_correction_events": 1,
    }

    retry = client.post("/api/personal-corrections/episodes", json=first_request)
    assert retry.status_code == 200
    assert retry.json() == result
    assert row_counts(Path(initialized_settings.database_path))["personal_correction_events"] == 1

    recurrence = approval_request(prompt_id)
    recurrence["mapping"] = {
        "operation": "replacement",
        "observed_text": "  UMBER ",
        "intended_text": "ＡＭＢＥＲ",
    }
    recurrence["applicability_context"] = "A synthetic parcel color."
    repeated = client.post("/api/personal-corrections/episodes", json=recurrence)

    assert repeated.status_code == 201
    assert repeated.json()["correction"]["id"] == result["correction"]["id"]
    assert (
        repeated.json()["correction"]["aliases"][0]["id"]
        == result["correction"]["aliases"][0]["id"]
    )
    assert row_counts(Path(initialized_settings.database_path)) == {
        "personal_correction_profiles": 1,
        "personal_correction_entries": 1,
        "personal_correction_aliases": 1,
        "personal_correction_episodes": 2,
        "personal_correction_episode_mappings": 2,
        "personal_correction_events": 2,
    }


def test_approval_rolls_back_every_row_when_event_insert_fails(initialized_settings) -> None:
    database = ApplicationDatabase(Path(initialized_settings.database_path))
    store = PersonalCorrectionStore(database)
    inserts = 0

    def fail_event_insert(_connection, _cursor, statement, _parameters, _context, _many):
        nonlocal inserts
        if statement.lstrip().upper().startswith("INSERT INTO PERSONAL_CORRECTION_EVENTS"):
            inserts += 1
            if inserts == 2:
                raise RuntimeError("synthetic event failure")

    event.listen(database.engine, "before_cursor_execute", fail_event_insert)
    try:
        with pytest.raises(RuntimeError, match="synthetic event failure"):
            store.approve_replacements(
                approval_id=str(uuid4()),
                mappings=(("synthetic alias", "synthetic term"), ("other alias", "other term")),
                observed_sentence="A synthetic alias appears.",
                intended_sentence="A synthetic term appears.",
                applicability_context=None,
                source_mode="smart",
                prompt_version_id=1,
                correction_contract_version="personal-correction-v1",
            )
    finally:
        event.remove(database.engine, "before_cursor_execute", fail_event_insert)

    assert row_counts(Path(initialized_settings.database_path)) == {
        table: 0 for table in APPROVAL_TABLES
    }


def test_manual_batch_is_atomic_idempotent_and_honest_with_preparation_off(initialized_settings):
    client = TestClient(create_app(initialized_settings))
    client.put("/api/preferences/preparation-default", json={"preparation_default": "off"})
    request = approval_request(1)
    request["source_mode"] = "user_confirmed"
    request["prompt_version_id"] = None
    request["mappings"] = [
        request.pop("mapping"),
        {"operation": "replacement", "observed_text": "fries day", "intended_text": "Friday"},
        {"operation": "replacement", "observed_text": "UMBER", "intended_text": "AMBER"},
    ]
    first = client.post("/api/personal-corrections/episodes", json=request)
    assert first.status_code == 201
    saved = first.json()
    assert saved["source_mode"] == "user_confirmed"
    assert saved["prompt_version_id"] is None
    assert [(m["ordinal"], m["observed_text"], m["intended_text"]) for m in saved["mappings"]] == [
        (1, "umber", "amber"),
        (2, "fries day", "Friday"),
    ]
    counts = row_counts(Path(initialized_settings.database_path))
    assert counts["personal_correction_episodes"] == 1
    assert counts["personal_correction_episode_mappings"] == 2
    assert counts["personal_correction_entries"] == 2
    retry = client.post("/api/personal-corrections/episodes", json=request)
    assert retry.status_code == 200 and retry.json() == saved
    request["mappings"][1]["intended_text"] = "Thursday"
    assert client.post("/api/personal-corrections/episodes", json=request).status_code == 409
    assert row_counts(Path(initialized_settings.database_path)) == counts

    # A conflict on the second mapping must also roll back the first new mapping.
    request["approval_id"] = str(uuid4())
    request["applicability_context"] = "Different context"
    request["mappings"] = [
        {"operation": "replacement", "observed_text": "new alias", "intended_text": "new term"},
        {"operation": "replacement", "observed_text": "umber", "intended_text": "amber"},
    ]
    assert client.post("/api/personal-corrections/episodes", json=request).status_code == 409
    assert row_counts(Path(initialized_settings.database_path)) == counts
    request["prompt_version_id"] = 1
    assert client.post("/api/personal-corrections/episodes", json=request).status_code == 422
    assert row_counts(Path(initialized_settings.database_path)) == counts


def test_batch_migration_preserves_existing_episode_and_guards_downgrade(initialized_settings):
    client = TestClient(create_app(initialized_settings))
    prompt_id = client.get("/api/config").json()["active_prompt_version_id"]
    request = approval_request(prompt_id)
    saved = client.post("/api/personal-corrections/episodes", json=request).json()
    database = ApplicationDatabase(Path(initialized_settings.database_path))
    config = _alembic_config(database.url)
    counts = row_counts(database.path)
    command.downgrade(config, "0005_personal_correction_approval")
    command.upgrade(config, "head")
    assert row_counts(database.path) == counts
    assert client.post("/api/personal-corrections/episodes", json=request).json() == saved
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE personal_correction_episodes SET source_mode = 'user_confirmed'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE personal_correction_episode_mappings SET ordinal = 0")
    request["approval_id"] = str(uuid4())
    request["source_mode"] = "user_confirmed"
    request["prompt_version_id"] = None
    assert client.post("/api/personal-corrections/episodes", json=request).status_code == 201
    with pytest.raises(RuntimeError, match="cannot downgrade"):
        command.downgrade(config, "0005_personal_correction_approval")
    assert database.schema_status().ready


def test_approval_rejects_stale_prompt_invalid_contract_and_private_values_without_writes(
    initialized_settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    prompt_id = client.get("/api/config").json()["active_prompt_version_id"]
    stale_request = approval_request(prompt_id)
    client.post(
        "/api/prompts",
        json={
            "title": "Synthetic revision",
            "system_text": "Synthetic instruction.",
            "activate": True,
        },
    )

    stale = client.post("/api/personal-corrections/episodes", json=stale_request)
    assert stale.status_code == 409
    assert stale.headers["cache-control"] == "no-store"
    assert stale.json()["detail"]["code"] == "stale_personal_correction_result"

    invalid = approval_request(prompt_id)
    invalid["correction_contract_version"] = "private text\ninvalid"
    invalid["mapping"] = {
        "operation": "addition",
        "observed_text": "",
        "intended_text": "private intended text",
    }
    rejected = client.post("/api/personal-corrections/episodes", json=invalid)
    assert rejected.status_code == 422
    assert rejected.headers["cache-control"] == "no-store"
    assert "private" not in rejected.text.lower()
    assert row_counts(Path(initialized_settings.database_path)) == {
        table: 0 for table in APPROVAL_TABLES
    }


def test_approval_rejects_differing_existing_context_without_overwriting(
    initialized_settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    prompt_id = client.get("/api/config").json()["active_prompt_version_id"]
    original = approval_request(prompt_id)
    assert client.post("/api/personal-corrections/episodes", json=original).status_code == 201
    conflicting = approval_request(prompt_id)
    conflicting["applicability_context"] = "A different synthetic context."

    response = client.post("/api/personal-corrections/episodes", json=conflicting)

    assert response.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    assert "different synthetic context" not in response.text.lower()
    assert row_counts(Path(initialized_settings.database_path)) == {
        "personal_correction_profiles": 1,
        "personal_correction_entries": 1,
        "personal_correction_aliases": 1,
        "personal_correction_episodes": 1,
        "personal_correction_episode_mappings": 1,
        "personal_correction_events": 1,
    }


def test_database_rejects_invalid_approval_shapes_and_control_characters(
    initialized_settings,
) -> None:
    path = Path(initialized_settings.database_path)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO personal_correction_profiles VALUES "
            "('local', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO personal_correction_episodes "
            "(id, owner_id, approval_id, observed_sentence, intended_sentence, source_mode, "
            "prompt_version_id, correction_contract_version, created_at) VALUES "
            "('episode', 'local', ?, NULL, NULL, 'smart', 1, 'personal-correction-v1', "
            "CURRENT_TIMESTAMP)",
            (str(uuid4()),),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO personal_correction_episode_mappings "
                "(id, owner_id, episode_id, ordinal, operation, observed_text, intended_text, "
                "entry_id, alias_id) VALUES "
                "('invalid-shape', 'local', 'episode', 1, 'replacement', '', 'term', NULL, NULL)"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO personal_correction_episodes "
                "(id, owner_id, approval_id, observed_sentence, intended_sentence, source_mode, "
                "prompt_version_id, correction_contract_version, created_at) VALUES "
                "('controls', 'local', ?, 'bad' || char(10) || 'sentence', NULL, 'smart', 1, "
                "'personal-correction-v1', CURRENT_TIMESTAMP)",
                (str(uuid4()),),
            )
