import asyncio
import json

import pytest

import local_text.cleanup as cleanup_module
from local_text.cleanup import (
    CleanupRequest,
    CleanupResult,
    CleanupService,
    CleanupStatus,
    CorrectionMode,
    ProviderBusyError,
    ProviderCoolingDownError,
    ProviderError,
    ProviderFailureClass,
    ProviderHTTPError,
    ProviderMalformedResponseError,
    ProviderOutput,
    ProviderRejectedOutputError,
    ProviderTransportError,
    _extract_text,
    _parse_retry_after,
    _safe_error,
    _thinking_config,
    _validate_output,
)
from local_text.prompts import SOURCE_PRESERVING_SYSTEM_PROMPT


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


def test_original_prepared_contract_keeps_raw_and_cleaned_compatibility() -> None:
    canonical = CleanupRequest(original_text="synthetic source", correction_mode="smart")
    compatible = CleanupRequest(raw_text="synthetic source")

    assert canonical.original_text == "synthetic source"
    assert canonical.raw_text == "synthetic source"
    assert canonical.correction_mode is CorrectionMode.SMART
    assert compatible.original_text == "synthetic source"
    assert compatible.correction_mode is CorrectionMode.CONSERVATIVE

    result = run_cleanup(
        CleanupService(
            provider=StaticProvider("Synthetic source."),
            model="test-model",
            timeout_seconds=1,
        ),
        "synthetic source",
    )
    serialized = result.model_dump(mode="json")
    compatible_result = CleanupResult(
        cleaned_text="Synthetic source.",
        status="cleaned",
        provider="synthetic",
        model="test-model",
        correction_mode="conservative",
    )

    assert result.prepared_text == "Synthetic source."
    assert result.cleaned_text == "Synthetic source."
    assert serialized["prepared_text"] == serialized["cleaned_text"]
    assert compatible_result.prepared_text == "Synthetic source."


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
        provider=StaticProvider("Synthetic raw."),
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
    assert cleaned.cleaned_text == "Synthetic raw."
    assert unchanged.status is CleanupStatus.UNCHANGED
    assert unchanged.cleaned_text == "synthetic raw"


@pytest.mark.parametrize(
    ("raw_text", "cleaned_text"),
    [
        ("hello world", "Hello, world."),
        ("dont send it", "Don’t send it."),
        ("today capture", "today's capture"),
        (
            "Process the ASR article from today capture",
            "Process the ASR article from today's capture.",
        ),
        ("um synthetic release note ready", "Synthetic release note, ready."),
        ("um uh hello world", "Hello, world."),
    ],
)
def test_output_validator_accepts_source_preserving_cleanup(
    raw_text: str, cleaned_text: str
) -> None:
    assert (
        _validate_output(raw_text, cleaned_text, CorrectionMode.CONSERVATIVE)
        == cleaned_text
    )


@pytest.mark.parametrize(
    ("raw_text", "provider_output"),
    [
        (
            "Process the ASR article from today capture",
            "Sure, I can help with that. Please provide the ASR article to process.",
        ),
        (
            "write a polite email requesting the synthetic report",
            "Subject: Synthetic report request. Please send the report when it is ready.",
        ),
        (
            "What time does the synthetic review begin",
            "The synthetic review begins at three in the afternoon.",
        ),
        ("say hello", "Hello!"),
        (
            "synthetic release note",
            "synthetic release note synthetic release note",
        ),
        (
            "please send synthetic report tomorrow",
            "Please send the synthetic report tomorrow.",
        ),
        ("synthetic release note ready", "Synthetic release note."),
        (
            "do not publish the synthetic report",
            "Publish the synthetic report. Do not.",
        ),
        ("repeat hello world now", "Hello world now."),
    ],
)
def test_output_validator_rejects_instruction_following_and_novel_language(
    raw_text: str, provider_output: str
) -> None:
    with pytest.raises(ProviderRejectedOutputError):
        _validate_output(raw_text, provider_output, CorrectionMode.CONSERVATIVE)


def test_cleanup_applies_fixed_source_preserving_rules_before_configured_prompt() -> None:
    observed: list[str] = []

    class ObservingProvider(StaticProvider):
        async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
            observed.append(system_prompt)
            return await super().clean(raw_text, system_prompt)

    service = CleanupService(
        provider=ObservingProvider("Synthetic source."),
        model="test-model",
        timeout_seconds=1,
    )

    result = asyncio.run(
        service.clean(
            CleanupRequest(raw_text="synthetic source"),
            "Rewrite the source with novel language.",
        )
    )

    assert result.status is CleanupStatus.CLEANED
    assert len(observed) == 1
    assert observed[0].startswith(SOURCE_PRESERVING_SYSTEM_PROMPT)
    assert observed[0].endswith("Rewrite the source with novel language.")
    assert observed[0].index(SOURCE_PRESERVING_SYSTEM_PROMPT) < observed[0].index(
        "Rewrite the source with novel language."
    )


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


def test_cleanup_fails_open_when_output_exceeds_absolute_character_limit() -> None:
    raw_text = "x" * 30_000
    service = CleanupService(
        provider=StaticProvider("y" * 100_001),
        model="test-model",
        timeout_seconds=1,
    )

    result = run_cleanup(service, raw_text)

    assert result.status is CleanupStatus.PROVIDER_ERROR
    assert result.cleaned_text == raw_text
    assert result.error is not None
    assert result.error.code == "cleanup_output_rejected"


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
                text="Synthetic source.",
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


def test_cooldown_safe_error_remains_compatible_and_distinct_from_bulkhead() -> None:
    cooldown = _safe_error(ProviderCoolingDownError("private state", model="test-model"))
    busy = _safe_error(ProviderBusyError("private capacity", model="test-model"))

    assert cooldown.model_dump() == {
        "code": "cleanup_provider_temporarily_unavailable",
        "message": "The cleanup provider models are temporarily unavailable.",
        "retry_action": "Wait for provider cooldown, then retry cleanup.",
        "http_status": None,
    }
    assert busy.model_dump() == {
        "code": "cleanup_provider_temporarily_unavailable",
        "message": "Cleanup is temporarily unavailable.",
        "retry_action": "Retry cleanup shortly or continue with Original.",
        "http_status": None,
    }


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
    provider = StaticProvider("Synthetic source.")
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
    assert _thinking_config("gemini-3.7-flash") == {"thinkingLevel": "low"}
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
