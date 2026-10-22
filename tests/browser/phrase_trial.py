#!/usr/bin/env python3
"""Real browser/API trial checks. Synthetic provider only; no credentials or paid calls.

Requires installed Python Playwright and Chromium. Takes at most three targeted
screenshots, if --screenshots-dir is supplied. All state uses a disposable directory.
"""

import argparse
import asyncio
import json
import socket
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
from local_text.cleanup import CleanupService, PreparationMode
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


def run(screenshots: Path | None, scratch: Path):
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
            cleanup_service=CleanupService(provider=None, model="synthetic", timeout_seconds=30),
            trial_transport=httpx.MockTransport(provider),
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
                            cleanup_requests.append(request.url)
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
                    if screenshots:
                        page.locator(".workspace-shell").screenshot(
                            path=screenshots / "trial-ready.png"
                        )
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
                    if screenshots:
                        page.locator(".workspace-shell").screenshot(
                            path=screenshots / "trial-alternatives.png"
                        )
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
                    if screenshots:
                        page.locator("#trial-panel").screenshot(
                            path=screenshots / "trial-phrase-edit-390.png"
                        )
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
                    page.locator("#trial-exit").click()
                    expect(page.locator("#trial-working")).to_be_hidden()
                    expect(page.locator("#trial-panel")).to_be_hidden()
                    expect(page.locator(".prepared-panel")).to_be_visible()
                    expect(page.locator("#trial-include")).to_be_checked()
                    assert not list((root / "trial").glob("passage-*.json"))

                    page.set_viewport_size({"width": 1200, "height": 1050})
                    with patch("local_text.phrase_trial.secrets.choice", return_value="manual"):
                        page.locator("#clear-text").click()
                        page.locator("#original-text").fill(TEXT)
                        page.locator("#trial-begin").click()
                        expect(page.locator("#trial-switch")).to_be_visible()
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
                    expect(page.locator("#trial-message")).to_contain_text("excluded and deleted")
                    assert not list((root / "trial").glob("passage-*.json"))
                    assert len(calls) == 2 and not errors, errors
                    browser.close()
                    print(
                        "Browser passed: opt-in, both arms, exact occurrence, phrase apply/cancel, "
                        "undo, copy, crossover, late discard, withdrawal/exclusion; page and both "
                        "editors scroll at desktop, short desktop and 390px."
                    )
            finally:
                server.should_exit = True
                worker.join(timeout=5)
                database.engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots-dir", type=Path)
    parser.add_argument("--scratch-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.screenshots_dir:
        args.screenshots_dir.mkdir(parents=True, exist_ok=True)
    args.scratch_dir.mkdir(parents=True, exist_ok=True)
    run(args.screenshots_dir, args.scratch_dir)
