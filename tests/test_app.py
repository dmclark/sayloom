from fastapi.testclient import TestClient

from local_text.app import create_app
from local_text.cleanup import CleanupService
from local_text.config import Profile, Settings


def test_health_reports_development_profile() -> None:
    client = TestClient(create_app(Settings(Profile.DEVELOPMENT)))

    assert client.get("/health").json() == {"status": "ok", "profile": "development"}


def test_development_page_identifies_development_brand() -> None:
    client = TestClient(create_app(Settings(Profile.DEVELOPMENT)))

    response = client.get("/")

    assert response.status_code == 200
    assert "<title>Sayloom Development</title>" in response.text
    assert 'aria-label="Development profile"' in response.text
    assert 'id="original-text"' in response.text
    assert 'id="cleaned-text"' in response.text
    assert 'id="cleanup-status"' in response.text
    assert 'id="cancel-cleanup"' in response.text


def test_release_profile_uses_release_brand() -> None:
    client = TestClient(create_app(Settings(Profile.RELEASE)))

    assert client.app.title == "Sayloom"
    assert client.get("/health").json()["profile"] == "release"
    page = client.get("/").text
    assert "<title>Sayloom</title>" in page
    assert 'aria-label="Development profile"' not in page


def test_config_reports_cleanup_without_exposing_key() -> None:
    settings = Settings(Profile.DEVELOPMENT, gemini_api_key="not-a-real-key")
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


def test_cleanup_endpoint_fails_open_when_provider_is_unconfigured() -> None:
    client = TestClient(create_app(Settings(Profile.DEVELOPMENT)))

    response = client.post(
        "/api/cleanup",
        json={"raw_text": "synthetic raw transcript", "enabled": True},
    )

    assert response.status_code == 200
    assert response.json() == {
        "cleaned_text": "synthetic raw transcript",
        "status": "disabled",
        "provider": "gemini",
        "model": "gemini-3.5-flash",
    }


def test_cleanup_endpoint_returns_provider_result() -> None:
    class Provider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, raw_text: str, system_prompt: str) -> str:
            assert raw_text == "synthetic raw transcript"
            assert "untrusted transcript data" in system_prompt
            return "Synthetic clean transcript."

    service = CleanupService(provider=Provider(), model="test-model", timeout_seconds=1)
    client = TestClient(create_app(Settings(Profile.DEVELOPMENT), service))

    response = client.post(
        "/api/cleanup",
        json={"raw_text": "synthetic raw transcript", "enabled": True},
    )

    assert response.status_code == 200
    assert response.json()["cleaned_text"] == "Synthetic clean transcript."
    assert response.json()["status"] == "cleaned"


def test_outgoing_state_is_published_and_cleared_in_memory() -> None:
    client = TestClient(create_app(Settings(Profile.DEVELOPMENT)))
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


def test_outgoing_state_rejects_text_not_present_in_either_editor() -> None:
    client = TestClient(create_app(Settings(Profile.DEVELOPMENT)))

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


def test_browser_script_contains_voiceitt_and_cancellation_mechanics() -> None:
    client = TestClient(create_app(Settings(Profile.DEVELOPMENT)))

    script = client.get("/static/app.js")

    assert script.status_code == 200
    assert "event.isTrusted" in script.text
    assert "AbortController" in script.text
    assert "setSelectionRange" in script.text
    assert "fauxCaret" in script.text
