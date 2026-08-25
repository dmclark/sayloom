import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parent.parent
RAYCAST_DIRECTORY = REPOSITORY_ROOT / "raycast"
COMMANDS = {
    "open-sayloom.sh": "Dev: Open Sayloom",
    "send-to-amp.sh": "Dev: Send to Amp",
    "send-to-iterm.sh": "Dev: Send to iTerm",
    "send-to-supacode.sh": "Dev: Send to Supacode",
    "send-to-vs-code.sh": "Dev: Send to VS Code",
}


def run_installer(
    *arguments: str, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(REPOSITORY_ROOT / "scripts/install-raycast.py"), *arguments],
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_exactly_five_development_branded_script_commands() -> None:
    command_files = {
        path.name: path
        for path in RAYCAST_DIRECTORY.glob("*.sh")
        if "# @raycast.schemaVersion" in path.read_text()
    }

    assert set(command_files) == set(COMMANDS)
    for name, title in COMMANDS.items():
        assert title.startswith("Dev: ")
        content = command_files[name].read_text()
        assert f"# @raycast.title {title}" in content
        assert "# @raycast.packageName Sayloom Development" in content
        assert "# @raycast.icon 🧵" in content


def test_installer_defaults_to_development_prefixed_aliases(tmp_path: Path) -> None:
    environment = {**os.environ, "HOME": str(tmp_path)}

    installed = run_installer(environment=environment)

    assert installed.returncode == 0
    directory = tmp_path / ".config/raycast/scripts"
    assert sorted(path.name for path in directory.iterdir()) == [
        f"dev-{name}" for name in sorted(COMMANDS)
    ]
    for name in COMMANDS:
        alias = directory / f"dev-{name}"
        assert alias.is_symlink()
        assert alias.resolve() == (RAYCAST_DIRECTORY / name).resolve()


def test_installer_is_idempotent_with_an_explicit_directory(tmp_path: Path) -> None:
    directory = tmp_path / "commands"
    first = run_installer("--directory", str(directory))
    links = {path.name: path.readlink() for path in directory.iterdir()}

    second = run_installer("--directory", str(directory))

    assert first.returncode == 0
    assert second.returncode == 0
    assert {path.name: path.readlink() for path in directory.iterdir()} == links


def test_installed_alias_resolves_the_repository_library(tmp_path: Path) -> None:
    directory = tmp_path / "commands"
    assert run_installer("--directory", str(directory)).returncode == 0

    opened = subprocess.run(
        [str(directory / "dev-open-sayloom.sh")],
        env={**os.environ, "LOCAL_TEXT_BASE_URL": "http://127.0.0.1:1"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert opened.returncode != 0
    assert "development is not healthy" in opened.stderr
    assert "lib.sh" not in opened.stderr


@pytest.mark.parametrize("conflict", ["file", "broken-link", "unrelated-link", "other-source"])
def test_installer_refuses_to_replace_existing_entries(tmp_path: Path, conflict: str) -> None:
    directory = tmp_path / "commands"
    directory.mkdir()
    destination = directory / "dev-open-sayloom.sh"
    if conflict == "file":
        destination.write_text("existing local command\n")
    elif conflict == "broken-link":
        destination.symlink_to(tmp_path / "missing.sh")
    elif conflict == "unrelated-link":
        unrelated = tmp_path / "unrelated.sh"
        unrelated.write_text("#!/bin/sh\n")
        destination.symlink_to(unrelated)
    else:
        destination.symlink_to(RAYCAST_DIRECTORY / "send-to-amp.sh")
    original = destination.readlink() if destination.is_symlink() else destination.read_text()

    rejected = run_installer("--directory", str(directory))

    assert rejected.returncode != 0
    assert "refusing to replace" in rejected.stderr
    current = destination.readlink() if destination.is_symlink() else destination.read_text()
    assert current == original
    assert sorted(path.name for path in directory.iterdir()) == ["dev-open-sayloom.sh"]


def test_send_commands_target_expected_apps_without_submitting() -> None:
    all_scripts = "\n".join(path.read_text() for path in RAYCAST_DIRECTORY.glob("*.sh"))

    assert "com.google.Chrome.app.bpgpkfmeagdpdcenbogglipmfkalmple" in all_scripts
    assert "app.supabit.supacode" in all_scripts
    assert "com.microsoft.VSCode" in all_scripts
    assert 'tell application "iTerm"' in all_scripts
    assert "newline NO" in all_scripts
    assert "kp:return" not in all_scripts
    assert "key code 36" not in all_scripts


def test_all_raycast_shell_files_parse() -> None:
    for path in RAYCAST_DIRECTORY.glob("*.sh"):
        subprocess.run(["/bin/sh", "-n", path], check=True)


def test_raycast_uses_the_fixed_development_port_without_a_generic_service() -> None:
    library = (RAYCAST_DIRECTORY / "lib.sh").read_text()
    opener = (RAYCAST_DIRECTORY / "open-sayloom.sh").read_text()

    assert "http://127.0.0.1:7523" in library
    assert "http://127.0.0.1:7523/" in opener
    assert "launchctl kickstart" not in opener
    assert "local.local-text.development\"" not in opener


class OutgoingStateServer:
    def __init__(self, state: object) -> None:
        body = json.dumps(state, ensure_ascii=False).encode()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever)

    def __enter__(self) -> str:
        self.thread.start()
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()


def run_fetch(base_url: str) -> subprocess.CompletedProcess[bytes]:
    command = """
      . ./raycast/lib.sh
      prepare_command
      fetch_outgoing_text "$command_temp_directory/outgoing.txt"
      /bin/cat "$command_temp_directory/outgoing.txt"
    """
    return subprocess.run(
        ["/bin/sh", "-c", command],
        cwd=REPOSITORY_ROOT,
        env={"PATH": "/usr/bin:/bin", "LOCAL_TEXT_BASE_URL": base_url},
        capture_output=True,
        check=False,
    )


def test_raycast_fetch_preserves_multiline_outgoing_text() -> None:
    with OutgoingStateServer({"outgoing_text": "synthetic line one\nsynthetic line two"}) as url:
        result = run_fetch(url)

    assert result.returncode == 0
    assert result.stdout == b"synthetic line one\nsynthetic line two"


def test_raycast_fetch_preserves_utf8_outgoing_text() -> None:
    outgoing = "Synthetic\u00a0text — ‘quoted’ café"
    with OutgoingStateServer({"outgoing_text": outgoing}) as url:
        result = run_fetch(url)

    assert result.returncode == 0
    assert result.stdout == outgoing.encode()
    assert "LC_ALL=en_US.UTF-8 /usr/bin/pbcopy" in (RAYCAST_DIRECTORY / "lib.sh").read_text()
    assert "LC_ALL=en_US.UTF-8 /usr/bin/pbpaste" in (RAYCAST_DIRECTORY / "lib.sh").read_text()


def test_raycast_fetch_refuses_empty_or_malformed_state() -> None:
    with OutgoingStateServer({"outgoing_text": "  \n"}) as url:
        empty = run_fetch(url)
    with OutgoingStateServer({"outgoing_text": 42}) as url:
        malformed = run_fetch(url)

    assert empty.returncode != 0
    assert b"there is no outgoing text" in empty.stderr
    assert malformed.returncode != 0
    assert b"outgoing state is malformed" in malformed.stderr
