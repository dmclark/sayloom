#!/usr/bin/env python3
"""Affected synthetic browser checks for Correct Prepared and optional batch review.

Serves the real app/API with a disposable migrated database. Only generation is
synthetic; candidate derivation and selected-mapping persistence use real code.
Requires an installed Node Playwright module (PLAYWRIGHT_MODULE may name it) and
Chromium (CHROMIUM_EXECUTABLE may name an installed executable). Installs nothing.
Run with --screenshots-dir PATH to retain three targeted button-visibility captures.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from fastapi.testclient import TestClient

from local_text.admin import _alembic_config
from local_text.app import create_app
from local_text.cleanup import PreparationMode
from local_text.config import Profile, Settings
from local_text.database import ApplicationDatabase
from local_text.prompt_store import PromptStore
from local_text.target_store import TargetStore

ROOT = Path(__file__).resolve().parents[2]

CHECKS = r"""
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath:process.env.CHROMIUM_EXECUTABLE} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1280,height:1000}});
    page.setDefaultTimeout(5000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const requests = [];
    page.on('request', req => {
      if (req.url().includes('/api/')) requests.push({path:new URL(req.url()).pathname,
        body:req.postData() ? JSON.parse(req.postData()) : null});
    });
    const original = 'please send the umber parcel on fries day';
    const starting = 'Please send the umber parcel on fries day.';
    const confirmed = 'Please send the amber parcel on Friday.';
    const value = selector => page.locator(selector).inputValue();
    const writes = () => requests.filter(r => r.path.endsWith('/episodes'));
    const candidates = () => requests.filter(r => r.path.endsWith('/candidates'));
    const layoutChecks = [];
    const reviewState = page.locator('#missed-repair-review-state');
    const waitState = state => page.waitForFunction(state =>
      document.querySelector('#missed-repair-review-state').dataset.state === state, state);
    const waitReview = () => page.waitForFunction(() =>
      document.querySelector('#missed-repair-review-state').dataset.state === 'ready');
    async function confirm(text, review) {
      await page.click('#correct-prepared');
      assert.equal(await page.isChecked('#review-personal-corrections'), false);
      await page.fill('#intended-prepared', text);
      if (review) await page.check('#review-personal-corrections');
      await page.click('#confirm-prepared');
      assert.equal(await value('#prepared-text'), text);
      if (review) await waitReview();
    }
    async function reset() {
      if (await page.locator('#missed-repair-dialog').evaluate(e => e.open)) {
        await page.click('#dismiss-missed-repair');
      }
      await page.click('#clear-text');
      await page.selectOption('#draft-preparation-mode', 'off');
      await page.fill('#original-text', original);
      await page.selectOption('#draft-preparation-mode', 'conservative');
      await page.waitForFunction(text =>
        document.querySelector('#prepared-text').value === text
        && !document.querySelector('#correct-prepared').hidden, starting);
    }
    async function layout(dialog) {
      const bounds = await page.locator(dialog).evaluate(e => {
        const r=e.getBoundingClientRect();
        return {left:r.left,right:r.right,width:innerWidth,overflow:e.scrollWidth>e.clientWidth,
          pageOverflow:document.documentElement.scrollWidth>innerWidth};
      });
      assert(bounds.left >= 0 && bounds.right <= bounds.width);
      assert(!bounds.overflow && !bounds.pageOverflow);
      const scrollTop = await page.locator(dialog).evaluate(e=>e.scrollTop);
      const actions = page.locator(`${dialog} .missed-repair-actions`);
      await actions.scrollIntoViewIfNeeded();
      const reachable = await actions.evaluate(e => {
        const r=e.getBoundingClientRect(), d=e.closest('dialog').getBoundingClientRect();
        return r.top>=d.top && r.bottom<=d.bottom && r.bottom<=innerHeight;
      });
      assert(reachable, 'dialog actions must be fully reachable by scrolling');
      layoutChecks.push({dialog,width:bounds.width,actionsReachable:reachable});
      await page.locator(dialog).evaluate((e,top)=>{e.scrollTop=top;},scrollTop);
    }
    async function captureAvailability(name) {
      if (process.argv[2]) {
        fs.mkdirSync(process.argv[2], {recursive:true});
        await page.locator('.prepared-panel .panel-footer')
          .screenshot({path:path.join(process.argv[2],name)});
      }
    }
    await page.goto(process.argv[1]);
    await page.waitForFunction(() =>
      document.querySelector('#mode-save-state').textContent.includes('saved default'));
    assert.equal(await page.locator('#open-missed-repair').count(),0);

    // Original alone must not expose Correct Prepared, including at mobile width.
    assert(await page.locator('#correct-prepared').isHidden());
    await page.fill('#original-text', original);
    assert(await page.locator('#correct-prepared').isHidden());
    assert(await page.isDisabled('#correct-prepared'));
    await page.dispatchEvent('#correct-prepared', 'click');
    assert.equal(await page.locator('#prepared-correction-dialog').evaluate(e=>e.open),false);
    await captureAvailability('correct-prepared-unavailable-desktop.png');
    await page.setViewportSize({width:390,height:844});
    assert(await page.locator('#correct-prepared').isHidden());
    await captureAvailability('correct-prepared-unavailable-390px.png');
    await page.setViewportSize({width:1280,height:1000});

    // A delayed cleanup keeps entry hidden; its successful result makes it available.
    let releaseCleanup;
    const cleanupGate = new Promise(resolve => { releaseCleanup = resolve; });
    await page.route('**/api/cleanup', async route => {
      await cleanupGate;
      await route.continue();
    });
    await page.selectOption('#draft-preparation-mode','conservative');
    await page.waitForFunction(() =>
      document.querySelector('#outgoing-kind').dataset.state === 'cleaning');
    assert(await page.locator('#correct-prepared').isHidden());
    await page.dispatchEvent('#correct-prepared', 'click');
    assert.equal(await page.locator('#prepared-correction-dialog').evaluate(e=>e.open),false);
    releaseCleanup();
    await page.waitForFunction(text =>
      document.querySelector('#prepared-text').value === text
      && !document.querySelector('#correct-prepared').hidden, starting);
    await page.unroute('**/api/cleanup');
    assert(await page.locator('#correct-prepared').isEnabled());
    await captureAvailability('correct-prepared-available-desktop.png');
    await page.setViewportSize({width:390,height:844});
    assert(await page.locator('#correct-prepared').isVisible());
    await page.setViewportSize({width:1280,height:1000});
    await page.click('#correct-prepared');
    assert.equal(await value('#intended-prepared'),starting);
    assert.equal(await page.isChecked('#review-personal-corrections'),false);
    await layout('#prepared-correction-dialog');
    await page.setViewportSize({width:390,height:844});
    await layout('#prepared-correction-dialog');
    await page.setViewportSize({width:1280,height:1000});
    await page.fill('#intended-prepared',confirmed);
    await page.check('#review-personal-corrections');
    await page.click('#confirm-prepared');
    await waitReview();
    assert.equal(await value('#original-text'),original);
    assert.equal(await value('#prepared-text'),confirmed);
    assert.deepEqual(candidates().at(-1).body, {before_text:starting,after_text:confirmed,
      source_mode:'user_confirmed',prompt_version_id:null,correction_contract_version:'personal-correction-v1'});
    const selections = page.locator('.missed-repair-candidate > input');
    assert.equal(await selections.count(),2);
    assert.deepEqual(await selections.evaluateAll(es => es.map(e=>e.checked)),[false,false]);
    assert(await page.isDisabled('#missed-repair-approval'));
    await layout('#missed-repair-dialog');
    await page.setViewportSize({width:390,height:844});
    await selections.nth(1).check();
    await layout('#missed-repair-dialog');
    await page.click('#missed-repair-approval');
    await waitState('error');
    assert.equal(await value('#prepared-text'),confirmed);
    assert(await selections.nth(1).isDisabled());
    await page.click('#missed-repair-approval');
    await waitState('saved');
    assert.deepEqual(writes()[0].body,writes()[1].body);
    assert.deepEqual(writes()[1].body.mappings,
      [{operation:'replacement',observed_text:'fries day',intended_text:'Friday'}]);
    assert.equal(await page.locator('#missed-repair-saved-mappings').innerText(),
      'fries day → Friday');
    assert.equal(await value('#prepared-text'),confirmed);
    await page.setViewportSize({width:1280,height:1000});

    // Settings changes during manual editing stay protected, even when switched Off.
    await reset();
    const generationCount = requests.filter(r=>r.path==='/api/cleanup').length;
    await page.click('#correct-prepared');
    await page.evaluate(() => {
      const e=document.querySelector('#draft-preparation-mode'); e.value='off';
      e.dispatchEvent(new Event('change',{bubbles:true}));
    });
    await page.keyboard.press('Escape');
    assert(await page.locator('#correct-prepared').isVisible());
    await confirm(confirmed,true);
    await page.locator('.missed-repair-mapping-field input').nth(1).fill('Amber');
    await selections.nth(0).check(); await selections.nth(1).check();
    await page.click('#missed-repair-approval');
    await waitState('saved');
    assert.equal(writes().at(-1).body.mappings.length,2);
    assert.equal(writes().at(-1).body.mappings[0].intended_text,'Amber');
    assert.equal(await value('#prepared-text'),confirmed);
    assert.equal(requests.filter(r=>r.path==='/api/cleanup').length,generationCount);

    // None selected/dismissal and unchecked review save nothing, exact text preserved.
    await reset(); await confirm(confirmed,true);
    const writeCount = writes().length;
    await page.click('#dismiss-missed-repair');
    assert.equal(writes().length,writeCount);
    assert.equal(await value('#prepared-text'),confirmed);
    const candidateCount = candidates().length;
    const exact = '  Please send the amber parcel on frriday.\n\nThanks!  ';
    await confirm(exact,false);
    assert.equal(candidates().length,candidateCount);
    assert.equal(writes().length,writeCount);
    await page.waitForFunction(async text => {
      const state = await (await fetch('/api/outgoing-state')).json();
      return state.outgoing_kind === 'prepared' && state.outgoing_text === text;
    }, exact, {polling:100});
    await page.click('#correct-prepared');
    assert.equal(await value('#intended-prepared'),exact);
    await page.fill('#intended-prepared','   ');
    assert(await page.isDisabled('#confirm-prepared'));
    await page.keyboard.press('Escape');
    assert.equal(await value('#prepared-text'),exact);

    // Only additions/removals: no offered mappings but confirmed wording stays usable.
    await reset(); await confirm('Please send the umber parcel on fries day now.',true);
    assert.equal(await selections.count(),0);
    assert(await page.isDisabled('#missed-repair-approval'));
    assert((await reviewState.innerText()).includes('Additions and removals'));
    await page.click('#dismiss-missed-repair');
    assert.equal(await value('#prepared-text'),'Please send the umber parcel on fries day now.');

    // Stale review, including identical Original input as a non-invalidation control.
    await reset(); await confirm(confirmed,true);
    await page.evaluate(() => document.querySelector('#original-text')
      .dispatchEvent(new Event('input',{bubbles:true})));
    assert.equal(await reviewState.getAttribute('data-state'),'ready');
    await page.evaluate(() => {
      const e=document.querySelector('#original-text'); e.value+=' Changed.';
      e.dispatchEvent(new Event('input',{bubbles:true}));
    });
    assert.equal(await reviewState.getAttribute('data-state'),'stale');
    assert(await page.isDisabled('#missed-repair-approval'));
    assert(await page.locator('#correct-prepared').isHidden());
    assert.equal(writes().length,writeCount);

    // Failure fallbacks may contain Original text, but they are not current Prepared.
    await page.click('#dismiss-missed-repair');
    for (const status of ['timeout','provider_error','unchanged']) {
      await page.route('**/api/cleanup', route => route.fulfill({json:{
        prepared_text:original,status,lexical_repairs:[],attempts:[]}}));
      await page.click('#run-cleanup');
      await page.waitForFunction(expected =>
        document.querySelector('#outgoing-kind').dataset.state === expected,
        status === 'provider_error' ? 'error' : status);
      assert.equal(await page.locator('#correct-prepared').isVisible(),status === 'unchanged');
      await page.unroute('**/api/cleanup');
    }
    await page.selectOption('#draft-preparation-mode','off');
    assert(await page.locator('#correct-prepared').isHidden());
    await page.click('#clear-text');
    assert(await page.locator('#correct-prepared').isHidden());
    assert.deepEqual(errors,[]);
    const unauthorized = requests.filter(r=>r.path.includes('deliver')
      || r.path.includes('copy') || r.path.includes('capture'));
    assert.deepEqual(unauthorized,[]);
    console.log(JSON.stringify({passed:true,browserErrors:errors,layoutChecks,
      saveAttempts:writes().length,
      checks:['Prepared formatting seed','frozen-start derivation','exact Outgoing',
        'optional unchecked review',
        'two unchecked proposals','save some/all/none','editable mappings','response-loss retry',
        'Off during protected editing without generation','unsupported addition retained',
        'stale Original protection','hidden for empty/Off/busy/stale/failed Prepared',
        'visible for generated/unchanged/user-confirmed Prepared',
        'whitespace rejection','Escape cancellation','desktop/390px fit',
        'no delivery or research calls']}));
  } finally { await browser.close(); }
})().catch(e=>{console.error(e.stack);process.exit(1);});
"""


def run_checks(screenshots_dir: Path | None) -> None:
    with TemporaryDirectory(prefix="local-text-correction-check-") as temporary:
        database = ApplicationDatabase(Path(temporary) / "synthetic.sqlite3")
        command.upgrade(_alembic_config(database.url), "head")
        prompts = PromptStore(database)
        prompts.seed_default()
        prompts.set_preparation_default(PreparationMode.OFF)
        TargetStore(database).seed_defaults()
        client = TestClient(create_app(Settings(Profile.DEVELOPMENT, database_path=database.path)))
        lose_first_save_response = True

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: object) -> None:
                pass

            def handle_request(self) -> None:
                nonlocal lose_first_save_response
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                if self.path == "/api/cleanup":
                    request = json.loads(body)
                    original = request["original_text"]
                    result = {
                        "prepared_text": original[0].upper() + original[1:] + ".",
                        "status": "prepared",
                        "provider": "synthetic",
                        "model": "synthetic",
                        "correction_mode": request["correction_mode"],
                        "lexical_repairs": [],
                        "attempts": [],
                    }
                    payload, status, content_type = (
                        json.dumps(result).encode(),
                        200,
                        "application/json",
                    )
                else:
                    response = client.request(
                        self.command,
                        self.path,
                        content=body,
                        headers={"Content-Type": "application/json"} if body else {},
                    )
                    payload, status = response.content, response.status_code
                    content_type = response.headers.get("content-type", "application/json")
                    if (
                        self.path == "/api/personal-corrections/episodes"
                        and lose_first_save_response
                    ):
                        assert status == 201
                        lose_first_save_response = False
                        payload = json.dumps({"detail": "Synthetic lost acknowledgement"}).encode()
                        status = 503
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = do_DELETE = do_PUT = handle_request

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            result = subprocess.run(
                [
                    "node",
                    "-e",
                    CHECKS,
                    f"http://127.0.0.1:{server.server_port}",
                    str(screenshots_dir.resolve()) if screenshots_dir else "",
                ],
                cwd=ROOT,
                env=os.environ,
                capture_output=True,
                text=True,
                timeout=90,
            )
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
            with sqlite3.connect(database.path) as connection:
                assert connection.execute(
                    "SELECT COUNT(*) FROM personal_correction_episodes"
                ).fetchone() == (2,)
                assert connection.execute(
                    "SELECT COUNT(*) FROM personal_correction_episode_mappings"
                ).fetchone() == (3,)
                assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
            print(result.stdout.strip())
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
            client.close()
            database.engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screenshots-dir", type=Path)
    arguments = parser.parse_args()
    run_checks(arguments.screenshots_dir)


if __name__ == "__main__":
    main()
