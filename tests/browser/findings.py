#!/usr/bin/env python3
"""Synthetic normal-route #197 supply checks, not recognition-quality evidence.

Run with a Python containing Playwright and installed Chromium:
    python3 tests/browser/findings.py [--screenshots-dir PATH]

Browser HTTP requests cross the actual FastAPI /api/cleanup route, service,
sequential router, and OpenAI adapter using MockTransport. The child interpreter
uses the project venv; no browser package is added to project dependencies.
Database/prompt admission is stubbed in memory. No migrations, operating data,
live network, credentials, saving, delivery, or OS clipboard are used.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src/local_text/static"
ORIGINAL = "📝 send umber then umber parcel pigment"
PREPARED = "📝 Send umber, then umber parcel pigment."


def provider_payload(text: str, scenario: str) -> dict:
    # These are transport fixtures, not claims about intended wording or evaluation cases.
    prepared = PREPARED if text == ORIGINAL else text.strip()
    findings = (
        [
            {
                "original_span": {"start": start, "end": end, "text": word},
                "prepared_span": {"start": start + 1, "end": end + 1, "text": word},
                "reason": "Synthetic recognition hypothesis; not verified intent.",
                "alternatives": alternatives,
            }
            for start, end, word, alternatives in [
                (18, 23, "umber", ["amber", "ochre"]),
                (24, 30, "parcel", ["package"]),
                (31, 38, "pigment", []),
            ]
        ]
        if text == ORIGINAL
        else []
    )
    payload = {"prepared_text": prepared, "findings": findings}
    if scenario == "empty":
        payload["findings"] = []
    elif scenario == "removal" and findings:
        findings[0]["alternatives"] = [""]
    elif scenario == "long_alternative" and findings:
        findings[0]["alternatives"] = ["amber", "ochre 🟠"]
    elif scenario == "smart_repair" and findings:
        payload["prepared_text"] = "📝 Send amber, then umber parcel pigment."
    elif scenario == "partial":
        payload["findings"] = [None, *findings, {"reason": "x" * 161}]
    elif scenario == "all_invalid":
        payload["findings"] = [None, {}]
    elif scenario == "unavailable":
        del payload["findings"]
    elif scenario == "invalid_prepared":
        payload["prepared_text"] = "Unrelated invented wording."
    elif scenario.startswith("lifecycle_"):
        payload["prepared_text"] = text
        payload["findings"] = [
            {
                "original_span": {"start": start, "end": start + len(word), "text": word},
                "prepared_span": {"start": start, "end": start + len(word), "text": word},
                "reason": "Synthetic occurrence pending contextual review.",
                "alternatives": ["replacement"],
            }
            for word in ("umber", "parcel", "pigment")
            if (start := text.rfind(word)) >= 0
        ]
        if scenario == "lifecycle_complete":
            payload["findings"] = []
        elif scenario == "lifecycle_partial":
            payload["findings"] = [*payload["findings"][:1], None]
        elif scenario == "lifecycle_unavailable":
            del payload["findings"]
        elif scenario == "lifecycle_failure":
            payload["prepared_text"] = "Unrelated invented wording."
    return payload


def http_worker() -> None:
    import httpx
    from fastapi.testclient import TestClient

    import local_text.app as app_module
    from local_text.cleanup import (
        CleanupPartitionSchedule,
        CleanupRoute,
        CleanupService,
        OpenAIAdapter,
        PreparationMode,
        SequentialCleanupProvider,
    )
    from local_text.config import Profile, Settings

    current = {}
    provider_calls = 0

    def respond(_request):
        nonlocal provider_calls
        provider_calls += 1
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(current),
                            }
                        ],
                    }
                ],
            },
        )

    # Nothing can open a database or a real provider connection in this worker.
    with (
        patch.object(app_module, "ApplicationDatabase") as database,
        patch.object(app_module, "PromptStore") as prompts,
        patch.object(app_module, "_new_provider_client", side_effect=AssertionError("Live client")),
        patch("socket.create_connection", side_effect=AssertionError("Network blocked")),
    ):
        database.return_value.schema_status.return_value = SimpleNamespace(ready=True)
        database.return_value.session_factory.side_effect = AssertionError("Storage blocked")
        prompts.return_value.preparation_default.return_value = PreparationMode.OFF
        prompts.return_value.active.return_value = SimpleNamespace(
            id=1,
            system_text="Synthetic instruction",
        )
        provider_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        adapter = OpenAIAdapter("synthetic-not-a-credential", provider_client)
        router = SequentialCleanupProvider(
            (CleanupRoute(adapter, "synthetic-quota"),),
            partition_schedule=CleanupPartitionSchedule(7, (7,)),
        )
        app = app_module.create_app(
            Settings(Profile.DEVELOPMENT, database_path=Path("unused-synthetic.sqlite3")),
            CleanupService(router, adapter.model, 7),
        )
        with TestClient(app) as client:
            for line in sys.stdin:
                message = json.loads(line)
                current = provider_payload(message["body"]["original_text"], message["scenario"])
                before = provider_calls
                response = client.post("/api/cleanup", json=message["body"])
                assert response.status_code == 200
                print(
                    json.dumps({"result": response.json(), "calls": provider_calls - before}),
                    flush=True,
                )
        import asyncio

        asyncio.run(provider_client.aclose())


def run_checks(screenshots: Path | None) -> None:
    from playwright.sync_api import expect, sync_playwright

    worker = subprocess.Popen(
        [str(ROOT / ".venv/bin/python"), str(Path(__file__).resolve()), "--http-worker"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        cwd=ROOT,
    )
    requests, results, errors, pending = [], [], [], []
    scenario = "valid"
    delayed = False

    def cleanup(body):
        worker.stdin.write(json.dumps({"body": body, "scenario": scenario}) + "\n")
        worker.stdin.flush()
        result = json.loads(worker.stdout.readline())
        assert result["calls"] == int(body.get("enabled", True))
        results.append(result["result"])
        return result["result"]

    try:
        # HTTP Off also returns no findings and does not invoke the provider.
        off = cleanup({"original_text": ORIGINAL, "enabled": False})
        assert off["status"] == "disabled" and off["findings"] == []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1480, "height": 1050},
                service_workers="block",
                accept_downloads=False,
            )
            context.add_init_script("""window.syntheticCopies = [];
              Object.defineProperty(navigator, 'clipboard', {value: {
                writeText: async text => window.syntheticCopies.push(text)}});""")
            page = context.new_page()
            page.set_default_timeout(5000)
            page.on("pageerror", lambda error: errors.append(str(error)))

            def respond(route):
                parsed = urlsplit(route.request.url)
                if parsed.scheme != "http" or parsed.netloc != "findings.test":
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
                            body.replace("__PAGE_TITLE__", "Synthetic findings supply")
                            .replace("__DISPLAY_NAME__", "Sayloom")
                            .replace("__PROFILE__", "development")
                            .replace(
                                "__DEVELOPMENT_BADGE__",
                                '<span class="development-badge">'
                                "SYNTHETIC · NO LIVE PROVIDERS</span>",
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
                    if scenario == "http_failure":
                        route.fulfill(status=503, json={"detail": "Synthetic failure"})
                        return
                    if scenario == "network_failure":
                        route.abort("failed")
                        return
                    if scenario == "malformed_response":
                        route.fulfill(body="{", content_type="application/json")
                        return
                    result = cleanup(body)
                    if delayed:
                        pending.append((route, result))
                        return
                else:
                    route.fulfill(status=403, json={"detail": "Disabled in synthetic checks"})
                    return
                route.fulfill(json=result)

            context.route("**/*", respond)
            page.goto("http://findings.test/")
            original, prepared = page.locator("#original-text"), page.locator("#prepared-text")
            cards = page.locator(".inspection-entry")
            marks = page.locator("#prepared-highlights mark")
            review = page.locator("#smart-repair-review")
            note = page.locator("#smart-repair-note")

            def capture(name):
                if screenshots:
                    screenshots.mkdir(parents=True, exist_ok=True)
                    page.locator(".workspace").screenshot(
                        path=screenshots / name, animations="disabled"
                    )

            def edit(text):
                original.evaluate(
                    """(e, text) => {e.value = text;
                  e.dispatchEvent(new Event('input', {bubbles:true}));} """,
                    text,
                )

            # Real edits and controlled responses use the normal preparation route.
            # Identical flagged wording can be resolved by surrounding context.
            scenario = "lifecycle_valid"
            original.fill(ORIGINAL)
            page.select_option("#draft-preparation-mode", "conservative", force=True)
            expect(cards).to_have_count(3)
            capture("197-lifecycle-current.png")
            delayed = True
            scenario = "lifecycle_complete"
            original.focus()
            original.evaluate("e => e.setSelectionRange(0, 0)")
            page.keyboard.insert_text("🟠 Context: ")
            expect(cards).to_have_count(3)
            expect(cards.first.locator(".inspection-location")).to_have_text("Awaiting recheck")
            for radio in cards.get_by_role("radio").all():
                expect(radio).to_be_disabled()
            for button in cards.locator(".inspection-keep").all():
                expect(button).to_be_disabled()
            capture("197-lifecycle-pending.png")
            page.wait_for_timeout(850)
            assert len(pending) == 1
            route, result = pending.pop()
            assert result["findings_status"] == "complete" and not result["findings"]
            route.fulfill(json=result)
            expect(cards).to_have_count(0)
            expect(prepared).to_have_value("🟠 Context: " + ORIGINAL)
            delayed = False

            for outcome in (
                "partial",
                "unavailable",
                "failure",
                "http_failure",
                "network_failure",
                "malformed_response",
            ):
                scenario = "lifecycle_valid"
                page.reload()
                original.fill(ORIGINAL)
                page.select_option("#draft-preparation-mode", "smart", force=True)
                expect(cards).to_have_count(3)
                # Shifting by a non-BMP prefix must preserve exact occurrence identity.
                scenario = (
                    f"lifecycle_{outcome}"
                    if outcome in ("partial", "unavailable", "failure")
                    else outcome
                )
                original.focus()
                original.evaluate("e => e.setSelectionRange(0, 0)")
                page.keyboard.insert_text("🟠 ")
                expect(cards.first.locator(".inspection-location")).to_have_text("Awaiting recheck")
                if outcome not in ("partial", "unavailable"):
                    expect(page.locator("#retry-cleanup")).to_be_visible()
                    expect(prepared).to_have_value("🟠 " + ORIGINAL)
                    expect(cards.filter(has_text="Not rechecked")).to_have_count(3)
                    if outcome == "failure":
                        for width in (1280, 1480):
                            page.set_viewport_size({"width": width, "height": 1050})
                            for layout in ("stacked", "side-by-side"):
                                page.click(f"#layout-{layout}")
                                footer = page.locator(".original-panel-footer").bounding_box()
                                retry = page.locator("#retry-cleanup").bounding_box()
                                assert (
                                    0
                                    <= footer["x"] + footer["width"] - (retry["x"] + retry["width"])
                                    <= 16
                                )
                                assert retry["x"] > footer["x"] + footer["width"] / 2
                                assert page.evaluate(
                                    "document.documentElement.scrollWidth <= innerWidth"
                                )
                        page.click("#layout-stacked")
                        capture("197-lifecycle-retry.png")
                    count = len(results)
                    scenario = "lifecycle_valid"
                    # Button retries the same Smart request, not a mode switch.
                    page.click("#retry-cleanup")
                    expect(review).to_have_attribute("data-findings-status", "complete")
                    assert len(results) == count + 1 and results[-1]["correction_mode"] == "smart"
                    expect(page.locator("#retry-cleanup")).to_be_hidden()
                else:
                    expect(review).to_have_attribute("data-findings-status", outcome)
                    expect(prepared).to_have_value("🟠 " + ORIGINAL)
                    expect(cards).to_have_count(3)
                    expect(cards.filter(has_text="Not rechecked")).to_have_count(
                        2 if outcome == "partial" else 3
                    )
                    expect(cards.locator("input:not(:disabled)")).to_have_count(
                        1 if outcome == "partial" else 0
                    )
                    expect(note).to_contain_text(
                        "Findings incomplete" if outcome == "partial" else "Findings unavailable"
                    )
                # An edited occurrence disappears even from a retained incomplete result.
                original.focus()
                original.evaluate("""e => {const start = e.value.indexOf('parcel');
                  e.setSelectionRange(start, start + 6);} """)
                page.keyboard.insert_text("package")
                expect(cards).to_have_count(2)
                expect(cards.filter(has_text="parcel")).to_have_count(0)
                expect(cards.first.locator(".inspection-location")).to_have_text("Awaiting recheck")
                # Cancel pending automatic work without requesting another stream.
                page.select_option("#draft-preparation-mode", "off", force=True)

            # Repeated wording: deleting the unflagged first occurrence must not
            # delete the flagged second occurrence, or revive it at another word.
            for remove_flagged in (False, True, "backward"):
                scenario = "lifecycle_valid"
                delayed = False
                page.reload()
                original.fill("📝 umber umber parcel pigment")
                page.select_option("#draft-preparation-mode", "conservative", force=True)
                expect(cards).to_have_count(3)
                delayed = True
                scenario = "lifecycle_partial"
                original.focus()
                if remove_flagged == "backward":
                    original.evaluate("""e => {const start = e.value.lastIndexOf('umber');
                      e.setSelectionRange(start, start);} """)
                    page.keyboard.press("Alt+Backspace")
                    expect(original).to_have_value("📝 umber parcel pigment")
                else:
                    original.evaluate(
                        """(e, last) => {const start = last ? e.value.lastIndexOf('umber')
                          : e.value.indexOf('umber'); e.setSelectionRange(start, start + 6);} """,
                        remove_flagged,
                    )
                    page.keyboard.press("Backspace")
                expect(cards).to_have_count(2 if remove_flagged is True else 3)
                expect(cards.filter(has_text="umber")).to_have_count(
                    0 if remove_flagged is True else 1
                )
                page.wait_for_timeout(850)
                assert len(pending) == 1
                route, result = pending.pop()
                route.fulfill(json=result)
                expect(review).to_have_attribute("data-findings-status", "partial")
                # A returned finding for the surviving occurrence replaces, not duplicates.
                expect(cards).to_have_count(3)
                expect(cards.locator("input:not(:disabled)")).to_have_count(1)

            # Replacing a flagged occurrence with identical letters is still an edit.
            delayed = False
            scenario = "lifecycle_valid"
            page.reload()
            original.fill(ORIGINAL)
            page.select_option("#draft-preparation-mode", "conservative", force=True)
            expect(cards).to_have_count(3)
            original.focus()
            original.evaluate("""e => {const start = e.value.lastIndexOf('umber');
              e.setSelectionRange(start, start + 5);} """)
            page.keyboard.insert_text("umber")
            expect(cards).to_have_count(2)
            page.select_option("#draft-preparation-mode", "off", force=True)

            scenario = "valid"
            page.reload()

            count = len(results)
            original.fill(ORIGINAL)
            page.wait_for_timeout(800)
            assert len(results) == count, "Off must not request generation"
            page.select_option("#draft-preparation-mode", "conservative", force=True)
            expect(prepared).to_have_value(PREPARED)
            expect(cards).to_have_count(3)
            expect(marks).to_have_text(["umber", "parcel", "pigment"])
            expect(review).to_have_attribute("data-findings-status", "complete")
            expect(cards.nth(0).locator(".inspection-suggestion")).to_have_text(["amber", "ochre"])
            expect(cards.nth(1).locator(".inspection-suggestion")).to_have_text(["package"])
            expect(cards.nth(2).locator(".inspection-suggestion")).to_have_count(0)
            page.locator("#workspace-resizer").focus()
            page.keyboard.press("Home")
            count = len(results)
            cards.first.locator(".smart-repair-item").focus()
            page.keyboard.press("Enter")
            assert prepared.evaluate("e => [e.selectionStart, e.selectionEnd]") == [20, 25]
            assert (
                prepared.evaluate("e => e.value.slice(e.selectionStart,e.selectionEnd)") == "umber"
            )
            assert original.input_value() == ORIGINAL
            page.locator("#copy-outgoing").click()
            page.wait_for_function("window.syntheticCopies.length === 1")
            assert page.evaluate("window.syntheticCopies[0]") == PREPARED
            cards.last.locator(".inspection-keep").focus()
            page.keyboard.press("Enter")
            expect(cards).to_have_count(2)
            page.wait_for_timeout(800)
            assert len(results) == count, "Inspect/copy/Keep must not generate"
            page.click("#maximize-prepared")
            expect(marks).to_have_count(0)
            page.click("#maximize-prepared")
            expect(marks).to_have_count(2)

            # A complete result replaces old findings, even with identical wording.
            page.select_option("#draft-preparation-mode", "smart", force=True)
            expect(cards).to_have_count(3)
            expect(marks).to_have_count(3)
            assert results[-1]["correction_mode"] == "smart"

            # A captured append preserves occurrences, without live pending highlights.
            original.evaluate(
                "e => {e.focus(); e.setSelectionRange(e.value.length, e.value.length);}"
            )
            page.keyboard.insert_text(" ")
            expect(cards.first.locator(".inspection-location")).to_have_text("Awaiting recheck")
            expect(marks).to_have_count(0)
            edit(ORIGINAL)
            expect(marks).to_have_count(3)
            expect(cards).to_have_count(3)

            # Input-only changes cannot establish which old occurrences survived.
            edit(ORIGINAL + " ")
            expect(cards).to_have_count(0)
            expect(marks).to_have_count(0)
            edit(ORIGINAL)
            expect(cards).to_have_count(3)
            expect(marks).to_have_count(3)

            for width in (1280, 1480):
                page.set_viewport_size({"width": width, "height": 1050})
                for layout in ("side-by-side", "stacked"):
                    page.click(f"#layout-{layout}")
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

            # Normal-route selection/choice/application changes only the second occurrence.
            for mode, scenario_name, option, changed, selection in [
                ("smart", "valid", "ochre", "📝 send umber then ochre parcel pigment", [19, 24]),
                (
                    "conservative",
                    "long_alternative",
                    "ochre 🟠",
                    "📝 send umber then ochre 🟠 parcel pigment",
                    [19, 27],
                ),
            ]:
                scenario = scenario_name
                page.reload()
                original.fill(ORIGINAL)
                page.select_option("#draft-preparation-mode", mode, force=True)
                expect(cards).to_have_count(3)
                expect(cards.locator(".inspection-apply")).to_have_count(0)
                expect(cards.get_by_role("radio", checked=True)).to_have_count(0)
                count = len(results)
                cards.first.locator(".smart-repair-item").click()
                expect(original).to_have_value(ORIGINAL)
                page.wait_for_timeout(800)
                assert len(results) == count, "Inspection must not generate"
                if mode == "smart":
                    cards.first.get_by_role("radio", name="amber", exact=True).focus()
                    page.keyboard.press("ArrowDown")
                else:
                    cards.first.get_by_role("radio", name=option, exact=True).click()
                expect(original).to_have_value(changed)
                expect(prepared).to_have_value(changed)
                expect(cards).to_have_count(1)
                expect(cards.locator(".inspection-keep")).to_have_count(0)
                assert len(results) == count + 1, "Apply must use one normal preparation"
                applied = cards.filter(has_text="Applied in Original.")
                expect(applied).to_have_count(1)
                applied.locator(".smart-repair-item").click()
                assert original.evaluate("e => [e.selectionStart,e.selectionEnd]") == selection
                assert (
                    original.evaluate("e => e.value.slice(e.selectionStart,e.selectionEnd)")
                    == option
                )
                page.click("#copy-outgoing")
                page.wait_for_function("window.syntheticCopies.length === 1")
                assert page.evaluate("window.syntheticCopies[0]") == changed
                page.wait_for_timeout(800)
                assert len(results) == count + 1, "Inspect/copy must not generate"
                published = [
                    body
                    for path, method, body in requests
                    if path == "outgoing-state" and method == "PUT"
                ]
                assert published[-1]["outgoing_text"] == changed
                edit(changed)
                expect(review).to_have_attribute("data-findings-status", "complete")
                expect(cards).to_have_count(1)
                applied.locator(".smart-repair-item").click()
                assert (
                    original.evaluate("e => e.value.slice(e.selectionStart,e.selectionEnd)")
                    == option
                )
                # Keep the same chosen word elsewhere: do not search to revive its location.
                edit(changed + " edited")
                expect(applied.locator(".inspection-location")).to_have_text("Location unavailable")
                edit(changed)
                expect(applied.locator(".inspection-location")).to_have_text("Location unavailable")
                expect(cards.get_by_role("radio")).to_have_count(0)

            # Already-applied Smart repairs are retained too; their stale locations are not guessed.
            scenario = "smart_repair"
            page.reload()
            original.fill(ORIGINAL)
            page.select_option("#draft-preparation-mode", "smart", force=True)
            expect(cards).to_have_count(4)
            generated = cards.filter(has_text="Applied in Prepared.")
            generated.locator(".smart-repair-item").click()
            assert (
                prepared.evaluate("e => e.value.slice(e.selectionStart,e.selectionEnd)") == "amber"
            )
            cards.nth(1).get_by_role("radio", name="ochre", exact=True).click()
            expect(prepared).to_have_value("📝 send umber then ochre parcel pigment")
            expect(cards).to_have_count(2)
            expect(generated.locator(".inspection-location")).to_have_text("Location unavailable")
            expect(cards.filter(has_text="Applied in Original.")).to_have_count(1)

            # Options from an older generation never become actionable again.
            scenario = "valid"
            page.reload()
            original.fill(ORIGINAL)
            page.select_option("#draft-preparation-mode", "smart", force=True)
            expect(cards).to_have_count(3)
            original.evaluate(
                "e => {e.focus(); e.setSelectionRange(e.value.length, e.value.length);}"
            )
            page.keyboard.insert_text(" ")
            expect(cards).to_have_count(3)
            expect(cards.first.get_by_role("radio", name="ochre", exact=True)).to_be_disabled()
            count = len(results)
            page.select_option("#draft-preparation-mode", "off", force=True)
            expect(prepared).to_have_value("")
            page.wait_for_timeout(800)
            assert len(results) == count
            expect(original).to_have_value(ORIGINAL + " ")
            for radio in cards.get_by_role("radio").all():
                expect(radio).to_be_disabled()

            # A one-option removal still requires a choice, and cannot highlight another word.
            scenario = "removal"
            page.reload()
            original.fill(ORIGINAL)
            page.select_option("#draft-preparation-mode", "conservative", force=True)
            expect(cards).to_have_count(3)
            cards.first.get_by_role("radio").click()
            expect(original).to_have_value("📝 send umber then  parcel pigment")
            expect(prepared).to_have_value("📝 send umber then  parcel pigment")
            applied = cards.filter(has_text="Applied in Original.")
            expect(applied.locator(".inspection-location")).to_have_text("Location unavailable")
            applied.locator(".smart-repair-item").click()
            assert original.evaluate("e => e.selectionStart === e.selectionEnd")
            assert prepared.evaluate("e => e.selectionStart === e.selectionEnd")
            expect(marks).to_have_count(0)

            # Apply uses manual-edit policy even with a protected correction and Off selected.
            scenario = "valid"
            page.reload()
            original.fill(ORIGINAL)
            page.select_option("#draft-preparation-mode", "conservative", force=True)
            expect(cards).to_have_count(3)
            page.click("#correct-prepared")
            page.select_option("#draft-preparation-mode", "off", force=True)
            count = len(results)
            # The modal intentionally makes background controls inert to real clicks.
            # Exercise the same guarded action while the correction remains open.
            cards.first.get_by_role("radio", name="ochre", exact=True).evaluate("e => e.click()")
            expect(original).to_have_value("📝 send umber then ochre parcel pigment")
            expect(page.locator("#confirm-prepared")).to_be_disabled()
            page.wait_for_timeout(800)
            assert len(results) == count, "Open correction/Off must not generate after Apply"
            page.click("#cancel-prepared-correction")

            # Select-all replacement starts a new passage; ordinary edits above retain entries.
            for replacement in ("Next synthetic passage.", ORIGINAL):
                page.reload()
                original.fill(ORIGINAL)
                page.select_option("#draft-preparation-mode", "smart", force=True)
                expect(cards).to_have_count(3)
                count = len(results)
                original.focus()
                page.keyboard.press("ControlOrMeta+A")
                page.keyboard.insert_text(replacement)
                expect(original).to_have_value(replacement)
                expect(cards).to_have_count(0)
                expect(marks).to_have_count(0)
                expect(review).to_be_hidden()
                page.wait_for_timeout(800)
                assert len(results) == count, "New passage restores the existing Off default"

            # Fresh browser state for complete-zero, partial-zero and unavailable.
            for scenario_name, expected_status, summary in [
                ("empty", "complete", "No findings or repairs"),
                ("all_invalid", "partial", "Findings incomplete"),
                ("unavailable", "unavailable", "Findings unavailable"),
            ]:
                scenario = scenario_name
                page.click("#clear-text")
                page.reload()
                original.fill(ORIGINAL)
                page.select_option("#draft-preparation-mode", "conservative", force=True)
                expect(prepared).to_have_value(PREPARED)
                expect(cards).to_have_count(0)
                expect(review).to_have_attribute("data-findings-status", expected_status)
                expect(page.locator("#smart-repair-summary")).to_have_text(summary)
                expect(note).to_be_visible()

            scenario = "partial"
            edit(ORIGINAL)
            expect(cards).to_have_count(3)
            expect(review).to_have_attribute("data-findings-status", "partial")
            assert len(results[-1]["attempts"]) == 1
            scenario = "invalid_prepared"
            edit(ORIGINAL)
            expect(prepared).to_have_value(ORIGINAL)
            expect(marks).to_have_count(0)
            expect(cards).to_have_count(3)
            assert results[-1]["status"] == "provider_error"

            # Existing open-correction and current-confirmation protections still apply.
            scenario = "valid"
            page.keyboard.press("ControlOrMeta+Enter")
            expect(prepared).to_have_value(PREPARED)
            expect(page.locator("#retry-cleanup")).to_be_hidden()
            count = len(results)
            page.keyboard.press("ControlOrMeta+Enter")
            expect(page.locator("#retry-cleanup-state")).to_contain_text(
                "only after preparation fails"
            )
            assert len(results) == count
            page.click("#correct-prepared")
            page.fill("#intended-prepared", "Unsaved synthetic correction.")
            page.keyboard.press("ControlOrMeta+Enter")
            expect(page.locator("#prepared-correction-state")).to_contain_text("Retry blocked")
            expect(page.locator("#intended-prepared")).to_have_value(
                "Unsaved synthetic correction."
            )
            expect(page.locator("#prepared-correction-dialog")).to_be_visible()
            # A programmatic button invocation uses the identical guarded action.
            page.locator("#retry-cleanup").evaluate("e => e.click()")
            expect(page.locator("#prepared-correction-state")).to_contain_text("Retry blocked")
            assert len(results) == count
            count = len(results)
            page.select_option("#draft-preparation-mode", "off", force=True)
            page.wait_for_timeout(800)
            assert len(results) == count
            page.fill("#intended-prepared", "Owner-confirmed synthetic wording.")
            page.click("#confirm-prepared")
            expect(prepared).to_have_value("Owner-confirmed synthetic wording.")
            page.keyboard.press("ControlOrMeta+Enter")
            expect(page.locator("#retry-cleanup-state")).to_contain_text("Retry blocked")
            page.locator("#retry-cleanup").evaluate("e => e.click()")
            expect(prepared).to_have_value("Owner-confirmed synthetic wording.")
            assert len(results) == count
            for radio in cards.get_by_role("radio").all():
                expect(radio).to_be_disabled()
            page.select_option("#draft-preparation-mode", "smart", force=True)
            page.wait_for_timeout(800)
            assert len(results) == count

            delayed = True
            edit(ORIGINAL + " Late.")
            page.wait_for_timeout(900)
            assert pending
            edit("Newest synthetic passage.")
            page.select_option("#draft-preparation-mode", "off", force=True)
            retained = cards.count()
            for route, result in pending:
                route.fulfill(json=result)
            page.wait_for_timeout(800)
            expect(prepared).to_have_value("")
            expect(cards).to_have_count(retained)
            expect(marks).to_have_count(0)
            assert original.input_value() == "Newest synthetic passage."
            assert all(path in {"config", "outgoing-state", "cleanup"} for path, _, _ in requests)
            assert not errors, errors
            browser.close()
        print(
            json.dumps(
                {
                    "passed": True,
                    "synthetic_only": True,
                    "http_results": len(results),
                    "browser_errors": errors,
                    "live_provider_requests": 0,
                    "saved_correction_requests": 0,
                    "database_access": 0,
                    "migrations": 0,
                }
            )
        )
    finally:
        worker.stdin.close()
        worker.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots-dir", type=Path)
    parser.add_argument("--http-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.http_worker:
        http_worker()
    else:
        run_checks(args.screenshots_dir)
