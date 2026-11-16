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
              const p = document.querySelector('#prepared-text');
              const detail = {original_text:e.value, revision:Number(e.dataset.revision),
                prepared_text:p.value, prepared_generation:Number(p.dataset.generation),
                findings, ...overrides};
              e.dispatchEvent(new CustomEvent('inspection-findings', {detail}));
              return detail;
            }""",
                {"findings": findings, "overrides": overrides},
            )

        def finding(start: int, end: int, text: str, alternatives: list[str] | None = None) -> dict:
            # Explicit mapping for this synthetic response only. Production must
            # supply independently bound Prepared spans, never copy source offsets.
            mapped = fields() == (ORIGINAL, PREPARED)
            target_start = start - 3 if mapped and start >= 27 else start
            target_text = "amber" if mapped and start == 11 else text
            return {
                "original_span": {"start": start, "end": end, "text": text},
                "prepared_span": {"start": target_start, "end": target_start + len(target_text),
                                  "text": target_text},
                "reason": "Synthetic finding: inspect whether this matches intended wording.",
                "alternatives": alternatives or [],
            }

        def capture(name: str) -> None:
            if screenshots:
                screenshots.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=screenshots / name, full_page=True, animations="disabled")

        if manual:
            original.fill(ORIGINAL)
            page.select_option("#draft-preparation-mode", "smart", force=True)
            expect(prepared).to_have_value(PREPARED)
            inject([
                finding(34, 39, "Umber", ["Amber", "Ochre"]),
                finding(50, 57, "pigment"),
                finding(17, 23, "parcel", ["package"]),
            ])
            expect(entries).to_have_count(5)
            page.locator("#workspace-resizer").focus()
            page.keyboard.press("Home")
            print(
                "Synthetic inspection demo is open in Chromium on this host.\n"
                "No live detector: both findings and preparation are fixed synthetic fixtures.\n"
                "All browser-context network requests are mocked or blocked; no server/port.\n"
                "Use synthetic text only. No private runtime, credentials, saving, delivery,\n"
                "downloads, or app clipboard writes.\n"
                "Inspection stays right of Prepared with compact colour-matched entries.\n"
                "Try Keep on pigment without selecting it; Original stays unmarked.\n"
                "See all marked findings before selection; compare zero, one or multiple\n"
                "alternatives (viewing them applies nothing); select wording to highlight;\n"
                "edit umber to amber in\n"
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
        page.select_option("#draft-preparation-mode", "conservative", force=True)
        expect(prepared).to_have_value(PREPARED)
        bound = inject([finding(11, 16, "umber", ["amber", "ochre"]), finding(50, 57, "pigment")])
        expect(entries).to_have_count(2)
        marks = page.locator("#prepared-highlights mark")
        expect(marks).to_have_text(["amber", "pigment"])
        expect(page.locator('mark[data-selected="true"]')).to_have_count(0)
        assert original.input_value() == ORIGINAL
        assert page.locator("#prepared-highlights").text_content() == PREPARED + "\n"
        expect(page.locator("#original-highlights")).to_have_count(0)
        assert marks.first.evaluate("e => getComputedStyle(e).textDecorationStyle") == "wavy"
        assert page.locator("#prepared-highlights").get_attribute("aria-hidden") == "true"
        page.locator("#workspace-resizer").focus()
        page.keyboard.press("Home")
        expect(page.locator("#smart-repair-selection")).to_have_count(0)
        # Details and per-entry actions are expanded before any selection.
        for card in cards.all():
            expect(card.locator(".inspection-reason")).to_be_visible()
            expect(card.locator(".inspection-location")).to_have_text("Prepared")
            expect(card.locator(".inspection-keep")).to_be_visible()
        expect(cards.nth(0).locator(".inspection-suggestion")).to_have_text(["amber", "ochre"])
        expect(cards.nth(1).locator(".inspection-suggestion")).to_have_count(0)
        # One option is also valid. Adding/removing it leaves other findings marked.
        inject([finding(34, 39, "Umber", ["Amber"])])
        expect(cards.last.locator(".inspection-suggestion")).to_have_text("Amber")
        expect(marks).to_have_text(["amber", "Umber", "pigment"])
        cards.last.locator(".inspection-keep").click()
        expect(marks).to_have_text(["amber", "pigment"])
        before = fields()
        page.click("#layout-side-by-side")
        # UTF-16 selection must account for the leading supplementary character.
        entries.nth(0).focus()
        page.keyboard.press("Enter")
        assert selection("#prepared-text") == [12, 17]
        expect(page.locator('mark[data-selected="true"]')).to_have_text("amber")
        assert marks.first.evaluate("e => getComputedStyle(e).textDecorationStyle") == "double"
        page.click("#layout-stacked")
        # Viewing the non-first hypothesis is not an application action.
        cards.first.locator(".inspection-suggestion").nth(1).click()
        assert fields() == before
        page.wait_for_timeout(850)
        assert len(cleanups) == 1, "Selection and inaction must not generate"
        # Keep on an unselected entry cannot dismiss the selected finding instead.
        # No replacement is required. Keyboard-only Keep changes neither field.
        cards.nth(1).locator(".inspection-keep").focus()
        page.keyboard.press("Enter")
        expect(entries).to_have_count(1)
        expect(entries.first.locator(".smart-repair-item-change")).to_have_text("amber")
        expect(entries.first).to_be_focused()
        expect(marks).to_have_text(["amber"])
        assert fields() == before
        assert len(cleanups) == 1

        page.select_option("#draft-preparation-mode", "smart", force=True)
        expect(prepared).to_have_value(PREPARED)
        expect(marks).to_have_text(["amber"])  # Only the newly bound repair is marked.
        expect(entries).to_have_count(3)
        # Applied repairs include details before selection, but never dismissal.
        for card in cards.all()[1:]:
            expect(card.locator(".inspection-reason")).to_be_visible()
            expect(card.locator(".inspection-keep")).to_have_count(0)
        entries.nth(1).click()
        assert selection("#prepared-text") == [12, 17]
        assert fields() == (ORIGINAL, PREPARED)
        # The removal selects exact Original wording, never its empty Prepared span.
        entries.nth(2).click()
        assert selection("#original-text") == [25, 27]
        inject([finding(11, 16, "umber", ["amber", "ochre"])])
        entries.nth(3).click()
        expect(cards.nth(3).locator(".inspection-location")).to_have_text("Prepared")
        cards.nth(3).scroll_into_view_if_needed()
        # CART suppresses even current unresolved marks, not only stale ones.
        expect(marks).to_have_text(["amber"])
        page.click("#maximize-prepared")
        expect(marks).to_have_count(0)
        expect(page.locator("#prepared-highlights")).to_be_hidden()
        entries.nth(3).click()
        page.wait_for_function("document.querySelector('#prepared-text').selectionEnd === 0")
        assert selection("#prepared-text") == [0, 0]
        page.click("#maximize-prepared")
        expect(marks).to_have_text(["amber"])

        # Two quick edits use one existing debounce, retaining entries throughout.
        count = len(cleanups)
        edit(ORIGINAL.replace("umber parcel um", "amber parcel"))
        original.press("End")
        original.type(" ")
        expect(entries).to_have_count(4)
        entries.nth(3).click()
        expect(cards.nth(3).locator(".inspection-location")).to_have_text("Text changed")
        for option in cards.nth(3).locator(".inspection-suggestion").all():
            expect(option).to_have_attribute("aria-disabled", "true")
        expect(marks).to_have_count(0)
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
        cards.nth(3).scroll_into_view_if_needed()
        capture("196-prepared-stale.png")

        # Matching wording restored in the same place must not resurrect bindings.
        edit(ORIGINAL)
        expect(prepared).to_have_value(PREPARED)
        expect(entries).to_have_count(6)
        expect(marks).to_have_text(["amber"])
        entries.nth(3).click()
        expect(cards.nth(3).locator(".inspection-location")).to_have_text("Text changed")
        entries.nth(1).click()
        expect(cards.nth(1).locator(".inspection-location")).to_have_text("Location unavailable")
        assert selection("#prepared-text") == [0, 0]
        # Stale, wrong-passage and invalid-offset findings are rejected atomically.
        inject(bound["findings"], revision=bound["revision"])
        inject(bound["findings"], original_text=ORIGINAL + " Other passage.")
        inject(bound["findings"], prepared_text=PREPARED + " Other result.")
        inject(bound["findings"], prepared_generation=bound["prepared_generation"])
        wrong_target = finding(50, 57, "pigment")
        wrong_target["prepared_span"] = wrong_target["original_span"]
        inject([wrong_target])  # Removal shifted this occurrence by three code points.
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
        inject([{**finding(11, 16, "umber"),
                 "prepared_span": {"start": 0, "end": 5, "text": "Owner"}}])
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
        delayed = False
        page.reload()
        expect(page.locator("#draft-preparation-mode")).to_have_value("off")
        expect(entries).to_have_count(0)
        expect(marks).to_have_count(0)
        # Plain text, repeated occurrences, overlaps, wrapping and native editing.
        text = "📝 umber umber <b>& text\t" + ("wrapped text " * 18 + "\n") * 30 + "umber\n"
        original.fill(text)
        page.select_option("#draft-preparation-mode", "conservative", force=True)
        expect(prepared).to_have_value(text)
        second = text.index("umber", text.index("umber") + 1)
        last = text.rindex("umber")
        inject([finding(second, second + 5, "umber", ["amber", "ochre"]),
                finding(last, last + 5, "umber")])
        expect(marks).to_have_text(["umber", "umber"])
        assert page.locator("#prepared-highlights").text_content() == text + "\n"
        expect(page.locator("#prepared-highlights b")).to_have_count(0)
        page.click("#select-original")
        assert any(path == "outgoing-state" and body and body.get("outgoing_text") == text
                   for path, _, body in requests)
        # Invalid/duplicate alternatives reject a whole batch without marking it.
        inject([finding(2, 7, "umber"), finding(second, second + 5, "umber", ["x", "x"])])
        inject([{**finding(2, 7, "umber"), "alternatives": [42]}])
        expect(entries).to_have_count(2)
        # Legacy one-suggestion producers are preserved at the existing UI boundary.
        legacy = finding(2, 7, "umber")
        legacy.pop("alternatives")
        legacy["suggestion"] = "amber"
        inject([legacy])
        expect(marks).to_have_count(3)
        inject([finding(2, second + 5, text[2:second + 5])])
        assert page.locator("#prepared-highlights").text_content() == text + "\n"
        for width in (1280, 1480):
            page.set_viewport_size({"width": width, "height": 1050})
            for layout in ("side-by-side", "stacked"):
                page.click(f"#layout-{layout}")
                prepared.evaluate("e => {e.scrollTop = e.scrollHeight;}")
                page.wait_for_function("""() => {
                  const e = document.querySelector('#prepared-text');
                  const m = document.querySelector('#prepared-highlights');
                  return e.scrollTop > 0 && e.scrollTop === m.scrollTop
                    && e.clientWidth === m.clientWidth;
                }""")
                assert prepared.evaluate("""e => {
                  const m = document.querySelector('#prepared-highlights');
                  const a = getComputedStyle(e), b = getComputedStyle(m);
                  return ['fontFamily', 'fontSize', 'lineHeight', 'letterSpacing', 'padding']
                    .every(k => a[k] === b[k]);
                }""")
        # A real keyboard replacement touches just the selected occurrence; undo
        # restores wording but must not revive the now-stale finding bindings.
        page.select_option("#draft-preparation-mode", "off", force=True)
        count = len(cleanups)
        original.focus()
        original.evaluate("(e, start) => e.setSelectionRange(start, start + 5)", second + 1)
        page.keyboard.insert_text("amber")
        expect(original).to_have_value(text[:second] + "amber" + text[second + 5:])
        expect(marks).to_have_count(0)
        page.keyboard.press("ControlOrMeta+z")
        expect(original).to_have_value(text)
        expect(marks).to_have_count(0)
        expect(entries).to_have_count(4)
        page.click("#clear-text")
        expect(entries).to_have_count(0)
        page.wait_for_timeout(850)
        assert len(cleanups) == count == 7
        delayed = False
        original.fill(ORIGINAL)
        page.select_option("#draft-preparation-mode", "smart", force=True)
        expect(prepared).to_have_value(PREPARED)
        inject([finding(34, 39, "Umber", ["Amber", "Ochre"]),
                finding(50, 57, "pigment"), finding(17, 23, "parcel", ["package"])])
        expect(entries).to_have_count(5)
        page.click("#layout-stacked")
        page.locator("#workspace-resizer").focus()
        page.keyboard.press("Home")
        expect(marks).to_have_text(["amber", "parcel", "Umber", "pigment"])
        # Right-hand placement and matched backgrounds are observable contracts.
        assert page.locator("#smart-repair-review").bounding_box()["x"] >= (
            prepared.bounding_box()["x"] + prepared.bounding_box()["width"]
        )
        for mark in marks.all():
            tone = mark.get_attribute("data-tone")
            card = page.locator(f'.inspection-entry[data-tone="{tone}"]').first
            assert mark.evaluate("e => getComputedStyle(e).backgroundColor") == card.evaluate(
                "e => getComputedStyle(e).backgroundColor"
            )
        capture("196-prepared-before-selection.png")
        pigment = marks.last.bounding_box()
        page.mouse.click(pigment["x"] + pigment["width"] / 2,
                         pigment["y"] + pigment["height"] / 2)
        expect(cards.nth(3)).to_have_attribute("data-selected", "true")
        entries.nth(2).focus()
        page.keyboard.press("Enter")
        expect(page.locator('mark[data-selected="true"]')).to_have_text("Umber")
        assert selection("#prepared-text") == [32, 37]  # Not Original's [35, 40].
        assert selection("#original-text")[0] == selection("#original-text")[1]
        assert prepared.evaluate("e => getComputedStyle(e, '::selection').backgroundColor") == (
            cards.nth(2).evaluate("e => getComputedStyle(e).backgroundColor")
        )
        capture("196-prepared-selected-options.png")
        before = fields()
        page.click("#select-prepared")
        assert any(path == "outgoing-state" and body and body.get("outgoing_text") == PREPARED
                   for path, _, body in requests)
        assert fields() == before
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
