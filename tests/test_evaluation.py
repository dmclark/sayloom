import hashlib
import json
import sqlite3
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from conftest import initialize_database
from fastapi.testclient import TestClient

from local_text.app import create_app
from local_text.cleanup import CleanupService, ProviderOutput
from local_text.config import Profile, Settings
from local_text.evaluation import (
    CLEANUP_SCHEMA_VERSION,
    CONSENT_VERSION,
    CONTRACT_VERSION,
    EXPORT_FIELDS,
    EXPORT_WARNING,
    PURPOSE,
    AttemptCapture,
    CaptureProofs,
    CaseCaptureRequest,
    CleanupCapture,
    ConsentCapture,
    EvaluationError,
    EvaluationStore,
    ExportSelection,
    ExportTokens,
    RetentionRequest,
)
from local_text.evaluation_admin import _evaluation_alembic_config
from local_text.evaluation_database import (
    EVALUATION_DATABASE_NAME,
    EvaluationDatabase,
)
from local_text.evaluation_models import EvaluationAnnotation


def migrate_evaluation(path: Path, revision: str = "head") -> EvaluationDatabase:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    database = EvaluationDatabase(path)
    command.upgrade(_evaluation_alembic_config(database.url), revision)
    path.chmod(0o600)
    return database


def cleanup_capture(completed_at: datetime) -> CleanupCapture:
    return CleanupCapture(
        completed_at=completed_at,
        provider="synthetic-provider",
        model="synthetic-model",
        attempts=[
            AttemptCapture(
                route_index=0,
                provider="synthetic-provider",
                model="synthetic-model",
                outcome="success",
                elapsed_ms=7,
                input_tokens=11,
                output_tokens=5,
            )
        ],
        prompt_version_id=1,
        prompt_content_sha256=hashlib.sha256(b"Synthetic prompt.").hexdigest(),
        prompt_text="Synthetic prompt.",
        cleanup_schema_version=CLEANUP_SCHEMA_VERSION,
    )


def capture_request(
    proofs: CaptureProofs,
    completed_at: datetime,
    *,
    source_text: str = "Synthetic source.",
    provider_output: str = "Synthetic source!",
    expected_cleanup: str = "Synthetic source!",
) -> CaseCaptureRequest:
    cleanup = cleanup_capture(completed_at)
    return CaseCaptureRequest(
        contract_version=CONTRACT_VERSION,
        capture_proof=proofs.issue(source_text, provider_output, cleanup),
        consent=ConsentCapture(
            version=CONSENT_VERSION,
            scope=PURPOSE,
            confirmed=True,
        ),
        source_category="typed",
        source_text=source_text,
        provider_output=provider_output,
        expected_cleanup=expected_cleanup,
        cleanup=cleanup,
    )


def test_evaluation_migrations_work_fresh_and_from_predecessor(tmp_path: Path) -> None:
    fresh = migrate_evaluation(tmp_path / "fresh" / EVALUATION_DATABASE_NAME)
    assert fresh.schema_status().ready

    predecessor_path = tmp_path / "predecessor" / EVALUATION_DATABASE_NAME
    predecessor = migrate_evaluation(predecessor_path, "0001_evaluation_core")
    assert predecessor.schema_status().current_revision == "0001_evaluation_core"
    with sqlite3.connect(predecessor_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "evaluation_cases" in tables
    assert "benchmark_holds" not in tables

    command.upgrade(_evaluation_alembic_config(predecessor.url), "head")
    assert predecessor.schema_status().ready
    with sqlite3.connect(predecessor_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"evaluation_annotations", "benchmark_holds"} <= tables
    assert stat.S_IMODE(fresh.path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(fresh.path.stat().st_mode) == 0o600
    with fresh.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA secure_delete").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA temp_store").scalar_one() == 2
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "delete"
        assert connection.exec_driver_sql("PRAGMA journal_size_limit").scalar_one() == 0


def test_ordinary_startup_does_not_create_evaluation_directory_or_database(
    tmp_path: Path,
) -> None:
    app_database_path = tmp_path / "application-state" / "local-text.sqlite3"
    app_database_path.parent.mkdir()
    initialize_database(app_database_path)
    evaluation_directory = tmp_path / "external-evaluation"

    application = create_app(
        Settings(
            Profile.DEVELOPMENT,
            database_path=app_database_path,
            evaluation_data_directory=evaluation_directory,
        )
    )

    assert application is not None
    assert not evaluation_directory.exists()


def test_capture_proof_cancellation_expiry_and_mismatch_write_nothing(tmp_path: Path) -> None:
    database = migrate_evaluation(tmp_path / "evaluation" / EVALUATION_DATABASE_NAME)
    clock = [datetime(2026, 1, 1, 12, tzinfo=UTC)]
    store = EvaluationStore(database, now=lambda: clock[0])
    proofs = CaptureProofs(secret=b"p" * 32, now=lambda: clock[0])

    capture_request(proofs, clock[0])
    assert store.list_metadata() == []

    altered = capture_request(proofs, clock[0])
    altered.source_text = "Altered synthetic source."
    with pytest.raises(EvaluationError, match="capture_proof_mismatch"):
        proofs.verify_and_consume(altered)
    assert store.list_metadata() == []

    expired = capture_request(proofs, clock[0])
    clock[0] += timedelta(minutes=31)
    with pytest.raises(EvaluationError, match="stale_confirmation"):
        proofs.verify_and_consume(expired)
    assert store.list_metadata() == []

    rolled_back = capture_request(proofs, clock[0])
    proofs.verify_and_consume(rolled_back)
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            "CREATE TRIGGER synthetic_attempt_failure BEFORE INSERT ON evaluation_attempts "
            "BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"
        )
    with pytest.raises(EvaluationError, match="evaluation_storage_error"):
        store.capture(rolled_back)
    assert store.list_metadata() == []


def test_capture_readback_retention_expiry_and_transactional_delete(tmp_path: Path) -> None:
    path = tmp_path / "evaluation" / EVALUATION_DATABASE_NAME
    database = migrate_evaluation(path)
    clock = [datetime(2026, 2, 1, 9, tzinfo=UTC)]
    store = EvaluationStore(database, now=lambda: clock[0])
    proofs = CaptureProofs(secret=b"q" * 32, now=lambda: clock[0])
    request = capture_request(proofs, clock[0])
    proofs.verify_and_consume(request)

    captured = store.capture(request)
    assert set(captured) == {"case_id", "revision", "captured_at", "expires_at", "actions"}
    assert datetime.fromisoformat(captured["expires_at"]) == clock[0] + timedelta(days=90)
    assert "Synthetic" not in json.dumps(captured)

    listing = store.list_metadata()
    assert len(listing) == 1
    assert not {
        "source_text",
        "provider_output",
        "expected_cleanup",
        "prompt_text",
    } & listing[0].keys()
    reviewed = store.review(captured["case_id"])
    assert reviewed["source_text"] == "Synthetic source."
    assert reviewed["provider_output"] == "Synthetic source!"
    assert reviewed["expected_cleanup"] == "Synthetic source!"

    shortened = store.change_retention(
        captured["case_id"],
        RetentionRequest(revision=1, expires_at=clock[0] + timedelta(days=30)),
    )
    held = store.change_retention(
        captured["case_id"],
        RetentionRequest(
            revision=shortened["revision"],
            benchmark_id="synthetic-benchmark",
            release_at=clock[0] + timedelta(days=50),
        ),
    )
    assert held["hold"]["benchmark_id"] == "synthetic-benchmark"
    clock[0] += timedelta(days=31)
    assert len(store.list_metadata()) == 1
    clock[0] += timedelta(days=20)
    assert store.list_metadata() == []

    clock[0] = datetime(2026, 5, 1, 9, tzinfo=UTC)
    second = capture_request(proofs, clock[0], source_text="Synthetic second source.")
    proofs.verify_and_consume(second)
    saved = store.capture(second)
    store.change_retention(
        saved["case_id"],
        RetentionRequest(
            revision=1,
            benchmark_id="delete-check",
            release_at=clock[0] + timedelta(days=1),
        ),
    )
    with database.session_factory.begin() as session:
        session.add(
            EvaluationAnnotation(
                case_id=saved["case_id"],
                protocol_tag="synthetic-tag",
                category="synthetic-category",
                source_start=0,
                source_end=9,
                acceptable_values_json='["Synthetic"]',
            )
        )
    assert store.delete(saved["case_id"], 2) == {"deleted_case_id": saved["case_id"]}
    assert store.delete(saved["case_id"], 2) == {"deleted_case_id": saved["case_id"]}
    with sqlite3.connect(path) as connection:
        for table in (
            "evaluation_cases",
            "evaluation_consents",
            "evaluation_attempts",
            "evaluation_annotations",
            "benchmark_holds",
        ):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_jsonl_export_is_deterministic_private_and_stale_aware(tmp_path: Path) -> None:
    database = migrate_evaluation(tmp_path / "evaluation" / EVALUATION_DATABASE_NAME)
    clock = [datetime(2026, 3, 1, 10, tzinfo=UTC)]
    store = EvaluationStore(database, now=lambda: clock[0])
    proofs = CaptureProofs(secret=b"r" * 32, now=lambda: clock[0])
    request = capture_request(
        proofs,
        clock[0],
        source_text="Synthetic café source.",
        provider_output="Synthetic café source!",
        expected_cleanup="Synthetic café source!",
    )
    proofs.verify_and_consume(request)
    saved = store.capture(request)
    selection = [ExportSelection(case_id=saved["case_id"], revision=1)]

    first = store.export_material(selection)
    second = store.export_material(selection)
    assert first.content == second.content
    assert b"caf\xc3\xa9" in first.content
    assert first.content.endswith(b"\n")
    record = json.loads(first.content)
    assert tuple(record) == EXPORT_FIELDS
    digest = record.pop("record_sha256")
    canonical = json.dumps(
        record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    assert digest == hashlib.sha256(canonical).hexdigest()
    assert EXPORT_WARNING == (
        "This JSONL export contains sensitive source text, provider output, expected cleanup, "
        "and prompt text. Save it only to a private local destination. Export does not share or "
        "upload it."
    )

    tokens = ExportTokens(secret=b"s" * 32, now=lambda: clock[0])
    token = tokens.issue(selection)
    store.change_retention(
        saved["case_id"],
        RetentionRequest(revision=1, expires_at=clock[0] + timedelta(days=20)),
    )
    stale_selection = tokens.verify_and_consume(token)
    with pytest.raises(EvaluationError, match="stale_export_preview"):
        store.export_material(stale_selection)


def test_api_issues_proof_and_evaluation_operations_never_call_provider(tmp_path: Path) -> None:
    application_database_path = tmp_path / "application-state" / "local-text.sqlite3"
    application_database_path.parent.mkdir()
    initialize_database(application_database_path)
    evaluation_directory = tmp_path / "external-evaluation"
    migrate_evaluation(evaluation_directory / EVALUATION_DATABASE_NAME)
    provider_calls = 0

    class Provider:
        provider_id = "synthetic-provider"
        model = "synthetic-model"

        async def clean(self, original_text: str, system_prompt: str) -> ProviderOutput:
            nonlocal provider_calls
            provider_calls += 1
            return ProviderOutput(
                text="Synthetic API source!",
                provider_id=self.provider_id,
                model_id=self.model,
                elapsed_ms=4,
            )

    settings = Settings(
        Profile.DEVELOPMENT,
        database_path=application_database_path,
        evaluation_data_directory=evaluation_directory,
    )
    service = CleanupService(provider=Provider(), model="synthetic-model", timeout_seconds=1)
    client = TestClient(create_app(settings, service))
    cleanup = client.post(
        "/api/cleanup", json={"original_text": "Synthetic API source.", "enabled": True}
    ).json()
    context = cleanup["evaluation"]
    assert context["capture_proof"]
    smart_cleanup = client.post(
        "/api/cleanup",
        json={
            "original_text": "Synthetic API source.",
            "enabled": True,
            "correction_mode": "smart",
        },
    ).json()
    assert "evaluation" not in smart_cleanup
    safe_attempts = []
    for attempt in cleanup["attempts"]:
        safe_attempt = dict(attempt)
        safe_attempts.append(safe_attempt)

    payload = {
        "contract_version": CONTRACT_VERSION,
        "capture_proof": context["capture_proof"],
        "consent": {"version": CONSENT_VERSION, "scope": PURPOSE, "confirmed": True},
        "source_category": "typed",
        "source_text": "Synthetic API source.",
        "provider_output": cleanup["prepared_text"],
        "expected_cleanup": cleanup["prepared_text"],
        "cleanup": {
            "completed_at": context["completed_at"],
            "provider": cleanup["provider"],
            "model": cleanup["model"],
            "attempts": safe_attempts,
            "prompt_version_id": context["prompt_version_id"],
            "prompt_content_sha256": context["prompt_content_sha256"],
            "prompt_text": context["prompt_text"],
            "cleanup_schema_version": context["cleanup_schema_version"],
        },
    }
    saved_response = client.post("/api/evaluation/cases", json=payload)
    assert saved_response.status_code == 201
    saved = saved_response.json()
    assert "Synthetic API" not in saved_response.text
    listing = client.get("/api/evaluation/cases")
    assert listing.status_code == 200
    assert "source_text" not in listing.text
    review = client.get(f"/api/evaluation/cases/{saved['case_id']}")
    assert review.json()["source_text"] == "Synthetic API source."

    preview = client.post(
        "/api/evaluation/exports/preview",
        json={"cases": [{"case_id": saved["case_id"], "revision": 1}]},
    )
    assert preview.status_code == 200
    assert preview.json()["warning"] == EXPORT_WARNING
    exported = client.post(
        "/api/evaluation/exports",
        json={"preview_token": preview.json()["preview_token"], "confirmed": True},
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/x-ndjson")

    invalid = client.post(
        "/api/evaluation/cases",
        json={**payload, "capture_proof": "private synthetic invalid proof", "extra": "private"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_evaluation_request"
    assert "private synthetic" not in invalid.text
    assert provider_calls == 2


def test_evaluation_ui_is_explicit_accessible_and_destination_first(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    page = client.get("/").text
    script = client.get("/static/app.js").text
    stylesheet = client.get("/static/app.css").text

    assert 'id="nav-evaluation"' in page
    assert 'id="save-evaluation-case"' in page
    assert 'id="evaluation-capture-dialog"' in page
    assert 'id="evaluation-review-dialog"' in page
    assert 'id="evaluation-export-dialog"' in page
    assert "Saving this case does not consent to model training or personalization." in page
    assert 'role="status" aria-live="polite"' in page
    assert 'aria-label="Cancel saving evaluation case"' in page
    assert "showModal()" in script
    cancel = script.split("function closeEvaluationCapture()", 1)[1].split(
        "function openEvaluationCapture()", 1
    )[0]
    assert "fetch(" not in cancel
    destination_index = script.index("window.showSaveFilePicker")
    confirmation_index = script.index('fetch("/api/evaluation/exports"')
    assert destination_index < confirmation_index
    assert "URL.createObjectURL" not in script
    assert "application/x-ndjson" in script
    assert "input:focus-visible" in stylesheet
