import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

import local_text.cleanup as cleanup_module
from local_text.cleanup import (
    CleanupRequest,
    CleanupService,
    CleanupStatus,
    GeminiProvider,
    ProviderError,
    ProviderFailureClass,
    ProviderHTTPError,
    ProviderMalformedResponseError,
    ProviderOutput,
    ProviderRejectedOutputError,
    ProviderTransportError,
    _extract_text,
    _parse_retry_after,
    _thinking_config,
)


class StaticProvider:
    provider_id = "gemini"
    model = "test-model"

    def __init__(self, output: str) -> None:
        self.output = output
        self.calls = 0

    async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
        self.calls += 1
        return ProviderOutput(
            text=self.output,
            provider_id=self.provider_id,
            model_id=self.model,
            elapsed_ms=4,
        )


def run_cleanup(service: CleanupService, raw_text: str, *, enabled: bool = True):
    return asyncio.run(
        service.clean(
            CleanupRequest(raw_text=raw_text, enabled=enabled),
            "Synthetic cleanup instruction",
        )
    )


def test_empty_input_and_disabled_cleanup_do_not_call_provider() -> None:
    provider = StaticProvider("unused")
    service = CleanupService(provider=provider, model=provider.model, timeout_seconds=1)

    empty = run_cleanup(service, "")
    disabled = run_cleanup(service, "synthetic raw", enabled=False)

    assert empty.status is CleanupStatus.EMPTY_INPUT
    assert empty.cleaned_text == ""
    assert disabled.status is CleanupStatus.DISABLED
    assert disabled.cleaned_text == "synthetic raw"
    assert provider.calls == 0


def test_successful_and_unchanged_cleanup_are_distinguished() -> None:
    cleaned_service = CleanupService(
        provider=StaticProvider("Synthetic clean text."),
        model="test-model",
        timeout_seconds=1,
    )
    unchanged_service = CleanupService(
        provider=StaticProvider("synthetic raw"),
        model="test-model",
        timeout_seconds=1,
    )

    cleaned = run_cleanup(cleaned_service, "synthetic raw")
    unchanged = run_cleanup(unchanged_service, "synthetic raw")

    assert cleaned.status is CleanupStatus.CLEANED
    assert cleaned.cleaned_text == "Synthetic clean text."
    assert unchanged.status is CleanupStatus.UNCHANGED
    assert unchanged.cleaned_text == "synthetic raw"


def test_timeout_fails_open_to_raw_text() -> None:
    class SlowProvider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, raw_text: str, system_prompt: str) -> str:
            await asyncio.sleep(0.1)
            return "too late"

    service = CleanupService(provider=SlowProvider(), model="test-model", timeout_seconds=0.001)

    result = run_cleanup(service, "synthetic raw")

    assert result.status is CleanupStatus.TIMEOUT
    assert result.cleaned_text == "synthetic raw"
    assert result.error is not None
    assert result.error.code == "cleanup_timeout"
    assert "synthetic raw" not in result.error.message


def test_provider_error_and_rejected_output_fail_open_to_raw_text() -> None:
    class BrokenProvider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, raw_text: str, system_prompt: str) -> str:
            raise RuntimeError("synthetic provider failure")

    broken_service = CleanupService(
        provider=BrokenProvider(), model="test-model", timeout_seconds=1
    )
    expanded_service = CleanupService(
        provider=StaticProvider("x" * 2_000), model="test-model", timeout_seconds=1
    )

    broken = run_cleanup(broken_service, "synthetic raw")
    expanded = run_cleanup(expanded_service, "synthetic raw")

    assert broken.status is CleanupStatus.PROVIDER_ERROR
    assert broken.cleaned_text == "synthetic raw"
    assert broken.error is not None
    assert broken.error.code == "cleanup_provider_error"
    assert "synthetic provider failure" not in broken.error.message
    assert expanded.status is CleanupStatus.PROVIDER_ERROR
    assert expanded.cleaned_text == "synthetic raw"
    assert expanded.error is not None
    assert expanded.error.code == "cleanup_output_rejected"


def test_provider_failures_have_specific_safe_classifications() -> None:
    cases = (
        (ProviderHTTPError(401), "cleanup_provider_auth_error", 401),
        (ProviderHTTPError(403), "cleanup_provider_auth_error", 403),
        (ProviderHTTPError(429), "cleanup_provider_quota_error", 429),
        (ProviderHTTPError(503), "cleanup_provider_server_error", 503),
        (ProviderHTTPError(404), "cleanup_provider_http_error", 404),
        (
            ProviderTransportError("private transport detail"),
            "cleanup_provider_transport_error",
            None,
        ),
        (
            ProviderMalformedResponseError("private provider payload"),
            "cleanup_provider_malformed_response",
            None,
        ),
        (
            ProviderRejectedOutputError("private safety detail"),
            "cleanup_output_rejected",
            None,
        ),
    )

    class FailingProvider:
        provider_id = "gemini"
        model = "test-model"

        def __init__(self, error: Exception) -> None:
            self.error = error

        async def clean(self, raw_text: str, system_prompt: str) -> str:
            raise self.error

    for provider_error, expected_code, expected_status in cases:
        result = run_cleanup(
            CleanupService(
                provider=FailingProvider(provider_error), model="test-model", timeout_seconds=1
            ),
            "synthetic source",
        )

        assert result.status is CleanupStatus.PROVIDER_ERROR
        assert result.cleaned_text == "synthetic source"
        assert result.error is not None
        assert result.error.code == expected_code
        assert result.error.http_status == expected_status
        serialized = result.error.model_dump_json()
        assert "private" not in serialized
        assert "synthetic source" not in serialized


def test_miscellaneous_provider_http_status_preserves_safe_api_error() -> None:
    class FailingProvider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, raw_text: str, system_prompt: str) -> str:
            raise ProviderHTTPError(418)

    result = run_cleanup(
        CleanupService(provider=FailingProvider(), model="test-model", timeout_seconds=1),
        "synthetic source",
    )

    assert result.attempts[0].failure_class is ProviderFailureClass.UNKNOWN
    assert result.error is not None
    assert result.error.model_dump() == {
        "code": "cleanup_provider_http_error",
        "message": "The cleanup provider rejected the request.",
        "retry_action": "Check the provider model configuration, then retry cleanup.",
        "http_status": 418,
    }


@pytest.mark.parametrize("failure_class", list(ProviderFailureClass))
def test_every_normalized_failure_class_has_safe_public_attribution(
    failure_class: ProviderFailureClass,
) -> None:
    failure = ProviderError(
        "private provider response /Users/private/file",
        failure_class=failure_class,
        provider_id="alternate-provider",
        model="alternate-model",
        provider_code="safe_code",
        http_status=429,
        retry_after_seconds=12,
        elapsed_ms=34,
        quota_group_id="alternate-quota",
        route_index=2,
    )

    class FailingProvider:
        provider_id = "alternate-provider"
        model = "alternate-model"

        async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
            raise failure

    result = run_cleanup(
        CleanupService(provider=FailingProvider(), model="alternate-model", timeout_seconds=1),
        "private synthetic source",
    )

    assert result.cleaned_text == "private synthetic source"
    assert result.provider == "alternate-provider"
    assert result.model == "alternate-model"
    assert len(result.attempts) == 1
    assert result.attempts[0].model_dump(mode="json") == {
        "provider": "alternate-provider",
        "model": "alternate-model",
        "outcome": "failure",
        "elapsed_ms": 34,
        "route_index": 2,
        "input_tokens": None,
        "output_tokens": None,
        "failure_class": failure_class,
        "provider_code": "safe_code",
        "http_status": 429,
        "retry_after_seconds": 12,
        "quota_group_id": "alternate-quota",
    }
    assert "provider response" not in result.model_dump_json()
    assert "/Users/" not in result.model_dump_json()


def test_provider_neutral_success_attribution_includes_optional_usage() -> None:
    class AlternateProvider:
        provider_id = "alternate-provider"
        model = "alternate-model"

        async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
            return ProviderOutput(
                text="Synthetic clean text.",
                provider_id=self.provider_id,
                model_id=self.model,
                elapsed_ms=25,
                input_tokens=11,
                output_tokens=7,
                route_index=3,
            )

    result = run_cleanup(
        CleanupService(provider=AlternateProvider(), model="alternate-model", timeout_seconds=1),
        "synthetic source",
    )

    assert result.provider == "alternate-provider"
    assert result.model == "alternate-model"
    assert result.attempts[0].model_dump(mode="json") == {
        "provider": "alternate-provider",
        "model": "alternate-model",
        "outcome": "success",
        "elapsed_ms": 25,
        "route_index": 3,
        "input_tokens": 11,
        "output_tokens": 7,
        "failure_class": None,
        "provider_code": None,
        "http_status": None,
        "retry_after_seconds": None,
        "quota_group_id": None,
    }


def test_cleanup_cancellation_propagates_without_provider_failure(monkeypatch) -> None:
    cancelled = asyncio.Event()
    messages: list[str] = []

    class WaitingProvider:
        provider_id = "alternate-provider"
        model = "alternate-model"

        async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    monkeypatch.setattr(
        cleanup_module.logger,
        "info",
        lambda template, payload: messages.append(template % payload),
    )

    async def cancel_cleanup() -> None:
        service = CleanupService(
            provider=WaitingProvider(), model="alternate-model", timeout_seconds=30
        )
        task = asyncio.create_task(
            service.clean(CleanupRequest(raw_text="synthetic source"), "Synthetic instruction")
        )
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_cleanup())

    assert cancelled.is_set()
    assert len(messages) == 1
    payload = json.loads(messages[0].split(" ", maxsplit=1)[1])
    assert payload["category"] == "cancelled"
    assert payload["attempts"] == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [("15", 15), ("-1", None), ("999999", None), ("private detail", None)],
)
def test_retry_after_parsing_accepts_only_safe_bounded_values(
    value: str, expected: int | None
) -> None:
    assert _parse_retry_after(value) == expected


@pytest.mark.parametrize("status_code", [429, 503])
def test_transient_http_failure_uses_fallback_and_cools_primary(
    monkeypatch, status_code: int
) -> None:
    provider = GeminiProvider(
        "synthetic-key",
        "primary-model",
        fallback_models=("fallback-model",),
    )
    calls: list[str] = []

    async def clean_model(model: str, raw_text: str, system_prompt: str) -> str:
        calls.append(model)
        if model == "primary-model":
            raise ProviderHTTPError(status_code, model=model)
        return "Synthetic clean text."

    monkeypatch.setattr(provider, "_clean_model", clean_model)
    service = CleanupService(provider=provider, model=provider.model, timeout_seconds=1)

    first = run_cleanup(service, "synthetic source")
    second = run_cleanup(service, "synthetic source")

    assert first.status is CleanupStatus.CLEANED
    assert first.model == "fallback-model"
    assert [(attempt.outcome, attempt.model) for attempt in first.attempts] == [
        ("failure", "primary-model"),
        ("success", "fallback-model"),
    ]
    assert first.attempts[0].failure_class is (
        ProviderFailureClass.TEMPORARY_QUOTA
        if status_code == 429
        else ProviderFailureClass.TRANSIENT_ROUTE
    )
    assert second.status is CleanupStatus.CLEANED
    assert second.model == "fallback-model"
    assert calls == ["primary-model", "fallback-model", "fallback-model"]


def test_non_transient_http_failure_does_not_use_fallback(monkeypatch) -> None:
    provider = GeminiProvider(
        "synthetic-key",
        "primary-model",
        fallback_models=("fallback-model",),
    )
    calls: list[str] = []

    async def clean_model(model: str, raw_text: str, system_prompt: str) -> str:
        calls.append(model)
        raise ProviderHTTPError(500, model=model)

    monkeypatch.setattr(provider, "_clean_model", clean_model)
    result = run_cleanup(
        CleanupService(provider=provider, model=provider.model, timeout_seconds=1),
        "synthetic source",
    )

    assert result.status is CleanupStatus.PROVIDER_ERROR
    assert result.model == "primary-model"
    assert result.error is not None
    assert result.error.http_status == 500
    assert calls == ["primary-model"]


def test_exhausted_fallbacks_fail_open_and_cool_down(monkeypatch) -> None:
    provider = GeminiProvider(
        "synthetic-key",
        "primary-model",
        fallback_models=("fallback-model",),
    )
    calls: list[str] = []

    async def clean_model(model: str, raw_text: str, system_prompt: str) -> str:
        calls.append(model)
        raise ProviderHTTPError(429, model=model)

    monkeypatch.setattr(provider, "_clean_model", clean_model)
    service = CleanupService(provider=provider, model=provider.model, timeout_seconds=1)

    exhausted = run_cleanup(service, "synthetic source")
    cooling_down = run_cleanup(service, "synthetic source")

    assert exhausted.status is CleanupStatus.PROVIDER_ERROR
    assert exhausted.cleaned_text == "synthetic source"
    assert exhausted.model == "fallback-model"
    assert exhausted.error is not None
    assert exhausted.error.code == "cleanup_provider_quota_error"
    assert cooling_down.status is CleanupStatus.PROVIDER_ERROR
    assert cooling_down.cleaned_text == "synthetic source"
    assert cooling_down.model == "fallback-model"
    assert cooling_down.error is not None
    assert cooling_down.error.code == "cleanup_provider_temporarily_unavailable"
    assert calls == ["primary-model", "fallback-model"]


def test_duplicate_fallback_models_are_not_retried(monkeypatch) -> None:
    provider = GeminiProvider(
        "synthetic-key",
        "primary-model",
        fallback_models=("primary-model", "fallback-model", "fallback-model"),
    )
    calls: list[str] = []

    async def clean_model(model: str, raw_text: str, system_prompt: str) -> str:
        calls.append(model)
        raise ProviderHTTPError(429, model=model)

    monkeypatch.setattr(provider, "_clean_model", clean_model)

    with pytest.raises(ProviderHTTPError):
        asyncio.run(provider.clean("synthetic source", "Synthetic cleanup instruction"))

    assert provider.fallback_models == ("fallback-model",)
    assert calls == ["primary-model", "fallback-model"]


def test_primary_model_is_retried_after_cooldown_expires(monkeypatch) -> None:
    provider = GeminiProvider(
        "synthetic-key",
        "primary-model",
        fallback_models=("fallback-model",),
        cooldown_seconds=300,
    )
    now = 100.0
    calls: list[str] = []

    async def clean_model(model: str, raw_text: str, system_prompt: str) -> str:
        calls.append(model)
        if calls == ["primary-model"]:
            raise ProviderHTTPError(503, model=model)
        return "Synthetic clean text."

    monkeypatch.setattr(provider, "_clean_model", clean_model)
    monkeypatch.setattr(cleanup_module.time, "monotonic", lambda: now)

    first = asyncio.run(provider.clean("synthetic source", "Synthetic cleanup instruction"))
    now += 301
    second = asyncio.run(provider.clean("synthetic source", "Synthetic cleanup instruction"))

    assert first.model_id == "fallback-model"
    assert second.model_id == "primary-model"
    assert calls == ["primary-model", "fallback-model", "primary-model"]


def test_cleanup_log_contains_only_allowlisted_diagnostics(monkeypatch) -> None:
    class FailingProvider:
        provider_id = "gemini"
        model = "test-model"

        async def clean(self, raw_text: str, system_prompt: str) -> str:
            raise ProviderHTTPError(429)

    messages: list[str] = []
    monkeypatch.setattr(
        cleanup_module.logger,
        "info",
        lambda template, payload: messages.append(template % payload),
    )
    result = run_cleanup(
        CleanupService(provider=FailingProvider(), model="test-model", timeout_seconds=1),
        "private synthetic source",
    )

    assert result.error is not None
    assert len(messages) == 1
    message = messages[0]
    prefix, payload = message.split(" ", maxsplit=1)
    assert prefix == "cleanup_result"
    parsed = json.loads(payload)
    assert parsed == {
        "attempts": parsed["attempts"],
        "category": "temporary_quota",
        "duration_ms": json.loads(payload)["duration_ms"],
        "http_status": 429,
        "input_length": 24,
        "model": "test-model",
        "provider": "gemini",
    }
    assert parsed["attempts"] == [
        {
            "elapsed_ms": 0,
            "failure_class": "temporary_quota",
            "http_status": 429,
            "input_tokens": None,
            "model": "test-model",
            "outcome": "failure",
            "output_tokens": None,
            "provider": "gemini",
            "provider_code": "http_429",
            "quota_group_id": None,
            "retry_after_seconds": None,
            "route_index": 0,
        }
    ]
    assert isinstance(json.loads(payload)["duration_ms"], int)
    assert all(
        forbidden not in message
        for forbidden in (
            "private synthetic source",
            "Synthetic cleanup instruction",
            "credential",
            "headers",
            "payload",
            "Traceback",
            "/Users/",
        )
    )


def test_cleanup_log_does_not_emit_an_unvalidated_model(monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(
        cleanup_module.logger,
        "info",
        lambda template, payload: messages.append(template % payload),
    )
    provider = StaticProvider("Synthetic clean text.")
    provider.model = "private model\nprivate path"
    service = CleanupService(provider=provider, model=provider.model, timeout_seconds=1)

    run_cleanup(service, "synthetic source")

    assert len(messages) == 1
    assert '"model":"invalid"' in messages[0]
    assert "private model" not in messages[0]


def test_gemini_response_requires_text_parts() -> None:
    assert (
        _extract_text({"candidates": [{"content": {"parts": [{"text": "Clean text."}]}}]})
        == "Clean text."
    )


def test_thinking_configuration_matches_model_generation() -> None:
    assert _thinking_config("gemini-3.5-flash") == {"thinkingLevel": "minimal"}
    assert _thinking_config("gemini-2.5-flash") == {"thinkingBudget": 0}


def test_gemini_response_distinguishes_rejection_from_malformed_output() -> None:
    try:
        _extract_text({"promptFeedback": {"blockReason": "SAFETY"}})
    except ProviderRejectedOutputError:
        pass
    else:
        raise AssertionError("blocked response was not rejected")

    try:
        _extract_text({"candidates": []})
    except ProviderMalformedResponseError:
        pass
    else:
        raise AssertionError("malformed response was not classified")


def test_gemini_provider_converts_http_failure_without_reading_provider_payload() -> None:
    private_payload = b'{"error":"private provider detail"}'

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(private_payload)))
            self.send_header("Retry-After", "17")
            self.end_headers()
            self.wfile.write(private_payload)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        host, port = server.server_address
        provider = GeminiProvider(
            "synthetic-key",
            "test-model",
            timeout_seconds=1,
            endpoint=f"http://{host}:{port}",
        )
        with pytest.raises(ProviderHTTPError) as caught:
            asyncio.run(provider.clean("synthetic source", "Synthetic system prompt"))
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    assert caught.value.status_code == 429
    assert caught.value.retry_after_seconds == 17
    assert "private provider detail" not in str(caught.value)


def test_gemini_provider_separately_frames_prompt_and_untrusted_source_text() -> None:
    observed: dict[str, object] = {}
    response_body = json.dumps(
        {"candidates": [{"content": {"parts": [{"text": "Synthetic clean text."}]}}]}
    ).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers["Content-Length"])
            observed["url"] = self.path
            observed["body"] = json.loads(self.rfile.read(length))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        host, port = server.server_address
        provider = GeminiProvider(
            "synthetic-key",
            "test-model",
            timeout_seconds=1,
            endpoint=f"http://{host}:{port}",
        )
        result = asyncio.run(provider.clean("synthetic source text", "Synthetic system prompt"))
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    request_url = urlparse(str(observed["url"]))
    request_body = observed["body"]
    assert result.text == "Synthetic clean text."
    assert result.provider_id == "gemini"
    assert result.model_id == "test-model"
    assert result.elapsed_ms >= 0
    assert request_url.path == "/models/test-model:generateContent"
    assert parse_qs(request_url.query) == {"key": ["synthetic-key"]}
    assert request_body["system_instruction"]["parts"][0]["text"] == "Synthetic system prompt"
    assert (
        request_body["contents"][0]["parts"][0]["text"]
        == "<SOURCE_TEXT>\nsynthetic source text\n</SOURCE_TEXT>"
    )
    assert request_body["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": "minimal"
    }
