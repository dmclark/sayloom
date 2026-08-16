"""Fail-open source-text cleanup using Gemini."""

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field


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


class CleanupResult(BaseModel):
    cleaned_text: str
    status: CleanupStatus
    provider: str = "gemini"
    model: str


class CleanupProvider(Protocol):
    provider_id: str
    model: str

    async def clean(self, raw_text: str, system_prompt: str) -> str: ...


class ProviderOutputError(ValueError):
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
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                url,
                params={"key": self.api_key},
                json=payload,
            )
            response.raise_for_status()
        return _extract_text(response.json())


def _extract_text(payload: Any) -> str:
    try:
        parts = payload["candidates"][0]["content"]["parts"]
        if not isinstance(parts, list):
            raise ProviderOutputError("Gemini returned malformed output")
        text = "".join(
            part["text"]
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    except (KeyError, IndexError, TypeError) as error:
        raise ProviderOutputError("Gemini returned malformed output") from error
    if not text.strip():
        raise ProviderOutputError("Gemini returned empty output")
    return text


def _validate_output(raw_text: str, cleaned_text: str) -> str:
    cleaned = cleaned_text.strip()
    if not cleaned:
        raise ProviderOutputError("The cleanup result was empty")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in cleaned):
        raise ProviderOutputError("The cleanup result contained control characters")
    maximum_length = max(len(raw_text) * 4, len(raw_text) + 1_000)
    if len(cleaned) > maximum_length:
        raise ProviderOutputError("The cleanup result expanded beyond the safety limit")
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

        try:
            provider_output = await asyncio.wait_for(
                self.provider.clean(raw_text, system_prompt),
                timeout=self.timeout_seconds,
            )
            cleaned_text = _validate_output(raw_text, provider_output)
        except (TimeoutError, httpx.TimeoutException):
            return self._result(raw_text, CleanupStatus.TIMEOUT)
        except Exception:
            return self._result(raw_text, CleanupStatus.PROVIDER_ERROR)

        status = CleanupStatus.UNCHANGED if cleaned_text == raw_text else CleanupStatus.CLEANED
        return self._result(cleaned_text, status)

    def _result(self, text: str, status: CleanupStatus) -> CleanupResult:
        return CleanupResult(
            cleaned_text=text,
            status=status,
            provider="gemini",
            model=self.model,
        )
