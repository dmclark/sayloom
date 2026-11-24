#!/usr/bin/env python3
"""Operate the separately installed Stable checkout; never manage development state."""

import argparse
import ast
import fcntl
import hashlib
import json
import os
import plistlib
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from contextlib import contextmanager
from http.client import HTTPException
from pathlib import Path
from urllib import error, request
from urllib.parse import urlencode

STABLE_PROTOCOL = 2
PORT = 7532
UPSTREAM = "https://github.com/dmclark/sayloom.git"
DEFAULT_ROOT = Path.home() / ".local/share/local-text/stable-runtime"
DEFAULT_CHECKOUT = Path.home() / ".local/share/local-text/stable-checkout"
DEFAULT_DATABASE = Path.home() / ".local/share/local-text/stable/local-text.sqlite3"
DEFAULT_CONFIGURATION = Path.home() / ".config/local-text/stable/environment.json"
CONFIGURATION_KEYS = {
    "LOCAL_TEXT_GEMINI_API_KEY",
    "LOCAL_TEXT_GEMINI_MODEL",
    "LOCAL_TEXT_GEMINI_QUOTA_GROUP_ID",
    "LOCAL_TEXT_OPENAI_API_KEY",
    "LOCAL_TEXT_OPENAI_MODEL",
    "LOCAL_TEXT_OPENAI_QUOTA_GROUP_ID",
    "LOCAL_TEXT_OPENROUTER_API_KEY",
    "LOCAL_TEXT_OPENROUTER_MODEL",
    "LOCAL_TEXT_OPENROUTER_MODELS",
    "LOCAL_TEXT_OPENROUTER_ENDPOINTS",
    "LOCAL_TEXT_CLEANUP_ROUTE_ORDER",
    "LOCAL_TEXT_CLEANUP_ROUTE_ATTEMPT_SECONDS",
    "LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS",
    "LOCAL_TEXT_CLEANUP_PAID_DATA_ACKNOWLEDGEMENT",
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(*arguments: str, cwd: Path | None = None, check: bool = True, **kwargs):
    return subprocess.run(
        arguments,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=True,
        timeout=kwargs.pop("timeout", 60),
        **kwargs,
    )


def git(checkout: Path, *arguments: str) -> str:
    return run("git", "-C", str(checkout), *arguments).stdout.rstrip("\n")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, value: dict) -> None:
    write_private(path, json.dumps(value, indent=2))


def write_private(path: Path, contents: str, mode: int = 0o600) -> None:
    temporary = path.with_suffix(".tmp")
    with open(
        temporary, "w", opener=lambda name, flags: os.open(name, flags | os.O_NOFOLLOW, mode)
    ) as output:
        os.fchmod(output.fileno(), mode)
        output.write(contents)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def locked(root: Path):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        fail("Stable runtime directory must be private (0700) and not a symlink")
    with open(
        root / "operation.lock",
        "a+",
        opener=lambda name, flags: os.open(name, flags | os.O_NOFOLLOW, 0o600),
    ) as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("another Stable lifecycle operation is active")
        yield


def configuration(path: Path) -> dict:
    if path.is_symlink() or path.stat().st_mode & 0o077:
        fail("Stable configuration must be a regular private file (0600)")
    try:
        values = read_json(path)
    except json.JSONDecodeError:
        if path.name != "environment":
            raise
        # Legacy Stable used literal shell assignments. Never source the file:
        # substitutions, commands, duplicate keys and unknown settings are refused.
        values = {}
        for number, line in enumerate(path.read_text().splitlines(), 1):
            lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            words = list(lexer)
            if words and words[0] == "export":
                words = words[1:]
            if not words:
                continue
            if len(words) != 1 or "=" not in words[0]:
                fail(f"legacy Stable configuration requires literal assignments (line {number})")
            key, value = words[0].split("=", 1)
            if key in values or key not in CONFIGURATION_KEYS or "$" in value or "`" in value:
                fail(f"unsupported legacy Stable configuration assignment (line {number})")
            values[key] = value
    if not isinstance(values, dict) or any(
        key not in CONFIGURATION_KEYS or not isinstance(value, str) for key, value in values.items()
    ):
        fail("Stable configuration accepts only documented provider/model string settings")
    return values


def environment(installed: dict, source: Path, database: Path | None = None) -> dict:
    values = {
        key: value
        for key, value in os.environ.items()
        if (not key.startswith(("LOCAL_TEXT_", "UV_", "PYTHON", "PYTEST_")) or key == "UV_OFFLINE")
        and key not in {
            "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
            "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN",
        }
    }
    values.update(configuration(Path(installed["configuration"])))
    values.update(
        LOCAL_TEXT_PROFILE="release",
        PYTHONPATH=str(source / "src"),
        LOCAL_TEXT_DATABASE_PATH=str(database or installed["database"]),
        LOCAL_TEXT_RAYCAST_DIRECTORY=installed["raycast_directory"],
        LOCAL_TEXT_PORT=str(installed.get("port", PORT)),
        PYTHONDONTWRITEBYTECODE="1",
    )
    return values


def load_installation(root: Path) -> dict:
    if not (root / "installation.json").is_file():
        fail("Stable is not installed; use install to review defaults or select external paths")
    installed = read_json(root / "installation.json")
    if type(installed["protocol"]) is not int or installed["protocol"] not in {1, STABLE_PROTOCOL}:
        fail("unsupported Stable installation protocol")
    return installed


def require_idle(root: Path) -> None:
    if (root / "maintenance.json").exists():
        fail(f"Stable is in maintenance; inspect {root / 'maintenance.json'} and use recover")


def require_checkout(installed: dict) -> None:
    checkout = Path(installed["checkout"])
    if git(checkout, "branch", "--show-current") != "main":
        fail(
            "Stable checkout must be on main; run from Stable's main checkout or select --checkout"
        )
    if git(checkout, "rev-parse", "HEAD") != installed["commit"]:
        fail("checkout differs from installed commit; do not pull Stable manually")
    if git(checkout, "status", "--porcelain", "--untracked-files=no"):
        fail("Stable has tracked changes; refusing to stash or discard them")


def probe(installed: dict, source: Path, database: Path | None = None) -> dict:
    script = """
import json
from dataclasses import asdict
from pathlib import Path
from alembic.script import ScriptDirectory
from local_text.config import load_settings
from local_text.database import ApplicationDatabase, SCHEMA_REVISION
graph = ScriptDirectory(str(Path.cwd() / 'migrations'))
assert graph.get_heads() == [SCHEMA_REVISION], 'migration head and runtime schema disagree'
status = ApplicationDatabase(load_settings().resolved_database_path).schema_status()
pending = list(graph.iterate_revisions(SCHEMA_REVISION, status.current_revision))
print(json.dumps({**asdict(status), 'migrations': [r.revision for r in reversed(pending)]}))
"""
    return json.loads(
        run(
            installed["python"],
            "-c",
            script,
            cwd=source,
            env=environment(installed, source, database),
        ).stdout
    )


def admin(installed: dict, source: Path, operation: str, database: Path | None = None) -> None:
    run(
        installed["python"],
        "-m",
        "local_text.admin",
        operation,
        cwd=source,
        env=environment(installed, source, database),
    )


def validate_application(installed: dict, source: Path) -> None:
    run(
        installed["python"],
        "-c",
        "from local_text.app import create_app; "
        "app = create_app(); assert app.title == 'Sayloom'; "
        "from fastapi.testclient import TestClient; "
        "response = TestClient(app).get('/health'); "
        "assert response.status_code == 200 and response.json()['profile'] == 'release'",
        cwd=source,
        env=environment(installed, source),
    )


def prepare_environment(root: Path, installed: dict, source: Path) -> dict:
    destination = root / "environments" / uuid.uuid4().hex
    values = environment(installed, source)
    values["UV_PROJECT_ENVIRONMENT"] = str(destination)
    run(
        "uv",
        "sync",
        "--locked",
        "--no-editable",
        "--python",
        installed.get("python", sys.executable),
        "--project",
        str(source),
        env=values,
        timeout=300,
    )
    prepared = {**installed, "python": str(destination / "bin/python")}
    if "service_arguments" in prepared:
        prepared["service_arguments"] = [prepared["python"], *installed["service_arguments"][1:]]
    return prepared


def service_target(installed: dict) -> str:
    return f"gui/{os.getuid()}/{installed['label']}"


def service_status(root: Path, installed: dict) -> dict:
    if not shutil.which("launchctl"):
        return {"state": "unavailable", "owned": False, "pid": None}
    result = run("launchctl", "print", service_target(installed), check=False)
    if result.returncode:
        return {"state": "stopped", "owned": False, "pid": None}
    # Check the loaded arguments, not just the on-disk plist or a health response.
    lines = [line.strip() for line in result.stdout.splitlines()]
    if "arguments = {" not in lines:
        return {"state": "loaded", "owned": False, "pid": None}
    arguments = lines[lines.index("arguments = {") + 1 :]
    arguments = arguments[: arguments.index("}")]
    owned = arguments == installed["service_arguments"]
    pid = next(
        (
            int(line.strip().split(" = ", 1)[1])
            for line in result.stdout.splitlines()
            if line.strip().startswith("pid = ")
        ),
        None,
    )
    return {"state": "loaded", "owned": owned, "pid": pid}


def require_free_port(port: int) -> None:
    import socket

    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            fail(f"Stable port {port} is occupied; refusing to stop an unverified listener")


def listener_pids(port: int) -> set[str]:
    result = run("lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t", check=False)
    if result.returncode not in {0, 1}:
        fail("could not verify Stable listener ownership")
    return set(result.stdout.split())


def stop_service(root: Path, installed: dict) -> None:
    port = installed.get("port", PORT)
    state = service_status(root, installed)
    if state["state"] == "unavailable":
        fail("launchctl is required for Stable lifecycle operations")
    listeners = listener_pids(port)
    if listeners and (not state["owned"] or listeners != {str(state["pid"])}):
        fail(f"Stable port {port} has an unverified listener; no service was stopped")
    if state["state"] == "loaded":
        if not state["owned"]:
            fail("loaded Stable service does not belong to this installation")
        run("launchctl", "bootout", service_target(installed))
    for _ in range(30):
        try:
            require_free_port(port)
            if service_status(root, installed)["state"] == "stopped":
                return
        except RuntimeError:
            pass
        time.sleep(0.1)
    fail("Stable service did not finish unloading; no replacement was started")


def write_plist(root: Path, installed: dict, previous: dict | None = None) -> Path:
    plist = Path(installed["plist"])
    plist.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if plist.exists():
        existing = plistlib.loads(plist.read_bytes())
        if existing.get("ProgramArguments") not in (
            installed["service_arguments"],
            (previous or installed)["service_arguments"],
        ):
            fail("refusing to replace an unmanaged LaunchAgent")
    content = {
        "Label": installed["label"],
        "ProgramArguments": installed["service_arguments"],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": str(root / "service.log"),
        "StandardErrorPath": str(root / "service-error.log"),
    }
    temporary = plist.with_suffix(".tmp")
    temporary.write_bytes(plistlib.dumps(content))
    temporary.chmod(0o600)
    temporary.replace(plist)
    return plist


def start_service(root: Path, installed: dict) -> None:
    port = installed.get("port", PORT)
    state = service_status(root, installed)
    if state["state"] == "loaded":
        if not state["owned"]:
            fail("loaded Stable service does not belong to this installation")
        if state["pid"]:
            if health(port)["ready"]:
                if listener_pids(port) == {str(state["pid"])}:
                    return
            fail("Stable is running but not healthy; inspect status before restart")
        run("launchctl", "bootout", service_target(installed))
    require_free_port(port)
    plist = write_plist(root, installed)
    run("launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist))
    for _ in range(30):
        state = service_status(root, installed)
        if state["owned"] and state["pid"] and health(port)["ready"]:
            # The listening PID must be the launched uvicorn process, not another release app.
            if listener_pids(port) == {str(state["pid"])}:
                return
        time.sleep(1)
    fail(f"Stable did not become healthy; inspect {root / 'service-error.log'}")


def launch(root: Path, installed: dict) -> None:
    if (root / "maintenance.json").exists():
        record = read_json(root / "maintenance.json")
        if (
            record.get("phase") != "activating"
            or record.get("launch_commit") != installed["commit"]
        ):
            require_idle(root)
        # Only a live, lock-holding activation may pass the persistent maintenance guard.
        with (root / "operation.lock").open() as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                fail("interrupted activation; use recover before starting Stable")
    require_checkout(installed)
    source = Path(installed["checkout"])
    validate_application(installed, source)
    os.execve(
        installed["python"],
        [
            installed["python"],
            "-m",
            "uvicorn",
            "local_text.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(installed.get("port", PORT)),
        ],
        environment(installed, source),
    )


def raycast_commands(installed: dict, source: Path) -> dict:
    script = """
import json
from pathlib import Path
from local_text.config import Profile, load_settings
from local_text.database import ApplicationDatabase
from local_text.target_store import TargetStore
from local_text.targets import INITIAL_TARGETS, command_filename, generate_command
database = ApplicationDatabase(Path(__import__('os').environ['LOCAL_TEXT_DATABASE_PATH']))
if database.path.exists():
    database.assert_ready()
    definitions = [(t.id, t.definition) for t in TargetStore(database).list() if t.enabled]
else:
    definitions = INITIAL_TARGETS
print(json.dumps({command_filename(key, Profile.RELEASE):
                 generate_command(key, value, Profile.RELEASE, port=load_settings().port).content
                 for key, value in definitions}))
"""
    commands = json.loads(
        run(
            installed["python"], "-c", script, cwd=source, env=environment(installed, source)
        ).stdout
    )
    endpoint = f"http://127.0.0.1:{installed.get('port', PORT)}"
    commands["stable-open-sayloom.sh"] = (
        (source / "raycast/stable/open-sayloom.sh")
        .read_text()
        .replace("http://127.0.0.1:7532", endpoint)
    )
    for name, contents in commands.items():
        if (
            Path(name).name != name
            or endpoint not in contents
            or "http://127.0.0.1:7523" in contents
            or "/health" not in contents
        ):
            fail("candidate Raycast commands do not implement the Stable endpoint contract")
        run("/bin/sh", "-n", input=contents)
    return commands


def require_command_destinations(directory: Path, commands: dict) -> None:
    for name, contents in commands.items():
        destination = directory / name
        if (
            destination.is_symlink()
            or destination.exists()
            and (not destination.is_file() or destination.read_text() != contents)
        ):
            fail("refusing to replace an existing Raycast entry; review the command collision")


def command_entry(root: Path, installed: dict) -> str:
    # The administrative controller must survive a damaged application environment.
    return (
        "#!/bin/sh\nexec "
        + shlex.join(
            [
                installed.get("controller_python", installed["python"]),
                str(root / "stable.py"),
                "--root",
                str(root),
            ]
        )
        + ' "$@"\n'
    )


def install(root: Path, arguments: argparse.Namespace) -> None:
    require_idle(root)
    if (root / "installation.json").exists():
        installed = load_installation(root)
        for option in ("database", "configuration", "raycast_directory"):
            selected = getattr(arguments, option)
            if selected is not None and selected.expanduser().resolve() != Path(installed[option]):
                fail("Stable is already installed; refusing changed paths; use status/update")
        if arguments.port is not None and arguments.port != installed.get("port", PORT):
            fail("Stable is already installed; refusing changed port; use status/update")
        if arguments.initialize:
            fail("--initialize cannot be used with an existing installation")
        print(f"Existing Stable installation: {root}; configuration: {installed['configuration']}")
        if arguments.reuse_existing or (
            not arguments.yes and confirm("Use this installation unchanged?", False)
        ):
            print("Using existing Stable unchanged. Use start or status; no files were replaced.")
            return
        fail("Stable already exists; use --reuse-existing to retain it, or status/update")
    for reserved in ("stable.py", "stable", "environments", "backups"):
        path = root / reserved
        if path.exists() or path.is_symlink():
            fail(f"refusing to replace unmanaged Stable runtime path: {reserved}")
    checkout = arguments.checkout.expanduser().resolve()
    if not checkout.is_dir():
        fail(
            "Stable checkout directory does not exist; --checkout expects a path, not a branch name"
        )
    database = (arguments.database or DEFAULT_DATABASE).expanduser().resolve()
    config_path = (arguments.configuration or DEFAULT_CONFIGURATION).expanduser()
    legacy = config_path.with_name("environment")
    if (
        arguments.configuration is None
        and not config_path.exists()
        and not config_path.is_symlink()
        and (legacy.exists() or legacy.is_symlink())
    ):
        config_path = legacy
    if config_path.is_symlink():
        fail("Stable configuration must not be a symlink")
    config = config_path.resolve()
    command_directory = (
        (arguments.raycast_directory or Path.home() / ".config/raycast/scripts")
        .expanduser()
        .resolve()
    )
    for private in (root, database, config, command_directory):
        if private.is_relative_to(checkout):
            fail(
                "Stable runtime, database, configuration, and commands must be outside the checkout"
            )
    print(f"Database: {database}\nConfiguration: {config}\nRaycast directory: {command_directory}")
    if config.exists():
        configuration(config)
    elif arguments.configuration is not None:
        fail("explicit configuration file is missing; create a private JSON file first")
    if not database.exists() and not arguments.initialize:
        fail("database is missing; explicit install --initialize is required")
    if arguments.initialize and database.exists():
        fail("--initialize is only for a new database; existing data requires explicit review")
    commit = getattr(arguments, "pinned_commit", None) or git(checkout, "rev-parse", "HEAD")
    port = arguments.port if arguments.port is not None else PORT
    if not 1024 <= port <= 65535 or port == 7523:
        fail("Stable port must be between 1024 and 65535 and not development port 7523")
    label = "local.local-text.stable." + hashlib.sha256(str(root).encode()).hexdigest()[:12]
    installed = {
        "protocol": STABLE_PROTOCOL,
        "controller_python": str(Path(sys.executable).resolve()),
        "commit": commit,
        "port": port,
        "checkout": str(checkout),
        "upstream": arguments.upstream,
        "database": str(database),
        "configuration": str(config),
        "raycast_directory": str(command_directory),
        "label": label,
        "plist": str(Path.home() / "Library/LaunchAgents" / f"{label}.plist"),
    }
    if (database.exists() or config.exists()) and not arguments.reuse_existing:
        if arguments.yes:
            fail("existing files preserved; review paths and select --reuse-existing to use them")
        if not confirm("Reuse these existing Stable files unchanged?", False):
            print("Existing Stable files preserved; installation cancelled.")
            return
    require_checkout(installed)
    controller = git(checkout, "show", f"{commit}:scripts/stable.py")
    if assignment(controller, "STABLE_PROTOCOL") != STABLE_PROTOCOL:
        fail(
            "Stable installation requires port-aware source with launcher protocol "
            f"{STABLE_PROTOCOL}"
        )
    if not getattr(arguments, "preparing_replacement", False):
        require_free_port(port)
    if not confirm("Prepare Stable installation (does not start it)?", arguments.yes):
        return
    if not config.exists():
        config.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Exclusive creation must never replace an existing provider configuration.
        with open(config, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
            output.write("{}\n")
        print("Created empty provider configuration; external cleanup is not enabled.")
    require_checkout(installed)
    installed = prepare_environment(root, installed, checkout)
    require_checkout(installed)
    installed["service_arguments"] = [
        installed["python"],
        str(root / "stable.py"),
        "--root",
        str(root),
        "serve",
    ]
    commands = raycast_commands(installed, checkout)
    command_directory = Path(installed["raycast_directory"])
    require_command_destinations(command_directory, commands)
    if not arguments.initialize:
        validate_application(installed, checkout)
    require_checkout(installed)
    shutil.copyfile(checkout / "scripts/stable.py", root / "stable.py")
    os.chmod(root / "stable.py", 0o700)
    entry = root / "stable"
    entry.write_text(command_entry(root, installed))
    entry.chmod(0o700)
    write_plist(root, installed)
    command_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, contents in commands.items():
        destination = command_directory / name
        destination.write_text(contents)
        destination.chmod(0o700)
    installed["commands"] = commands
    write_json(root / "installation.json", installed)
    if arguments.initialize:
        write_json(
            root / "maintenance.json",
            {
                "phase": "initializing",
                "initialization": True,
                "previous": installed,
                "candidate": installed,
                "backup": None,
                "data_mutated": True,
            },
        )
        admin(installed, checkout, "migrate")
        admin(installed, checkout, "seed")
        validate_application(installed, checkout)
    (root / "maintenance.json").unlink(missing_ok=True)
    print("Prepared Stable; not started. Use start after reviewing status.")


def confirm(message: str, yes: bool) -> bool:
    if yes:
        return True
    try:
        return input(message + " [y/N] ").strip().lower() == "y"
    except EOFError:
        return False


def assignment(source: str, name: str):
    for node in ast.parse(source).body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
            or isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            return ast.literal_eval(node.value)
    fail(f"candidate does not declare {name}")


def database_revision(path: Path) -> str:
    if not path.is_file():
        fail("Stable database is missing; refusing to initialize during update/restart")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
    if len(rows) != 1:
        fail("Stable requires one recognized schema revision")
    return rows[0][0]


def require_no_collisions(checkout: Path, target: str) -> None:
    current = set(git(checkout, "ls-files", "-z").split("\0"))
    added = set(git(checkout, "ls-tree", "-r", "--name-only", "-z", target).split("\0")) - current
    untracked = git(checkout, "ls-files", "--others", "-z").split("\0")
    for path in filter(None, untracked):
        if any(
            path == name or path.startswith(name + "/") or name.startswith(path + "/")
            for name in added
        ):
            fail("candidate collides with untracked files; refusing to overwrite them")


def update_plan(installed: dict, candidate: str, seed: bool, *, rebuilding: bool = False) -> dict:
    checkout = Path(installed["checkout"])
    if not rebuilding:
        require_checkout(installed)
        require_no_collisions(checkout, candidate)
    controller = git(checkout, "show", f"{candidate}:scripts/stable.py")
    if assignment(controller, "STABLE_PROTOCOL") != STABLE_PROTOCOL:
        fail("candidate launcher protocol requires a separately reviewed installation")
    changed = git(
        checkout,
        "diff",
        "--name-status",
        "--no-renames",
        installed["commit"],
        candidate,
        "--",
        "migrations",
    ).splitlines()
    if any(not change.startswith("A\t") for change in changed):
        fail("candidate modifies historical migrations; explicit review is required")
    current = database_revision(Path(installed["database"]))
    target = assignment(
        git(checkout, "show", f"{candidate}:src/local_text/database.py"), "SCHEMA_REVISION"
    )
    migrations = {}
    for filename in git(
        checkout, "ls-tree", "-r", "--name-only", candidate, "--", "migrations/versions"
    ).splitlines():
        if filename.endswith(".py"):
            contents = git(checkout, "show", f"{candidate}:{filename}")
            revision = assignment(contents, "revision")
            predecessor = assignment(contents, "down_revision")
            if (
                not isinstance(revision, str)
                or not revision
                or (predecessor is not None and not isinstance(predecessor, str))
            ):
                fail("candidate requires a separately reviewed non-linear migration graph")
            if revision in migrations:
                fail("duplicate candidate migration revision")
            migrations[revision] = predecessor
    pending = []
    cursor = target
    while cursor != current:
        if cursor not in migrations or cursor in pending:
            fail("database revision is not an ancestor of candidate; no downgrade is allowed")
        pending.append(cursor)
        cursor = migrations[cursor]
    if current not in migrations or set(migrations.values()) - {None} - set(migrations):
        fail("candidate migration graph is incomplete")
    heads = set(migrations) - set(migrations.values())
    if heads != {target}:
        fail("candidate has unsupported migration branches")
    return {
        "installed_commit": installed["commit"],
        "candidate": candidate,
        "current_revision": current,
        "target_revision": target,
        "migrations": list(reversed(pending)),
        "migration_files": changed,
        "seed": seed,
        "commits": git(checkout, "log", "--format=%h %s", f"{installed['commit']}..{candidate}"),
        "changed_files": git(checkout, "diff", "--name-only", installed["commit"], candidate),
        "dependency_preparation": "not run",
        "migration_rehearsal": "not run",
        "warning": "Review migration files for data loss. Database restore is never automatic.",
    }


@contextmanager
def candidate_source(root: Path, checkout: Path, candidate: str):
    with tempfile.TemporaryDirectory(prefix="candidate-", dir=root) as directory:
        archive = Path(directory) / "source.tar"
        git(checkout, "archive", "--format=tar", f"--output={archive}", candidate)
        source = Path(directory) / "source"
        source.mkdir()
        with tarfile.open(archive) as bundle:
            bundle.extractall(source, filter="data")
        yield source


def backup_database(root: Path, database: Path) -> Path:
    destination = root / "backups" / f"{time.time_ns()}.sqlite3"
    destination.parent.mkdir(mode=0o700, exist_ok=True)
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(destination) as backup:
            source.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                fail("SQLite backup integrity verification failed")
    destination.chmod(0o600)
    if database_revision(destination) != database_revision(database):
        fail("SQLite backup revision verification failed")
    return destination


def backup_installation(
    root: Path, installed: dict, record: dict, source_checkout: Path | None = None
) -> None:
    destination = root / "backups" / f"{time.time_ns()}-installation"
    destination.mkdir(mode=0o700, parents=True)
    record["preservation"] = str(destination)
    progress(root, record, "backing_up")
    record["backup"] = str(backup_database(root, Path(installed["database"])))
    checkout = source_checkout or Path(installed["checkout"])
    archive = destination / "source.tar"
    git(checkout, "archive", "--format=tar", f"--output={archive}", installed["commit"])
    archive.chmod(0o600)
    # A tar is obtainable source even if the checkout or remote later disappears.
    with tarfile.open(archive) as source:
        if not source.getmember("scripts/stable.py").isfile():
            fail("backup does not contain the installed controller source")
    bundle = destination / "source.bundle"
    git(checkout, "bundle", "create", str(bundle), "--all")
    bundle.chmod(0o600)
    git(checkout, "bundle", "verify", str(bundle))
    files = {
        "installation.json": root / "installation.json",
        "controller.py": root / "stable.py",
        "stable": root / "stable",
        "launch.plist": Path(installed["plist"]),
        "configuration": Path(installed["configuration"]),
    }
    for name, path in files.items():
        if path.is_symlink():
            fail(f"cannot preserve symlinked installation artifact: {name}")
        if path.is_file():
            shutil.copyfile(path, destination / name)
            (destination / name).chmod(0o600)
    runtime = Path(installed["python"]).parent.parent
    if runtime.is_dir() and (runtime / "pyvenv.cfg").is_file():
        shutil.copytree(runtime, destination / "environment", symlinks=True)
        (destination / "environment").chmod(0o700)
        run(
            str(destination / "environment/bin/python"), "-c", "import alembic, fastapi, sqlalchemy"
        )
    try:
        original_head = git(Path(installed["checkout"]), "rev-parse", "HEAD")
    except subprocess.SubprocessError:
        original_head = None
    metadata = {
        "installation": installed,
        "schema": database_revision(Path(record["backup"])),
        "database_backup": record["backup"],
        "checkout_commit": original_head,
        "source_commit": installed["commit"],
        "retained_environment": installed["python"],
        "sha256": {
            str(path.relative_to(destination)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in destination.rglob("*")
            if path.is_file() and not path.is_symlink()
        },
    }
    write_json(destination / "recovery.json", metadata)
    verify_preservation(destination)
    print(f"Private recovery material retained: {destination}; database: {record['backup']}")


def verify_preservation(destination: Path) -> dict:
    metadata = read_json(destination / "recovery.json")
    for name, expected in metadata["sha256"].items():
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != expected:
            fail("retained installation backup failed integrity verification")
    return metadata


@contextmanager
def preparing(root: Path, record: dict):
    progress(root, record, "preparing")
    try:
        yield
    except BaseException:
        if (root / "maintenance.json").exists() and read_json(root / "maintenance.json").get(
            "phase"
        ) == "preparing":
            # Ordinary preparation failure leaves the old runtime untouched. A killed
            # controller leaves this durable marker for explicit recovery instead.
            (root / "maintenance.json").unlink()
        raise


def progress(root: Path, record: dict, phase: str) -> None:
    record["phase"] = phase
    write_json(root / "maintenance.json", record)


def activate(root: Path, installed: dict, record: dict, controller: Path | None = None) -> None:
    record["launch_commit"] = installed["commit"]
    progress(root, record, "activating")
    previous = load_installation(root)
    commands = raycast_commands(installed, Path(installed["checkout"]))
    directory = Path(installed["raycast_directory"])
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, contents in commands.items():
        path = directory / name
        if path.exists() and (
            path.is_symlink()
            or path.read_text() not in (contents, previous.get("commands", {}).get(name))
        ):
            fail("changed/unowned command collision; repair cannot overwrite owner files")
    for name, contents in commands.items():
        path = directory / name
        path.write_text(contents)
        path.chmod(0o700)
    installed["commands"] = commands
    write_plist(root, installed, previous)
    write_private(
        root / "stable.py",
        (controller or Path(installed["checkout"]) / "scripts/stable.py").read_text(),
        0o700,
    )
    write_private(root / "stable", command_entry(root, installed), 0o700)
    write_json(root / "installation.json", installed)
    start_service(root, installed)
    record["phase"] = "completed"
    write_json(root / "last-update.json", record)
    (root / "maintenance.json").unlink()


def linux_ci(upstream: str, candidate: str) -> dict:
    """Public, credential-free evidence only; never execute candidate code here."""
    result = {"eligible": False, "candidate": candidate}
    if upstream not in {
        UPSTREAM,
        "https://github.com/dmclark/sayloom",
        "git@github.com:dmclark/sayloom.git",
        "ssh://git@github.com/dmclark/sayloom.git",
    }:
        return {
            **result,
            "blocker": "updates require the canonical github.com/dmclark/sayloom upstream",
        }
    api = "https://api.github.com/repos/dmclark/sayloom"
    repository = "https://github.com/dmclark/sayloom"

    def require(condition: bool) -> None:
        if not condition:
            fail("Linux CI provenance or response could not be verified")

    def get(path: str) -> dict:
        url = api + path
        with request.urlopen(
            request.Request(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "sayloom-stable",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            ),
            timeout=20,
        ) as response:
            require(response.status == 200 and response.geturl() == url)
            payload = response.read(4_000_001)
            require(len(payload) <= 4_000_000)
            length = response.headers.get("Content-Length")
            require(length is None or int(length) == len(payload))
            value = json.loads(payload)
            require(isinstance(value, dict))
            return value

    def pages(path: str, key: str) -> list:
        items = []
        total = None
        for page in range(1, 11):
            separator = "&" if "?" in path else "?"
            value = get(f"{path}{separator}per_page=100&page={page}")
            count = value["total_count"]
            require(type(count) is int and 0 <= count <= 1000)
            require(total is None or total == count)
            total = count
            batch = value[key]
            require(isinstance(batch, list) and len(batch) <= 100)
            items.extend(batch)
            if len(items) == total:
                return items
            require(bool(batch) and len(items) < total)
        fail("Linux CI pagination could not be verified")

    def provenance(run: dict, workflow: dict) -> None:
        require(
            run["head_sha"] == candidate
            and run["head_branch"] == "main"
            and run["event"] == "push"
            and run["path"] == ".github/workflows/ci.yml"
            and run["workflow_id"] == workflow["id"]
            and run["workflow_url"] == workflow["url"]
        )
        for key in ("repository", "head_repository"):
            repo = run[key]
            require(
                repo["full_name"] == "dmclark/sayloom"
                and repo["html_url"] == repository
                and repo["url"] == api
                and repo["fork"] is False
            )
        require(
            type(run["id"]) is int
            and run["id"] > 0
            and type(run["run_number"]) is int
            and run["run_number"] > 0
            and type(run["run_attempt"]) is int
            and run["run_attempt"] > 0
        )
        require(
            run["url"] == f"{api}/actions/runs/{run['id']}"
            and run["html_url"] == f"{repository}/actions/runs/{run['id']}"
        )

    try:
        workflow = get("/actions/workflows/ci.yml")
        require(
            type(workflow["id"]) is int
            and workflow["id"] > 0
            and workflow["path"] == ".github/workflows/ci.yml"
            and workflow["url"] == f"{api}/actions/workflows/{workflow['id']}"
            and workflow["html_url"] == f"{repository}/actions/workflows/ci.yml"
            and workflow["state"] == "active"
        )
        query = urlencode({"head_sha": candidate, "branch": "main", "event": "push"})
        path = f"/actions/workflows/{workflow['id']}/runs?{query}"

        def latest() -> dict:
            runs = pages(path, "workflow_runs")
            require(len({run["id"] for run in runs}) == len(runs))
            for run in runs:
                provenance(run, workflow)
            if not runs:
                fail("no exact-commit main push Linux CI run exists")
            return max(runs, key=lambda run: (run["run_number"], run["id"]))

        run = latest()
        # The list may lag a rerun; read the run itself before selecting its attempt.
        current = get(f"/actions/runs/{run['id']}")
        provenance(current, workflow)
        require(current["run_attempt"] >= run["run_attempt"])
        run = current
        result.update(run_id=run["id"], attempt=run["run_attempt"], url=run["html_url"])
        if run["status"] != "completed" or run["conclusion"] != "success":
            fail("latest exact-commit Linux CI run/attempt is not completed successfully")
        jobs = pages(f"/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs", "jobs")
        require(len({job["id"] for job in jobs}) == len(jobs))
        required = [job for job in jobs if job["name"] == "Linux full checks"]
        if len(required) != 1:
            fail("required Linux full checks job is missing or ambiguous")
        job = required[0]
        require(
            type(job["id"]) is int
            and job["id"] > 0
            and job["run_id"] == run["id"]
            and job["head_sha"] == candidate
            and type(job["run_attempt"]) is int
            and job["run_attempt"] == run["run_attempt"]
        )
        if job["status"] != "completed" or job["conclusion"] != "success":
            fail("required Linux full checks job is not completed successfully")
        final = get(f"/actions/runs/{run['id']}")
        newest = latest()
        for observed in (final, newest):
            provenance(observed, workflow)
            require(
                observed["id"] == run["id"]
                and observed["run_attempt"] == run["run_attempt"]
                and observed["status"] == "completed"
                and observed["conclusion"] == "success"
            )
        return {**result, "eligible": True, "job": "Linux full checks"}
    except RuntimeError as exc:
        return {**result, "blocker": str(exc)}
    except (OSError, error.URLError, HTTPException, ValueError, KeyError, TypeError):
        return {
            **result,
            "blocker": "GitHub Linux CI API unavailable, rate-limited or unverifiable",
        }


def update(
    root: Path,
    installed: dict,
    arguments: argparse.Namespace,
    fetched: dict | None = None,
    *,
    replacement: Path | None = None,
) -> None:
    require_idle(root)
    if installed["protocol"] != STABLE_PROTOCOL and not getattr(
        arguments, "adoption_revision", None
    ):
        fail("launcher protocol transition requires the reviewed external adoption bootstrap")
    if replacement is None:
        require_checkout(installed)
    print("[Stable update] Fetching published main candidate", file=sys.stderr, flush=True)
    if fetched is None:
        fetched = availability(
            Path(installed["checkout"]), installed["upstream"], installed["commit"]
        )
    if fetched["updates"] == "current" and replacement is None:
        print(json.dumps({"updates": "current", "health": health(installed.get("port", PORT))}))
        return
    if fetched["updates"] not in {"behind", "current"}:
        fail(f"cannot update: upstream state is {fetched['updates']}")
    candidate = fetched["candidate"]
    planning = {**installed, "checkout": str(replacement or installed["checkout"])}
    if replacement:
        planning["python"] = sys.executable
    plan = update_plan(planning, candidate, arguments.seed, rebuilding=replacement is not None)
    print("[Stable update] Looking up exact-commit Linux CI", file=sys.stderr, flush=True)
    eligibility = linux_ci(installed["upstream"], candidate)
    print(
        json.dumps(
            {
                **plan,
                "linux_ci": eligibility,
                "local_verification": (
                    "Operator must review applicable candidate-bound local evidence for the "
                    "complete "
                    "installed-to-candidate delta under docs/verification.md before approval. "
                    "This is not automatically verified; --yes does not waive review."
                ),
            },
            indent=2,
        ),
        flush=True,
    )
    if not eligibility["eligible"]:
        fail(eligibility["blocker"])
    if arguments.dry_run or not confirm("Prepare and install this exact commit?", arguments.yes):
        return
    started = time.monotonic()

    def phase(name: str) -> None:
        print(f"[Stable update +{time.monotonic() - started:.1f}s] {name}", flush=True)

    checkout = replacement or Path(installed["checkout"])
    record = {
        "previous": installed,
        "candidate": None,
        "backup": None,
        "data_mutated": False,
        "adoption": bool(getattr(arguments, "adoption_revision", None)),
    }
    with preparing(root, record), candidate_source(root, checkout, candidate) as source:
        phase("Linux CI verified; preparing locked candidate environment")
        prepared = prepare_environment(root, {**planning, "commit": candidate}, source)
        prepared["controller_python"] = str(Path(sys.executable).resolve())
        prepared["protocol"] = STABLE_PROTOCOL
        if replacement:
            prepared["managed_checkout"] = True
        phase("Validating synthetic commands")
        synthetic_configuration = source.parent / "test-configuration.json"
        write_json(synthetic_configuration, {})
        synthetic = {
            **prepared,
            "configuration": str(synthetic_configuration),
            "database": str(source.parent / "test-database.sqlite3"),
        }
        raycast_commands(synthetic, source)
        # No automatic post-preparation fetch: the reviewed commit remains pinned.
        if (
            update_plan(planning, candidate, arguments.seed, rebuilding=replacement is not None)
            != plan
        ):
            fail("installation/schema changed since preview; review a fresh update")
        phase("Rechecking Linux CI before stopping Stable")
        eligibility = linux_ci(installed["upstream"], candidate)
        if not eligibility["eligible"]:
            fail(eligibility["blocker"])
        record["candidate"] = prepared
        progress(root, record, "stopping")
        try:
            phase("Stopping Stable; backup and rehearsal follow during maintenance")
            stop_service(root, installed)
            backup_installation(root, installed, record, replacement)
            backup = Path(record["backup"])
            if plan["migrations"] or arguments.seed:
                phase("Backing up and rehearsing on a copy")
                progress(root, record, "backing_up")
                progress(root, record, "rehearsing")
                with tempfile.TemporaryDirectory(prefix="rehearsal-", dir=root) as directory:
                    rehearsal = Path(directory) / "database.sqlite3"
                    shutil.copyfile(backup, rehearsal)
                    if plan["migrations"]:
                        admin(prepared, source, "migrate", rehearsal)
                    if arguments.seed:
                        admin(prepared, source, "seed", rehearsal)
                    validate_application({**prepared, "database": str(rehearsal)}, source)
            else:
                validate_application(prepared, source)
            require_checkout({**planning, "commit": candidate} if replacement else installed)
            require_no_collisions(checkout, candidate)
            phase("Rechecking Linux CI before replacing code")
            eligibility = linux_ci(installed["upstream"], candidate)
            if not eligibility["eligible"]:
                fail(eligibility["blocker"])
            progress(root, record, "replacing_code")
            phase("Replacing code and applying approved migrations/seeds")
            git(checkout, "-c", "core.hooksPath=/dev/null", "merge", "--ff-only", candidate)
            if plan["migrations"] or arguments.seed:
                record["data_mutated"] = True
                progress(root, record, "migrating")
                if plan["migrations"]:
                    admin(prepared, checkout, "migrate")
                if arguments.seed:
                    admin(prepared, checkout, "seed")
            phase("Validating candidate application and activating with health checks")
            validate_application(prepared, checkout)
            activate(root, prepared, record)
            phase("Update succeeded; Linux CI verified, local evidence remains operator-reviewed")
            print(f"Stable is healthy at {candidate}; previous environment and backups retained.")
        except BaseException:
            phase("Update failed; attempting pre-mutation recovery when safe")
            progress(root, record, "failed")
            try:
                stop_service(root, load_installation(root))
                if not record["data_mutated"]:
                    if (
                        not replacement
                        and git(checkout, "rev-parse", "HEAD") != installed["commit"]
                    ):
                        git(checkout, "reset", "--keep", installed["commit"])
                    require_checkout(installed)
                    validate_application(installed, Path(installed["checkout"]))
                    activate(root, installed, record)
                    print("Previous Stable recovered; no database mutation occurred.")
            except (OSError, RuntimeError, subprocess.SubprocessError):
                progress(root, record, "recovery_required")
            if (root / "maintenance.json").exists():
                print(
                    f"Stable remains in maintenance; inspect {root / 'maintenance.json'}",
                    file=sys.stderr,
                )
            raise


def recover(root: Path, installed: dict, arguments: argparse.Namespace) -> None:
    path = root / "maintenance.json"
    if not path.exists():
        path = root / "last-update.json"
    if not path.exists():
        fail("no update recovery record exists")
    record = read_json(path)
    if record.get("preservation"):
        if (Path(record["preservation"]) / "recovery.json").exists():
            verify_preservation(Path(record["preservation"]))
        elif arguments.restore_backup or record["data_mutated"]:
            fail("installation backup was interrupted; no verified restoration is available")
    selected = record.get(arguments.use)
    if not selected:
        fail("recovery record has no selected runtime; manual inspection is required")
    selected = dict(selected)
    preservation = Path(record["preservation"]) if record.get("preservation") else None
    if arguments.use == "previous" and record.get("adoption") and not preservation:
        fail(
            "interrupted adoption has no complete original snapshot; use candidate recovery "
            "to preserve originals before activation, not a manual checkout reset"
        )
    if arguments.use == "previous" and preservation:
        if (
            not Path(selected["python"]).is_file()
            and (preservation / "environment/bin/python").is_file()
        ):
            selected["python"] = str(preservation / "environment/bin/python")
            selected["service_arguments"] = [selected["python"], *selected["service_arguments"][1:]]
        if record.get("adoption") or not Path(selected["checkout"]).is_dir():
            destination = root / "sources" / uuid.uuid4().hex
            destination.parent.mkdir(mode=0o700, exist_ok=True)
            run("git", "clone", str(preservation / "source.bundle"), str(destination))
            git(destination, "checkout", "-B", "main", selected["commit"])
            selected["checkout"] = str(destination)
            selected["managed_checkout"] = True
    checkout = Path(selected["checkout"])
    head = git(checkout, "rev-parse", "HEAD")
    if head not in {
        runtime["commit"]
        for runtime in (record.get("previous"), record.get("candidate"))
        if runtime
    }:
        fail("checkout has unrelated changes; recovery requires manual review")
    require_checkout({**selected, "commit": head})
    require_no_collisions(checkout, selected["commit"])
    backup = record.get("backup")
    if record.get("initialization") and (arguments.use != "candidate" or arguments.restore_backup):
        fail("interrupted initialization requires recover --use candidate; data will be preserved")
    if arguments.restore_backup and not backup:
        fail("this update has no database backup")
    if arguments.restore_backup and selected["database"] != installed["database"]:
        fail("selected runtime uses a retained separate database; recover without --restore-backup")
    if (
        arguments.use == "previous"
        and record.get("data_mutated")
        and not arguments.restore_backup
        and record["previous"]["database"] == (record.get("candidate") or {}).get("database")
    ):
        fail(
            "database mutation began; previous-runtime recovery requires explicit --restore-backup"
        )
    print("Recovery never downgrades schema. Restoring a backup discards later database changes.")
    if not confirm(
        "Recover the selected runtime"
        + (" AND RESTORE THE DATABASE?" if arguments.restore_backup else "?"),
        arguments.yes,
    ):
        return
    if arguments.use == "candidate" and not record.get("initialization"):
        eligibility = linux_ci(selected["upstream"], selected["commit"])
        if not eligibility["eligible"]:
            fail(eligibility["blocker"])
    progress(root, record, "recovering")
    stop_service(root, installed)
    if arguments.use == "candidate" and not record.get("initialization") and not backup:
        backup_installation(root, installed, record, checkout)
        backup = record["backup"]
    if arguments.restore_backup:
        database = Path(installed["database"])
        try:
            preserved = backup_database(root, database)
        except (sqlite3.Error, RuntimeError):
            # A failed migration may leave no readable revision, or corrupt SQLite.
            # Preserve the stopped database and its journals without requiring valid schema.
            preserved = root / "backups" / f"{time.time_ns()}-damaged"
            preserved.mkdir(mode=0o700, parents=True)
            for suffix in ("", "-wal", "-shm", "-journal"):
                original = Path(str(database) + suffix)
                if original.exists():
                    destination = preserved / ("database.sqlite3" + suffix)
                    shutil.copyfile(original, destination)
                    destination.chmod(0o600)
        record["before_restore"] = str(preserved)
        progress(root, record, "restoring_database")
        with sqlite3.connect(Path(backup).as_uri() + "?mode=ro", uri=True) as source:
            if source.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                fail("recovery backup failed integrity verification")
            # Prepare beside the original for an atomic same-filesystem replacement.
            with tempfile.TemporaryDirectory(prefix="restore-", dir=database.parent) as directory:
                replacement = Path(directory) / "database.sqlite3"
                with sqlite3.connect(replacement) as destination:
                    source.backup(destination)
                replacement.chmod(0o600)
                with replacement.open("rb") as output:
                    os.fsync(output.fileno())
                for suffix in ("-wal", "-shm", "-journal"):
                    Path(str(database) + suffix).unlink(missing_ok=True)
                replacement.replace(database)
    git(checkout, "reset", "--keep", selected["commit"])
    if record.get("initialization"):
        admin(selected, checkout, "migrate")
        admin(selected, checkout, "seed")
    elif arguments.use == "candidate":
        pending = probe(selected, checkout)["migrations"]
        if pending:
            with tempfile.TemporaryDirectory(prefix="recovery-rehearsal-", dir=root) as directory:
                rehearsal = Path(directory) / "database.sqlite3"
                shutil.copyfile(backup, rehearsal)
                admin(selected, checkout, "migrate", rehearsal)
                validate_application({**selected, "database": str(rehearsal)}, checkout)
            record["data_mutated"] = True
            progress(root, record, "migrating")
            admin(selected, checkout, "migrate")
    validate_application(selected, checkout)
    previous_controller = preservation / "controller.py" if preservation else None
    activate(
        root,
        selected,
        record,
        previous_controller
        if arguments.use == "previous" and previous_controller and previous_controller.is_file()
        else None,
    )
    print("Stable recovery verified; recovery material retained.")


def health(port: int) -> dict:
    try:
        with request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
            result = json.load(response)
        return {"ready": result.get("status") == "ok" and result.get("profile") == "release"}
    except (OSError, ValueError, error.URLError):
        return {"ready": False}


def availability(checkout: Path, upstream: str, installed: str) -> dict:
    result = {"updates": "unknown", "candidate": None, "commits": ""}
    try:
        # An explicit source avoids the local-checkout origin used by older installations.
        git(
            checkout,
            "fetch",
            "--no-tags",
            "--no-write-fetch-head",
            upstream,
            "+refs/heads/main:refs/local-text/stable-main",
        )
        candidate = git(checkout, "rev-parse", "refs/local-text/stable-main")
        behind, ahead = map(
            int,
            git(
                checkout, "rev-list", "--left-right", "--count", f"{candidate}...{installed}"
            ).split(),
        )
        state = (
            "divergent"
            if behind and ahead
            else ("behind" if behind else "ahead" if ahead else "current")
        )
        result.update(
            updates=state,
            candidate=candidate,
            commits=git(checkout, "log", "--format=%h %s", f"{installed}..{candidate}"),
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return result


def status(root: Path, checkout: Path, upstream: str) -> dict:
    manifest = root / "installation.json"
    installed = read_json(manifest) if manifest.exists() else None
    if installed:
        checkout = Path(installed["checkout"])
        upstream = installed["upstream"]
    schema = None
    if installed:
        try:
            schema = probe(installed, checkout)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            schema = {"state": "unknown", "detail": "installed schema check could not run"}
    commit = installed["commit"] if installed else git(checkout, "rev-parse", "HEAD")
    return {
        "installed": installed is not None,
        "installed_commit": commit,
        "checkout_commit": git(checkout, "rev-parse", "HEAD"),
        "checkout_status": git(checkout, "status", "--short"),
        "maintenance": read_json(root / "maintenance.json")
        if (root / "maintenance.json").exists()
        else None,
        "health": health(installed.get("port", PORT)) if installed else {"ready": False},
        "port": installed.get("port", PORT) if installed else PORT,
        "service": service_status(root, installed) if installed else None,
        "schema": schema,
        **availability(checkout, upstream, commit),
    }


def prerequisites() -> None:
    if sys.version_info < (3, 12):  # noqa: UP036 - standalone bootstrap host, not project Python
        fail("Stable requires Python 3.12 or newer; select a supported host interpreter")
    for executable in ("git", "uv", "launchctl", "lsof"):
        if not shutil.which(executable):
            fail(f"Stable requires {executable} on PATH; install this host prerequisite first")


def require_complete(root: Path, installed: dict) -> None:
    require_idle(root)
    require_checkout(installed)
    if installed["protocol"] != STABLE_PROTOCOL:
        fail("legacy installation requires the external adoption bootstrap; no files changed")
    expected = [installed["python"], str(root / "stable.py"), "--root", str(root), "serve"]
    if installed["service_arguments"] != expected:
        fail("inconsistent service registration; inspect installation before repair")
    checkout = Path(installed["checkout"])
    controller = root / "stable.py"
    if (
        not controller.is_file()
        or controller.is_symlink()
        or controller.read_text()
        != run(
            "git", "-C", str(checkout), "show", f"{installed['commit']}:scripts/stable.py"
        ).stdout
        or not Path(installed["python"]).is_file()
        or not (root / "stable").is_file()
        or (root / "stable").read_text() != command_entry(root, installed)
    ):
        fail("incomplete Stable runtime; inspect installation before repair")
    plist = Path(installed["plist"])
    if (
        not plist.is_file()
        or plistlib.loads(plist.read_bytes()).get("ProgramArguments") != expected
    ):
        fail("inconsistent Stable LaunchAgent; inspect installation before repair")
    for name, contents in installed.get("commands", {}).items():
        command = Path(installed["raycast_directory"]) / name
        if not command.is_file() or command.is_symlink() or command.read_text() != contents:
            fail("incomplete Stable commands; inspect installation before repair")
    validate_application(installed, checkout)


def default_launch(root: Path, arguments: argparse.Namespace) -> None:
    prerequisites()
    require_idle(root)
    manifest = root / "installation.json"
    if manifest.exists():
        installed = load_installation(root)
        for option in ("checkout", "database", "configuration", "raycast_directory", "port"):
            selected = getattr(arguments, option)
            if selected is not None and str(selected) != str(installed.get(option, PORT)):
                fail(f"existing Stable retains its selected {option}; override refused")
        require_complete(root, installed)
        fetched = availability(
            Path(installed["checkout"]), installed["upstream"], installed["commit"]
        )
        if fetched["updates"] == "current":
            state = service_status(root, installed)
            if state["owned"] and state["pid"] and not health(installed.get("port", PORT))["ready"]:
                stop_service(root, installed)
            start_service(root, installed)
            print(f"Stable is current and healthy at {installed['commit']}")
            return
        if fetched["updates"] == "behind":
            update(root, installed, arguments, fetched)
            if load_installation(root)["commit"] != fetched["candidate"]:
                fail("update not approved; installation preserved, not an up-to-date success")
            return
        fail(f"published main could not be selected ({fetched['updates']}); installation preserved")
    for reserved in ("stable.py", "stable", "environments", "backups"):
        if (root / reserved).exists() or (root / reserved).is_symlink():
            fail("incomplete installation; inspect/repair rather than initialize new data")
    checkout = (arguments.checkout or DEFAULT_CHECKOUT).expanduser().resolve()
    managed = not checkout.exists()
    if managed:
        checkout.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        run(
            "git", "clone", "--branch", "main", "--single-branch", arguments.upstream, str(checkout)
        )
    candidate = git(checkout, "rev-parse", "HEAD")
    require_checkout({"checkout": str(checkout), "commit": candidate})
    fetched = availability(checkout, arguments.upstream, candidate)
    if fetched["updates"] != "current":
        fail("fresh checkout is not published main; preserved for inspection, no data initialized")
    eligibility = linux_ci(arguments.upstream, candidate)
    print(
        json.dumps(
            {
                "candidate": candidate,
                "linux_ci": eligibility,
                "local_verification": "Review applicable candidate-bound local evidence under "
                "docs/verification.md. --yes does not waive review.",
            },
            indent=2,
        ),
        flush=True,
    )
    if not eligibility["eligible"]:
        fail(eligibility["blocker"])
    selected = argparse.Namespace(**vars(arguments))
    selected.checkout = checkout
    selected.pinned_commit = candidate
    selected.initialize = not (arguments.database or DEFAULT_DATABASE).expanduser().exists()
    selected.reuse_existing = True
    if not confirm(
        "Install this exact Stable candidate, prepare its database and start it?", arguments.yes
    ):
        fail("installation not approved; no database or configuration changed")
    selected.yes = True
    install(root, selected)
    installed = load_installation(root)
    installed["managed_checkout"] = managed
    write_json(manifest, installed)
    require_checkout(installed)
    eligibility = linux_ci(arguments.upstream, candidate)
    if not eligibility["eligible"]:
        fail(eligibility["blocker"])
    start_service(root, installed)
    print(f"Stable is current and healthy at {candidate}. Command: {root / 'stable'}")


def acquire_replacement(root: Path, installed: dict) -> tuple[Path, dict]:
    destination = root / "sources" / uuid.uuid4().hex
    destination.parent.mkdir(mode=0o700, exist_ok=True)
    run(
        "git",
        "clone",
        "--branch",
        "main",
        "--single-branch",
        installed["upstream"],
        str(destination),
    )
    fetched = availability(destination, installed["upstream"], installed["commit"])
    if fetched["updates"] not in {"current", "behind"}:
        fail("cannot acquire published main for repair; original installation preserved")
    eligibility = linux_ci(installed["upstream"], fetched["candidate"])
    print(json.dumps({"candidate": fetched["candidate"], "linux_ci": eligibility}, indent=2))
    if not eligibility["eligible"]:
        fail(eligibility["blocker"])
    # This newly created checkout is disposable; never reset the selected installation.
    git(destination, "reset", "--hard", fetched["candidate"])
    return destination, fetched


def repair(root: Path, arguments: argparse.Namespace) -> None:
    prerequisites()
    require_idle(root)
    installed = load_installation(root)
    if installed["protocol"] != STABLE_PROTOCOL:
        fail("protocol-1 requires the reviewed external adoption bootstrap, not ordinary repair")
    print(
        "Repair preserves configuration and database, rebuilding managed application artifacts. "
        "It cannot bypass failed release verification, ownership checks or unsupported migrations."
    )
    replacement, fetched = acquire_replacement(root, installed)
    update(root, installed, arguments, fetched, replacement=replacement)


def adopt(root: Path, arguments: argparse.Namespace) -> None:
    prerequisites()
    require_idle(root)
    installed = load_installation(root)
    if installed["protocol"] == STABLE_PROTOCOL:
        if installed["commit"] != arguments.adoption_revision:
            fail("already-adopted installation differs from the reviewed bootstrap pin")
        default_launch(root, arguments)
        return
    copied = root / "stable.py"
    if copied.is_symlink() or assignment(copied.read_text(), "STABLE_PROTOCOL") != 1:
        fail("adoption requires a supported protocol-1 copied controller; original preserved")
    configuration(Path(installed["configuration"]))
    replacement, fetched = acquire_replacement(root, installed)
    if fetched["candidate"] != arguments.adoption_revision:
        fail("published main moved from the reviewed bootstrap pin; review a new invocation")
    try:
        original_head = git(Path(installed["checkout"]), "rev-parse", "HEAD")
    except (OSError, subprocess.SubprocessError):
        original_head = None
    print(
        json.dumps(
            {
                "operation": "explicit protocol-1 adoption, not ordinary update",
                "recorded_application": installed["commit"],
                "checkout": installed["checkout"],
                "checkout_commit": original_head,
                "copied_controller_sha256": hashlib.sha256(copied.read_bytes()).hexdigest(),
                "service": service_status(root, installed),
                "candidate": fetched["candidate"],
                "database_preserved": installed["database"],
                "configuration_preserved": installed["configuration"],
                "original_source_environment": "retained; replacement uses a new isolated checkout",
                "private_recovery_location": str(root / "backups"),
                "warning": "After database mutation, rollback needs confirmed restoration and can "
                "lose newer changes. Unsupported populated transitions require a separately "
                "confirmed clean installation, never clearing the original.",
            },
            indent=2,
        ),
        flush=True,
    )
    update(root, installed, arguments, fetched, replacement=replacement)
    if load_installation(root)["protocol"] != STABLE_PROTOCOL:
        fail("adoption not approved; original installation preserved")


def clean_install(root: Path, arguments: argparse.Namespace) -> None:
    prerequisites()
    # A separately confirmed fresh installation may follow a refused/interrupted
    # transition. Preserve that transaction as well as its original backup.
    prior_transaction = root / "maintenance.json"
    interrupted = read_json(prior_transaction) if prior_transaction.exists() else None
    installed = load_installation(root)
    replacement, fetched = acquire_replacement(root, installed)
    candidate = fetched["candidate"]
    if arguments.adoption_revision and candidate != arguments.adoption_revision:
        fail("clean-install candidate differs from the reviewed bootstrap pin")
    if (
        assignment(git(replacement, "show", f"{candidate}:scripts/stable.py"), "STABLE_PROTOCOL")
        != STABLE_PROTOCOL
    ):
        fail("clean installation requires the supported candidate launcher protocol")
    database = Path(installed["database"])
    fresh = database.with_name(f"{database.stem}-clean-{uuid.uuid4().hex}{database.suffix}")
    print(
        f"Clean installation preview: {root}\nCandidate: {candidate}\n"
        f"Fresh database with reset application settings: {fresh}\n"
        f"Retain provider configuration: {installed['configuration']}\n"
        f"Original database remains untouched: {database}\n"
        f"Original checkout/environment retained; recovery material: {root / 'backups'}\n"
        "Review candidate-bound local evidence under docs/verification.md before approval."
    )
    if not confirm(
        "Create this fresh installation AND reset application settings?",
        arguments.confirm_clean_install,
    ):
        fail("clean installation cancelled; original database/runtime/configuration preserved")
    if interrupted is not None:
        retained = root / "backups" / f"{uuid.uuid4().hex}-transaction.json"
        retained.parent.mkdir(mode=0o700, exist_ok=True)
        write_json(retained, interrupted)
        print(f"Previous interrupted transaction and its recovery locations retained at {retained}")
    record = {
        "previous": installed,
        "candidate": None,
        "backup": None,
        "data_mutated": False,
        "clean_install": True,
        "adoption": installed["protocol"] == 1,
    }
    stage = root / "staging" / uuid.uuid4().hex
    stage.mkdir(mode=0o700, parents=True)
    selected = argparse.Namespace(
        checkout=replacement,
        pinned_commit=candidate,
        database=fresh,
        configuration=Path(installed["configuration"]),
        raycast_directory=stage / "commands",
        port=installed.get("port", PORT),
        upstream=installed["upstream"],
        reuse_existing=True,
        initialize=True,
        yes=True,
        preparing_replacement=True,
    )
    with preparing(root, record):
        install(stage, selected)
        prepared = load_installation(stage)
        Path(prepared["plist"]).unlink()
        prepared.update(
            label=installed["label"],
            plist=installed["plist"],
            raycast_directory=installed["raycast_directory"],
            managed_checkout=True,
        )
        prepared["service_arguments"] = [
            prepared["python"],
            str(root / "stable.py"),
            "--root",
            str(root),
            "serve",
        ]
        record["candidate"] = prepared
        eligibility = linux_ci(installed["upstream"], candidate)
        if not eligibility["eligible"]:
            fail(eligibility["blocker"])
        progress(root, record, "stopping")
        stop_service(root, installed)
        backup_installation(root, installed, record, replacement)
        eligibility = linux_ci(installed["upstream"], candidate)
        if not eligibility["eligible"]:
            fail(eligibility["blocker"])
        activate(root, prepared, record)
    print(
        f"Fresh Stable is healthy; original database remains at {database}. "
        f"Private backups retained at {record['preservation']}."
    )


def launch_with_choices(root: Path, arguments: argparse.Namespace) -> None:
    if arguments.recovery:
        arguments.use = arguments.recovery
        recover(root, load_installation(root), arguments)
        return
    operation = (
        clean_install
        if arguments.clean_install
        else repair
        if arguments.repair
        else adopt
        if arguments.adoption_revision
        else default_launch
    )
    try:
        operation(root, arguments)
    except (OSError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print(f"Operation did not complete: {reason}", file=sys.stderr)
        print(
            "Safe choices: retry stable; stable --repair rebuilds artifacts, not eligibility; "
            "stable --clean-install previews a separately confirmed fresh database while retaining "
            "the original. Interrupted transactions: stable --recovery candidate or previous; "
            "--restore-backup requires confirmation and can lose newer changes.",
            file=sys.stderr,
        )
        if not sys.stdin.isatty():
            raise
        choice = (
            input("Retry [r], repair [p], clean installation [c], or cancel [N]? ").strip().lower()
        )
        if choice == "r":
            operation(root, arguments)
        elif choice == "p":
            repair(root, arguments)
        elif choice == "c":
            clean_install(root, arguments)
        else:
            raise


def uninstall(root: Path, installed: dict, yes: bool) -> None:
    print(
        f"Remove owned Stable service and application artifacts from {root}.\n"
        f"Retain database: {installed['database']}\n"
        f"Retain configuration: {installed['configuration']}\n"
        f"Retain backups/recovery records: {root / 'backups'}"
    )
    if not confirm("Uninstall Stable, retaining private data and backups?", yes):
        fail("uninstall not confirmed; no files or services changed")
    # Do not require the checkout, dependencies, configuration parser or network.
    plist = Path(installed["plist"])
    if plist.exists() and (
        plist.is_symlink()
        or plistlib.loads(plist.read_bytes()).get("ProgramArguments")
        != installed["service_arguments"]
    ):
        fail("refusing to remove an unmanaged LaunchAgent")
    stop_service(root, installed)
    plist.unlink(missing_ok=True)
    for name, contents in installed.get("commands", {}).items():
        command = Path(installed["raycast_directory"]) / name
        if command.is_file() and not command.is_symlink() and command.read_text() == contents:
            command.unlink()
        elif command.exists() or command.is_symlink():
            print(f"Retained changed or unowned command: {command}")
    if installed.get("managed_checkout"):
        checkout = Path(installed["checkout"])
        if checkout.exists():
            try:
                require_checkout(installed)
                if git(checkout, "status", "--porcelain", "--untracked-files=all", "--ignored"):
                    fail("additional checkout files")
            except (OSError, RuntimeError, subprocess.SubprocessError):
                print(f"Retained changed or damaged checkout: {checkout}")
            else:
                shutil.rmtree(checkout)
    runtime = Path(installed["python"]).parent.parent
    if (
        runtime.is_relative_to(root)
        and runtime.parent.name == "environments"
        and not runtime.is_symlink()
    ):
        if any(
            Path(installed[key]).is_relative_to(runtime) for key in ("database", "configuration")
        ):
            print(f"Retained environment containing private data: {runtime}")
        elif runtime.is_dir():
            shutil.rmtree(runtime)
    for name in ("stable", "stable.py"):
        (root / name).unlink(missing_ok=True)
    write_json(root / "uninstalled.json", installed)
    (root / "installation.json").unlink()
    print("Stable uninstalled; private data, configuration and recovery material retained.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--upstream", default=UPSTREAM)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--configuration", type=Path)
    parser.add_argument("--raycast-directory", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--yes", action="store_true", help="approve after local evidence review")
    choices = parser.add_mutually_exclusive_group()
    choices.add_argument("--repair", action="store_true", help="rebuild artifacts; preserve data")
    choices.add_argument(
        "--clean-install", action="store_true", help="preview a preserved-original reset"
    )
    choices.add_argument("--recovery", choices=("previous", "candidate"))
    parser.add_argument(
        "--confirm-clean-install",
        action="store_true",
        help="separately approve the displayed fresh-database/settings reset",
    )
    parser.add_argument("--restore-backup", action="store_true")
    parser.add_argument("--adoption-revision", help=argparse.SUPPRESS)
    parser.set_defaults(dry_run=False, seed=False)
    commands = parser.add_subparsers(dest="command", help="default: install/update/prepare/start")
    commands.add_parser("status")
    commands.add_parser("stop", help="stop only this service; no network or database preparation")
    uninstaller = commands.add_parser(
        "uninstall", help="remove owned artifacts; retain private data"
    )
    uninstaller.add_argument("--yes", action="store_true", default=argparse.SUPPRESS)
    installer = commands.add_parser("install", help="compatibility: prepare without starting")
    installer.add_argument(
        "--checkout",
        type=Path,
        default=argparse.SUPPRESS,
        help="Stable main checkout directory, not a branch name",
    )
    installer.add_argument("--database", type=Path, help=f"default: {DEFAULT_DATABASE}")
    installer.add_argument("--port", type=int, help=f"installation loopback port (default: {PORT})")
    installer.add_argument("--configuration", type=Path, help=f"default: {DEFAULT_CONFIGURATION}")
    installer.add_argument(
        "--raycast-directory", type=Path, help="default: ~/.config/raycast/scripts"
    )
    installer.add_argument(
        "--reuse-existing", action="store_true", help="use existing Stable files unchanged"
    )
    installer.add_argument("--initialize", action="store_true")
    installer.add_argument("--yes", action="store_true")
    for operation in ("start", "restart", "serve"):
        commands.add_parser(operation, help="compatibility: readiness-only service operation")
    updater = commands.add_parser("update", help="compatibility: explicitly update")
    updater.add_argument("--dry-run", action="store_true")
    updater.add_argument("--seed", action="store_true", help="explicitly apply deterministic seeds")
    updater.add_argument("--yes", action="store_true")
    recovery = commands.add_parser("recover")
    recovery.add_argument("--use", choices=("previous", "candidate"), required=True)
    recovery.add_argument("--restore-backup", action="store_true")
    recovery.add_argument("--yes", action="store_true")
    arguments = parser.parse_args()
    if arguments.command in {"install", "status"} and arguments.checkout is None:
        arguments.checkout = Path(__file__).resolve().parents[1]
    root = arguments.root.expanduser().absolute()
    try:
        if arguments.command == "status":
            print(json.dumps(status(root, arguments.checkout, arguments.upstream), indent=2))
        elif arguments.command == "serve":
            launch(root, load_installation(root))
        else:
            with locked(root):
                if arguments.command is None:
                    launch_with_choices(root, arguments)
                elif arguments.command == "stop":
                    stop_service(root, load_installation(root))
                elif arguments.command == "uninstall":
                    uninstall(root, load_installation(root), arguments.yes)
                elif arguments.command == "install":
                    install(root, arguments)
                elif arguments.command == "update":
                    update(root, load_installation(root), arguments)
                elif arguments.command == "recover":
                    recover(root, load_installation(root), arguments)
                else:
                    require_idle(root)
                    installed = load_installation(root)
                    require_checkout(installed)
                    validate_application(installed, Path(installed["checkout"]))
                    if arguments.command == "restart":
                        stop_service(root, installed)
                    start_service(root, installed)
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        sqlite3.Error,
        subprocess.SubprocessError,
    ) as exc:
        message = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        if (
            isinstance(exc, subprocess.CalledProcessError)
            and root.is_dir()
            and arguments.command not in {"status", "serve"}
        ):
            diagnostic = root / "operation-error.log"
            with open(
                diagnostic,
                "w",
                opener=lambda name, flags: os.open(name, flags | os.O_NOFOLLOW, 0o600),
            ) as output:
                os.fchmod(output.fileno(), 0o600)
                output.write((exc.stdout or "") + (exc.stderr or ""))
            message = f"{Path(exc.cmd[0]).name} failed; inspect {diagnostic}"
        print(f"error: Stable operation failed: {message}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
