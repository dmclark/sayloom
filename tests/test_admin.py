import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
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

    listed = run_dev(state_root, "list")
    preview = run_dev(state_root, "prune")

    assert listed.returncode == 0
    assert "stale" in listed.stdout.lower()
    assert preview.returncode == 0
    assert "Preview only" in preview.stdout
    assert stale_path.exists()

    applied = run_dev(
        state_root,
        "prune",
        "--apply",
        environment={**os.environ, "HOME": str(tmp_path / "home")},
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
    write_foreign_state(
        state_root,
        name="managed",
        repository=repository,
        port=unused_port(),
    )
    worktree_id = "%2Fmanaged-worktree%2F"
    events: list[str] = []
    monkeypatch.setattr(module, "supacode_worktrees", lambda: {repository.resolve(): worktree_id})
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
        lambda _root, _state, *, confirmed: events.append("remove state"),
    )

    module.prune(state_root, apply=False)

    preview = capsys.readouterr().out
    assert "Stale: managed" in preview
    assert "Preview only. Run scripts/dev.py prune --apply" in preview
    assert events == []

    module.prune(state_root, apply=True)

    assert events == ["stop runner", "delete worktree", "remove state"]


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
    manifest = write_foreign_state(
        state_root,
        name="managed",
        repository=repository,
        port=unused_port(),
    )
    monkeypatch.setattr(
        module, "supacode_worktrees", lambda: {repository.resolve(): "%2Fmanaged-worktree%2F"}
    )
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

    assert not repository.exists()
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
        "list",
        "remove",
        "prune",
        "db",
        "evidence-package",
    ):
        assert command_name in result.stdout
    assert "Running without a command is equivalent to status" in result.stdout


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


def test_runtime_environment_passes_evaluation_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "states"
    assert run_dev(state_root, "create", "selected").returncode == 0
    manifest = json.loads((state_root / "selected/state.json").read_text())
    config_root = tmp_path / "home/.config/local-text/development"
    environment_path = config_root / "environment"
    environment_path.parent.mkdir(parents=True)
    evaluation_data_directory = tmp_path / "synthetic-evaluation-data"
    environment_path.write_text(
        f"LOCAL_TEXT_EVALUATION_DATA_DIRECTORY={evaluation_data_directory}\n"
    )
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

    assert captured_environment["LOCAL_TEXT_EVALUATION_DATA_DIRECTORY"] == str(
        evaluation_data_directory
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
