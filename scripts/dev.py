#!/usr/bin/env python3
"""Manage checkout-scoped Sayloom development environments."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import runpy
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from collections import deque
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace
from pathlib import Path
from urllib import parse, request

from development_state import (
    APPLICATION_ENVIRONMENT_KEYS,
    DEFAULT_STATE_ROOT,
    DEVELOPMENT_PORT,
    LEGACY_STATE_ROOT,
    MANIFEST_NAME,
    MIGRATION_MARKER_NAME,
    PRODUCTION_PORT,
    State,
    available_port,
    configuration_paths,
    fail,
    legacy_configuration_path,
    load_state,
    migrate_state_configuration,
    port_is_available,
    registered_states,
    repository_root,
    state_configuration,
    state_environment,
    state_label,
    state_path,
    states_on_port,
    write_state,
)
from raycast_aliases import DEFAULT_DIRECTORY as RAYCAST_DIRECTORY
from raycast_aliases import AliasPlan, apply_plan, plan_install


class HelpFormatter(argparse.RawDescriptionHelpFormatter):
    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=26, width=88)


MIGRATION_LOCK_NAME = ".state-root-migration.lock"
MIGRATION_STAGING_NAME = ".state-root-migration-staging"


def positive_line_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("lines must be a positive integer") from None
    if count < 1:
        raise argparse.ArgumentTypeError("lines must be a positive integer")
    return count


def print_state(state: State) -> None:
    print(f"State: {state.name}")
    print(f"Repository: {state.repository_root}")
    print(f"State directory: {state.state_directory}")
    print(f"Database: {Path(state.state_directory) / 'local-text.sqlite3'}")
    print(f"Service: {state.label}")
    print(f"Port: {state.port}")


def run_admin(state: State, *arguments: str) -> int:
    return subprocess.run(
        ["uv", "run", "python", "-m", "local_text.admin", *arguments],
        cwd=repository_root(),
        env=state_environment(state),
        check=False,
    ).returncode


def initialize(state: State) -> None:
    migrate_state_configuration(state)
    for admin_command in ("migrate", "seed"):
        subprocess.run(
            ["uv", "run", "python", "-m", "local_text.admin", admin_command],
            cwd=repository_root(),
            env=state_environment(state),
            check=True,
        )


def print_configuration_status(state: State) -> None:
    shared, selected = configuration_paths(state)
    legacy = legacy_configuration_path(state)
    configuration = state_configuration(state)
    print(f"Shared configuration: {shared} ({'present' if shared.exists() else 'missing'})")
    if selected.exists():
        state_location = f"{selected} (present)"
    elif legacy.exists():
        state_location = f"{legacy} (present; moves on init or restart)"
    else:
        state_location = f"{selected} (missing)"
    print(f"State configuration: {state_location}")
    gemini_credential = "configured" if "LOCAL_TEXT_GEMINI_API_KEY" in configuration else "missing"
    openai_credential = "configured" if "LOCAL_TEXT_OPENAI_API_KEY" in configuration else "missing"
    route_order = configuration.get("LOCAL_TEXT_CLEANUP_ROUTE_ORDER", "legacy Gemini-only")
    print(f"Cleanup route order: {route_order}")
    print(f"Gemini credential: {gemini_credential}")
    print(f"Gemini model: {configuration.get('LOCAL_TEXT_GEMINI_MODEL', 'application default')}")
    print(
        "Gemini quota group: "
        f"{'configured' if 'LOCAL_TEXT_GEMINI_QUOTA_GROUP_ID' in configuration else 'missing'}"
    )
    print(f"OpenAI credential: {openai_credential}")
    print(f"OpenAI model: {configuration.get('LOCAL_TEXT_OPENAI_MODEL', 'missing')}")
    print(
        "OpenAI quota group: "
        f"{'configured' if 'LOCAL_TEXT_OPENAI_QUOTA_GROUP_ID' in configuration else 'missing'}"
    )
    print(
        "OpenRouter credential: "
        f"{'configured' if 'LOCAL_TEXT_OPENROUTER_API_KEY' in configuration else 'missing'}"
    )
    for key in ("MODEL", "MODELS", "ENDPOINTS"):
        value = configuration.get(f"LOCAL_TEXT_OPENROUTER_{key}", "missing")
        print(f"OpenRouter {key.lower()}: {value}")
    acknowledgement = configuration.get("LOCAL_TEXT_CLEANUP_PAID_DATA_ACKNOWLEDGEMENT")
    print(
        "Paid-data acknowledgement: "
        f"{'configured' if acknowledgement == 'paid-external-cleanup-v1' else 'missing or invalid'}"
    )
    print(
        "Cleanup timeout: "
        f"{configuration.get('LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS', 'application default')}"
    )


def preflight(state: State) -> None:
    state_configuration(state)
    print(f"Configuration ready for isolated-state restart: {state.name}")


def print_status(state: State) -> int:
    print_state(state)
    print_configuration_status(state)
    sys.stdout.flush()
    return run_admin(state, "schema")


def states_for_current_checkout(root: Path) -> list[State]:
    current_repository = repository_root().resolve()
    return sorted(
        (
            state
            for state in registered_states(root)
            if Path(state.repository_root).resolve() == current_repository
        ),
        key=lambda state: state.name,
    )


def state_for_current_checkout(root: Path) -> State | None:
    matches = states_for_current_checkout(root)
    if len(matches) > 1:
        names = ", ".join(state.name for state in matches)
        fail(f"this checkout has multiple development states ({names}); remove the extras")
    return matches[0] if matches else None


def resolve_state(root: Path, name: str | None = None) -> State:
    if name is not None:
        return load_state(root, name)
    state = state_for_current_checkout(root)
    if state is None:
        fail("this checkout has no development state; run scripts/dev.py init")
    return state


def default_state_name() -> str:
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repository_root(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    source = branch or repository_root().name
    normalized = re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-") or "development"
    if len(normalized) <= 48:
        return normalized
    digest = hashlib.sha256(source.encode()).hexdigest()[:8]
    return f"{normalized[:39].rstrip('-')}-{digest}"


def create_state(root: Path, name: str | None = None, port: int | None = None) -> State:
    matches = states_for_current_checkout(root)
    if matches:
        names = ", ".join(state.name for state in matches)
        fail(f"this checkout already has a development state ({names})")
    generated_name = name is None
    name = name or default_state_name()
    directory = state_path(root, name)
    if directory.exists() and generated_name:
        suffix = hashlib.sha256(str(repository_root().resolve()).encode()).hexdigest()[:8]
        name = f"{name[:39].rstrip('-')}-{suffix}"
        directory = state_path(root, name)
    if directory.exists():
        fail(f"state {name!r} already exists")

    if port is None:
        port = available_port(root)
    elif not 1024 <= port <= 65535:
        fail("development port must be between 1024 and 65535")
    elif port == PRODUCTION_PORT:
        fail(f"port {PRODUCTION_PORT} is reserved for production")
    else:
        owners = states_on_port(root, port)
        if owners:
            fail(f"development port {port} is already assigned to state {owners[0].name!r}")
        if not port_is_available(port):
            fail(f"development port {port} is occupied by an unregistered process")

    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    directory.mkdir(mode=0o700)
    state = State(
        name=name,
        repository_root=str(repository_root().resolve()),
        state_directory=str(directory),
        label=state_label(name),
        port=port,
    )
    write_state(state)
    return state


def state_tree_entries(root: Path) -> dict[str, tuple[object, ...]]:
    entries: dict[str, tuple[object, ...]] = {}

    def visit(directory: Path, prefix: Path) -> None:
        for entry in os.scandir(directory):
            relative = prefix / entry.name
            if relative == Path(MANIFEST_NAME):
                continue
            metadata = entry.stat(follow_symlinks=False)
            mode = stat.S_IMODE(metadata.st_mode)
            if stat.S_ISLNK(metadata.st_mode):
                entries[str(relative)] = ("symlink", mode, os.readlink(entry.path))
            elif stat.S_ISDIR(metadata.st_mode):
                entries[str(relative)] = ("directory", mode)
                visit(Path(entry.path), relative)
            elif stat.S_ISREG(metadata.st_mode):
                digest = hashlib.sha256()
                with open(entry.path, "rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                entries[str(relative)] = ("file", mode, metadata.st_size, digest.hexdigest())
            else:
                fail(f"state contains unsupported filesystem entry: {relative}")

    visit(root, Path())
    return entries


def verify_migrated_state(
    state: State,
    destination: Path,
    *,
    registration_directory: Path | None = None,
    divergent: bool = False,
) -> None:
    prefix = (
        f"divergent destination state {state.name!r}"
        if divergent
        else f"verification failed for state {state.name!r}"
    )
    try:
        manifest = json.loads((destination / MANIFEST_NAME).read_text())
        registered_at = registration_directory or destination
        expected = asdict(replace(state, state_directory=str(registered_at.resolve())))
        if manifest != expected:
            fail(f"{prefix}: registration differs")
        if state_tree_entries(Path(state.state_directory)) != state_tree_entries(destination):
            fail(f"{prefix}: state data differs")
    except (OSError, TypeError, json.JSONDecodeError) as error:
        fail(f"{prefix}: {error}")


def write_migration_marker(marker: Path, source_root: Path, states: list[State]) -> None:
    temporary = marker.with_suffix(".tmp")
    temporary.unlink(missing_ok=True)
    payload = {
        "source_root": str(source_root),
        "states": sorted(state.name for state in states),
    }
    with temporary.open("x") as output:
        json.dump(payload, output, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.chmod(temporary, 0o600)
    temporary.replace(marker)


def preflight_state_root_migration(
    source_root: Path, destination_root: Path
) -> tuple[list[State], list[tuple[State, Path]]]:
    states = sorted(registered_states(source_root), key=lambda state: state.name)
    marker = destination_root / MIGRATION_MARKER_NAME
    if not states:
        if marker.exists():
            fail("migration is incomplete and its source states are unavailable")
        return states, []

    marker_payload = {
        "source_root": str(source_root),
        "states": [state.name for state in states],
    }
    if marker.exists():
        try:
            if json.loads(marker.read_text()) != marker_payload:
                fail("incomplete migration marker does not match this migration")
        except (OSError, json.JSONDecodeError) as error:
            fail(f"invalid incomplete migration marker: {error}")

    missing: list[tuple[State, Path]] = []
    for state in states:
        destination = destination_root / state.name
        if destination.exists() or destination.is_symlink():
            verify_migrated_state(state, destination, divergent=True)
        else:
            missing.append((state, destination))
    return states, missing


def stop_migration_services(states: list[State]) -> None:
    loaded = [state for state in states if service_is_loaded(state)]
    for state in loaded:
        try:
            stop_service(state)
        except (OSError, subprocess.CalledProcessError) as error:
            fail(f"could not stop development service {state.name!r}: {error}")
    remaining = [state.name for state in loaded if service_is_loaded(state)]
    if remaining:
        fail("development services did not stop: " + ", ".join(remaining))


def migrate_state_root(source_root: Path, destination_root: Path) -> None:
    source_root = source_root.expanduser().resolve()
    destination_root = destination_root.expanduser().resolve()
    if source_root == destination_root:
        fail("source and destination state roots must differ")

    states, _missing = preflight_state_root_migration(source_root, destination_root)
    if not states:
        if registered_states(destination_root):
            print("Development-state registration already uses the destination root.")
        else:
            print("No registered development states require migration.")
        return

    stop_migration_services(states)

    destination_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(destination_root, 0o700)
    lock_path = destination_root / MIGRATION_LOCK_NAME
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        marker = destination_root / MIGRATION_MARKER_NAME
        locked_states, missing = preflight_state_root_migration(source_root, destination_root)
        if locked_states != states:
            fail("source registrations changed during migration preflight")

        staging = destination_root / MIGRATION_STAGING_NAME
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(mode=0o700)
        try:
            for state, destination in missing:
                staged = staging / state.name
                shutil.copytree(
                    state.state_directory,
                    staged,
                    symlinks=True,
                    copy_function=shutil.copy2,
                )
                migrated = replace(state, state_directory=str(destination.resolve()))
                manifest = staged / MANIFEST_NAME
                manifest.write_text(json.dumps(asdict(migrated), indent=2) + "\n")
                os.chmod(manifest, 0o600)
                verify_migrated_state(
                    state,
                    staged,
                    registration_directory=destination,
                )

            if not marker.exists():
                write_migration_marker(marker, source_root, states)

            for state, destination in missing:
                (staging / state.name).rename(destination)
            for state in states:
                verify_migrated_state(state, destination_root / state.name)

            for state in states:
                plist_path(state).unlink(missing_ok=True)
            marker.unlink()
            for state in states:
                shutil.rmtree(state.state_directory)
            print(
                f"Migrated {len(states)} registered development states to {destination_root}."
            )
            print(
                "Development services remain stopped; run scripts/dev.py restart from each "
                "checkout you want to start."
            )
        except OSError as error:
            fail(f"state-root migration failed: {error}")
        finally:
            if not marker.exists():
                shutil.rmtree(staging, ignore_errors=True)


def clean_environment() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items() if key not in APPLICATION_ENVIRONMENT_KEYS
    }


def service_name(state: State) -> str:
    return f"gui/{os.getuid()}/{state.label}"


def service_is_loaded(state: State) -> bool:
    if sys.platform != "darwin":
        return False
    return (
        subprocess.run(
            ["launchctl", "print", service_name(state)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def stop_service(state: State) -> bool:
    if not service_is_loaded(state):
        return False
    subprocess.run(["launchctl", "bootout", service_name(state)], check=True)
    return True


def plist_path(state: State) -> Path:
    return Path.home() / "Library/LaunchAgents" / f"{state.label}.plist"


def prepare_service_files(state: State) -> None:
    log_directory = Path(state.state_directory) / "logs"
    log_directory.mkdir(mode=0o700, exist_ok=True)
    os.chmod(log_directory, 0o700)
    for filename in ("service.log", "service-error.log"):
        log_path = log_directory / filename
        log_path.touch(mode=0o600, exist_ok=True)
        os.chmod(log_path, 0o600)


def print_log_entries(label: str, entries: list[str]) -> None:
    print(f"==> {label} <==")
    for entry in entries:
        prefix = ""
        try:
            parsed = json.loads(entry)
        except json.JSONDecodeError:
            decoder = json.JSONDecoder()
            for index, character in enumerate(entry):
                if character not in "{[":
                    continue
                try:
                    parsed, end = decoder.raw_decode(entry, index)
                except json.JSONDecodeError:
                    continue
                if entry[end:].strip():
                    continue
                prefix = entry[:index].rstrip()
                break
            else:
                print(entry, end="" if entry.endswith("\n") else "\n")
                continue
        if prefix:
            print(prefix)
        print(json.dumps(parsed, indent=2, ensure_ascii=False))


def marker_matches_descriptor(marker: Path, descriptor: int) -> bool:
    try:
        opened = os.fstat(descriptor)
        current = os.stat(marker, follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISREG(opened.st_mode)
        and stat.S_ISREG(current.st_mode)
        and (opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino)
    )


def remove_inactive_diagnostics_marker(marker: Path) -> None:
    descriptor = os.open(marker, os.O_RDWR | os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            fail("provider traffic diagnostics marker is invalid")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("another provider traffic diagnostics session is active")
        if not marker_matches_descriptor(marker, descriptor):
            fail("provider traffic diagnostics marker is invalid")
        marker.unlink()
    finally:
        os.close(descriptor)


@contextmanager
def provider_traffic_diagnostics(state: State):
    marker = Path(state.state_directory) / ".provider-traffic-diagnostics"
    descriptor: int | None = None
    try:
        if marker.exists() or marker.is_symlink():
            if marker.is_symlink() or not marker.is_file():
                fail("provider traffic diagnostics marker is invalid")
            remove_inactive_diagnostics_marker(marker)
        descriptor = os.open(
            marker,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600,
        )
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.write(descriptor, str(os.getpid()).encode())
    except OSError:
        if descriptor is not None:
            try:
                if marker_matches_descriptor(marker, descriptor):
                    marker.unlink()
            finally:
                os.close(descriptor)
        fail("cannot enable provider traffic diagnostics for the selected state")

    print(
        "WARNING: provider traffic diagnostics are active; logs will contain exact "
        "dictated/transcribed text, prompts, and provider response bodies."
    )
    print("Press Ctrl-C to stop diagnostics and remove the temporary opt-in.")
    sys.stdout.flush()
    try:
        yield
    finally:
        try:
            if descriptor is not None and marker_matches_descriptor(marker, descriptor):
                marker.unlink()
        except OSError:
            pass
        if descriptor is not None:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def show_logs(state: State, *, lines: int, follow: bool) -> None:
    log_directory = Path(state.state_directory) / "logs"
    streams = (
        ("service output", log_directory / "service.log"),
        ("service errors", log_directory / "service-error.log"),
    )
    try:
        if (
            log_directory.is_symlink()
            or not log_directory.is_dir()
            or any(path.is_symlink() or not path.is_file() for _, path in streams)
        ):
            fail("selected development state logs are missing or unreadable")
        with ExitStack() as stack:
            opened = [
                (label, stack.enter_context(path.open())) for label, path in streams
            ]
            output = [(label, list(deque(stream, maxlen=lines))) for label, stream in opened]
            for label, entries in output:
                print_log_entries(label, entries)
            sys.stdout.flush()
            while follow:
                for label, stream in opened:
                    entries = stream.readlines()
                    if not entries:
                        continue
                    print_log_entries(label, entries)
                    sys.stdout.flush()
                time.sleep(0.1)
    except KeyboardInterrupt:
        return
    except (OSError, UnicodeError):
        fail("selected development state logs are missing or unreadable")


def install_service(state: State) -> None:
    root = Path(state.repository_root)
    plist = plist_path(state)
    plist.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    prepare_service_files(state)
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
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)], check=True)


def verify_service(state: State) -> None:
    for _ in range(30):
        try:
            health_url = f"http://127.0.0.1:{state.port}/health"
            with request.urlopen(health_url, timeout=1) as response:
                health = json.load(response)
                if (
                    response.status == 200
                    and health.get("status") == "ok"
                    and health.get("profile") == "development"
                    and health.get("development_state") == state.name
                ):
                    print(f"Verified {state.label} on 127.0.0.1:{state.port}")
                    return
        except (OSError, ValueError):
            time.sleep(1)
    fail("selected development service did not become healthy after restart")


def verify_repository() -> None:
    root = repository_root()
    environment = clean_environment()
    for check in (
        ["uv", "sync", "--locked"],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "pytest"],
        ["/usr/bin/env", "node", "--check", "src/local_text/static/app.js"],
        ["git", "diff", "--check"],
    ):
        subprocess.run(check, cwd=root, env=environment, check=True)
    for shell_script in sorted((*root.glob("scripts/*.sh"), *root.glob("raycast/*.sh"))):
        subprocess.run(["/bin/sh", "-n", str(shell_script)], env=environment, check=True)


def restart(state: State, *, run_checks: bool = True) -> None:
    preflight(state)
    if run_checks:
        verify_repository()
    if stop_service(state):
        time.sleep(1)
    if not port_is_available(state.port):
        state_root = Path(state.state_directory).parent
        owners = [
            candidate.name
            for candidate in states_on_port(state_root, state.port)
            if candidate.name != state.name
        ]
        if owners:
            fail(
                f"development port {state.port} is in use by a registered state; "
                "run scripts/dev.py activate to move this checkout to the Raycast port"
            )
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
    install_service(state)
    verify_service(state)


def activate(root: Path, state: State, *, raycast_directory: Path = RAYCAST_DIRECTORY) -> None:
    try:
        alias_plan = plan_install(
            raycast_directory,
            repository_root(),
            repoint_managed=True,
            installed_only=True,
        )
    except ValueError as error:
        fail(str(error))
    previous_owners = [
        candidate
        for candidate in states_on_port(root, DEVELOPMENT_PORT)
        if candidate.name != state.name
    ]
    if state.port == DEVELOPMENT_PORT and not previous_owners:
        if service_is_loaded(state):
            repoint_raycast_aliases(alias_plan)
            print(f"State {state.name!r} already owns the Raycast port {DEVELOPMENT_PORT}")
            return
        restart(state)
        repoint_raycast_aliases(alias_plan)
        return

    verify_repository()
    affected = [state, *previous_owners]
    loaded_names = {candidate.name for candidate in affected if stop_service(candidate)}
    if loaded_names:
        time.sleep(1)

    excluded = {candidate.name for candidate in affected}
    assigned_ports = {DEVELOPMENT_PORT}
    replacement_ports: list[int] = []
    updated_owners: list[State] = []
    if state.port != DEVELOPMENT_PORT and port_is_available(state.port):
        replacement_ports.append(state.port)
    for owner in previous_owners:
        if replacement_ports:
            port = replacement_ports.pop(0)
        else:
            port = available_port(
                root, excluded_names=excluded, excluded_ports=assigned_ports
            )
        updated = replace(owner, port=port)
        write_state(updated)
        updated_owners.append(updated)
        assigned_ports.add(port)
        excluded.discard(owner.name)
        print(f"Moved state {owner.name!r} to port {port}")

    state = replace(state, port=DEVELOPMENT_PORT)
    write_state(state)
    print(f"Activated state {state.name!r} on Raycast port {DEVELOPMENT_PORT}")

    restart(state, run_checks=False)
    for owner in updated_owners:
        if owner.name in loaded_names and Path(owner.repository_root).is_dir():
            install_service(owner)
            verify_service(owner)
    repoint_raycast_aliases(alias_plan)


def repoint_raycast_aliases(plan: AliasPlan) -> None:
    updated, _verified = apply_plan(plan)
    if updated:
        print(f"Repointed {updated} Raycast aliases to {repository_root()}")


def remove_state(root: Path, state: State, *, confirmed: bool) -> None:
    if not confirmed:
        if not sys.stdin.isatty():
            fail("removal requires confirmation; rerun with --yes")
        answer = input(f"Remove state {state.name!r} and all of its data? [y/N] ")
        if answer.lower() not in {"y", "yes"}:
            print("State preserved")
            return
    stop_service(state)
    plist_path(state).unlink(missing_ok=True)
    legacy = legacy_configuration_path(state)
    legacy.unlink(missing_ok=True)
    for directory in legacy.parents:
        if directory == legacy.parents[3]:
            break
        try:
            directory.rmdir()
        except OSError:
            break
    directory = state_path(root, state.name)
    shutil.rmtree(directory)
    print(f"Removed state {state.name!r}")


def amp_runner_processes(*, required: bool = False) -> dict[Path, set[int]]:
    try:
        processes = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        if required:
            fail("could not inspect Amp runners; preserving development worktrees")
        return {}

    runner_pids: list[int] = []
    for process in processes:
        fields = process.strip().split(maxsplit=2)
        if len(fields) < 2 or Path(fields[1]).name != "amp":
            continue
        arguments = fields[2] if len(fields) == 3 else ""
        if not arguments or arguments.startswith("-"):
            runner_pids.append(int(fields[0]))

    lsof = shutil.which("lsof")
    if not runner_pids:
        return {}
    if lsof is None:
        if required:
            fail("lsof is unavailable; preserving development worktrees")
        return {}
    result = subprocess.run(
        [lsof, "-a", "-d", "cwd", "-p", ",".join(map(str, runner_pids)), "-Fpn"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if required:
            fail("could not inspect Amp runner directories; preserving development worktrees")
        return {}
    runners: dict[Path, set[int]] = {}
    pid: int | None = None
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("n") and pid is not None:
            runners.setdefault(Path(line[1:]).resolve(), set()).add(pid)
    return runners


def stop_amp_runners(repository: Path) -> None:
    repository = repository.resolve()
    runners = amp_runner_processes(required=True).get(repository, set())
    for pid in runners:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError as error:
            fail(f"could not stop Amp runner {pid} in {repository}: {error}")
    if not runners:
        return
    for _ in range(50):
        if repository not in amp_runner_processes(required=True):
            print(f"Stopped {len(runners)} Amp runner(s) in {repository}")
            return
        time.sleep(0.1)
    fail(f"Amp runner(s) in {repository} did not stop; preserving its worktree")


def supacode_worktrees() -> dict[Path, tuple[str, str]]:
    supacode = shutil.which("supacode")
    if supacode is None:
        return {}
    result = subprocess.run(
        [supacode, "worktree", "list", "--with-status"],
        check=True,
        capture_output=True,
        text=True,
    )
    worktrees: dict[Path, tuple[str, str]] = {}
    for line in result.stdout.splitlines():
        worktree_id, status = line.split("\t", maxsplit=1)
        worktrees[Path(parse.unquote(worktree_id)).resolve()] = (worktree_id, status)
    return worktrees


def repository_worktrees() -> set[Path]:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repository_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        Path(line.removeprefix("worktree ")).resolve()
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    }


def abbreviated_path(path: Path) -> str:
    try:
        relative = path.relative_to(Path.home())
    except ValueError:
        return str(path)
    return str(Path("~") / relative) if relative.parts else "~"


def worktree_prune_reason(repository: Path) -> str | None:
    if repository == repository_root().resolve():
        return "current worktree"

    def git(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments], cwd=repository, check=check, capture_output=True, text=True,
        )

    try:
        common = git("rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        if repository == Path(common).resolve().parent:
            return "primary worktree"
        if git(
            "--no-optional-locks", "status", "--porcelain",
            "--untracked-files=all", "--ignore-submodules=none",
        ).stdout:
            return "uncommitted changes"
        if int(git("rev-list", "--count", "HEAD", "--not", "--remotes").stdout) > 0:
            return "unpushed commits"
        merged = git("merge-base", "--is-ancestor", "HEAD", "refs/heads/main", check=False)
        if merged.returncode == 1:
            return "not merged into local main"
        merged.check_returncode()
    except (OSError, subprocess.CalledProcessError):
        return "Git status unavailable"
    return None


def print_registered_states(root: Path, *, prune: bool = False) -> None:
    states = sorted(registered_states(root), key=lambda state: (state.port, state.name))
    if not states:
        print("No development states are registered.")
        return
    supacode = supacode_worktrees()
    worktrees = repository_worktrees()
    prunable: dict[Path, list[State]] = {}
    rows: list[tuple[str, ...]] = []
    for state in states:
        repository = Path(state.repository_root)
        checkout = "present" if repository.is_dir() else "stale"
        service = "running" if service_is_loaded(state) else "stopped"
        resolved = repository.resolve()
        entry = supacode.get(resolved)
        eligible = False
        if entry is None and checkout == "stale":
            prune_status = "yes: orphaned state"
            eligible = True
        elif entry is None:
            prune_status = "no: not registered with Supacode"
        elif resolved not in worktrees:
            prune_status = "no: outside this Git repository"
        elif checkout == "stale":
            prune_status = "no: missing checkout; cannot verify Git status"
        else:
            reason = worktree_prune_reason(resolved)
            eligible = reason is None
            prune_status = f"no: {reason}" if reason else "yes: clean, pushed, merged"
        if eligible:
            prunable.setdefault(resolved, []).append(state)
        rows.append(
            (
                state.name,
                str(state.port),
                checkout,
                service,
                prune_status,
                abbreviated_path(repository),
            )
        )
    headers = ("STATE", "PORT", "CHECKOUT", "SERVICE", "PRUNE", "REPOSITORY")
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]
    for row in (headers, *rows):
        print("  ".join(f"{value:<{widths[index]}}" for index, value in enumerate(row)).rstrip())

    if prune:
        if not prunable:
            print("No prunable development states found.")
        for repository, associated in prunable.items():
            stop_amp_runners(repository)
            entry = supacode.get(repository)
            if entry is not None:
                if supacode_worktrees().get(repository) != entry:
                    fail(f"worktree registration changed; preserving {repository}; list again")
                reason = worktree_prune_reason(repository)
                if reason is not None:
                    fail(f"preserving {repository}: {reason}; list again")
                if entry[1] != "archived":
                    subprocess.run(
                        ["supacode", "worktree", "archive", "--worktree", entry[0], "--background"],
                        check=True,
                    )
                if supacode_worktrees().get(repository) != (entry[0], "archived"):
                    fail(f"worktree is not archived; preserving {repository}; list again")
                reason = worktree_prune_reason(repository)
                if reason is not None:
                    fail(f"preserving {repository}: {reason}; list again")
                delete_supacode_worktree(root, repository, entry[0], associated)
            else:
                if repository.is_dir() or repository in supacode_worktrees():
                    fail(f"checkout registration changed; preserving {repository}; list again")
                for state in associated:
                    if state_path(root, state.name).exists():
                        remove_state(root, state, confirmed=True)


def delete_supacode_worktree(
    root: Path, repository: Path, worktree_id: str, states: list[State]
) -> None:
    subprocess.run(
        ["supacode", "worktree", "delete", "--worktree", worktree_id, "--background"],
        check=True,
    )
    print(f"Removed Supacode worktree {repository}")
    for state in states:
        if state_path(root, state.name).exists():
            remove_state(root, state, confirmed=True)


def db_command(state: State, arguments: argparse.Namespace) -> int:
    operation = arguments.db_command or "status"
    if operation in {"status", "schema"}:
        return run_admin(state, "schema")
    if operation in {"initialize", "init"}:
        initialize(state)
        return 0
    if operation in {"migrate", "seed"}:
        migrate_state_configuration(state)
        return run_admin(state, operation)
    if operation == "import-preview":
        return run_admin(state, "import-preview", str(arguments.source))
    if operation == "import-confirm":
        migrate_state_configuration(state)
        return run_admin(
            state,
            "import-confirm",
            str(arguments.source),
            "--digest",
            arguments.digest,
        )
    fail(f"unsupported database command {operation!r}")


def command(arguments: argparse.Namespace) -> int:
    root = arguments.state_root.expanduser().resolve()
    operation = arguments.command or "status"

    if operation == "update-stable":
        installer = runpy.run_path(str(Path(__file__).with_name("install-stable.py")))
        installer["update"](
            repository_root(),
            confirmed=arguments.yes,
            dry_run=arguments.dry_run,
        )
        return 0

    if operation == "migrate-state-root":
        migrate_state_root(arguments.source_root, root)
        return 0

    if operation == "create":
        state = create_state(root, arguments.name, arguments.port)
        print_state(state)
        return 0

    if operation in {"initialize", "init"}:
        if arguments.state is None and not states_for_current_checkout(root):
            state = create_state(root)
            print_state(state)
        else:
            state = resolve_state(root, arguments.state)
        initialize(state)
        return 0

    if operation == "status":
        selected_name = getattr(arguments, "state", None)
        if selected_name is not None:
            return print_status(resolve_state(root, selected_name))
        state = state_for_current_checkout(root)
        if state is None:
            print("No development state for this checkout.")
            print("Create and initialize one with: scripts/dev.py init")
            return 0
        return print_status(state)

    if operation == "preflight":
        preflight(resolve_state(root, arguments.state))
        return 0

    if operation == "list":
        print_registered_states(root, prune=arguments.prune)
        return 0

    if operation == "remove" and arguments.all:
        matches = states_for_current_checkout(root)
        if not matches:
            print("This checkout has no development state to remove.")
            return 0
        for state in matches:
            remove_state(root, state, confirmed=arguments.yes)
        return 0

    state = resolve_state(root, getattr(arguments, "state", None))
    if operation == "restart":
        print_state(state)
        restart(state)
        return 0
    if operation == "activate":
        activate(root, state)
        return 0
    if operation == "logs":
        if arguments.provider_traffic:
            with provider_traffic_diagnostics(state):
                show_logs(state, lines=arguments.lines, follow=True)
        else:
            show_logs(state, lines=arguments.lines, follow=arguments.follow)
        return 0
    if operation == "remove":
        remove_state(root, state, confirmed=arguments.yes)
        return 0
    if operation == "db":
        return db_command(state, arguments)
    fail(f"unsupported command {operation!r}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="scripts/dev.py",
        description="Sayloom development environment\n\n"
        "State selection is inferred from the current Git checkout.\n"
        "Running without a command is equivalent to status.",
        epilog="""examples:
  scripts/dev.py                 show this checkout's development status
  scripts/dev.py preflight       check configuration before costly restart verification
  scripts/dev.py init            create its state, then migrate and seed
  scripts/dev.py restart         verify, back up, initialize, and restart
  scripts/dev.py update-stable --dry-run
                                review a separate Stable replacement without mutation
  scripts/dev.py activate        move this checkout to Raycast port 7523
  scripts/dev.py logs            show the last 100 lines from each service stream
  scripts/dev.py logs -f         continue showing output appended to either stream
  scripts/dev.py logs --provider-traffic
                                temporarily log and follow exact provider traffic
  scripts/dev.py list            show every registered development state
  scripts/dev.py list --prune    delete entries marked yes in the PRUNE column, without prompting
  scripts/dev.py migrate-state-root
                                migrate all legacy registrations to the XDG root

database commands:
  scripts/dev.py db              report schema status without mutation
  scripts/dev.py db migrate      apply migrations through Alembic head
  scripts/dev.py db seed         create or validate deterministic seed data
  scripts/dev.py db init         apply migrations and seed data
  scripts/dev.py db --help       show import and other database commands

state data:
  ${XDG_DATA_HOME:-~/.local/share}/local-text/dev-states/

state-root and database migrations are explicit; normal startup performs neither.
status and list are read-only unless list receives --prune.
list --prune permanently deletes eligible worktrees and associated state databases/environments.
""",
        formatter_class=HelpFormatter,
    )
    result.add_argument(
        "--state-root",
        type=Path,
        default=DEFAULT_STATE_ROOT,
        help="use another state root for testing or recovery",
    )
    subparsers = result.add_subparsers(dest="command", title="commands", metavar="COMMAND")

    status = subparsers.add_parser("status", help="show this checkout's state and schema")
    status.add_argument("--state", help=argparse.SUPPRESS)

    preflight_parser = subparsers.add_parser(
        "preflight",
        help="check configuration before costly restart verification",
        description="Check configuration before costly restart verification.",
    )
    preflight_parser.add_argument("--state", help=argparse.SUPPRESS)

    create = subparsers.add_parser("create", help="create an uninitialized checkout state")
    create.add_argument("name", nargs="?", help="default: sanitized Git branch name")
    create.add_argument("--port", type=int, help="request a specific loopback port")

    initialize_parser = subparsers.add_parser(
        "initialize", aliases=["init"], help="create if needed, then migrate and seed"
    )
    initialize_parser.add_argument("--state", help=argparse.SUPPRESS)

    restart_parser = subparsers.add_parser(
        "restart", help="preflight, verify, back up, initialize, and restart"
    )
    restart_parser.add_argument("--state", help=argparse.SUPPRESS)

    stable_parser = subparsers.add_parser(
        "update-stable",
        help="confirm and replace the separate Stable source snapshot",
        description="Replace Stable with this checkout, including uncommitted implementation. "
        "Requires confirmation, verifies ownership, preserves rollback code, and restarts only "
        "the release service on 7532. Never syncs dependencies, migrates data, or changes "
        "settings, trial records or Raycast commands. dev.py is a stdlib Python orchestrator; "
        "development application operations use uv. update-stable reuses the installed venv.",
    )
    stable_parser.add_argument("--yes", action="store_true", help="confirm Stable code replacement")
    stable_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show source changes and check readiness without mutation",
    )

    activate_parser = subparsers.add_parser(
        "activate", help=f"move this checkout to Raycast port {DEVELOPMENT_PORT}"
    )
    activate_parser.add_argument("--state", help=argparse.SUPPRESS)

    logs_parser = subparsers.add_parser(
        "logs",
        help="show this checkout's service logs",
        description="Show only the current checkout's registered development-state logs. "
        "Valid JSON entries are indented for readability. Stream labels do not reveal "
        "private filesystem paths. --provider-traffic temporarily logs exact request and "
        "response content, including dictated/transcribed text, and follows until interrupted.",
    )
    logs_parser.add_argument(
        "-n",
        "--lines",
        type=positive_line_count,
        default=100,
        help="initial lines per stream (default: 100)",
    )
    logs_parser.add_argument(
        "-f", "--follow", action="store_true", help="continue showing appended output"
    )
    logs_parser.add_argument(
        "--provider-traffic",
        action="store_true",
        help="temporarily log exact provider content and follow until interrupted",
    )

    list_parser = subparsers.add_parser("list", help="list every registered state")
    list_parser.add_argument(
        "--prune", action="store_true",
        help="permanently delete entries marked yes in PRUNE, including associated "
        "databases/environments, without confirmation",
    )

    state_root_migration = subparsers.add_parser(
        "migrate-state-root",
        help="verify and migrate all legacy state registrations to the XDG data root",
    )
    state_root_migration.add_argument(
        "--source-root",
        type=Path,
        default=LEGACY_STATE_ROOT,
        help="legacy state root (default: macOS Application Support)",
    )

    remove_parser = subparsers.add_parser("remove", help="remove this checkout's state and data")
    selection = remove_parser.add_mutually_exclusive_group()
    selection.add_argument("--state", help=argparse.SUPPRESS)
    selection.add_argument(
        "--all", action="store_true", help="remove all states bound to this checkout"
    )
    remove_parser.add_argument("-y", "--yes", action="store_true", help="skip confirmation")

    database = subparsers.add_parser("db", help="run focused database administration")
    database.add_argument("--state", help=argparse.SUPPRESS)
    database_commands = database.add_subparsers(
        dest="db_command", title="database commands", metavar="COMMAND"
    )
    database_commands.add_parser("status", aliases=["schema"], help="report schema status")
    database_commands.add_parser(
        "initialize", aliases=["init"], help="apply migrations and deterministic seed data"
    )
    database_commands.add_parser("migrate", help="apply migrations through Alembic head")
    database_commands.add_parser("seed", help="create or validate deterministic seed data")
    preview = database_commands.add_parser("import-preview", help="preview legacy configuration")
    preview.add_argument("source", type=Path)
    confirm = database_commands.add_parser(
        "import-confirm", help="confirm an unchanged import preview"
    )
    confirm.add_argument("source", type=Path)
    confirm.add_argument("--digest", required=True)
    result.usage = "scripts/dev.py [COMMAND] [OPTIONS]"
    return result


def main() -> None:
    arguments = parser().parse_args()
    try:
        raise SystemExit(command(arguments))
    except subprocess.CalledProcessError as error:
        print(f"error: command failed with status {error.returncode}: {error.cmd}", file=sys.stderr)
        raise SystemExit(error.returncode) from error


if __name__ == "__main__":
    main()
