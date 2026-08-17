import json
import os
import subprocess
from pathlib import Path

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


def test_controlled_workflow_orders_backup_migrate_seed_restart_and_health() -> None:
    workflow = (REPOSITORY_ROOT / "scripts/verify-then-restart.sh").read_text()
    positions = [
        workflow.index("source.backup(destination)"),
        workflow.index("local_text.admin migrate"),
        workflow.index("local_text.admin seed"),
        workflow.index("launchctl kickstart"),
        workflow.index("http://127.0.0.1:7523/health"),
    ]

    assert positions == sorted(positions)
    startup = (REPOSITORY_ROOT / "scripts/run-development.sh").read_text()
    assert "local_text.admin" not in startup
    assert "alembic" not in startup
