#!/usr/bin/env python3
"""Explicit stable setup from a content-identified uncommitted source snapshot.

--prepare captures this checkout, isolates configuration/state and explicitly
migrates/seeds. --start installs commands and the login-persistent LaunchAgent.
Neither operation updates development or legacy data; no Git commit is created.
"""

import argparse
import fcntl
import hashlib
import json
import os
import plistlib
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib import request

from development_state import DEFAULT_CONFIG_ROOT, load_environment_file

ROOT = Path(__file__).resolve().parent.parent
DESTINATION = Path.home() / "local-apps/sayloom-stable"
STATE = Path.home() / ".local/share/local-text/stable"
CONFIGURATION = Path.home() / ".config/local-text/stable"
LABEL = "local.local-text.stable"


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def snapshot_identity(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def source_snapshot(source):
    # Materialize tracked changes and new implementation files, never ignored evidence.
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=source).split(b"\0")
    new = subprocess.check_output(
        [
            "git",
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            "src",
            "scripts",
            "raycast",
            "tests",
            "migrations",
        ],
        cwd=source,
    ).split(b"\0")
    hashes = {}
    for raw in sorted(set(tracked + new)):
        if not raw:
            continue
        relative = raw.decode()
        path = source / relative
        if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
            raise SystemExit(f"Snapshot source must be a regular in-tree file: {relative}")
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    return {
        "base_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source, text=True
        ).strip(),
        "snapshot_sha256": snapshot_identity(hashes),
        "files": hashes,
        "description": "Base plus uncommitted content overlay; base alone is not the snapshot",
    }


def capture_snapshot(source, destination, manifest):
    run("git", "clone", "--quiet", "--no-hardlinks", "--no-checkout", str(source), str(destination))
    run("git", "-C", str(destination), "checkout", "--quiet", "--detach", manifest["base_revision"])
    for relative, expected in manifest["files"].items():
        target = destination / relative
        if expected is None:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, target)
    (destination / "source-snapshot.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (destination / "source-overlay.patch").write_bytes(
        subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=source)
    )
    verify_snapshot(destination)


def verify_snapshot(directory):
    if directory.is_symlink():
        raise SystemExit("Stable snapshot directory must not be a symlink")
    try:
        manifest = json.loads((directory / "source-snapshot.json").read_text())
    except (OSError, ValueError) as error:
        raise SystemExit(
            "Stable source manifest missing or unreadable; inspect initial setup"
        ) from error
    actual = source_snapshot(directory)
    if not isinstance(manifest, dict) or any(
        manifest.get(key) != actual[key] for key in ("files", "base_revision", "snapshot_sha256")
    ):
        raise SystemExit(
            "Installed snapshot differs from its content manifest; reverify before update"
        )
    return manifest


def prepare():
    if any(path.exists() for path in (DESTINATION, STATE, CONFIGURATION)):
        raise SystemExit("Stable paths already exist; refusing to overwrite an installed snapshot")
    environment = load_environment_file(DEFAULT_CONFIG_ROOT / "environment")
    if not environment.get("LOCAL_TEXT_OPENAI_API_KEY"):
        raise SystemExit("Configured OpenAI credential required; no credential values printed")
    manifest = source_snapshot(ROOT)
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    capture_snapshot(ROOT, DESTINATION, manifest)
    # Deliberate installation, locked dependency set, no automatic pull/update at login.
    run(shutil.which("uv") or "uv", "sync", "--frozen", cwd=DESTINATION)
    STATE.mkdir(mode=0o700, parents=True)
    CONFIGURATION.mkdir(mode=0o700, parents=True)
    credential_file = CONFIGURATION / "environment"
    credential_file.write_text("".join(f"{key}={value}\n" for key, value in environment.items()))
    credential_file.chmod(0o600)
    setup_environment = {
        key: value for key, value in os.environ.items() if not key.startswith("LOCAL_TEXT_")
    }
    setup_environment.update(LOCAL_TEXT_PROFILE="release", LOCAL_TEXT_STATE_DIRECTORY=str(STATE))
    for operation in ("migrate", "seed"):
        run(
            str(DESTINATION / ".venv/bin/python"),
            "-m",
            "local_text.admin",
            operation,
            cwd=DESTINATION,
            env=setup_environment,
        )
    print(
        f"Prepared content-identified snapshot {manifest['snapshot_sha256']}; service not started"
    )


def stable_agent():
    return Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"


def stable_definition():
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(DESTINATION / ".venv/bin/python"),
            str(DESTINATION / "scripts/run-stable.py"),
        ],
        "WorkingDirectory": str(DESTINATION),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "Umask": 0o077,
        "StandardOutPath": str(STATE / "service.stdout.log"),
        "StandardErrorPath": str(STATE / "service.stderr.log"),
    }


def service(action):
    domain = f"gui/{os.getuid()}"
    if action == "bootstrap":
        run("launchctl", action, domain, str(stable_agent()))
    else:
        run("launchctl", action, f"{domain}/{LABEL}")
        # A free port does not mean launchd has finished unregistering the old job.
        for _ in range(30):
            if loaded_service() is None:
                with socket.socket() as probe:
                    # Match uvicorn: closed HTTP connections in TIME_WAIT are not listeners.
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    try:
                        probe.bind(("127.0.0.1", 7532))
                        return
                    except OSError:
                        pass
            time.sleep(0.1)
        raise SystemExit(
            "Stable shutdown incomplete: launchd job remains loaded or 7532 remains occupied; "
            "refusing to replace its owner"
        )


def loaded_service():
    result = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        missing = f'Could not find service "{LABEL}" in domain for user gui: {os.getuid()}'
        if result.returncode == 113 and missing in result.stderr.splitlines():
            return None
        raise SystemExit(
            f"Cannot inspect Stable service (launchctl exit {result.returncode}); "
            "service state is unknown, not confirmed absent"
        )
    lines = [line.strip() for line in result.stdout.splitlines()]
    arguments = lines.index("arguments = {") if "arguments = {" in lines else -1
    expected_arguments = stable_definition()["ProgramArguments"]
    if (
        f"path = {stable_agent()}" not in lines
        or f"program = {DESTINATION / '.venv/bin/python'}" not in lines
        or f"working directory = {DESTINATION}" not in lines
        or arguments < 0
        or lines[arguments + 1 : arguments + 4] != [*expected_arguments, "}"]
    ):
        raise SystemExit("Loaded Stable service is not owned by the expected installation")
    return lines


def verify_owner():
    agent = stable_agent()
    if agent.is_symlink() or plistlib.loads(agent.read_bytes()) != stable_definition():
        raise SystemExit(
            "Stable LaunchAgent differs from the installer definition; reverify its owner"
        )
    lines = loaded_service()
    if not lines:
        raise SystemExit("Stable service is not loaded; use initial setup or explicit recovery")
    pids = [line.removeprefix("pid = ") for line in lines if line.startswith("pid = ")]
    if len(pids) != 1 or not pids[0].isdigit():
        raise SystemExit("Stable service has no verified running PID")
    listener = subprocess.run(
        ["lsof", "-nP", "-iTCP:7532", "-sTCP:LISTEN", "-t"],
        capture_output=True,
        text=True,
        check=False,
    )
    process = subprocess.check_output(["ps", "-p", pids[0], "-o", "command="], text=True)
    expected = [
        "uvicorn",
        "local_text.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "7532",
        "--app-dir",
        str(DESTINATION / "src"),
        "--no-access-log",
    ]
    # Executing uvicorn's Python entry-point script exposes its shebang in ps.
    entrypoint = [
        str(DESTINATION / ".venv/bin/python"),
        str(DESTINATION / ".venv/bin/uvicorn"),
        *expected[1:],
    ]
    if (
        listener.returncode
        or set(listener.stdout.split()) != set(pids)
        or shlex.split(process) not in (expected, entrypoint)
    ):
        raise SystemExit(
            "Port 7532 is not owned by the verified Stable process; refusing to stop it"
        )


def verify_health(*, attempts=1):
    for _ in range(attempts):
        try:
            with request.urlopen("http://127.0.0.1:7532/health", timeout=1) as response:
                health = json.load(response)
            if (
                health.get("status") == "ok"
                and health.get("profile") == "release"
                and health.get("development_state") is None
                and health.get("database", {}).get("state") == "current"
            ):
                return
        except (OSError, ValueError):
            pass
        if attempts > 1:
            time.sleep(1)
    raise SystemExit("Stable release on 7532 did not become healthy")


def compatible_snapshot(previous, candidate):
    protected = {
        "pyproject.toml",
        "uv.lock",
        "src/local_text/database.py",
        "scripts/run-stable.py",
        "scripts/development_state.py",
    }
    protected.update(
        path
        for manifest in (previous, candidate)
        for path in manifest["files"]
        if path.startswith("migrations/") or path == "alembic.ini"
    )
    changed = sorted(
        path for path in protected if previous["files"].get(path) != candidate["files"].get(path)
    )
    if changed:
        raise SystemExit(
            "Separate dependency/schema/launcher update required before Stable: "
            + ", ".join(changed)
            + ". No sync or migrations were run."
        )


def check_staged_snapshot(staging):
    # Use the unchanged installed environment, never uv sync or database migrations.
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("LOCAL_TEXT_") and not key.endswith("API_KEY")
    }
    environment["PYTHONPATH"] = str(staging / "src")
    try:
        run(
            str(DESTINATION / ".venv/bin/python"),
            "-B",
            "-c",
            "from pathlib import Path; from local_text.database import ApplicationDatabase; "
            "import local_text.cleanup; import sys; "
            "ApplicationDatabase(Path(sys.argv[1])).assert_ready()",
            str(STATE / "local-text.sqlite3"),
            cwd=staging,
            env=environment,
            capture_output=True,
        )
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            "Staged source cannot use the installed environment/schema. Stable unchanged; "
            "arrange a separate reviewed dependency/schema update. No sync or migrations ran."
        ) from error


def update(source, *, confirmed=False, dry_run=False):
    previous = verify_snapshot(DESTINATION)
    candidate = source_snapshot(source)
    branch = (
        subprocess.check_output(["git", "branch", "--show-current"], cwd=source, text=True).strip()
        or "detached HEAD"
    )
    print(f"Source branch: {branch}; base: {candidate['base_revision']}")
    print(f"Stable snapshot: {previous['snapshot_sha256']}")
    print(f"Candidate snapshot: {candidate['snapshot_sha256']}")
    changes = [
        path
        for path in sorted(previous["files"].keys() | candidate["files"].keys())
        if previous["files"].get(path) != candidate["files"].get(path)
    ]
    print("Changed paths:\n" + ("\n".join(changes) or "(none)"))
    compatible_snapshot(previous, candidate)
    if not STATE.is_dir() or not CONFIGURATION.is_dir():
        raise SystemExit("Stable state/configuration missing; use explicit initial setup")
    verify_owner()
    verify_health()
    if dry_run:
        print("Dry run only; Stable, settings, data and commands are unchanged")
        return
    if not confirmed:
        if not sys.stdin.isatty():
            raise SystemExit("Stable replacement requires confirmation; rerun with --yes")
        if input(
            "Replace Stable code and restart only its release service? [y/N] "
        ).lower() not in {
            "y",
            "yes",
        }:
            print("Stable preserved")
            return
    with (DESTINATION.parent / ".sayloom-stable-update.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another Stable update is running") from None
        staging = Path(tempfile.mkdtemp(prefix=".sayloom-stable-stage-", dir=DESTINATION.parent))
        rollback = staging.with_name(staging.name.replace("stage-", "rollback-"))
        stopped = swapped = False
        try:
            capture_snapshot(source, staging, candidate)
            check_staged_snapshot(staging)
            shutil.copytree(DESTINATION / ".venv", staging / ".venv", symlinks=True)
            if verify_snapshot(DESTINATION) != previous or source_snapshot(source) != candidate:
                raise SystemExit(
                    "Source or installed snapshot changed during staging; retry review"
                )
            verify_owner()
            verify_health()
            stopped = True
            phase = "stopping Stable"
            service("bootout")
            phase = "replacing Stable source"
            DESTINATION.rename(rollback)
            try:
                staging.rename(DESTINATION)
            except BaseException:
                rollback.rename(DESTINATION)
                raise
            swapped = True
            phase = "starting updated Stable"
            service("bootstrap")
            phase = "checking updated Stable health"
            verify_health(attempts=30)
            phase = "verifying updated Stable owner"
            verify_owner()
        except BaseException as error:
            if stopped:
                try:
                    if loaded_service() is not None:
                        service("bootout")
                    if swapped:
                        DESTINATION.rename(staging)
                        rollback.rename(DESTINATION)
                    service("bootstrap")
                    verify_health(attempts=30)
                    verify_owner()
                except BaseException as recovery:
                    raise SystemExit(
                        f"Stable update failed while {phase}: {error}. "
                        f"Recovery needs manual action; prior source: {rollback}; "
                        f"recovery error: {recovery}"
                    ) from error
                raise SystemExit(
                    f"Stable update failed while {phase}: {error}; "
                    "prior runnable snapshot/service restored"
                ) from error
            raise
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        print(f"Updated Stable to {candidate['snapshot_sha256']}; rollback snapshot: {rollback}")


def start():
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", 7532))
        except OSError as exc:
            raise SystemExit(
                "7532 is occupied; reverify and stop its approved owner first"
            ) from exc
    verify_snapshot(DESTINATION)
    # Generate commands from the verified installed snapshot, not newer checkout edits.
    import sys

    sys.path.insert(0, str(DESTINATION / "src"))
    from local_text.targets import INITIAL_TARGETS, command_filename, generate_command

    commands = Path.home() / ".config/raycast/scripts"
    planned = {
        commands / "stable-open-sayloom.sh": (
            DESTINATION / "raycast/stable/open-sayloom.sh"
        ).read_text()
    }
    for target_id, definition in INITIAL_TARGETS:
        planned[commands / command_filename(target_id, stable=True)] = generate_command(
            target_id, definition, stable=True
        ).content
    if any(path.exists() or path.is_symlink() for path in planned):
        raise SystemExit("Stable command collision; refusing to overwrite")
    agent = stable_agent()
    if agent.exists():
        raise SystemExit("LaunchAgent already exists; refusing to overwrite")
    for path, text in planned.items():
        path.write_text(text)
        path.chmod(0o700)
    agent.parent.mkdir(parents=True, exist_ok=True)
    agent.write_bytes(plistlib.dumps(stable_definition()))
    run("launchctl", "bootstrap", f"gui/{os.getuid()}", str(agent))
    print("Installed stable commands and login-persistent LaunchAgent on loopback 7532")


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--start", action="store_true")
    args = parser.parse_args()
    prepare() if args.prepare else start()
