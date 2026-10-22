#!/usr/bin/env python3
"""Explicit stable setup from a content-identified uncommitted source snapshot.

--prepare captures this checkout, isolates configuration/state and explicitly
migrates/seeds. --start installs commands and the login-persistent LaunchAgent.
Neither operation updates development or legacy data; no Git commit is created.
"""

import argparse
import hashlib
import json
import os
import plistlib
import shutil
import socket
import subprocess
from pathlib import Path

from development_state import DEFAULT_CONFIG_ROOT, load_environment_file

ROOT = Path(__file__).resolve().parent.parent
DESTINATION = Path.home() / "local-apps/sayloom-stable"
STATE = Path.home() / ".local/share/local-text/stable"
CONFIGURATION = Path.home() / ".config/local-text/stable"
LABEL = "local.local-text.stable"


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def prepare():
    if any(path.exists() for path in (DESTINATION, STATE, CONFIGURATION)):
        raise SystemExit("Stable paths already exist; refusing to overwrite an installed snapshot")
    environment = load_environment_file(DEFAULT_CONFIG_ROOT / "environment")
    if not environment.get("LOCAL_TEXT_OPENAI_API_KEY"):
        raise SystemExit("Configured OpenAI credential required; no credential values printed")
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    run("git", "clone", "--no-hardlinks", "--no-checkout", str(ROOT), str(DESTINATION))
    run("git", "-C", str(DESTINATION), "checkout", "--detach", base)
    # Materialize tracked changes and new implementation files, never ignored evidence.
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).split(b"\0")
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
        ],
        cwd=ROOT,
    ).split(b"\0")
    hashes = {}
    for raw in sorted(set(tracked + new)):
        if not raw:
            continue
        relative = raw.decode()
        source, destination = ROOT / relative, DESTINATION / relative
        if not source.exists():
            destination.unlink(missing_ok=True)
            hashes[relative] = None
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            hashes[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    (DESTINATION / "source-snapshot.json").write_text(
        json.dumps(
            {
                "base_revision": base,
                "snapshot_sha256": identity,
                "files": hashes,
                "description": (
                    "Base plus uncommitted content overlay; base alone does not contain this tool"
                ),
            },
            indent=2,
        )
        + "\n"
    )
    (DESTINATION / "source-overlay.patch").write_bytes(
        subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=ROOT)
    )
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
    print(f"Prepared content-identified snapshot {identity}; service not started")


def start():
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", 7532))
        except OSError as exc:
            raise SystemExit(
                "7532 is occupied; reverify and stop its approved owner first"
            ) from exc
    manifest = json.loads((DESTINATION / "source-snapshot.json").read_text())
    for relative, expected in manifest["files"].items():
        path = DESTINATION / relative
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        if actual != expected:
            raise SystemExit(f"Installed snapshot differs: {relative}")
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
    agent = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
    if agent.exists():
        raise SystemExit("LaunchAgent already exists; refusing to overwrite")
    for path, text in planned.items():
        path.write_text(text)
        path.chmod(0o700)
    agent.parent.mkdir(parents=True, exist_ok=True)
    agent.write_bytes(
        plistlib.dumps(
            {
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
        )
    )
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
