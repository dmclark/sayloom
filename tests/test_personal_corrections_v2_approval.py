"""Synthetic-only contracts for v2 approval and immutable reconciliation (#205/206)."""

import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from test_personal_correction_approval import APPROVAL_TABLES, row_counts

from local_text.admin import _alembic_config
from local_text.app import create_app
from local_text.config import Profile, Settings
from local_text.database import ApplicationDatabase
from local_text.personal_corrections import (
    PersonalCorrectionConflictError,
    PersonalCorrectionError,
    PersonalCorrectionRevisionConflictError,
    PersonalCorrectionStore,
    ReviewedApproval,
)


def replacement(before="umber", intended="amber", *, source_start=7):
    return {
        "operation": "replacement",
        "reusable_before_text": before,
        "reusable_intended_text": intended,
        "before_change_span": {"start": 0, "end": len(before)},
        "after_change_span": {"start": 0, "end": len(intended)},
        "source_start": source_start,
        "source_end": None if source_start is None else source_start + len(before),
    }


def approval(instance_id, **changes):
    return {
        "approval_id": str(uuid4()),
        "review_id": str(uuid4()),
        "correction_contract_version": "personal-correction-v2",
        "source_kind": "original_selection",
        "source_mode": "user_confirmed",
        "prompt_version_id": None,
        "application_instance_id": instance_id,
        "expected_authorization_generation": 0,
        "passage_id": str(uuid4()),
        "draft_revision": 3,
        "selection_start": 7,
        "selection_end": 12,
        "observed_sentence": "An umber parcel.",
        "intended_sentence": "An amber parcel.",
        "applicability_context": "Parcel color",
        "mappings": [replacement()],
        **changes,
    }


def save(store, payload):
    return store.approve_reviewed_replacements(ReviewedApproval.model_validate(payload))


def client_and_payload(settings):
    client = TestClient(create_app(settings))
    state = client.get("/api/personal-corrections").json()
    return client, approval(state["application_instance_id"])


def test_exact_immutable_approval_and_truthful_source_bindings(initialized_settings):
    client, payload = client_and_payload(initialized_settings)
    payload["observed_sentence"] = "  An umber parcel.  "
    response = client.post("/api/personal-corrections/episodes", json=payload)
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    saved = response.json()
    assert saved["approval"]["observed_sentence"] == payload["observed_sentence"]
    assert saved["approval"]["mappings"][0].items() >= payload["mappings"][0].items()
    assert saved["profile"] == {"enabled": True, "authorization_generation": 0}
    path = Path(initialized_settings.database_path)
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT review_id, source_kind, passage_id, draft_revision, selection_start, "
            "selection_end, prepared_id, prompt_version_id, authorization_generation, "
            "application_instance_id, applicability_context FROM personal_correction_episodes"
        ).fetchone() == (
            payload["review_id"],
            "original_selection",
            payload["passage_id"],
            3,
            7,
            12,
            None,
            None,
            0,
            payload["application_instance_id"],
            "Parcel color",
        )
        assert db.execute(
            "SELECT event_type, use_id, episode_id FROM personal_correction_events"
        ).fetchall() == [("alias_observed", payload["approval_id"], saved["approval"]["id"])]
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("UPDATE personal_correction_episodes SET observed_sentence = 'changed'")
    retry = client.post("/api/personal-corrections/episodes", json=payload)
    assert retry.status_code == 201
    assert retry.headers["cache-control"] == "no-store"
    assert retry.json() == saved
    assert (
        client.post(
            "/api/personal-corrections/episodes", json={**payload, "applicability_context": None}
        ).status_code
        == 409
    )
    restarted = TestClient(create_app(initialized_settings))
    assert restarted.post("/api/personal-corrections/episodes", json=payload).json() == saved
    assert row_counts(path)["personal_correction_episodes"] == 1


def test_manual_prepared_save_needs_no_provider_or_active_prompt_lookup(
    initialized_settings,
    monkeypatch,
):
    client, payload = client_and_payload(initialized_settings)
    client.put("/api/preferences/preparation-default", json={"preparation_default": "off"})

    def forbidden(*args, **kwargs):
        raise AssertionError("manual approval must not look up a prompt")

    monkeypatch.setattr("local_text.app.PromptStore.active", forbidden)
    payload.update(
        source_kind="manual_prepared",
        selection_start=None,
        selection_end=None,
        prepared_id=str(uuid4()),
        prepared_generation=8,
        confirmation_id=str(uuid4()),
        mappings=[replacement(source_start=None)],
    )
    response = client.post("/api/personal-corrections/episodes", json=payload)
    assert response.status_code == 201, response.text
    with sqlite3.connect(initialized_settings.database_path) as db:
        assert db.execute(
            "SELECT source_kind, selection_start, selection_end, prepared_id, "
            "prepared_generation, confirmation_id FROM personal_correction_episodes"
        ).fetchone() == (
            "manual_prepared",
            None,
            None,
            payload["prepared_id"],
            8,
            payload["confirmation_id"],
        )
        assert db.execute(
            "SELECT source_start, source_end FROM personal_correction_episode_mappings"
        ).fetchone() == (None, None)


def test_v2_save_with_unseeded_schema_has_no_prompt_dependency(tmp_path):
    database = ApplicationDatabase(tmp_path / "unseeded.sqlite3")
    command.upgrade(_alembic_config(database.url), "head")
    client, payload = client_and_payload(Settings(Profile.DEVELOPMENT, database_path=database.path))
    assert client.post("/api/personal-corrections/episodes", json=payload).status_code == 201
    with sqlite3.connect(database.path) as db:
        assert db.execute("SELECT COUNT(*) FROM prompt_versions").fetchone() == (0,)
    assert (
        client.put(
            "/api/personal-corrections/profile",
            json={
                "enabled": False,
                "expected_authorization_generation": 0,
            },
        ).status_code
        == 200
    )


def test_exact_internal_spans_and_source_order_with_astral_prefix(initialized_settings):
    client, payload = client_and_payload(initialized_settings)
    mapping = replacement("𐐀 umber!", "𐐀 amber!", source_start=7)
    mapping["before_change_span"] = {"start": 2, "end": 7}
    mapping["after_change_span"] = {"start": 2, "end": 7}
    second = replacement("ochre", "orange", source_start=20)
    payload.update(selection_end=25, mappings=[mapping, second], intended_sentence="  ")
    invalid = {**payload, "mappings": [second, mapping]}
    assert client.post("/api/personal-corrections/episodes", json=invalid).status_code == 422
    response = client.post("/api/personal-corrections/episodes", json=payload)
    assert response.status_code == 201, response.text
    saved = response.json()["approval"]
    assert saved["intended_sentence"] == "  "
    assert saved["mappings"][0]["before_change_span"] == {"start": 2, "end": 7}
    assert saved["mappings"][1]["source_start"] == 20


@pytest.mark.parametrize(
    "before,intended,operation",
    [
        ("umber", "umber", "replacement"),
        ("umber", "UMBER", "replacement"),
        ("parcel", "amber parcel", "replacement"),
        ("amber parcel", "parcel", "replacement"),
        ("one red parcel", "two red boxes", "replacement"),
        ("umber", "amber", "addition"),
        ("umber", "amber", "removal"),
        ("", "amber", "replacement"),
    ],
)
def test_independent_operation_validation_rejects_disguised_changes(
    initialized_settings,
    before,
    intended,
    operation,
):
    client, payload = client_and_payload(initialized_settings)
    payload["mappings"] = [{**replacement(before, intended), "operation": operation}]
    assert client.post("/api/personal-corrections/episodes", json=payload).status_code == 422
    assert not any(row_counts(Path(initialized_settings.database_path)).values())


@pytest.mark.parametrize(
    "mutation",
    [
        {"before_change_span": {"start": 2, "end": 5}},
        {"after_change_span": {"start": 0, "end": 6}},
        {
            "reusable_before_text": "umber!",
            "source_end": 13,
            "before_change_span": {"start": 0, "end": 5},
        },
        {"source_end": 13},
        {"source_start": None},
    ],
)
def test_bad_spans_and_inexact_reconstruction_write_nothing(initialized_settings, mutation):
    client, payload = client_and_payload(initialized_settings)
    payload["mappings"][0].update(mutation)
    assert client.post("/api/personal-corrections/episodes", json=payload).status_code == 422
    assert not any(row_counts(Path(initialized_settings.database_path)).values())


@pytest.mark.parametrize(
    "changes",
    [
        {"selection_end": 7},
        {"selection_start": 20, "selection_end": 22},
        {"prepared_id": str(uuid4())},
        {"review_id": "private invalid identifier"},
        {"draft_revision": -1},
        {"prompt_version_id": 1},
        {"source_mode": "smart"},
        {"before_text": "unapproved full snapshot"},
        {"owner_id": "foreign"},
        {"expected_authorization_generation": True},
    ],
)
def test_invalid_bindings_have_private_safe_http_errors(initialized_settings, changes):
    client, payload = client_and_payload(initialized_settings)
    payload.update(changes)
    response = client.post("/api/personal-corrections/episodes", json=payload)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert "umber" not in response.text
    assert "private invalid" not in response.text
    assert "unapproved full" not in response.text
    assert not any(row_counts(Path(initialized_settings.database_path)).values())


@pytest.mark.parametrize("field", ["draft_revision", "prepared_generation"])
@pytest.mark.parametrize(
    "value,status",
    [
        (9223372036854775807, 201),
        (9223372036854775808, 422),
    ],
)
def test_revision_metadata_sqlite_integer_boundary(initialized_settings, field, value, status):
    client, payload = client_and_payload(initialized_settings)
    payload.update(
        source_kind="manual_prepared",
        selection_start=None,
        selection_end=None,
        prepared_id=str(uuid4()),
        prepared_generation=0,
        confirmation_id=str(uuid4()),
        mappings=[replacement(source_start=None)],
    )
    payload[field] = value
    response = client.post("/api/personal-corrections/episodes", json=payload)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    path = Path(initialized_settings.database_path)
    if status == 201:
        assert response.json()["approval"][field] == value
        with sqlite3.connect(path) as db:
            assert db.execute(f"SELECT {field} FROM personal_correction_episodes").fetchone() == (
                value,
            )
    else:
        assert "umber" not in response.text
        assert not any(row_counts(path).values())


@pytest.mark.parametrize("field", ["draft_revision", "prepared_generation"])
def test_store_rejects_unchecked_revision_overflow(initialized_settings, field):
    store = PersonalCorrectionStore(ApplicationDatabase(Path(initialized_settings.database_path)))
    payload = approval(
        store.application_instance_id,
        source_kind="manual_prepared",
        selection_start=None,
        selection_end=None,
        prepared_id=str(uuid4()),
        prepared_generation=0,
        confirmation_id=str(uuid4()),
        mappings=[replacement(source_start=None)],
    )
    valid = ReviewedApproval.model_validate(payload)
    unchecked = valid.model_copy(update={field: 9223372036854775808})
    with pytest.raises(PersonalCorrectionError, match="invalid reviewed approval"):
        store.approve_reviewed_replacements(unchecked)
    assert not any(row_counts(store.database.path).values())


@pytest.mark.parametrize(
    "field,value",
    [
        ("applicability_context", "x" * 501),
        ("observed_sentence", "x" * 501),
        ("intended_sentence", "x" * 501),
        ("applicability_context", " " * 501),
        ("observed_sentence", "\t"),
        ("applicability_context", "\x00"),
        ("intended_sentence", "bad\x85text"),
        ("intended_sentence", "bad\ud800text"),
    ],
)
def test_private_text_bounds_cannot_be_bypassed_by_blank_fields(initialized_settings, field, value):
    client, payload = client_and_payload(initialized_settings)
    payload[field] = value
    response = client.post(
        "/api/personal-corrections/episodes",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "bad" not in response.text
    assert not any(row_counts(Path(initialized_settings.database_path)).values())


def test_codepoint_bounds_batch_limits_order_and_duplicate_selection(initialized_settings):
    client, payload = client_and_payload(initialized_settings)
    # Astral letters count once, not as UTF-16 pairs. Asymmetric before/after lengths.
    payload.update(
        source_kind="manual_prepared",
        selection_start=None,
        selection_end=None,
        prepared_id=str(uuid4()),
        prepared_generation=0,
        confirmation_id=str(uuid4()),
        applicability_context="r" * 500,
        observed_sentence="𐐀" * 500,
        intended_sentence="s" * 500,
    )
    mappings = [replacement("𐐀" * 200, "b" * 199, source_start=None)] + [
        replacement(f"before{i}", f"after{i}", source_start=None) for i in range(19)
    ]
    for selected in (
        [],
        mappings + [replacement("extra", "other", source_start=None)],
        [mappings[1], mappings[1]],
        [replacement("a" * 201, "b", source_start=None)],
    ):
        payload["mappings"] = selected
        assert client.post("/api/personal-corrections/episodes", json=payload).status_code == 422
    payload["mappings"] = mappings
    response = client.post("/api/personal-corrections/episodes", json=payload)
    assert response.status_code == 201, response.text
    assert [m["ordinal"] for m in response.json()["approval"]["mappings"]] == list(range(1, 21))
    with sqlite3.connect(initialized_settings.database_path) as db:
        assert db.execute(
            "SELECT observed_text, intended_text FROM personal_correction_episode_mappings "
            "ORDER BY ordinal"
        ).fetchall() == [(m["reusable_before_text"], m["reusable_intended_text"]) for m in mappings]


def test_independent_identity_exact_restrictions_and_preserved_canonical_state(
    initialized_settings,
):
    store = PersonalCorrectionStore(ApplicationDatabase(Path(initialized_settings.database_path)))
    payload = approval(store.application_instance_id)
    first = save(store, payload)
    entry = first["corrections"][0]
    # Synthetic pre-existing disabled mapping: #205 adds no per-entry management surface.
    with sqlite3.connect(initialized_settings.database_path) as db:
        db.execute("UPDATE personal_correction_entries SET enabled=0 WHERE id=?", (entry["id"],))
    store.set_profile_enabled(False, expected_authorization_generation=0)
    equivalent = approval(store.application_instance_id, expected_authorization_generation=1)
    equivalent["mappings"] = [replacement("ＵＭＢＥＲ", "ＡＭＢＥＲ")]
    second = save(store, equivalent)
    assert second["corrections"][0] == {**entry, "enabled": False}
    assert second["profile"] == {"enabled": False, "authorization_generation": 1}
    assert second["approval"]["mappings"][0]["reusable_before_text"] == "ＵＭＢＥＲ"
    for restriction in (None, "", "  ", "parcel color", " Parcel color "):
        save(
            store,
            approval(
                store.application_instance_id,
                expected_authorization_generation=1,
                applicability_context=restriction,
            ),
        )
    save(
        store,
        approval(
            store.application_instance_id,
            expected_authorization_generation=1,
            mappings=[replacement("ochre", "amber")],
        ),
    )
    assert len(store.read().entries) == 5  # Three blank restrictions share one mapping.
    assert store.read().authorization_generation == 1


@pytest.mark.parametrize("equivalent,same_uuid", [(False, False), (True, False), (True, True)])
def test_serialized_concurrent_first_saves(initialized_settings, equivalent, same_uuid):
    client, first = client_and_payload(initialized_settings)
    second = copy.deepcopy(first) if same_uuid else approval(first["application_instance_id"])
    if not equivalent:
        second["mappings"] = [replacement("ochre", "amber")]
    barrier = Barrier(2)

    def post(payload):
        barrier.wait(timeout=10)
        return client.post("/api/personal-corrections/episodes", json=payload).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(post, (first, second)))
    assert outcomes == [201, 201]
    counts = row_counts(Path(initialized_settings.database_path))
    assert counts["personal_correction_profiles"] == 1
    assert counts["personal_correction_entries"] == (1 if equivalent else 2)
    for table in APPROVAL_TABLES[3:]:
        assert counts[table] == (1 if same_uuid else 2)


def test_profile_preconditions_and_management_race(initialized_settings):
    client, payload = client_and_payload(initialized_settings)
    route = "/api/personal-corrections/profile"
    toggle = {"enabled": False, "expected_authorization_generation": 0}
    assert client.put(route, json={"enabled": True}).status_code == 422
    assert client.put(route, json=toggle).status_code == 409
    assert client.post("/api/personal-corrections/episodes", json=payload).status_code == 201
    barrier = Barrier(2)

    def change(_):
        barrier.wait(timeout=10)
        return client.put(route, json=toggle).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(change, range(2))) == [200, 409]
    stale = approval(payload["application_instance_id"])
    assert client.post("/api/personal-corrections/episodes", json=stale).status_code == 409
    stale["expected_authorization_generation"] = 1
    response = client.post("/api/personal-corrections/episodes", json=stale)
    assert response.status_code == 201
    assert response.json()["profile"] == {"enabled": False, "authorization_generation": 1}
    stale["approval_id"] = str(uuid4())
    stale["application_instance_id"] = str(uuid4())
    assert client.post("/api/personal-corrections/episodes", json=stale).status_code == 409


@pytest.mark.parametrize("failure_table", APPROVAL_TABLES[1:])
def test_injected_store_failure_rolls_back_whole_batch(initialized_settings, failure_table):
    database = ApplicationDatabase(Path(initialized_settings.database_path))
    store = PersonalCorrectionStore(database)
    payload = approval(
        store.application_instance_id,
        selection_end=25,
        mappings=[replacement(), replacement("ochre", "orange", source_start=20)],
    )

    def fail(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lower().startswith(f"insert into {failure_table} "):
            raise OperationalError("synthetic failure", {}, None)

    event.listen(database.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(OperationalError):
            save(store, payload)
    finally:
        event.remove(database.engine, "before_cursor_execute", fail)
    assert not any(row_counts(database.path).values())
    assert save(store, payload)["profile"]["enabled"] is True


def test_store_revalidates_unchecked_models_and_profile_generation(initialized_settings):
    store = PersonalCorrectionStore(ApplicationDatabase(Path(initialized_settings.database_path)))
    valid = ReviewedApproval.model_validate(approval(store.application_instance_id))
    invalid = valid.model_copy(update={"mappings": ()})
    with pytest.raises(PersonalCorrectionError):
        store.approve_reviewed_replacements(invalid)
    saved = save(store, valid.model_dump())
    assert store.approve_reviewed_replacements(valid) == saved
    store.set_profile_enabled(False, expected_authorization_generation=0)
    with pytest.raises(PersonalCorrectionRevisionConflictError):
        store.set_profile_enabled(True, expected_authorization_generation=0)
    with pytest.raises(PersonalCorrectionRevisionConflictError):
        save(store, approval(store.application_instance_id))


def test_approval_racing_profile_disablement_never_resets_state(initialized_settings):
    store = PersonalCorrectionStore(ApplicationDatabase(Path(initialized_settings.database_path)))
    save(store, approval(store.application_instance_id))
    barrier = Barrier(2)

    def run(action):
        barrier.wait(timeout=10)
        try:
            if action == "toggle":
                store.set_profile_enabled(False, expected_authorization_generation=0)
            else:
                save(store, approval(store.application_instance_id))
        except PersonalCorrectionRevisionConflictError:
            return "conflict"
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        saved, toggled = pool.map(run, ("approval", "toggle"))
    assert toggled == "saved"
    assert saved in {"saved", "conflict"}
    assert store.read().enabled is False
    assert store.read().authorization_generation == 1
    counts = row_counts(store.database.path)
    assert counts["personal_correction_episodes"] == (2 if saved == "saved" else 1)


def test_legacy_management_changes_invalidate_review_and_cannot_edit_v2(initialized_settings):
    client, payload = client_and_payload(initialized_settings)
    saved = client.post("/api/personal-corrections/episodes", json=payload).json()
    entry_id = saved["corrections"][0]["id"]
    edit = {
        "expected_revision": 1,
        "intended_term": "altered",
        "aliases": ["changed"],
        "applicability_context": None,
        "enabled": False,
    }
    assert client.put(f"/api/personal-corrections/entries/{entry_id}", json=edit).status_code == 409
    legacy = client.post(
        "/api/personal-corrections/entries",
        json={
            "intended_term": "Other term",
            "aliases": ["other alias"],
            "applicability_context": None,
        },
    )
    assert legacy.status_code == 201
    stale = approval(payload["application_instance_id"])
    assert client.post("/api/personal-corrections/episodes", json=stale).status_code == 409
    state = client.get("/api/personal-corrections").json()
    assert state["authorization_generation"] == 1
    assert (
        client.put(
            f"/api/personal-corrections/entries/{legacy.json()['id']}",
            json=edit,
        ).status_code
        == 200
    )
    stale["expected_authorization_generation"] = 1
    assert client.post("/api/personal-corrections/episodes", json=stale).status_code == 409
    assert client.get("/api/personal-corrections").json()["authorization_generation"] == 2
    assert client.get("/api/personal-corrections").json()["entries"][0] == saved["corrections"][0]


def test_http_transaction_failure_is_private_safe_and_rolls_back(initialized_settings):
    from sqlalchemy.engine import Engine

    client, payload = client_and_payload(initialized_settings)

    def fail(connection, _cursor, statement, _parameters, _context, _many):
        if connection.engine.url.database == str(
            initialized_settings.database_path
        ) and statement.lower().startswith("insert into personal_correction_events "):
            raise OperationalError("synthetic private failure", {}, None)

    event.listen(Engine, "before_cursor_execute", fail)
    try:
        response = client.post("/api/personal-corrections/episodes", json=payload)
    finally:
        event.remove(Engine, "before_cursor_execute", fail)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert "umber" not in response.text
    assert "synthetic private" not in response.text
    assert not any(row_counts(Path(initialized_settings.database_path)).values())
    assert client.post("/api/personal-corrections/episodes", json=payload).status_code == 201


@pytest.mark.parametrize("source_kind", ["original_selection", "manual_prepared"])
def test_lost_response_lookup_and_restart_keep_history_separate_from_current_state(
    initialized_settings, source_kind, monkeypatch
):
    client, payload = client_and_payload(initialized_settings)
    if source_kind == "manual_prepared":
        payload.update(
            source_kind=source_kind,
            selection_start=None,
            selection_end=None,
            prepared_id=str(uuid4()),
            prepared_generation=8,
            confirmation_id=str(uuid4()),
            mappings=[replacement(source_start=None)],
        )

    def forbidden(*args, **kwargs):
        raise AssertionError("reconciliation must not need a provider or prompt")

    monkeypatch.setattr("local_text.app.PromptStore.active", forbidden)
    # The caller discards the save response, as after a transport loss.
    assert client.post("/api/personal-corrections/episodes", json=payload).status_code == 201
    route = f"/api/personal-corrections/episodes/{payload['approval_id']}"
    original = client.get(route)
    assert original.status_code == 200
    assert original.headers["cache-control"] == "no-store"
    historical = original.json()["approval"]
    entry_id = historical["mappings"][0]["entry_id"]
    # Synthetic management state, not a new management API or activation.
    with sqlite3.connect(initialized_settings.database_path) as db:
        db.execute(
            "UPDATE personal_correction_entries SET enabled=0, revision=2 WHERE id=?",
            (entry_id,),
        )
    assert (
        client.put(
            "/api/personal-corrections/profile",
            json={"enabled": False, "expected_authorization_generation": 0},
        ).status_code
        == 200
    )
    monkeypatch.undo()  # Existing startup may inspect prompt readiness; these routes must not.
    restarted = TestClient(create_app(initialized_settings))
    monkeypatch.setattr("local_text.app.PromptStore.active", forbidden)
    assert (
        restarted.get("/api/personal-corrections").json()["application_instance_id"]
        != (payload["application_instance_id"])
    )
    before = row_counts(Path(initialized_settings.database_path))
    retry = restarted.post("/api/personal-corrections/episodes", json=payload)
    assert retry.status_code == 201, retry.text
    assert retry.json()["approval"] == historical
    assert retry.json()["profile"] == {"enabled": False, "authorization_generation": 1}
    assert retry.json()["corrections"][0]["enabled"] is False
    assert retry.json()["corrections"][0]["revision"] == 2
    assert restarted.get(route).json() == retry.json()
    # Reusing the original instance for a NEW approval remains stale after restart.
    new = {**payload, "approval_id": str(uuid4()), "expected_authorization_generation": 1}
    assert restarted.post("/api/personal-corrections/episodes", json=new).status_code == 409
    assert row_counts(Path(initialized_settings.database_path)) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"review_id": str(uuid4())},
        {"passage_id": str(uuid4())},
        {"draft_revision": 4},
        {"selection_start": 6},
        {"selection_end": 13},
        {"application_instance_id": str(uuid4())},
        {"expected_authorization_generation": 1},
        {"observed_sentence": "An Umber parcel."},
        {"intended_sentence": "An amber parcel. "},
        {"applicability_context": "parcel color"},
        {"mappings": [replacement("ＵＭＢＥＲ", "ＡＭＢＥＲ")]},
        {"mappings": [replacement("umber", "azure")]},
        {"mappings": [replacement(source_start=8)], "selection_end": 13},
        {
            "source_kind": "manual_prepared",
            "selection_start": None,
            "selection_end": None,
            "prepared_id": str(uuid4()),
            "prepared_generation": 8,
            "confirmation_id": str(uuid4()),
            "mappings": [replacement(source_start=None)],
        },
    ],
)
def test_changed_immutable_payload_conflicts_without_writes(initialized_settings, changes):
    client, payload = client_and_payload(initialized_settings)
    saved = client.post("/api/personal-corrections/episodes", json=payload).json()
    changed = {**payload, **changes}
    ReviewedApproval.model_validate(changed)  # Exercise conflict, not invalid input rejection.
    with sqlite3.connect(initialized_settings.database_path) as db:
        before = list(db.iterdump())
    response = client.post("/api/personal-corrections/episodes", json=changed)
    assert response.status_code == 409, response.text
    assert response.headers["cache-control"] == "no-store"
    assert "umber" not in response.text
    assert "Parcel color" not in response.text
    assert (
        client.get(f"/api/personal-corrections/episodes/{payload['approval_id']}").json() == saved
    )
    with sqlite3.connect(initialized_settings.database_path) as db:
        assert list(db.iterdump()) == before


def test_prepared_binding_order_and_exact_spans_are_immutable(initialized_settings):
    store = PersonalCorrectionStore(ApplicationDatabase(Path(initialized_settings.database_path)))
    first = replacement("𐐀 umber!", "𐐀 amber!", source_start=None)
    first["before_change_span"] = first["after_change_span"] = {"start": 2, "end": 7}
    payload = approval(
        store.application_instance_id,
        source_kind="manual_prepared",
        selection_start=None,
        selection_end=None,
        prepared_id=str(uuid4()),
        prepared_generation=8,
        confirmation_id=str(uuid4()),
        mappings=[first, replacement("ochre", "orange", source_start=None)],
    )
    saved = save(store, payload)
    for changes in (
        {"prepared_id": str(uuid4())},
        {"prepared_generation": 9},
        {"confirmation_id": str(uuid4())},
        {"mappings": list(reversed(payload["mappings"]))},
        {
            "mappings": [
                {
                    **first,
                    "before_change_span": {"start": 0, "end": 7},
                    "after_change_span": {"start": 0, "end": 7},
                },
                payload["mappings"][1],
            ]
        },
    ):
        with pytest.raises(PersonalCorrectionConflictError):
            save(store, {**payload, **changes})
    assert store.approval_detail(payload["approval_id"]) == saved
    assert save(store, payload) == saved


def test_absent_optional_values_have_one_canonical_receipt(initialized_settings):
    store = PersonalCorrectionStore(ApplicationDatabase(Path(initialized_settings.database_path)))
    payload = approval(
        store.application_instance_id,
        applicability_context="  ",
        observed_sentence="",
        intended_sentence=None,
    )
    saved = save(store, payload)
    assert (
        save(store, {**payload, "applicability_context": None, "observed_sentence": None}) == saved
    )
    with pytest.raises(PersonalCorrectionConflictError):
        save(store, {**payload, "intended_sentence": "  "})


def test_concurrent_changed_payload_has_one_winner_and_one_immutable_receipt(initialized_settings):
    client, payload = client_and_payload(initialized_settings)
    changed = {**payload, "applicability_context": "Different restriction"}
    barrier = Barrier(2)

    def post(request):
        barrier.wait(timeout=10)
        return client.post("/api/personal-corrections/episodes", json=request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(post, (payload, changed)))
    assert sorted(r.status_code for r in responses) == [201, 409]
    winner = next(r.json() for r in responses if r.status_code == 201)
    assert (
        client.get(f"/api/personal-corrections/episodes/{payload['approval_id']}").json() == winner
    )
    assert all(
        value == 1 for value in row_counts(Path(initialized_settings.database_path)).values()
    )


def test_approval_lookup_is_owner_scoped_and_absence_is_not_no_save(initialized_settings):
    client, payload = client_and_payload(initialized_settings)
    assert client.post("/api/personal-corrections/episodes", json=payload).status_code == 201
    # Adversarial fixture: bypass schema ownership/immutability, not application behavior.
    with sqlite3.connect(initialized_settings.database_path) as db:
        db.execute("PRAGMA ignore_check_constraints=ON")
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():
            db.execute(f'DROP TRIGGER "{name}"')
        for table in APPROVAL_TABLES:
            db.execute(f"UPDATE {table} SET owner_id='foreign'")
    for identifier in (payload["approval_id"], str(uuid4()), "private-invalid-id"):
        response = client.get(f"/api/personal-corrections/episodes/{identifier}")
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store"
        assert "does not prove that no save occurred" in response.text
        assert "umber" not in response.text
        assert identifier not in response.text
    assert all(
        value == 1 for value in row_counts(Path(initialized_settings.database_path)).values()
    )
    # A foreign UUID cannot resolve a local retry or prevent a new owned save.
    saved = client.post("/api/personal-corrections/episodes", json=payload)
    assert saved.status_code == 201
    assert (
        client.get(f"/api/personal-corrections/episodes/{payload['approval_id']}").json()
        == saved.json()
    )
    with sqlite3.connect(initialized_settings.database_path) as db:
        assert db.execute(
            "SELECT owner_id FROM personal_correction_episodes ORDER BY owner_id"
        ).fetchall() == [("foreign",), ("local",)]


def test_approval_read_failure_is_private_safe_and_keeps_outcome_unknown(
    initialized_settings, monkeypatch
):
    client, payload = client_and_payload(initialized_settings)

    def fail(*args, **kwargs):
        raise OperationalError("private database failure", {}, None)

    monkeypatch.setattr(PersonalCorrectionStore, "approval_detail", fail)
    response = client.get(f"/api/personal-corrections/episodes/{payload['approval_id']}")
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert "outcome is unknown" in response.text
    assert "private database" not in response.text
