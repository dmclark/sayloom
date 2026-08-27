"""Fail-open source-text cleanup with provider-neutral HTTP adapters."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("uvicorn.error.local_text.cleanup")
MODEL_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
GEMINI_37_FLASH = "gemini-3.7-flash"
OPENAI_GPT_56_LUNA = "gpt-5.6-luna"
MAX_CLEANED_TEXT_CHARACTERS = 100_000
GEMINI_MAX_OUTPUT_TOKENS = 65_536
OPENAI_MAX_OUTPUT_TOKENS = 128_000
EVALUATION_TOTAL_BUDGET_SECONDS = 20.0
EVALUATION_PRIMARY_ATTEMPT_SECONDS = 12.0
EVALUATION_FALLBACK_ATTEMPT_SECONDS = 8.0
MINIMUM_ATTEMPT_SECONDS = 0.5
ROUTE_BREAKER_BASE_SECONDS = 15.0
ROUTE_BREAKER_MAX_SECONDS = 300.0
QUOTA_BREAKER_BASE_SECONDS = 60.0
QUOTA_BREAKER_MAX_SECONDS = 900.0
CLEANED_TEXT_SCHEMA = {
    "type": "object",
    "properties": {
        "cleaned_text": {
            "type": "string",
            "description": "The cleaned version of the supplied source text.",
            "maxLength": MAX_CLEANED_TEXT_CHARACTERS,
        }
    },
    "required": ["cleaned_text"],
    "additionalProperties": False,
}
OPENAI_PERMANENT_QUOTA_CODES = {
    "credit_balance_exhausted",
    "organization_spend_limit_exceeded",
    "organization_usage_limit_exceeded",
    "project_spend_limit_exceeded",
}


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


class RouteFailureAction(StrEnum):
    ADVANCE = "advance"
    TERMINAL = "terminal"


ROUTE_FAILURE_ACTIONS = {
    ProviderFailureClass.TRANSIENT_ROUTE: RouteFailureAction.ADVANCE,
    ProviderFailureClass.TEMPORARY_QUOTA: RouteFailureAction.ADVANCE,
    ProviderFailureClass.PERMANENT_QUOTA: RouteFailureAction.ADVANCE,
    ProviderFailureClass.PERMANENT_CONFIGURATION: RouteFailureAction.ADVANCE,
    ProviderFailureClass.INVALID_OUTPUT: RouteFailureAction.ADVANCE,
    ProviderFailureClass.SAFETY_POLICY: RouteFailureAction.TERMINAL,
    ProviderFailureClass.INVALID_LOCAL_REQUEST: RouteFailureAction.TERMINAL,
    ProviderFailureClass.UNKNOWN: RouteFailureAction.TERMINAL,
}


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
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        attempted: bool = True,
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
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.attempted = attempted


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


class ProviderConfigurationError(ProviderError):
    """The adapter is missing required local configuration."""

    def __init__(self, message: str, *, model: str | None = None) -> None:
        super().__init__(
            message,
            failure_class=ProviderFailureClass.PERMANENT_CONFIGURATION,
            model=model,
            provider_code="missing_api_key",
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
            failure_class=ProviderFailureClass.TRANSIENT_ROUTE,
            model=model,
            provider_code="circuit_open",
            attempted=False,
        )


class ProviderBusyError(ProviderError):
    """The local no-queue cleanup bulkhead has no capacity."""

    def __init__(self, message: str, *, model: str | None = None) -> None:
        super().__init__(
            message,
            failure_class=ProviderFailureClass.TRANSIENT_ROUTE,
            model=model,
            provider_code="bulkhead_full",
            attempted=False,
        )


@dataclass(frozen=True)
class GeminiAdapter:
    """One Gemini model and one HTTP request per cleanup call."""

    api_key: str
    model: str
    client: httpx.AsyncClient
    endpoint: str = "https://generativelanguage.googleapis.com/v1beta"
    provider_id: str = "gemini"
    quota_group_id: str | None = None

    def __post_init__(self) -> None:
        if not MODEL_IDENTIFIER.fullmatch(self.model):
            raise ValueError("provider model identifier is invalid")
        if self.quota_group_id is not None and not SAFE_IDENTIFIER.fullmatch(self.quota_group_id):
            raise ValueError("provider quota group identifier is invalid")

    async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
        started = time.monotonic()
        if not self.api_key:
            error = ProviderConfigurationError(
                "provider API key is not configured", model=self.model
            )
            _attribute_failure(error, self, started)
            raise error
        url = f"{self.endpoint}/models/{self.model}:generateContent"
        generation_config = {
            "thinkingConfig": _thinking_config(self.model),
            "maxOutputTokens": _output_token_cap(
                raw_text,
                provider_max=GEMINI_MAX_OUTPUT_TOKENS,
                thinking_headroom=2_048,
            ),
            "responseMimeType": "application/json",
            "responseJsonSchema": CLEANED_TEXT_SCHEMA,
        }
        if self.model != GEMINI_37_FLASH:
            generation_config["temperature"] = 0.2
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"<SOURCE_TEXT>\n{raw_text}\n</SOURCE_TEXT>"}],
                }
            ],
            "generationConfig": generation_config,
        }
        try:
            response = await self.client.post(
                url,
                headers={"x-goog-api-key": self.api_key},
                json=payload,
            )
        except httpx.TimeoutException as error:
            failure = ProviderTimeoutError("provider request timed out", model=self.model)
            _attribute_failure(failure, self, started)
            raise failure from error
        except httpx.TransportError as error:
            failure = ProviderTransportError("provider transport failure", model=self.model)
            _attribute_failure(failure, self, started)
            raise failure from error
        if response.is_error:
            error = ProviderHTTPError(
                response.status_code,
                model=self.model,
                provider_code=_provider_error_code(response),
                retry_after_seconds=_parse_retry_after(response.headers.get("Retry-After")),
            )
            _attribute_failure(error, self, started)
            raise error
        try:
            response_payload = response.json()
        except json.JSONDecodeError as error:
            failure = ProviderMalformedResponseError(
                "provider returned invalid JSON", model=self.model
            )
            _attribute_failure(failure, self, started)
            raise failure from error
        input_tokens, output_tokens = _gemini_usage(response_payload)
        try:
            text = _extract_gemini_text(response_payload)
            cleaned_text = _parse_cleaned_text(text)
        except (ProviderMalformedResponseError, ProviderRejectedOutputError) as error:
            _attribute_failure(error, self, started)
            error.input_tokens = input_tokens
            error.output_tokens = output_tokens
            raise
        return ProviderOutput(
            text=cleaned_text,
            provider_id=self.provider_id,
            model_id=self.model,
            elapsed_ms=_elapsed_ms(started),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


@dataclass(frozen=True)
class OpenAIAdapter:
    """One OpenAI model and one HTTP request per cleanup call."""

    api_key: str
    client: httpx.AsyncClient
    model: str = OPENAI_GPT_56_LUNA
    endpoint: str = "https://api.openai.com/v1/responses"
    provider_id: str = "openai"
    quota_group_id: str | None = None

    def __post_init__(self) -> None:
        if self.model != OPENAI_GPT_56_LUNA:
            raise ValueError("OpenAI adapter supports only gpt-5.6-luna")
        if self.quota_group_id is not None and not SAFE_IDENTIFIER.fullmatch(self.quota_group_id):
            raise ValueError("provider quota group identifier is invalid")

    async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
        started = time.monotonic()
        if not self.api_key:
            error = ProviderConfigurationError(
                "provider API key is not configured", model=self.model
            )
            _attribute_failure(error, self, started)
            raise error
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"<SOURCE_TEXT>\n{raw_text}\n</SOURCE_TEXT>",
                },
            ],
            "max_output_tokens": _output_token_cap(
                raw_text,
                provider_max=OPENAI_MAX_OUTPUT_TOKENS,
            ),
            "reasoning": {"effort": "none"},
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "cleanup_result",
                    "strict": True,
                    "schema": CLEANED_TEXT_SCHEMA,
                }
            },
        }
        try:
            response = await self.client.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
        except httpx.TimeoutException as error:
            failure = ProviderTimeoutError("provider request timed out", model=self.model)
            _attribute_failure(failure, self, started)
            raise failure from error
        except httpx.TransportError as error:
            failure = ProviderTransportError("provider transport failure", model=self.model)
            _attribute_failure(failure, self, started)
            raise failure from error
        if response.is_error:
            provider_code = _provider_error_code(response)
            error = ProviderHTTPError(
                response.status_code,
                model=self.model,
                provider_code=provider_code,
                retry_after_seconds=_parse_retry_after(response.headers.get("Retry-After")),
            )
            if provider_code in OPENAI_PERMANENT_QUOTA_CODES:
                error.failure_class = ProviderFailureClass.PERMANENT_QUOTA
            _attribute_failure(error, self, started)
            raise error
        try:
            response_payload = response.json()
        except json.JSONDecodeError as error:
            failure = ProviderMalformedResponseError(
                "provider returned invalid JSON", model=self.model
            )
            _attribute_failure(failure, self, started)
            raise failure from error
        input_tokens, output_tokens = _openai_usage(response_payload)
        try:
            text = _extract_openai_text(response_payload)
            cleaned_text = _parse_cleaned_text(text)
        except (ProviderMalformedResponseError, ProviderRejectedOutputError) as error:
            _attribute_failure(error, self, started)
            error.input_tokens = input_tokens
            error.output_tokens = output_tokens
            raise
        return ProviderOutput(
            text=cleaned_text,
            provider_id=self.provider_id,
            model_id=self.model,
            elapsed_ms=_elapsed_ms(started),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


@dataclass(frozen=True)
class CleanupRoute:
    """One configured adapter/model attempt in a sequential route."""

    adapter: CleanupProvider
    attempt_budget_seconds: float
    quota_group_id: str

    def __post_init__(self) -> None:
        if not math.isfinite(self.attempt_budget_seconds) or self.attempt_budget_seconds <= 0:
            raise ValueError("route attempt budget must be positive and finite")
        if not SAFE_IDENTIFIER.fullmatch(self.quota_group_id):
            raise ValueError("provider quota group identifier is invalid")
        if not SAFE_IDENTIFIER.fullmatch(self.adapter.provider_id):
            raise ValueError("provider identifier is invalid")
        if not MODEL_IDENTIFIER.fullmatch(self.adapter.model):
            raise ValueError("provider model identifier is invalid")
        adapter_quota_group = getattr(self.adapter, "quota_group_id", None)
        if adapter_quota_group is not None and adapter_quota_group != self.quota_group_id:
            raise ValueError("route and adapter quota groups must match")

    @property
    def provider_id(self) -> str:
        return self.adapter.provider_id

    @property
    def model(self) -> str:
        return self.adapter.model


@dataclass
class _BreakerState:
    open_until: float = 0.0
    failure_count: int = 0
    probe_in_flight: bool = False
    permanently_disabled: bool = False
    base_delay_seconds: float = 0.0


class SequentialCleanupProvider:
    """Route one cleanup through bounded, breaker-aware single-request adapters."""

    def __init__(
        self,
        routes: tuple[CleanupRoute, ...],
        *,
        total_budget_seconds: float,
        minimum_attempt_seconds: float = MINIMUM_ATTEMPT_SECONDS,
        max_active_cleanups: int = 2,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[float], float] | None = None,
        timeout_runner: Callable[
            [Awaitable[ProviderOutput], float], Awaitable[ProviderOutput]
        ] = asyncio.wait_for,
        output_validator: Callable[[str, str], str] | None = None,
    ) -> None:
        if not routes:
            raise ValueError("at least one cleanup route is required")
        if not math.isfinite(total_budget_seconds) or total_budget_seconds <= 0:
            raise ValueError("total budget must be positive and finite")
        if not math.isfinite(minimum_attempt_seconds) or minimum_attempt_seconds <= 0:
            raise ValueError("minimum attempt budget must be positive and finite")
        if max_active_cleanups < 1:
            raise ValueError("cleanup capacity must be at least one")
        self.routes = routes
        self.provider_id = routes[0].provider_id
        self.model = routes[0].model
        self.total_budget_seconds = total_budget_seconds
        self.minimum_attempt_seconds = minimum_attempt_seconds
        self.max_active_cleanups = max_active_cleanups
        self._clock = clock
        self._jitter = jitter or _jitter_delay
        self._timeout_runner = timeout_runner
        self._output_validator = output_validator or _validate_output
        self._route_breakers = [_BreakerState() for _route in routes]
        self._quota_breakers = {
            route.quota_group_id: _BreakerState() for route in routes
        }
        self._active_cleanups = 0

    async def clean(self, raw_text: str, system_prompt: str) -> ProviderOutput:
        if self._active_cleanups >= self.max_active_cleanups:
            error = ProviderBusyError("local cleanup capacity is full", model=self.model)
            error.provider_id = self.provider_id
            raise error
        self._active_cleanups += 1
        try:
            return await self._clean_with_routes(raw_text, system_prompt)
        finally:
            self._active_cleanups -= 1

    async def _clean_with_routes(self, raw_text: str, system_prompt: str) -> ProviderOutput:
        deadline = self._clock() + self.total_budget_seconds
        failures: list[ProviderFailure] = []
        last_failure: ProviderFailure | None = None
        for route_index, route in enumerate(self.routes):
            now = self._clock()
            remaining = deadline - now
            attempt_budget = min(route.attempt_budget_seconds, remaining)
            if attempt_budget < self.minimum_attempt_seconds:
                raise self._deadline_failure(route, route_index, failures)

            route_breaker = self._route_breakers[route_index]
            quota_breaker = self._quota_breakers[route.quota_group_id]
            route_half_open = _acquire_breaker(route_breaker, now)
            if route_half_open is None:
                continue
            quota_half_open = _acquire_breaker(quota_breaker, now)
            if quota_half_open is None:
                _release_probe(route_breaker, route_half_open)
                continue

            attempt_started = self._clock()
            try:
                output = await self._timeout_runner(
                    route.adapter.clean(raw_text, system_prompt), attempt_budget
                )
            except asyncio.CancelledError:
                _release_probe(route_breaker, route_half_open)
                _release_probe(quota_breaker, quota_half_open)
                raise
            except TimeoutError:
                failure = ProviderTimeoutError("provider request timed out", model=route.model)
                self._attribute_route_failure(failure, route, route_index, attempt_started)
            except ProviderFailure as error:
                failure = error
                self._attribute_route_failure(failure, route, route_index, attempt_started)
            except Exception as error:
                _release_probe(route_breaker, route_half_open)
                _release_probe(quota_breaker, quota_half_open)
                failure = ProviderFailure(
                    "unexpected provider route error",
                    provider_id=route.provider_id,
                    model=route.model,
                    elapsed_ms=_clock_elapsed_ms(self._clock, attempt_started),
                    quota_group_id=route.quota_group_id,
                    route_index=route_index,
                    prior_failures=tuple(failures),
                )
                raise failure from error
            else:
                try:
                    cleaned_text = self._output_validator(raw_text, output.text)
                except ProviderRejectedOutputError as error:
                    failure = error
                    self._attribute_route_failure(failure, route, route_index, attempt_started)
                    failure.input_tokens = output.input_tokens
                    failure.output_tokens = output.output_tokens
                else:
                    _record_breaker_success(route_breaker, route_half_open)
                    _record_breaker_success(quota_breaker, quota_half_open)
                    return ProviderOutput(
                        text=cleaned_text,
                        provider_id=route.provider_id,
                        model_id=route.model,
                        elapsed_ms=_clock_elapsed_ms(self._clock, attempt_started),
                        route_index=route_index,
                        input_tokens=output.input_tokens,
                        output_tokens=output.output_tokens,
                        prior_failures=tuple(failures),
                    )

            _release_probe(route_breaker, route_half_open)
            _release_probe(quota_breaker, quota_half_open)
            self._apply_failure_to_breakers(
                failure,
                route_breaker,
                quota_breaker,
                route_half_open=route_half_open,
                quota_half_open=quota_half_open,
            )
            failure.prior_failures = tuple(failures)
            last_failure = failure
            if ROUTE_FAILURE_ACTIONS[failure.failure_class] is RouteFailureAction.TERMINAL:
                raise failure
            failures.append(failure)
            if deadline - self._clock() < self.minimum_attempt_seconds:
                next_route = self.routes[min(route_index + 1, len(self.routes) - 1)]
                raise self._deadline_failure(next_route, route_index + 1, failures)

        if last_failure is not None:
            raise last_failure
        route = self.routes[-1]
        error = ProviderCoolingDownError("all cleanup routes are unavailable", model=route.model)
        error.provider_id = route.provider_id
        error.quota_group_id = route.quota_group_id
        error.route_index = len(self.routes) - 1
        raise error

    def _attribute_route_failure(
        self,
        failure: ProviderFailure,
        route: CleanupRoute,
        route_index: int,
        attempt_started: float,
    ) -> None:
        failure.provider_id = route.provider_id
        failure.model = route.model
        failure.elapsed_ms = _clock_elapsed_ms(self._clock, attempt_started)
        failure.quota_group_id = route.quota_group_id
        failure.route_index = route_index

    def _apply_failure_to_breakers(
        self,
        failure: ProviderFailure,
        route_breaker: _BreakerState,
        quota_breaker: _BreakerState,
        *,
        route_half_open: bool,
        quota_half_open: bool,
    ) -> None:
        now = self._clock()
        if failure.failure_class is ProviderFailureClass.TRANSIENT_ROUTE:
            self._open_breaker(
                route_breaker,
                now,
                base_seconds=ROUTE_BREAKER_BASE_SECONDS,
                max_seconds=ROUTE_BREAKER_MAX_SECONDS,
                half_open_failure=route_half_open,
            )
        elif failure.failure_class is ProviderFailureClass.TEMPORARY_QUOTA:
            retry_after = failure.retry_after_seconds
            self._open_breaker(
                quota_breaker,
                now,
                base_seconds=float(retry_after or QUOTA_BREAKER_BASE_SECONDS),
                max_seconds=QUOTA_BREAKER_MAX_SECONDS,
                half_open_failure=quota_half_open,
                minimum_seconds=float(retry_after or 0),
            )
        elif failure.failure_class is ProviderFailureClass.PERMANENT_CONFIGURATION:
            route_breaker.permanently_disabled = True
            if failure.http_status in {401, 403} or failure.provider_code == "missing_api_key":
                quota_breaker.permanently_disabled = True
        elif failure.failure_class is ProviderFailureClass.PERMANENT_QUOTA:
            quota_breaker.permanently_disabled = True

    def _open_breaker(
        self,
        state: _BreakerState,
        now: float,
        *,
        base_seconds: float,
        max_seconds: float,
        half_open_failure: bool,
        minimum_seconds: float = 0.0,
    ) -> None:
        if half_open_failure:
            state.failure_count += 1
        elif state.failure_count == 0:
            state.failure_count = 1
            state.base_delay_seconds = base_seconds
        else:
            return
        if state.base_delay_seconds == 0:
            state.base_delay_seconds = base_seconds
        exponential_delay = min(state.base_delay_seconds, max_seconds)
        remaining_failures = state.failure_count - 1
        while remaining_failures > 0 and exponential_delay < max_seconds:
            exponential_delay = min(exponential_delay * 2, max_seconds)
            remaining_failures -= 1
        backoff_delay = min(max(self._jitter(exponential_delay), 0.0), max_seconds)
        delay = max(backoff_delay, minimum_seconds)
        state.open_until = now + delay

    def _deadline_failure(
        self,
        route: CleanupRoute,
        route_index: int,
        failures: list[ProviderFailure],
    ) -> ProviderTimeoutError:
        error = ProviderTimeoutError("cleanup total deadline exhausted", model=route.model)
        error.provider_id = route.provider_id
        error.provider_code = "total_deadline"
        error.quota_group_id = route.quota_group_id
        error.route_index = min(route_index, len(self.routes) - 1)
        error.prior_failures = tuple(failures)
        error.attempted = False
        return error


def _acquire_breaker(state: _BreakerState, now: float) -> bool | None:
    if state.permanently_disabled or state.open_until > now:
        return None
    if state.failure_count == 0:
        return False
    if state.probe_in_flight:
        return None
    state.probe_in_flight = True
    return True


def _release_probe(state: _BreakerState, was_half_open: bool) -> None:
    if was_half_open:
        state.probe_in_flight = False


def _reset_breaker(state: _BreakerState) -> None:
    state.open_until = 0.0
    state.failure_count = 0
    state.probe_in_flight = False
    state.base_delay_seconds = 0.0


def _record_breaker_success(state: _BreakerState, was_half_open: bool) -> None:
    if not state.permanently_disabled and (was_half_open or state.failure_count == 0):
        _reset_breaker(state)
    else:
        _release_probe(state, was_half_open)


def _jitter_delay(delay: float) -> float:
    return random.uniform(delay * 0.9, delay * 1.1)


def _clock_elapsed_ms(clock: Callable[[], float], started: float) -> int:
    return max(0, round((clock() - started) * 1_000))


def _thinking_config(model: str) -> dict[str, str | int]:
    if model.startswith("gemini-2.5-"):
        return {"thinkingBudget": 0}
    if model == GEMINI_37_FLASH:
        return {"thinkingLevel": "low"}
    return {"thinkingLevel": "minimal"}


def _extract_gemini_text(payload: Any) -> str:
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


_extract_text = _extract_gemini_text


def _extract_openai_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise ProviderMalformedResponseError("OpenAI returned malformed output")
    output = payload.get("output")
    if not isinstance(output, list):
        raise ProviderMalformedResponseError("OpenAI returned malformed output")
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "refusal":
                raise ProviderRejectedOutputError(
                    "provider rejected unsafe output", safety_policy=True
                )
    if payload.get("status") == "incomplete":
        details = payload.get("incomplete_details")
        reason = details.get("reason") if isinstance(details, dict) else None
        raise ProviderRejectedOutputError(
            "provider did not complete structured output",
            safety_policy=reason == "content_filter",
        )
    if payload.get("status") != "completed":
        raise ProviderMalformedResponseError("OpenAI returned incomplete output")
    text_parts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        text_parts.extend(
            part["text"]
            for part in content
            if isinstance(part, dict)
            and part.get("type") == "output_text"
            and isinstance(part.get("text"), str)
        )
    text = "".join(text_parts)
    if not text.strip():
        raise ProviderMalformedResponseError("OpenAI returned empty output")
    return text


def _parse_cleaned_text(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ProviderMalformedResponseError(
            "provider returned invalid structured output"
        ) from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"cleaned_text"}
        or not isinstance(payload.get("cleaned_text"), str)
        or not payload["cleaned_text"].strip()
        or len(payload["cleaned_text"]) > MAX_CLEANED_TEXT_CHARACTERS
    ):
        raise ProviderMalformedResponseError("provider returned malformed structured output")
    return payload["cleaned_text"]


def _output_token_cap(
    raw_text: str,
    *,
    provider_max: int,
    thinking_headroom: int = 0,
) -> int:
    """Bound cleanup cost while allowing JSON framing and provider reasoning tokens.

    Cleanup may expand to the smaller of its semantic expansion limit and the absolute
    100,000-character contract. Two output characters per token is conservative for ordinary
    prose; 256 tokens cover JSON escaping/framing. Gemini low thinking receives a separate 2,048
    token allowance at its call site. Truncation is intentionally handled as invalid output.
    """
    allowed_characters = min(
        MAX_CLEANED_TEXT_CHARACTERS,
        max(len(raw_text) * 4, len(raw_text) + 1_000),
    )
    estimated_text_tokens = (allowed_characters + 1) // 2
    return min(provider_max, estimated_text_tokens + 256 + thinking_headroom)


def _gemini_usage(payload: Any) -> tuple[int | None, int | None]:
    usage = payload.get("usageMetadata") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return None, None
    return _optional_token_count(usage.get("promptTokenCount")), _optional_token_count(
        usage.get("candidatesTokenCount")
    )


def _openai_usage(payload: Any) -> tuple[int | None, int | None]:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return None, None
    return _optional_token_count(usage.get("input_tokens")), _optional_token_count(
        usage.get("output_tokens")
    )


def _optional_token_count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _provider_error_code(response: httpx.Response) -> str:
    fallback = f"http_{response.status_code}"
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return fallback
    error = payload.get("error") if isinstance(payload, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) and SAFE_IDENTIFIER.fullmatch(code) else fallback


def _attribute_failure(error: ProviderFailure, adapter: Any, started: float) -> None:
    error.provider_id = adapter.provider_id
    error.model = adapter.model
    error.quota_group_id = adapter.quota_group_id
    error.elapsed_ms = _elapsed_ms(started)


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1_000))


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
    if len(cleaned) > MAX_CLEANED_TEXT_CHARACTERS:
        raise ProviderRejectedOutputError("The cleanup result exceeded the character limit")
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
            if isinstance(self.provider, SequentialCleanupProvider):
                provider_output = await self.provider.clean(raw_text, system_prompt)
            else:
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
                error.input_tokens = provider_output.input_tokens
                error.output_tokens = provider_output.output_tokens
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
            if error.attempted:
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
    if isinstance(error, ProviderBusyError):
        return SafeError(
            code="cleanup_provider_temporarily_unavailable",
            message="Cleanup is temporarily unavailable.",
            retry_action="Retry cleanup shortly or continue with Original.",
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
        input_tokens=error.input_tokens,
        output_tokens=error.output_tokens,
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
