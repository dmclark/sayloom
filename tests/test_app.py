import asyncio
import fcntl
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import local_text.app as app_module
from local_text.app import PAID_DATA_ACKNOWLEDGEMENT, STATIC_VERSION, create_app
from local_text.cleanup import (
    CleanupService,
    ProviderMalformedResponseError,
    ProviderOutput,
    SequentialCleanupProvider,
)
from local_text.config import Profile, Settings, load_settings
from local_text.prompts import effective_system_prompt


def test_health_reports_development_profile(initialized_settings: Settings) -> None:
    client = TestClient(create_app(initialized_settings))

    response = client.get("/health")

    assert response.status_code == 200
    health = response.json()
    cleanup_configuration = health.pop("cleanup_configuration")
    evidence_collection = health.pop("evidence_collection")
    assert health == {
        "status": "ok",
        "profile": "development",
        "development_state": None,
        "database": {
            "state": "current",
            "current_revision": "0004_personal_corrections_foundation",
            "expected_revision": "0004_personal_corrections_foundation",
        },
        "configuration_error": None,
    }
    assert cleanup_configuration["status"] == "unavailable"
    assert cleanup_configuration["available"] is False
    assert cleanup_configuration["routes"] == []
    assert cleanup_configuration["validation_error"] is None
    assert evidence_collection == {
        "ready": False,
        "reason": "unconfigured",
        "package_version": None,
        "contract_version": None,
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
        "expected_revision": "0004_personal_corrections_foundation",
    }


def test_default_cleanup_timeout_allows_provider_generation_latency() -> None:
    assert Settings(Profile.DEVELOPMENT).cleanup_timeout_seconds == 30


def test_provider_traffic_diagnostics_require_an_actively_locked_development_session(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "provider-traffic"
    marker.write_text(str(os.getpid()))

    development = Settings(
        Profile.DEVELOPMENT,
        provider_traffic_diagnostics_file=marker,
    )
    release = Settings(
        Profile.RELEASE,
        provider_traffic_diagnostics_file=marker,
    )

    assert development.provider_traffic_diagnostics_enabled() is False
    assert release.provider_traffic_diagnostics_enabled() is False
    with marker.open() as session:
        fcntl.flock(session, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert development.provider_traffic_diagnostics_enabled() is True
        assert release.provider_traffic_diagnostics_enabled() is False
    assert development.provider_traffic_diagnostics_enabled() is False
    marker.write_text("reused-current-pid-content")
    assert development.provider_traffic_diagnostics_enabled() is False


def test_development_page_identifies_development_brand(initialized_settings: Settings) -> None:
    client = TestClient(create_app(initialized_settings))

    response = client.get("/")

    assert response.status_code == 200
    assert "<title>Sayloom Development</title>" in response.text
    assert 'aria-label="Development profile"' in response.text
    assert 'id="original-text"' in response.text
    assert 'id="prepared-text"' in response.text
    assert f'href="/static/app.css?v={STATIC_VERSION}"' in response.text
    assert f'src="/static/app.js?v={STATIC_VERSION}"' in response.text
    assert 'id="cleanup-status"' in response.text
    assert 'class="status-label"' not in response.text
    assert 'id="cancel-cleanup"' not in response.text
    assert 'id="active-prompt-selector"' not in response.text
    assert 'id="prompt-manager"' not in response.text
    assert 'id="save-prompt"' not in response.text
    assert 'id="workspace-resizer"' in response.text
    assert 'id="select-prepared"' in response.text
    assert 'id="select-original"' in response.text
    assert '<h2>Prepared</h2>' in response.text
    assert '>Prepared</button>' in response.text
    assert 'aria-label="Resize Original and Prepared fields"' in response.text
    assert 'aria-valuetext="Original 55 percent, Prepared 45 percent"' in response.text
    assert '<h2>Cleaned</h2>' not in response.text
    assert '>Cleaned</button>' not in response.text
    assert 'id="toggle-original"' not in response.text
    assert 'id="layout-stacked"' in response.text
    assert 'id="layout-side-by-side"' in response.text
    assert 'id="maximize-original"' in response.text
    assert 'id="maximize-prepared"' in response.text
    assert 'id="toggle-sidebar"' in response.text
    assert 'id="draft-preparation-mode"' in response.text
    assert 'id="default-preparation-mode"' in response.text
    assert '<option value="off">Off — Keep Original</option>' in response.text
    assert (
        '<option value="conservative">Conservative — Preserve my words</option>'
        in response.text
    )
    assert (
        '<option value="smart">Smart — Repair likely wrong words</option>' in response.text
    )
    assert 'id="cleanup-enabled"' not in response.text
    assert "Clean automatically" not in response.text
    assert "Experimental — not yet evidence-backed" in response.text
    assert "Learn about the pilot" in response.text
    assert "Enrollment is not currently open." in response.text
    assert 'id="run-smart-correction"' not in response.text
    assert 'id="nav-settings"' in response.text
    assert response.text.index('id="correction-settings-title"') < response.text.index(
        'id="targets-title"'
    )
    assert 'id="smart-task-context"' in response.text
    assert "Task context · this request only" in response.text
    assert 'id="smart-repair-review"' in response.text
    assert 'id="smart-repair-list"' in response.text
    assert 'id="copy-outgoing"' in response.text
    assert (
        "Editing Intended records the correct meaning; it does not replace Original or directly "
        "determine Prepared."
        in response.text
    )
    for disposition in (
        "ready_as_is",
        "presentation_cleanup_needed",
        "edit_intended",
        "not_voiceitt",
        "cannot_reliably_reconstruct",
        "exclude",
    ):
        option = response.text.split(f'<option value="{disposition}">', maxsplit=1)[1].split(
            "</option>", maxsplit=1
        )[0]
        assert " — " in option
    assert (
        "Select a repair to inspect its corresponding wording and sentence context."
        in response.text
    )
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
    assert 'id="layout-stacked"' in control_rail
    assert 'id="layout-side-by-side"' in control_rail
    assert 'id="run-cleanup"' in control_rail
    assert 'id="clear-text"' in control_rail
    original_panel = response.text.split('class="text-panel original-panel"', maxsplit=1)[
        1
    ].split("</article>", maxsplit=1)[0]
    assert 'class="panel-footer original-panel-footer"' in original_panel
    assert 'id="maximize-original"' in original_panel
    assert 'id="run-cleanup"' not in original_panel
    assert 'id="clear-text"' not in original_panel
    prepared_panel = response.text.split('class="text-panel prepared-panel"', maxsplit=1)[
        1
    ].split("</article>", maxsplit=1)[0]
    assert "readonly" in prepared_panel
    assert 'id="cleanup-disclosure"' in prepared_panel
    assert 'id="cleanup-disclosure"' not in response.text.split(
        'class="outgoing-strip"', maxsplit=1
    )[1]


def test_obsolete_capture_interfaces_are_absent(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    page = client.get("/")
    script = client.get("/static/app.js")
    configuration = client.get("/api/config")
    removed_smart_endpoint = client.post(
        "/api/correction-benchmark/examples",
        json={
            "original_text": "Synthetic original wording.",
            "intended_text": "Synthetic intended wording.",
        },
    )

    assert page.status_code == 200
    assert 'id="correct-and-add-example"' not in page.text
    assert 'id="benchmark-capture-dialog"' not in page.text
    assert 'id="save-evaluation-case"' not in page.text
    assert 'id="evaluation-manager"' not in page.text
    assert 'id="nav-evaluation"' not in page.text
    assert "/api/correction-benchmark/examples" not in script.text
    assert "/api/evaluation" not in script.text
    assert "evaluation_configuration" not in configuration.json()
    assert "correction_benchmark_configuration" not in configuration.json()
    assert removed_smart_endpoint.status_code == 404
    assert client.get("/api/evaluation/cases").status_code == 404
    assert client.post("/api/evaluation/cases", json={}).status_code == 404


def test_status_errors_use_one_accessible_privacy_safe_dialog(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    page = client.get("/").text
    script = client.get("/static/app.js").text
    stylesheet = client.get("/static/app.css").text

    prepared_header = page.split(
        'class="text-panel prepared-panel"', maxsplit=1
    )[1].split("</header>", maxsplit=1)[0]
    outgoing = page.split('class="outgoing-strip"', maxsplit=1)[1].split(
        "</section>", maxsplit=1
    )[0]

    assert 'id="cleanup-status"' in prepared_header
    assert "Cleanup unavailable</button>" in prepared_header
    assert '<button id="retry-cleanup"' in prepared_header
    assert "Retry cleanup\n" in prepared_header
    assert 'id="cleanup-status"' not in outgoing
    assert 'id="retry-cleanup"' not in outgoing
    assert '<span id="outgoing-kind"' in page
    assert '<button id="publication-state"' in page
    assert page.count('<dialog id="error-details-dialog"') == 1
    assert page.count('aria-controls="error-details-dialog"') == 2
    assert 'id="cleanup-error"' not in page
    assert 'id="publication-error"' not in page
    assert "Copy details" in page
    assert 'elements.cleanupStatus.addEventListener("click"' in script
    assert 'elements.publication.addEventListener("click"' in script
    assert "elements.errorDialog.showModal()" in script
    assert "navigator.clipboard.writeText" in script
    assert 'id="copy-outgoing-state" class="visually-hidden"' in page
    assert ">Copy</button>" in page
    assert "Copy outgoing" not in page
    assert 'id="publication-state"' in page and "disabled hidden" in page
    assert 'elements.publication.hidden = nextState !== "error"' in script

    retry_handler = script.split(
        'elements.retryCleanup.addEventListener("click"', maxsplit=1
    )[1].split("});", maxsplit=1)[0]
    assert "runCleanup()" in retry_handler
    assert 'failedCorrectionMode === "smart"' in retry_handler
    assert 'applyDraftPreparationMode("conservative")' in retry_handler
    assert "copyOutgoing" not in retry_handler
    assert "requestEvidenceJudgment" not in retry_handler
    assert "publishNow" not in retry_handler

    assert 'id="cleanup-result"' in page
    assert "Prepared with backup model" in script
    attempt_renderer = script.split("function renderCleanupAttempts", maxsplit=1)[1].split(
        "function validateSmartRepairs", maxsplit=1
    )[0]
    assert all(
        field in attempt_renderer
        for field in ("provider", "model", "route_index", "outcome")
    )
    assert all(
        private_field not in attempt_renderer
        for private_field in (
            "original_text",
            "prepared_text",
            "task_context",
            "prompt",
            "credential",
            "payload",
            "provider_code",
            "http_status",
        )
    )

    feedback = script.split("function showCopyFeedback", maxsplit=1)[1].split(
        "async function copyOutgoing", maxsplit=1
    )[0]
    assert 'elements.copyOutgoing.textContent = "Copy"' in feedback
    assert 'elements.copyOutgoingState.textContent = ""' in feedback
    assert "1_500" in feedback

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
        cleanup_route_attempt_seconds=(18.0, 12.0),
        database_path=initialized_settings.database_path,
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/config")

    configuration = response.json()
    cleanup_configuration = configuration.pop("cleanup_configuration")
    evidence_collection = configuration.pop("evidence_collection")
    assert configuration == {
        "display_name": "Sayloom Development",
        "profile": "development",
        "development_state": None,
        "preparation_default": "conservative",
        "cleanup_available": True,
        "cleanup_model": "gemini-3.5-flash",
    }
    assert cleanup_configuration["status"] == "gemini_only"
    assert cleanup_configuration["routes"] == [
        {"provider": "gemini", "model": "gemini-3.5-flash"},
        {"provider": "gemini", "model": "gemini-2.5-flash"},
    ]
    assert cleanup_configuration["paid_data_acknowledgement"] is None
    assert evidence_collection["ready"] is False
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
        "cleanup_route_attempt_seconds": (18.0, 12.0),
        "database_path": initialized_settings.database_path,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize("mode", ["conservative", "smart"])
def test_acknowledged_cross_provider_route_is_exact_sanitized_and_falls_back_once(
    initialized_settings: Settings, monkeypatch, mode: str
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
                                "text": '{"prepared_text":"Synthetic source."}',
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
            "/api/cleanup",
            json={
                "original_text": "synthetic source",
                "enabled": True,
                "correction_mode": mode,
            },
        )
        provider = client.app.state.cleanup_service.provider
        assert isinstance(provider, SequentialCleanupProvider)
        assert [route.quota_group_id for route in provider.routes] == [
            "gemini-paid-project",
            "openai-paid-project",
        ]
        assert provider.total_budget_seconds == 30
        assert provider.partition_schedule.route_allocations_seconds == (18.0, 12.0)

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
    assert cleanup_configuration["disclosure"]["corpus"] == (
        "Routine cleanup does not retain Original, Prepared, or provider payloads."
    )
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


def test_configured_routes_without_a_partition_schedule_fail_configuration(
    initialized_settings: Settings, monkeypatch
) -> None:
    calls = 0

    def unexpected_client(_timeout: float):
        nonlocal calls
        calls += 1
        raise AssertionError("missing allocation must not create a provider client")

    monkeypatch.setattr(app_module, "_new_provider_client", unexpected_client)
    settings = Settings(
        Profile.DEVELOPMENT,
        gemini_api_key="synthetic-key",
        database_path=initialized_settings.database_path,
    )

    with TestClient(create_app(settings)) as client:
        configuration = client.get("/health").json()["cleanup_configuration"]

    assert configuration["status"] == "invalid"
    assert configuration["available"] is False
    assert configuration["routes"] == []
    assert configuration["validation_error"] == "route_attempt_allocations_required"
    assert calls == 0


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
            "/api/cleanup", json={"original_text": "synthetic source", "enabled": True}
        )

    configuration = configuration_response.json()["cleanup_configuration"]
    assert configuration["status"] == "invalid"
    assert configuration["available"] is False
    assert configuration["routes"] == []
    assert configuration["validation_error"] == "paid_data_acknowledgement_required"
    assert result.json()["status"] == "disabled"
    assert result.json()["prepared_text"] == "synthetic source"
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
        "LOCAL_TEXT_CLEANUP_ROUTE_ATTEMPT_SECONDS",
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
        "LOCAL_TEXT_CLEANUP_ROUTE_ATTEMPT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "ambient-gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai-key")
    monkeypatch.setenv("LOCAL_TEXT_CLEANUP_ROUTE_ATTEMPT_SECONDS", "18,12")
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
        prepared_text = f"Synthetic source {'one' if calls == 1 else 'two'}."
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": json.dumps({"prepared_text": prepared_text})}
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
        cleanup_route_attempt_seconds=(18.0, 12.0),
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
        assert provider.partition_schedule.route_allocations_seconds == (18.0, 12.0)
        assert {route.quota_group_id for route in provider.routes} == {"gemini-default"}
        for source in ("synthetic source one", "synthetic source two"):
            response = client.post(
                "/api/cleanup", json={"original_text": source, "enabled": True}
            )
            assert response.status_code == 200
            assert response.json()["status"] == "prepared"
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
                    {"content": {"parts": [{"text": '{"prepared_text":"Synthetic source."}'}]}}
                ]
            },
        )

    provider_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(app_module, "_new_provider_client", lambda _timeout: provider_client)
    settings = Settings(
        Profile.DEVELOPMENT,
        gemini_api_key="synthetic-key",
        cleanup_route_attempt_seconds=(18.0, 12.0),
        database_path=initialized_settings.database_path,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/cleanup", json={"original_text": "synthetic source", "enabled": True}
        )

    assert response.status_code == 200
    assert response.json()["status"] == "prepared"
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
        cleanup_route_attempt_seconds=(18.0, 12.0),
        database_path=initialized_settings.database_path,
    )

    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/cleanup", json={"original_text": "synthetic source", "enabled": True}
        )

    assert response.status_code == 200
    assert response.json()["prepared_text"] == "synthetic source"
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
        json={"original_text": "synthetic source text", "enabled": True},
    )

    assert response.status_code == 200
    assert response.json() == {
        "prepared_text": "synthetic source text",
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

        async def clean(self, original_text: str, system_prompt: str) -> ProviderOutput:
            assert original_text == "synthetic source text"
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
    assert "cleaned_text" not in response.json()
    assert response.json()["correction_mode"] == "smart"
    assert response.json()["status"] == "prepared"
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
        }
    ]


@pytest.mark.parametrize(
    (
        "original_text",
        "prepared_text",
        "operation",
        "reason_verb",
        "original_span",
        "prepared_span",
    ),
    [
        (
            "Send synthetic report now",
            "Send the synthetic report now.",
            "addition",
            "adds wording",
            {"start": 5, "end": 5, "text": ""},
            {"start": 5, "end": 8, "text": "the"},
        ),
        (
            "Send the extra synthetic report now",
            "Send the synthetic report now.",
            "removal",
            "removes wording",
            {"start": 9, "end": 14, "text": "extra"},
            {"start": 9, "end": 9, "text": ""},
        ),
        (
            "Send teh synthetic report now",
            "Send the synthetic report now.",
            "replacement",
            "replaces wording",
            {"start": 5, "end": 8, "text": "teh"},
            {"start": 5, "end": 8, "text": "the"},
        ),
    ],
)
def test_smart_cleanup_api_returns_every_server_derived_repair_operation(
    initialized_settings: Settings,
    original_text: str,
    prepared_text: str,
    operation: str,
    reason_verb: str,
    original_span: dict[str, object],
    prepared_span: dict[str, object],
) -> None:
    class Provider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, _original_text: str, _system_prompt: str) -> ProviderOutput:
            return ProviderOutput(prepared_text, self.provider_id, self.model, 3)

    response = TestClient(
        create_app(
            initialized_settings,
            CleanupService(Provider(), "test-model", timeout_seconds=1),
        )
    ).post(
        "/api/cleanup",
        json={"original_text": original_text, "correction_mode": "smart"},
    )

    assert response.status_code == 200
    repair = response.json()["lexical_repairs"][0]
    assert repair == {
        "operation": operation,
        "original_span": original_span,
        "prepared_span": prepared_span,
        "context": prepared_text if operation != "removal" else original_text,
        "queue_position": 1,
        "inspection_reason": (
            f"Prepared {reason_verb}; "
            "verify it matches the intended meaning."
        ),
    }


def test_conservative_cleanup_api_shape_remains_compatible(initialized_settings: Settings) -> None:
    response = TestClient(create_app(initialized_settings)).post(
        "/api/cleanup", json={"original_text": "synthetic source"}
    )

    assert response.status_code == 200
    assert response.json()["correction_mode"] == "conservative"
    assert "lexical_repairs" not in response.json()


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_code"),
    [
        ("bounded_rejection", "provider_error", "cleanup_output_rejected"),
        ("malformed", "provider_error", "cleanup_provider_malformed_response"),
        ("timeout", "timeout", "cleanup_timeout"),
    ],
)
def test_smart_cleanup_api_failures_leave_original_usable(
    initialized_settings: Settings,
    failure: str,
    expected_status: str,
    expected_code: str,
) -> None:
    original_text = "one two three four five six seven eight"

    class Provider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, _original_text: str, _system_prompt: str) -> ProviderOutput:
            if failure == "malformed":
                raise ProviderMalformedResponseError("private malformed payload")
            if failure == "timeout":
                await asyncio.sleep(0.05)
            return ProviderOutput(
                "nine ten eleven four five six seven eight",
                self.provider_id,
                self.model,
                3,
            )

    response = TestClient(
        create_app(
            initialized_settings,
            CleanupService(Provider(), "test-model", timeout_seconds=0.001),
        )
    ).post(
        "/api/cleanup",
        json={"original_text": original_text, "correction_mode": "smart"},
    )

    assert response.status_code == 200
    assert response.json()["prepared_text"] == original_text
    assert response.json()["lexical_repairs"] == []
    assert response.json()["status"] == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert "private malformed payload" not in response.text


def test_cleanup_endpoint_rejects_instruction_like_output_before_publication(
    initialized_settings: Settings,
) -> None:
    original_text = "Process the ASR article from today capture"
    rejected_output = (
        "Sure, I can help with that. Please provide the ASR article to process."
    )

    class Provider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, original_text: str, system_prompt: str) -> ProviderOutput:
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
        json={"original_text": original_text, "enabled": True},
    )

    assert cleanup.status_code == 200
    assert cleanup.json()["prepared_text"] == original_text
    assert cleanup.json()["status"] == "provider_error"
    assert cleanup.json()["error"]["code"] == "cleanup_output_rejected"
    assert rejected_output not in cleanup.text

    publication = client.put(
        "/api/outgoing-state",
        json={
            "cleanup_enabled": True,
            "original_text": original_text,
            "prepared_text": original_text,
            "outgoing_text": original_text,
            "outgoing_kind": "original",
            "status": "error",
        },
    )

    assert publication.status_code == 200
    assert publication.json()["outgoing_text"] == original_text
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

        async def clean(self, original_text: str, system_prompt: str) -> ProviderOutput:
            observed.append(system_prompt)
            return ProviderOutput(
                text=original_text,
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
        json={"original_text": "synthetic source text", "enabled": True},
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

        async def clean(self, original_text: str, system_prompt: str) -> ProviderOutput:
            observed.append(system_prompt)
            return ProviderOutput(
                text=original_text,
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
            "original_text": "synthetic source text",
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
            "original_text": "synthetic source text",
            "enabled": True,
            "prompt_version_id": 9999,
        },
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "prompt_version_not_found"


def test_active_draft_does_not_change_saved_preparation_default(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    update = {
        "cleanup_enabled": False,
        "original_text": "synthetic original text",
        "prepared_text": "synthetic original text",
        "outgoing_text": "synthetic original text",
        "outgoing_kind": "original",
        "status": "disabled",
    }

    assert client.put("/api/outgoing-state", json=update).status_code == 200

    restarted = TestClient(create_app(initialized_settings))
    assert restarted.get("/api/config").json()["preparation_default"] == "conservative"
    assert restarted.get("/api/outgoing-state").json()["cleanup_enabled"] is True


def test_preparation_default_is_durable_and_new_draft_snapshots_it(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    saved = client.put(
        "/api/preferences/preparation-default",
        json={"preparation_default": "smart"},
    )
    assert saved.status_code == 200
    assert saved.json() == {"preparation_default": "smart"}

    workspace_override = client.put(
        "/api/outgoing-state",
        json={
            "cleanup_enabled": True,
            "original_text": "synthetic original",
            "prepared_text": "Synthetic original.",
            "outgoing_text": "Synthetic original.",
            "outgoing_kind": "prepared",
            "status": "prepared",
            "correction_mode": "conservative",
        },
    )
    assert workspace_override.status_code == 200
    assert workspace_override.json()["correction_mode"] == "conservative"

    assert client.get("/api/outgoing-state").json()["correction_mode"] == "conservative"

    new_draft = client.delete("/api/outgoing-state")
    assert new_draft.json()["cleanup_enabled"] is True
    assert new_draft.json()["correction_mode"] == "smart"

    restarted = TestClient(create_app(initialized_settings))
    assert restarted.get("/api/config").json()["preparation_default"] == "smart"
    assert restarted.get("/api/outgoing-state").json()["correction_mode"] == "smart"

    invalid = client.put(
        "/api/preferences/preparation-default",
        json={"preparation_default": "polished"},
    )
    assert invalid.status_code == 422

    off = client.put(
        "/api/preferences/preparation-default",
        json={"preparation_default": "off"},
    )
    assert off.status_code == 200
    off_draft = client.delete("/api/outgoing-state").json()
    assert off_draft["cleanup_enabled"] is False
    assert off_draft["correction_mode"] == "conservative"


def test_outgoing_state_is_published_and_cleared_in_memory(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))
    update = {
        "cleanup_enabled": True,
        "original_text": "synthetic original text",
        "prepared_text": "Synthetic prepared text.",
        "outgoing_text": "Synthetic prepared text.",
        "outgoing_kind": "prepared",
        "status": "prepared",
    }

    published = client.put("/api/outgoing-state", json=update)

    assert published.status_code == 200
    expanded = {
        **update,
        "correction_mode": "conservative",
        "revision": 1,
    }
    assert published.json() == expanded
    assert client.get("/api/outgoing-state").json() == expanded

    cleared = client.delete("/api/outgoing-state")
    assert cleared.status_code == 200
    assert cleared.json()["outgoing_text"] == ""
    assert cleared.json()["outgoing_kind"] == "empty"
    assert cleared.json()["original_text"] == ""
    assert cleared.json()["prepared_text"] == ""
    assert "raw_text" not in cleared.json()
    assert "cleaned_text" not in cleared.json()
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
            "status": "prepared",
            "correction_mode": "smart",
        },
    )

    assert response.status_code == 200
    assert response.json()["original_text"] == "synthetic original"
    assert response.json()["prepared_text"] == "Synthetic original."
    assert "raw_text" not in response.json()
    assert "cleaned_text" not in response.json()
    assert response.json()["outgoing_kind"] == "prepared"
    assert response.json()["correction_mode"] == "smart"

    legacy_cleanup = client.post(
        "/api/cleanup",
        json={"raw_text": "synthetic original", "enabled": True},
    )
    legacy_outgoing = client.put(
        "/api/outgoing-state",
        json={
            "cleanup_enabled": True,
            "original_text": "synthetic original",
            "prepared_text": "Synthetic original.",
            "raw_text": "synthetic original",
            "outgoing_text": "Synthetic original.",
            "outgoing_kind": "prepared",
            "status": "prepared",
        },
    )

    assert legacy_cleanup.status_code == 422
    assert legacy_outgoing.status_code == 422


def test_outgoing_state_rejects_text_not_present_in_either_editor(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    response = client.put(
        "/api/outgoing-state",
        json={
            "cleanup_enabled": True,
            "original_text": "current original",
            "prepared_text": "current prepared",
            "outgoing_text": "stale text",
            "outgoing_kind": "prepared",
            "status": "prepared",
        },
    )

    assert response.status_code == 422

    mismatched_source = client.put(
        "/api/outgoing-state",
        json={
            "cleanup_enabled": True,
            "original_text": "current original",
            "prepared_text": "current prepared",
            "outgoing_text": "current original",
            "outgoing_kind": "prepared",
            "status": "prepared",
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
    assert "selectedPromptVersionId" not in script.text
    assert "originalOutgoingOverride = true" in script.text
    assert "originalOutgoingOverride = false" in script.text
    assert "Using Original — Replacement Prepared pending" in script.text
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
    assert "toggleMaximizedPane" in script.text
    assert "WORKSPACE_PREFERENCES_KEY" in script.text
    assert 'window.matchMedia("(max-width: 980px)")' in script.text
    assert "correction_mode: correctionMode" in script.text
    assert "task_context: taskContext" in script.text
    assert 'fetch("/api/preferences/preparation-default"' in script.text
    assert 'elements.draftPreparationMode.addEventListener("change"' in script.text
    assert "requestDraftRevision !== draftRevision" in script.text
    assert "correctionMode !== effectiveCorrectionMode()" in script.text
    assert "renderCorrectionMode();" in script.text
    assert 'elements.prepared.addEventListener("input"' not in script.text
    run_cleanup = script.text.split("async function runCleanup(", maxsplit=1)[1].split(
        "function scheduleCleanup()", maxsplit=1
    )[0]
    scheduled_cleanup = script.text.split("function scheduleCleanup()", maxsplit=1)[1].split(
        "function originalIsFullySelected", maxsplit=1
    )[0]
    assert 'if (draftPreparationMode === "off")' in run_cleanup
    assert 'if (draftPreparationMode === "off")' in scheduled_cleanup
    assert '(status === "prepared" || status === "unchanged")' in script.text
    initialization = script.text.split("async function initialize()", maxsplit=1)[1].split(
        "initialize();", maxsplit=1
    )[0]
    assert "clearPublishedState()" in initialization
    assert 'elements.original.value = "";' not in initialization
    assert 'elements.prepared.value = "";' in initialization
    assert 'fetch("/api/outgoing-state")' not in initialization
    assert "publishNow();" not in initialization


def test_browser_sends_ephemeral_task_context_and_discards_stale_smart_state(
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
    this.hidden = false;
    this.dataset = {};
    this.options = [{ textContent: "" }];
    this.style = { setProperty() {} };
    this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
    this.lastElementChild = { textContent: "" };
    this.listeners = {};
    this.selectionStart = 0;
    this.selectionEnd = 0;
  }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  async dispatch(type, event = {}) {
    event.target ||= this;
    event.preventDefault ||= () => {};
    for (const callback of this.listeners[type] || []) await callback(event);
  }
  setAttribute() {}
  getAttribute(name) { return name === "aria-valuenow" ? "65" : null; }
  removeAttribute() {}
  append() {}
  setPointerCapture() {}
  setSelectionRange() {}
  getBoundingClientRect() { return { top: 0, height: 100 }; }
  focus() { document.activeElement = this; }
  close() {}
}

const elements = {};
const document = {
  activeElement: null,
  querySelector(selector) { return elements[selector] ||= new Element(); },
  createElement() { return new Element(); },
  addEventListener() {},
};
const cleanupRequests = [];
const cleanupResolvers = [];
const response = (body) => ({ ok: true, status: 200, json: async () => body });
const fetch = (url, options = {}) => {
  if (url === "/api/config") return Promise.resolve(response({
    preparation_default: "smart",
    cleanup_configuration: { status: "unavailable", routes: [], disclosure: {} },
  }));
  if (url === "/api/prompts") return Promise.resolve(response({
    versions: [], active_prompt_version_id: null,
  }));
  if (url === "/api/outgoing-state") return Promise.resolve(response({ revision: 1 }));
  if (url === "/api/cleanup") {
    cleanupRequests.push(JSON.parse(options.body));
    return new Promise((resolve) => cleanupResolvers.push(resolve));
  }
  throw new Error(`Unexpected request: ${url}`);
};
const window = {
  clearTimeout, setTimeout,
  requestAnimationFrame(callback) { callback(); },
  addEventListener() {},
};
const context = { document, window, fetch, AbortController, Promise, console };

async function settle() {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
}

(async () => {
  vm.runInNewContext(process.argv[1], context);
  await settle();
  const original = elements["#original-text"];
  const prepared = elements["#prepared-text"];
  const taskContext = elements["#smart-task-context"];
  original.value = "send teh report";
  await original.dispatch("input", { isTrusted: true });
  taskContext.value = "First transient context";
  const staleRun = elements["#run-cleanup"].dispatch("click");
  await settle();
  taskContext.value = "Current transient context";
  const currentRun = elements["#run-cleanup"].dispatch("click");
  await settle();
  cleanupResolvers[1](response({
    prepared_text: "Send the report.", status: "prepared", lexical_repairs: [{
      operation: "replacement",
      original_span: { start: 5, end: 8, text: "teh" },
      prepared_span: { start: 5, end: 8, text: "the" },
      context: "Send the report.", queue_position: 1,
      inspection_reason: "Prepared replaces wording; verify meaning.",
    }],
  }));
  await currentRun;
  cleanupResolvers[0](response({
    prepared_text: "STALE PREPARED", status: "prepared",
    lexical_repairs: [{ operation: "replacement" }],
  }));
  await staleRun;
  process.stdout.write(JSON.stringify({
    cleanupRequests,
    prepared: prepared.value,
    repairCount: prepared.dataset.repairCount,
    taskContextHidden: elements["#smart-task-context-field"].hidden,
  }));
})().catch((error) => { process.stderr.write(error.stack); process.exit(1); });
"""

    result = subprocess.run(
        ["node", "-e", harness, script],
        check=True,
        capture_output=True,
        text=True,
    )
    observed = json.loads(result.stdout)

    assert [request["task_context"] for request in observed["cleanupRequests"]] == [
        "First transient context",
        "Current transient context",
    ]
    assert observed["prepared"] == "Send the report."
    assert observed["repairCount"] == "1"
    assert observed["taskContextHidden"] is False


def test_browser_applies_active_preparation_mode_independently_of_saved_default(
    initialized_settings: Settings,
) -> None:
    script = TestClient(create_app(initialized_settings)).get("/static/app.js").text
    harness = r"""
const vm = require("vm");

class Element {
  constructor() {
    this.value = ""; this.checked = true; this.disabled = false; this.hidden = false;
    this.readOnly = false; this.open = false; this.dataset = {}; this.listeners = {};
    this.children = []; this.attributes = {}; this.textContent = "";
    this.selectionStart = 0; this.selectionEnd = 0;
    this.lastElementChild = { textContent: "" }; this.style = { setProperty() {} };
    this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
  }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  async dispatch(type, event = {}) {
    event.target ||= this; event.preventDefault ||= () => {};
    for (const callback of this.listeners[type] || []) await callback(event);
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || (name === "aria-valuenow" ? "55" : null); }
  removeAttribute(name) { delete this.attributes[name]; }
  toggleAttribute() {}
  append(...children) { this.children.push(...children); }
  setPointerCapture() {}
  setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; }
  getBoundingClientRect() { return { top: 0, left: 0, width: 100, height: 100 }; }
  focus() { document.activeElement = this; }
  close() { this.open = false; }
  showModal() { this.open = true; }
  reportValidity() { return true; }
  querySelectorAll() { return []; }
  querySelector() { return null; }
}
const elements = {};
const document = {
  activeElement: null,
  querySelector(selector) { return elements[selector] ||= new Element(); },
  createElement() { return new Element(); },
  addEventListener() {},
};
const requests = [];
const response = (body, status = 200) => ({
  ok: status >= 200 && status < 300, status, json: async () => body,
});
const fetch = async (url, options = {}) => {
  const body = options.body ? JSON.parse(options.body) : null;
  requests.push({ url, method: options.method || "GET", body });
  if (url === "/api/config") return response({
    preparation_default: "conservative",
    cleanup_configuration: { status: "unavailable", routes: [], disclosure: {} },
    evidence_collection: { ready: false },
  });
  if (url === "/api/preferences/preparation-default") {
    return response({ preparation_default: body.preparation_default });
  }
  if (url === "/api/cleanup") return response({
    prepared_text: body.original_text, status: "unchanged", lexical_repairs: [],
  });
  if (url === "/api/outgoing-state") return response({ revision: 1 });
  throw new Error(`Unexpected request: ${url}`);
};
const window = {
  clearTimeout() {}, setTimeout() { return 1; },
  requestAnimationFrame(callback) { callback(); }, addEventListener() {},
  matchMedia() { return { matches: false, addEventListener() {} }; },
};
const context = {
  document, window, fetch, AbortController, Promise, console,
  navigator: { clipboard: {} },
};
const settle = async () => {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
};

(async () => {
  vm.runInNewContext(process.argv[1], context); await settle();
  const original = elements["#original-text"];
  const defaultMode = elements["#default-preparation-mode"];
  const draftMode = elements["#draft-preparation-mode"];
  const runCleanup = elements["#run-cleanup"];

  original.value = "First draft";
  await original.dispatch("input", { isTrusted: true });
  await runCleanup.dispatch("click"); await settle();

  defaultMode.value = "smart";
  await defaultMode.dispatch("change"); await settle();
  const cleanupCountAfterSave = requests.filter((item) => item.url === "/api/cleanup").length;

  original.value = "First draft edited";
  await original.dispatch("input", { isTrusted: true });
  await runCleanup.dispatch("click"); await settle();

  draftMode.value = "smart";
  await draftMode.dispatch("change"); await settle();
  const smartMode = {
    selected: draftMode.value,
    disclosureHidden: elements["#smart-mode-disclosure"].hidden,
    taskContextHidden: elements["#smart-task-context-field"].hidden,
  };

  draftMode.value = "off";
  await draftMode.dispatch("change"); await settle();
  const offMode = {
    prepared: elements["#prepared-text"].value,
    outgoing: elements["#outgoing-kind"].textContent,
  };

  elements["#smart-task-context"].value = "Stale context from the previous Original";
  original.selectionStart = 0; original.selectionEnd = original.value.length;
  await original.dispatch("beforeinput", { isTrusted: true });
  original.value = "Replacement draft";
  await original.dispatch("input", { isTrusted: true });
  await runCleanup.dispatch("click"); await settle();

  process.stdout.write(JSON.stringify({
    cleanupCountAfterSave,
    modes: requests.filter((item) => item.url === "/api/cleanup")
      .map((item) => item.body.correction_mode),
    promptOverrides: requests.filter((item) => item.url === "/api/cleanup")
      .map((item) => Object.hasOwn(item.body, "prompt_version_id")),
    promptHistoryRequested: requests.some((item) => item.url === "/api/prompts"),
    replacementCarriedTaskContext: Object.hasOwn(
      requests.filter((item) => item.url === "/api/cleanup").at(-1).body,
      "task_context",
    ),
    smartMode, offMode,
    replacementMode: draftMode.value,
    savedDefault: defaultMode.value,
  }));
})().catch((error) => { process.stderr.write(error.stack); process.exit(1); });
"""

    result = subprocess.run(
        ["node", "-e", harness, script], check=True, capture_output=True, text=True
    )
    observed = json.loads(result.stdout)

    assert observed == {
        "cleanupCountAfterSave": 1,
        "modes": ["conservative", "conservative", "smart", "smart"],
        "promptOverrides": [False, False, False, False],
        "promptHistoryRequested": False,
        "replacementCarriedTaskContext": False,
        "smartMode": {
            "selected": "smart",
            "disclosureHidden": False,
            "taskContextHidden": False,
        },
        "offMode": {
            "prepared": "",
            "outgoing": "Using Original — Cleanup disabled",
        },
        "replacementMode": "smart",
        "savedDefault": "smart",
    }


def test_browser_failed_smart_recovery_uses_latest_original_and_safe_attempt_details(
    initialized_settings: Settings,
) -> None:
    script = TestClient(create_app(initialized_settings)).get("/static/app.js").text
    harness = r"""
const vm = require("vm");

class Element {
  constructor() {
    this.value = ""; this.checked = true; this.disabled = false; this.hidden = false;
    this.open = false; this.dataset = {}; this.listeners = {}; this.children = [];
    this.attributes = {}; this.textContent = ""; this.selectionStart = 0; this.selectionEnd = 0;
    this.lastElementChild = { textContent: "" }; this.style = { setProperty() {} };
    this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
  }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  async dispatch(type, event = {}) {
    event.target ||= this; event.preventDefault ||= () => {};
    for (const callback of this.listeners[type] || []) await callback(event);
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || (name === "aria-valuenow" ? "55" : null); }
  removeAttribute(name) { delete this.attributes[name]; }
  toggleAttribute() {}
  append(...children) { this.children.push(...children); }
  setPointerCapture() {}
  setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; }
  getBoundingClientRect() { return { top: 0, left: 0, width: 100, height: 100 }; }
  focus() { document.activeElement = this; }
  close() { this.open = false; }
  showModal() { this.open = true; }
  reportValidity() { return true; }
  querySelectorAll() { return []; }
  querySelector() { return null; }
}
const elements = {};
const document = {
  activeElement: null,
  querySelector(selector) { return elements[selector] ||= new Element(); },
  createElement() { return new Element(); },
  addEventListener() {},
};
const cleanupRequests = [];
const publications = [];
let holdConservative = false;
let resolveConservative;
let primarySuccess = false;
const response = (body) => ({ ok: true, status: 200, json: async () => body });
const fetch = async (url, options = {}) => {
  if (url === "/api/config") return response({
    preparation_default: "smart",
    cleanup_configuration: { status: "unavailable", routes: [], disclosure: {} },
    evidence_collection: { ready: false },
  });
  if (url === "/api/cleanup") {
    const body = JSON.parse(options.body);
    cleanupRequests.push(body);
    if (body.correction_mode === "smart") return response({
      prepared_text: body.original_text, status: "provider_error",
      provider: "test", model: "model-a",
      lexical_repairs: [], attempts: [{
        provider: "provider-a", model: "model-a", route_index: 0, outcome: "failure",
        unsafe_provider_text: "PRIVATE PROVIDER PAYLOAD",
      }], error: {
        code: "cleanup_provider_error", message: "The provider failed.",
        retry_action: "Retry correction or continue with Original.", http_status: 503,
      },
    });
    if (holdConservative) {
      return await new Promise((resolve) => { resolveConservative = () => resolve(response({
        prepared_text: `${body.original_text} stale`, status: "prepared",
        provider: "provider-b", model: "model-b", attempts: [{
          provider: "provider-b", model: "model-b", route_index: 0, outcome: "success",
        }],
      })); });
    }
    if (primarySuccess) return response({
      prepared_text: `${body.original_text} primary`, status: "prepared",
      provider: "provider-a", model: "model-a", attempts: [{
        provider: "provider-a", model: "model-a", route_index: 0, outcome: "success",
      }],
    });
    return response({
      prepared_text: `${body.original_text} recovered`, status: "prepared",
      provider: "provider-b", model: "model-b", attempts: [
        { provider: "provider-a", model: "model-a", route_index: 0, outcome: "failure" },
        { provider: "provider-b", model: "model-b", route_index: 1, outcome: "success" },
      ],
    });
  }
  if (url === "/api/outgoing-state") {
    if ((options.method || "GET") === "PUT") publications.push(JSON.parse(options.body));
    return response({ revision: publications.length + 1 });
  }
  throw new Error(`Unexpected request: ${url}`);
};
const window = {
  clearTimeout() {}, setTimeout() { return 1; },
  requestAnimationFrame(callback) { callback(); }, addEventListener() {},
  matchMedia() { return { matches: false, addEventListener() {} }; },
};
const context = {
  document, window, fetch, AbortController, Promise, console,
  navigator: { clipboard: {} },
};
const settle = async () => {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
};

(async () => {
  vm.runInNewContext(process.argv[1], context); await settle();
  elements["#original-text"].value = "Original one";
  await elements["#original-text"].dispatch("input", { isTrusted: true });
  await elements["#run-cleanup"].dispatch("click"); await settle();

  const smartFailure = {
    cleanupDetailsVisible: !elements["#cleanup-recovery"].hidden,
    recoveryLabel: elements["#retry-cleanup"].textContent,
    prepared: elements["#prepared-text"].value,
    outgoing: elements["#outgoing-kind"].textContent,
    details: elements["#cleanup-attempt-list"].children.map((item) => item.textContent),
  };

  holdConservative = true;
  await elements["#retry-cleanup"].dispatch("click"); await settle();
  elements["#original-text"].value = "Original two";
  await elements["#original-text"].dispatch("input", { isTrusted: true });
  resolveConservative(); await settle();
  const stale = {
    prepared: elements["#prepared-text"].value,
    outgoing: elements["#outgoing-kind"].textContent,
    attemptsHidden: elements["#cleanup-result"].hidden,
  };

  holdConservative = false;
  elements["#draft-preparation-mode"].value = "smart";
  await elements["#draft-preparation-mode"].dispatch("change"); await settle();
  await elements["#retry-cleanup"].dispatch("click"); await settle();
  const backup = {
    mode: elements["#draft-preparation-mode"].value,
    prepared: elements["#prepared-text"].value,
    outgoing: elements["#outgoing-kind"].textContent,
    status: elements["#cleanup-result-status"].textContent,
    details: elements["#cleanup-attempt-list"].children.slice(-2).map((item) => item.textContent),
  };
  await elements["#select-prepared"].dispatch("click"); await settle();

  primarySuccess = true;
  await elements["#run-cleanup"].dispatch("click"); await settle();
  await elements["#select-prepared"].dispatch("click"); await settle();
  const primary = {
    prepared: elements["#prepared-text"].value,
    outgoing: elements["#outgoing-kind"].textContent,
    backupStatusHidden: elements["#cleanup-result-status"].hidden,
    details: elements["#cleanup-attempt-list"].children.slice(-1).map((item) => item.textContent),
  };

  process.stdout.write(JSON.stringify({
    smartFailure, stale, backup, primary, cleanupRequests,
    publishedOutgoing: publications.slice(-2).map((item) => ({
      original_text: item.original_text,
      prepared_text: item.prepared_text,
      outgoing_text: item.outgoing_text,
      outgoing_kind: item.outgoing_kind,
      status: item.status,
      correction_mode: item.correction_mode,
    })),
  }));
})().catch((error) => { process.stderr.write(error.stack); process.exit(1); });
"""

    result = subprocess.run(
        ["node", "-e", harness, script], check=True, capture_output=True, text=True
    )

    assert json.loads(result.stdout) == {
        "smartFailure": {
            "cleanupDetailsVisible": True,
            "recoveryLabel": "Try Conservative",
            "prepared": "Original one",
            "outgoing": "Using Original",
            "details": ["Route 1: provider-a · model-a — Failed"],
        },
        "stale": {
            "prepared": "",
            "outgoing": "Using Original — Replacement Prepared pending",
            "attemptsHidden": True,
        },
        "backup": {
            "mode": "conservative",
            "prepared": "Original two recovered",
            "outgoing": "Using Prepared",
            "status": "Prepared with backup model",
            "details": [
                "Route 1: provider-a · model-a — Failed",
                "Route 2: provider-b · model-b — Succeeded",
            ],
        },
        "primary": {
            "prepared": "Original two primary",
            "outgoing": "Using Prepared",
            "backupStatusHidden": True,
            "details": ["Route 1: provider-a · model-a — Succeeded"],
        },
        "cleanupRequests": [
            {"original_text": "Original one", "enabled": True, "correction_mode": "smart"},
            {
                "original_text": "Original one",
                "enabled": True,
                "correction_mode": "conservative",
            },
            {"original_text": "Original two", "enabled": True, "correction_mode": "smart"},
            {
                "original_text": "Original two",
                "enabled": True,
                "correction_mode": "conservative",
            },
            {
                "original_text": "Original two",
                "enabled": True,
                "correction_mode": "conservative",
            },
        ],
        "publishedOutgoing": [
            {
                "original_text": "Original two",
                "prepared_text": "Original two recovered",
                "outgoing_text": "Original two recovered",
                "outgoing_kind": "prepared",
                "status": "prepared",
                "correction_mode": "conservative",
            },
            {
                "original_text": "Original two",
                "prepared_text": "Original two primary",
                "outgoing_text": "Original two primary",
                "outgoing_kind": "prepared",
                "status": "prepared",
                "correction_mode": "conservative",
            },
        ],
    }


def test_browser_smart_repair_queue_selects_span_and_does_not_gate_outgoing(
    initialized_settings: Settings,
) -> None:
    script = TestClient(create_app(initialized_settings)).get("/static/app.js").text

    assert "function validateSmartRepairs" in script
    assert "function invalidateSmartRepairReview" in script
    assert "function selectSmartRepair" in script
    assert 'elements.smartTaskContext.addEventListener("input"' in script
    assert 'elements.activePromptSelector.addEventListener("change"' not in script
    assert 'elements.copyOutgoing.addEventListener("click"' in script
    assert "navigator.clipboard.writeText(outgoing.outgoing_text)" in script

    selected_state = script.split("function selectedOutgoingState()", maxsplit=1)[1].split(
        "function renderCountsAndSelection()", maxsplit=1
    )[0]
    assert "selectedSmartRepair" not in selected_state

    validation = script.split("function validateSmartRepairs", maxsplit=1)[1].split(
        "function invalidateSmartRepairReview", maxsplit=1
    )[0]
    for required in (
        "queue_position",
        "inspection_reason",
        "original_span",
        "prepared_span",
        "addition",
        "removal",
        "replacement",
    ):
        assert required in validation

    harness = r"""
const vm = require("vm");
class Element {
  constructor() {
    this.value = ""; this.checked = true; this.disabled = false; this.hidden = false;
    this.open = false; this.dataset = {}; this.options = [{ textContent: "" }]; this.children = [];
    this.listeners = {}; this.textContent = ""; this.attributes = {};
    this.style = { setProperty() {} };
    this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
    this.lastElementChild = { textContent: "" };
    this.selectionStart = 0; this.selectionEnd = 0;
  }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  async dispatch(type, event = {}) {
    event.target ||= this; event.preventDefault ||= () => {};
    for (const callback of this.listeners[type] || []) await callback(event);
  }
  append(...children) { this.children.push(...children); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || (name === "aria-valuenow" ? "65" : null); }
  removeAttribute(name) { delete this.attributes[name]; }
  toggleAttribute() {}
  setPointerCapture() {}
  setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; }
  getBoundingClientRect() { return { top: 0, height: 100 }; }
  focus() { document.activeElement = this; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}
const elements = {};
const document = {
  activeElement: null,
  querySelector(selector) { return elements[selector] ||= new Element(); },
  createElement() { return new Element(); },
  addEventListener() {},
};
const publications = [];
const copied = [];
let malformed = false;
let cleanupRequests = 0;
const response = (body) => ({ ok: true, status: 200, json: async () => body });
const fetch = async (url, options = {}) => {
  if (url === "/api/config") return response({
    preparation_default: "smart",
    cleanup_configuration: { status: "unavailable", routes: [], disclosure: {} },
  });
  if (url === "/api/prompts") return response({ versions: [], active_prompt_version_id: null });
  if (url === "/api/outgoing-state") {
    if (options.body) publications.push(JSON.parse(options.body));
    return response({ revision: publications.length + 1 });
  }
  if (url === "/api/cleanup") {
    cleanupRequests += 1;
    if (malformed) return response({
      prepared_text: "unlisted lexical change", status: "prepared", provider: "test",
      model: "model-b", lexical_repairs: [], attempts: [],
    });
    return response({
      prepared_text: "send the report now", status: "prepared", provider: "test", model: "model-a",
      lexical_repairs: [
        { operation: "replacement", original_span: { start: 5, end: 8, text: "teh" },
          prepared_span: { start: 5, end: 8, text: "the" }, context: "send the report now",
          queue_position: 1, inspection_reason: "Prepared replaces wording; verify meaning." },
        { operation: "addition", original_span: { start: 15, end: 15, text: "" },
          prepared_span: { start: 16, end: 19, text: "now" }, context: "send the report now",
          queue_position: 2, inspection_reason: "Prepared adds wording; verify meaning." },
      ], attempts: [],
    });
  }
  throw new Error(`Unexpected request: ${url}`);
};
const window = {
  clearTimeout() {}, setTimeout() { return 1; }, requestAnimationFrame(callback) { callback(); },
  addEventListener() {},
};
const navigator = { clipboard: { async writeText(text) { copied.push(text); } } };
const context = { document, window, navigator, fetch, AbortController, Promise, console };
async function settle() { await new Promise((resolve) => setImmediate(resolve)); }
(async () => {
  vm.runInNewContext(process.argv[1], context); await settle(); await settle();
  elements["#original-text"].value = "send teh report";
  await elements["#run-cleanup"].dispatch("click"); await settle();
  await elements["#select-prepared"].dispatch("click"); await settle();
  const queue = elements["#smart-repair-list"];
  const before = {
    hidden: elements["#smart-repair-review"].hidden,
    summary: elements["#smart-repair-summary"].textContent,
    outgoing: publications.at(-1).outgoing_text,
    queue: queue.children.map((item) => {
      const button = item.children[0];
      return [
        button.children[0].textContent,
        button.children[1].children[0].textContent,
        button.children[1].children[2].textContent,
      ];
    }),
  };
  await queue.children[0].children[0].dispatch("click");
  const inspected = {
    selection: [
      elements["#prepared-text"].selectionStart,
      elements["#prepared-text"].selectionEnd,
    ],
    context: elements["#smart-repair-context"].textContent,
    reason: elements["#smart-repair-reason"].textContent,
    selected: elements["#smart-repair-list"].children.some(
      (item) => item.children[0].attributes["aria-current"] === "true",
    ),
  };
  await elements["#copy-outgoing"].dispatch("click");
  elements["#smart-task-context"].value = "changed";
  await elements["#smart-task-context"].dispatch("input");
  malformed = true;
  await elements["#run-cleanup"].dispatch("click");
  const cleanupTrigger = elements["#cleanup-status"];
  await cleanupTrigger.dispatch("click");
  const malformedResult = {
    prepared: elements["#prepared-text"].value,
    status: elements["#outgoing-kind"].dataset.state,
    outgoing: elements["#outgoing-kind"].textContent,
    trigger: cleanupTrigger.textContent,
    recoveryHidden: elements["#cleanup-recovery"].hidden,
    dialogOpen: elements["#error-details-dialog"].open,
    dialogKind: elements["#error-details-dialog"].dataset.kind,
  };
  const invalidatedBeforeRetry = elements["#smart-repair-review"].hidden;
  malformed = false;
  const cleanupRequestsBeforeRetry = cleanupRequests;
  const copiedBeforeRetry = copied.length;
  await elements["#retry-cleanup"].dispatch("click"); await settle();
  process.stdout.write(JSON.stringify({
    before, inspected, copied, invalidated: invalidatedBeforeRetry,
    malformed: malformedResult,
    retry: {
      prepared: elements["#prepared-text"].value,
      outgoing: elements["#outgoing-kind"].textContent,
      cleanupRequestDelta: cleanupRequests - cleanupRequestsBeforeRetry,
      copiedDelta: copied.length - copiedBeforeRetry,
      recoveryHidden: elements["#cleanup-recovery"].hidden,
      dialogOpen: elements["#error-details-dialog"].open,
    },
  }));
})().catch((error) => { process.stderr.write(error.stack); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", harness, script], check=True, capture_output=True, text=True
    )
    observed = json.loads(result.stdout)

    assert observed == {
        "before": {
            "hidden": False,
            "summary": "2 repairs",
            "outgoing": "send the report now",
            "queue": [
                ["1 · replacement", "teh", "the"],
                ["2 · addition", "∅", "now"],
            ],
        },
        "inspected": {
            "selection": [5, 8],
            "context": "Context: send the report now",
            "reason": "Prepared replaces wording; verify meaning.",
            "selected": True,
        },
        "copied": ["send the report now"],
        "invalidated": True,
        "malformed": {
            "prepared": "send teh report",
            "status": "error",
            "outgoing": "Using Original",
            "trigger": "Cleanup unavailable",
            "recoveryHidden": False,
            "dialogOpen": True,
            "dialogKind": "cleanup",
        },
        "retry": {
            "prepared": "send the report now",
            "outgoing": "Using Prepared",
            "cleanupRequestDelta": 1,
            "copiedDelta": 0,
            "recoveryHidden": True,
            "dialogOpen": False,
        },
    }


def test_workspace_initialization_focuses_only_an_empty_original_editor(
    initialized_settings: Settings,
) -> None:
    script = TestClient(create_app(initialized_settings)).get("/static/app.js").text
    harness = r"""
const vm = require("vm");

async function run(originalValue) {
  let focusCalls = 0;
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
    "#prepared-text": new Element(), "#cleanup-enabled": new Element(),
    "#run-cleanup": new Element(), "#clear-text": new Element(),
    "#toggle-original": new Element(), "#original-count": new Element(),
    "#prepared-count": new Element(), "#outgoing-kind": new Element(),
    "#select-prepared": new Element(), "#select-original": new Element(),
    "#publication-state": new Element(), "#model-label": new Element(),
    "#cleanup-disclosure": new Element(), "#cleanup-disclosure-summary": new Element(),
    "#cleanup-route-list": new Element(), "#cleanup-processing-disclosure": new Element(),
    "#cleanup-fallback-disclosure": new Element(), "#cleanup-corpus-disclosure": new Element(),
    "#cleanup-validation-detail": new Element(), "#default-preparation-mode": new Element(),
    "#run-smart-correction": new Element(), "#smart-correction-state": new Element(),
    ".workspace": new Element(), "#workspace-resizer": new Element(),
    "#error-details-dialog": new Element(),
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
    const configBody = {
      preparation_default: "conservative",
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
  await new Promise((resolve) => setImmediate(resolve));
  return { focusCalls, originalValue: original.value };
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
        '[{"focusCalls":1,"originalValue":""},'
        '{"focusCalls":0,'
        '"originalValue":"synthetic existing entry"}]'
    )


def test_configurable_workspace_uses_native_caret_and_accessible_controls(
    initialized_settings: Settings,
) -> None:
    client = TestClient(create_app(initialized_settings))

    stylesheet = client.get("/static/app.css")
    script = client.get("/static/app.js")
    page = client.get("/")

    assert stylesheet.status_code == 200
    assert script.status_code == 200
    assert "caret-color: var(--blue)" in stylesheet.text
    assert "caret-color: transparent" not in stylesheet.text
    assert ".faux-caret" not in stylesheet.text
    assert "grid-template-rows:" in stylesheet.text
    assert "cursor: row-resize" in stylesheet.text
    assert "cursor: col-resize" in stylesheet.text
    assert ".utility-rail" in stylesheet.text
    assert ".workspace.is-side-by-side" in stylesheet.text
    assert ".workspace.is-original-maximized" in stylesheet.text
    assert ".workspace.is-prepared-maximized" in stylesheet.text
    assert ".workspace-shell.is-sidebar-collapsed" in stylesheet.text
    assert ".workspace-shell.is-sidebar-collapsed .utility-rail-icon { display: block; }" in (
        stylesheet.text
    )
    assert "min-width: 720px" not in stylesheet.text
    assert "@media (max-width: 760px)" in stylesheet.text
    assert 'role="separator"' in page.text
    assert 'aria-valuemin="25"' in page.text
    assert 'aria-valuemax="75"' in page.text
    assert 'class="panel-prompt-control"' not in page.text
    assert 'class="prepared-heading-actions"' in page.text
    assert page.text.count('class="utility-rail-icon"') == 2
    assert 'setLayoutPreference("side-by-side")' in script.text
    assert 'aria-orientation", sideBySide ? "vertical" : "horizontal"' in script.text
    assert "ArrowLeft: sideBySide ? currentShare - 2" in script.text
    assert "ArrowDown: sideBySide ? undefined : currentShare + 2" in script.text
    saved_preferences = script.text.split(
        "function saveWorkspacePreferences()", maxsplit=1
    )[1].split("function effectiveLayout()", maxsplit=1)[0]
    assert "layout: layoutPreference" in saved_preferences
    assert "stackedShare" in saved_preferences
    assert "sideBySideShare" in saved_preferences
    assert "sidebarCollapsed" in saved_preferences
    assert "maximizedPane" not in saved_preferences
    responsive_layout = script.text.split("function effectiveLayout()", maxsplit=1)[1].split(
        "function setWorkspaceShare", maxsplit=1
    )[0]
    assert 'return narrowWorkspace.matches ? "stacked" : layoutPreference' in responsive_layout


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
    assert "minmax(0, var(--prepared-share))" in stylesheet
    assert "minmax(260px" not in stylesheet
    assert "minmax(170px" not in stylesheet
