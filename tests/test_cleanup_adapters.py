import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from local_text.cleanup import (
    GEMINI_37_FLASH,
    GEMINI_MAX_OUTPUT_TOKENS,
    MAX_PREPARED_TEXT_CHARACTERS,
    OPENAI_GPT_56_LUNA,
    OPENAI_MAX_OUTPUT_TOKENS,
    PREPARED_TEXT_SCHEMA,
    GeminiAdapter,
    OpenAIAdapter,
    ProviderConfigurationError,
    ProviderFailureClass,
    ProviderHTTPError,
    ProviderMalformedResponseError,
    ProviderRejectedOutputError,
    ProviderTimeoutError,
    ProviderTransportError,
    _output_token_cap,
    _parse_prepared_text,
)


def gemini_response(
    prepared_text: str = "Synthetic prepared text.",
    *,
    usage: bool = True,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps({"prepared_text": prepared_text})}]
                }
            }
        ]
    }
    if usage:
        response["usageMetadata"] = {"promptTokenCount": 11, "candidatesTokenCount": 7}
    return response


def openai_response(
    prepared_text: str = "Synthetic prepared text.",
    *,
    usage: bool = True,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps({"prepared_text": prepared_text}),
                    }
                ],
            }
        ],
    }
    if usage:
        response["usage"] = {"input_tokens": 13, "output_tokens": 5}
    return response


def test_gemini_37_request_shape_and_usage_are_provider_correct() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=gemini_response())

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = GeminiAdapter("synthetic-key", GEMINI_37_FLASH, client)
            output = await adapter.clean("synthetic source", "Synthetic system instruction")
        assert output.text == "Synthetic prepared text."
        assert output.provider_id == "gemini"
        assert output.model_id == GEMINI_37_FLASH
        assert output.elapsed_ms >= 0
        assert (output.input_tokens, output.output_tokens) == (11, 7)

    asyncio.run(exercise())

    assert len(requests) == 1
    request = requests[0]
    assert request.url == (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-3.7-flash:generateContent"
    )
    assert request.url.query == b""
    assert request.headers["x-goog-api-key"] == "synthetic-key"
    body = json.loads(request.content)
    assert body["system_instruction"] == {
        "parts": [{"text": "Synthetic system instruction"}]
    }
    assert body["contents"] == [
        {
            "role": "user",
            "parts": [{"text": "<SOURCE_TEXT>\nsynthetic source\n</SOURCE_TEXT>"}],
        }
    ]
    assert body["generationConfig"] == {
        "thinkingConfig": {"thinkingLevel": "low"},
        "maxOutputTokens": 2_812,
        "responseMimeType": "application/json",
        "responseJsonSchema": PREPARED_TEXT_SCHEMA,
    }
    assert body["generationConfig"]["maxOutputTokens"] < 4_096
    assert "temperature" not in body["generationConfig"]
    assert "minimal" not in request.content.decode()


def test_openai_luna_request_shape_and_usage_are_provider_correct() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=openai_response())

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = OpenAIAdapter("synthetic-key", client)
            output = await adapter.clean("synthetic source", "Synthetic system instruction")
        assert output.text == "Synthetic prepared text."
        assert output.provider_id == "openai"
        assert output.model_id == OPENAI_GPT_56_LUNA
        assert output.elapsed_ms >= 0
        assert (output.input_tokens, output.output_tokens) == (13, 5)

    asyncio.run(exercise())

    assert len(requests) == 1
    request = requests[0]
    assert request.url == "https://api.openai.com/v1/responses"
    assert request.headers["authorization"] == "Bearer synthetic-key"
    body = json.loads(request.content)
    assert body == {
        "model": "gpt-5.6-luna",
        "input": [
            {"role": "system", "content": "Synthetic system instruction"},
            {
                "role": "user",
                "content": "<SOURCE_TEXT>\nsynthetic source\n</SOURCE_TEXT>",
            },
        ],
        "max_output_tokens": 764,
        "reasoning": {"effort": "none"},
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "cleanup_result",
                "strict": True,
                "schema": PREPARED_TEXT_SCHEMA,
            }
        },
    }
    assert body["max_output_tokens"] < 2_048
    assert "temperature" not in body


def test_output_token_cap_is_source_sensitive_and_provider_bounded() -> None:
    short_openai = _output_token_cap(
        "synthetic source",
        provider_max=OPENAI_MAX_OUTPUT_TOKENS,
    )
    short_gemini = _output_token_cap(
        "synthetic source",
        provider_max=GEMINI_MAX_OUTPUT_TOKENS,
        thinking_headroom=2_048,
    )
    longer_openai = _output_token_cap(
        "x" * 10_000,
        provider_max=OPENAI_MAX_OUTPUT_TOKENS,
    )

    assert short_openai == 764
    assert short_gemini == short_openai + 2_048
    assert longer_openai > short_openai
    assert _output_token_cap("x" * 100_000, provider_max=1_234) == 1_234


def test_structured_output_character_ceiling_is_in_schema_and_runtime_parser() -> None:
    assert PREPARED_TEXT_SCHEMA["properties"]["prepared_text"]["maxLength"] == 100_000
    boundary_text = "x" * MAX_PREPARED_TEXT_CHARACTERS

    assert _parse_prepared_text(json.dumps({"prepared_text": boundary_text})) == boundary_text
    with pytest.raises(ProviderMalformedResponseError):
        _parse_prepared_text(json.dumps({"prepared_text": boundary_text + "x"}))


AdapterFactory = Callable[[str, httpx.AsyncClient], GeminiAdapter | OpenAIAdapter]


@pytest.fixture(params=["gemini", "openai"])
def adapter_case(request: pytest.FixtureRequest):
    if request.param == "gemini":
        return (
            lambda key, client: GeminiAdapter(key, GEMINI_37_FLASH, client),
            gemini_response,
        )
    return (lambda key, client: OpenAIAdapter(key, client), openai_response)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 408, 429, 500, 502, 503, 504])
def test_adapter_normalizes_http_status_retry_after_and_safe_code(
    adapter_case: tuple[AdapterFactory, Callable[[], dict[str, Any]]], status: int
) -> None:
    factory, _ = adapter_case
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status,
            headers={"Retry-After": "17"},
            json={"error": {"code": "safe_provider_code", "message": "private body"}},
        )

    async def exercise() -> ProviderHTTPError:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(ProviderHTTPError) as caught:
                await factory("synthetic-key", client).clean(
                    "synthetic source", "Synthetic instruction"
                )
        return caught.value

    error = asyncio.run(exercise())

    assert calls == 1
    assert error.http_status == status
    assert error.provider_code == "safe_provider_code"
    assert error.retry_after_seconds == 17
    assert error.provider_id in {"gemini", "openai"}
    assert error.model in {GEMINI_37_FLASH, OPENAI_GPT_56_LUNA}
    assert error.elapsed_ms >= 0
    assert error.failure_class is (
        ProviderFailureClass.PERMANENT_CONFIGURATION
        if status in {400, 401, 403, 404}
        else ProviderFailureClass.TEMPORARY_QUOTA
        if status == 429
        else ProviderFailureClass.TRANSIENT_ROUTE
    )
    assert "private body" not in str(error)


def test_openai_permanent_quota_code_is_distinguished() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "error": {
                    "code": "project_spend_limit_exceeded",
                    "message": "private body",
                }
            },
        )

    async def exercise() -> ProviderHTTPError:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(ProviderHTTPError) as caught:
                await OpenAIAdapter("synthetic-key", client).clean("source", "instruction")
        return caught.value

    error = asyncio.run(exercise())
    assert error.failure_class is ProviderFailureClass.PERMANENT_QUOTA
    assert error.provider_code == "project_spend_limit_exceeded"


def test_missing_configuration_is_normalized_without_a_request(
    adapter_case: tuple[AdapterFactory, Callable[[], dict[str, Any]]],
) -> None:
    factory, _ = adapter_case
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    async def exercise() -> ProviderConfigurationError:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(ProviderConfigurationError) as caught:
                await factory("", client).clean("source", "instruction")
        return caught.value

    error = asyncio.run(exercise())
    assert calls == 0
    assert error.failure_class is ProviderFailureClass.PERMANENT_CONFIGURATION
    assert error.provider_code == "missing_api_key"
    assert error.provider_id in {"gemini", "openai"}
    assert error.model in {GEMINI_37_FLASH, OPENAI_GPT_56_LUNA}


@pytest.mark.parametrize("exception_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_transport_and_timeout_failures_are_normalized_once(
    adapter_case: tuple[AdapterFactory, Callable[[], dict[str, Any]]],
    exception_type: type[httpx.TransportError],
) -> None:
    factory, _ = adapter_case
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise exception_type("private transport detail", request=request)

    async def exercise() -> Exception:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            expected = (
                ProviderTimeoutError
                if exception_type is httpx.ReadTimeout
                else ProviderTransportError
            )
            with pytest.raises(expected) as caught:
                await factory("synthetic-key", client).clean("source", "instruction")
        return caught.value

    error = asyncio.run(exercise())
    assert calls == 1
    assert "private transport detail" not in str(error)


@pytest.mark.parametrize(
    "payload_kind",
    ["invalid_json", "missing_field", "extra_field", "wrong_type", "empty"],
)
def test_malformed_or_empty_structured_output_is_rejected(
    adapter_case: tuple[AdapterFactory, Callable[[], dict[str, Any]]], payload_kind: str
) -> None:
    factory, response_factory = adapter_case
    structured: Any = {
        "missing_field": {},
        "extra_field": {"prepared_text": "prepared", "extra": "no"},
        "wrong_type": {"prepared_text": 3},
        "empty": {"prepared_text": "   "},
    }.get(payload_kind)

    def respond(request: httpx.Request) -> httpx.Response:
        if payload_kind == "invalid_json":
            return httpx.Response(200, content=b"not-json")
        response = response_factory()
        encoded = json.dumps(structured)
        if "candidates" in response:
            response["candidates"][0]["content"]["parts"][0]["text"] = encoded
        else:
            response["output"][0]["content"][0]["text"] = encoded
        return httpx.Response(200, json=response)

    async def exercise() -> ProviderMalformedResponseError:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(ProviderMalformedResponseError) as caught:
                await factory("synthetic-key", client).clean("source", "instruction")
        return caught.value

    error = asyncio.run(exercise())
    expected_usage = (None, None) if payload_kind == "invalid_json" else (
        (11, 7) if "gemini" in error.provider_id else (13, 5)
    )
    assert (error.input_tokens, error.output_tokens) == expected_usage


def test_provider_safety_refusals_are_normalized(adapter_case) -> None:
    factory, response_factory = adapter_case

    def respond(request: httpx.Request) -> httpx.Response:
        response = response_factory()
        if "candidates" in response:
            response = {"promptFeedback": {"blockReason": "SAFETY"}}
        else:
            response["output"][0]["content"] = [
                {"type": "refusal", "refusal": "private refusal text"}
            ]
        return httpx.Response(200, json=response)

    async def exercise() -> ProviderRejectedOutputError:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(ProviderRejectedOutputError) as caught:
                await factory("synthetic-key", client).clean("source", "instruction")
        return caught.value

    error = asyncio.run(exercise())
    assert error.failure_class is ProviderFailureClass.SAFETY_POLICY
    assert "private refusal text" not in str(error)


def test_openai_incomplete_output_distinguishes_content_filter() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "incomplete",
                "incomplete_details": {"reason": "content_filter"},
                "output": [],
            },
        )

    async def exercise() -> ProviderRejectedOutputError:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(ProviderRejectedOutputError) as caught:
                await OpenAIAdapter("synthetic-key", client).clean("source", "instruction")
        return caught.value

    assert asyncio.run(exercise()).failure_class is ProviderFailureClass.SAFETY_POLICY


def test_cancellation_propagates_through_active_request_without_another_call(adapter_case) -> None:
    factory, _ = adapter_case
    started = asyncio.Event()
    cancelled = asyncio.Event()
    calls = 0

    async def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            task = asyncio.create_task(
                factory("synthetic-key", client).clean("source", "instruction")
            )
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert cancelled.is_set()

    asyncio.run(exercise())
    assert calls == 1


def test_one_client_is_reused_across_requests_and_closes_deterministically(adapter_case) -> None:
    factory, response_factory = adapter_case
    client: httpx.AsyncClient | None = None
    client_ids: list[int] = []
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        client_ids.append(id(client))
        return httpx.Response(200, json=response_factory())

    async def exercise() -> None:
        nonlocal client
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        adapter = factory("synthetic-key", client)
        await adapter.clean("first source", "instruction")
        await adapter.clean("second source", "instruction")
        assert not client.is_closed
        await client.aclose()
        assert client.is_closed

    asyncio.run(exercise())
    assert calls == 2
    assert len(set(client_ids)) == 1
