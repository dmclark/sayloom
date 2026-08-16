import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from local_text.cleanup import (
    CleanupRequest,
    CleanupService,
    CleanupStatus,
    GeminiProvider,
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
    assert expanded.status is CleanupStatus.PROVIDER_ERROR
    assert expanded.cleaned_text == "synthetic raw"


def test_gemini_response_requires_text_parts() -> None:
    assert (
        _extract_text({"candidates": [{"content": {"parts": [{"text": "Clean text."}]}}]})
        == "Clean text."
    )


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
