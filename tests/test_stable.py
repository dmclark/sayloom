"""Stable's public CLI against isolated repositories and synthetic state."""

import json
import os
import runpy
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib import request

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts/stable.py"


@pytest.fixture(scope="session")
def dependency_cache_home(
    tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest
) -> Path:
    preparation = tmp_path_factory.mktemp("dependency-cache")
    cache = preparation / "cache"
    config = preparation / "configuration.json"
    config.write_text("{}\n")
    config.chmod(0o600)
    controller = runpy.run_path(str(SCRIPT))
    values = controller["environment"](
        {
            "configuration": str(config),
            "database": str(preparation / "unused.sqlite3"),
            "raycast_directory": str(preparation / "unused-commands"),
        },
        REPOSITORY,
    )
    seed_environment = preparation / "environment"
    values.update(
        HOME=str(preparation / "home"),
        XDG_CONFIG_HOME=str(preparation / "config"),
        XDG_DATA_HOME=str(preparation / "data"),
        XDG_CACHE_HOME=str(cache),
        UV_PROJECT_ENVIRONMENT=str(seed_environment),
    )
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    capture = request.config.pluginmanager.get_plugin("capturemanager")
    log = preparation / "preparation.log"
    if reporter is not None:
        with capture.global_and_fixture_disabled():
            reporter.write_line(
                f"[lifecycle cache] Preparing locked dependencies; progress log: {log}"
            )
            reporter.flush()
    started = time.monotonic()
    failure = None
    with log.open("w") as output:
        try:
            result = subprocess.run(
                [
                    "uv", "sync", "--locked", "--no-editable", "--python", sys.executable,
                    "--project", str(REPOSITORY),
                ],
                env=values,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=300,
            )
            if result.returncode:
                failure = f"exit {result.returncode}"
        except (OSError, subprocess.TimeoutExpired) as error:
            failure = type(error).__name__
    elapsed = time.monotonic() - started
    # No test uses the seed environment, only its downloaded/built cache inputs.
    if seed_environment.exists():
        shutil.rmtree(seed_environment)
    if failure is not None:
        pytest.exit(
            f"Lifecycle cache preparation failed after {elapsed:.2f}s ({failure}); "
            f"see {log}. No controller install was attempted.",
            returncode=1,
        )
    if reporter is not None:
        with capture.global_and_fixture_disabled():
            reporter.write_line(
                f"[lifecycle cache] Prepared in {elapsed:.2f}s; seed environment removed"
            )
            reporter.flush()
    return cache


@pytest.fixture(autouse=True)
def shared_dependency_cache(dependency_cache_home: Path, monkeypatch: pytest.MonkeyPatch):
    # Stable strips UV_* overrides. uv honors XDG_CACHE_HOME on Unix, including macOS.
    # Only downloads/build inputs are shared; HOME and installed environments stay disposable.
    monkeypatch.setenv("XDG_CACHE_HOME", str(dependency_cache_home))


@pytest.fixture(autouse=True)
def isolated_port(tmp_path: Path):
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = candidate.getsockname()[1]
    (tmp_path / "port").write_text(str(port))


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
    if "install" in arguments and "--port" not in arguments:
        arguments = (*arguments, "--port", (tmp_path / "port").read_text())
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


def test_legacy_installation_keeps_default_port_without_rewriting_manifest(tmp_path: Path) -> None:
    controller = runpy.run_path(str(SCRIPT))
    configuration = tmp_path / "environment.json"
    configuration.write_text("{}\n")
    configuration.chmod(0o600)
    installed = {
        "protocol": 1,
        "configuration": str(configuration),
        "database": str(tmp_path / "data.sqlite3"),
        "raycast_directory": str(tmp_path / "commands"),
    }
    manifest = tmp_path / "installation.json"
    manifest.write_text(json.dumps(installed))
    before = manifest.read_bytes()
    loaded = controller["load_installation"](tmp_path)
    assert loaded == installed
    assert controller["environment"](loaded, tmp_path)["LOCAL_TEXT_PORT"] == "7532"
    assert manifest.read_bytes() == before


@pytest.mark.parametrize("port", ["1023", "65536", "7523"])
def test_install_rejects_invalid_or_development_port_before_preparing_runtime(tmp_path, port):
    upstream, checkout = repository_pair(tmp_path)
    rejected = stable(tmp_path, checkout, upstream, "install", "--initialize", "--port", port)
    assert rejected.returncode != 0
    assert "Stable port must be between" in rejected.stderr
    assert not (tmp_path / "stable/environments").exists()
    assert not (tmp_path / "home/.config/local-text/stable/environment.json").exists()


def application_pair(tmp_path: Path) -> tuple[Path, Path]:
    upstream, checkout = repository_pair(tmp_path)
    for name in ("src", "migrations", "scripts", "raycast", "launchd"):
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
        "--reuse-existing",
        *arguments,
    )


def test_default_install_and_existing_installation_preserve_files(tmp_path: Path) -> None:
    upstream, checkout = application_pair(tmp_path)
    home = tmp_path / "home"
    config = home / ".config/local-text/stable/environment.json"
    database = home / ".local/share/local-text/stable/local-text.sqlite3"
    missing = stable(tmp_path, checkout, upstream, "install")
    assert missing.returncode != 0
    assert "--initialize" in missing.stderr
    assert str(database) in missing.stdout
    assert str(config) in missing.stdout
    assert not config.exists()

    declined = stable(tmp_path, checkout, upstream, "install", "--initialize", input="n\n")
    assert declined.returncode == 0, declined.stderr
    assert not config.exists()
    assert not database.exists()

    prepared = stable(tmp_path, checkout, upstream, "install", "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    root = tmp_path / "stable"
    manifest = root / "installation.json"
    installed = json.loads(manifest.read_text())
    assert installed["database"] == str(database)
    assert installed["configuration"] == str(config)
    assert installed["raycast_directory"] == str(home / ".config/raycast/scripts")
    assert config.read_text() == "{}\n"
    assert config.stat().st_mode & 0o777 == 0o600
    config.write_text('{"LOCAL_TEXT_OPENAI_MODEL": "owner-model"}\n')
    before = {path: path.read_bytes() for path in (manifest, config, database, root / "stable.py")}
    for arguments, answer, success in (
        ((), "", False),
        (("--yes",), "", False),
        ((), "y\n", True),
        (("--reuse-existing", "--yes"), "", True),
        (("--configuration", str(tmp_path / "other.json"), "--reuse-existing"), "", False),
        (("--port", "12345", "--reuse-existing"), "", False),
        (("--initialize", "--reuse-existing"), "", False),
    ):
        result = stable(tmp_path, checkout, upstream, "install", *arguments, input=answer)
        assert (result.returncode == 0) is success, result.stderr
        assert {path: path.read_bytes() for path in before} == before


def test_install_rejects_older_source_before_preparing_files(tmp_path, monkeypatch):
    upstream, checkout = application_pair(tmp_path)
    controller = upstream / "scripts/stable.py"
    controller.write_text(
        controller.read_text().replace("STABLE_PROTOCOL = 2", "STABLE_PROTOCOL = 1")
    )
    git(upstream, "commit", "-am", "Synthetic older controller protocol")
    git(checkout, "pull", "--ff-only")
    monkeypatch.setenv("UV_OFFLINE", "1")

    rejected = stable(tmp_path, checkout, upstream, "install", "--initialize", "--yes")

    assert rejected.returncode != 0
    assert "requires port-aware source with launcher protocol" in rejected.stderr
    assert not (tmp_path / "stable/environments").exists()
    assert not (tmp_path / "stable/installation.json").exists()
    assert not (tmp_path / "home/.config/local-text/stable/environment.json").exists()
    assert not (tmp_path / "home/.local/share/local-text/stable/local-text.sqlite3").exists()
    assert not (tmp_path / "home/.config/raycast/scripts").exists()


def test_install_checkout_option_accepts_either_position_and_requires_a_directory(tmp_path):
    upstream, checkout = repository_pair(tmp_path)
    after = stable(tmp_path, checkout, upstream, "install", "--checkout", str(checkout))
    assert after.returncode != 0
    assert "--initialize" in after.stderr
    assert "unrecognized arguments" not in after.stderr
    for arguments in (("--checkout", "main", "install"), ("install", "--checkout", "main")):
        invalid = stable(tmp_path, checkout, upstream, *arguments)
        assert invalid.returncode != 0
        assert "directory" in invalid.stderr
        assert "branch" in invalid.stderr
        assert "database is missing" not in invalid.stderr


def test_existing_stable_database_is_offered_without_initializing_a_new_one(tmp_path):
    upstream, checkout = repository_pair(tmp_path)
    home = tmp_path / "home"
    database = home / ".local/share/local-text/stable/local-text.sqlite3"
    database.parent.mkdir(parents=True)
    # The decline path must not open or interpret existing database contents.
    database.write_bytes(b"owner database must not be opened or replaced")
    before = database.read_bytes()
    declined = stable(tmp_path, checkout, upstream, "install", input="n\n")
    assert declined.returncode == 0, declined.stderr
    assert str(database) in declined.stdout
    assert "Reuse" in declined.stdout
    assert database.read_bytes() == before
    assert not (home / "Library/Application Support/local-text/release").exists()
    assert not (home / ".config/local-text/stable/environment.json").exists()
    refused = stable(tmp_path, checkout, upstream, "install", "--initialize", "--yes")
    assert refused.returncode != 0
    assert "--initialize is only for a new database" in refused.stderr
    explicit = tmp_path / "different.sqlite3"
    overridden = stable(tmp_path, checkout, upstream, "install", "--database", str(explicit))
    assert overridden.returncode != 0
    assert "database is missing" in overridden.stderr
    assert str(explicit) in overridden.stdout


def test_existing_configuration_requires_reuse_and_legacy_is_preserved(tmp_path: Path) -> None:
    upstream, checkout = application_pair(tmp_path)
    directory = tmp_path / "home/.config/local-text/stable"
    directory.mkdir(parents=True)
    legacy = directory / "environment"
    legacy.write_text("SYNTHETIC_OWNER_SETTING=preserve\n")
    legacy.chmod(0o600)
    refused = stable(tmp_path, checkout, upstream, "install", "--initialize", "--yes")
    assert refused.returncode != 0
    assert "legacy" in refused.stderr
    assert legacy.read_text() == "SYNTHETIC_OWNER_SETTING=preserve\n"
    assert not (directory / "environment.json").exists()

    config = directory / "environment.json"
    config.write_text('{"LOCAL_TEXT_OPENAI_MODEL": "synthetic-model"}\n')
    config.chmod(0o600)
    refused = stable(tmp_path, checkout, upstream, "install", "--initialize", "--yes")
    assert refused.returncode != 0
    assert "--reuse-existing" in refused.stderr
    assert not (tmp_path / "stable/installation.json").exists()
    prepared = stable(
        tmp_path, checkout, upstream, "install", "--initialize", "--reuse-existing", "--yes"
    )
    assert prepared.returncode == 0, prepared.stderr
    assert config.read_text() == '{"LOCAL_TEXT_OPENAI_MODEL": "synthetic-model"}\n'
    assert legacy.read_text() == "SYNTHETIC_OWNER_SETTING=preserve\n"


def test_isolated_installations_reuse_dependencies_offline(tmp_path: Path) -> None:
    installations = []
    for index in range(2):
        directory = tmp_path / str(index)
        directory.mkdir()
        (directory / "port").write_text(str(18000 + index))
        upstream, checkout = application_pair(directory)
        prepared = stable(
            directory, checkout, upstream, "install", "--initialize", "--yes",
            environment={"UV_OFFLINE": "1"},
        )
        assert prepared.returncode == 0, prepared.stderr
        installed = json.loads((directory / "stable/installation.json").read_text())
        assert not (checkout / ".venv").exists()
        prefix = subprocess.check_output(
            [installed["python"], "-c", "import sys; print(sys.prefix)"], text=True
        ).strip()
        assert Path(prefix) == Path(installed["python"]).parent.parent
        installations.append(installed)

    for key in ("python", "database", "configuration", "port", "label", "plist"):
        assert installations[0][key] != installations[1][key]
    first_config = Path(installations[0]["configuration"])
    first_config.write_text('{"LOCAL_TEXT_OPENAI_MODEL": "first-only"}\n')
    assert Path(installations[1]["configuration"]).read_text() == "{}\n"


def test_legacy_configuration_can_be_reused_without_conversion(tmp_path: Path) -> None:
    upstream, checkout = application_pair(tmp_path)
    directory = tmp_path / "home/.config/local-text/stable"
    directory.mkdir(parents=True)
    legacy = directory / "environment"
    contents = (
        "# Existing Stable settings\n"
        "export LOCAL_TEXT_OPENAI_MODEL='synthetic model'\n"
        "LOCAL_TEXT_OPENAI_API_KEY='synthetic-secret'\n"
    )
    legacy.write_text(contents)
    legacy.chmod(0o600)

    declined = stable(tmp_path, checkout, upstream, "install", "--initialize", input="n\n")
    assert declined.returncode == 0, declined.stderr
    assert "Reuse" in declined.stdout
    assert str(legacy) in declined.stdout
    assert not (tmp_path / "stable/installation.json").exists()
    refused = stable(tmp_path, checkout, upstream, "install", "--initialize", "--yes")
    assert refused.returncode != 0
    assert "--reuse-existing" in refused.stderr

    prepared = stable(tmp_path, checkout, upstream, "install", "--initialize", input="y\ny\n")
    assert prepared.returncode == 0, prepared.stderr
    installed = json.loads((tmp_path / "stable/installation.json").read_text())
    assert installed["configuration"] == str(legacy)
    assert legacy.read_text() == contents
    assert not (directory / "environment.json").exists()
    assert "synthetic-secret" not in declined.stdout + refused.stderr + prepared.stdout
    status = stable(tmp_path, checkout, upstream, "status")
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["schema"]["state"] == "current"


@pytest.mark.parametrize(
    "contents",
    [
        'LOCAL_TEXT_OPENAI_MODEL="$(touch {marker})"\n',
        "touch {marker}\n",
        "LOCAL_TEXT_OPENAI_MODEL=synthetic;true\n",
        "LOCAL_TEXT_DATABASE_PATH=/unrelated/database\n",
        "LOCAL_TEXT_OPENAI_MODEL=first\nLOCAL_TEXT_OPENAI_MODEL=second\n",
    ],
)
def test_legacy_configuration_refuses_shell_code_and_unsupported_settings(
    tmp_path: Path, contents: str
) -> None:
    upstream, checkout = repository_pair(tmp_path)
    directory = tmp_path / "home/.config/local-text/stable"
    directory.mkdir(parents=True)
    legacy = directory / "environment"
    marker = tmp_path / "must-not-exist"
    contents = contents.format(marker=marker)
    legacy.write_text(contents)
    legacy.chmod(0o600)
    result = stable(
        tmp_path, checkout, upstream, "install", "--initialize", "--reuse-existing", "--yes"
    )
    assert result.returncode != 0
    assert "legacy Stable configuration" in result.stderr
    assert legacy.read_text() == contents
    assert not marker.exists()
    assert not (directory / "environment.json").exists()
    assert not (tmp_path / "stable/installation.json").exists()


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


def test_restart_and_confirmed_update_pin_the_previewed_commit(
    tmp_path,
    service_environment,
    monkeypatch,
):
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
    # A caller's test paths must not govern the nested candidate verification.
    monkeypatch.setenv("PYTEST_ADDOPTS", f"--basetemp={tmp_path}")
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


@pytest.mark.parametrize("with_development", [False, True])
def test_stable_runs_independently_with_selected_paths_and_endpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    service_environment: dict,
    with_development: bool,
) -> None:
    upstream, checkout = application_pair(tmp_path)
    home = tmp_path / "home"
    development = None
    development_database = None
    development_before = None
    if with_development:
        dev_checkout = tmp_path / "development-checkout"
        subprocess.run(
            ["git", "clone", str(upstream), str(dev_checkout)], check=True, capture_output=True
        )
        environment = {**os.environ, "HOME": str(home)}
        # As with Stable installation, the caller controls offline dependency bootstrap.
        prepared_development = subprocess.run(
            ["uv", "sync", "--locked", "--python", sys.executable],
            cwd=dev_checkout,
            env=environment,
            text=True,
            capture_output=True,
        )
        assert prepared_development.returncode == 0, prepared_development.stderr
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            dev_port = candidate.getsockname()[1]
        dev_root = home / ".local/share/local-text/dev-states"
        command = [str(dev_checkout / "scripts/dev.py"), "--state-root", str(dev_root)]
        for arguments in (("create", "coexisting", "--port", str(dev_port)), ("db", "init")):
            result = subprocess.run(
                [*command, *arguments],
                cwd=dev_checkout,
                env=environment,
                text=True,
                capture_output=True,
            )
            assert result.returncode == 0, result.stderr
        state = json.loads((dev_root / "coexisting/state.json").read_text())
        development_database = dev_root / "coexisting/local-text.sqlite3"
        development_before = development_database.read_bytes()
        development = subprocess.Popen(
            [
                str(dev_checkout / "scripts/run-development.sh"),
                "--state-root",
                str(dev_root),
                "--state",
                "coexisting",
                "--label",
                state["label"],
                "--port",
                str(dev_port),
            ],
            cwd=dev_checkout,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    try:
        if development:
            for _ in range(100):
                try:
                    with request.urlopen(
                        f"http://127.0.0.1:{dev_port}/health", timeout=1
                    ) as response:
                        assert json.load(response)["development_state"] == "coexisting"
                    break
                except OSError:
                    assert development.poll() is None, "synthetic development service exited"
                    time.sleep(0.05)
            else:
                pytest.fail("synthetic development service did not start")

        # An invalid, irrelevant configuration must not become a Stable prerequisite.
        irrelevant = home / ".config/local-text/development/environment"
        irrelevant.parent.mkdir(parents=True, exist_ok=True)
        irrelevant.write_text("invalid development configuration; preserve me\n")
        for key, value in {
            "LOCAL_TEXT_PROFILE": "development",
            "LOCAL_TEXT_STATE_DIRECTORY": str(tmp_path / "irrelevant-state"),
            "LOCAL_TEXT_DATABASE_PATH": str(tmp_path / "irrelevant.sqlite3"),
            "LOCAL_TEXT_RAYCAST_DIRECTORY": str(irrelevant),
            "UV_PROJECT_ENVIRONMENT": str(tmp_path / "irrelevant-venv"),
            "PYTHONPATH": str(tmp_path / "irrelevant-source"),
        }.items():
            monkeypatch.setenv(key, value)
        prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
        assert prepared.returncode == 0, prepared.stderr
        installed = json.loads((tmp_path / "stable/installation.json").read_text())
        port = int((tmp_path / "port").read_text())
        assert installed["port"] == port
        for path in (tmp_path / "commands").glob("*.sh"):
            assert f"http://127.0.0.1:{port}" in path.read_text()
            assert "http://127.0.0.1:7532" not in path.read_text()

        for operation in ("start", "restart"):
            result = stable(
                tmp_path, checkout, upstream, operation, environment=service_environment
            )
            assert result.returncode == 0, result.stderr
        status = stable(
            tmp_path,
            tmp_path / "irrelevant-checkout",
            tmp_path / "irrelevant-upstream",
            "status",
            environment=service_environment,
        )
        assert status.returncode == 0, status.stderr
        assert json.loads(status.stdout)["health"]["ready"] is True
        assert json.loads(status.stdout)["service"]["owned"] is True
        with request.urlopen(f"http://127.0.0.1:{port}/api/targets", timeout=2) as response:
            targets = json.load(response)["targets"]
        assert targets
        assert all(f"http://127.0.0.1:{port}" in target["preview"] for target in targets)
        assert irrelevant.read_text() == "invalid development configuration; preserve me\n"
        assert not (tmp_path / "irrelevant.sqlite3").exists()
        assert not (tmp_path / "irrelevant-venv").exists()
        if development:
            assert development.poll() is None
            with request.urlopen(f"http://127.0.0.1:{dev_port}/health", timeout=2) as response:
                assert json.load(response)["development_state"] == "coexisting"
            assert development_database.read_bytes() == development_before
    finally:
        if development:
            development.terminate()
            development.wait(timeout=10)


def test_development_activation_and_restart_preserve_coexisting_stable(
    tmp_path: Path, service_environment: dict
) -> None:
    if "SYNTHETIC_SERVICE" not in service_environment:
        pytest.skip("development activation uses the synthetic launchctl boundary")
    upstream, checkout = application_pair(tmp_path)
    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    started = stable(tmp_path, checkout, upstream, "start", environment=service_environment)
    assert started.returncode == 0, started.stderr
    installed = json.loads((tmp_path / "stable/installation.json").read_text())
    preserved = {
        path: path.read_bytes()
        for path in (
            tmp_path / "stable/installation.json",
            tmp_path / "data.sqlite3",
            tmp_path / "environment.json",
            tmp_path / f"synthetic-service-{installed['label']}.json",
        )
    }

    dev_checkout = tmp_path / "development-checkout"
    subprocess.run(
        ["git", "clone", str(upstream), str(dev_checkout)], check=True, capture_output=True
    )
    # Only the disposable checkout's Raycast port changes; real socket guards remain active.
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        activation_port = candidate.getsockname()[1]
        with socket.socket() as initial:
            initial.bind(("127.0.0.1", 0))
            initial_port = initial.getsockname()[1]
    state_module = dev_checkout / "scripts/development_state.py"
    state_module.write_text(
        state_module.read_text().replace(
            "DEVELOPMENT_PORT = 7523", f"DEVELOPMENT_PORT = {activation_port}"
        )
    )
    git(dev_checkout, "config", "user.email", "synthetic@example.invalid")
    git(dev_checkout, "config", "user.name", "Synthetic test")
    git(dev_checkout, "commit", "-am", "Select disposable Raycast port")
    environment = {**os.environ, "HOME": str(tmp_path / "home"), **service_environment}
    dependencies = subprocess.run(
        ["uv", "sync", "--locked", "--python", sys.executable],
        cwd=dev_checkout,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert dependencies.returncode == 0, dependencies.stderr
    environment.update(
        LOCAL_TEXT_PROFILE="release",
        LOCAL_TEXT_DATABASE_PATH=installed["database"],
        LOCAL_TEXT_RAYCAST_DIRECTORY=str(tmp_path / "irrelevant-command-path"),
        PYTEST_ADDOPTS="-k must_not_select_this",
    )
    state_root = tmp_path / "development-states"
    command = [
        str(dev_checkout / ".venv/bin/python"),
        "-c",
        # Exercise the macOS controller boundary with synthetic launchctl on every host.
        "import runpy, sys; from pathlib import Path; "
        "sys.argv = sys.argv[1:]; "
        "sys.path.insert(0, str(Path(sys.argv[0]).parent)); "
        "controller = runpy.run_path(sys.argv[0]); "
        "sys.platform = 'darwin'; controller['main']()",
        str(dev_checkout / "scripts/dev.py"),
        "--state-root",
        str(state_root),
    ]
    created = subprocess.run(
        [*command, "create", "coexisting", "--port", str(initial_port)],
        cwd=dev_checkout,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert created.returncode == 0, created.stderr
    restarted = subprocess.run(
        [*command, "restart"],
        cwd=dev_checkout,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert restarted.returncode == 0, restarted.stdout + restarted.stderr
    manifest = state_root / "coexisting/state.json"
    database = state_root / "coexisting/local-text.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO app_settings VALUES ('synthetic_saved', '\"Café 73\"', CURRENT_TIMESTAMP)"
        )
        connection.execute("UPDATE targets SET enabled = 0 WHERE id = 'amp'")
    before = {path: path.read_bytes() for path in (manifest, database)}
    services_before = {
        path: path.read_bytes() for path in tmp_path.glob("synthetic-service-*.json")
    }
    assert len(services_before) == 2
    alias = tmp_path / "home/.config/raycast/scripts/dev-open-sayloom.sh"
    alias.parent.mkdir(parents=True)
    previous_target = tmp_path / "previous-checkout/raycast/open-sayloom.sh"
    alias.symlink_to(previous_target)
    for configuration in (
        tmp_path / "home/.config/local-text/development/environment",
        state_root / "coexisting/environment",
    ):
        configuration.parent.mkdir(parents=True, exist_ok=True)
        configuration.write_text("LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS=not-a-number\n")
        configuration.chmod(0o600)
        configured = configuration.read_bytes()
        backups_before = list((state_root / "coexisting/backups").glob("*.sqlite3"))
        for operation in ("activate", "restart"):
            blocked = subprocess.run(
                [*command, operation],
                cwd=dev_checkout,
                env=environment,
                text=True,
                capture_output=True,
            )
            assert blocked.returncode != 0
            assert "could not convert string to float" in blocked.stderr
            assert {path: path.read_bytes() for path in before} == before
            assert {path: path.read_bytes() for path in services_before} == services_before
            assert {path: path.read_bytes() for path in preserved} == preserved
            assert configuration.read_bytes() == configured
            assert alias.readlink() == previous_target
            assert list((state_root / "coexisting/backups").glob("*.sqlite3")) == backups_before
        configuration.unlink()
    javascript = dev_checkout / "src/local_text/static/app.js"
    original_javascript = javascript.read_text()
    javascript.write_text("const invalid = ;\n")
    for operation in ("activate", "restart"):
        blocked = subprocess.run(
            [*command, operation],
            cwd=dev_checkout,
            env=environment,
            text=True,
            capture_output=True,
        )
        assert blocked.returncode != 0
        assert "JavaScript finished: exit 1" in blocked.stdout
        assert {path: path.read_bytes() for path in before} == before
        assert {path: path.read_bytes() for path in services_before} == services_before
        assert {path: path.read_bytes() for path in preserved} == preserved
    javascript.write_text(original_javascript)

    for mutation, message in (
        (
            "UPDATE alembic_version SET version_num = 'unknown_revision'",
            "no supported upgrade path",
        ),
        ("INSERT INTO alembic_version VALUES ('unknown_revision')", "incompatible"),
        ("DROP TABLE alembic_version", "incompatible"),
    ):
        with sqlite3.connect(database) as connection:
            connection.execute(mutation)
        incompatible = database.read_bytes()
        for operation in ("activate", "restart"):
            blocked = subprocess.run(
                [*command, operation],
                cwd=dev_checkout,
                env=environment,
                text=True,
                capture_output=True,
            )
            assert blocked.returncode != 0
            assert f"{message}; database preserved" in blocked.stderr
            assert database.read_bytes() == incompatible
            assert manifest.read_bytes() == before[manifest]
            assert {path: path.read_bytes() for path in services_before} == services_before
            assert {path: path.read_bytes() for path in preserved} == preserved
        database.write_bytes(before[database])

    # An unrelated failing test must not run during either ordinary operation.
    smoke = dev_checkout / "tests/test_smoke.py"
    smoke.write_text(
        "def test_candidate():\n    raise AssertionError('synthetic pytest failure')\n"
    )
    add_schema_release(dev_checkout)
    full = subprocess.run(
        [str(dev_checkout / "scripts/check"), "--full"],
        cwd=dev_checkout,
        env={**environment, "PYTEST_ADDOPTS": ""},
        text=True,
        capture_output=True,
    )
    assert full.returncode == 1, full.stdout + full.stderr
    assert "Pytest finished: exit 1" in full.stdout
    assert "synthetic pytest failure" in full.stdout

    for operation in ("activate", "restart"):
        result = subprocess.run(
            [*command, operation],
            cwd=dev_checkout,
            env=environment,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Pytest started" not in result.stdout
        assert "Schema ready for controlled initialization/upgrade" in result.stdout
        assert f"{1 if operation == 'activate' else 0} pending migration(s)" in result.stdout
        assert json.loads(manifest.read_text())["port"] == activation_port
        with sqlite3.connect(database) as connection:
            assert connection.execute(
                "SELECT value_json FROM app_settings WHERE key = 'synthetic_saved'"
            ).fetchone() == ('"Café 73"',)
            assert connection.execute(
                "SELECT enabled FROM targets WHERE id = 'amp'"
            ).fetchone() == (0,)
            assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
                "0007_synthetic_release",
            )
        with request.urlopen(f"http://127.0.0.1:{activation_port}/health", timeout=2) as response:
            health = json.load(response)
        assert health["profile"] == "development"
        assert health["development_state"] == "coexisting"
        with request.urlopen(f"http://127.0.0.1:{installed['port']}/health", timeout=2) as response:
            assert json.load(response)["profile"] == "release"
        assert {path: path.read_bytes() for path in preserved} == preserved
    backup_revisions = set()
    for backup in (state_root / "coexisting/backups").glob("*.sqlite3"):
        with sqlite3.connect(backup) as connection:
            backup_revisions.add(
                connection.execute("SELECT version_num FROM alembic_version").fetchone()
            )
    assert ("0006_confirmed_correction_batches",) in backup_revisions
    assert alias.resolve() == dev_checkout / "raycast/open-sayloom.sh"
    assert not (tmp_path / "irrelevant-command-path").exists()


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
failure = state.with_suffix('.fail')
command = sys.argv[1]
if command == 'bootstrap':
    plist = plistlib.loads(Path(sys.argv[3]).read_bytes())
    label = plist['Label']
else:
    label = sys.argv[2].rsplit('/', 1)[-1]
state = state.with_name(state.stem + '-' + label + state.suffix)
if command == 'print':
    if not state.exists():
        sys.exit(3)
    installed = json.loads(state.read_text())
    print('arguments = {')
    print(*installed['arguments'], sep=chr(10))
    print('}')
    print('pid = ' + str(installed['pid']))
elif command == 'bootstrap':
    if failure.exists():
        failure.unlink()
        sys.exit(5)
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
    validator = directory / "plutil"
    validator.write_text(
        f"#!{sys.executable}\n"
        "import plistlib, sys\n"
        "from pathlib import Path\n"
        "plistlib.loads(Path(sys.argv[2]).read_bytes())\n"
    )
    validator.chmod(0o700)
    state = tmp_path / "synthetic-service.json"
    yield {
        "PATH": str(directory) + os.pathsep + os.environ["PATH"],
        "SYNTHETIC_SERVICE": str(state),
    }
    for state in tmp_path.glob("synthetic-service-*.json"):
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
        port = int((tmp_path / "port").read_text())
        listener.bind(("127.0.0.1", port))
        listener.listen()
        blocked = stable(tmp_path, checkout, upstream, "start")
        assert blocked.returncode != 0
        assert "occupied" in blocked.stderr
        assert listener.getsockname()[1] == port
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
