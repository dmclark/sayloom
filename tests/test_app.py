import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from local_text.app import create_app
from local_text.cleanup import CleanupService
from local_text.config import Profile, Settings


def test_health_reports_development_profile(initialized_settings: Settings) -> None:
    client = TestClient(create_app(initialized_settings))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "profile": "development",
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
    assert 'id="cleanup-status"' in response.text
    assert 'id="cancel-cleanup"' in response.text
    assert 'id="prompt-history"' in response.text
    assert 'id="active-prompt-selector"' in response.text
    assert 'id="prompt-manager"' in response.text
    assert 'id="save-prompt"' in response.text
    assert 'id="workspace-resizer"' in response.text
    assert 'id="show-canvas"' in response.text
    assert 'id="show-prompts"' in response.text
    assert "Type, paste, or dictate here" in response.text
    assert response.text.index('class="outgoing-strip"') < response.text.index(
        'id="cleanup-status"'
    )


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


def test_browser_script_supports_generic_input_and_dictation_compatibility(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    script = client.get("/static/app.js")

    assert script.status_code == 200
    assert "syntheticPastePending" in script.text
    assert "followsSyntheticPaste" in script.text
    assert "event.isTrusted" in script.text
    assert 'elements.original.addEventListener("input", handleOriginalInput)' in script.text
    assert "scheduleCleanup();" in script.text
    assert "AbortController" in script.text
    assert "setSelectionRange" in script.text
    assert "fauxCaret" not in script.text
    assert 'elements.workspaceResizer.addEventListener("pointerdown"' in script.text
    assert 'elements.promptsNav.addEventListener("click"' in script.text
    assert "elements.promptManager.showModal()" in script.text
    run_cleanup = script.text.split("async function runCleanup()", maxsplit=1)[1].split(
        "function scheduleCleanup()", maxsplit=1
    )[0]
    scheduled_cleanup = script.text.split("function scheduleCleanup()", maxsplit=1)[1].split(
        "function handleOriginalInput", maxsplit=1
    )[0]
    assert 'elements.cleaned.value = "";' in run_cleanup
    assert 'elements.cleaned.value = "";' in scheduled_cleanup


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
    assert "min-width: 720px" not in stylesheet.text
    assert "@media (max-width: 760px)" in stylesheet.text
    assert 'role="separator"' in page.text
    assert 'aria-valuemin="45"' in page.text
    assert 'aria-valuemax="80"' in page.text
    assert 'class="panel-prompt-control"' in page.text
