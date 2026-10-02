import json
import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from local_text.app import create_app
from local_text.config import Settings


def candidate_request(before: str, after: str, prompt_version_id: int) -> dict[str, object]:
    return {
        "before_text": before,
        "after_text": after,
        "source_mode": "conservative",
        "prompt_version_id": prompt_version_id,
        "correction_contract_version": "personal-correction-v1",
    }


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (
            "Carry amber parcel",
            "Carry one amber parcel",
            ("addition", "", "one", 6, 6, 6, 9),
        ),
        (
            "Carry spare amber parcel",
            "Carry amber parcel",
            ("removal", "spare", "", 6, 11, 6, 6),
        ),
        (
            "Carry umber parcel",
            "Carry amber parcel",
            ("replacement", "umber", "amber", 6, 11, 6, 11),
        ),
        (
            "Um send report",
            "send report",
            ("removal", "Um", "", 0, 2, 0, 0),
        ),
        (
            "send report",
            "Um send report",
            ("addition", "", "Um", 0, 0, 0, 2),
        ),
    ],
)
def test_candidate_endpoint_reuses_ordered_lexical_review_contract(
    initialized_settings: Settings,
    before: str,
    after: str,
    expected: tuple[object, ...],
) -> None:
    client = TestClient(create_app(initialized_settings))
    prompt_id = client.get("/api/config").json()["active_prompt_version_id"]

    response = client.post(
        "/api/personal-corrections/candidates",
        json=candidate_request(before, after, prompt_id),
    )

    assert response.status_code == 200
    candidate = response.json()["candidates"][0]
    assert (
        candidate["operation"],
        candidate["original_span"]["text"],
        candidate["prepared_span"]["text"],
        candidate["original_span"]["start"],
        candidate["original_span"]["end"],
        candidate["prepared_span"]["start"],
        candidate["prepared_span"]["end"],
    ) == expected
    assert candidate["queue_position"] == 1


def test_candidate_sentences_exclude_neighbors_without_truncating(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    prompt_id = client.get("/api/config").json()["active_prompt_version_id"]
    long_word = "𐐀" * 501
    before = f"Neighbor before. Keep {long_word} teh. Neighbor after!"
    after = f"Neighbor before. Keep {long_word} the. Neighbor after!"

    response = client.post(
        "/api/personal-corrections/candidates",
        json=candidate_request(before, after, prompt_id),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["observed_sentence"] == f"Keep {long_word} teh."
    assert result["intended_sentence"] == f"Keep {long_word} the."
    assert "Neighbor" not in result["observed_sentence"]
    assert len(result["observed_sentence"]) > 500


@pytest.mark.parametrize(
    ("before", "after", "expected_observed", "expected_intended"),
    [
        ("First. Remove me. Last.", "First. Last.", "Remove me.", ""),
        ("First. Last.", "First. Add me. Last.", "", "Add me."),
    ],
)
def test_candidate_whole_sentence_changes_do_not_prefill_neighbor(
    initialized_settings: Settings,
    before: str,
    after: str,
    expected_observed: str,
    expected_intended: str,
) -> None:
    client = TestClient(create_app(initialized_settings))
    prompt_id = client.get("/api/config").json()["active_prompt_version_id"]

    response = client.post(
        "/api/personal-corrections/candidates",
        json=candidate_request(before, after, prompt_id),
    )

    assert response.status_code == 200
    assert response.json()["observed_sentence"] == expected_observed
    assert response.json()["intended_sentence"] == expected_intended
    assert "Last." not in {
        response.json()["observed_sentence"],
        response.json()["intended_sentence"],
    }


def test_candidate_rejects_result_when_active_prompt_changed(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    original_prompt_id = client.get("/api/config").json()["active_prompt_version_id"]
    changed_prompt = client.post(
        "/api/prompts",
        json={
            "title": "Changed prompt",
            "system_text": "Changed synthetic instruction.",
            "activate": True,
        },
    ).json()

    response = client.post(
        "/api/personal-corrections/candidates",
        json=candidate_request("Send teh report", "Send the report", original_prompt_id),
    )

    assert changed_prompt["id"] != original_prompt_id
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stale_personal_correction_result"


def test_candidate_failure_is_private_and_candidate_review_writes_nothing(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    database_path = Path(initialized_settings.resolved_database_path)
    with sqlite3.connect(database_path) as connection:
        before = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "personal_correction_profiles",
                "personal_correction_entries",
                "personal_correction_aliases",
            )
        }

    failed = client.post(
        "/api/personal-corrections/candidates",
        json=candidate_request("Private teh text", "Private the text", 999_999),
    )

    assert failed.status_code == 409
    assert "Private" not in failed.text
    with sqlite3.connect(database_path) as connection:
        after = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
    assert after == before


def test_browser_capture_contract_covers_binding_limits_staleness_and_no_save(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    page = client.get("/").text
    script = client.get("/static/app.js").text

    assert 'id="original-text"' in page
    assert 'id="prepared-text"' in page and "readonly" in page
    assert 'id="open-missed-repair"' in page
    assert 'id="missed-repair-dialog"' in page
    assert 'id="retain-observed-sentence"' in page
    assert 'id="retain-intended-sentence"' in page
    assert 'id="missed-repair-context"' in page
    assert 'id="missed-repair-approval"' in page and "disabled" in page
    assert 'selected.checked = false' in script
    assert 'Array.from(field.value).length' in script
    assert 'length > 500' in script
    assert 'binding.preEdit' in script and 'binding.postEdit' in script
    assert 'binding.postRevision !== draftRevision' in script
    assert 'invocation !== "automatic"' in script
    assert 'missedRepairBinding.state = "available"' in script
    assert 'missedRepairBinding = null;' in script
    assert 'fetch("/api/personal-corrections/candidates"' in script
    assert '/api/personal-corrections/episodes' not in script

    stale_reasons = (
        "Original changed again",
        "correction mode changed",
        "task context changed",
        "cleanup was run again",
        "draft was cleared",
        "Original was replaced",
        "different result replaced it",
    )
    for reason in stale_reasons:
        assert reason in script


def test_browser_binds_multikeystroke_edit_allows_exact_regeneration_and_fails_open(
    initialized_settings: Settings,
) -> None:
    script = TestClient(create_app(initialized_settings)).get("/static/app.js").text
    harness = r"""
const vm = require("vm");
class Element {
  constructor() {
    this.value = ""; this.checked = true; this.disabled = false; this.hidden = false;
    this.open = false; this.dataset = {}; this.options = [{ textContent: "" }];
    this.children = []; this.listeners = {}; this.textContent = ""; this.attributes = {};
    this.style = { setProperty() {} };
    this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
    this.lastElementChild = { textContent: "" }; this.selectionStart = 0; this.selectionEnd = 0;
  }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  async dispatch(type, event = {}) {
    event.target ||= this; event.preventDefault ||= () => {};
    for (const callback of this.listeners[type] || []) await callback(event);
  }
  append(...children) { this.children.push(...children); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || (name === "aria-valuenow" ? "55" : null); }
  removeAttribute(name) { delete this.attributes[name]; }
  toggleAttribute() {}
  setPointerCapture() {}
  setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; }
  getBoundingClientRect() { return { top: 0, left: 0, height: 100, width: 100 }; }
  focus() { document.activeElement = this; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  querySelector() { return new Element(); }
  reportValidity() { return true; }
  reset() {}
}
const elements = {};
const document = {
  activeElement: null,
  querySelector(selector) { return elements[selector] ||= new Element(); },
  createElement() { return new Element(); },
  addEventListener() {},
};
const requests = [];
const timers = [];
let candidateFailure = false;
let candidateStale = false;
const response = (body, ok = true, status = 200) => ({ ok, status, json: async () => body });
const fetch = async (url, options = {}) => {
  const body = options.body ? JSON.parse(options.body) : null;
  requests.push({ url, method: options.method || "GET", body });
  if (url === "/api/config") return response({
    preparation_default: "conservative", active_prompt_version_id: 7,
    cleanup_configuration: { status: "unavailable", routes: [], disclosure: {} },
  });
  if (url === "/api/outgoing-state") return response({ revision: requests.length });
  if (url === "/api/cleanup") return response({
    prepared_text: body.original_text, status: "unchanged", provider: "test", model: "test",
    correction_mode: body.correction_mode, lexical_repairs: [], attempts: [],
  });
  if (url === "/api/personal-corrections/candidates") {
    if (candidateStale) return response({ detail: {
      code: "stale_personal_correction_result", message: "The result is stale.",
      retry_action: "Run correction again.",
    } }, false, 409);
    if (candidateFailure) return response({ detail: {
      code: "candidate_failure", message: "Candidate generation failed.", retry_action: "Retry.",
    } }, false, 503);
    const beforeReplacement = body.before_text.indexOf("umber");
    const afterReplacement = body.after_text.indexOf("amber");
    const beforeAddition = body.before_text.indexOf(". After");
    const afterAddition = body.after_text.indexOf("now");
    return response({
      candidates: [
        { operation: "replacement",
          original_span: { start: beforeReplacement, end: beforeReplacement + 5, text: "umber" },
          prepared_span: { start: afterReplacement, end: afterReplacement + 5, text: "amber" },
          context: "Carry amber parcel now.", queue_position: 1,
          inspection_reason: "Prepared replaces wording; verify meaning." },
        { operation: "addition",
          original_span: { start: beforeAddition, end: beforeAddition, text: "" },
          prepared_span: { start: afterAddition, end: afterAddition + 3, text: "now" },
          context: "Carry amber parcel now.", queue_position: 2,
          inspection_reason: "Prepared adds wording; verify meaning." },
      ],
      observed_sentence: "x".repeat(501), intended_sentence: "Carry amber parcel now.",
      applicability_context: null,
    });
  }
  throw new Error(`Unexpected request: ${url}`);
};
const window = {
  clearTimeout() {},
  setTimeout(callback, delay) { timers.push({ callback, delay }); return timers.length; },
  requestAnimationFrame(callback) { callback(); },
  addEventListener() {}, confirm() { return true; },
};
const navigator = { clipboard: { async writeText() {} } };
const context = { document, window, navigator, fetch, AbortController, Promise, console };
async function settle() { await new Promise((resolve) => setImmediate(resolve)); }
async function runCleanupTimer() {
  const timer = timers.filter((item) => item.delay === 700).at(-1);
  await timer.callback(); await settle();
}
(async () => {
  vm.runInNewContext(process.argv[1], context); await settle(); await settle();
  const original = elements["#original-text"];
  original.value = "Before. Carry umber parcel. After.";
  await elements["#run-cleanup"].dispatch("click"); await settle();
  original.value = "Before. Carry amber parcel. After.";
  await original.dispatch("input", { isTrusted: true });
  original.value = "Before. Carry amber parcel now. After.";
  await original.dispatch("input", { isTrusted: true });
  const actionVisibleDuringEdit = !elements["#open-missed-repair"].hidden;
  await runCleanupTimer();
  const actionVisibleAfterRegeneration = !elements["#open-missed-repair"].hidden;
  await elements["#open-missed-repair"].dispatch("click"); await settle();
  const candidateRequest = requests.filter((item) => item.url.endsWith("/candidates")).at(-1).body;
  const overLimit = elements["#missed-repair-review-state"].dataset.state;
  elements["#retain-observed-sentence"].checked = false;
  await elements["#retain-observed-sentence"].dispatch("change");
  const afterRemoval = elements["#missed-repair-review-state"].dataset.state;
  const selectedByDefault = elements["#missed-repair-candidate-list"].children
    .map((item) => item.children[0].checked);
  await elements["#select-original"].dispatch("click");
  await elements["#copy-outgoing"].dispatch("click");
  original.value += " More.";
  await original.dispatch("input", { isTrusted: true });
  const stale = elements["#missed-repair-review-state"].dataset.state;

  await elements["#dismiss-missed-repair"].dispatch("click");
  original.value = "Before. Carry umber parcel. After.";
  await elements["#run-cleanup"].dispatch("click"); await settle();
  original.value = "Before. Carry amber parcel now. After.";
  await original.dispatch("input", { isTrusted: true });
  candidateFailure = true;
  await elements["#open-missed-repair"].dispatch("click"); await settle();
  const failureState = elements["#missed-repair-review-state"].dataset.state;
  const originalAfterFailure = original.value;
  await elements["#run-cleanup"].dispatch("click"); await settle();
  candidateFailure = false;
  candidateStale = true;
  original.value = "Before. Carry amber parcel later. After.";
  await original.dispatch("input", { isTrusted: true });
  await elements["#open-missed-repair"].dispatch("click"); await settle();
  const promptChangeState = elements["#missed-repair-review-state"].dataset.state;
  const personalWrites = requests.filter((item) =>
    item.url.startsWith("/api/personal-corrections/")
    && item.url !== "/api/personal-corrections/candidates");
  process.stdout.write(JSON.stringify({
    actionVisibleDuringEdit, actionVisibleAfterRegeneration, candidateRequest,
    overLimit, afterRemoval, selectedByDefault, stale, failureState, originalAfterFailure,
    promptChangeState,
    cleanupPromptVersionIds: requests
      .filter((item) => item.url === "/api/cleanup")
      .map((item) => item.body.prompt_version_id),
    personalWrites: personalWrites.length,
  }));
})().catch((error) => { process.stderr.write(error.stack); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", harness, script], check=True, capture_output=True, text=True
    )
    observed = json.loads(result.stdout)

    assert observed == {
        "actionVisibleDuringEdit": True,
        "actionVisibleAfterRegeneration": True,
        "candidateRequest": {
            "before_text": "Before. Carry umber parcel. After.",
            "after_text": "Before. Carry amber parcel now. After.",
            "source_mode": "conservative",
            "prompt_version_id": 7,
            "correction_contract_version": "personal-correction-v1",
        },
        "overLimit": "error",
        "afterRemoval": "ready",
        "selectedByDefault": [False, False],
        "stale": "stale",
        "failureState": "error",
        "originalAfterFailure": "Before. Carry amber parcel now. After.",
        "promptChangeState": "stale",
        "cleanupPromptVersionIds": [7, 7, 7, 7],
        "personalWrites": 0,
    }
