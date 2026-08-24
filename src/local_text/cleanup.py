"""Fail-open source-text cleanup using Gemini."""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("uvicorn.error.local_text.cleanup")
MODEL_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


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


class CleanupResult(BaseModel):
    cleaned_text: str
    status: CleanupStatus
    provider: str = "gemini"
    model: str
    error: SafeError | None = None


class CleanupProvider(Protocol):
    provider_id: str
    model: str

    async def clean(self, raw_text: str, system_prompt: str) -> str: ...


class ProviderHTTPError(RuntimeError):
    """The provider rejected a request with an HTTP response."""

    def __init__(self, status_code: int) -> None:
        super().__init__("provider HTTP error")
        self.status_code = status_code


class ProviderTransportError(RuntimeError):
    """The provider could not be reached."""


class ProviderMalformedResponseError(ValueError):
    """The provider returned a response that could not be interpreted."""


class ProviderRejectedOutputError(ValueError):
    """The provider returned a response that is unsafe to use as outgoing text."""


@dataclass(frozen=True)
class GeminiProvider:
    api_key: str
    model: str
    timeout_seconds: float = 8.0
    endpoint: str = "https://generativelanguage.googleapis.com/v1beta"
    provider_id: str = "gemini"

    async def clean(self, raw_text: str, system_prompt: str) -> str:
        url = f"{self.endpoint}/models/{self.model}:generateContent"
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
                "thinkingConfig": {"thinkingLevel": "minimal"},
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    url,
                    params={"key": self.api_key},
                    json=payload,
                )
        except httpx.TimeoutException:
            raise
        except httpx.TransportError as error:
            raise ProviderTransportError("provider transport failure") from error
        if response.is_error:
            raise ProviderHTTPError(response.status_code)
        try:
            response_payload = response.json()
        except json.JSONDecodeError as error:
            raise ProviderMalformedResponseError("provider returned invalid JSON") from error
        return _extract_text(response_payload)


def _extract_text(payload: Any) -> str:
    if _response_was_rejected(payload):
        raise ProviderRejectedOutputError("provider rejected unsafe output")
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

    async def clean(self, request: CleanupRequest, system_prompt: str) -> CleanupResult:
        raw_text = request.raw_text
        if not raw_text.strip():
            return self._result(raw_text, CleanupStatus.EMPTY_INPUT)
        if not request.enabled or self.provider is None:
            return self._result(raw_text, CleanupStatus.DISABLED)

        started = time.monotonic()
        category = "success"
        http_status: int | None = None
        try:
            provider_output = await asyncio.wait_for(
                self.provider.clean(raw_text, system_prompt),
                timeout=self.timeout_seconds,
            )
            cleaned_text = _validate_output(raw_text, provider_output)
        except (TimeoutError, httpx.TimeoutException):
            category = "timeout"
            result = self._result(
                raw_text,
                CleanupStatus.TIMEOUT,
                error=SafeError(
                    code="cleanup_timeout",
                    message="Cleanup did not finish before the time limit.",
                    retry_action="Retry cleanup or continue with Original.",
                ),
            )
        except ProviderHTTPError as error:
            http_status = error.status_code
            category, safe_error = _http_failure(error.status_code)
            result = self._result(
                raw_text,
                CleanupStatus.PROVIDER_ERROR,
                error=safe_error,
            )
        except ProviderTransportError:
            category = "transport"
            result = self._result(
                raw_text,
                CleanupStatus.PROVIDER_ERROR,
                error=SafeError(
                    code="cleanup_provider_transport_error",
                    message="The cleanup provider could not be reached.",
                    retry_action=(
                        "Check the network connection, retry cleanup, or continue with Original."
                    ),
                ),
            )
        except ProviderMalformedResponseError:
            category = "malformed_response"
            result = self._result(
                raw_text,
                CleanupStatus.PROVIDER_ERROR,
                error=SafeError(
                    code="cleanup_provider_malformed_response",
                    message="The cleanup provider returned an unreadable response.",
                    retry_action="Retry cleanup or continue with Original.",
                ),
            )
        except ProviderRejectedOutputError:
            category = "rejected_output"
            result = self._result(
                raw_text,
                CleanupStatus.PROVIDER_ERROR,
                error=SafeError(
                    code="cleanup_output_rejected",
                    message="The cleanup result was rejected by safety checks.",
                    retry_action="Revise the Original, retry cleanup, or continue with Original.",
                ),
            )
        except Exception:
            category = "unexpected_provider_error"
            result = self._result(
                raw_text,
                CleanupStatus.PROVIDER_ERROR,
                error=SafeError(
                    code="cleanup_provider_error",
                    message="The cleanup provider failed for an unknown reason.",
                    retry_action="Retry cleanup or continue with Original.",
                ),
            )
        else:
            status = CleanupStatus.UNCHANGED if cleaned_text == raw_text else CleanupStatus.CLEANED
            result = self._result(cleaned_text, status)
        finally:
            _log_cleanup(
                provider=self.provider.provider_id,
                model=self.model,
                category=category,
                http_status=http_status,
                duration_ms=round((time.monotonic() - started) * 1_000),
                input_length=len(raw_text),
            )
        return result

    def _result(
        self,
        text: str,
        status: CleanupStatus,
        *,
        error: SafeError | None = None,
    ) -> CleanupResult:
        return CleanupResult(
            cleaned_text=text,
            status=status,
            provider="gemini",
            model=self.model,
            error=error,
        )


def _http_failure(status_code: int) -> tuple[str, SafeError]:
    if status_code in {401, 403}:
        return "http_auth", SafeError(
            code="cleanup_provider_auth_error",
            message="The cleanup provider rejected the configured access.",
            retry_action="Check the provider credential and model access, then retry cleanup.",
            http_status=status_code,
        )
    if status_code == 429:
        return "http_quota", SafeError(
            code="cleanup_provider_quota_error",
            message="The cleanup provider rate or quota limit was reached.",
            retry_action="Wait for provider capacity or quota, then retry cleanup.",
            http_status=status_code,
        )
    if 500 <= status_code <= 599:
        return "http_server", SafeError(
            code="cleanup_provider_server_error",
            message="The cleanup provider is temporarily unavailable.",
            retry_action="Retry cleanup later or continue with Original.",
            http_status=status_code,
        )
    return "http_rejection", SafeError(
        code="cleanup_provider_http_error",
        message="The cleanup provider rejected the request.",
        retry_action="Check the provider model configuration, then retry cleanup.",
        http_status=status_code,
    )


def _log_cleanup(
    *,
    provider: str,
    model: str,
    category: str,
    http_status: int | None,
    duration_ms: int,
    input_length: int,
) -> None:
    logger.info(
        "cleanup_result %s",
        json.dumps(
            {
                "provider": provider,
                "model": model if MODEL_IDENTIFIER.fullmatch(model) else "invalid",
                "category": category,
                "http_status": http_status,
                "duration_ms": duration_ms,
                "input_length": input_length,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
    )
