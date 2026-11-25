"""Stable's public CLI against isolated repositories and synthetic state."""

import json
import os
import pty
import runpy
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request
from urllib.parse import parse_qs, urlsplit

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts/stable.py"
CANONICAL = "https://github.com/dmclark/sayloom.git"


def controller_command(script: Path = SCRIPT) -> list[str]:
    # Test-side HTTP transport only: production has no endpoint override or CI bypass.
    return [sys.executable, "-c", """
import os, runpy, sys
from urllib import request
original = request.urlopen
def fixture_open(req, *args, **kwargs):
    url = req.full_url if isinstance(req, request.Request) else req
    prefix = 'https://api.github.com/repos/dmclark/sayloom'
    if url.startswith(prefix):
        forwarded = request.Request(os.environ['SAYLOOM_FIXTURE_API'] + url[len(prefix):],
                                    headers=dict(req.header_items()))
        response = original(forwarded, *args, **kwargs)
        response.url = url
        return response
    return original(req, *args, **kwargs)
request.urlopen = fixture_open
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
""", str(script)]


@pytest.fixture(autouse=True)
def github_api(monkeypatch):
    api = "https://api.github.com/repos/dmclark/sayloom"
    web = "https://github.com/dmclark/sayloom"
    state = {"workflow_reads": 0, "requests": [], "sha": "", "run": {}, "job": {}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state["requests"].append(self.path)
            assert "Authorization" not in self.headers
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            path = parsed.path
            if path == "/actions/workflows/ci.yml":
                state["workflow_reads"] += 1
            status = state.get("http_status", 200)
            if state.get("lose_at") == state["workflow_reads"]:
                status = 503
            repo = {"full_name": "dmclark/sayloom", "html_url": web, "url": api, "fork": False}
            run = {
                "id": 20, "run_number": 2, "run_attempt": 1,
                "url": api + "/actions/runs/20", "html_url": web + "/actions/runs/20",
                "head_sha": state["sha"], "head_branch": "main", "event": "push",
                "path": ".github/workflows/ci.yml", "workflow_id": 7,
                "workflow_url": api + "/actions/workflows/7",
                "repository": repo, "head_repository": repo,
                "updated_at": str(len(state["requests"])),  # Not structural plan identity.
                "status": "completed", "conclusion": "success", **state["run"],
            }
            if path.endswith("/runs"):
                state["sha"] = query["head_sha"][0]
                run["head_sha"] = state["run"].get("head_sha", state["sha"])
                runs = [] if state.get("missing_run") else [run]
                if state.get("pagination"):
                    runs.insert(0, {**run, "id": 10, "run_number": 1,
                                    "url": api + "/actions/runs/10",
                                    "html_url": web + "/actions/runs/10"})
                if state.get("newer_failed"):
                    runs.append({**run, "id": 30, "run_number": 3, "conclusion": "failure",
                                 "url": api + "/actions/runs/30",
                                 "html_url": web + "/actions/runs/30"})
                value = {"total_count": len(runs), "workflow_runs": runs}
                if state.get("pagination"):
                    page = int(query["page"][0])
                    value["workflow_runs"] = runs[page - 1:page]
                    if page > 1 and state.get("empty_page"):
                        value["workflow_runs"] = []
                if state.get("incomplete_page"):
                    value["total_count"] += 1
            elif path.endswith("/jobs"):
                jobs = [{"id": 100, "run_id": 20, "head_sha": state["sha"],
                         "run_attempt": run["run_attempt"], "name": "Linux full checks",
                         "status": "completed", "conclusion": "success", **state["job"]}]
                if state.get("missing_job"):
                    jobs = []
                if state.get("ambiguous_job"):
                    jobs.append({**jobs[0], "id": 101})
                if state.get("pagination"):
                    jobs.insert(0, {**jobs[0], "id": 99, "name": "unrelated job"})
                value = {"total_count": len(jobs), "jobs": jobs}
                if state.get("pagination"):
                    page = int(query["page"][0])
                    value["jobs"] = jobs[page - 1:page]
            elif path == "/actions/workflows/ci.yml":
                value = {"id": 7, "path": ".github/workflows/ci.yml", "state": "active",
                         "url": api + "/actions/workflows/7",
                         "html_url": web + "/blob/main/.github/workflows/ci.yml",
                         **state.get("workflow", {})}
            else:
                value = run
                if state.get("newer_failed"):
                    value = {**run, "id": 30, "run_number": 3, "conclusion": "failure",
                             "url": api + "/actions/runs/30",
                             "html_url": web + "/actions/runs/30"}
                if state.get("rerun_pending"):
                    value = {**value, "run_attempt": 2, "status": "queued", "conclusion": None}
            payload = b"invalid-json" if state.get("invalid_json") else json.dumps(value).encode()
            self.send_response(status)
            if state.get("truncated"):
                self.send_header("Content-Length", str(len(payload) + 50))
                self.close_connection = True
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
    thread.start()
    monkeypatch.setenv("SAYLOOM_FIXTURE_API", f"http://127.0.0.1:{server.server_port}")
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


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
    git(checkout, "config", f"url.{upstream}.insteadOf", CANONICAL)
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
            *controller_command(),
            "--root",
            str(tmp_path / "stable"),
            "--checkout",
            str(checkout),
            "--upstream",
            CANONICAL if "install" in arguments else str(upstream),
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
    github_api,
):
    upstream, checkout = application_pair(tmp_path)
    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    before = (tmp_path / "data.sqlite3").read_bytes()
    github_api["http_status"] = 503
    for operation in ("start", "start", "restart"):
        result = stable(tmp_path, checkout, upstream, operation, environment=service_environment)
        assert result.returncode == 0, result.stderr
    assert (tmp_path / "data.sqlite3").read_bytes() == before
    assert github_api["requests"] == []  # Installed start/restart require no GitHub access.
    github_api.pop("http_status")
    github_api["pagination"] = True
    github_api["run"] = {"run_attempt": 2}
    token_keys = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
    for key in token_keys:
        monkeypatch.setenv(key, "synthetic-token-must-not-reach-candidate")
    with (upstream / "src/local_text/database.py").open("a") as output:
        output.write(f"\nassert not set({token_keys!r}) & __import__('os').environ.keys()\n")
    # Controlled CI evidence replaces these candidate-wide reruns, not operator review.
    (upstream / "tests/test_smoke.py").write_text(
        "import os\n\ndef test_candidate():\n    assert False\n"
    )
    (upstream / "src/local_text/static/app.js").write_text("{ invalid JavaScript\n")
    (upstream / "tracked").write_text("reviewed release\n")
    git(upstream, "commit", "-am", "Reviewed release")
    reviewed = git(upstream, "rev-parse", "HEAD")
    # A caller's test paths must not govern the nested candidate verification.
    monkeypatch.setenv("PYTEST_ADDOPTS", f"--basetemp={tmp_path}")
    process = subprocess.Popen(
        [
            *controller_command(tmp_path / "stable/stable.py"),
            "--root",
            str(tmp_path / "stable"),
            "update",
        ],
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
    assert any("page=2" in path and "/runs?" in path for path in github_api["requests"])
    assert any("/attempts/2/jobs" in path and "page=2" in path for path in github_api["requests"])


@pytest.mark.parametrize(
    "responses",
    [
        pytest.param(
            [
                {"run": {"head_sha": "0" * 40}},
                {"run": {"repository": {"full_name": "other/sayloom"}}},
                {"run": {"head_repository": {"full_name": "fork/sayloom"}}},
                {"run": {"path": ".github/workflows/other.yml"}},
                {"run": {"workflow_id": 99}},
                {"run": {"head_branch": "feature"}},
                {"run": {"event": "pull_request"}},
                {"workflow": {"path": ".github/workflows/other.yml"}},
                {"workflow": {"html_url": "https://github.com/fork/sayloom/blob/main/"
                                          ".github/workflows/ci.yml"}},
                {"missing_job": True},
                {"missing_run": True},
                {"rerun_pending": True},
                {"newer_failed": True, "pagination": True},
                {"job": {"run_attempt": 99}},
                {"job": {"head_sha": "0" * 40}},
                {"job": {"run_id": 99}},
                {"ambiguous_job": True},
                {"http_status": 503},
                {"http_status": 403},
                {"http_status": 429},
                {"invalid_json": True},
                {"truncated": True},
                {"incomplete_page": True},
                {"pagination": True, "empty_page": True},
            ],
            id="initial-ci",
        ),
        pytest.param([{"lose_at": 2}], id="pre-stop-recheck"),
        pytest.param([{"preparation_failure": True}], id="preparation-failure"),
    ],
)
def test_ci_refusal_preserves_running_installation(
    tmp_path, service_environment, github_api, responses
):
    upstream, checkout = application_pair(tmp_path)
    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    started = stable(tmp_path, checkout, upstream, "start", environment=service_environment)
    assert started.returncode == 0, started.stderr
    root = tmp_path / "stable"
    paths = [
        tmp_path / "data.sqlite3",
        root / "installation.json",
        root / "stable.py",
        *tmp_path.glob("synthetic-service-*.json"),
    ]
    before = {path: path.read_bytes() for path in paths}
    old = git(checkout, "rev-parse", "HEAD")
    (upstream / "tracked").write_text("unapproved candidate\n")
    if responses[0].get("preparation_failure"):
        (upstream / "uv.lock").write_text("synthetic-private-lock-error\n")
    git(upstream, "commit", "-am", "Synthetic candidate")
    original_api = deepcopy(github_api)
    # Only initial CI refusals share an installation. Later failures stay isolated above.
    for index, response in enumerate(responses):
        case = f"response {index}"
        github_api.clear()
        github_api.update(deepcopy(original_api))
        github_api.update(response)
        refused = stable(
            tmp_path, checkout, upstream, "update", "--yes", environment=service_environment
        )
        assert refused.returncode != 0, f"{case}: {refused.stdout}"
        assert (
            '"eligible": false' in refused.stdout
            or "Rechecking Linux CI" in refused.stdout
            or response.get("preparation_failure")
        ), case
        assert "error: Stable operation failed:" in refused.stderr, case
        assert "synthetic-private-lock-error" not in refused.stdout + refused.stderr, case
        if response.get("preparation_failure"):
            assert (root / "operation-error.log").stat().st_mode & 0o777 == 0o600, case
        assert git(checkout, "rev-parse", "HEAD") == old, case
        assert {path: path.read_bytes() for path in paths} == before, case
        assert not (root / "maintenance.json").exists(), case
        assert not (root / "backups").exists(), case
        status = stable(tmp_path, checkout, upstream, "status", environment=service_environment)
        assert json.loads(status.stdout)["health"]["ready"] is True, case


def test_preview_refuses_non_success_ci(tmp_path, github_api):
    upstream, checkout = application_pair(tmp_path)
    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    (upstream / "tracked").write_text("candidate\n")
    git(upstream, "commit", "-am", "Synthetic candidate")
    original_api = deepcopy(github_api)
    for status, conclusion in (
        ("queued", None),
        ("in_progress", None),
        ("completed", "failure"),
        ("completed", "cancelled"),
        ("completed", "skipped"),
        ("completed", "neutral"),
        ("completed", "timed_out"),
        ("completed", None),
    ):
        for part in ("run", "job"):
            case = f"{part}: {status}/{conclusion}"
            github_api.clear()
            github_api.update(deepcopy(original_api))
            github_api[part] = {"status": status, "conclusion": conclusion}
            refused = stable(tmp_path, checkout, upstream, "update", "--dry-run")
            assert refused.returncode != 0, case
            preview = json.loads(refused.stdout)
            assert preview["candidate"] == git(upstream, "rev-parse", "HEAD"), case
            assert preview["changed_files"] == "tracked", case
            assert preview["migrations"] == [], case
            assert preview["linux_ci"]["eligible"] is False, case
            assert "not automatically verified" in preview["local_verification"], case


def test_noncanonical_upstream_update_refuses_but_installed_restart_works(
    tmp_path,
    service_environment,
    github_api,
):
    upstream, checkout = application_pair(tmp_path)
    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    manifest = tmp_path / "stable/installation.json"
    installed = json.loads(manifest.read_text())
    installed["upstream"] = str(upstream)
    manifest.write_text(json.dumps(installed))
    old = git(checkout, "rev-parse", "HEAD")
    (upstream / "tracked").write_text("custom source\n")
    git(upstream, "commit", "-am", "Custom candidate")
    refused = stable(
        tmp_path, checkout, upstream, "update", "--yes", environment=service_environment
    )
    assert refused.returncode != 0
    assert "canonical github.com/dmclark/sayloom upstream" in refused.stderr
    restarted = stable(tmp_path, checkout, upstream, "restart", environment=service_environment)
    assert restarted.returncode == 0, restarted.stderr
    assert github_api["requests"] == []
    assert git(checkout, "rev-parse", "HEAD") == old


def test_lost_ci_after_stop_recovers_before_code_or_data_mutation(
    tmp_path,
    service_environment,
    github_api,
):
    upstream, checkout = application_pair(tmp_path)
    prepared = install(tmp_path, checkout, upstream, "--initialize", "--yes")
    assert prepared.returncode == 0, prepared.stderr
    started = stable(tmp_path, checkout, upstream, "start", environment=service_environment)
    assert started.returncode == 0, started.stderr
    old = git(checkout, "rev-parse", "HEAD")
    before = (tmp_path / "data.sqlite3").read_bytes()
    add_schema_release(upstream)
    github_api["lose_at"] = 3
    refused = stable(
        tmp_path, checkout, upstream, "update", "--yes", environment=service_environment
    )
    assert refused.returncode != 0
    assert "Previous Stable recovered; no database mutation occurred" in refused.stdout
    assert git(checkout, "rev-parse", "HEAD") == old
    assert (tmp_path / "data.sqlite3").read_bytes() == before
    assert not (tmp_path / "stable/maintenance.json").exists()
    status = stable(tmp_path, checkout, upstream, "status", environment=service_environment)
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


def test_default_launch_stop_and_offline_uninstall(tmp_path, service_environment):
    upstream, checkout = application_pair(tmp_path)
    home = tmp_path / "home"
    root = tmp_path / "stable"
    environment = {
        **os.environ,
        "HOME": str(home),
        **service_environment,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.{upstream}.insteadOf",
        "GIT_CONFIG_VALUE_0": CANONICAL,
    }
    port = (tmp_path / "port").read_text()

    def invoke(*arguments, input="", script=SCRIPT):
        return subprocess.run(
            [*controller_command(script), "--root", str(root), *arguments],
            env=environment,
            input=input,
            text=True,
            capture_output=True,
        )

    result = invoke("--port", port, "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    installed = json.loads((root / "installation.json").read_text())
    managed = home / ".local/share/local-text/stable-checkout"
    database = home / ".local/share/local-text/stable/local-text.sqlite3"
    assert installed["checkout"] == str(managed)
    assert installed["database"] == str(database)
    assert installed["managed_checkout"] is True
    assert git(managed, "rev-parse", "HEAD") == git(upstream, "rev-parse", "HEAD")
    assert installed["port"] == int(port)
    before = {
        path: path.read_bytes()
        for path in (
            database,
            Path(installed["configuration"]),
            root / "installation.json",
        )
    }
    state = tmp_path / f"synthetic-service-{installed['label']}.json"
    if state.exists():
        running = state.read_bytes()
    result = invoke(script=root / "stable.py")
    assert result.returncode == 0, result.stderr
    if state.exists():
        assert state.read_bytes() == running, "current healthy service must not restart"
    assert {path: path.read_bytes() for path in before} == before
    if state.exists():
        # A crashed process may leave a loaded registration with a stale PID.
        previous_pid = json.loads(state.read_text())["pid"]
        os.kill(previous_pid, signal.SIGTERM)
        result = invoke(script=root / "stable.py")
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(state.read_text())["pid"] != previous_pid
    result = invoke("stop", script=root / "stable.py")
    assert result.returncode == 0, result.stderr
    result = invoke("stop", script=root / "stable.py")
    assert result.returncode == 0, result.stderr
    result = invoke(script=root / "stable.py")
    assert result.returncode == 0, result.stderr

    # A later published release is prepared and activated by the same default command.
    (upstream / "tracked").write_text("second synthetic release\n")
    git(upstream, "commit", "-am", "Second synthetic release")
    previous_python = installed["python"]
    result = invoke("--yes", script=root / "stable.py")
    assert result.returncode == 0, result.stdout + result.stderr
    installed = json.loads((root / "installation.json").read_text())
    assert installed["commit"] == git(upstream, "rev-parse", "HEAD")
    assert installed["python"] != previous_python
    assert installed["service_arguments"][0] == installed["python"]
    if state.exists():
        assert json.loads(state.read_text())["arguments"] == installed["service_arguments"]
    result = invoke(script=root / "stable.py")
    assert result.returncode == 0, result.stderr

    # Keep unrelated commands and private backup material, even with broken dependencies.
    commands = Path(installed["raycast_directory"])
    unrelated = commands / "dev-unrelated.sh"
    unrelated.write_text("private unrelated command\n")
    changed = commands / "stable-open-sayloom.sh"
    changed.write_text("owner replacement\n")
    backup = root / "backups/retained"
    backup.parent.mkdir(exist_ok=True)
    backup.write_text("synthetic retained backup\n")
    shutil.rmtree(Path(installed["python"]).parent.parent)
    # Removing the source checkout also prevents an accidental fetch on teardown.
    shutil.rmtree(managed)
    result = invoke("uninstall", input="n\n", script=root / "stable.py")
    assert result.returncode != 0
    assert (root / "installation.json").exists()
    result = invoke("uninstall", "--yes", script=root / "stable.py")
    assert result.returncode == 0, result.stderr
    assert {path: path.read_bytes() for path in before if path != root / "installation.json"} == {
        path: contents for path, contents in before.items() if path != root / "installation.json"
    }
    assert not (root / "installation.json").exists()
    assert not (root / "stable").exists()
    assert not Path(installed["plist"]).exists()
    assert unrelated.read_text() == "private unrelated command\n"
    assert changed.read_text() == "owner replacement\n"
    assert backup.read_text() == "synthetic retained backup\n"
    assert sorted(p.name for p in commands.iterdir()) == [unrelated.name, changed.name]


@pytest.mark.parametrize("failure", ["ci", "decline", "partial", "prerequisite"])
def test_default_launch_refusal_preserves_data(tmp_path, service_environment, github_api, failure):
    upstream, checkout = application_pair(tmp_path)
    if failure == "ci":
        github_api["run"]["conclusion"] = "failure"
    if failure == "partial":
        (tmp_path / "stable").mkdir(mode=0o700)
        (tmp_path / "stable/stable.py").write_text("incomplete previous installation\n")
    environment = {**service_environment}
    if failure == "prerequisite":
        # Leave Python invocable by its absolute path, but remove required host commands.
        environment["PATH"] = str(tmp_path / "empty-bin")
    result = stable(
        tmp_path,
        checkout,
        upstream,
        "--upstream",
        CANONICAL,
        "--port",
        (tmp_path / "port").read_text(),
        input="n\n",
        environment=environment,
    )
    assert result.returncode != 0, result.stdout
    assert not (tmp_path / "home/.local/share/local-text/stable/local-text.sqlite3").exists()
    assert not (tmp_path / "home/.config/local-text/stable/environment.json").exists()
    if failure == "ci":
        assert "not completed successfully" in result.stderr
    elif failure == "partial":
        assert "incomplete installation" in result.stderr
        assert (tmp_path / "stable/stable.py").read_text() == "incomplete previous installation\n"
    elif failure == "prerequisite":
        assert "requires git on PATH" in result.stderr
    else:
        assert "not approved" in result.stderr


def publication_environment(upstream: Path, service_environment: dict) -> dict:
    return {
        **service_environment,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": f"url.{upstream}.insteadOf",
        "GIT_CONFIG_VALUE_0": CANONICAL,
    }


def test_repair_preserves_wal_data_and_rebuilds_damaged_artifacts(
    tmp_path, service_environment, github_api
):
    upstream, checkout = application_pair(tmp_path)
    assert install(tmp_path, checkout, upstream, "--initialize", "--yes").returncode == 0
    environment = publication_environment(upstream, service_environment)
    started = stable(tmp_path, checkout, upstream, "start", environment=environment)
    assert started.returncode == 0, started.stderr
    root = tmp_path / "stable"
    original = json.loads((root / "installation.json").read_text())
    configuration = Path(original["configuration"])
    config_before = configuration.read_bytes()
    with sqlite3.connect(original["database"]) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "INSERT INTO app_settings VALUES ('wal-survivor', '219', CURRENT_TIMESTAMP)"
        )
        connection.commit()
        assert Path(original["database"] + "-wal").exists()
        github_api["run"]["conclusion"] = "failure"
        refused = stable(tmp_path, checkout, upstream, "--repair", "--yes", environment=environment)
        assert refused.returncode != 0
        assert "not completed successfully" in refused.stderr
        assert json.loads((root / "installation.json").read_text()) == original
        github_api["run"].clear()
        (checkout / "tracked").write_text("owner changed checkout; must preserve\n")
        (root / "stable.py").write_text("damaged controller\n")
        shutil.rmtree(Path(original["python"]).parent.parent)
        shutil.rmtree(Path(original["raycast_directory"]))
        repaired = stable(
            tmp_path, checkout, upstream, "--repair", "--yes", environment=environment
        )
        assert repaired.returncode == 0, repaired.stdout + repaired.stderr
        installed = json.loads((root / "installation.json").read_text())
        assert installed["checkout"] != original["checkout"]
        assert installed["database"] == original["database"]
        assert (Path(installed["raycast_directory"]) / "stable-open-sayloom.sh").is_file()
        assert configuration.read_bytes() == config_before
        assert (checkout / "tracked").read_text() == "owner changed checkout; must preserve\n"
        assert connection.execute(
            "SELECT value_json FROM app_settings WHERE key = 'wal-survivor'"
        ).fetchone() == ("219",)
        record = json.loads((root / "last-update.json").read_text())
        with sqlite3.connect(record["backup"]) as backup:
            assert backup.execute(
                "SELECT value_json FROM app_settings WHERE key = 'wal-survivor'"
            ).fetchone() == ("219",)
            assert backup.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        preserved = Path(record["preservation"])
        assert (preserved / "controller.py").read_text() == "damaged controller\n"
        assert (preserved / "source.tar").is_file()
        assert (preserved / "configuration").stat().st_mode & 0o077 == 0


def test_confirmed_clean_install_keeps_original_and_can_return_to_it(tmp_path, service_environment):
    upstream, checkout = application_pair(tmp_path)
    assert install(tmp_path, checkout, upstream, "--initialize", "--yes").returncode == 0
    environment = publication_environment(upstream, service_environment)
    root = tmp_path / "stable"
    original = json.loads((root / "installation.json").read_text())
    database = Path(original["database"])
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO app_settings VALUES ('old-only', '73', CURRENT_TIMESTAMP)")
    before = {
        path: path.read_bytes()
        for path in (
            database,
            Path(original["configuration"]),
            root / "installation.json",
            root / "stable.py",
        )
    }
    refused = stable(
        tmp_path, checkout, upstream, "--clean-install", "--yes", environment=environment
    )
    assert refused.returncode != 0, refused.stdout
    assert "cancelled" in refused.stderr
    assert {path: path.read_bytes() for path in before} == before
    accepted = stable(
        tmp_path,
        checkout,
        upstream,
        "--clean-install",
        "--confirm-clean-install",
        environment=environment,
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    installed = json.loads((root / "installation.json").read_text())
    assert installed["database"] != original["database"]
    assert database.read_bytes() == before[database]
    assert Path(original["python"]).is_file()
    with sqlite3.connect(installed["database"]) as fresh:
        assert fresh.execute(
            "SELECT count(*) FROM app_settings WHERE key = 'old-only'"
        ).fetchone() == (0,)
    restored = stable(
        tmp_path, checkout, upstream, "--recovery", "previous", "--yes", environment=environment
    )
    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert json.loads((root / "installation.json").read_text())["database"] == original["database"]
    assert Path(installed["database"]).exists(), "fresh database must also be retained"


def test_backup_failure_prevents_replacement_and_recovers_previous(tmp_path, service_environment):
    upstream, checkout = application_pair(tmp_path)
    assert install(tmp_path, checkout, upstream, "--initialize", "--yes").returncode == 0
    root = tmp_path / "stable"
    original = json.loads((root / "installation.json").read_text())
    before = Path(original["database"]).read_bytes()
    (upstream / "tracked").write_text("candidate release\n")
    git(upstream, "commit", "-am", "Candidate release")
    (root / "backups").write_text("synthetic unavailable backup destination\n")
    result = stable(
        tmp_path, checkout, upstream, "update", "--yes", environment=service_environment
    )
    assert result.returncode != 0
    assert git(checkout, "rev-parse", "HEAD") == original["commit"]
    assert Path(original["database"]).read_bytes() == before
    assert not (root / "maintenance.json").exists()
    status = stable(tmp_path, checkout, upstream, "status", environment=service_environment)
    assert json.loads(status.stdout)["health"]["ready"]


def test_interrupted_update_requires_explicit_recovery(tmp_path, service_environment):
    if "SYNTHETIC_SERVICE" not in service_environment:
        pytest.skip("fault injection uses synthetic launchctl; native lane runs bounded lifecycle")
    upstream, checkout = application_pair(tmp_path)
    assert install(tmp_path, checkout, upstream, "--initialize", "--yes").returncode == 0
    assert (
        stable(tmp_path, checkout, upstream, "start", environment=service_environment).returncode
        == 0
    )
    root = tmp_path / "stable"
    original = json.loads((root / "installation.json").read_text())
    (upstream / "tracked").write_text("candidate release\n")
    git(upstream, "commit", "-am", "Candidate release")
    executable = tmp_path / "bin/launchctl"
    contents = executable.read_text()
    executable.write_text(
        contents.replace(
            "command = sys.argv[1]",
            "command = sys.argv[1]\n"
            "if command == 'bootout' and os.environ.get('SYNTHETIC_INTERRUPT') == '1':\n"
            "    os.kill(os.getppid(), signal.SIGKILL)\n"
            "    sys.exit(9)",
        )
    )
    interrupted = stable(
        tmp_path,
        checkout,
        upstream,
        "update",
        "--yes",
        environment={**service_environment, "SYNTHETIC_INTERRUPT": "1"},
    )
    assert interrupted.returncode == -signal.SIGKILL
    assert json.loads((root / "maintenance.json").read_text())["phase"] == "stopping"
    refused = stable(tmp_path, checkout, upstream, environment=service_environment)
    assert refused.returncode != 0
    assert "maintenance" in refused.stderr
    assert git(checkout, "rev-parse", "HEAD") == original["commit"]
    recovered = stable(
        tmp_path,
        checkout,
        upstream,
        "--recovery",
        "previous",
        "--yes",
        environment=service_environment,
    )
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    assert not (root / "maintenance.json").exists()


def test_populated_guard_refuses_without_mutation_and_clean_is_a_different_database(
    tmp_path, service_environment
):
    upstream, checkout = application_pair(tmp_path)
    assert install(tmp_path, checkout, upstream, "--initialize", "--yes").returncode == 0
    database = tmp_path / "data.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO personal_correction_profiles VALUES "
            "('local', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute("INSERT INTO app_settings VALUES ('keep', '219', CURRENT_TIMESTAMP)")
    before = database.read_bytes()
    add_schema_release(upstream)
    migration = upstream / "migrations/versions/0007_synthetic_release.py"
    migration.write_text(
        migration.read_text().replace(
            "def upgrade():\n",
            "def upgrade():\n"
            "    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM "
            "personal_correction_profiles')).scalar():\n"
            "        raise RuntimeError('Populated correction store: unsupported transition')\n",
        )
    )
    git(upstream, "commit", "-am", "Synthetic populated-store refusal, not the #204 schema")
    environment = publication_environment(upstream, service_environment)
    refused = stable(tmp_path, checkout, upstream, "update", "--yes", environment=environment)
    assert refused.returncode != 0
    assert database.read_bytes() == before
    assert git(checkout, "rev-parse", "HEAD") != git(upstream, "rev-parse", "HEAD")
    root = tmp_path / "stable"
    assert not (root / "maintenance.json").exists()
    clean = stable(
        tmp_path,
        checkout,
        upstream,
        "--clean-install",
        "--confirm-clean-install",
        environment=environment,
    )
    assert clean.returncode == 0, clean.stdout + clean.stderr
    fresh = json.loads((root / "installation.json").read_text())["database"]
    assert fresh != str(database)
    assert database.read_bytes() == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM personal_correction_profiles"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT value_json FROM app_settings WHERE key = 'keep'"
        ).fetchone() == ("219",)
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0006_confirmed_correction_batches",
        )
    with sqlite3.connect(fresh) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0007_synthetic_release",
        )


def protocol_one_mismatch(tmp_path: Path, service_environment: dict):
    """Three synthetic identities with the diagnosed contracts, never owner fixtures."""
    upstream, checkout = application_pair(tmp_path)
    controller = upstream / "scripts/stable.py"
    current = controller.read_text()
    legacy = current.replace("STABLE_PROTOCOL = 2", "STABLE_PROTOCOL = 1")
    prefix, rest = legacy.split("def configuration(path: Path) -> dict:\n", 1)
    _, suffix = rest.split("def environment(", 1)
    json_only = prefix + "def configuration(path: Path) -> dict:\n    return read_json(path)\n\n\n"
    json_only += "def environment(" + suffix
    controller.write_text(json_only)
    git(upstream, "commit", "-am", "Synthetic recorded protocol-1 application, JSON-only parser")
    git(checkout, "pull", "--ff-only")
    recorded = git(upstream, "rev-parse", "HEAD")
    external = tmp_path / "ordinary-terminal"
    external.mkdir()
    old = external / "old-controller.py"
    old.write_text(json_only)
    config = tmp_path / "environment.json"
    config.write_text("{}\n")
    config.chmod(0o600)
    environment = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        **publication_environment(upstream, service_environment),
    }
    root = tmp_path / "stable"
    prepared = subprocess.run(
        [
            *controller_command(old),
            "--root",
            str(root),
            "--checkout",
            str(checkout),
            "install",
            "--database",
            str(tmp_path / "data.sqlite3"),
            "--configuration",
            str(config),
            "--raycast-directory",
            str(tmp_path / "commands"),
            "--port",
            (tmp_path / "port").read_text(),
            "--reuse-existing",
            "--initialize",
            "--yes",
        ],
        env=environment,
        text=True,
        capture_output=True,
    )
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    controller.write_text(legacy)
    git(
        upstream, "commit", "-am", "Synthetic newer copied protocol-1 controller with legacy parser"
    )
    copied = git(upstream, "rev-parse", "HEAD")
    shutil.copyfile(controller, root / "stable.py")
    config = tmp_path / "environment"
    config.write_text("LOCAL_TEXT_OPENAI_MODEL='synthetic-preserved-model'\n")
    config.chmod(0o600)
    manifest = json.loads((root / "installation.json").read_text())
    manifest["configuration"] = str(config)
    # Protocol-1 did not persist generated-command ownership metadata.
    manifest.pop("commands", None)
    (root / "installation.json").write_text(json.dumps(manifest))

    def invoke(script, *arguments):
        return subprocess.run(
            [*controller_command(script), "--root", str(root), *arguments],
            env=environment,
            cwd=external,
            input="",
            text=True,
            capture_output=True,
        )

    older = invoke(old, "status")
    newer = invoke(root / "stable.py", "status")
    assert json.loads(older.stdout)["schema"]["state"] == "unknown"
    assert json.loads(newer.stdout)["schema"]["state"] == "current"
    started = invoke(root / "stable.py", "start")
    assert started.returncode == 0, started.stdout + started.stderr
    controller.write_text(current)
    git(upstream, "commit", "-am", "Synthetic protocol-2 target")
    target = git(upstream, "rev-parse", "HEAD")
    for script in (old, root / "stable.py"):
        refused = invoke(script, "update", "--yes")
        assert refused.returncode != 0
        assert "launcher protocol" in refused.stderr
    git(checkout, "pull", "--ff-only")
    assert manifest["commit"] == recorded
    assert recorded != copied != target
    assert not (root / "maintenance.json").exists()
    assert not (root / "last-update.json").exists()
    bootstrap = external / "stable-bootstrap.py"
    shutil.copyfile(REPOSITORY / "scripts/stable-bootstrap.py", bootstrap)
    # Use the same test-only GitHub API transport with the actual generated shell entry.
    (external / "sitecustomize.py").write_text(controller_command()[2].split("sys.argv =")[0])
    environment["PYTHONPATH"] = str(external)
    return upstream, checkout, root, external, bootstrap, environment, target


@pytest.mark.parametrize("checkout_damage", ["intact", "missing-git"])
def test_external_bootstrap_adopts_three_version_mismatch_then_launches_and_updates(
    tmp_path, service_environment, checkout_damage
):
    upstream, checkout, root, external, bootstrap, environment, target = protocol_one_mismatch(
        tmp_path, service_environment
    )
    original = {
        path: path.read_bytes()
        for path in (
            tmp_path / "environment",
            tmp_path / "data.sqlite3",
            root / "stable.py",
            root / "installation.json",
        )
    }
    command = [sys.executable, str(bootstrap), "--revision", target, "--root", str(root)]
    declined = subprocess.run(
        command, cwd=external, env=environment, input="n\n", text=True, capture_output=True
    )
    assert declined.returncode != 0, declined.stdout + declined.stderr
    assert {path: path.read_bytes() for path in original} == original
    if checkout_damage == "missing-git":
        shutil.rmtree(checkout / ".git")
    adopted = subprocess.run(
        [*command, "--yes"], cwd=external, env=environment, input="", text=True, capture_output=True
    )
    assert adopted.returncode == 0, adopted.stdout + adopted.stderr
    installed = json.loads((root / "installation.json").read_text())
    assert installed["protocol"] == 2
    assert installed["commit"] == target
    assert installed["checkout"] != str(checkout)
    assert (tmp_path / "environment").read_bytes() == original[tmp_path / "environment"]
    assert (tmp_path / "data.sqlite3").read_bytes() == original[tmp_path / "data.sqlite3"]
    preserved = Path(json.loads((root / "last-update.json").read_text())["preservation"])
    assert (preserved / "controller.py").read_bytes() == original[root / "stable.py"]
    assert (preserved / "installation.json").read_bytes() == original[root / "installation.json"]
    launched = subprocess.run(
        [str(root / "stable")],
        cwd=external,
        env=environment,
        input="",
        text=True,
        capture_output=True,
    )
    assert launched.returncode == 0, launched.stdout + launched.stderr
    (upstream / "tracked").write_text("subsequent synthetic release\n")
    git(upstream, "commit", "-am", "Subsequent release after adoption")
    updated = subprocess.run(
        [str(root / "stable"), "--yes"],
        cwd=external,
        env=environment,
        input="",
        text=True,
        capture_output=True,
    )
    assert updated.returncode == 0, updated.stdout + updated.stderr
    assert json.loads((root / "installation.json").read_text())["commit"] == git(
        upstream, "rev-parse", "HEAD"
    )
    launched = subprocess.run(
        [str(root / "stable")],
        cwd=external,
        env=environment,
        input="",
        text=True,
        capture_output=True,
    )
    assert launched.returncode == 0, launched.stdout + launched.stderr
    uninstalled = subprocess.run(
        [str(root / "stable"), "uninstall", "--yes"],
        cwd=external,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert uninstalled.returncode == 0, uninstalled.stdout + uninstalled.stderr


@pytest.mark.parametrize("boundary", ["before-replacement", "after-mutation"])
def test_bootstrap_interruption_preserves_original_and_has_explicit_recovery(
    tmp_path, service_environment, boundary
):
    if "SYNTHETIC_SERVICE" not in service_environment and boundary == "before-replacement":
        pytest.skip("pre-replacement kill injection uses synthetic launchctl")
    upstream, checkout, root, external, bootstrap, environment, target = protocol_one_mismatch(
        tmp_path, service_environment
    )
    before = json.loads((root / "installation.json").read_text())
    database = Path(before["database"])
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO app_settings VALUES ('survivor', '218', CURRENT_TIMESTAMP)")
    original_data = database.read_bytes()
    if boundary == "before-replacement":
        executable = tmp_path / "bin/launchctl"
        executable.write_text(
            executable.read_text().replace(
                "command = sys.argv[1]",
                "command = sys.argv[1]\n"
                "if command == 'bootout' and os.environ.get('SYNTHETIC_INTERRUPT') == '1':\n"
                "    os.kill(os.getppid(), signal.SIGKILL)\n    sys.exit(9)",
            )
        )
        failure = {**environment, "SYNTHETIC_INTERRUPT": "1"}
    else:
        add_schema_release(upstream)
        migration = upstream / "migrations/versions/0007_synthetic_release.py"
        migration.write_text(
            migration.read_text()
            .replace("import sqlalchemy as sa", "import os, signal\nimport sqlalchemy as sa")
            .replace(
                "nullable=True))",
                "nullable=True))\n"
                "    if op.get_bind().engine.url.database.endswith('data.sqlite3') and "
                "os.environ.get('SYNTHETIC_INTERRUPT') == '1':\n"
                "        os.kill(os.getppid(), signal.SIGKILL)",
            )
        )
        git(upstream, "commit", "-am", "Synthetic controller kill after live database mutation")
        target = git(upstream, "rev-parse", "HEAD")
        failure = {**environment, "SYNTHETIC_INTERRUPT": "1"}
    command = [sys.executable, str(bootstrap), "--revision", target, "--root", str(root)]
    interrupted = subprocess.run(
        [*command, "--yes"], cwd=external, env=failure, input="", text=True, capture_output=True
    )
    assert interrupted.returncode == -signal.SIGKILL, interrupted.stdout + interrupted.stderr
    record = json.loads((root / "maintenance.json").read_text())
    assert record["adoption"] is True
    assert json.loads((root / "installation.json").read_text()) == before
    assert git(checkout, "rev-parse", "HEAD") != before["commit"], (
        "mismatched checkout stays untouched"
    )
    blocked = subprocess.run(
        command, cwd=external, env=environment, input="", text=True, capture_output=True
    )
    assert blocked.returncode != 0
    assert "maintenance" in blocked.stderr
    if boundary == "before-replacement":
        assert record["data_mutated"] is False
        assert database.read_bytes() == original_data
        recovery = ["--recovery", "candidate", "--yes"]
    else:
        assert record["data_mutated"] is True
        with sqlite3.connect(database) as connection:
            assert "synthetic_note" in {
                row[1] for row in connection.execute("PRAGMA table_info(targets)")
            }
        refused = subprocess.run(
            [*command, "--recovery", "previous", "--yes"],
            cwd=external,
            env=environment,
            text=True,
            capture_output=True,
        )
        assert refused.returncode != 0
        assert "requires explicit --restore-backup" in refused.stderr
        recovery = ["--recovery", "previous", "--restore-backup", "--yes"]
    recovered = subprocess.run(
        [*command, *recovery],
        cwd=external,
        env=environment,
        input="",
        text=True,
        capture_output=True,
    )
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    assert not (root / "maintenance.json").exists()
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT value_json FROM app_settings WHERE key = 'survivor'"
        ).fetchone() == ("218",)
    if boundary == "after-mutation":
        assert json.loads((root / "installation.json").read_text())["protocol"] == 1
        retained = json.loads((root / "last-update.json").read_text())["before_restore"]
        assert Path(retained).exists()
        retried = subprocess.run(
            [*command, "--yes"],
            cwd=external,
            env=environment,
            input="",
            text=True,
            capture_output=True,
        )
        assert retried.returncode == 0, retried.stdout + retried.stderr
    installed = json.loads((root / "installation.json").read_text())
    assert installed["protocol"] == 2
    assert installed["commit"] == target
    # Retrying an already completed invocation must not create another transaction.
    backups = sorted((root / "backups").iterdir())
    repeated = subprocess.run(
        [*command, "--yes"], cwd=external, env=environment, input="", text=True, capture_output=True
    )
    assert repeated.returncode == 0, repeated.stdout + repeated.stderr
    assert sorted((root / "backups").iterdir()) == backups
    stopped = subprocess.run(
        [str(root / "stable"), "uninstall", "--yes"],
        cwd=external,
        env=environment,
        text=True,
        capture_output=True,
    )
    assert stopped.returncode == 0, stopped.stdout + stopped.stderr


@pytest.mark.parametrize(
    "reason", ["ci-unavailable", "unknown-protocol", "wrong-pin", "tampered-bootstrap"]
)
def test_bootstrap_refusal_does_not_interrupt_or_replace_original(
    tmp_path, service_environment, github_api, reason
):
    upstream, checkout, root, external, bootstrap, environment, target = protocol_one_mismatch(
        tmp_path, service_environment
    )
    if reason == "ci-unavailable":
        github_api["http_status"] = 503
    elif reason == "unknown-protocol":
        manifest = json.loads((root / "installation.json").read_text())
        manifest["protocol"] = 99
        (root / "installation.json").write_text(json.dumps(manifest))
    elif reason == "wrong-pin":
        target = "0" * 40
    else:
        bootstrap.write_text(bootstrap.read_text() + "\n# unreviewed modification\n")
    paths = [
        root / "installation.json",
        root / "stable.py",
        tmp_path / "data.sqlite3",
        tmp_path / "environment",
        *tmp_path.glob("synthetic-service-*.json"),
    ]
    original = {path: path.read_bytes() for path in paths}
    refused = subprocess.run(
        [sys.executable, str(bootstrap), "--revision", target, "--root", str(root), "--yes"],
        cwd=external,
        env=environment,
        input="",
        text=True,
        capture_output=True,
    )
    assert refused.returncode != 0
    assert {path: path.read_bytes() for path in original} == original
    assert not (root / "maintenance.json").exists()
    assert not (root / "last-update.json").exists()
    assert (
        git(checkout, "rev-parse", "HEAD")
        != json.loads((root / "installation.json").read_text())["commit"]
    )


def test_bootstrap_offers_confirmed_clean_install_after_populated_refusal(
    tmp_path, service_environment
):
    upstream, checkout, root, external, bootstrap, environment, _ = protocol_one_mismatch(
        tmp_path, service_environment
    )
    database = tmp_path / "data.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO personal_correction_profiles VALUES "
            "('local', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute("INSERT INTO app_settings VALUES ('keep', '218', CURRENT_TIMESTAMP)")
    before = database.read_bytes()
    add_schema_release(upstream)
    migration = upstream / "migrations/versions/0007_synthetic_release.py"
    migration.write_text(
        migration.read_text().replace(
            "def upgrade():\n",
            "def upgrade():\n"
            "    if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM "
            "personal_correction_profiles')).scalar():\n"
            "        raise RuntimeError('Populated correction store: unsupported transition')\n",
        )
    )
    git(upstream, "commit", "-am", "Synthetic populated refusal during adoption")
    target = git(upstream, "rev-parse", "HEAD")
    terminal, input_terminal = pty.openpty()
    try:
        process = subprocess.Popen(
            [sys.executable, str(bootstrap), "--revision", target, "--root", str(root)],
            cwd=external,
            env=environment,
            stdin=input_terminal,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        # Approve adoption, choose clean after its refusal, then confirm the reset.
        os.write(terminal, b"y\nc\ny\n")
        output, _ = process.communicate(timeout=180)
    finally:
        os.close(terminal)
        os.close(input_terminal)
    assert process.returncode == 0, output
    assert "clean installation [c]" in output
    assert "Previous interrupted transaction" in output
    assert not (root / "maintenance.json").exists()
    assert list((root / "backups").glob("*-transaction.json"))
    installed = json.loads((root / "installation.json").read_text())
    assert installed["database"] != str(database)
    assert installed["protocol"] == 2
    assert installed["commit"] == target
    assert database.read_bytes() == before
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM personal_correction_profiles"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT value_json FROM app_settings WHERE key = 'keep'"
        ).fetchone() == ("218",)
    assert git(checkout, "rev-parse", "HEAD") != target


def test_fresh_default_launch_rejects_checkout_movement_during_approval(
    tmp_path, service_environment
):
    upstream, checkout = application_pair(tmp_path)
    home = tmp_path / "home"
    root = tmp_path / "stable"
    environment = {
        **os.environ,
        "HOME": str(home),
        **publication_environment(upstream, service_environment),
    }
    output = tmp_path / "approval-output"
    with output.open("w") as transcript:
        process = subprocess.Popen(
            [
                *controller_command(),
                "--root",
                str(root),
                "--checkout",
                str(checkout),
                "--port",
                (tmp_path / "port").read_text(),
            ],
            env=environment,
            stdin=subprocess.PIPE,
            stdout=transcript,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.monotonic() + 20
        while "Install this exact Stable candidate" not in output.read_text():
            assert process.poll() is None, output.read_text()
            assert time.monotonic() < deadline, output.read_text()
            time.sleep(0.05)
        (upstream / "tracked").write_text("different, unreviewed candidate\n")
        git(upstream, "commit", "-am", "Move selected checkout during approval")
        git(checkout, "pull", "--ff-only")
        process.communicate(input="y\n", timeout=30)
    assert process.returncode != 0, output.read_text()
    assert "checkout differs from installed commit" in output.read_text()
    assert not (root / "installation.json").exists()
    assert not (home / ".local/share/local-text/stable/local-text.sqlite3").exists()
    assert not (home / ".config/local-text/stable/environment.json").exists()
