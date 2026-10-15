import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

import local_text.cleanup as cleanup_module
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


@pytest.mark.parametrize("model", ["openai/gpt-4.1", "openai/gpt-4.1-mini"])
def test_openrouter_pins_endpoint_and_parses_complete_output(model: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == model
        assert body["provider"] == {
            "only": ["azure"],
            "allow_fallbacks": False,
            "zdr": True,
            "require_parameters": True,
            "data_collection": "deny",
        }
        assert body["max_completion_tokens"] == 764
        assert "max_tokens" not in body
        assert body["response_format"]["json_schema"]["schema"] == PREPARED_TEXT_SCHEMA
        assert body["messages"][1]["content"] == ("<SOURCE_TEXT>\nsynthetic source\n</SOURCE_TEXT>")
        return httpx.Response(
            200,
            json={
                "provider": "Azure",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": '{"prepared_text":"Synthetic source."}',
                        },
                    }
                ],
                "usage": {"prompt_tokens": 19, "completion_tokens": 8},
            },
        )

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            output = await cleanup_module.OpenRouterAdapter(
                "synthetic-key",
                model,
                "azure",
                client,
            ).clean("synthetic source", "Preserve words")
        assert output.text == "Synthetic source."
        assert output.model_id == model
        assert output.provider_id == "openrouter"
        assert (output.input_tokens, output.output_tokens) == (19, 8)

    asyncio.run(exercise())


@pytest.mark.parametrize("content,finish", [(None, "stop"), ("{}", "length")])
def test_openrouter_rejects_missing_or_incomplete_content(content, finish) -> None:
    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "provider": "Azure",
                        "choices": [
                            {
                                "finish_reason": finish,
                                "message": {"content": content},
                            }
                        ],
                    },
                )
            )
        ) as client:
            with pytest.raises(ProviderMalformedResponseError):
                await cleanup_module.OpenRouterAdapter(
                    "synthetic-key",
                    "openai/gpt-4.1",
                    "azure",
                    client,
                ).clean("synthetic source", "Preserve words")

    asyncio.run(exercise())


def test_openrouter_counts_context_in_input_bound_without_truncation() -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        evidence = json.loads(json.loads(request.content)["messages"][1]["content"].split("\n")[1])
        calls.append(evidence)
        return httpx.Response(200, json={
            "provider": "Azure", "choices": [{"finish_reason": "stop", "message": {
                "content": '{"prepared_text":"Synthetic output."}',
            }}],
        })

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = cleanup_module.OpenRouterAdapter(
                "synthetic-key", "openai/gpt-4.1-mini", "azure", client,
            )
            await adapter.clean("é" * 11_980, "Preserve words", task_context="x" * 20)
            with pytest.raises(cleanup_module.ProviderFailure) as caught:
                await adapter.clean("é" * 11_980, "Preserve words", task_context="x" * 21)
            assert caught.value.failure_class == ProviderFailureClass.INVALID_LOCAL_REQUEST
        assert len(calls) == 1
        assert calls[0]["original_text"] == "é" * 11_980
        assert calls[0]["task_context"] == "x" * 20

    asyncio.run(exercise())


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


@pytest.mark.parametrize("provider", ["gemini", "openai"])
def test_enabled_provider_traffic_logs_exact_request_and_success_response(
    provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[str] = []
    raw_body = (
        '{"candidates":[{"content":{"parts":[{"text":"{\\"prepared_text\\":'
        '\\"Synthetic prepared text.\\"}"}]}}],"usageMetadata":'
        '{"promptTokenCount":11,"candidatesTokenCount":7}}'
        if provider == "gemini"
        else '{"status":"completed","output":[{"type":"message","content":'
        '[{"type":"output_text","text":"{\\"prepared_text\\":'
        '\\"Synthetic prepared text.\\"}"}]}],"usage":{"input_tokens":13,'
        '"output_tokens":5}}'
    )

    monkeypatch.setattr(
        cleanup_module.logger,
        "info",
        lambda template, entry: messages.append(template % entry),
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw_body, headers={"content-type": "application/json"})

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = (
                GeminiAdapter(
                    "synthetic-key",
                    GEMINI_37_FLASH,
                    client,
                    traffic_diagnostics_enabled=lambda: True,
                )
                if provider == "gemini"
                else OpenAIAdapter(
                    "synthetic-key",
                    client,
                    traffic_diagnostics_enabled=lambda: True,
                )
            )
            await adapter.clean("private synthetic dictation", "Synthetic system instruction")

    asyncio.run(exercise())

    entries = [json.loads(message.split(" ", maxsplit=1)[1]) for message in messages]
    assert [entry["direction"] for entry in entries] == ["request", "response"]
    request_entry, response_entry = entries
    assert request_entry["event"] == "provider_traffic"
    assert request_entry["provider"] == provider
    assert request_entry["model"] == (
        GEMINI_37_FLASH if provider == "gemini" else OPENAI_GPT_56_LUNA
    )
    if provider == "gemini":
        assert request_entry["payload"]["system_instruction"] == {
            "parts": [{"text": "Synthetic system instruction"}]
        }
        assert request_entry["payload"]["contents"] == [
            {
                "role": "user",
                "parts": [
                    {"text": "<SOURCE_TEXT>\nprivate synthetic dictation\n</SOURCE_TEXT>"}
                ],
            }
        ]
    else:
        assert request_entry["payload"]["model"] == "gpt-5.6-luna"
        assert request_entry["payload"]["input"] == [
            {"role": "system", "content": "Synthetic system instruction"},
            {
                "role": "user",
                "content": "<SOURCE_TEXT>\nprivate synthetic dictation\n</SOURCE_TEXT>",
            },
        ]
        assert request_entry["payload"]["store"] is False
    assert response_entry == {
        "body": raw_body,
        "direction": "response",
        "event": "provider_traffic",
        "model": GEMINI_37_FLASH if provider == "gemini" else OPENAI_GPT_56_LUNA,
        "provider": provider,
        "status": 200,
    }
    serialized = json.dumps(entries)
    assert "synthetic-key" not in serialized
    assert "authorization" not in serialized.lower()
    assert "api.openai.com" not in serialized
    assert "googleapis.com" not in serialized


@pytest.mark.parametrize("provider", ["gemini", "openai"])
def test_enabled_provider_traffic_logs_exact_error_response(
    provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[str] = []
    raw_body = '{"error":{"code":"synthetic_failure","message":"exact private detail"}}'
    monkeypatch.setattr(
        cleanup_module.logger,
        "info",
        lambda template, entry: messages.append(template % entry),
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=raw_body)

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = (
                GeminiAdapter(
                    "synthetic-key",
                    GEMINI_37_FLASH,
                    client,
                    traffic_diagnostics_enabled=lambda: True,
                )
                if provider == "gemini"
                else OpenAIAdapter(
                    "synthetic-key",
                    client,
                    traffic_diagnostics_enabled=lambda: True,
                )
            )
            with pytest.raises(ProviderHTTPError):
                await adapter.clean("synthetic source", "Synthetic instruction")

    asyncio.run(exercise())

    response_entry = json.loads(messages[-1].split(" ", maxsplit=1)[1])
    assert response_entry["provider"] == provider
    assert response_entry["status"] == 503
    assert response_entry["body"] == raw_body


def test_disabled_or_broken_provider_traffic_diagnostics_do_not_change_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logging_attempts = 0

    def fail_to_log(template: str, entry: str) -> None:
        nonlocal logging_attempts
        logging_attempts += 1
        raise RuntimeError("synthetic logging failure")

    monkeypatch.setattr(cleanup_module.logger, "info", fail_to_log)

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=openai_response())

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            disabled = OpenAIAdapter(
                "synthetic-key", client, traffic_diagnostics_enabled=lambda: False
            )
            assert (await disabled.clean("private disabled source", "instruction")).text == (
                "Synthetic prepared text."
            )
            broken = OpenAIAdapter(
                "synthetic-key",
                client,
                traffic_diagnostics_enabled=lambda: (_ for _ in ()).throw(RuntimeError()),
            )
            assert (await broken.clean("private broken source", "instruction")).text == (
                "Synthetic prepared text."
            )
            enabled = OpenAIAdapter(
                "synthetic-key", client, traffic_diagnostics_enabled=lambda: True
            )
            assert (await enabled.clean("private enabled source", "instruction")).text == (
                "Synthetic prepared text."
            )

    asyncio.run(exercise())
    assert logging_attempts == 2


@pytest.mark.parametrize("provider", ["gemini", "openai"])
def test_smart_evidence_is_ephemeral_untrusted_and_foreground(provider: str) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        response = gemini_response() if provider == "gemini" else openai_response()
        return httpx.Response(200, json=response)

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = (
                GeminiAdapter("synthetic-key", GEMINI_37_FLASH, client)
                if provider == "gemini"
                else OpenAIAdapter("synthetic-key", client)
            )
            await adapter.clean(
                "synthetic Original",
                "Synthetic immutable instruction",
                task_context="Writing a release note.",
                relevant_curated_knowledge=("Prefer Sayloom.",),
            )

    asyncio.run(exercise())

    body = json.loads(requests[0].content)
    user_content = (
        body["contents"][0]["parts"][0]["text"]
        if provider == "gemini"
        else body["input"][1]["content"]
    )
    assert user_content == (
        '<REQUEST_EVIDENCE>\n{"original_text":"synthetic Original",'
        '"task_context":"Writing a release note.",'
        '"relevant_curated_knowledge":["Prefer Sayloom."]}\n</REQUEST_EVIDENCE>'
    )
    instruction = body["system_instruction"] if provider == "gemini" else body["input"][0]
    assert "Writing a release note." not in json.dumps(instruction)
    assert "tools" not in body
    assert "background" not in body
    if provider == "openai":
        assert body["store"] is False
        assert body["text"]["format"]["type"] == "json_schema"
    else:
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert "cachedContent" not in body


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
