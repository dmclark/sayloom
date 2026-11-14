"""Stable's public CLI against isolated repositories and synthetic state."""

import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts/stable.py"


def git(repository: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "commit.gpgsign=false", "-C", str(repository), *arguments], text=True
    ).strip()


def repository_pair(tmp_path: Path) -> tuple[Path, Path]:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    git(upstream, "init", "-b", "main")
    git(upstream, "config", "user.email", "synthetic@example.invalid")
    git(upstream, "config", "user.name", "Synthetic test")
    (upstream / "tracked").write_text("installed\n")
    git(upstream, "add", ".")
    git(upstream, "commit", "-m", "Installed revision")
    checkout = tmp_path / "checkout"
    subprocess.run(["git", "clone", str(upstream), str(checkout)], check=True, capture_output=True)
    git(checkout, "config", "user.email", "synthetic@example.invalid")
    git(checkout, "config", "user.name", "Synthetic test")
    return upstream, checkout


def stable(
    tmp_path: Path,
    checkout: Path,
    upstream: Path,
    *arguments: str,
    input: str = "",
    environment: dict | None = None,
):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(tmp_path / "stable"),
            "--checkout",
            str(checkout),
            "--upstream",
            str(upstream),
            *arguments,
        ],
        env={**os.environ, "HOME": str(tmp_path / "home"), **(environment or {})},
        input=input,
        text=True,
        capture_output=True,
        check=False,
    )


def test_status_fetches_main_without_changing_checkout_and_reports_offline(tmp_path: Path) -> None:
    upstream, checkout = repository_pair(tmp_path)
    installed = git(checkout, "rev-parse", "HEAD")
    (upstream / "tracked").write_text("candidate\n")
    git(upstream, "commit", "-am", "Preserve synthetic settings")
    candidate = git(upstream, "rev-parse", "HEAD")

    result = stable(tmp_path, checkout, upstream, "status")

    assert result.returncode == 0, result.stderr
    status = json.loads(result.stdout)
    assert status["updates"] == "behind"
    assert status["candidate"] == candidate
    assert status["installed_commit"] == installed
    assert "Preserve synthetic settings" in status["commits"]
    assert status["installed"] is False
    assert git(checkout, "rev-parse", "HEAD") == installed
    assert (checkout / "tracked").read_text() == "installed\n"
    assert not (tmp_path / "stable").exists()

    unavailable = stable(tmp_path, checkout, tmp_path / "missing-upstream", "status")
    assert unavailable.returncode == 0, unavailable.stderr
    assert json.loads(unavailable.stdout)["updates"] == "unknown"
    assert git(checkout, "remote", "get-url", "origin") == str(upstream)


def application_pair(tmp_path: Path) -> tuple[Path, Path]:
    upstream, checkout = repository_pair(tmp_path)
    for name in ("src", "migrations", "scripts", "raycast"):
        shutil.copytree(
            REPOSITORY / name,
            upstream / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    for name in ("pyproject.toml", "uv.lock", "alembic.ini", "README.md", ".gitignore"):
        shutil.copy2(REPOSITORY / name, upstream / name)
    (upstream / "tests").mkdir()
    (upstream / "tests/test_smoke.py").write_text("def test_candidate():\n    assert True\n")
    git(upstream, "add", ".")
    git(upstream, "commit", "-m", "Add application")
    git(checkout, "pull", "--ff-only")
    return upstream, checkout


def install(tmp_path: Path, checkout: Path, upstream: Path, *arguments: str):
    config = tmp_path / "environment.json"
    config.write_text("{}\n")
    config.chmod(0o600)
    return stable(
        tmp_path,
        checkout,
        upstream,
        "install",
        "--database",
        str(tmp_path / "data.sqlite3"),
        "--configuration",
        str(config),
        "--raycast-directory",
        str(tmp_path / "commands"),
        *arguments,
    )


def test_install_requires_explicit_initialization_and_never_starts_service(tmp_path: Path) -> None:
    upstream, checkout = application_pair(tmp_path)
    missing = install(tmp_path, checkout, upstream)
    assert missing.returncode != 0
    assert "--initialize" in missing.stderr
    assert not (tmp_path / "data.sqlite3").exists()

    unmanaged = tmp_path / "stable/stable.py"
    unmanaged.write_text("owner file\n")
    refused = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert refused.returncode != 0
    assert unmanaged.read_text() == "owner file\n"
    unmanaged.unlink()

    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    root = tmp_path / "stable"
    installed = json.loads((root / "installation.json").read_text())
    assert installed["commit"] == git(checkout, "rev-parse", "HEAD")
    assert Path(installed["python"]).is_file()
    assert (root / "stable.py").is_file()
    assert sorted(path.name for path in (tmp_path / "commands").iterdir()) == [
        "stable-open-sayloom.sh",
        "stable-sayloom-target-amp.sh",
        "stable-sayloom-target-iterm.sh",
        "stable-sayloom-target-supacode.sh",
        "stable-sayloom-target-vs-code.sh",
    ]
    assert not (root / "maintenance.json").exists()
    assert not (checkout / ".venv").exists()
    with sqlite3.connect(tmp_path / "data.sqlite3") as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0006_confirmed_correction_batches",
        )
        assert connection.execute("SELECT count(*) FROM active_prompt").fetchone() == (1,)

    # The installed controller remains usable even when checkout tooling disappears.
    (checkout / "scripts/stable.py").unlink()
    result = subprocess.run(
        [sys.executable, str(root / "stable.py"), "--root", str(root), "status"],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["schema"]["state"] == "current"


@pytest.mark.parametrize("change", ["ahead", "divergent"])
def test_status_distinguishes_local_history(tmp_path: Path, change: str) -> None:
    upstream, checkout = repository_pair(tmp_path)
    (checkout / "local").write_text("owner changes\n")
    git(checkout, "add", ".")
    git(checkout, "commit", "-m", "Local change")
    if change == "divergent":
        (upstream / "tracked").write_text("upstream changes\n")
        git(upstream, "commit", "-am", "Remote change")
    result = stable(tmp_path, checkout, upstream, "status")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["updates"] == change


def test_update_preview_and_decline_preserve_source_and_data(tmp_path: Path) -> None:
    upstream, checkout = application_pair(tmp_path)
    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    installed = git(checkout, "rev-parse", "HEAD")
    before = (tmp_path / "data.sqlite3").read_bytes()
    with (upstream / "src/local_text/database.py").open("a") as output:
        output.write("\n# Synthetic code-only change\n")
    git(upstream, "commit", "-am", "A code-only release")
    candidate = git(upstream, "rev-parse", "HEAD")

    preview = stable(tmp_path, checkout, upstream, "update", "--dry-run")
    assert preview.returncode == 0, preview.stderr
    plan = json.loads(preview.stdout)
    assert plan["candidate"] == candidate
    assert plan["migrations"] == []
    assert plan["dependency_preparation"] == "not run"
    declined = stable(tmp_path, checkout, upstream, "update", input="n\n")
    assert declined.returncode == 0, declined.stderr
    assert "A code-only release" in declined.stdout
    assert git(checkout, "rev-parse", "HEAD") == installed
    assert (tmp_path / "data.sqlite3").read_bytes() == before
    assert not (tmp_path / "stable/maintenance.json").exists()

    # An untracked file must survive even when Git would ordinarily ignore it.
    (checkout / "collision.sqlite3").write_text("owner data")
    (upstream / "collision.sqlite3").write_text("candidate file")
    git(upstream, "add", "-f", "collision.sqlite3")
    git(upstream, "commit", "-m", "Collision")
    rejected = stable(tmp_path, checkout, upstream, "update", "--dry-run")
    assert rejected.returncode != 0
    assert "untracked" in rejected.stderr
    assert (checkout / "collision.sqlite3").read_text() == "owner data"


def test_restart_and_confirmed_update_pin_the_previewed_commit(tmp_path, service_environment):
    upstream, checkout = application_pair(tmp_path)
    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    before = (tmp_path / "data.sqlite3").read_bytes()
    for operation in ("start", "start", "restart"):
        result = stable(tmp_path, checkout, upstream, operation, environment=service_environment)
        assert result.returncode == 0, result.stderr
    assert (tmp_path / "data.sqlite3").read_bytes() == before
    (upstream / "tracked").write_text("reviewed release\n")
    git(upstream, "commit", "-am", "Reviewed release")
    reviewed = git(upstream, "rev-parse", "HEAD")
    process = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path / "stable"), "update"],
        env={**os.environ, "HOME": str(tmp_path / "home"), **service_environment},
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        preview = ""
        while not preview.endswith("[y/N] "):
            character = process.stdout.read(1)
            assert character, process.stderr.read()
            preview += character
        assert reviewed in preview
        (upstream / "tracked").write_text("later unreviewed release\n")
        git(upstream, "commit", "-am", "Unreviewed later release")
        output, errors = process.communicate("y\n", timeout=300)
        assert process.returncode == 0, output + errors
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
    assert git(checkout, "rev-parse", "HEAD") == reviewed
    assert (checkout / "tracked").read_text() == "reviewed release\n"
    assert (tmp_path / "data.sqlite3").read_bytes() == before
    status = stable(tmp_path, checkout, upstream, "status", environment=service_environment)
    assert json.loads(status.stdout)["updates"] == "behind"
    assert json.loads(status.stdout)["health"]["ready"] is True


def test_code_only_activation_failure_recovers_previous_runtime(tmp_path, service_environment):
    if "SYNTHETIC_SERVICE" not in service_environment:
        pytest.skip("failure injection uses the synthetic launchctl boundary")
    upstream, checkout = application_pair(tmp_path)
    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    original = git(checkout, "rev-parse", "HEAD")
    before = (tmp_path / "data.sqlite3").read_bytes()
    (upstream / "tracked").write_text("new release\n")
    git(upstream, "commit", "-am", "Release that cannot start")
    Path(service_environment["SYNTHETIC_SERVICE"]).with_suffix(".fail").touch()
    result = stable(
        tmp_path, checkout, upstream, "update", "--yes", environment=service_environment
    )
    assert result.returncode != 0
    assert "Previous Stable recovered" in result.stdout
    assert git(checkout, "rev-parse", "HEAD") == original
    assert (tmp_path / "data.sqlite3").read_bytes() == before
    assert not (tmp_path / "stable/maintenance.json").exists()
    status = stable(tmp_path, checkout, upstream, "status", environment=service_environment)
    assert json.loads(status.stdout)["health"]["ready"] is True


def test_restart_never_initializes_missing_database(tmp_path: Path) -> None:
    upstream, checkout = application_pair(tmp_path)
    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    (tmp_path / "data.sqlite3").unlink()
    result = stable(tmp_path, checkout, upstream, "restart")
    assert result.returncode != 0
    assert not (tmp_path / "data.sqlite3").exists()
    assert not (checkout / ".venv").exists()
    status = stable(tmp_path, checkout, upstream, "status")
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["schema"]["state"] == "missing"


@pytest.fixture
def service_environment(tmp_path: Path):
    """Use real launchd only on an explicitly opted-in disposable Mac satellite."""
    if os.environ.get("LOCAL_TEXT_TEST_LAUNCHD") == "1":
        assert sys.platform == "darwin"
        yield {}
        manifest = tmp_path / "stable/installation.json"
        if manifest.exists():
            label = json.loads(manifest.read_text())["label"]
            subprocess.run(
                ["launchctl", "bootout", f"gui/{os.getuid()}/{label}"], capture_output=True
            )
        return
    directory = tmp_path / "bin"
    directory.mkdir()
    executable = directory / "launchctl"
    executable.write_text(
        f"#!{sys.executable}\n"
        + """
import json, os, plistlib, signal, subprocess, sys
from pathlib import Path
state = Path(os.environ['SYNTHETIC_SERVICE'])
command = sys.argv[1]
if command == 'print':
    if not state.exists():
        sys.exit(3)
    installed = json.loads(state.read_text())
    print('arguments = {')
    print(*installed['arguments'], sep=chr(10))
    print('}')
    print('pid = ' + str(installed['pid']))
elif command == 'bootstrap':
    failure = state.with_suffix('.fail')
    if failure.exists():
        failure.unlink()
        sys.exit(5)
    plist = plistlib.loads(Path(sys.argv[3]).read_bytes())
    with open(plist['StandardOutPath'], 'a') as output, \\
         open(plist['StandardErrorPath'], 'a') as errors:
        process = subprocess.Popen(plist['ProgramArguments'], stdout=output, stderr=errors)
    state.write_text(json.dumps({'pid': process.pid, 'arguments': plist['ProgramArguments']}))
elif command == 'bootout':
    if state.exists():
        installed = json.loads(state.read_text())
        try:
            os.kill(installed['pid'], signal.SIGTERM)
        except ProcessLookupError:
            pass
        state.unlink()
else:
    sys.exit(2)
"""
    )
    executable.chmod(0o700)
    state = tmp_path / "synthetic-service.json"
    yield {
        "PATH": str(directory) + os.pathsep + os.environ["PATH"],
        "SYNTHETIC_SERVICE": str(state),
    }
    if state.exists():
        try:
            os.kill(json.loads(state.read_text())["pid"], signal.SIGTERM)
        except ProcessLookupError:
            pass


def add_schema_release(upstream: Path, *, fail_live: bool = False) -> str:
    source = upstream / "src/local_text/database.py"
    source.write_text(
        source.read_text().replace(
            'SCHEMA_REVISION = "0006_confirmed_correction_batches"',
            'SCHEMA_REVISION = "0007_synthetic_release"',
        )
    )
    migration = upstream / "migrations/versions/0007_synthetic_release.py"
    migration.write_text(
        '''"""Add a synthetic nullable field without changing existing data."""
import sqlalchemy as sa
from alembic import op

revision = "0007_synthetic_release"
down_revision = "0006_confirmed_correction_batches"


def upgrade():
    op.add_column("targets", sa.Column("synthetic_note", sa.Text(), nullable=True))
'''
        + (
            '    if op.get_bind().engine.url.database.endswith("data.sqlite3"):\n'
            '        raise RuntimeError("Synthetic live migration failure")\n'
            if fail_live
            else ""
        )
        + """

def downgrade():
    raise RuntimeError("No automatic downgrade")
"""
    )
    git(upstream, "add", ".")
    git(upstream, "commit", "-m", "Synthetic data-preserving migration")
    return git(upstream, "rev-parse", "HEAD")


def test_update_migrates_data_and_explicit_recovery_restores_backup(
    tmp_path: Path,
    service_environment: dict,
) -> None:
    upstream, checkout = application_pair(tmp_path)
    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    original = git(checkout, "rev-parse", "HEAD")
    database = tmp_path / "data.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO app_settings VALUES ('synthetic_saved', '\"Café 73\"', CURRENT_TIMESTAMP)"
        )
        connection.execute("UPDATE targets SET enabled = 0 WHERE id = 'amp'")
        connection.execute(
            "INSERT INTO personal_correction_profiles VALUES "
            "('local', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO personal_correction_entries VALUES "
            "('entry-9', 'local', 'Synthetic intended term', 'synthetic intended term', "
            "'Synthetic context', 1, 3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    candidate = add_schema_release(upstream)
    result = stable(
        tmp_path, checkout, upstream, "update", "--yes", environment=service_environment
    )
    assert result.returncode == 0, result.stderr
    assert git(checkout, "rev-parse", "HEAD") == candidate
    root = tmp_path / "stable"
    assert not (root / "maintenance.json").exists()
    record = json.loads((root / "last-update.json").read_text())
    assert record["previous"]["commit"] == original
    assert Path(record["previous"]["python"]).is_file()
    assert Path(record["backup"]).stat().st_mode & 0o077 == 0
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0007_synthetic_release",
        )
        assert connection.execute(
            "SELECT value_json FROM app_settings WHERE key = 'synthetic_saved'"
        ).fetchone() == ('"Café 73"',)
        assert connection.execute(
            "SELECT intended_term, revision FROM personal_correction_entries WHERE id = 'entry-9'"
        ).fetchone() == (
            "Synthetic intended term",
            3,
        )
        assert connection.execute("SELECT count(*) FROM prompt_versions").fetchone() == (1,)
        connection.execute(
            "UPDATE app_settings SET value_json = '\"Later write\"' WHERE key = 'synthetic_saved'"
        )
    incompatible = stable(
        tmp_path,
        checkout,
        upstream,
        "recover",
        "--use",
        "previous",
        "--yes",
        environment=service_environment,
    )
    assert incompatible.returncode != 0
    restored = stable(
        tmp_path,
        checkout,
        upstream,
        "recover",
        "--use",
        "previous",
        "--restore-backup",
        "--yes",
        environment=service_environment,
    )
    assert restored.returncode == 0, restored.stderr
    assert git(checkout, "rev-parse", "HEAD") == original
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value_json FROM app_settings WHERE key = 'synthetic_saved'"
        ).fetchone() == ('"Café 73"',)
    recovery = json.loads((root / "last-update.json").read_text())
    with sqlite3.connect(recovery["before_restore"]) as connection:
        assert connection.execute(
            "SELECT value_json FROM app_settings WHERE key = 'synthetic_saved'"
        ).fetchone() == ('"Later write"',)


def test_failed_live_migration_stays_in_maintenance_without_automatic_restore(
    tmp_path: Path,
    service_environment: dict,
) -> None:
    upstream, checkout = application_pair(tmp_path)
    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    candidate = add_schema_release(upstream, fail_live=True)
    result = stable(
        tmp_path, checkout, upstream, "update", "--yes", environment=service_environment
    )
    assert result.returncode != 0
    root = tmp_path / "stable"
    record = json.loads((root / "maintenance.json").read_text())
    assert record["data_mutated"] is True
    assert record["candidate"]["commit"] == candidate
    assert Path(record["backup"]).exists()
    with sqlite3.connect(tmp_path / "data.sqlite3") as connection:
        assert "synthetic_note" in {
            row[1] for row in connection.execute("PRAGMA table_info(targets)")
        }
    blocked = stable(tmp_path, checkout, upstream, "start", environment=service_environment)
    assert blocked.returncode != 0
    assert "maintenance" in blocked.stderr
    # Recovery must not require the failed live schema to remain readable.
    with sqlite3.connect(tmp_path / "data.sqlite3") as connection:
        connection.execute("DROP TABLE alembic_version")
    recovered = stable(
        tmp_path,
        checkout,
        upstream,
        "recover",
        "--use",
        "previous",
        "--restore-backup",
        "--yes",
        environment=service_environment,
    )
    assert recovered.returncode == 0, recovered.stderr
    with sqlite3.connect(tmp_path / "data.sqlite3") as connection:
        assert "synthetic_note" not in {
            row[1] for row in connection.execute("PRAGMA table_info(targets)")
        }
    record = json.loads((root / "last-update.json").read_text())
    damaged = Path(record["before_restore"]) / "database.sqlite3"
    assert damaged.is_file()
    with sqlite3.connect(damaged) as connection:
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE name = 'alembic_version'"
        ).fetchone() == (0,)


def test_interrupted_initialization_resumes_explicitly_without_replacing_data(
    tmp_path, monkeypatch, service_environment
):
    upstream, checkout = application_pair(tmp_path)
    admin = upstream / "src/local_text/admin.py"
    admin.write_text(
        admin.read_text().replace(
            'if __name__ == "__main__":',
            "import os\n"
            "if 'seed' in sys.argv and os.environ.get('SYNTHETIC_SEED_FAILURE') == '1':\n"
            "    raise RuntimeError('Synthetic interrupted initialization')\n\n"
            'if __name__ == "__main__":',
        )
    )
    git(upstream, "commit", "-am", "Synthetic initialization failure")
    git(checkout, "pull", "--ff-only")
    monkeypatch.setenv("SYNTHETIC_SEED_FAILURE", "1")
    failed = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert failed.returncode != 0
    database = tmp_path / "data.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO app_settings VALUES ('survivor', '73', CURRENT_TIMESTAMP)")
    monkeypatch.delenv("SYNTHETIC_SEED_FAILURE")
    recovered = stable(
        tmp_path,
        checkout,
        upstream,
        "recover",
        "--use",
        "candidate",
        "--yes",
        environment=service_environment,
    )
    assert recovered.returncode == 0, recovered.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value_json FROM app_settings WHERE key = 'survivor'"
        ).fetchone() == ("73",)
        assert connection.execute("SELECT count(*) FROM active_prompt").fetchone() == (1,)
    assert not (tmp_path / "stable/maintenance.json").exists()


def test_foreign_listener_and_interrupted_activation_cannot_start_stable(tmp_path):
    upstream, checkout = application_pair(tmp_path)
    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    before = (tmp_path / "data.sqlite3").read_bytes()
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 7532))
        listener.listen()
        blocked = stable(tmp_path, checkout, upstream, "start")
        assert blocked.returncode != 0
        assert "occupied" in blocked.stderr
        assert listener.getsockname()[1] == 7532
    root = tmp_path / "stable"
    (root / "maintenance.json").write_text(
        json.dumps(
            {
                "phase": "activating",
                "launch_commit": git(checkout, "rev-parse", "HEAD"),
            }
        )
    )
    blocked = stable(tmp_path, checkout, upstream, "serve")
    assert blocked.returncode != 0
    assert "interrupted activation" in blocked.stderr
    assert (tmp_path / "data.sqlite3").read_bytes() == before
