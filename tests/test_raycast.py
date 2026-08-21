import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parent.parent
RAYCAST_DIRECTORY = REPOSITORY_ROOT / "raycast"
COMMANDS = {
    "open-sayloom.sh": "Open Sayloom Development",
    "send-to-amp.sh": "Send to Amp — Sayloom Development",
    "send-to-iterm.sh": "Send to iTerm — Sayloom Development",
    "send-to-supacode.sh": "Send to Supacode — Sayloom Development",
    "send-to-vs-code.sh": "Send to VS Code — Sayloom Development",
}


def test_exactly_five_development_branded_script_commands() -> None:
    command_files = {
        path.name: path
        for path in RAYCAST_DIRECTORY.glob("*.sh")
        if "# @raycast.schemaVersion" in path.read_text()
    }

    assert set(command_files) == set(COMMANDS)
    for name, title in COMMANDS.items():
        assert "Sayloom Development" in title
        content = command_files[name].read_text()
        assert f"# @raycast.title {title}" in content
        assert "# @raycast.packageName Sayloom Development" in content
        assert "# @raycast.icon 🧵" in content


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
