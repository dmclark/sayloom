#!/usr/bin/env python3
"""Real browser/API trial checks. Synthetic provider only; no credentials or paid calls.

Requires installed Python Playwright and Chromium. Takes at most three targeted
screenshots, if --screenshots-dir is supplied. All state uses a disposable directory.
"""

import argparse
import asyncio
import json
import socket
import subprocess
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
import uvicorn
from alembic import command
from playwright.sync_api import expect, sync_playwright

from local_text.admin import _alembic_config
from local_text.app import create_app
from local_text.cleanup import CleanupService, PreparationMode, ProviderOutput
from local_text.config import Profile, Settings
from local_text.database import ApplicationDatabase
from local_text.prompt_store import PromptStore
from local_text.target_store import TargetStore

TEXT = "🧵 Keep ‘pole request’ in the fixture. Open a pole request for review.\n" + (
    "Synthetic long-passage scroll control.\n" * 40
)
FINAL = TEXT.replace("Open a pole request", "Open a pull request")


def check_scrolling(page):
    page.evaluate("window.scrollTo(0, 0)")
    page.mouse.move(5, 250)
    page.mouse.wheel(0, 600)
    page.wait_for_function("scrollY > 0", timeout=2000)
    for selector in ("#original-text", "#trial-passage"):
        editor = page.locator(selector)
        editor.scroll_into_view_if_needed()
        editor.evaluate("el => el.scrollTop = 0")
        editor.hover(position={"x": 30, "y": 30})
        page.mouse.wheel(0, 450)
        page.wait_for_function(
            "selector => document.querySelector(selector).scrollTop > 0",
            arg=selector,
            timeout=2000,
        )
        if selector == "#trial-passage":
            page.wait_for_function("""document.querySelector('#trial-highlights').scrollTop
                === document.querySelector('#trial-passage').scrollTop""")
        editor.evaluate("el => el.scrollTop = 0")
    page.evaluate("window.scrollTo(0, 0)")


def run(screenshots: Path | None, scratch: Path, feedback_screenshots: bool = False):
    with TemporaryDirectory(dir=scratch, prefix="trial-browser-") as temporary:
        root = Path(temporary)
        database = ApplicationDatabase(root / "synthetic.sqlite3")
        command.upgrade(_alembic_config(database.url), "head")
        prompts = PromptStore(database)
        prompts.seed_default()
        prompts.set_preparation_default(PreparationMode.CONSERVATIVE)
        TargetStore(database).seed_defaults()
        calls = []
        slow = False
        cleanup_slow = False
        cleanup_fails = False

        class SyntheticCleanup:
            provider_id = "openai"
            model = "synthetic"

            async def clean(self, raw_text, system_prompt):
                if cleanup_slow:
                    await asyncio.sleep(0.8)
                if cleanup_fails:
                    raise RuntimeError("Synthetic failure")
                return ProviderOutput(raw_text.rstrip() + "!", "openai", "synthetic", 0)

        async def provider(request):
            calls.append(json.loads(request.content))
            if slow:
                await asyncio.sleep(0.8)
            return httpx.Response(
                200,
                json={
                    "model": "gpt-6-luna",
                    "status": "completed",
                    "service_tier": "default",
                    "usage": {"input_tokens": 700, "output_tokens": 120},
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "suggestions": [
                                                {
                                                    "phrase": "pole request",
                                                    "occurrence": 2,
                                                    "alternatives": ["pull request"],
                                                }
                                            ]
                                        }
                                    ),
                                }
                            ],
                        }
                    ],
                },
            )

        app = create_app(
            Settings(
                Profile.RELEASE,
                database_path=database.path,
                trial_directory=root / "trial",
                openai_api_key="synthetic-only",
                stable_instance=True,
            ),
            cleanup_service=CleanupService(
                provider=SyntheticCleanup(), model="synthetic", timeout_seconds=30
            ),
            trial_transport=httpx.MockTransport(provider),
        )

        def fetch_target_payload():
            # Exercise the real target-command reader, never clipboard/paste/send.
            return subprocess.run(
                [
                    "/bin/sh",
                    "-c",
                    ". ./raycast/lib.sh; prepare_command; "
                    'fetch_outgoing_text "$command_temp_directory/outgoing.txt"; '
                    '/bin/cat "$command_temp_directory/outgoing.txt"',
                ],
                cwd=Path(__file__).resolve().parents[2],
                env={
                    "PATH": "/usr/bin:/bin",
                    "LOCAL_TEXT_BASE_URL": f"http://127.0.0.1:{port}",
                    "TMPDIR": str(root.resolve()),
                },
                capture_output=True,
                check=False,
            )

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
            worker = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
            worker.start()
            while not server.started:
                time.sleep(0.01)
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1200, "height": 1050})
                    errors, cleanup_requests = [], []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on(
                        "request",
                        lambda request: (
                            cleanup_requests.append(request.post_data_json)
                            if request.url.endswith("/api/cleanup")
                            else None
                        ),
                    )
                    page.add_init_script(
                        "navigator.clipboard.writeText = async text => { window.copied = text; }"
                    )
                    page.goto(f"http://127.0.0.1:{port}")
                    page.wait_for_load_state("networkidle")
                    expect(page.locator("#trial-include")).not_to_be_checked()
                    expect(page.locator(".prepared-panel")).to_be_visible()
                    expect(page.locator("#trial-panel")).to_be_hidden()
                    expect(page.locator("#trial-message")).to_be_hidden()
                    page.locator("#trial-include").check()
                    expect(page.locator(".prepared-panel")).to_be_hidden()
                    expect(page.locator("#trial-panel")).to_be_visible()
                    expect(page.locator("#trial-begin")).to_be_disabled()
                    page.locator("#original-text").fill(TEXT)
                    page.locator("#copy-outgoing").click()
                    assert page.evaluate("window.copied") == TEXT
                    page.wait_for_timeout(600)
                    assert not cleanup_requests
                    assert not list((root / "trial").glob("passage-*.json"))
                    page.locator("#clear-text").click()
                    page.locator("#trial-include").uncheck()
                    expect(page.locator(".prepared-panel")).to_be_visible()
                    expect(page.locator("#trial-panel")).to_be_hidden()
                    assert (
                        page.request.get(f"http://127.0.0.1:{port}/api/trial").json()["ends_at"]
                        is None
                    )
                    # Post-trial cleanup must ignore a normal Smart selection.
                    page.locator("#draft-preparation-mode").select_option("smart")
                    page.locator("#trial-controls-open").click()
                    expect(
                        page.get_by_role("dialog", name="Trial controls & privacy")
                    ).to_be_visible()
                    page.keyboard.press("Escape")
                    expect(page.locator("#trial-controls-open")).to_be_focused()
                    page.locator("#trial-controls-open").click()
                    page.on("dialog", lambda dialog: dialog.accept())
                    page.locator('[data-trial-control="start"]').click()
                    expect(page.locator("#trial-state")).to_contain_text("active")
                    expect(
                        page.get_by_role("dialog", name="Trial controls & privacy")
                    ).to_be_hidden()
                    page.locator("#trial-include").check()
                    page.wait_for_timeout(100)
                    cleanup_requests.clear()

                    with patch(
                        "local_text.phrase_trial.secrets.choice", return_value="alternatives"
                    ):
                        page.locator("#original-text").fill(TEXT)
                        page.locator("#trial-begin").click()
                        expect(page.locator("#trial-message")).to_have_text(
                            "Alternatives ready. Nothing has been replaced."
                        )
                    expect(page.locator("#trial-passage")).to_have_value(TEXT)
                    expect(page.locator(".prepared-panel")).to_be_hidden()
                    assert page.locator("#trial-panel").evaluate(
                        "el => el.parentElement.classList.contains('workspace')"
                    )
                    assert page.locator("#trial-panel").bounding_box()["y"] >= (
                        page.locator(".original-panel").bounding_box()["y"]
                        + page.locator(".original-panel").bounding_box()["height"]
                    )
                    for width, height in ((1200, 1050), (1200, 700), (390, 844)):
                        page.set_viewport_size({"width": width, "height": height})
                        check_scrolling(page)
                    page.set_viewport_size({"width": 1200, "height": 1050})
                    page.locator("#trial-choices").get_by_role(
                        "button", name="Use “pull request”", exact=True
                    ).click()
                    expect(page.locator("#trial-passage")).to_have_value(FINAL)
                    page.locator("#trial-choices").get_by_role(
                        "button", name="Edit “pull request”", exact=True
                    ).click()
                    field = page.get_by_role("textbox", name="Edit this phrase only")
                    field.fill("pull-request draft")
                    page.locator("#copy-outgoing").click()
                    assert page.evaluate("window.copied") == FINAL
                    page.locator("#trial-choices").get_by_role(
                        "button", name="Cancel", exact=True
                    ).click()
                    page.locator("#trial-choices").get_by_role(
                        "button", name="Edit “pull request”", exact=True
                    ).click()
                    field.fill("draft change")
                    field.press("End")
                    field.press("ArrowRight")
                    assert field.evaluate("el => el.selectionStart") == len("draft change")
                    page.set_viewport_size({"width": 390, "height": 844})
                    # The highlight mirror follows the textarea through ResizeObserver.
                    page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
                    overflow = page.evaluate("""() => [...document.querySelectorAll('body *')]
                        .filter(el => el.getBoundingClientRect().right > innerWidth + 1)
                        .map(el => ({tag: el.tagName, id: el.id, class: el.className,
                          right: el.getBoundingClientRect().right}))""")
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
                        overflow
                    )
                    field.fill("code review")
                    page.locator("#trial-choices").get_by_role(
                        "button", name="Use wording", exact=True
                    ).click()
                    expect(page.locator("#trial-passage")).to_have_value(
                        TEXT.replace("Open a pole request", "Open a code review")
                    )
                    page.locator("#trial-undo").click()
                    expect(page.locator("#trial-passage")).to_have_value(FINAL)
                    page.locator("#trial-passage").fill(FINAL + " Check later.")
                    page.locator("#copy-outgoing").click()
                    assert page.evaluate("window.copied") == FINAL + " Check later."
                    page.wait_for_timeout(200)
                    assert not cleanup_requests, (
                        "Included passages must never call ordinary correction"
                    )
                    repaired = FINAL + " Check later."
                    page.locator("#trial-spoken").select_option("confirmed")
                    page.locator("#trial-effort").select_option("less")
                    page.locator("#trial-note").fill("Synthetic pre-cleanup feedback")
                    page.locator("#trial-feedback-save").click()
                    expect(page.locator("#trial-feedback-status")).to_have_text(
                        "Optional feedback saved."
                    )
                    expect(page.locator("#trial-note")).to_be_editable()
                    record_path = next((root / "trial").glob("passage-*.json"))
                    assert json.loads(record_path.read_text())["feedback"] == {
                        "spoken": "confirmed",
                        "effort": "less",
                        "note": "Synthetic pre-cleanup feedback",
                    }
                    for width in (1200, 390):
                        page.set_viewport_size({"width": width, "height": 844})
                        page.locator("#trial-feedback-save").scroll_into_view_if_needed()
                        expect(page.locator("#trial-feedback-status")).to_be_in_viewport()
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                        if screenshots and feedback_screenshots:
                            page.locator("#trial-feedback").screenshot(
                                path=screenshots / f"feedback-saved-{width}.png"
                            )

                    fail_feedback, hold_feedback = True, False
                    pending_feedback = []

                    def feedback_write(route):
                        if route.request.post_data_json["action"] != "feedback":
                            route.continue_()
                        elif hold_feedback:
                            pending_feedback.append(route)
                        elif fail_feedback:
                            route.fulfill(status=503, json={"detail": "Synthetic feedback failure"})
                        else:
                            route.continue_()

                    page.route("**/api/trial/passages/*/events", feedback_write)
                    page.locator("#trial-note").fill("Synthetic feedback retry")
                    expect(page.locator("#trial-feedback-status")).to_be_hidden()
                    page.locator("#trial-feedback-save").click()
                    expect(page.locator("#trial-feedback-status")).to_have_text(
                        "Feedback could not be saved. Try saving again."
                    )
                    expect(page.locator("#trial-message")).to_have_text(
                        "Synthetic feedback failure"
                    )
                    expect(page.locator("#trial-note")).to_be_editable()
                    assert json.loads(record_path.read_text())["feedback"]["note"] == (
                        "Synthetic pre-cleanup feedback"
                    )
                    if screenshots and feedback_screenshots:
                        page.locator("#trial-feedback").screenshot(
                            path=screenshots / "feedback-failed-390.png"
                        )
                    fail_feedback = False
                    page.locator("#trial-feedback-save").click()
                    expect(page.locator("#trial-feedback-status")).to_have_text(
                        "Optional feedback saved."
                    )
                    assert json.loads(record_path.read_text())["feedback"]["note"] == (
                        "Synthetic feedback retry"
                    )
                    page.locator("#trial-note").fill("Synthetic pre-cleanup feedback")
                    expect(page.locator("#trial-feedback-status")).to_be_hidden()
                    page.locator("#trial-clean").click()
                    expect(page.locator("#trial-cleaned")).to_have_value(repaired + "!")
                    expect(page.locator("#trial-feedback-status")).to_have_text(
                        "Optional feedback saved."
                    )
                    page.wait_for_timeout(200)
                    assert cleanup_requests[-1] == {
                        "original_text": repaired,
                        "enabled": True,
                        "correction_mode": "conservative",
                    }
                    published = page.request.get(
                        f"http://127.0.0.1:{port}/api/outgoing-state"
                    ).json()
                    assert published["outgoing_text"] == repaired + "!"
                    assert published["correction_mode"] == "conservative"
                    assert published["outgoing_kind"] == "prepared"
                    target_payload = fetch_target_payload()
                    assert target_payload.returncode == 0, target_payload.stderr
                    assert target_payload.stdout == (repaired + "!").encode()
                    expect(page.locator("#trial-passage")).to_have_value(repaired)
                    assert page.locator("#trial-passage").get_attribute("readonly") is not None
                    expect(page.locator("#trial-feedback-save")).to_be_disabled()
                    record_path = next((root / "trial").glob("passage-*.json"))
                    frozen = json.loads(record_path.read_text())
                    assert frozen["final_text"] == repaired
                    assert frozen["feedback"] == {
                        "spoken": "confirmed",
                        "effort": "less",
                        "note": "Synthetic pre-cleanup feedback",
                    }
                    page.locator("#copy-outgoing").click()
                    assert page.evaluate("window.copied") == repaired + "!"
                    page.wait_for_timeout(100)
                    assert json.loads(record_path.read_text()) == frozen
                    for width, name in ((1200, "cleanup-ready"), (390, "cleanup-ready-390")):
                        page.set_viewport_size({"width": width, "height": 1050})
                        page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
                        review = page.locator("#trial-cleaned")
                        review.evaluate("el => el.scrollTop = el.scrollHeight")
                        assert review.evaluate(
                            "el => el.scrollTop > 0 && "
                            "el.scrollHeight <= el.scrollTop + el.clientHeight + 1"
                        )
                        review.evaluate("el => el.scrollTop = 0")
                        if screenshots and not feedback_screenshots:
                            page.locator('[aria-labelledby="trial-clean-title"]').screenshot(
                                path=screenshots / f"{name}.png"
                            )
                    cleanup_fails = True
                    page.locator("#trial-clean").click()
                    expect(page.locator("#trial-cleanup-state")).to_contain_text(
                        "Cleanup unavailable"
                    )
                    expect(page.locator("#copy-outgoing")).to_be_disabled()
                    assert fetch_target_payload().returncode != 0
                    assert (
                        page.request.get(f"http://127.0.0.1:{port}/api/outgoing-state").json()[
                            "outgoing_text"
                        ]
                        == ""
                    )
                    if screenshots and not feedback_screenshots:
                        page.locator('[aria-labelledby="trial-clean-title"]').screenshot(
                            path=screenshots / "cleanup-failed-390.png"
                        )
                    assert json.loads(record_path.read_text()) == frozen
                    cleanup_fails = False
                    page.locator("#trial-clean").click()
                    expect(page.locator("#trial-cleaned")).to_have_value(repaired + "!")
                    assert json.loads(record_path.read_text()) == frozen
                    page.locator("#trial-exit").click()
                    expect(page.locator("#trial-working")).to_be_hidden()
                    expect(page.locator("#trial-panel")).to_be_hidden()
                    expect(page.locator(".prepared-panel")).to_be_visible()
                    expect(page.locator("#trial-include")).to_be_checked()
                    assert not list((root / "trial").glob("passage-*.json"))
                    # Exiting deliberately restores ordinary non-trial cleanup.
                    page.locator("#draft-preparation-mode").select_option("conservative")
                    expect(page.locator("#prepared-text")).to_have_value(repaired + "!")

                    page.set_viewport_size({"width": 1200, "height": 1050})
                    with patch("local_text.phrase_trial.secrets.choice", return_value="manual"):
                        page.locator("#clear-text").click()
                        page.locator("#original-text").fill(TEXT)
                        page.locator("#trial-begin").click()
                        expect(page.locator("#trial-switch")).to_be_visible()
                    expect(page.locator("#trial-feedback-status")).to_be_hidden()
                    assert len(calls) == 1
                    slow = True
                    page.locator("#trial-passage").fill(TEXT + " Manual adjustment.")
                    page.locator("#trial-switch").click()
                    page.locator("#trial-passage").fill("Manually revised before response")
                    page.locator("#copy-outgoing").click()
                    assert page.evaluate("window.copied") == "Manually revised before response"
                    page.wait_for_timeout(1100)
                    expect(page.locator("#trial-choices .trial-suggestion")).to_have_count(0)
                    expect(page.locator("#trial-passage")).to_have_value(
                        "Manually revised before response"
                    )
                    record = json.loads(next((root / "trial").glob("passage-*.json")).read_text())
                    assert "switched_at" in record and record["shown_suggestions"] == []
                    expect(page.get_by_label("Spoken wording")).to_be_visible()
                    expect(page.get_by_label("Whole-task effort")).to_be_visible()
                    page.locator("#trial-spoken").select_option("revised")
                    page.locator("#trial-feedback-save").click()
                    expect(page.locator("#trial-feedback-status")).to_contain_text(
                        "excluded and deleted"
                    )
                    assert not list((root / "trial").glob("passage-*.json"))
                    page.locator("#trial-clean").click()
                    expect(page.locator("#trial-cleaned")).to_have_value(
                        "Manually revised before response!"
                    )
                    assert cleanup_requests[-1]["correction_mode"] == "conservative"
                    assert (
                        cleanup_requests[-1]["original_text"] == "Manually revised before response"
                    )
                    assert not list((root / "trial").glob("passage-*.json"))
                    cleanup_slow = True
                    page.locator("#trial-clean").click()
                    expect(page.locator("#trial-cleanup-state")).to_contain_text("in progress")
                    expect(page.locator("#copy-outgoing")).to_be_disabled()
                    assert (
                        page.request.get(f"http://127.0.0.1:{port}/api/outgoing-state").json()[
                            "outgoing_text"
                        ]
                        == ""
                    )
                    page.locator("#original-text").fill("Different synthetic passage")
                    page.wait_for_timeout(1100)
                    expect(page.locator("#trial-working")).to_be_hidden()
                    assert (
                        page.request.get(f"http://127.0.0.1:{port}/api/outgoing-state").json()[
                            "outgoing_text"
                        ]
                        == "Different synthetic passage"
                    )
                    cleanup_slow = False
                    with patch("local_text.phrase_trial.secrets.choice", return_value="manual"):
                        page.locator("#trial-begin").click()
                        expect(page.locator("#trial-working")).to_be_visible()
                    fail_edits = True
                    rejected_edits = []

                    def event_write(route):
                        payload = route.request.post_data_json
                        if fail_edits and payload["action"] == "edit":
                            rejected_edits.append(payload)
                            route.fulfill(status=503, json={"detail": "Synthetic write failure"})
                        else:
                            route.continue_()

                    page.route("**/api/trial/passages/*/events", event_write)
                    page.locator("#trial-passage").fill("Different synthetic repair")
                    page.locator("#trial-note").fill("Synthetic failure control")
                    expect(page.locator("#trial-message")).to_contain_text(
                        "Synthetic write failure"
                    )
                    manual_path = next((root / "trial").glob("passage-*.json"))
                    assert (
                        json.loads(manual_path.read_text())["final_text"]
                        == "Different synthetic passage"
                    )
                    before_cleanup = len(cleanup_requests)
                    for _ in range(2):
                        page.locator("#trial-clean").click()
                        expect(page.locator("#trial-cleanup-state")).to_contain_text(
                            "Cleanup unavailable"
                        )
                        assert len(cleanup_requests) == before_cleanup
                        assert fetch_target_payload().returncode != 0
                        assert (
                            json.loads(manual_path.read_text())["final_text"]
                            == "Different synthetic passage"
                        )
                    assert len(rejected_edits) >= 3
                    fail_edits = False
                    page.locator("#trial-clean").click()
                    expect(page.locator("#trial-cleaned")).to_have_value(
                        "Different synthetic repair!"
                    )
                    manual_record = json.loads(
                        next((root / "trial").glob("passage-*.json")).read_text()
                    )
                    assert manual_record["assignment"] == "manual"
                    assert manual_record["final_text"] == "Different synthetic repair"
                    assert fetch_target_payload().stdout == b"Different synthetic repair!"
                    # A late feedback response must not label a different passage as saved.
                    page.unroute("**/api/trial/passages/*/events", event_write)
                    page.locator("#clear-text").click()
                    page.locator("#original-text").fill("Synthetic late feedback control")
                    with patch("local_text.phrase_trial.secrets.choice", return_value="manual"):
                        page.locator("#trial-begin").click()
                        expect(page.locator("#trial-working")).to_be_visible()
                    hold_feedback = True
                    page.locator("#trial-feedback-save").click()
                    page.wait_for_timeout(100)
                    assert len(pending_feedback) == 1
                    expect(page.locator("#trial-feedback-status")).to_be_hidden()
                    page.locator("#original-text").fill("Synthetic next passage")
                    pending_feedback.pop().continue_()
                    page.wait_for_timeout(200)
                    with patch("local_text.phrase_trial.secrets.choice", return_value="manual"):
                        page.locator("#trial-begin").click()
                        expect(page.locator("#trial-working")).to_be_visible()
                    expect(page.locator("#trial-feedback-status")).to_be_hidden()
                    assert len(calls) == 2 and not errors, errors
                    browser.close()
                    print(
                        "Browser passed: opt-in, both arms, exact occurrence, phrase apply/cancel, "
                        "undo, copy, crossover, late discard, withdrawal/exclusion; page and both "
                        "editors scroll at desktop, short desktop and 390px; Conservative cleanup, "
                        "published target payload, frozen records/feedback, failure, retry, "
                        "late cleanup discard, ordinary non-trial preparation, and nearby feedback "
                        "confirmation, editable resave, failure/retry, reset and late save discard."
                    )
            finally:
                server.should_exit = True
                worker.join(timeout=5)
                database.engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots-dir", type=Path)
    parser.add_argument("--feedback-screenshots", action="store_true")
    parser.add_argument("--scratch-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.screenshots_dir:
        args.screenshots_dir.mkdir(parents=True, exist_ok=True)
    args.scratch_dir.mkdir(parents=True, exist_ok=True)
    run(args.screenshots_dir, args.scratch_dir, args.feedback_screenshots)
