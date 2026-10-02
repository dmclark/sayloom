import fcntl
import hashlib
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parent.parent


def unused_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


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
    isolated_environment = dict(environment or os.environ)
    if environment is None or isolated_environment.get("HOME") == os.environ.get("HOME"):
        isolated_environment["HOME"] = str(state_root.parent / "synthetic-home")
    return subprocess.run(
        [
            str(REPOSITORY_ROOT / "scripts/dev.py"),
            "--state-root",
            str(state_root),
            *arguments,
        ],
        cwd=REPOSITORY_ROOT,
        env=isolated_environment,
        text=True,
        capture_output=True,
        check=False,
    )


def write_foreign_state(
    state_root: Path,
    *,
    name: str,
    repository: Path,
    port: int,
) -> Path:
    directory = state_root / name
    directory.mkdir(parents=True)
    checkout = str(repository.resolve())
    checkout_id = hashlib.sha256(checkout.encode()).hexdigest()[:12]
    manifest = {
        "name": name,
        "repository_root": checkout,
        "state_directory": str(directory.resolve()),
        "label": f"local.local-text.development.{checkout_id}.{name}",
        "port": port,
    }
    manifest_path = directory / "state.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path


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
    assert 7523 <= manifest["port"] <= 7622
    assert manifest["port"] != 7532

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


def test_status_without_selection_reports_state_for_current_checkout(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    selected_port = unused_port()
    assert (
        run_dev(state_root, "create", "selected", "--port", str(selected_port)).returncode == 0
    )
    write_foreign_state(
        state_root,
        name="other",
        repository=tmp_path / "another-checkout",
        port=unused_port(),
    )

    status = run_dev(state_root, "status")

    assert status.returncode == 1
    assert status.stdout.count('"state": "missing"') == 1
    assert "State: selected" in status.stdout
    assert "State: other" not in status.stdout
    duplicate = run_dev(state_root, "create", "duplicate")
    assert duplicate.returncode != 0
    assert "already has a development state" in duplicate.stderr


def test_status_without_selection_prompts_to_create_state_for_current_checkout(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "states"

    status = run_dev(state_root, "status")

    assert status.returncode == 0
    assert status.stdout.splitlines() == [
        "No development state for this checkout.",
        "Create and initialize one with: scripts/dev.py init",
    ]

    implicit = run_dev(state_root)
    assert implicit.returncode == 0
    assert implicit.stdout == status.stdout


def test_status_without_selection_rejects_multiple_states_for_current_checkout(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "states"
    for name in ("first", "second"):
        write_foreign_state(
            state_root,
            name=name,
            repository=REPOSITORY_ROOT,
            port=unused_port(),
        )

    status = run_dev(state_root, "status")

    assert status.returncode != 0
    assert "multiple development states (first, second)" in status.stderr


def test_logs_show_bounded_labeled_output_for_current_checkout(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    selected_logs = state_root / "selected/logs"
    selected_logs.mkdir()
    (selected_logs / "service.log").write_text("old output\nrecent output\nlatest output\n")
    (selected_logs / "service-error.log").write_text("old error\nlatest error\n")
    write_foreign_state(
        state_root,
        name="other",
        repository=tmp_path / "another-checkout",
        port=unused_port(),
    )
    other_logs = state_root / "other/logs"
    other_logs.mkdir()
    (other_logs / "service.log").write_text("private other output\n")
    (other_logs / "service-error.log").write_text("private other error\n")

    result = run_dev(state_root, "logs", "--lines", "2")

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "==> service output <==",
        "recent output",
        "latest output",
        "==> service errors <==",
        "old error",
        "latest error",
    ]
    assert "private other" not in result.stdout
    assert str(state_root) not in result.stdout


def test_logs_line_count_short_option_bounds_each_stream(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    logs = state_root / "selected/logs"
    logs.mkdir()
    (logs / "service.log").write_text("first output\nlast output\n")
    (logs / "service-error.log").write_text("first error\nlast error\n")

    result = run_dev(state_root, "logs", "-n", "1")

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "==> service output <==",
        "last output",
        "==> service errors <==",
        "last error",
    ]


def test_logs_format_json_entries_for_human_reading(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    logs = state_root / "selected/logs"
    logs.mkdir()
    (logs / "service.log").write_text('{"level":"info","event":"ready"}\nplain output\n')
    (logs / "service-error.log").write_text('{"level":"error","status":503}\n')

    result = run_dev(state_root, "logs")

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "==> service output <==",
        "{",
        '  "level": "info",',
        '  "event": "ready"',
        "}",
        "plain output",
        "==> service errors <==",
        "{",
        '  "level": "error",',
        '  "status": 503',
        "}",
    ]


def test_logs_format_complete_json_after_a_text_prefix(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    logs = state_root / "selected/logs"
    logs.mkdir()
    (logs / "service.log").write_text(
        'INFO:     cleanup_result {"attempts":[{"outcome":"failure"}],"status":503}\n'
    )
    (logs / "service-error.log").write_text("ordinary text with {braces}\n")

    result = run_dev(state_root, "logs")

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "==> service output <==",
        "INFO:     cleanup_result",
        "{",
        '  "attempts": [',
        "    {",
        '      "outcome": "failure"',
        "    }",
        "  ],",
        '  "status": 503',
        "}",
        "==> service errors <==",
        "ordinary text with {braces}",
    ]


def test_logs_default_output_is_bounded_per_stream(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    logs = state_root / "selected/logs"
    logs.mkdir()
    for filename, label in (("service.log", "output"), ("service-error.log", "error")):
        (logs / filename).write_text("".join(f"{label} {number}\n" for number in range(101)))

    result = run_dev(state_root, "logs")

    assert result.returncode == 0
    assert "output 0\n" not in result.stdout
    assert "error 0\n" not in result.stdout
    assert "output 1\n" in result.stdout
    assert "error 1\n" in result.stdout


@pytest.mark.parametrize("invalid_count", ["0", "-1", "many"])
def test_logs_reject_invalid_line_counts_before_reading_logs(
    tmp_path: Path, invalid_count: str
) -> None:
    state_root = tmp_path / "private-states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    logs = state_root / "selected/logs"
    logs.mkdir()
    (logs / "service.log").write_text("private sentinel output\n")
    (logs / "service-error.log").write_text("private sentinel error\n")

    result = run_dev(state_root, "logs", "--lines", invalid_count)

    assert result.returncode != 0
    assert "lines must be a positive integer" in result.stderr
    assert "private sentinel" not in result.stdout + result.stderr
    assert str(state_root) not in result.stdout + result.stderr


@pytest.mark.parametrize("follow_option", ["-f", "--follow"])
def test_logs_follow_both_streams_until_stopped(tmp_path: Path, follow_option: str) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    logs = state_root / "selected/logs"
    logs.mkdir()
    output_log = logs / "service.log"
    error_log = logs / "service-error.log"
    output_log.write_text("")
    error_log.write_text("")
    process = subprocess.Popen(
        [
            str(REPOSITORY_ROOT / "scripts/dev.py"),
            "--state-root",
            str(state_root),
            "logs",
            follow_option,
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    initial = [process.stdout.readline().strip(), process.stdout.readline().strip()]

    with output_log.open("a") as stream:
        stream.write("appended output\n")
    with error_log.open("a") as stream:
        stream.write("appended error\n")
    time.sleep(0.3)
    process.send_signal(signal.SIGINT)
    stdout, stderr = process.communicate(timeout=2)

    combined = "\n".join([*initial, stdout])
    assert process.returncode == 0
    assert "==> service output <==" in combined
    assert "appended output" in combined
    assert "==> service errors <==" in combined
    assert "appended error" in combined
    assert str(state_root) not in combined + stderr


def test_logs_fail_without_a_state_or_complete_readable_log_set(tmp_path: Path) -> None:
    missing_state_root = tmp_path / "missing-state"
    missing_state = run_dev(missing_state_root, "logs")
    assert missing_state.returncode != 0
    assert "this checkout has no development state" in missing_state.stderr
    assert str(missing_state_root) not in missing_state.stdout + missing_state.stderr

    state_root = tmp_path / "private-states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    logs = state_root / "selected/logs"
    logs.mkdir()
    (logs / "service.log").write_text("private sentinel output\n")
    missing_file = run_dev(state_root, "logs")
    assert missing_file.returncode != 0
    assert "selected development state logs are missing or unreadable" in missing_file.stderr
    assert "private sentinel" not in missing_file.stdout + missing_file.stderr
    assert str(state_root) not in missing_file.stdout + missing_file.stderr

    unreadable = logs / "service-error.log"
    unreadable.write_text("private sentinel error\n")
    unreadable.chmod(0)
    try:
        unreadable_file = run_dev(state_root, "logs")
    finally:
        unreadable.chmod(0o600)
    assert unreadable_file.returncode != 0
    assert "selected development state logs are missing or unreadable" in unreadable_file.stderr
    assert "private sentinel" not in unreadable_file.stdout + unreadable_file.stderr
    assert str(state_root) not in unreadable_file.stdout + unreadable_file.stderr


def test_logs_reject_a_log_directory_outside_the_registered_state(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    external_logs = tmp_path / "unregistered-logs"
    external_logs.mkdir()
    (external_logs / "service.log").write_text("private external output\n")
    (external_logs / "service-error.log").write_text("private external error\n")
    (state_root / "selected/logs").symlink_to(external_logs, target_is_directory=True)

    result = run_dev(state_root, "logs")

    assert result.returncode != 0
    assert "selected development state logs are missing or unreadable" in result.stderr
    assert "private external" not in result.stdout + result.stderr
    assert str(external_logs) not in result.stdout + result.stderr


def test_init_creates_branch_named_state_then_migrates_and_seeds(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    expected_name = branch.lower().replace("/", "-") or REPOSITORY_ROOT.name

    initialized = run_dev(state_root, "init")

    assert initialized.returncode == 0
    manifest = json.loads((state_root / expected_name / "state.json").read_text())
    assert manifest["name"] == expected_name
    assert 7523 <= manifest["port"] <= 7622
    assert (state_root / expected_name / "local-text.sqlite3").is_file()
    database_status = run_dev(state_root, "db")
    assert database_status.returncode == 0
    assert '"state": "current"' in database_status.stdout


def test_create_allocates_unique_ports_and_accepts_an_override(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    write_foreign_state(
        state_root,
        name="foreign",
        repository=tmp_path / "deleted-worktree",
        port=7523,
    )

    created = run_dev(state_root, "create", "selected")

    assert created.returncode == 0
    manifest = json.loads((state_root / "selected/state.json").read_text())
    assert manifest["port"] != 7523

    other_root = tmp_path / "other-states"
    requested_port = unused_port()
    overridden = run_dev(
        other_root, "create", "explicit", "--port", str(requested_port)
    )
    assert overridden.returncode == 0
    assert json.loads((other_root / "explicit/state.json").read_text())["port"] == requested_port


def test_list_prune_and_remove_manage_only_registered_state_data(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    stale_path = write_foreign_state(
        state_root,
        name="stale",
        repository=tmp_path / "deleted-worktree",
        port=unused_port(),
    )
    (stale_path.parent / "environment").write_text("LOCAL_TEXT_OPENAI_MODEL=fixture\n")
    isolated_environment = {
        **os.environ,
        "PATH": os.pathsep.join(
            entry
            for entry in os.environ["PATH"].split(os.pathsep)
            if "supacode.app" not in entry
        ),
    }

    listed = run_dev(state_root, "list")
    preview = run_dev(state_root, "prune", environment=isolated_environment)

    assert listed.returncode == 0
    assert "stale" in listed.stdout.lower()
    assert preview.returncode == 0
    assert preview.stdout.splitlines() == [
        f"Orphaned state: stale ({stale_path.parent}; "
        f"missing checkout {tmp_path / 'deleted-worktree'})",
        "Preview only. Run scripts/dev.py prune --apply to remove these resources.",
    ]
    assert stale_path.exists()

    applied = run_dev(
        state_root,
        "prune",
        "--apply",
        environment={**isolated_environment, "HOME": str(tmp_path / "home")},
    )
    assert applied.returncode == 0
    assert not stale_path.parent.exists()

    current_root = tmp_path / "current-states"
    assert (
        run_dev(
            current_root, "create", "removable", "--port", str(unused_port())
        ).returncode
        == 0
    )
    unconfirmed = run_dev(current_root, "remove")
    assert unconfirmed.returncode != 0
    assert "requires confirmation" in unconfirmed.stderr
    assert (current_root / "removable/state.json").exists()

    removed = run_dev(
        current_root,
        "remove",
        "--yes",
        environment={**os.environ, "HOME": str(tmp_path / "home")},
    )
    assert removed.returncode == 0
    assert not (current_root / "removable").exists()

    absent = run_dev(current_root, "remove", "--all", "--yes")
    assert absent.returncode == 0
    assert "no development state" in absent.stdout

    write_foreign_state(
        current_root,
        name="legacy-one",
        repository=REPOSITORY_ROOT,
        port=unused_port(),
    )
    write_foreign_state(
        current_root,
        name="legacy-two",
        repository=REPOSITORY_ROOT,
        port=unused_port(),
    )
    all_removed = run_dev(
        current_root,
        "remove",
        "--all",
        "--yes",
        environment={**os.environ, "HOME": str(tmp_path / "home")},
    )
    assert all_removed.returncode == 0
    assert not (current_root / "legacy-one").exists()
    assert not (current_root / "legacy-two").exists()


def test_list_orders_and_aligns_states_with_short_paths_and_runner_status(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    scripts = str(REPOSITORY_ROOT / "scripts")
    sys.path.insert(0, scripts)
    try:
        specification = importlib.util.spec_from_file_location(
            "sayloom_dev_list_script", REPOSITORY_ROOT / "scripts/dev.py"
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)

    state_root = tmp_path / "states"
    home = Path.home()
    repository_parent = home / f".missing-{tmp_path.name}"
    first_repository = repository_parent / "first"
    second_repository = repository_parent / "second"
    write_foreign_state(
        state_root,
        name="higher-port",
        repository=second_repository,
        port=7600,
    )
    write_foreign_state(
        state_root,
        name="lower-port",
        repository=first_repository,
        port=7500,
    )
    monkeypatch.setattr(module, "amp_runner_repositories", lambda: {first_repository})
    monkeypatch.setattr(module, "service_is_loaded", lambda _state: False)

    module.print_registered_states(state_root)

    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "STATE        PORT  CHECKOUT  SERVICE  RUNNER  REPOSITORY",
        f"lower-port   7500  stale     stopped  ✓       ~/.missing-{tmp_path.name}/first",
        f"higher-port  7600  stale     stopped          ~/.missing-{tmp_path.name}/second",
    ]


def test_amp_runner_processes_maps_runner_pids_to_checkout_paths(
    tmp_path: Path, monkeypatch
) -> None:
    scripts = str(REPOSITORY_ROOT / "scripts")
    sys.path.insert(0, scripts)
    try:
        specification = importlib.util.spec_from_file_location(
            "sayloom_dev_runner_script", REPOSITORY_ROOT / "scripts/dev.py"
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)

    repository = tmp_path / "managed-worktree"
    responses = iter(
        (
            subprocess.CompletedProcess(
                [], 0, "101 /opt/bin/amp --no-tui\n202 /opt/bin/amp threads list\n"
            ),
            subprocess.CompletedProcess([], 0, f"p101\nn{repository}\n"),
        )
    )
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: next(responses))

    assert module.amp_runner_processes(required=True) == {repository.resolve(): {101}}


def test_amp_runner_processes_fail_closed_when_directory_inspection_fails(monkeypatch) -> None:
    scripts = str(REPOSITORY_ROOT / "scripts")
    sys.path.insert(0, scripts)
    try:
        specification = importlib.util.spec_from_file_location(
            "sayloom_dev_runner_failure_script", REPOSITORY_ROOT / "scripts/dev.py"
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)

    responses = iter(
        (
            subprocess.CompletedProcess([], 0, "101 /opt/bin/amp --no-tui\n"),
            subprocess.CompletedProcess([], 1, "", "inspection failed"),
        )
    )
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: next(responses))

    with pytest.raises(SystemExit, match="could not inspect Amp runner directories"):
        module.amp_runner_processes(required=True)


def test_supacode_worktrees_preserve_encoded_ids_and_statuses(tmp_path: Path, monkeypatch) -> None:
    scripts = str(REPOSITORY_ROOT / "scripts")
    sys.path.insert(0, scripts)
    try:
        specification = importlib.util.spec_from_file_location(
            "sayloom_dev_supacode_script", REPOSITORY_ROOT / "scripts/dev.py"
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)

    repository = tmp_path / "managed worktree"
    worktree_id = module.parse.quote(f"{repository}/", safe="")
    monkeypatch.setattr(module.shutil, "which", lambda _command: "/opt/bin/supacode")

    def fake_run(command: list[str], **_arguments) -> subprocess.CompletedProcess[str]:
        assert command == ["/opt/bin/supacode", "worktree", "list", "--with-status"]
        return subprocess.CompletedProcess(command, 0, f"{worktree_id}\tarchived\n")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module.supacode_worktrees() == {
        repository.resolve(): (worktree_id, "archived")
    }


def test_prune_apply_stops_runner_before_deleting_worktree_and_state(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    scripts = str(REPOSITORY_ROOT / "scripts")
    sys.path.insert(0, scripts)
    try:
        specification = importlib.util.spec_from_file_location(
            "sayloom_dev_prune_script", REPOSITORY_ROOT / "scripts/dev.py"
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)

    state_root = tmp_path / "states"
    repository = tmp_path / "managed-worktree"
    repository.mkdir()
    write_foreign_state(
        state_root,
        name="managed",
        repository=repository,
        port=unused_port(),
    )
    write_foreign_state(
        state_root,
        name="also-managed",
        repository=repository,
        port=unused_port(),
    )
    worktree_id = "%2Fmanaged-worktree%2F"
    events: list[str] = []
    monkeypatch.setattr(
        module,
        "supacode_worktrees",
        lambda: {repository.resolve(): (worktree_id, "archived")},
    )
    monkeypatch.setattr(module, "repository_worktrees", lambda: {repository.resolve()})
    monkeypatch.setattr(
        module, "stop_amp_runners", lambda _repository: events.append("stop runner")
    )

    def fake_run(command: list[str], **_arguments) -> subprocess.CompletedProcess[str]:
        assert command == [
            "supacode",
            "worktree",
            "delete",
            "--worktree",
            worktree_id,
            "--background",
        ]
        events.append("delete worktree")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        module,
        "remove_state",
        lambda _root, state, *, confirmed: events.append(f"remove state {state.name}"),
    )

    module.prune(state_root, apply=False)

    assert capsys.readouterr().out.splitlines() == [
        f"Archived worktree: {repository}",
        f"  State: also-managed ({state_root / 'also-managed'})",
        f"  State: managed ({state_root / 'managed'})",
        "Preview only. Run scripts/dev.py prune --apply to remove these resources.",
    ]
    assert events == []

    module.prune(state_root, apply=True)

    assert events == [
        "stop runner",
        "delete worktree",
        "remove state also-managed",
        "remove state managed",
    ]


def test_prune_protects_non_archived_foreign_and_unregistered_worktrees(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    scripts = str(REPOSITORY_ROOT / "scripts")
    sys.path.insert(0, scripts)
    try:
        specification = importlib.util.spec_from_file_location(
            "sayloom_dev_protected_prune_script", REPOSITORY_ROOT / "scripts/dev.py"
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)

    state_root = tmp_path / "states"
    repositories = {
        name: tmp_path / name
        for name in ("active", "pinned", "primary", "foreign", "unregistered")
    }
    for index, (name, repository) in enumerate(repositories.items(), start=1):
        repository.mkdir()
        write_foreign_state(
            state_root,
            name=name,
            repository=repository,
            port=7400 + index,
        )
    monkeypatch.setattr(
        module,
        "supacode_worktrees",
        lambda: {
            repositories["active"].resolve(): ("active-id", "unpinned"),
            repositories["pinned"].resolve(): ("pinned-id", "pinned"),
            repositories["primary"].resolve(): ("primary-id", "main"),
            repositories["foreign"].resolve(): ("foreign-id", "archived"),
        },
    )
    monkeypatch.setattr(
        module,
        "repository_worktrees",
        lambda: {
            repositories["active"].resolve(),
            repositories["pinned"].resolve(),
            repositories["primary"].resolve(),
            repositories["unregistered"].resolve(),
        },
    )
    monkeypatch.setattr(
        module,
        "stop_amp_runners",
        lambda _repository: pytest.fail("protected worktrees must not be inspected for shutdown"),
    )

    module.prune(state_root, apply=True)

    assert (
        capsys.readouterr().out
        == "No archived worktrees or orphaned development states found.\n"
    )
    assert all((state_root / name / "state.json").exists() for name in repositories)


def test_prune_apply_preserves_worktree_and_state_when_runner_does_not_stop(
    tmp_path: Path, monkeypatch
) -> None:
    scripts = str(REPOSITORY_ROOT / "scripts")
    sys.path.insert(0, scripts)
    try:
        specification = importlib.util.spec_from_file_location(
            "sayloom_dev_failed_prune_script", REPOSITORY_ROOT / "scripts/dev.py"
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)

    state_root = tmp_path / "states"
    repository = tmp_path / "managed-worktree"
    repository.mkdir()
    manifest = write_foreign_state(
        state_root,
        name="managed",
        repository=repository,
        port=unused_port(),
    )
    monkeypatch.setattr(
        module,
        "supacode_worktrees",
        lambda: {repository.resolve(): ("%2Fmanaged-worktree%2F", "archived")},
    )
    monkeypatch.setattr(module, "repository_worktrees", lambda: {repository.resolve()})
    monkeypatch.setattr(
        module,
        "stop_amp_runners",
        lambda _repository: module.fail("runner remained active; preserving its worktree"),
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_arguments, **_keywords: pytest.fail("worktree deletion must not run"),
    )

    with pytest.raises(SystemExit, match="runner remained active"):
        module.prune(state_root, apply=True)

    assert repository.exists()
    assert manifest.exists()


def test_activate_swaps_the_raycast_port_and_repoints_installed_aliases(
    tmp_path: Path, monkeypatch
) -> None:
    state_root = tmp_path / "states"
    selected_port = unused_port()
    assert (
        run_dev(state_root, "create", "selected", "--port", str(selected_port)).returncode == 0
    )
    write_foreign_state(
        state_root,
        name="raycast-owner",
        repository=tmp_path / "other-worktree",
        port=7523,
    )

    scripts = str(REPOSITORY_ROOT / "scripts")
    sys.path.insert(0, scripts)
    try:
        specification = importlib.util.spec_from_file_location(
            "sayloom_dev_script", REPOSITORY_ROOT / "scripts/dev.py"
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)
    restarted = []
    monkeypatch.setattr(module, "verify_repository", lambda: None)
    monkeypatch.setattr(
        module, "restart", lambda state, **_arguments: restarted.append(state)
    )
    raycast_directory = tmp_path / "raycast-commands"
    raycast_directory.mkdir()
    old_checkout = tmp_path / "old-checkout" / "raycast"
    for source in (REPOSITORY_ROOT / "raycast").glob("*.sh"):
        if "# @raycast.schemaVersion" in source.read_text():
            (raycast_directory / f"dev-{source.name}").symlink_to(old_checkout / source.name)

    selected = module.load_state(state_root, "selected")
    module.activate(state_root, selected, raycast_directory=raycast_directory)

    assert module.load_state(state_root, "selected").port == 7523
    foreign = json.loads((state_root / "raycast-owner/state.json").read_text())
    assert foreign["port"] == selected_port
    assert [state.name for state in restarted] == ["selected"]
    for alias in raycast_directory.iterdir():
        source = REPOSITORY_ROOT / "raycast" / alias.name.removeprefix("dev-")
        assert alias.resolve() == source.resolve()


def test_activate_rejects_alias_conflicts_before_changing_state(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    selected_port = unused_port()
    assert (
        run_dev(state_root, "create", "selected", "--port", str(selected_port)).returncode == 0
    )
    raycast_directory = tmp_path / "raycast-commands"
    raycast_directory.mkdir()
    conflict = raycast_directory / "dev-open-sayloom.sh"
    conflict.write_text("unrelated command\n")

    scripts = str(REPOSITORY_ROOT / "scripts")
    sys.path.insert(0, scripts)
    try:
        specification = importlib.util.spec_from_file_location(
            "sayloom_dev_conflict_script", REPOSITORY_ROOT / "scripts/dev.py"
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)

    selected = module.load_state(state_root, "selected")
    with pytest.raises(SystemExit, match="refusing to replace existing entry"):
        module.activate(state_root, selected, raycast_directory=raycast_directory)

    assert module.load_state(state_root, "selected").port == selected_port
    assert conflict.read_text() == "unrelated command\n"


def test_help_lists_checkout_service_database_and_cleanup_commands() -> None:
    result = subprocess.run(
        [str(REPOSITORY_ROOT / "scripts/dev.py"), "--help"],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    for command_name in (
        "status",
        "create",
        "initialize",
        "restart",
        "activate",
        "logs",
        "list",
        "remove",
        "prune",
        "db",
    ):
        assert command_name in result.stdout
    assert "evidence-package" not in result.stdout
    assert "Running without a command is equivalent to status" in result.stdout

    logs_help = run_dev(Path("unused"), "logs", "--help")
    assert logs_help.returncode == 0
    assert "-n LINES, --lines LINES" in logs_help.stdout
    assert "-f, --follow" in logs_help.stdout
    assert "--provider-traffic" in logs_help.stdout
    assert "default: 100" in logs_help.stdout
    normalized_help = " ".join(logs_help.stdout.split())
    assert "Valid JSON entries are indented" in normalized_help
    assert "private filesystem paths" in normalized_help
    assert "exact request and response content, including dictated/transcribed text" in (
        normalized_help
    )


def test_provider_traffic_diagnostics_marker_is_temporary_and_exclusively_locked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0

    scripts = str(REPOSITORY_ROOT / "scripts")
    sys.path.insert(0, scripts)
    try:
        specification = importlib.util.spec_from_file_location(
            "sayloom_dev_provider_traffic_script", REPOSITORY_ROOT / "scripts/dev.py"
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)

    marker = state_root / "selected/.provider-traffic-diagnostics"
    marker.write_text(str(os.getpid()))
    observed: list[tuple[int, bool]] = []

    def observe_logs(state, *, lines: int, follow: bool) -> None:
        assert marker.read_text() == str(os.getpid())
        assert marker.stat().st_mode & 0o777 == 0o600
        with marker.open() as contender:
            with pytest.raises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_SH | fcntl.LOCK_NB)
        observed.append((lines, follow))

    module.show_logs = observe_logs
    arguments = module.parser().parse_args(
        ["--state-root", str(state_root), "logs", "--provider-traffic"]
    )

    assert module.command(arguments) == 0
    assert not marker.exists()
    assert observed == [(100, True)]
    warning = capsys.readouterr().out
    assert "exact dictated/transcribed text" in warning
    assert "Press Ctrl-C" in warning


def test_supacode_lifecycle_initializes_runs_and_deletes_without_archiving() -> None:
    configuration = json.loads((REPOSITORY_ROOT / "supacode.json").read_text())

    assert configuration["setupScript"] == "scripts/dev.py init"
    assert configuration["runScript"] == "scripts/dev.py restart"
    assert configuration["deleteScript"] == "scripts/dev.py remove --all --yes"
    assert "archiveScript" not in configuration


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("repository_root", "/tmp/another-checkout", "different checkout"),
        ("state_directory", "/tmp/outside-state-root", "outside its selected"),
        ("label", "local.local-text.development.other", "invalid service label"),
        ("port", 700, "invalid loopback port"),
        ("port", 7532, "reserved production port"),
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


@pytest.mark.parametrize(
    "entry",
    [
        "LOCAL_TEXT_DATABASE_PATH=/tmp/other.sqlite3",
        "LOCAL_TEXT_EVIDENCE_PACKAGE_DIRECTORY=/tmp/retired-evidence-package",
    ],
)
def test_runtime_environment_rejects_unsupported_configuration(
    tmp_path: Path, entry: str
) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    manifest = json.loads((state_root / "selected/state.json").read_text())
    home = tmp_path / "home"
    environment_path = home / ".config/local-text/development/environment"
    environment_path.parent.mkdir(parents=True)
    environment_path.write_text(f"{entry}\n")
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


def test_runtime_environment_passes_supported_runtime_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    manifest = json.loads((state_root / "selected/state.json").read_text())
    config_root = tmp_path / "home/.config/local-text/development"
    environment_path = config_root / "environment"
    environment_path.parent.mkdir(parents=True)
    environment_path.write_text("LOCAL_TEXT_CLEANUP_ROUTE_ATTEMPT_SECONDS=18,12\n")
    environment_path.chmod(0o600)

    scripts = str(REPOSITORY_ROOT / "scripts")
    sys.path.insert(0, scripts)
    try:
        specification = importlib.util.spec_from_file_location(
            "sayloom_run_development_script",
            REPOSITORY_ROOT / "scripts/run-development.py",
        )
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)

    development_state = sys.modules[module.state_environment.__module__]
    monkeypatch.setattr(development_state, "DEFAULT_CONFIG_ROOT", config_root)
    captured_environment: dict[str, str] = {}

    def capture_execve(
        executable: Path, arguments: list[str], environment: dict[str, str]
    ) -> None:
        captured_environment.update(environment)
        raise RuntimeError("execution intercepted")

    monkeypatch.setattr(module.os, "execve", capture_execve)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run-development.py",
            "--state-root",
            str(state_root),
            "--state",
            "selected",
            "--label",
            manifest["label"],
            "--port",
            str(manifest["port"]),
        ],
    )

    with pytest.raises(RuntimeError, match="execution intercepted"):
        module.main()

    assert captured_environment["LOCAL_TEXT_CLEANUP_ROUTE_ATTEMPT_SECONDS"] == "18,12"
    assert captured_environment["LOCAL_TEXT_PROVIDER_TRAFFIC_DIAGNOSTICS_FILE"] == str(
        state_root / "selected/.provider-traffic-diagnostics"
    )


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
    legacy = config_root / f"states/{checkout_id}/selected/environment"
    selected = state_root / "selected/environment"
    shared.parent.mkdir(parents=True)
    legacy.parent.mkdir(parents=True)
    secret = "synthetic-secret-not-for-output"
    openai_secret = "synthetic-openai-secret-not-for-output"
    shared.write_text(
        f"LOCAL_TEXT_GEMINI_API_KEY={secret}\n"
        "LOCAL_TEXT_GEMINI_MODEL=shared-model\n"
        "LOCAL_TEXT_GEMINI_QUOTA_GROUP_ID=gemini-paid-project\n"
        f"LOCAL_TEXT_OPENAI_API_KEY={openai_secret}\n"
        "LOCAL_TEXT_OPENAI_MODEL=gpt-5.6-luna\n"
        "LOCAL_TEXT_OPENAI_QUOTA_GROUP_ID=openai-paid-project\n"
        "LOCAL_TEXT_CLEANUP_ROUTE_ORDER=gemini,openai\n"
        "LOCAL_TEXT_CLEANUP_PAID_DATA_ACKNOWLEDGEMENT=paid-external-cleanup-v1\n"
    )
    legacy.write_text("LOCAL_TEXT_GEMINI_MODEL=selected-model\n")
    shared.chmod(0o600)
    legacy.chmod(0o600)
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
    assert f"State configuration: {legacy} (present; moves on init or restart)" in status.stdout
    assert "Gemini credential: configured" in status.stdout
    assert "Gemini model: selected-model" in status.stdout
    assert "Cleanup route order: gemini,openai" in status.stdout
    assert "Gemini quota group: configured" in status.stdout
    assert "OpenAI credential: configured" in status.stdout
    assert "OpenAI model: gpt-5.6-luna" in status.stdout
    assert "OpenAI quota group: configured" in status.stdout
    assert "Paid-data acknowledgement: configured" in status.stdout
    assert secret not in status.stdout
    assert secret not in status.stderr
    assert openai_secret not in status.stdout
    assert openai_secret not in status.stderr

    initialized = run_dev(
        state_root,
        "init",
        environment=environment,
    )
    assert initialized.returncode == 0
    assert selected.read_text() == "LOCAL_TEXT_GEMINI_MODEL=selected-model\n"
    assert not legacy.exists()

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


def test_runtime_helpers_require_explicit_state_selection(tmp_path: Path) -> None:
    state_root = tmp_path / "states"
    development = run_dev(state_root)
    assert development.returncode == 0
    assert "No development state for this checkout" in development.stdout

    for script_name in ("run-development.py", "render-launchd-plist.py"):
        result = subprocess.run(
            [
                str(REPOSITORY_ROOT / "scripts" / script_name),
                "--state-root",
                str(state_root),
            ],
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
