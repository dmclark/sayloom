import sqlite3
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from local_text.app import STATIC_VERSION, create_app
from local_text.cleanup import CleanupService
from local_text.config import Profile, Settings


def test_health_reports_development_profile(initialized_settings: Settings) -> None:
    client = TestClient(create_app(initialized_settings))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "profile": "development",
        "development_state": None,
        "database": {
            "state": "current",
            "current_revision": "0001_gate2_prompt_core",
            "expected_revision": "0001_gate2_prompt_core",
        },
        "configuration_error": None,
    }


def test_health_reports_missing_schema_without_creating_database(tmp_path: Path) -> None:
    database_path = tmp_path / "missing.sqlite3"
    client = TestClient(
        create_app(Settings(Profile.DEVELOPMENT, database_path=database_path))
    )

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "setup_required"
    assert response.json()["database"]["state"] == "missing"
    assert not database_path.exists()


def test_health_reports_schema_mismatch(tmp_path: Path) -> None:
    database_path = tmp_path / "mismatch.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('obsolete_revision')")
    client = TestClient(
        create_app(Settings(Profile.DEVELOPMENT, database_path=database_path))
    )

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["database"] == {
        "state": "mismatch",
        "current_revision": "obsolete_revision",
        "expected_revision": "0001_gate2_prompt_core",
    }


def test_default_cleanup_timeout_allows_provider_generation_latency() -> None:
    assert Settings(Profile.DEVELOPMENT).cleanup_timeout_seconds == 30


def test_development_page_identifies_development_brand(initialized_settings: Settings) -> None:
    client = TestClient(create_app(initialized_settings))

    response = client.get("/")

    assert response.status_code == 200
    assert "<title>Sayloom Development</title>" in response.text
    assert 'aria-label="Development profile"' in response.text
    assert 'id="original-text"' in response.text
    assert 'id="cleaned-text"' in response.text
    assert f'href="/static/app.css?v={STATIC_VERSION}"' in response.text
    assert f'src="/static/app.js?v={STATIC_VERSION}"' in response.text
    assert 'id="cleanup-status"' in response.text
    assert 'class="status-label"' not in response.text
    assert 'id="cancel-cleanup"' not in response.text
    assert 'id="active-prompt-selector"' in response.text
    assert 'id="prompt-manager"' not in response.text
    assert 'id="save-prompt"' not in response.text
    assert 'id="workspace-resizer"' in response.text
    assert 'id="select-cleaned"' in response.text
    assert 'id="select-original"' in response.text
    assert 'id="toggle-original"' in response.text
    assert "Type, paste, or dictate here" in response.text
    assert 'aria-keyshortcuts="Meta+Enter Control+Enter"' in response.text
    assert 'title="Run cleanup (⌘↵)"' in response.text
    assert 'class="page-footer"' not in response.text
    assert "keeps the raw text sendable" not in response.text
    control_rail = response.text.split('class="control-rail"', maxsplit=1)[1].split(
        "</section>", maxsplit=1
    )[0]
    assert 'id="toggle-original"' in control_rail
    original_panel = response.text.split('class="text-panel original-panel"', maxsplit=1)[
        1
    ].split("</article>", maxsplit=1)[0]
    assert 'id="toggle-original"' not in original_panel
    assert 'class="panel-footer original-panel-footer"' in original_panel
    assert 'id="run-cleanup"' in original_panel
    assert 'id="clear-text"' in original_panel
    cleaned_panel = response.text.split('class="text-panel cleaned-panel"', maxsplit=1)[
        1
    ].split("</article>", maxsplit=1)[0]
    assert "readonly" in cleaned_panel
    assert response.text.index('class="outgoing-strip"') < response.text.index(
        'id="cleanup-status"'
    )


def test_status_errors_use_one_accessible_privacy_safe_dialog(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    page = client.get("/").text
    script = client.get("/static/app.js").text
    stylesheet = client.get("/static/app.css").text

    assert '<button id="cleanup-status"' in page
    assert '<button id="publication-state"' in page
    assert page.count('<dialog id="error-details-dialog"') == 1
    assert page.count('aria-controls="error-details-dialog"') == 2
    assert 'id="cleanup-error"' not in page
    assert 'id="publication-error"' not in page
    assert "Copy details" in page
    assert 'elements.status.addEventListener("click"' in script
    assert 'elements.publication.addEventListener("click"' in script
    assert "elements.errorDialog.showModal()" in script
    assert "navigator.clipboard.writeText" in script

    error_fields = script.split("function errorFields", maxsplit=1)[1].split(
        "function errorTrigger", maxsplit=1
    )[0]
    assert all(
        label in error_fields
        for label in (
            "Operation",
            "Local time",
            "Model",
            "HTTP status",
            "Code",
            "Sanitized message",
            "Recovery action",
        )
    )
    assert all(
        forbidden not in error_fields
        for forbidden in ("rawText", "cleanedText", "headers", "stack", "payload", "path")
    )
    assert "text-align: left" in stylesheet
    assert ".outgoing-summary { flex: 0 1 auto" in stylesheet


def test_development_page_identifies_selected_state(initialized_settings: Settings) -> None:
    settings = Settings(
        Profile.DEVELOPMENT,
        development_state_name="workflow-parity-regroup",
        database_path=initialized_settings.database_path,
    )
    client = TestClient(create_app(settings))

    page = client.get("/").text

    assert client.app.title == "Sayloom Development — workflow-parity-regroup"
    assert "<title>Sayloom Development — workflow-parity-regroup</title>" in page
    assert ">DEV · workflow-parity-regroup</span>" in page
    assert 'aria-label="Development state workflow-parity-regroup"' in page
    assert client.get("/api/config").json()["development_state"] == "workflow-parity-regroup"
    assert client.get("/health").json()["development_state"] == "workflow-parity-regroup"


def test_release_profile_uses_release_brand(initialized_settings: Settings) -> None:
    client = TestClient(
        create_app(Settings(Profile.RELEASE, database_path=initialized_settings.database_path))
    )

    assert client.app.title == "Sayloom"
    assert client.get("/health").json()["profile"] == "release"
    page = client.get("/").text
    assert "<title>Sayloom</title>" in page
    assert 'aria-label="Development profile"' not in page


def test_config_reports_cleanup_without_exposing_key(initialized_settings: Settings) -> None:
    settings = Settings(
        Profile.DEVELOPMENT,
        gemini_api_key="not-a-real-key",
        database_path=initialized_settings.database_path,
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/config")

    assert response.json() == {
        "display_name": "Sayloom Development",
        "profile": "development",
        "development_state": None,
        "cleanup_enabled_by_default": True,
        "cleanup_available": True,
        "cleanup_model": "gemini-3.5-flash",
    }
    assert "not-a-real-key" not in response.text


def test_cleanup_endpoint_fails_open_when_provider_is_unconfigured(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    response = client.post(
        "/api/cleanup",
        json={"raw_text": "synthetic source text", "enabled": True},
    )

    assert response.status_code == 200
    assert response.json() == {
        "cleaned_text": "synthetic source text",
        "status": "disabled",
        "provider": "gemini",
        "model": "gemini-3.5-flash",
        "error": None,
    }


def test_cleanup_endpoint_returns_provider_result(initialized_settings: Settings) -> None:
    class Provider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, raw_text: str, system_prompt: str) -> str:
            assert raw_text == "synthetic source text"
            assert "untrusted input data" in system_prompt
            return "Synthetic clean text."

    service = CleanupService(provider=Provider(), model="test-model", timeout_seconds=1)
    client = TestClient(create_app(initialized_settings, service))

    response = client.post(
        "/api/cleanup",
        json={"raw_text": "synthetic source text", "enabled": True},
    )

    assert response.status_code == 200
    assert response.json()["cleaned_text"] == "Synthetic clean text."
    assert response.json()["status"] == "cleaned"


def test_prompt_api_creates_history_and_activates_an_exact_version(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    initial = client.get("/api/prompts").json()
    seeded = initial["versions"][0]
    created_response = client.post(
        "/api/prompts",
        json={
            "title": "Synthetic concise cleanup",
            "system_text": "Return concise synthetic text only.",
            "activate": True,
        },
    )

    assert created_response.status_code == 201
    created = created_response.json()
    assert created["version"] == 2
    assert created["active"] is True
    history = client.get("/api/prompts").json()
    assert [prompt["version"] for prompt in history["versions"]] == [2, 1]
    assert history["active_prompt_version_id"] == created["id"]
    assert history["versions"][1]["system_text"] == seeded["system_text"]

    activated = client.post(f"/api/prompts/{seeded['id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["id"] == seeded["id"]
    assert client.get("/api/prompts").json()["active_prompt_version_id"] == seeded["id"]
    assert client.post("/api/prompts/9999/activate").status_code == 404


def test_cleanup_uses_the_durable_active_prompt(initialized_settings: Settings) -> None:
    observed: list[str] = []

    class Provider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, raw_text: str, system_prompt: str) -> str:
            observed.append(system_prompt)
            return raw_text

    service = CleanupService(provider=Provider(), model="test-model", timeout_seconds=1)
    client = TestClient(create_app(initialized_settings, service))
    client.post(
        "/api/prompts",
        json={
            "title": "Synthetic active prompt",
            "system_text": "Use this exact synthetic instruction.",
            "activate": True,
        },
    )

    response = client.post(
        "/api/cleanup",
        json={"raw_text": "synthetic source text", "enabled": True},
    )

    assert response.status_code == 200
    assert observed == ["Use this exact synthetic instruction."]


def test_cleanup_can_use_a_session_prompt_without_changing_the_durable_default(
    initialized_settings: Settings,
) -> None:
    observed: list[str] = []

    class Provider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, raw_text: str, system_prompt: str) -> str:
            observed.append(system_prompt)
            return raw_text

    service = CleanupService(provider=Provider(), model="test-model", timeout_seconds=1)
    client = TestClient(create_app(initialized_settings, service))
    durable_prompt_id = client.get("/api/prompts").json()["active_prompt_version_id"]
    session_prompt = client.post(
        "/api/prompts",
        json={
            "title": "Synthetic session prompt",
            "system_text": "Use this request-scoped synthetic instruction.",
            "activate": False,
        },
    ).json()

    response = client.post(
        "/api/cleanup",
        json={
            "raw_text": "synthetic source text",
            "enabled": True,
            "prompt_version_id": session_prompt["id"],
        },
    )

    assert response.status_code == 200
    assert observed == ["Use this request-scoped synthetic instruction."]
    assert client.get("/api/prompts").json()["active_prompt_version_id"] == durable_prompt_id

    missing = client.post(
        "/api/cleanup",
        json={
            "raw_text": "synthetic source text",
            "enabled": True,
            "prompt_version_id": 9999,
        },
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "prompt_version_not_found"


def test_cleanup_toggle_is_durable_configuration(initialized_settings: Settings) -> None:
    client = TestClient(create_app(initialized_settings))
    update = {
        "cleanup_enabled": False,
        "raw_text": "synthetic raw text",
        "cleaned_text": "synthetic raw text",
        "outgoing_text": "synthetic raw text",
        "outgoing_kind": "raw",
        "status": "disabled",
    }

    assert client.put("/api/outgoing-state", json=update).status_code == 200

    restarted = TestClient(create_app(initialized_settings))
    assert restarted.get("/api/config").json()["cleanup_enabled_by_default"] is False
    assert restarted.get("/api/outgoing-state").json()["cleanup_enabled"] is False


def test_outgoing_state_is_published_and_cleared_in_memory(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    update = {
        "cleanup_enabled": True,
        "raw_text": "synthetic raw text",
        "cleaned_text": "Synthetic clean text.",
        "outgoing_text": "Synthetic clean text.",
        "outgoing_kind": "cleaned",
        "status": "cleaned",
    }

    published = client.put("/api/outgoing-state", json=update)

    assert published.status_code == 200
    assert published.json() == {**update, "revision": 1}
    assert client.get("/api/outgoing-state").json() == {**update, "revision": 1}

    cleared = client.delete("/api/outgoing-state")
    assert cleared.status_code == 200
    assert cleared.json()["outgoing_text"] == ""
    assert cleared.json()["outgoing_kind"] == "empty"
    assert cleared.json()["revision"] == 2


def test_outgoing_state_rejects_text_not_present_in_either_editor(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    response = client.put(
        "/api/outgoing-state",
        json={
            "cleanup_enabled": True,
            "raw_text": "current raw",
            "cleaned_text": "current cleaned",
            "outgoing_text": "stale text",
            "outgoing_kind": "cleaned",
            "status": "cleaned",
        },
    )

    assert response.status_code == 422

    mismatched_source = client.put(
        "/api/outgoing-state",
        json={
            "cleanup_enabled": True,
            "raw_text": "current raw",
            "cleaned_text": "current cleaned",
            "outgoing_text": "current raw",
            "outgoing_kind": "cleaned",
            "status": "cleaned",
        },
    )
    assert mismatched_source.status_code == 422


def test_browser_script_supports_generic_input_and_dictation_compatibility(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    script = client.get("/static/app.js")

    assert script.status_code == 200
    assert "syntheticPastePending" in script.text
    assert "replaceAllPending" in script.text
    assert "followsSyntheticPaste" in script.text
    assert "event.isTrusted" in script.text
    assert 'elements.original.addEventListener("input", handleOriginalInput)' in script.text
    assert 'elements.original.addEventListener("beforeinput"' in script.text
    assert "scheduleCleanup();" in script.text
    assert "AbortController" in script.text
    assert "setSelectionRange" in script.text
    assert "fauxCaret" not in script.text
    assert 'elements.workspaceResizer.addEventListener("pointerdown"' in script.text
    assert "promptManager" not in script.text
    assert 'fetch(`/api/prompts/${prompt.id}/activate`' not in script.text
    assert "prompt_version_id: selectedPromptVersionId" in script.text
    assert "originalOutgoingOverride = true" in script.text
    assert "originalOutgoingOverride = false" in script.text
    assert "Original fallback · replacement Cleaned pending" in script.text
    assert "setCleanupError" in script.text
    assert "setPublicationError" in script.text
    assert 'message: "The browser could not connect to the local API."' in script.text
    assert "cancelCleanup" not in script.text
    assert "setOriginalCollapsed" in script.text
    assert 'elements.cleaned.addEventListener("input"' not in script.text
    run_cleanup = script.text.split("async function runCleanup()", maxsplit=1)[1].split(
        "function scheduleCleanup()", maxsplit=1
    )[0]
    scheduled_cleanup = script.text.split("function scheduleCleanup()", maxsplit=1)[1].split(
        "function originalIsFullySelected", maxsplit=1
    )[0]
    assert 'elements.cleaned.value = "";' not in run_cleanup
    assert 'elements.cleaned.value = "";' not in scheduled_cleanup
    assert '(status === "cleaned" || status === "unchanged")' in script.text
    initialization = script.text.split("async function initialize()", maxsplit=1)[1].split(
        "initialize();", maxsplit=1
    )[0]
    assert "clearPublishedState()" in initialization
    assert 'elements.original.value = "";' not in initialization
    assert 'elements.cleaned.value = "";' in initialization
    assert 'fetch("/api/outgoing-state")' not in initialization
    assert "publishNow();" not in initialization


def test_workspace_initialization_focuses_only_an_empty_original_editor(
    initialized_settings: Settings,
) -> None:
    script = TestClient(create_app(initialized_settings)).get("/static/app.js").text
    harness = r"""
const vm = require("vm");

async function run(originalValue) {
  let focusCalls = 0;
  let resolvePrompts;
  const promptResponse = new Promise((resolve) => { resolvePrompts = resolve; });
  class Element {
    constructor(value = "") {
      this.value = value;
      this.checked = true;
      this.dataset = {};
      this.open = false;
      this.style = { setProperty() {} };
      this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
      this.lastElementChild = new ElementText();
    }
    addEventListener() {}
    setAttribute() {}
    getAttribute() { return "65"; }
    removeAttribute() {}
    append() {}
    setPointerCapture() {}
    setSelectionRange() {}
    close() {}
    focus() { focusCalls += 1; }
  }
  class ElementText { constructor() { this.textContent = ""; } }
  const original = new Element(originalValue);
  const selectors = {
    "#original-text": original,
    "#cleaned-text": new Element(), "#cleanup-enabled": new Element(),
    "#run-cleanup": new Element(), "#clear-text": new Element(),
    "#toggle-original": new Element(), "#cleanup-status": new Element(),
    "#cleanup-status-text": new Element(), "#original-count": new Element(),
    "#cleaned-count": new Element(), "#outgoing-kind": new Element(),
    "#select-cleaned": new Element(), "#select-original": new Element(),
    "#publication-state": new Element(), "#model-label": new Element(),
    ".workspace": new Element(), "#workspace-resizer": new Element(),
    "#active-prompt-selector": new Element(), "#error-details-dialog": new Element(),
    "#error-details-ledger": new Element(), "#close-error-details": new Element(),
    "#copy-error-details": new Element(),
  };
  const querySelector = (selector) => selectors[selector];
  const createElement = () => new Element();
  const document = { querySelector, createElement, addEventListener() {} };
  const clearTimeout = () => {};
  const setTimeout = () => 1;
  const requestAnimationFrame = (callback) => { callback(); };
  const addEventListener = () => {};
  const window = { clearTimeout, setTimeout, requestAnimationFrame, addEventListener };
  const fetch = (url) => {
    if (url === "/api/prompts") return promptResponse;
    const configBody = {
      cleanup_enabled_by_default: true,
      cleanup_available: false,
    };
    const body = url === "/api/config" ? configBody : { revision: 1 };
    return Promise.resolve({ ok: true, status: 200, json: async () => body });
  };
  const context = {
    document, window, fetch, AbortController, Promise, console,
  };
  vm.runInNewContext(process.argv[1], context);
  await new Promise((resolve) => setImmediate(resolve));
  const focusBeforePromptHistory = focusCalls;
  const promptBody = { versions: [], active_prompt_version_id: null };
  resolvePrompts({ ok: true, status: 200, json: async () => promptBody });
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  return { focusBeforePromptHistory, focusCalls, originalValue: original.value };
}

const runs = [run(""), run("synthetic existing entry")];
Promise.all(runs).then(
  (result) => process.stdout.write(JSON.stringify(result)),
);
"""

    result = subprocess.run(
        ["node", "-e", harness, script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout == (
        '[{"focusBeforePromptHistory":0,"focusCalls":1,"originalValue":""},'
        '{"focusBeforePromptHistory":0,"focusCalls":0,'
        '"originalValue":"synthetic existing entry"}]'
    )


def test_stacked_workspace_uses_native_caret_and_accessible_resizer(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    stylesheet = client.get("/static/app.css")
    page = client.get("/")

    assert stylesheet.status_code == 200
    assert "caret-color: var(--blue)" in stylesheet.text
    assert "caret-color: transparent" not in stylesheet.text
    assert ".faux-caret" not in stylesheet.text
    assert "grid-template-rows:" in stylesheet.text
    assert "cursor: row-resize" in stylesheet.text
    assert ".utility-rail" in stylesheet.text
    assert ".workspace.is-original-collapsed" in stylesheet.text
    assert "min-width: 720px" not in stylesheet.text
    assert "@media (max-width: 760px)" in stylesheet.text
    assert 'role="separator"' in page.text
    assert 'aria-valuemin="45"' in page.text
    assert 'aria-valuemax="80"' in page.text
    assert 'class="panel-prompt-control"' in page.text


def test_regular_desktop_workspace_uses_the_remaining_viewport_height(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    stylesheet = client.get("/static/app.css").text
    desktop_fit = stylesheet.split(
        "@media (min-width: 761px)", maxsplit=1
    )[1].split("@media (max-width: 920px)", maxsplit=1)[0]

    assert "height: 100dvh" in desktop_fit
    assert "overflow: hidden" in desktop_fit
    assert "main {" in desktop_fit
    assert "flex: 1 1 auto" in desktop_fit
    assert ".workspace-shell" in desktop_fit
    assert ".workspace {" in desktop_fit
    assert "height: 100%" in desktop_fit
    assert "min-height: 0" in desktop_fit
    assert "minmax(0, var(--original-share))" in stylesheet
    assert "minmax(0, var(--cleaned-share))" in stylesheet
    assert "minmax(260px" not in stylesheet
    assert "minmax(170px" not in stylesheet
