import json
import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parent.parent


def run_admin(
    database_path: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "LOCAL_TEXT_DATABASE_PATH": str(database_path)}
    return subprocess.run(
        ["uv", "run", "python", "-m", "local_text.admin", *arguments],
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def run_dev(
    state_root: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(REPOSITORY_ROOT / "scripts/dev.py"),
            "--state-root",
            str(state_root),
            *arguments,
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_admin_initializes_and_requires_an_unchanged_import_preview(tmp_path: Path) -> None:
    database_path = tmp_path / "local-text.sqlite3"
    missing = run_admin(database_path, "schema")
    assert missing.returncode == 1
    assert json.loads(missing.stdout)["state"] == "missing"
    assert not database_path.exists()

    assert run_admin(database_path, "migrate").returncode == 0
    assert run_admin(database_path, "seed").returncode == 0

    source = tmp_path / "configuration"
    source.mkdir()
    prompt_path = source / "cleanup-prompt.txt"
    prompt_path.write_text("First synthetic instruction.\n")
    first_preview = json.loads(run_admin(database_path, "import-preview", str(source)).stdout)
    prompt_path.write_text("Second synthetic instruction.\n")

    stale = run_admin(
        database_path,
        "import-confirm",
        str(source),
        "--digest",
        first_preview["preview_digest"],
    )
    assert stale.returncode == 1
    assert "does not match" in stale.stderr

    current_preview = json.loads(run_admin(database_path, "import-preview", str(source)).stdout)
    confirmed = run_admin(
        database_path,
        "import-confirm",
        str(source),
        "--digest",
        current_preview["preview_digest"],
    )
    assert confirmed.returncode == 0
    assert json.loads(confirmed.stdout)["imported"] is True
    assert run_admin(
        database_path,
        "import-confirm",
        str(source),
        "--digest",
        current_preview["preview_digest"],
    ).returncode == 1


def test_named_development_state_is_explicit_read_only_then_initialized(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    created = run_dev(state_root, "create", "focused-work")
    assert created.returncode == 0

    manifest_path = state_root / "focused-work/state.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["repository_root"] == str(REPOSITORY_ROOT.resolve())
    assert manifest["state_directory"] == str((state_root / "focused-work").resolve())
    assert manifest["label"].startswith("local.local-text.development.")
    assert manifest["label"].endswith(".focused-work")
    assert manifest["port"] == 7523

    ambient_database = tmp_path / "ambient.sqlite3"
    environment = {
        **os.environ,
        "LOCAL_TEXT_DATABASE_PATH": str(ambient_database),
        "LOCAL_TEXT_STATE_DIRECTORY": str(tmp_path / "ambient-state"),
    }
    status = run_dev(state_root, "status", "--state", "focused-work", environment=environment)
    assert status.returncode == 1
    assert '"state": "missing"' in status.stdout
    assert not ambient_database.exists()
    assert not (state_root / "focused-work/local-text.sqlite3").exists()

    initialized = run_dev(state_root, "initialize", "--state", "focused-work")
    assert initialized.returncode == 0
    ready = run_dev(state_root, "status", "--state", "focused-work")
    assert ready.returncode == 0
    assert '"state": "current"' in ready.stdout

    rendered = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/render-launchd-plist.py",
            "--state-root",
            str(state_root),
            "--state",
            "focused-work",
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert manifest["label"] in rendered
    assert str(state_root.resolve()) in rendered
    assert "focused-work" in rendered
    assert str(manifest["port"]) in rendered
    assert "__" not in rendered


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("repository_root", "/tmp/another-checkout", "different checkout"),
        ("state_directory", "/tmp/outside-state-root", "outside its selected"),
        ("label", "local.local-text.development.other", "invalid service label"),
        ("port", 7524, "must use development port 7523"),
    ],
)
def test_state_manifest_rejects_changed_bindings(
    tmp_path: Path, field: str, value: str | int, message: str
) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    manifest_path = state_root / "selected/state.json"
    manifest = json.loads(manifest_path.read_text())
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest))

    rejected = run_dev(state_root, "status", "--state", "selected")
    assert rejected.returncode != 0
    assert message in rejected.stderr


def test_state_rejects_unknown_and_root_escaping_selection(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    unknown = run_dev(state_root, "status", "--state", "missing")
    assert unknown.returncode != 0
    assert "unknown state" in unknown.stderr

    state_root.mkdir()
    (state_root / "escaped").symlink_to(tmp_path)
    escaped = run_dev(state_root, "status", "--state", "escaped")
    assert escaped.returncode != 0
    assert "outside the development-state root" in escaped.stderr


def test_runtime_environment_rejects_state_overrides(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    manifest = json.loads((state_root / "selected/state.json").read_text())
    home = tmp_path / "home"
    environment_path = home / ".config/local-text/development/environment"
    environment_path.parent.mkdir(parents=True)
    environment_path.write_text("LOCAL_TEXT_DATABASE_PATH=/tmp/other.sqlite3\n")
    environment_path.chmod(0o600)
    environment = {**os.environ, "HOME": str(home)}
    rejected = subprocess.run(
        [
            str(REPOSITORY_ROOT / "scripts/run-development.py"),
            "--state-root",
            str(state_root),
            "--state",
            "selected",
            "--label",
            manifest["label"],
            "--port",
            str(manifest["port"]),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode != 0
    assert "invalid environment entry" in rejected.stderr


def test_shared_configuration_is_overridden_by_checkout_state_without_printing_secret(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    manifest = json.loads((state_root / "selected/state.json").read_text())
    checkout_id = manifest["label"].split(".")[-2]
    home = tmp_path / "home"
    config_root = home / ".config/local-text/development"
    shared = config_root / "environment"
    selected = config_root / f"states/{checkout_id}/selected/environment"
    shared.parent.mkdir(parents=True)
    selected.parent.mkdir(parents=True)
    secret = "synthetic-secret-not-for-output"
    shared.write_text(
        f"LOCAL_TEXT_GEMINI_API_KEY={secret}\nLOCAL_TEXT_GEMINI_MODEL=shared-model\n"
    )
    selected.write_text("LOCAL_TEXT_GEMINI_MODEL=selected-model\n")
    shared.chmod(0o600)
    selected.chmod(0o600)
    environment = {**os.environ, "HOME": str(home)}

    status = run_dev(
        state_root,
        "status",
        "--state",
        "selected",
        environment=environment,
    )
    assert status.returncode == 1
    assert f"Shared configuration: {shared} (present)" in status.stdout
    assert f"State configuration: {selected} (present)" in status.stdout
    assert "Gemini credential: configured" in status.stdout
    assert "Gemini model: selected-model" in status.stdout
    assert secret not in status.stdout
    assert secret not in status.stderr

    shared.chmod(0o644)
    insecure = run_dev(
        state_root,
        "status",
        "--state",
        "selected",
        environment=environment,
    )
    assert insecure.returncode != 0
    assert "must have mode 0600" in insecure.stderr


def test_development_runtime_requires_explicit_state_selection() -> None:
    for script_name in ("dev.py", "run-development.py", "render-launchd-plist.py"):
        result = subprocess.run(
            [str(REPOSITORY_ROOT / "scripts" / script_name)],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0

    startup = (REPOSITORY_ROOT / "scripts/run-development.sh").read_text()
    assert "LOCAL_TEXT_STATE_DIRECTORY" not in startup
    assert "local_text.admin" not in startup
    assert "alembic" not in startup
