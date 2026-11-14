#!/usr/bin/env python3
"""Synthetic #196 interaction regression checks, not detection-quality evidence.

Run with a Python environment containing Playwright and installed Chromium:
    python3 tests/browser/inspection.py [--screenshots-dir PATH]
    python3 tests/browser/inspection.py --manual

Manual mode opens a fresh, headed Chromium on this host and waits until closed.
The inspection.test address works only inside that mocked browser context, not
in another browser or over a forwarded port. Close and relaunch to reset.

Loads the actual HTML/CSS/JS, intercepts every network request, and uses no
database, credentials, live providers, delivery, or private runtime state.
The inspection-findings DOM event is a UI ingestion boundary, not a detector.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Route, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src/local_text/static"
ORIGINAL = "📝 Send the umber parcel um today. Umber is also a pigment."
PREPARED = "📝 Send the amber parcel today. Umber is also a pigment."


def run_checks(screenshots: Path | None, manual: bool = False) -> None:
    requests = []
    cleanups = []
    errors = []
    pending = []
    delayed = False
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not manual)
        context = browser.new_context(
            viewport={"width": 1480, "height": 1050},
            service_workers="block",
            accept_downloads=False,
        )
        # Fresh context: no signed-in profile, clipboard writes, or download saving.
        context.add_init_script("""Object.defineProperty(navigator, 'clipboard', {
          value: {writeText: async () => {throw new Error('Disabled in synthetic demo');}}
        });""")
        page = context.new_page()
        page.set_default_timeout(5000)
        page.on("pageerror", lambda error: errors.append(str(error)))

        def cleanup_result(text: str) -> dict:
            if text != ORIGINAL:
                return {"status": "unchanged", "prepared_text": text, "lexical_repairs": []}
            return {
                "status": "prepared",
                "prepared_text": PREPARED,
                "lexical_repairs": [
                    {
                        "operation": "replacement",
                        "queue_position": 1,
                        "original_span": {"start": 11, "end": 16, "text": "umber"},
                        "prepared_span": {"start": 11, "end": 16, "text": "amber"},
                        "context": "Send the amber parcel today.",
                        "inspection_reason": "Prepared changed wording; verify intended meaning.",
                    },
                    {
                        "operation": "removal",
                        "queue_position": 2,
                        "original_span": {"start": 24, "end": 26, "text": "um"},
                        "prepared_span": {"start": 24, "end": 24, "text": ""},
                        "context": "Send the amber parcel today.",
                        "inspection_reason": "Prepared removed wording; verify intended meaning.",
                    },
                ],
            }

        def respond(route: Route) -> None:
            nonlocal delayed
            url = route.request.url
            parsed = urlsplit(url)
            if parsed.scheme != "http" or parsed.netloc != "inspection.test":
                route.abort("blockedbyclient")
                return
            if not parsed.path.startswith("/api/"):
                name = {
                    "/": "index.html",
                    "/static/app.js": "app.js",
                    "/static/app.css": "app.css",
                }.get(parsed.path)
                if not name:
                    route.fulfill(status=404)
                    return
                body = (STATIC / name).read_text()
                if name == "index.html":
                    body = (
                        body.replace("__PAGE_TITLE__", "Synthetic inspection — no live detector")
                        .replace("__DISPLAY_NAME__", "Sayloom")
                        .replace("__PROFILE__", "development")
                        .replace(
                            "__DEVELOPMENT_BADGE__",
                            '<span class="development-badge">SYNTHETIC · ALL APIs MOCKED</span>',
                        )
                    )
                route.fulfill(
                    body=body,
                    content_type={
                        "index.html": "text/html",
                        "app.js": "text/javascript",
                        "app.css": "text/css",
                    }[name],
                )
                return
            path = parsed.path.removeprefix("/api/")
            body = route.request.post_data_json if route.request.post_data else None
            requests.append((path, route.request.method, body))
            if path == "config":
                result = {
                    "preparation_default": "off",
                    "cleanup_configuration": {
                        "status": "unavailable",
                        "routes": [],
                        "disclosure": {},
                    },
                }
            elif path == "outgoing-state":
                result = {"revision": len(requests)}
            elif path == "cleanup":
                cleanups.append(body)
                if delayed:
                    pending.append((route, cleanup_result(body["original_text"])))
                    return
                result = cleanup_result(body["original_text"])
            else:
                # Saving, preferences, delivery and every other API fail closed.
                route.fulfill(status=403, json={"detail": "Disabled in synthetic demo"})
                return
            route.fulfill(json=result)

        # Context-wide interception also covers popups; nothing falls through to a server.
        context.route("**/*", respond)
        page.goto("http://inspection.test/")
        expect(page.locator("#draft-preparation-mode")).to_have_value("off")
        original = page.locator("#original-text")
        prepared = page.locator("#prepared-text")
        entries = page.locator(".smart-repair-item")
        cards = page.locator(".inspection-entry")

        def fields() -> tuple[str, str]:
            return original.input_value(), prepared.input_value()

        def selection(selector: str) -> list:
            return page.locator(selector).evaluate("e => [e.selectionStart, e.selectionEnd]")

        def edit(text: str) -> None:
            # Model a partial manual edit, not Playwright fill's full-selection
            # replacement (which intentionally restores the saved default mode).
            original.evaluate(
                """(e, text) => {
              e.value = text;
              e.dispatchEvent(new Event('input', {bubbles:true}));
            }""",
                text,
            )

        def inject(findings: list, **overrides: object) -> dict:
            return page.evaluate(
                """({findings, overrides}) => {
              const e = document.querySelector('#original-text');
              const detail = {original_text:e.value, revision:Number(e.dataset.revision),
                findings, ...overrides};
              e.dispatchEvent(new CustomEvent('inspection-findings', {detail}));
              return detail;
            }""",
                {"findings": findings, "overrides": overrides},
            )

        def finding(start: int, end: int, text: str, suggestion: str | None = None) -> dict:
            result = {
                "original_span": {"start": start, "end": end, "text": text},
                "reason": "Synthetic finding: inspect whether this matches intended wording.",
            }
            if suggestion is not None:
                result["suggestion"] = suggestion
            return result

        def capture(name: str) -> None:
            if screenshots:
                screenshots.mkdir(parents=True, exist_ok=True)
                page.locator(".workspace-shell").screenshot(path=screenshots / name)

        if manual:
            original.fill(ORIGINAL)
            page.select_option("#draft-preparation-mode", "smart", force=True)
            expect(prepared).to_have_value(PREPARED)
            inject([finding(11, 16, "umber", "amber"), finding(50, 57, "pigment")])
            expect(entries).to_have_count(4)
            entries.nth(2).click()
            print(
                "Synthetic inspection demo is open in Chromium on this host.\n"
                "No live detector: both findings and preparation are fixed synthetic fixtures.\n"
                "All browser-context network requests are mocked or blocked; no server/port.\n"
                "Use synthetic text only. No private runtime, credentials, saving, delivery,\n"
                "downloads, or app clipboard writes.\n"
                "Every entry is expanded. Try Keep underneath pigment without selecting it;\n"
                "select finding wording to highlight; edit umber to amber in\n"
                "Original and pause to see Text changed; select the removal repair to see\n"
                "Location unavailable. Prepared updates are mocked, not generated.\n"
                "Close this window (or Ctrl-C) to stop. Close and relaunch to reset.\n"
                "inspection.test is not reachable outside this Chromium context.",
                flush=True,
            )
            try:
                page.wait_for_event("close", timeout=0)
            except KeyboardInterrupt:
                pass
            finally:
                browser.close()
            return

        original.fill(ORIGINAL)
        bound = inject([finding(11, 16, "umber", "amber"), finding(50, 57, "pigment")])
        expect(entries).to_have_count(2)
        expect(page.locator("#smart-repair-selection")).to_have_count(0)
        # Details and per-entry actions are expanded before any selection.
        for card in cards.all():
            expect(card.locator(".inspection-reason")).to_be_visible()
            expect(card.locator(".inspection-location")).to_have_text("Original")
            expect(card.locator(".inspection-keep")).to_be_visible()
        expect(cards.nth(0).locator(".inspection-suggestion")).to_have_text("Suggested: amber")
        expect(cards.nth(1).locator(".inspection-suggestion")).to_have_count(0)
        before = fields()
        # UTF-16 selection must account for the leading supplementary character.
        entries.nth(0).focus()
        page.keyboard.press("Enter")
        assert selection("#original-text") == [12, 17]
        assert fields() == before
        page.wait_for_timeout(850)
        assert len(cleanups) == 0, "Preparation off, selection and inaction must not generate"
        # Keep on an unselected entry cannot dismiss the selected finding instead.
        # No replacement is required. Keyboard-only Keep changes neither field.
        cards.nth(1).locator(".inspection-keep").focus()
        page.keyboard.press("Enter")
        expect(entries).to_have_count(1)
        expect(entries.first.locator(".smart-repair-item-change")).to_have_text("umber")
        expect(entries.first).to_be_focused()
        assert fields() == before
        assert len(cleanups) == 0

        page.select_option("#draft-preparation-mode", "smart", force=True)
        expect(prepared).to_have_value(PREPARED)
        expect(entries).to_have_count(3)
        # Applied repairs include details before selection, but never dismissal.
        for card in cards.all()[1:]:
            expect(card.locator(".inspection-context")).to_be_visible()
            expect(card.locator(".inspection-reason")).to_be_visible()
            expect(card.locator(".inspection-keep")).to_have_count(0)
        entries.nth(1).click()
        assert selection("#prepared-text") == [12, 17]
        assert fields() == (ORIGINAL, PREPARED)
        # The removal selects exact Original wording, never its empty Prepared span.
        entries.nth(2).click()
        assert selection("#original-text") == [25, 27]
        inject([finding(11, 16, "umber", "amber")])
        entries.nth(3).click()
        expect(cards.nth(3).locator(".inspection-location")).to_have_text("Original")
        cards.nth(3).scroll_into_view_if_needed()
        capture("196-expanded-current-final.png")

        # Two quick edits use one existing debounce, retaining entries throughout.
        count = len(cleanups)
        edit(ORIGINAL.replace("umber parcel um", "amber parcel"))
        original.press("End")
        original.type(" ")
        expect(entries).to_have_count(4)
        entries.nth(3).click()
        expect(cards.nth(3).locator(".inspection-location")).to_have_text("Text changed")
        expect(cards.nth(3).locator(".inspection-suggestion")).to_have_attribute(
            "aria-disabled", "true"
        )
        assert selection("#original-text")[0] == selection("#original-text")[1]
        assert selection("#prepared-text") == [0, 0]
        expect(prepared).to_have_value(original.input_value())
        assert len(cleanups) == count + 1
        expect(entries).to_have_count(4)
        # Stale suggestions and repair status remain visible without selection.
        expect(cards.nth(0).locator(".inspection-location")).to_have_text("Text changed")
        expect(cards.nth(2).locator(".inspection-location")).to_have_text("Location unavailable")
        entries.nth(2).click()
        expect(cards.nth(2).locator(".inspection-location")).to_have_text("Location unavailable")
        assert selection("#prepared-text") == [0, 0]
        cards.nth(2).scroll_into_view_if_needed()
        capture("196-expanded-stale-final.png")

        # Matching wording restored in the same place must not resurrect bindings.
        edit(ORIGINAL)
        expect(prepared).to_have_value(PREPARED)
        expect(entries).to_have_count(6)
        entries.nth(3).click()
        expect(cards.nth(3).locator(".inspection-location")).to_have_text("Text changed")
        entries.nth(1).click()
        expect(cards.nth(1).locator(".inspection-location")).to_have_text("Location unavailable")
        assert selection("#prepared-text") == [0, 0]
        # Stale, wrong-passage and invalid-offset findings are rejected atomically.
        inject(bound["findings"], revision=bound["revision"])
        inject(bound["findings"], original_text=ORIGINAL + " Other passage.")
        inject([finding(11, 16, "umber"), finding(999, 1000, "x")])
        expect(entries).to_have_count(6)

        # A new result with identical text still cannot rebind an older Prepared repair.
        count = len(cleanups)
        page.click("#run-cleanup")
        expect(entries).to_have_count(8)
        entries.nth(4).click()
        expect(cards.nth(4).locator(".inspection-location")).to_have_text("Location unavailable")
        entries.nth(6).click()
        assert selection("#prepared-text") == [12, 17]
        page.click("#maximize-prepared")
        page.wait_for_function("document.querySelector('#prepared-text').selectionEnd === 0")
        entries.nth(6).click()
        page.wait_for_function("document.querySelector('#prepared-text').selectionEnd === 0")
        assert selection("#prepared-text") == [0, 0], "CART selection must not mark output"
        page.click("#maximize-prepared")
        assert len(cleanups) == count + 1

        # Preserve both existing desktop layouts; no mobile scope or extra captures.
        for width in (1280, 1480):
            page.set_viewport_size({"width": width, "height": 1050})
            for layout in ("side-by-side", "stacked"):
                page.click(f"#layout-{layout}")
                expect(original).to_be_visible()
                expect(prepared).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

        # Inspection and mode changes respect open correction / confirmed Prepared.
        page.click("#correct-prepared")
        page.select_option("#draft-preparation-mode", "off", force=True)
        page.wait_for_timeout(850)
        assert len(cleanups) == count + 1
        page.fill("#intended-prepared", "Owner-confirmed synthetic wording.")
        page.click("#confirm-prepared")
        expect(prepared).to_have_value("Owner-confirmed synthetic wording.")
        inject([finding(11, 16, "umber")])
        cards.last.locator(".inspection-keep").click()
        page.select_option("#draft-preparation-mode", "smart", force=True)
        page.wait_for_timeout(850)
        assert len(cleanups) == count + 1
        expect(prepared).to_have_value("Owner-confirmed synthetic wording.")

        # Late response after edit / mode-off cannot update Prepared or inspection.
        delayed = True
        edit(ORIGINAL + " Late.")
        page.wait_for_function(
            "document.querySelector('#outgoing-kind').dataset.state === 'cleaning'"
        )
        page.wait_for_timeout(100)
        assert pending
        edit("Newest synthetic passage.")
        page.select_option("#draft-preparation-mode", "off", force=True)
        retained = entries.count()
        for route, result in pending:
            route.fulfill(json=result)
        page.wait_for_timeout(850)
        expect(prepared).to_have_value("")
        expect(entries).to_have_count(retained)
        assert original.input_value() == "Newest synthetic passage."
        assert all(path in {"config", "outgoing-state", "cleanup"} for path, _, _ in requests)
        page.click("#clear-text")
        expect(entries).to_have_count(0)
        page.reload()
        expect(entries).to_have_count(0)
        assert not errors, errors
        print(
            json.dumps(
                {
                    "passed": True,
                    "synthetic_only": True,
                    "cleanup_requests": len(cleanups),
                    "browser_errors": errors,
                    "saved_correction_requests": 0,
                    "live_provider_requests": 0,
                }
            )
        )
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots-dir", type=Path)
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Open an isolated synthetic demo on this host; close it to stop",
    )
    arguments = parser.parse_args()
    run_checks(arguments.screenshots_dir, manual=arguments.manual)
