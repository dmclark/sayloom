import json
import sqlite3
import subprocess
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import local_text.app as app_module
from local_text.app import PAID_DATA_ACKNOWLEDGEMENT, STATIC_VERSION, create_app
from local_text.cleanup import CleanupService, ProviderOutput, SequentialCleanupProvider
from local_text.config import Profile, Settings, load_settings
from local_text.correction_benchmark import BenchmarkError
from local_text.prompts import effective_system_prompt


def test_health_reports_development_profile(initialized_settings: Settings) -> None:
    client = TestClient(create_app(initialized_settings))

    response = client.get("/health")

    assert response.status_code == 200
    health = response.json()
    cleanup_configuration = health.pop("cleanup_configuration")
    evaluation_configuration = health.pop("evaluation_configuration")
    benchmark_configuration = health.pop("correction_benchmark_configuration")
    assert health == {
        "status": "ok",
        "profile": "development",
        "development_state": None,
        "database": {
            "state": "current",
            "current_revision": "0002_target_management",
            "expected_revision": "0002_target_management",
        },
        "configuration_error": None,
    }
    assert cleanup_configuration["status"] == "unavailable"
    assert cleanup_configuration["available"] is False
    assert cleanup_configuration["routes"] == []
    assert cleanup_configuration["validation_error"] is None
    assert evaluation_configuration["status"] == "unconfigured"
    assert evaluation_configuration["available"] is False
    assert benchmark_configuration == {
        "available": False,
        "destination": "configured private benchmark corpus",
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
        "expected_revision": "0002_target_management",
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
    assert '<h2>Prepared</h2>' in response.text
    assert '>Prepared</button>' in response.text
    assert 'aria-label="Resize Original and Prepared fields"' in response.text
    assert 'aria-valuetext="Original 65 percent, Prepared 35 percent"' in response.text
    assert '<h2>Cleaned</h2>' not in response.text
    assert '>Cleaned</button>' not in response.text
    assert 'id="toggle-original"' in response.text
    assert 'id="default-correction-mode"' in response.text
    assert 'id="current-correction-mode"' in response.text
    assert 'id="active-correction-mode"' in response.text
    assert 'id="cleanup-disclosure"' in response.text
    assert 'id="cleanup-route-list"' in response.text
    assert "This does not save an evaluation corpus." not in response.text
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

    configuration = response.json()
    cleanup_configuration = configuration.pop("cleanup_configuration")
    evaluation_configuration = configuration.pop("evaluation_configuration")
    benchmark_configuration = configuration.pop("correction_benchmark_configuration")
    assert configuration == {
        "display_name": "Sayloom Development",
        "profile": "development",
        "development_state": None,
        "cleanup_enabled_by_default": True,
        "default_correction_mode": "conservative",
        "cleanup_available": True,
        "cleanup_model": "gemini-3.5-flash",
    }
    assert cleanup_configuration["status"] == "gemini_only"
    assert cleanup_configuration["routes"] == [
        {"provider": "gemini", "model": "gemini-3.5-flash"},
        {"provider": "gemini", "model": "gemini-2.5-flash"},
    ]
    assert cleanup_configuration["paid_data_acknowledgement"] is None
    assert evaluation_configuration["status"] == "unconfigured"
    assert benchmark_configuration["available"] is False
    assert "not-a-real-key" not in response.text


def cross_provider_settings(initialized_settings: Settings, **overrides) -> Settings:
    values = {
        "profile": Profile.DEVELOPMENT,
        "gemini_api_key": "synthetic-gemini-key",
        "gemini_model": "gemini-3.7-flash",
        "openai_api_key": "synthetic-openai-key",
        "openai_model": "gpt-5.6-luna",
        "cleanup_route_order": "gemini,openai",
        "gemini_quota_group_id": "gemini-paid-project",
        "openai_quota_group_id": "openai-paid-project",
        "paid_data_acknowledgement": PAID_DATA_ACKNOWLEDGEMENT,
        "database_path": initialized_settings.database_path,
    }
    values.update(overrides)
    return Settings(**values)


def test_acknowledged_cross_provider_route_is_exact_sanitized_and_falls_back_once(
    initialized_settings: Settings, monkeypatch
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "generativelanguage" in request.url.host:
            return httpx.Response(503, json={"error": {"code": "service_unavailable"}})
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
                                "text": '{"cleaned_text":"Synthetic source."}',
                            }
                        ],
                    }
                ],
            },
        )

    transport = httpx.MockTransport(respond)
    provider_clients: list[httpx.AsyncClient] = []

    def new_client(_timeout: float) -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=transport)
        provider_clients.append(client)
        return client

    monkeypatch.setattr(app_module, "_new_provider_client", new_client)
    settings = cross_provider_settings(initialized_settings)

    with TestClient(create_app(settings)) as client:
        configuration_response = client.get("/api/config")
        health_response = client.get("/health")
        result = client.post(
            "/api/cleanup", json={"raw_text": "synthetic source", "enabled": True}
        )
        provider = client.app.state.cleanup_service.provider
        assert isinstance(provider, SequentialCleanupProvider)
        assert [route.quota_group_id for route in provider.routes] == [
            "gemini-paid-project",
            "openai-paid-project",
        ]
        assert provider.total_budget_seconds == 30
        assert [route.attempt_budget_seconds for route in provider.routes] == [30, 30]

    cleanup_configuration = configuration_response.json()["cleanup_configuration"]
    assert cleanup_configuration == health_response.json()["cleanup_configuration"]
    assert cleanup_configuration["status"] == "cross_provider"
    assert cleanup_configuration["routes"] == [
        {"provider": "gemini", "model": "gemini-3.7-flash"},
        {"provider": "openai", "model": "gpt-5.6-luna"},
    ]
    assert cleanup_configuration["paid_data_acknowledgement"] == PAID_DATA_ACKNOWLEDGEMENT
    assert "same current text and cleanup instruction" in cleanup_configuration["disclosure"][
        "fallback"
    ]
    assert result.json()["provider"] == "openai"
    assert result.json()["model"] == "gpt-5.6-luna"
    assert len(requests) == 2
    assert requests[0].headers["x-goog-api-key"] == "synthetic-gemini-key"
    assert requests[1].headers["authorization"] == "Bearer synthetic-openai-key"
    serialized = configuration_response.text + health_response.text
    assert "synthetic-gemini-key" not in serialized
    assert "synthetic-openai-key" not in serialized
    assert len(provider_clients) == 2
    assert all(provider_client.is_closed for provider_client in provider_clients)


def test_unacknowledged_cross_provider_configuration_creates_no_client_and_fails_open(
    initialized_settings: Settings, monkeypatch
) -> None:
    calls = 0

    def unexpected_client(_timeout: float):
        nonlocal calls
        calls += 1
        raise AssertionError("invalid configuration must not create a provider client")

    monkeypatch.setattr(app_module, "_new_provider_client", unexpected_client)
    settings = cross_provider_settings(initialized_settings, paid_data_acknowledgement=None)

    with TestClient(create_app(settings)) as client:
        configuration_response = client.get("/api/config")
        result = client.post(
            "/api/cleanup", json={"raw_text": "synthetic source", "enabled": True}
        )

    configuration = configuration_response.json()["cleanup_configuration"]
    assert configuration["status"] == "invalid"
    assert configuration["available"] is False
    assert configuration["routes"] == []
    assert configuration["validation_error"] == "paid_data_acknowledgement_required"
    assert result.json()["status"] == "disabled"
    assert result.json()["cleaned_text"] == "synthetic source"
    assert calls == 0
    assert "synthetic-gemini-key" not in configuration_response.text
    assert "synthetic-openai-key" not in configuration_response.text


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        ({"cleanup_route_order": "openai,gemini"}, "route_order_must_be_gemini_openai"),
        ({"gemini_api_key_is_explicit": False}, "explicit_gemini_credential_required"),
        ({"gemini_model": "gemini-3.5-flash"}, "gemini_model_must_be_gemini_3_7_flash"),
        ({"openai_api_key": None}, "explicit_openai_credential_required"),
        ({"openai_model": "other-model"}, "openai_model_must_be_gpt_5_6_luna"),
        (
            {"openai_quota_group_id": "gemini-paid-project"},
            "provider_quota_groups_must_differ",
        ),
    ],
)
def test_invalid_cross_provider_variants_create_no_clients(
    initialized_settings: Settings, monkeypatch, overrides, expected_error: str
) -> None:
    calls = 0

    def unexpected_client(_timeout: float):
        nonlocal calls
        calls += 1
        raise AssertionError("invalid configuration must not create a provider client")

    monkeypatch.setattr(app_module, "_new_provider_client", unexpected_client)
    settings = cross_provider_settings(initialized_settings, **overrides)

    with TestClient(create_app(settings)) as client:
        configuration = client.get("/health").json()["cleanup_configuration"]

    assert configuration["status"] == "invalid"
    assert configuration["validation_error"] == expected_error
    assert configuration["routes"] == []
    assert calls == 0


def test_generic_openai_key_never_activates_openai(
    initialized_settings: Settings, monkeypatch
) -> None:
    provider_keys = (
        "LOCAL_TEXT_GEMINI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "LOCAL_TEXT_OPENAI_API_KEY",
        "LOCAL_TEXT_OPENAI_MODEL",
        "LOCAL_TEXT_CLEANUP_ROUTE_ORDER",
        "LOCAL_TEXT_GEMINI_QUOTA_GROUP_ID",
        "LOCAL_TEXT_OPENAI_QUOTA_GROUP_ID",
        "LOCAL_TEXT_CLEANUP_PAID_DATA_ACKNOWLEDGEMENT",
    )
    for key in provider_keys:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai-key")
    monkeypatch.setenv("LOCAL_TEXT_DATABASE_PATH", str(initialized_settings.database_path))

    settings = load_settings()
    response = TestClient(create_app(settings)).get("/api/config")

    assert settings.openai_api_key is None
    assert response.json()["cleanup_configuration"]["status"] == "unavailable"
    assert "ambient-openai-key" not in response.text


def test_ambient_gemini_remains_legacy_compatible_without_activating_ambient_openai(
    initialized_settings: Settings, monkeypatch
) -> None:
    for key in (
        "LOCAL_TEXT_GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "LOCAL_TEXT_OPENAI_API_KEY",
        "LOCAL_TEXT_OPENAI_MODEL",
        "LOCAL_TEXT_CLEANUP_ROUTE_ORDER",
        "LOCAL_TEXT_GEMINI_QUOTA_GROUP_ID",
        "LOCAL_TEXT_OPENAI_QUOTA_GROUP_ID",
        "LOCAL_TEXT_CLEANUP_PAID_DATA_ACKNOWLEDGEMENT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "ambient-gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai-key")
    monkeypatch.setenv("LOCAL_TEXT_DATABASE_PATH", str(initialized_settings.database_path))

    settings = load_settings()
    response = TestClient(create_app(settings)).get("/api/config")

    assert settings.gemini_api_key == "ambient-gemini-key"
    assert settings.gemini_api_key_is_explicit is False
    assert settings.openai_api_key is None
    assert response.json()["cleanup_configuration"]["status"] == "gemini_only"
    assert "ambient-gemini-key" not in response.text
    assert "ambient-openai-key" not in response.text


def test_app_lifespan_reuses_and_closes_the_gemini_client(
    initialized_settings: Settings, monkeypatch
) -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        cleaned_text = f"Synthetic source {'one' if calls == 1 else 'two'}."
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": json.dumps({"cleaned_text": cleaned_text})}
                            ]
                        }
                    }
                ]
            },
        )

    provider_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(
        app_module,
        "_new_provider_client",
        lambda timeout_seconds: provider_client,
    )
    settings = Settings(
        Profile.DEVELOPMENT,
        gemini_api_key="synthetic-key",
        database_path=initialized_settings.database_path,
    )

    with TestClient(create_app(settings)) as client:
        provider = client.app.state.cleanup_service.provider
        assert isinstance(provider, SequentialCleanupProvider)
        assert provider.total_budget_seconds == 30
        assert [route.model for route in provider.routes] == [
            "gemini-3.5-flash",
            "gemini-2.5-flash",
        ]
        assert [route.attempt_budget_seconds for route in provider.routes] == [30, 30]
        assert {route.quota_group_id for route in provider.routes} == {"gemini-default"}
        for source in ("synthetic source one", "synthetic source two"):
            response = client.post("/api/cleanup", json={"raw_text": source, "enabled": True})
            assert response.status_code == 200
            assert response.json()["status"] == "cleaned"
        assert not provider_client.is_closed

    assert calls == 2
    assert provider_client.is_closed


def test_active_gemini_router_falls_back_once_on_route_transient_failure(
    initialized_settings: Settings, monkeypatch
) -> None:
    requested_models: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        model = request.url.path.split("/")[-1].split(":", maxsplit=1)[0]
        requested_models.append(model)
        if model == "gemini-3.5-flash":
            return httpx.Response(503, json={"error": {"code": "service_unavailable"}})
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": '{"cleaned_text":"Synthetic source."}'}]}}
                ]
            },
        )

    provider_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(app_module, "_new_provider_client", lambda _timeout: provider_client)
    settings = Settings(
        Profile.DEVELOPMENT,
        gemini_api_key="synthetic-key",
        database_path=initialized_settings.database_path,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/cleanup", json={"raw_text": "synthetic source", "enabled": True}
        )

    assert response.status_code == 200
    assert response.json()["status"] == "cleaned"
    assert response.json()["model"] == "gemini-2.5-flash"
    assert [
        (attempt["route_index"], attempt["outcome"]) for attempt in response.json()["attempts"]
    ] == [
        (0, "failure"),
        (1, "success"),
    ]
    assert requested_models == ["gemini-3.5-flash", "gemini-2.5-flash"]
    assert provider_client.is_closed


def test_active_gemini_shared_quota_failure_fails_open_without_replayed_call(
    initialized_settings: Settings, monkeypatch
) -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={"error": {"code": "rate_limited"}})

    provider_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(app_module, "_new_provider_client", lambda _timeout: provider_client)
    settings = Settings(
        Profile.DEVELOPMENT,
        gemini_api_key="synthetic-key",
        database_path=initialized_settings.database_path,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/cleanup", json={"raw_text": "synthetic source", "enabled": True}
        )

    assert response.status_code == 200
    assert response.json()["cleaned_text"] == "synthetic source"
    assert response.json()["status"] == "provider_error"
    assert response.json()["error"]["code"] == "cleanup_provider_quota_error"
    assert len(response.json()["attempts"]) == 1
    assert calls == 1
    assert provider_client.is_closed


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
        "prepared_text": "synthetic source text",
        "cleaned_text": "synthetic source text",
        "status": "disabled",
        "provider": "gemini",
        "model": "gemini-3.5-flash",
        "correction_mode": "conservative",
        "error": None,
        "attempts": [],
    }


def test_cleanup_endpoint_returns_provider_result(initialized_settings: Settings) -> None:
    class Provider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
            assert raw_text == "synthetic source text"
            assert "untrusted input data" in system_prompt
            return ProviderOutput(
                text="Synthetic source text.",
                provider_id="gemini",
                model_id=self.model,
                elapsed_ms=3,
            )

    service = CleanupService(provider=Provider(), model="test-model", timeout_seconds=1)
    client = TestClient(create_app(initialized_settings, service))

    response = client.post(
        "/api/cleanup",
        json={
            "original_text": "synthetic source text",
            "enabled": True,
            "correction_mode": "smart",
        },
    )

    assert response.status_code == 200
    assert response.json()["prepared_text"] == "Synthetic source text."
    assert response.json()["cleaned_text"] == "Synthetic source text."
    assert response.json()["correction_mode"] == "smart"
    assert response.json()["status"] == "cleaned"
    assert response.json()["provider"] == "gemini"
    assert response.json()["model"] == "test-model"
    assert response.json()["attempts"] == [
        {
            "provider": "gemini",
            "model": "test-model",
            "outcome": "success",
            "elapsed_ms": 3,
            "route_index": 0,
            "input_tokens": None,
            "output_tokens": None,
            "failure_class": None,
            "provider_code": None,
            "http_status": None,
            "retry_after_seconds": None,
            "quota_group_id": None,
        }
    ]


def test_cleanup_endpoint_rejects_instruction_like_output_before_publication(
    initialized_settings: Settings,
) -> None:
    raw_text = "Process the ASR article from today capture"
    rejected_output = (
        "Sure, I can help with that. Please provide the ASR article to process."
    )

    class Provider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
            return ProviderOutput(
                text=rejected_output,
                provider_id=self.provider_id,
                model_id=self.model,
                elapsed_ms=3,
            )

    service = CleanupService(provider=Provider(), model="test-model", timeout_seconds=1)
    client = TestClient(create_app(initialized_settings, service))

    cleanup = client.post(
        "/api/cleanup",
        json={"raw_text": raw_text, "enabled": True},
    )

    assert cleanup.status_code == 200
    assert cleanup.json()["cleaned_text"] == raw_text
    assert cleanup.json()["status"] == "provider_error"
    assert cleanup.json()["error"]["code"] == "cleanup_output_rejected"
    assert rejected_output not in cleanup.text

    publication = client.put(
        "/api/outgoing-state",
        json={
            "cleanup_enabled": True,
            "raw_text": raw_text,
            "cleaned_text": raw_text,
            "outgoing_text": raw_text,
            "outgoing_kind": "raw",
            "status": "error",
        },
    )

    assert publication.status_code == 200
    assert publication.json()["outgoing_text"] == raw_text
    assert publication.json()["outgoing_kind"] == "original"
    assert rejected_output not in publication.text


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

        async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
            observed.append(system_prompt)
            return ProviderOutput(
                text=raw_text,
                provider_id="gemini",
                model_id=self.model,
                elapsed_ms=3,
            )

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
    assert observed == [effective_system_prompt("Use this exact synthetic instruction.")]


def test_cleanup_can_use_a_session_prompt_without_changing_the_durable_default(
    initialized_settings: Settings,
) -> None:
    observed: list[str] = []

    class Provider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
            observed.append(system_prompt)
            return ProviderOutput(
                text=raw_text,
                provider_id="gemini",
                model_id=self.model,
                elapsed_ms=3,
            )

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
    assert observed == [
        effective_system_prompt("Use this request-scoped synthetic instruction.")
    ]
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


def test_correction_mode_preference_is_durable_and_separate_from_workspace_state(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    saved = client.put(
        "/api/preferences/correction-mode",
        json={"correction_mode": "smart"},
    )
    assert saved.status_code == 200
    assert saved.json() == {"default_correction_mode": "smart"}

    workspace_override = client.put(
        "/api/outgoing-state",
        json={
            "cleanup_enabled": True,
            "original_text": "synthetic original",
            "prepared_text": "Synthetic original.",
            "outgoing_text": "Synthetic original.",
            "outgoing_kind": "prepared",
            "status": "cleaned",
            "correction_mode": "conservative",
        },
    )
    assert workspace_override.status_code == 200
    assert workspace_override.json()["correction_mode"] == "conservative"

    restarted = TestClient(create_app(initialized_settings))
    assert restarted.get("/api/config").json()["default_correction_mode"] == "smart"
    assert restarted.get("/api/outgoing-state").json()["correction_mode"] == "smart"

    invalid = client.put(
        "/api/preferences/correction-mode",
        json={"correction_mode": "polished"},
    )
    assert invalid.status_code == 422


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
    expanded = {
        **update,
        "original_text": update["raw_text"],
        "prepared_text": update["cleaned_text"],
        "outgoing_kind": "prepared",
        "correction_mode": "conservative",
        "revision": 1,
    }
    assert published.json() == expanded
    assert client.get("/api/outgoing-state").json() == expanded

    cleared = client.delete("/api/outgoing-state")
    assert cleared.status_code == 200
    assert cleared.json()["outgoing_text"] == ""
    assert cleared.json()["outgoing_kind"] == "empty"
    assert cleared.json()["original_text"] == cleared.json()["raw_text"] == ""
    assert cleared.json()["prepared_text"] == cleared.json()["cleaned_text"] == ""
    assert cleared.json()["revision"] == 2


def test_outgoing_state_accepts_canonical_contract_and_smart_mode(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    response = client.put(
        "/api/outgoing-state",
        json={
            "cleanup_enabled": True,
            "original_text": "synthetic original",
            "prepared_text": "Synthetic original.",
            "outgoing_text": "Synthetic original.",
            "outgoing_kind": "prepared",
            "status": "cleaned",
            "correction_mode": "smart",
        },
    )

    assert response.status_code == 200
    assert response.json()["original_text"] == response.json()["raw_text"]
    assert response.json()["prepared_text"] == response.json()["cleaned_text"]
    assert response.json()["outgoing_kind"] == "prepared"
    assert response.json()["correction_mode"] == "smart"


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


def test_benchmark_example_api_writes_exact_synthetic_pair(
    initialized_settings: Settings, tmp_path: Path
) -> None:
    cases_path = tmp_path.parent / f"{tmp_path.name}-private-benchmark" / "cases.json"
    settings = replace(
        initialized_settings,
        correction_benchmark_cases_path=cases_path,
    )
    client = TestClient(create_app(settings))

    response = client.post(
        "/api/correction-benchmark/examples",
        json={
            "original_text": "Synthetic original wording.",
            "intended_text": "Synthetic intended wording.",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "status": "saved",
        "destination": "configured private benchmark corpus",
    }
    saved = json.loads(cases_path.read_text())
    assert saved[0]["source_text"] == "Synthetic original wording."
    assert saved[0]["intended_text"] == "Synthetic intended wording."


def test_benchmark_example_api_fails_safely_without_mutating_storage(
    initialized_settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    cases_path = tmp_path / "private-benchmark" / "cases.json"
    settings = replace(
        initialized_settings,
        correction_benchmark_cases_path=cases_path,
    )

    def fail_capture(**_kwargs: object) -> None:
        raise BenchmarkError("synthetic path detail must stay private")

    monkeypatch.setattr(app_module, "capture_example", fail_capture)
    response = TestClient(create_app(settings)).post(
        "/api/correction-benchmark/examples",
        json={
            "original_text": "Synthetic original wording.",
            "intended_text": "Synthetic intended wording.",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "benchmark_write_failed"
    assert "path detail" not in response.text
    assert not cases_path.exists()


def test_benchmark_example_api_requires_configured_external_storage(
    initialized_settings: Settings,
) -> None:
    response = TestClient(create_app(initialized_settings)).post(
        "/api/correction-benchmark/examples",
        json={
            "original_text": "Synthetic original wording.",
            "intended_text": "Synthetic intended wording.",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "benchmark_storage_unavailable"


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
    assert "Original fallback · replacement Prepared pending" in script.text
    assert "original_text: originalText" in script.text
    assert "prepared_text: preparedText" in script.text
    assert 'usePrepared ? "prepared" : "original"' in script.text
    outgoing_selection = script.text.split(
        "function selectedOutgoingState()", maxsplit=1
    )[1].split("function renderCountsAndSelection()", maxsplit=1)[0]
    assert "raw_text:" not in outgoing_selection
    assert "cleaned_text:" not in outgoing_selection
    assert "setCleanupError" in script.text
    assert "setPublicationError" in script.text
    assert 'message: "The browser could not connect to the local API."' in script.text
    assert "cancelCleanup" not in script.text
    assert "setOriginalCollapsed" in script.text
    assert "correction_mode: effectiveCorrectionMode()" in script.text
    assert 'fetch("/api/preferences/correction-mode"' in script.text
    assert "currentCorrectionModeOverride = null" in script.text
    assert "renderCorrectionMode();" in script.text
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
      this.options = [{ textContent: "" }];
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
    "#cleanup-disclosure": new Element(), "#cleanup-disclosure-summary": new Element(),
    "#cleanup-route-list": new Element(), "#cleanup-processing-disclosure": new Element(),
    "#cleanup-fallback-disclosure": new Element(), "#cleanup-corpus-disclosure": new Element(),
    "#cleanup-validation-detail": new Element(),
    ".workspace": new Element(), "#workspace-resizer": new Element(),
    "#active-prompt-selector": new Element(), "#error-details-dialog": new Element(),
    "#error-details-ledger": new Element(), "#close-error-details": new Element(),
    "#copy-error-details": new Element(),
  };
  const querySelector = (selector) => selectors[selector] || new Element();
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


def test_browser_benchmark_dialog_cancel_success_selection_and_failure(
    initialized_settings: Settings,
) -> None:
    script = TestClient(create_app(initialized_settings)).get("/static/app.js").text
    harness = r"""
const vm = require("vm");

class Element {
  constructor() {
    this.value = "";
    this.checked = true;
    this.disabled = false;
    this.dataset = {};
    this.open = false;
    this.options = [{ textContent: "" }];
    this.style = { setProperty() {} };
    this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
    this.lastElementChild = { textContent: "" };
    this.listeners = {};
    this.textContent = "";
    this.title = "";
    this.selectionStart = 0;
    this.selectionEnd = 0;
    this.focused = false;
    this.selected = false;
    this.attributes = {};
  }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  async dispatch(type, event = {}) {
    event.target ||= this;
    event.preventDefault ||= () => {};
    for (const callback of this.listeners[type] || []) await callback(event);
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || (name === "aria-valuenow" ? "65" : null); }
  removeAttribute(name) { delete this.attributes[name]; }
  append() {}
  querySelectorAll() { return []; }
  setPointerCapture() {}
  setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; }
  getBoundingClientRect() { return { top: 0, height: 100 }; }
  reportValidity() { return this.value !== "" || !this.required; }
  focus() { document.activeElement = this; this.focused = true; }
  select() { this.selected = true; }
  showModal() { this.open = true; }
  close() {
    this.open = false;
    for (const callback of this.listeners.close || []) callback({ target: this });
  }
}

const elements = {};
const document = {
  activeElement: null,
  querySelector(selector) { return elements[selector] ||= new Element(); },
  createElement() { return new Element(); },
  addEventListener() {},
};

function response(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

async function settle() {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
}

async function run({ cancel = false, originalSelected = false, fail = false, newCleaned = false }) {
  const requests = [];
  const fetch = async (url, options = {}) => {
    const method = options.method || "GET";
    if (url === "/api/config") return response(200, {
      cleanup_enabled_by_default: true,
      default_correction_mode: "conservative",
      cleanup_configuration: { status: "unavailable", routes: [], disclosure: {} },
      correction_benchmark_configuration: { available: true },
      evaluation_configuration: { available: false },
    });
    if (url === "/api/prompts") return response(200, {
      versions: [], active_prompt_version_id: null,
    });
    if (url === "/api/outgoing-state" && method === "DELETE") return response(200, { revision: 1 });
    if (url === "/api/outgoing-state" && method === "PUT") {
      requests.push({ url, body: JSON.parse(options.body) });
      return response(200, { revision: requests.length + 1 });
    }
    if (url === "/api/correction-benchmark/examples") {
      requests.push({ url, body: JSON.parse(options.body) });
      return fail
        ? response(503, { detail: {
            code: "benchmark_write_failed",
            message: "The example was not added to the private benchmark corpus.",
            retry_action: "Check the configured private destination and retry.",
          } })
        : response(201, { status: "saved", destination: "configured private benchmark corpus" });
    }
    if (url === "/api/cleanup") return response(200, {
      cleaned_text: "Synthetic new cleaned wording.", status: "cleaned",
    });
    throw new Error(`Unexpected request: ${method} ${url}`);
  };
  const window = {
    clearTimeout,
    setTimeout,
    requestAnimationFrame(callback) { callback(); },
    addEventListener() {},
    confirm() { return true; },
  };
  const context = {
    document, window, fetch, AbortController, Promise, console,
    navigator: { clipboard: {} }, Blob, URL,
  };
  vm.runInNewContext(process.argv[1], context);
  await settle();

  const original = elements["#original-text"];
  const cleaned = elements["#cleaned-text"];
  const dialog = elements["#benchmark-capture-dialog"];
  const intended = elements["#benchmark-intended-text"];
  original.value = "Synthetic original wording.";
  cleaned.value = "Synthetic prepared wording.";
  await elements["#select-cleaned"].dispatch("click");
  if (originalSelected) await elements["#select-original"].dispatch("click");
  await elements["#correct-and-add-example"].dispatch("click");
  const opened = {
    open: dialog.open, prefill: intended.value,
    focused: intended.focused, selected: intended.selected,
  };

  if (cancel) {
    await elements["#cancel-benchmark-capture-secondary"].dispatch("click");
    return {
      opened, open: dialog.open, original: original.value,
      cleaned: cleaned.value,
      buttonDisabledAfterSuccess: elements["#correct-and-add-example"].disabled,
      requests,
    };
  }

  intended.value = "Synthetic corrected wording.";
  await elements["#benchmark-capture-form"].dispatch("submit");
  await settle();
  const buttonDisabledAfterSuccess = elements["#correct-and-add-example"].disabled;
  const capturedCleaned = cleaned.value;
  const outgoingAfterSuccess = requests.at(-1).body.outgoing_text;
  const outgoingLabelAfterSuccess = elements["#outgoing-kind"].textContent;
  let buttonDisabledAfterNewCleaned = null;
  if (newCleaned) {
    original.value = "Synthetic new original wording.";
    await elements["#run-cleanup"].dispatch("click");
    await settle();
    buttonDisabledAfterNewCleaned = elements["#correct-and-add-example"].disabled;
  }
  return {
    opened,
    open: dialog.open,
    original: original.value,
    cleaned: cleaned.value,
    capturedCleaned,
    outgoingAfterSuccess,
    outgoingLabelAfterSuccess,
    feedback: elements["#benchmark-capture-status"].textContent,
    outgoingLabel: elements["#outgoing-kind"].textContent,
    buttonDisabledAfterSuccess,
    buttonDisabledAfterNewCleaned,
    requests,
  };
}

(async () => {
  const cancel = await run({ cancel: true });
  Object.keys(elements).forEach((key) => delete elements[key]);
  const prepared = await run({ newCleaned: true });
  Object.keys(elements).forEach((key) => delete elements[key]);
  const original = await run({ originalSelected: true });
  Object.keys(elements).forEach((key) => delete elements[key]);
  const failure = await run({ fail: true });
  process.stdout.write(JSON.stringify({ cancel, prepared, original, failure }));
})().catch((error) => { process.stderr.write(error.stack); process.exit(1); });
"""

    result = subprocess.run(
        ["node", "-e", harness, script],
        check=True,
        capture_output=True,
        text=True,
    )
    observed = json.loads(result.stdout)

    for scenario in (observed["cancel"], observed["original"], observed["failure"]):
        assert scenario["opened"] == {
            "open": True,
            "prefill": "Synthetic prepared wording.",
            "focused": True,
            "selected": True,
        }
        assert scenario["original"] == "Synthetic original wording."

    assert observed["cancel"]["cleaned"] == "Synthetic prepared wording."
    assert not any(
        request["url"] == "/api/correction-benchmark/examples"
        for request in observed["cancel"]["requests"]
    )
    assert observed["prepared"]["opened"] == {
        "open": True,
        "prefill": "Synthetic prepared wording.",
        "focused": True,
        "selected": True,
    }
    assert observed["prepared"]["capturedCleaned"] == "Synthetic corrected wording."
    assert observed["prepared"]["outgoingAfterSuccess"] == "Synthetic corrected wording."
    assert observed["prepared"]["requests"][-1]["body"]["outgoing_kind"] == "prepared"
    assert observed["prepared"]["requests"][-1]["body"]["original_text"] == (
        "Synthetic original wording."
    )
    assert observed["prepared"]["requests"][-1]["body"]["prepared_text"] == (
        "Synthetic corrected wording."
    )
    assert "raw_text" not in observed["prepared"]["requests"][-1]["body"]
    assert "cleaned_text" not in observed["prepared"]["requests"][-1]["body"]
    benchmark_request = next(
        request
        for request in observed["prepared"]["requests"]
        if request["url"] == "/api/correction-benchmark/examples"
    )
    assert benchmark_request["body"] == {
        "original_text": "Synthetic original wording.",
        "intended_text": "Synthetic corrected wording.",
    }
    assert observed["original"]["cleaned"] == "Synthetic corrected wording."
    assert observed["original"]["requests"][-1]["body"]["outgoing_text"] == (
        "Synthetic original wording."
    )
    assert observed["original"]["requests"][-1]["body"]["outgoing_kind"] == "original"
    assert observed["failure"]["open"] is True
    assert observed["failure"]["cleaned"] == "Synthetic prepared wording."
    assert "was not added" in observed["failure"]["feedback"]
    assert observed["cancel"]["buttonDisabledAfterSuccess"] is False
    assert observed["prepared"]["buttonDisabledAfterSuccess"] is True
    assert observed["prepared"]["buttonDisabledAfterNewCleaned"] is False
    assert observed["original"]["buttonDisabledAfterSuccess"] is True
    assert observed["failure"]["buttonDisabledAfterSuccess"] is False
    assert "Example added to private corpus" in observed["prepared"]["outgoingLabelAfterSuccess"]


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
