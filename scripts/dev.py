#!/usr/bin/env python3
"""State-scoped local development operations for Sayloom."""

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib import request

from development_state import (
    APPLICATION_ENVIRONMENT_KEYS,
    DEFAULT_STATE_ROOT,
    DEVELOPMENT_PORT,
    State,
    configuration_paths,
    fail,
    load_state,
    port_is_available,
    repository_root,
    state_configuration,
    state_environment,
    state_label,
    state_path,
    states_on_port,
    write_state,
)


def print_state(state: State) -> None:
    print(f"State: {state.name}")
    print(f"Repository: {state.repository_root}")
    print(f"Database: {Path(state.state_directory) / 'local-text.sqlite3'}")
    print(f"Service: {state.label}")
    print(f"Port: {state.port}")


def initialize(state: State) -> None:
    for admin_command in ("migrate", "seed"):
        subprocess.run(
            ["uv", "run", "python", "-m", "local_text.admin", admin_command],
            cwd=repository_root(),
            env=state_environment(state),
            check=True,
        )


def print_configuration_status(state: State) -> None:
    shared, selected = configuration_paths(state)
    configuration = state_configuration(state)
    print(f"Shared configuration: {shared} ({'present' if shared.exists() else 'missing'})")
    print(f"State configuration: {selected} ({'present' if selected.exists() else 'missing'})")
    credential = "configured" if "LOCAL_TEXT_GEMINI_API_KEY" in configuration else "missing"
    print(f"Gemini credential: {credential}")
    print(f"Gemini model: {configuration.get('LOCAL_TEXT_GEMINI_MODEL', 'application default')}")
    print(
        "Cleanup timeout: "
        f"{configuration.get('LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS', 'application default')}"
    )


def print_status(state: State) -> int:
    print_state(state)
    print_configuration_status(state)
    sys.stdout.flush()
    return subprocess.run(
        ["uv", "run", "python", "-m", "local_text.admin", "schema"],
        cwd=repository_root(),
        env=state_environment(state),
        check=False,
    ).returncode


def restart(state: State) -> None:
    root = repository_root()
    clean_environment = {
        key: value for key, value in os.environ.items() if key not in APPLICATION_ENVIRONMENT_KEYS
    }
    for check in (
        ["uv", "sync", "--locked"],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "pytest"],
        ["/usr/bin/env", "node", "--check", "src/local_text/static/app.js"],
        ["git", "diff", "--check"],
    ):
        subprocess.run(check, cwd=root, env=clean_environment, check=True)
    for shell_script in sorted((*root.glob("scripts/*.sh"), *root.glob("raycast/*.sh"))):
        subprocess.run(["/bin/sh", "-n", str(shell_script)], env=clean_environment, check=True)
    domain = f"gui/{os.getuid()}"
    stopped_service = False
    state_root = Path(state.state_directory).parent
    for candidate in states_on_port(state_root, state.port):
        service = f"{domain}/{candidate.label}"
        if (
            subprocess.run(
                ["launchctl", "print", service],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode
            == 0
        ):
            subprocess.run(["launchctl", "bootout", service], check=True)
            stopped_service = True
    if stopped_service:
        time.sleep(1)
    if not port_is_available(state.port):
        fail(
            f"development port {state.port} is occupied by an unregistered process; "
            "refusing to stop it"
        )
    database_path = Path(state.state_directory) / "local-text.sqlite3"
    if database_path.exists():
        backups = Path(state.state_directory) / "backups"
        backups.mkdir(mode=0o700, exist_ok=True)
        timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup_path = backups / f"local-text-{timestamp}-{os.getpid()}.sqlite3"
        with sqlite3.connect(database_path) as source, sqlite3.connect(backup_path) as destination:
            source.backup(destination)
        os.chmod(backup_path, 0o600)
        print(f"Backed up selected state to {backup_path}")
    initialize(state)
    log_directory = Path(state.state_directory) / "logs"
    log_directory.mkdir(mode=0o700, exist_ok=True)
    os.chmod(log_directory, 0o700)
    for filename in ("service.log", "service-error.log"):
        log_path = log_directory / filename
        log_path.touch(mode=0o600, exist_ok=True)
        os.chmod(log_path, 0o600)
    plist = Path.home() / "Library/LaunchAgents" / f"{state.label}.plist"
    plist.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    rendered = subprocess.run(
        [
            str(root / ".venv/bin/python"),
            str(root / "scripts/render-launchd-plist.py"),
            "--state-root",
            str(Path(state.state_directory).parent),
            "--state",
            state.name,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    with tempfile.NamedTemporaryFile(
        mode="w", dir=plist.parent, prefix=f".{state.label}.", delete=False
    ) as temporary:
        temporary.write(rendered)
        temporary_plist = Path(temporary.name)
    try:
        os.chmod(temporary_plist, 0o600)
        subprocess.run(["plutil", "-lint", str(temporary_plist)], check=True)
        temporary_plist.replace(plist)
    finally:
        temporary_plist.unlink(missing_ok=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)
    for _ in range(30):
        try:
            health_url = f"http://127.0.0.1:{state.port}/health"
            with request.urlopen(health_url, timeout=1) as response:
                health = json.load(response)
                if response.status == 200 and health.get("status") == "ok":
                    print(f"Verified {state.label} on 127.0.0.1:{state.port}")
                    return
        except OSError:
            time.sleep(1)
    fail("selected development service did not become healthy after restart")


def command(arguments: argparse.Namespace) -> int:
    root = arguments.state_root.expanduser().resolve()
    if arguments.command == "create":
        directory = state_path(root, arguments.name)
        if directory.exists():
            fail(f"state {arguments.name!r} already exists")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        directory.mkdir(mode=0o700)
        state = State(
            name=arguments.name,
            repository_root=str(repository_root().resolve()),
            state_directory=str(directory),
            label=state_label(arguments.name),
            port=DEVELOPMENT_PORT,
        )
        write_state(state)
        print_state(state)
        return 0

    if arguments.command == "status" and arguments.state is None:
        states = sorted(states_on_port(root, DEVELOPMENT_PORT), key=lambda state: state.name)
        if not states:
            print(f"No development states found in {root}")
            return 0
        return_code = 0
        for index, state in enumerate(states):
            if index:
                print()
            return_code = max(return_code, print_status(state))
        return return_code

    state = load_state(root, arguments.state)
    if arguments.command == "status":
        return print_status(state)
    print_state(state)
    if arguments.command == "initialize":
        initialize(state)
        return 0
    if arguments.command == "restart":
        restart(state)
        return 0
    fail(f"unsupported command {arguments.command!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="create an external state manifest")
    create.add_argument("name")
    for name in ("initialize", "restart"):
        operation = subparsers.add_parser(name)
        operation.add_argument("--state", required=True)
    status = subparsers.add_parser("status")
    status.add_argument("--state")
    arguments = parser.parse_args()
    try:
        raise SystemExit(command(arguments))
    except subprocess.CalledProcessError as error:
        print(f"error: command failed with status {error.returncode}: {error.cmd}", file=sys.stderr)
        raise SystemExit(error.returncode) from error


if __name__ == "__main__":
    main()
