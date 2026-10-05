#!/usr/bin/env python3
"""Synthetic browser acceptance for the Personal Correction approval UI.

Run from the repository root:
    uv run python tests/browser/personal_correction_approval.py

Pass ``--screenshots-dir PATH`` to retain desktop and 390px review captures.
The harness serves the tracked static UI against an in-memory synthetic API;
it never starts or connects to an application runtime or database.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src/local_text/static"
INITIAL_TEXT = "Please send the umber parcel."
BROWSER_OPERATION_TIMEOUT_MS = 4_000
PROCESS_TIMEOUT_SECONDS = 15


class SyntheticState:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any] | None]] = []
        self.episode_bodies: list[dict[str, Any]] = []
        self.fail_next_episode = True
        self.first_episode_started = threading.Event()
        self.release_first_episode = threading.Event()
        self.lock = threading.Lock()

    def record(self, path: str, body: dict[str, Any] | None) -> None:
        with self.lock:
            self.requests.append((path, body))

    def episode_count(self) -> int:
        with self.lock:
            return len(self.episode_bodies)


class SyntheticHandler(BaseHTTPRequestHandler):
    server: SyntheticServer

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def send_json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_file(self, path: Path, content_type: str) -> None:
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def read_body(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length)) if length else None

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/":
            template = (STATIC / "index.html").read_text()
            page = (
                template.replace("__PAGE_TITLE__", "Synthetic browser acceptance")
                .replace("__DISPLAY_NAME__", "Synthetic browser acceptance")
                .replace("__PROFILE__", "development")
                .replace("__DEVELOPMENT_BADGE__", "")
                .replace("__STATIC_VERSION__", "acceptance")
            ).encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        if path == "/static/app.css":
            self.send_file(STATIC / "app.css", "text/css; charset=utf-8")
            return
        if path == "/static/app.js":
            self.send_file(STATIC / "app.js", "text/javascript; charset=utf-8")
            return
        if path == "/api/config":
            self.send_json(
                {
                    "preparation_default": "conservative",
                    "active_prompt_version_id": 7,
                    "cleanup_configuration": {
                        "status": "unavailable",
                        "routes": [],
                        "disclosure": {},
                    },
                }
            )
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        self.server.state.record(path, None)
        if path == "/api/outgoing-state":
            self.send_json({"revision": 1})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        body = self.read_body()
        self.server.state.record(path, body)
        if path == "/api/outgoing-state":
            self.send_json({"revision": 1})
            return
        if path == "/api/cleanup":
            assert body is not None
            self.send_json(
                {
                    "prepared_text": body["original_text"],
                    "status": "unchanged",
                    "provider": "synthetic",
                    "model": "synthetic",
                    "correction_mode": body["correction_mode"],
                    "lexical_repairs": [],
                    "attempts": [],
                }
            )
            return
        if path == "/api/personal-corrections/candidates":
            assert body is not None
            before = body["before_text"]
            after = body["after_text"]
            before_start = before.index("umber")
            after_start = after.index("amber")
            self.send_json(
                {
                    "candidates": [
                        {
                            "operation": "replacement",
                            "original_span": {
                                "start": before_start,
                                "end": before_start + 5,
                                "text": "umber",
                            },
                            "prepared_span": {
                                "start": after_start,
                                "end": after_start + 5,
                                "text": "amber",
                            },
                            "context": after,
                            "queue_position": 1,
                            "inspection_reason": "Synthetic replacement for browser acceptance.",
                        }
                    ],
                    "observed_sentence": before,
                    "intended_sentence": after,
                    "applicability_context": "A synthetic parcel color.",
                }
            )
            return
        if path == "/api/personal-corrections/episodes":
            assert body is not None
            with self.server.state.lock:
                self.server.state.episode_bodies.append(body)
                should_fail = self.server.state.fail_next_episode
                self.server.state.fail_next_episode = False
            if should_fail:
                self.server.state.first_episode_started.set()
                if not self.server.state.release_first_episode.wait(
                    BROWSER_OPERATION_TIMEOUT_MS / 1_000
                ):
                    self.send_error(HTTPStatus.GATEWAY_TIMEOUT)
                    return
                self.send_json(
                    {
                        "detail": {
                            "code": "personal_correction_save_unavailable",
                            "message": "The Personal Correction could not be saved.",
                            "retry_action": "Retry while the review is current.",
                        }
                    },
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
            mapping = body["mapping"]
            self.send_json(
                {
                    "approval_id": body["approval_id"],
                    "mapping": {"ordinal": 1, **mapping},
                    "correction": {
                        "id": "synthetic-correction",
                        "intended_term": mapping["intended_text"],
                        "applicability_context": body["applicability_context"],
                        "aliases": [{"observed_alias": mapping["observed_text"]}],
                    },
                },
                HTTPStatus.CREATED,
            )
            return
        self.send_error(HTTPStatus.NOT_FOUND)


class SyntheticServer(ThreadingHTTPServer):
    def __init__(self, state: SyntheticState) -> None:
        super().__init__(("127.0.0.1", 0), SyntheticHandler)
        self.state = state


class Browser:
    def __init__(self, session: str) -> None:
        self.session = session
        self.environment = {
            **os.environ,
            "AGENT_BROWSER_DEFAULT_TIMEOUT": str(BROWSER_OPERATION_TIMEOUT_MS),
            "AGENT_BROWSER_IDLE_TIMEOUT_MS": "30000",
        }

    def run(self, *arguments: str) -> str:
        command = ["agent-browser", "--session", self.session, *arguments]
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=PROCESS_TIMEOUT_SECONDS,
        )
        if result.returncode:
            raise AssertionError(
                f"browser command failed: {' '.join(command)}\n{result.stdout}{result.stderr}"
            )
        return result.stdout.strip()

    def evaluate(self, expression: str) -> Any:
        output = self.run("eval", f"JSON.stringify({expression})")
        return json.loads(json.loads(output))

    def wait_for(self, expression: str) -> None:
        self.run("wait", "--fn", expression)

    def close(self) -> None:
        subprocess.run(
            ["agent-browser", "--session", self.session, "close"],
            cwd=ROOT,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=PROCESS_TIMEOUT_SECONDS,
        )


def assert_state(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def prepare_review(browser: Browser) -> None:
    browser.run("fill", "#original-text", INITIAL_TEXT)
    browser.run("click", "#run-cleanup")
    browser.wait_for(
        f"document.querySelector('#prepared-text').value === {json.dumps(INITIAL_TEXT)}"
    )
    start = INITIAL_TEXT.index("umber")
    browser.run("focus", "#original-text")
    browser.run(
        "eval",
        "document.querySelector('#original-text').setSelectionRange"
        f"({start}, {start + len('umber')})",
    )
    browser.run("keyboard", "type", "amber")
    browser.wait_for(
        "!document.querySelector('#open-missed-repair').hidden"
        " && document.querySelector('#missed-repair-state').textContent"
        ".includes('Correction review available')"
    )
    browser.run("click", "#open-missed-repair")
    browser.wait_for(
        "document.querySelector('#missed-repair-review-state').dataset.state === 'ready'"
    )


def reset_draft(browser: Browser) -> None:
    if browser.evaluate("document.querySelector('#missed-repair-dialog').open"):
        browser.run("click", "#dismiss-missed-repair")
    browser.run("click", "#clear-text")
    browser.wait_for("document.querySelector('#original-text').value === ''")


def assert_layout(browser: Browser, width: int, height: int) -> None:
    browser.run("set", "viewport", str(width), str(height), "2")
    browser.wait_for("window.devicePixelRatio === 2")
    layout = browser.evaluate(
        "(() => {"
        "const dialog = document.querySelector('#missed-repair-dialog').getBoundingClientRect();"
        "const fields = document.querySelectorAll('.missed-repair-mapping-field input');"
        "const observed = fields[0].getBoundingClientRect();"
        "const intended = fields[1].getBoundingClientRect();"
        "return { dialogLeft: dialog.left, dialogRight: dialog.right, viewport: innerWidth,"
        " observedTop: observed.top, intendedTop: intended.top,"
        " overflow: document.documentElement.scrollWidth > innerWidth };"
        "})()"
    )
    assert_state(layout["dialogLeft"] >= 0, f"dialog escapes left edge at {width}px")
    assert_state(
        layout["dialogRight"] <= layout["viewport"],
        f"dialog escapes right edge at {width}px",
    )
    assert_state(not layout["overflow"], f"page overflows horizontally at {width}px")
    if width == 390:
        assert_state(
            layout["intendedTop"] > layout["observedTop"],
            "390px mapping fields should stack",
        )
    else:
        assert_state(
            abs(layout["intendedTop"] - layout["observedTop"]) < 2,
            "desktop mapping fields should share a row",
        )


def run_acceptance(screenshots_dir: Path | None) -> None:
    if shutil.which("agent-browser") is None:
        raise RuntimeError("agent-browser is required for this acceptance harness")

    state = SyntheticState()
    server = SyntheticServer(state)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    browser = Browser(f"pc-approval-{os.getpid()}")
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        browser.run("open", base_url)
        browser.run("set", "viewport", "1280", "900", "2")
        browser.wait_for(
            "document.querySelector('#mode-save-state').textContent.includes('saved default')"
        )

        prepare_review(browser)
        initial = browser.evaluate(
            "({ selected: document.querySelector('.missed-repair-candidate > input').checked,"
            " saveDisabled: document.querySelector('#missed-repair-approval').disabled })"
        )
        assert_state(
            initial == {"selected": False, "saveDisabled": True},
            "review must start unselected",
        )

        browser.run("click", "#retain-observed-sentence")
        removed = browser.evaluate(
            "({ included: document.querySelector('#retain-observed-sentence').dataset.included,"
            " disabled: document.querySelector('#observed-sentence').disabled,"
            " noticeHidden: document.querySelector('#observed-sentence-removed').hidden })"
        )
        assert_state(
            removed == {"included": "false", "disabled": True, "noticeHidden": False},
            "removing a sentence must visibly exclude and disable it",
        )
        browser.run("click", "#retain-observed-sentence")
        restored = browser.evaluate(
            "({ included: document.querySelector('#retain-observed-sentence').dataset.included,"
            " disabled: document.querySelector('#observed-sentence').disabled,"
            " noticeHidden: document.querySelector('#observed-sentence-removed').hidden })"
        )
        assert_state(
            restored == {"included": "true", "disabled": False, "noticeHidden": True},
            "restoring a sentence must re-enable it",
        )

        assert_layout(browser, 1280, 900)
        if screenshots_dir:
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            desktop_capture = screenshots_dir / "personal-correction-desktop.png"
            browser.run("screenshot", str(desktop_capture.resolve()))
        assert_layout(browser, 390, 844)
        if screenshots_dir:
            narrow_capture = screenshots_dir / "personal-correction-390px.png"
            browser.run("screenshot", str(narrow_capture.resolve()))
        browser.run("set", "viewport", "1280", "900", "2")

        browser.run("click", ".missed-repair-candidate > input")
        browser.wait_for("!document.querySelector('#missed-repair-approval').disabled")
        browser.run("click", "#missed-repair-approval")
        assert_state(
            state.first_episode_started.wait(2),
            "synthetic save request did not reach the server",
        )
        saving = browser.evaluate(
            "({ state: document.querySelector('#missed-repair-review-state').dataset.state,"
            " label: document.querySelector('#missed-repair-approval').textContent,"
            " disabled: document.querySelector('#missed-repair-approval').disabled })"
        )
        assert_state(
            saving == {"state": "saving", "label": "Saving…", "disabled": True},
            "save must expose and lock the genuine in-flight state",
        )
        state.release_first_episode.set()
        browser.wait_for(
            "document.querySelector('#missed-repair-review-state').dataset.state === 'error'"
        )
        browser.run("click", "#missed-repair-approval")
        browser.wait_for(
            "document.querySelector('#missed-repair-review-state').dataset.state === 'saved'"
        )
        saved = browser.evaluate(
            "({ resultHidden: document.querySelector('#missed-repair-saved-result').hidden,"
            " observed: document.querySelector('#missed-repair-saved-observed').textContent,"
            " intended: document.querySelector('#missed-repair-saved-intended').textContent,"
            " approvalHidden: document.querySelector('#missed-repair-approval').hidden })"
        )
        assert_state(
            saved == {
                "resultHidden": False,
                "observed": "umber",
                "intended": "amber",
                "approvalHidden": True,
            },
            "successful retry must render the saved result",
        )
        assert_state(
            len(state.episode_bodies) == 2,
            "failure plus retry should make two save attempts",
        )
        assert_state(
            state.episode_bodies[0]["approval_id"] == state.episode_bodies[1]["approval_id"],
            "a retry must reuse the approval ID",
        )

        reset_draft(browser)
        prepare_review(browser)
        writes_before_stale = state.episode_count()
        browser.run(
            "eval",
            "(() => { const field = document.querySelector('#original-text');"
            " const start = field.value.indexOf('amber');"
            " field.setRangeText('ochre', start, start + 5, 'end');"
            " field.dispatchEvent(new InputEvent('input', { bubbles: true,"
            " inputType: 'insertText', data: 'ochre' })); })()",
        )
        browser.wait_for(
            "document.querySelector('#missed-repair-review-state').dataset.state === 'stale'"
        )
        assert_state(state.episode_count() == writes_before_stale, "a stale review must not write")
        stale = browser.evaluate(
            "({ disabled: document.querySelector('#missed-repair-approval').disabled,"
            " value: document.querySelector('#original-text').value })"
        )
        assert_state(
            stale == {"disabled": True, "value": "Please send the ochre parcel."},
            "bounded post-review edit must stale and disable approval",
        )

        reset_draft(browser)
        prepare_review(browser)
        writes_before_dismiss = state.episode_count()
        browser.run("click", "#dismiss-missed-repair")
        browser.wait_for("!document.querySelector('#missed-repair-dialog').open")
        assert_state(state.episode_count() == writes_before_dismiss, "dismissal must not write")

        expected_api_paths = {
            "/api/outgoing-state",
            "/api/cleanup",
            "/api/personal-corrections/candidates",
            "/api/personal-corrections/episodes",
        }
        unexpected = sorted({path for path, _body in state.requests} - expected_api_paths)
        assert_state(not unexpected, f"harness contacted unexpected API paths: {unexpected}")
        print(
            "PASS: Personal Correction browser acceptance "
            "(desktop + 390px, retry, stale, dismissal, no-write states)"
        )
    finally:
        state.release_first_episode.set()
        browser.close()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots-dir", type=Path)
    arguments = parser.parse_args()
    try:
        run_acceptance(arguments.screenshots_dir)
    except (AssertionError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
