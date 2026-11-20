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
from pathlib import Path
from urllib import error, request

STABLE_PROTOCOL = 2
PORT = 7532
UPSTREAM = "https://github.com/dmclark/sayloom.git"
DEFAULT_ROOT = Path.home() / ".local/share/local-text/stable-runtime"
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
    temporary = path.with_suffix(".tmp")
    with open(temporary, "w", opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
        json.dump(value, output, indent=2)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


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
        and key not in {"GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"}
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
    if installed["protocol"] not in {1, STABLE_PROTOCOL}:
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
    return {**installed, "python": str(destination / "bin/python")}


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


def write_plist(root: Path, installed: dict) -> Path:
    plist = Path(installed["plist"])
    plist.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if plist.exists():
        existing = plistlib.loads(plist.read_bytes())
        if existing.get("ProgramArguments") != installed["service_arguments"]:
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
    commit = git(checkout, "rev-parse", "HEAD")
    port = arguments.port if arguments.port is not None else PORT
    if not 1024 <= port <= 65535 or port == 7523:
        fail("Stable port must be between 1024 and 65535 and not development port 7523")
    label = "local.local-text.stable." + hashlib.sha256(str(root).encode()).hexdigest()[:12]
    installed = {
        "protocol": STABLE_PROTOCOL,
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
    require_free_port(port)
    if not confirm("Prepare Stable installation (does not start it)?", arguments.yes):
        return
    if not config.exists():
        config.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Exclusive creation must never replace an existing provider configuration.
        with open(config, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
            output.write("{}\n")
        print("Created empty provider configuration; external cleanup is not enabled.")
    installed = prepare_environment(root, installed, checkout)
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
    shutil.copyfile(Path(__file__), root / "stable.py")
    os.chmod(root / "stable.py", 0o700)
    entry = root / "stable"
    entry.write_text(
        "#!/bin/sh\nexec " + shlex.join(installed["service_arguments"][:-1]) + ' "$@"\n'
    )
    entry.chmod(0o700)
    write_plist(root, installed)
    command_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, contents in commands.items():
        destination = command_directory / name
        destination.write_text(contents)
        destination.chmod(0o700)
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


def update_plan(installed: dict, candidate: str, seed: bool) -> dict:
    checkout = Path(installed["checkout"])
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


def progress(root: Path, record: dict, phase: str) -> None:
    record["phase"] = phase
    write_json(root / "maintenance.json", record)


def activate(root: Path, installed: dict, record: dict) -> None:
    record["launch_commit"] = installed["commit"]
    progress(root, record, "activating")
    write_json(root / "installation.json", installed)
    start_service(root, installed)
    (root / "maintenance.json").unlink()


def update(root: Path, installed: dict, arguments: argparse.Namespace) -> None:
    require_idle(root)
    require_checkout(installed)
    fetched = availability(Path(installed["checkout"]), installed["upstream"], installed["commit"])
    if fetched["updates"] == "current":
        print(json.dumps({"updates": "current", "health": health(installed.get("port", PORT))}))
        return
    if fetched["updates"] != "behind":
        fail(f"cannot update: upstream state is {fetched['updates']}")
    candidate = fetched["candidate"]
    plan = update_plan(installed, candidate, arguments.seed)
    print(json.dumps(plan, indent=2), flush=True)
    if arguments.dry_run or not confirm("Prepare and install this exact commit?", arguments.yes):
        return
    checkout = Path(installed["checkout"])
    record = {"previous": installed, "candidate": None, "backup": None, "data_mutated": False}
    with candidate_source(root, checkout, candidate) as source:
        prepared = prepare_environment(root, {**installed, "commit": candidate}, source)
        # Candidate tests receive synthetic state and no provider credentials.
        synthetic_configuration = source.parent / "test-configuration.json"
        write_json(synthetic_configuration, {})
        synthetic = {
            **prepared,
            "configuration": str(synthetic_configuration),
            "database": str(source.parent / "test-database.sqlite3"),
        }
        raycast_commands(synthetic, source)
        for command in (("ruff", "check", "."), ("pytest", "-q")):
            run(
                prepared["python"],
                "-c",
                "import os,signal,sys; signal.signal(signal.SIGINT, signal.SIG_DFL); "
                "os.execv(sys.executable, [sys.executable, '-m', *sys.argv[1:]])",
                *command,
                cwd=source,
                env=environment(synthetic, source),
                timeout=600,
            )
        run("node", "--check", str(source / "src/local_text/static/app.js"))
        # No automatic post-preparation fetch: the reviewed commit remains pinned.
        if update_plan(installed, candidate, arguments.seed) != plan:
            fail("installation/schema changed since preview; review a fresh update")
        record["candidate"] = prepared
        progress(root, record, "stopping")
        try:
            stop_service(root, installed)
            if plan["migrations"] or arguments.seed:
                progress(root, record, "backing_up")
                backup = backup_database(root, Path(installed["database"]))
                record["backup"] = str(backup)
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
            require_checkout(installed)
            require_no_collisions(checkout, candidate)
            progress(root, record, "replacing_code")
            git(checkout, "-c", "core.hooksPath=/dev/null", "merge", "--ff-only", candidate)
            if plan["migrations"] or arguments.seed:
                record["data_mutated"] = True
                progress(root, record, "migrating")
                if plan["migrations"]:
                    admin(prepared, checkout, "migrate")
                if arguments.seed:
                    admin(prepared, checkout, "seed")
            validate_application(prepared, checkout)
            activate(root, prepared, record)
            write_json(root / "last-update.json", record)
            # Already-loaded control code remains intact while replacing its installed source.
            temporary = root / "stable.py.tmp"
            shutil.copyfile(checkout / "scripts/stable.py", temporary)
            temporary.chmod(0o700)
            temporary.replace(root / "stable.py")
            print(f"Stable is healthy at {candidate}; previous environment and backups retained.")
        except BaseException:
            progress(root, record, "failed")
            try:
                stop_service(root, installed)
                if not record["data_mutated"]:
                    if git(checkout, "rev-parse", "HEAD") != installed["commit"]:
                        git(checkout, "reset", "--keep", installed["commit"])
                    validate_application(installed, checkout)
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
    selected = record.get(arguments.use)
    if not selected:
        fail("recovery record has no selected runtime; manual inspection is required")
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
    if arguments.use == "previous" and record.get("data_mutated") and not arguments.restore_backup:
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
    progress(root, record, "recovering")
    stop_service(root, installed)
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
    validate_application(selected, checkout)
    activate(root, selected, record)
    write_json(root / "last-update.json", record)
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--checkout", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--upstream", default=UPSTREAM)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    installer = commands.add_parser("install", help="prepare a new installation; does not start it")
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
        commands.add_parser(operation)
    updater = commands.add_parser("update")
    updater.add_argument("--dry-run", action="store_true")
    updater.add_argument("--seed", action="store_true", help="explicitly apply deterministic seeds")
    updater.add_argument("--yes", action="store_true")
    recovery = commands.add_parser("recover")
    recovery.add_argument("--use", choices=("previous", "candidate"), required=True)
    recovery.add_argument("--restore-backup", action="store_true")
    recovery.add_argument("--yes", action="store_true")
    arguments = parser.parse_args()
    root = arguments.root.expanduser().absolute()
    try:
        if arguments.command == "status":
            print(json.dumps(status(root, arguments.checkout, arguments.upstream), indent=2))
        elif arguments.command == "serve":
            launch(root, load_installation(root))
        else:
            with locked(root):
                if arguments.command == "install":
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
            diagnostic.write_text((exc.stdout or "") + (exc.stderr or ""))
            diagnostic.chmod(0o600)
            message = f"{Path(exc.cmd[0]).name} failed; inspect {diagnostic}"
        print(f"error: Stable operation failed: {message}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
