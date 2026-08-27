"""Validation and environment handling for named development state."""

import hashlib
import json
import os
import re
import socket
from dataclasses import asdict, dataclass
from pathlib import Path

STATE_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
DEFAULT_STATE_ROOT = Path.home() / "Library/Application Support/local-text/dev-states"
DEFAULT_CONFIG_ROOT = Path.home() / ".config/local-text/development"
DEVELOPMENT_PORT = 7523
DEVELOPMENT_PORT_END = 7622
PRODUCTION_PORT = 7532
MANIFEST_NAME = "state.json"
ALLOWED_ENVIRONMENT_KEYS = {
    "LOCAL_TEXT_GEMINI_API_KEY",
    "LOCAL_TEXT_GEMINI_MODEL",
    "LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS",
}
APPLICATION_ENVIRONMENT_KEYS = ALLOWED_ENVIRONMENT_KEYS | {
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "LOCAL_TEXT_DATABASE_PATH",
    "LOCAL_TEXT_DEVELOPMENT_STATE_NAME",
    "LOCAL_TEXT_PROFILE",
    "LOCAL_TEXT_STATE_DIRECTORY",
}
ENVIRONMENT_LINE = re.compile(r"([A-Z][A-Z0-9_]*)=(.*)")


@dataclass(frozen=True)
class State:
    name: str
    repository_root: str
    state_directory: str
    label: str
    port: int


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def repository_root() -> Path:
    return Path(__file__).resolve().parent.parent


def validate_name(name: str) -> None:
    if not STATE_NAME.fullmatch(name):
        fail("state names use lowercase letters, digits, and hyphens only")


def state_path(root: Path, name: str) -> Path:
    validate_name(name)
    resolved_root = root.expanduser().resolve()
    candidate = (resolved_root / name).resolve()
    if resolved_root not in candidate.parents:
        fail("state resolves outside the development-state root")
    return candidate


def state_label(name: str, checkout: Path | None = None) -> str:
    checkout = (checkout or repository_root()).resolve()
    return f"local.local-text.development.{checkout_identifier(checkout)}.{name}"


def checkout_identifier(checkout: Path | None = None) -> str:
    checkout = (checkout or repository_root()).resolve()
    return hashlib.sha256(str(checkout).encode()).hexdigest()[:12]


def validate_state(
    state: State, root: Path, name: str, *, require_current_checkout: bool = True
) -> State:
    if state.name != name:
        fail("state manifest name does not match its directory")
    checkout = Path(state.repository_root)
    if not checkout.is_absolute():
        fail("state manifest has an invalid checkout path")
    if require_current_checkout and checkout.resolve() != repository_root().resolve():
        fail("state belongs to a different checkout")
    directory = Path(state.state_directory)
    if not directory.is_absolute() or directory.resolve() != state_path(root, name):
        fail("state manifest resolves outside its selected state directory")
    if state.label != state_label(name, checkout):
        fail("state manifest has an invalid service label")
    if isinstance(state.port, bool) or not isinstance(state.port, int):
        fail("state manifest has an invalid loopback port")
    if not 1024 <= state.port <= 65535:
        fail("state manifest has an invalid loopback port")
    if state.port == PRODUCTION_PORT:
        fail(f"state manifest cannot use reserved production port {PRODUCTION_PORT}")
    return state


def load_state(root: Path, name: str) -> State:
    manifest_path = state_path(root, name) / MANIFEST_NAME
    if not manifest_path.is_file():
        fail(f"unknown state {name!r}; create it explicitly first")
    try:
        contents = json.loads(manifest_path.read_text())
        if not isinstance(contents, dict):
            fail("invalid state manifest: expected an object")
        state = State(**contents)
    except (OSError, TypeError, json.JSONDecodeError) as error:
        fail(f"invalid state manifest: {error}")
    return validate_state(state, root, name)


def write_state(state: State) -> None:
    manifest_path = Path(state.state_directory) / MANIFEST_NAME
    manifest_path.write_text(json.dumps(asdict(state), indent=2) + "\n")
    os.chmod(manifest_path, 0o600)


def registered_states(root: Path) -> list[State]:
    states: list[State] = []
    for manifest_path in root.glob(f"*/{MANIFEST_NAME}"):
        try:
            contents = json.loads(manifest_path.read_text())
        except (OSError, TypeError, json.JSONDecodeError) as error:
            fail(f"invalid state manifest at {manifest_path}: {error}")
        if not isinstance(contents, dict):
            fail(f"invalid state manifest at {manifest_path}: expected an object")
        try:
            state = State(**contents)
        except TypeError as error:
            fail(f"invalid state manifest at {manifest_path}: {error}")
        states.append(
            validate_state(
                state,
                root,
                manifest_path.parent.name,
                require_current_checkout=False,
            )
        )
    return states


def states_on_port(root: Path, port: int) -> list[State]:
    return [state for state in registered_states(root) if state.port == port]


def available_port(
    root: Path,
    *,
    excluded_names: set[str] | None = None,
    excluded_ports: set[int] | None = None,
) -> int:
    excluded_names = excluded_names or set()
    excluded_ports = excluded_ports or set()
    reserved = {
        state.port for state in registered_states(root) if state.name not in excluded_names
    }
    reserved.update({PRODUCTION_PORT, *excluded_ports})
    for port in range(DEVELOPMENT_PORT, DEVELOPMENT_PORT_END + 1):
        if port not in reserved and port_is_available(port):
            return port
    fail(f"no development port is available from {DEVELOPMENT_PORT} to {DEVELOPMENT_PORT_END}")


def port_is_available(port: int) -> bool:
    try:
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", port))
    except OSError:
        return False
    return True


def load_environment_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file():
        fail(f"environment path must be a regular file: {path}")
    if path.stat().st_mode & 0o077:
        fail(f"environment file must have mode 0600: {path}")
    values: dict[str, str] = {}
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeError) as error:
        fail(f"cannot read environment file: {error}")
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ENVIRONMENT_LINE.fullmatch(stripped)
        if match is None or match.group(1) not in ALLOWED_ENVIRONMENT_KEYS:
            fail(f"invalid environment entry at {path}:{line_number}")
        key, value = match.groups()
        if key in values:
            fail(f"duplicate environment entry at {path}:{line_number}")
        values[key] = value
    return values


def configuration_paths(state: State) -> tuple[Path, Path]:
    shared = DEFAULT_CONFIG_ROOT / "environment"
    selected = Path(state.state_directory) / "environment"
    return shared, selected


def legacy_configuration_path(state: State) -> Path:
    return (
        DEFAULT_CONFIG_ROOT
        / "states"
        / checkout_identifier(Path(state.repository_root))
        / state.name
        / "environment"
    )


def migrate_state_configuration(state: State) -> None:
    _, selected = configuration_paths(state)
    legacy = legacy_configuration_path(state)
    if not legacy.exists():
        return
    if selected.exists():
        fail(
            "state has both legacy and current configuration files; reconcile them before "
            "continuing"
        )
    selected.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    legacy.replace(selected)
    os.chmod(selected, 0o600)
    for directory in legacy.parents:
        if directory == DEFAULT_CONFIG_ROOT:
            break
        try:
            directory.rmdir()
        except OSError:
            break


def state_configuration(state: State) -> dict[str, str]:
    shared, selected = configuration_paths(state)
    legacy = legacy_configuration_path(state)
    if selected.exists() and legacy.exists():
        fail("state has both legacy and current configuration files")
    state_values = load_environment_file(selected if selected.exists() else legacy)
    return {**load_environment_file(shared), **state_values}


def state_environment(state: State, *, load_configuration: bool = False) -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if key not in APPLICATION_ENVIRONMENT_KEYS
    }
    if load_configuration:
        environment.update(state_configuration(state))
    environment["LOCAL_TEXT_STATE_DIRECTORY"] = state.state_directory
    environment["LOCAL_TEXT_PROFILE"] = "development"
    return environment
