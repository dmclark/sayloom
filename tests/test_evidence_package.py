import hashlib
import json
import logging
import os
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from local_text.app import create_app
from local_text.evidence_package import (
    CONTRACT_VERSION,
    PACKAGE_VERSION,
    EvidencePackageError,
    approve_package,
    check_readiness,
    create_package,
    find_exact_repeats,
    verify_observation,
    withdraw_observation,
    write_exclusion,
    write_observation,
)

REPOSITORY_ROOT = Path(__file__).parent.parent


def approved_package(tmp_path: Path) -> Path:
    package = tmp_path / "external-package"
    creation = create_package(package)
    approve_package(package, creation.approval_digest)
    return package


def test_administrator_creates_approves_and_checks_a_content_free_package(tmp_path: Path) -> None:
    package = tmp_path / "external-package"

    creation = create_package(package)
    before_approval = check_readiness(package)
    approval = approve_package(package, creation.approval_digest)
    readiness = check_readiness(package)

    assert before_approval.ready is False
    assert before_approval.reason == "not_approved"
    assert approval.package_id == creation.package_id
    assert readiness.to_dict() == {
        "ready": True,
        "reason": None,
        "package_version": PACKAGE_VERSION,
        "contract_version": CONTRACT_VERSION,
        "external_location": True,
        "approved": True,
        "owned": True,
        "restrictive_permissions": True,
        "append_only_writes": True,
        "hash_and_reread": True,
    }
    assert str(package) not in json.dumps(readiness.to_dict())
    assert stat.S_IMODE(package.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
        for path in package.rglob("*")
    )


def test_package_rejects_wrong_approval_and_nonrestrictive_permissions(tmp_path: Path) -> None:
    package = tmp_path / "external-package"
    creation = create_package(package)

    with pytest.raises(EvidencePackageError, match="approval digest does not match"):
        approve_package(package, "0" * 64)

    approve_package(package, creation.approval_digest)
    package.chmod(0o750)
    readiness = check_readiness(package)
    assert readiness.ready is False
    assert readiness.reason == "permissions"
    assert readiness.restrictive_permissions is False


def test_readiness_rejects_an_approved_package_moved_inside_a_git_checkout(
    tmp_path: Path,
) -> None:
    package = approved_package(tmp_path)
    synthetic_checkout = tmp_path / "synthetic-checkout"
    synthetic_checkout.mkdir()
    (synthetic_checkout / ".git").mkdir()
    moved_package = package.rename(synthetic_checkout / "external-package")

    readiness = check_readiness(moved_package)

    assert readiness.ready is False
    assert readiness.reason == "location"
    assert readiness.external_location is False
    assert str(moved_package) not in json.dumps(readiness.to_dict())


def test_immutable_observation_is_reread_hash_verified_and_cannot_be_replaced(
    tmp_path: Path,
) -> None:
    package = approved_package(tmp_path)
    observation_id = uuid4()
    synthetic_record = {
        "original": "Synthetic imperfect sentence.",
        "intended": "Synthetic corrected sentence.",
        "disposition": "edit_intended",
    }

    receipt = write_observation(package, observation_id, synthetic_record)
    artifact = package / "observations" / f"{observation_id}.json"
    original_bytes = artifact.read_bytes()

    assert receipt.observation_id == observation_id
    assert receipt.sha256 == hashlib.sha256(original_bytes).hexdigest()
    assert verify_observation(package, receipt) is True
    with pytest.raises(EvidencePackageError, match="already exists"):
        write_observation(package, observation_id, {"original": "Replacement"})
    assert artifact.read_bytes() == original_bytes


def test_verification_fails_after_artifact_tampering(tmp_path: Path) -> None:
    package = approved_package(tmp_path)
    observation_id = uuid4()
    receipt = write_observation(
        package,
        observation_id,
        {"original": "Synthetic source", "intended": "Synthetic intent"},
    )
    artifact = package / "observations" / f"{observation_id}.json"
    artifact.write_text("{}")
    artifact.chmod(0o600)

    with pytest.raises(EvidencePackageError, match="verification failed"):
        verify_observation(package, receipt)


def test_exclusion_retains_only_content_free_audit_metadata(tmp_path: Path) -> None:
    package = approved_package(tmp_path)
    observation_id = uuid4()

    receipt = write_exclusion(
        package,
        observation_id,
        "cannot_reliably_reconstruct",
        excluded_at=datetime(2026, 9, 18, 12, 15, tzinfo=UTC),
    )
    artifact = package / "observations" / f"{observation_id}.json"
    retained = json.loads(artifact.read_text())

    assert receipt.observation_id == observation_id
    assert retained == {
        "artifact_type": "exclusion",
        "disposition": "cannot_reliably_reconstruct",
        "excluded_at": "2026-09-18T12:15:00Z",
        "observation_id": str(observation_id),
        "package_version": PACKAGE_VERSION,
    }
    assert not ({"record", "original", "intended", "context", "profile", "length"} & set(retained))
    assert verify_observation(package, receipt) is True


def test_exact_repeat_suggestions_use_only_nfc_and_newline_normalization(
    tmp_path: Path,
) -> None:
    package = approved_package(tmp_path)
    normalized_repeat = uuid4()
    different_case = uuid4()
    different_space = uuid4()
    write_observation(
        package,
        normalized_repeat,
        {"original": "Cafe\u0301\r\nline", "intended": "Résumé\rline"},
    )
    write_observation(
        package,
        different_case,
        {"original": "CAFÉ\nline", "intended": "Résumé\nline"},
    )
    write_observation(
        package,
        different_space,
        {"original": "Café\nline ", "intended": "Résumé\nline"},
    )

    suggestions = find_exact_repeats(package, "Café\nline", "Re\u0301sume\u0301\nline")

    assert suggestions == (normalized_repeat,)


def test_withdrawal_removes_private_content_and_leaves_only_a_content_free_tombstone(
    tmp_path: Path,
) -> None:
    package = approved_package(tmp_path)
    observation_id = uuid4()
    private_values = ("synthetic private source", "synthetic private intention")
    write_observation(
        package,
        observation_id,
        {"original": private_values[0], "intended": private_values[1]},
    )

    withdrawn_at = datetime(2026, 9, 18, 12, 30, tzinfo=UTC)
    tombstone = withdraw_observation(package, observation_id, withdrawn_at=withdrawn_at)
    tombstone_path = package / "tombstones" / f"{observation_id}.json"
    retained = json.loads(tombstone_path.read_text())

    assert tombstone.observation_id == observation_id
    assert not (package / "observations" / f"{observation_id}.json").exists()
    assert retained == {
        "artifact_type": "withdrawal_tombstone",
        "observation_id": str(observation_id),
        "package_version": PACKAGE_VERSION,
        "withdrawn_at": "2026-09-18T12:30:00Z",
    }
    serialized = tombstone_path.read_text()
    assert all(value not in serialized for value in private_values)
    assert not ({"hash", "sha256", "length", "group", "repeat"} & set(retained))
    assert withdraw_observation(package, observation_id).observation_id == observation_id


def test_withdrawal_writes_tombstone_before_removing_content_and_can_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = approved_package(tmp_path)
    observation_id = uuid4()
    observation = package / "observations" / f"{observation_id}.json"
    tombstone = package / "tombstones" / f"{observation_id}.json"
    write_observation(
        package,
        observation_id,
        {"original": "Synthetic source", "intended": "Synthetic intent"},
    )
    original_unlink = Path.unlink

    def fail_content_removal(path: Path, *args, **kwargs) -> None:
        if path == observation:
            raise OSError("synthetic removal failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_content_removal)
    with pytest.raises(EvidencePackageError, match="private content removal failed"):
        withdraw_observation(package, observation_id)
    assert observation.exists()
    assert tombstone.exists()

    monkeypatch.setattr(Path, "unlink", original_unlink)
    assert withdraw_observation(package, observation_id).observation_id == observation_id
    assert not observation.exists()


def test_evidence_never_writes_to_application_state_logs_or_git(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    application_state = tmp_path / "application-state"
    application_state.mkdir()
    package = approved_package(tmp_path)
    synthetic_private_text = "synthetic private phrase that must stay external"

    with caplog.at_level(logging.DEBUG):
        write_observation(
            package,
            uuid4(),
            {"original": synthetic_private_text, "intended": "synthetic intended phrase"},
        )

    assert list(application_state.iterdir()) == []
    assert synthetic_private_text not in caplog.text
    with pytest.raises(EvidencePackageError, match="outside Git"):
        create_package(REPOSITORY_ROOT / "forbidden-evidence-package")
    assert not (REPOSITORY_ROOT / "forbidden-evidence-package").exists()


def test_browser_has_no_package_administration_routes(initialized_settings) -> None:
    with TestClient(create_app(settings=initialized_settings)) as client:
        operations = {
            f"{method.upper()} {path}"
            for path, methods in client.app.openapi()["paths"].items()
            for method in methods
        }

    forbidden = ("package", "migrate", "repair", "approve")
    assert not [
        operation for operation in operations if any(word in operation for word in forbidden)
    ]


def test_development_administration_uses_state_configuration_without_application_database(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "states"
    created_state = subprocess.run(
        [
            str(REPOSITORY_ROOT / "scripts/dev.py"),
            "--state-root",
            str(state_root),
            "create",
            "selected",
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert created_state.returncode == 0
    evaluation_directory = tmp_path / "evaluation-data"
    evaluation_directory.mkdir(mode=0o700)
    environment_file = state_root / "selected/environment"
    environment_file.write_text(
        f"LOCAL_TEXT_EVALUATION_DATA_DIRECTORY={evaluation_directory}\n"
    )
    environment_file.chmod(0o600)
    package = evaluation_directory / "intended-meaning-evidence"
    database = tmp_path / "application-state.sqlite3"
    environment = {**os.environ, "LOCAL_TEXT_DATABASE_PATH": str(database)}
    command = [
        str(REPOSITORY_ROOT / "scripts/dev.py"),
        "--state-root",
        str(state_root),
        "evidence-package",
        "--state",
        "selected",
    ]

    created = subprocess.run(
        [*command, "create"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    creation = json.loads(created.stdout)
    approved = subprocess.run(
        [*command, "approve", creation["approval_digest"]],
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    ready = subprocess.run(
        [*command, "ready"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert created.returncode == approved.returncode == ready.returncode == 0
    assert json.loads(approved.stdout)["approved"] is True
    assert json.loads(ready.stdout)["ready"] is True
    assert str(package) not in created.stdout + approved.stdout + ready.stdout
    assert not database.exists()
    assert not (state_root / "selected/local-text.sqlite3").exists()
