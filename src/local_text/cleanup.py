"""Fail-open source-text cleanup using Gemini."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("uvicorn.error.local_text.cleanup")
MODEL_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
TRANSIENT_FALLBACK_STATUSES = {429, 503}


class CleanupStatus(StrEnum):
    CLEANED = "cleaned"
    UNCHANGED = "unchanged"
    EMPTY_INPUT = "empty_input"
    DISABLED = "disabled"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"


class CleanupRequest(BaseModel):
    raw_text: str = Field(max_length=100_000)
    enabled: bool = True
    prompt_version_id: int | None = Field(default=None, ge=1)


class SafeError(BaseModel):
    code: str
    message: str
    retry_action: str
    http_status: int | None = None


class ProviderFailureClass(StrEnum):
    TRANSIENT_ROUTE = "transient_route"
    TEMPORARY_QUOTA = "temporary_quota"
    PERMANENT_QUOTA = "permanent_quota"
    PERMANENT_CONFIGURATION = "permanent_configuration"
    SAFETY_POLICY = "safety_policy"
    INVALID_OUTPUT = "invalid_output"
    INVALID_LOCAL_REQUEST = "invalid_local_request"
    UNKNOWN = "unknown"


class CleanupAttempt(BaseModel):
    provider: str
    model: str
    outcome: Literal["success", "failure"]
    elapsed_ms: int = Field(ge=0)
    route_index: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    failure_class: ProviderFailureClass | None = None
    provider_code: str | None = None
    http_status: int | None = None
    retry_after_seconds: int | None = None
    quota_group_id: str | None = None


class CleanupResult(BaseModel):
    cleaned_text: str
    status: CleanupStatus
    provider: str
    model: str
    error: SafeError | None = None
    attempts: list[CleanupAttempt] = Field(default_factory=list)


class CleanupProvider(Protocol):
    provider_id: str
    model: str

    async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput: ...


@dataclass(frozen=True)
class ProviderOutput:
    text: str
    provider_id: str
    model_id: str
    elapsed_ms: int
    route_index: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    prior_failures: tuple[ProviderFailure, ...] = ()


class ProviderFailure(RuntimeError):
    """A normalized provider failure containing only safe attribution."""

    def __init__(
        self,
        message: str,
        *,
        failure_class: ProviderFailureClass = ProviderFailureClass.UNKNOWN,
        provider_id: str | None = None,
        model: str | None = None,
        provider_code: str = "unknown",
        http_status: int | None = None,
        retry_after_seconds: int | None = None,
        elapsed_ms: int = 0,
        quota_group_id: str | None = None,
        route_index: int = 0,
        prior_failures: tuple[ProviderFailure, ...] = (),
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.provider_id = provider_id
        self.model = model
        self.provider_code = provider_code
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds
        self.elapsed_ms = elapsed_ms
        self.quota_group_id = quota_group_id
        self.route_index = route_index
        self.prior_failures = prior_failures


ProviderError = ProviderFailure


class ProviderHTTPError(ProviderError):
    """The provider rejected a request with an HTTP response."""

    def __init__(
        self,
        status_code: int,
        *,
        model: str | None = None,
        provider_code: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(
            "provider HTTP error",
            failure_class=_http_failure_class(status_code),
            model=model,
            provider_code=provider_code or f"http_{status_code}",
            http_status=status_code,
            retry_after_seconds=retry_after_seconds,
        )
        self.status_code = status_code


class ProviderTransportError(ProviderError):
    """The provider could not be reached."""

    def __init__(self, message: str, *, model: str | None = None) -> None:
        super().__init__(
            message,
            failure_class=ProviderFailureClass.TRANSIENT_ROUTE,
            model=model,
            provider_code="transport_error",
        )


class ProviderTimeoutError(ProviderError):
    """One provider model exceeded its request timeout."""

    def __init__(self, message: str, *, model: str | None = None) -> None:
        super().__init__(
            message,
            failure_class=ProviderFailureClass.TRANSIENT_ROUTE,
            model=model,
            provider_code="timeout",
        )


class ProviderMalformedResponseError(ProviderError):
    """The provider returned a response that could not be interpreted."""

    def __init__(self, message: str, *, model: str | None = None) -> None:
        super().__init__(
            message,
            failure_class=ProviderFailureClass.INVALID_OUTPUT,
            model=model,
            provider_code="malformed_response",
        )


class ProviderRejectedOutputError(ProviderError):
    """The provider returned a response that is unsafe to use as outgoing text."""

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        safety_policy: bool = False,
    ) -> None:
        super().__init__(
            message,
            failure_class=(
                ProviderFailureClass.SAFETY_POLICY
                if safety_policy
                else ProviderFailureClass.INVALID_OUTPUT
            ),
            model=model,
            provider_code="safety_policy" if safety_policy else "rejected_output",
        )


class ProviderCoolingDownError(ProviderError):
    """Every configured provider model is in transient-error cooldown."""

    def __init__(self, message: str, *, model: str | None = None) -> None:
        super().__init__(
            message,
            failure_class=ProviderFailureClass.TEMPORARY_QUOTA,
            model=model,
            provider_code="cooldown",
        )


@dataclass
class GeminiProvider:
    api_key: str
    model: str
    timeout_seconds: float = 8.0
    endpoint: str = "https://generativelanguage.googleapis.com/v1beta"
    provider_id: str = "gemini"
    fallback_models: tuple[str, ...] = ()
    quota_group_id: str | None = None
    cooldown_seconds: float = 300.0
    _cooldowns: dict[str, float] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        for model in (self.model, *self.fallback_models):
            if not MODEL_IDENTIFIER.fullmatch(model):
                raise ValueError("provider model identifier is invalid")
        if self.quota_group_id is not None and not SAFE_IDENTIFIER.fullmatch(self.quota_group_id):
            raise ValueError("provider quota group identifier is invalid")
        self.fallback_models = tuple(
            dict.fromkeys(model for model in self.fallback_models if model != self.model)
        )

    async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
        now = time.monotonic()
        models = tuple(
            model
            for model in (self.model, *self.fallback_models)
            if self._cooldowns.get(model, 0) <= now
        )
        if not models:
            error = ProviderCoolingDownError(
                "provider models are cooling down",
                model=self.fallback_models[-1] if self.fallback_models else self.model,
            )
            error.provider_id = self.provider_id
            error.quota_group_id = self.quota_group_id
            raise error

        failures: list[ProviderFailure] = []
        for index, model in enumerate(models):
            started = time.monotonic()
            try:
                text = await self._clean_model(model, raw_text, system_prompt)
            except ProviderError as error:
                error.provider_id = self.provider_id
                error.model = model
                error.quota_group_id = self.quota_group_id
                error.elapsed_ms = round((time.monotonic() - started) * 1_000)
                error.route_index = index
                error.prior_failures = tuple(failures)
                has_fallback = index + 1 < len(models)
                if not isinstance(error, ProviderHTTPError) or (
                    error.status_code not in TRANSIENT_FALLBACK_STATUSES
                ):
                    raise
                self._cooldowns[model] = time.monotonic() + self.cooldown_seconds
                if not has_fallback:
                    raise
                failures.append(error)
            else:
                return ProviderOutput(
                    text=text,
                    provider_id=self.provider_id,
                    model_id=model,
                    elapsed_ms=round((time.monotonic() - started) * 1_000),
                    route_index=index,
                    prior_failures=tuple(failures),
                )
        raise AssertionError("provider model selection was empty")

    async def _clean_model(self, model: str, raw_text: str, system_prompt: str) -> str:
        url = f"{self.endpoint}/models/{model}:generateContent"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"<SOURCE_TEXT>\n{raw_text}\n</SOURCE_TEXT>"}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "thinkingConfig": _thinking_config(model),
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    url,
                    params={"key": self.api_key},
                    json=payload,
                )
        except httpx.TimeoutException as error:
            raise ProviderTimeoutError("provider request timed out", model=model) from error
        except httpx.TransportError as error:
            raise ProviderTransportError("provider transport failure", model=model) from error
        if response.is_error:
            raise ProviderHTTPError(
                response.status_code,
                model=model,
                retry_after_seconds=_parse_retry_after(response.headers.get("Retry-After")),
            )
        try:
            response_payload = response.json()
        except json.JSONDecodeError as error:
            raise ProviderMalformedResponseError(
                "provider returned invalid JSON", model=model
            ) from error
        try:
            return _extract_text(response_payload)
        except (ProviderMalformedResponseError, ProviderRejectedOutputError) as error:
            error.model = model
            raise


def _thinking_config(model: str) -> dict[str, str | int]:
    if model.startswith("gemini-2.5-"):
        return {"thinkingBudget": 0}
    return {"thinkingLevel": "minimal"}


def _extract_text(payload: Any) -> str:
    if _response_was_rejected(payload):
        raise ProviderRejectedOutputError("provider rejected unsafe output", safety_policy=True)
    try:
        parts = payload["candidates"][0]["content"]["parts"]
        if not isinstance(parts, list):
            raise ProviderMalformedResponseError("Gemini returned malformed output")
        text = "".join(
            part["text"]
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    except (KeyError, IndexError, TypeError) as error:
        raise ProviderMalformedResponseError("Gemini returned malformed output") from error
    if not text.strip():
        raise ProviderMalformedResponseError("Gemini returned empty output")
    return text


def _response_was_rejected(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    prompt_feedback = payload.get("promptFeedback")
    if isinstance(prompt_feedback, dict) and prompt_feedback.get("blockReason"):
        return True
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        return False
    return candidates[0].get("finishReason") in {
        "SAFETY",
        "RECITATION",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
    }


def _validate_output(raw_text: str, cleaned_text: str) -> str:
    cleaned = cleaned_text.strip()
    if not cleaned:
        raise ProviderRejectedOutputError("The cleanup result was empty")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in cleaned):
        raise ProviderRejectedOutputError("The cleanup result contained control characters")
    maximum_length = max(len(raw_text) * 4, len(raw_text) + 1_000)
    if len(cleaned) > maximum_length:
        raise ProviderRejectedOutputError("The cleanup result expanded beyond the safety limit")
    return cleaned


@dataclass(frozen=True)
class CleanupService:
    provider: CleanupProvider | None
    model: str
    timeout_seconds: float
    provider_id: str = "unconfigured"

    async def clean(self, request: CleanupRequest, system_prompt: str) -> CleanupResult:
        raw_text = request.raw_text
        if not raw_text.strip():
            return self._result(raw_text, CleanupStatus.EMPTY_INPUT)
        if not request.enabled or self.provider is None:
            return self._result(raw_text, CleanupStatus.DISABLED)

        started = time.monotonic()
        category = "success"
        http_status: int | None = None
        selected_provider = self.provider.provider_id
        selected_model = self.model
        attempts: list[CleanupAttempt] = []
        try:
            provider_output = await asyncio.wait_for(
                self.provider.clean(raw_text, system_prompt),
                timeout=self.timeout_seconds,
            )
            selected_provider = provider_output.provider_id
            selected_model = provider_output.model_id
            attempts.extend(_failure_attempt(failure) for failure in provider_output.prior_failures)
            try:
                cleaned_text = _validate_output(raw_text, provider_output.text)
            except ProviderRejectedOutputError as error:
                error.provider_id = selected_provider
                error.model = selected_model
                error.elapsed_ms = provider_output.elapsed_ms
                error.route_index = provider_output.route_index
                raise
            attempts.append(_success_attempt(provider_output))
        except asyncio.CancelledError:
            category = "cancelled"
            raise
        except (TimeoutError, httpx.TimeoutException):
            failure = ProviderTimeoutError("cleanup deadline exceeded", model=selected_model)
            failure.provider_id = selected_provider
            failure.elapsed_ms = round((time.monotonic() - started) * 1_000)
            attempts.append(_failure_attempt(failure))
            category = failure.failure_class
            result = self._result(
                raw_text,
                CleanupStatus.TIMEOUT,
                error=SafeError(
                    code="cleanup_timeout",
                    message="Cleanup did not finish before the time limit.",
                    retry_action="Retry cleanup or continue with Original.",
                ),
                provider=selected_provider,
                attempts=attempts,
            )
        except ProviderError as error:
            selected_provider = error.provider_id or selected_provider
            selected_model = error.model or selected_model
            error.provider_id = selected_provider
            error.model = selected_model
            http_status = error.http_status
            attempts.extend(_failure_attempt(failure) for failure in error.prior_failures)
            attempts.append(_failure_attempt(error))
            category = error.failure_class
            status = (
                CleanupStatus.TIMEOUT
                if isinstance(error, ProviderTimeoutError)
                else CleanupStatus.PROVIDER_ERROR
            )
            result = self._result(
                raw_text,
                status,
                error=_safe_error(error),
                provider=selected_provider,
                model=selected_model,
                attempts=attempts,
            )
        except Exception:
            failure = ProviderError(
                "unexpected provider error",
                provider_id=selected_provider,
                model=selected_model,
                elapsed_ms=round((time.monotonic() - started) * 1_000),
            )
            attempts.append(_failure_attempt(failure))
            category = failure.failure_class
            result = self._result(
                raw_text,
                CleanupStatus.PROVIDER_ERROR,
                error=SafeError(
                    code="cleanup_provider_error",
                    message="The cleanup provider failed for an unknown reason.",
                    retry_action="Retry cleanup or continue with Original.",
                ),
                provider=selected_provider,
                attempts=attempts,
            )
        else:
            status = CleanupStatus.UNCHANGED if cleaned_text == raw_text else CleanupStatus.CLEANED
            result = self._result(
                cleaned_text,
                status,
                provider=selected_provider,
                model=selected_model,
                attempts=attempts,
            )
        finally:
            _log_cleanup(
                provider=selected_provider,
                model=selected_model,
                category=str(category),
                http_status=http_status,
                duration_ms=round((time.monotonic() - started) * 1_000),
                input_length=len(raw_text),
                attempts=attempts,
            )
        return result

    def _result(
        self,
        text: str,
        status: CleanupStatus,
        *,
        error: SafeError | None = None,
        provider: str | None = None,
        model: str | None = None,
        attempts: list[CleanupAttempt] | None = None,
    ) -> CleanupResult:
        return CleanupResult(
            cleaned_text=text,
            status=status,
            provider=_safe_identifier(
                provider
                or (self.provider.provider_id if self.provider is not None else self.provider_id)
            ),
            model=_safe_model(model or self.model),
            error=error,
            attempts=attempts or [],
        )


def _safe_error(error: ProviderError) -> SafeError:
    if isinstance(error, ProviderTimeoutError):
        return SafeError(
            code="cleanup_timeout",
            message="Cleanup did not finish before the time limit.",
            retry_action="Retry cleanup or continue with Original.",
        )
    if error.failure_class is ProviderFailureClass.PERMANENT_CONFIGURATION:
        auth_error = error.http_status in {401, 403}
        return SafeError(
            code="cleanup_provider_auth_error" if auth_error else "cleanup_provider_http_error",
            message=(
                "The cleanup provider rejected the configured access."
                if auth_error
                else "The cleanup provider rejected the request."
            ),
            retry_action=(
                "Check the provider credential and model access, then retry cleanup."
                if auth_error
                else "Check the provider model configuration, then retry cleanup."
            ),
            http_status=error.http_status,
        )
    if isinstance(error, ProviderCoolingDownError):
        return SafeError(
            code="cleanup_provider_temporarily_unavailable",
            message="The cleanup provider models are temporarily unavailable.",
            retry_action="Wait for provider cooldown, then retry cleanup.",
        )
    if error.failure_class in {
        ProviderFailureClass.TEMPORARY_QUOTA,
        ProviderFailureClass.PERMANENT_QUOTA,
    }:
        return SafeError(
            code="cleanup_provider_quota_error",
            message="The cleanup provider rate or quota limit was reached.",
            retry_action="Wait for provider capacity or quota, then retry cleanup.",
            http_status=error.http_status,
        )
    if error.failure_class is ProviderFailureClass.TRANSIENT_ROUTE:
        if isinstance(error, ProviderTransportError):
            return SafeError(
                code="cleanup_provider_transport_error",
                message="The cleanup provider could not be reached.",
                retry_action=(
                    "Check the network connection, retry cleanup, or continue with Original."
                ),
                http_status=error.http_status,
            )
        return SafeError(
            code="cleanup_provider_server_error",
            message="The cleanup provider is temporarily unavailable.",
            retry_action="Retry cleanup later or continue with Original.",
            http_status=error.http_status,
        )
    if error.failure_class is ProviderFailureClass.INVALID_OUTPUT:
        if isinstance(error, ProviderMalformedResponseError):
            return SafeError(
                code="cleanup_provider_malformed_response",
                message="The cleanup provider returned an unreadable response.",
                retry_action="Retry cleanup or continue with Original.",
                http_status=error.http_status,
            )
        return SafeError(
            code="cleanup_output_rejected",
            message="The cleanup result was rejected by safety checks.",
            retry_action="Revise the Original, retry cleanup, or continue with Original.",
            http_status=error.http_status,
        )
    if error.failure_class is ProviderFailureClass.SAFETY_POLICY:
        return SafeError(
            code="cleanup_output_rejected",
            message="The cleanup result was rejected by safety checks.",
            retry_action="Revise the Original or continue with Original.",
            http_status=error.http_status,
        )
    if isinstance(error, ProviderHTTPError):
        return SafeError(
            code="cleanup_provider_http_error",
            message="The cleanup provider rejected the request.",
            retry_action="Check the provider model configuration, then retry cleanup.",
            http_status=error.http_status,
        )
    return SafeError(
        code="cleanup_provider_error",
        message="The cleanup provider failed for an unknown reason.",
        retry_action="Retry cleanup or continue with Original.",
        http_status=error.http_status,
    )


def _log_cleanup(
    *,
    provider: str,
    model: str,
    category: str,
    http_status: int | None,
    duration_ms: int,
    input_length: int,
    attempts: list[CleanupAttempt],
) -> None:
    logger.info(
        "cleanup_result %s",
        json.dumps(
            {
                "provider": _safe_identifier(provider),
                "model": _safe_model(model),
                "category": category,
                "http_status": http_status,
                "duration_ms": duration_ms,
                "input_length": input_length,
                "attempts": [attempt.model_dump(mode="json") for attempt in attempts],
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
    )


def _safe_model(model: str) -> str:
    return model if MODEL_IDENTIFIER.fullmatch(model) else "invalid"


def _safe_identifier(identifier: str | None) -> str:
    return identifier if identifier and SAFE_IDENTIFIER.fullmatch(identifier) else "invalid"


def _success_attempt(output: ProviderOutput) -> CleanupAttempt:
    return CleanupAttempt(
        provider=_safe_identifier(output.provider_id),
        model=_safe_model(output.model_id),
        outcome="success",
        elapsed_ms=max(0, output.elapsed_ms),
        route_index=max(0, output.route_index),
        input_tokens=output.input_tokens,
        output_tokens=output.output_tokens,
    )


def _failure_attempt(error: ProviderFailure) -> CleanupAttempt:
    return CleanupAttempt(
        provider=_safe_identifier(error.provider_id),
        model=_safe_model(error.model or "invalid"),
        outcome="failure",
        elapsed_ms=max(0, error.elapsed_ms),
        route_index=max(0, error.route_index),
        failure_class=error.failure_class,
        provider_code=_safe_identifier(error.provider_code),
        http_status=error.http_status,
        retry_after_seconds=error.retry_after_seconds,
        quota_group_id=(
            _safe_identifier(error.quota_group_id) if error.quota_group_id is not None else None
        ),
    )


def _http_failure_class(status_code: int) -> ProviderFailureClass:
    if status_code == 429:
        return ProviderFailureClass.TEMPORARY_QUOTA
    if status_code in {400, 401, 403, 404}:
        return ProviderFailureClass.PERMANENT_CONFIGURATION
    if status_code in {408, 500, 502, 503, 504}:
        return ProviderFailureClass.TRANSIENT_ROUTE
    return ProviderFailureClass.UNKNOWN


def _parse_retry_after(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        seconds = int(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            seconds = round(retry_at.timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return None
    return seconds if 0 <= seconds <= 86_400 else None
