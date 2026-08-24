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
    ProviderHTTPError,
    ProviderMalformedResponseError,
    ProviderRejectedOutputError,
    ProviderTransportError,
    _extract_text,
)


class StaticProvider:
    provider_id = "gemini"
    model = "test-model"

    def __init__(self, output: str) -> None:
        self.output = output
        self.calls = 0

    async def clean(self, raw_text: str, system_prompt: str) -> str:
        self.calls += 1
        return self.output


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
    assert json.loads(payload) == {
        "category": "http_quota",
        "duration_ms": json.loads(payload)["duration_ms"],
        "http_status": 429,
        "input_length": 24,
        "model": "test-model",
        "provider": "gemini",
    }
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
    service = CleanupService(
        provider=StaticProvider("Synthetic clean text."),
        model="private model\nprivate path",
        timeout_seconds=1,
    )

    run_cleanup(service, "synthetic source")

    assert len(messages) == 1
    assert '"model":"invalid"' in messages[0]
    assert "private model" not in messages[0]


def test_gemini_response_requires_text_parts() -> None:
    assert (
        _extract_text({"candidates": [{"content": {"parts": [{"text": "Clean text."}]}}]})
        == "Clean text."
    )


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
    assert result == "Synthetic clean text."
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
