import asyncio
import base64
import hashlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

import local_text.cleanup as cleanup_module
from local_text.cleanup import (
    GEMINI_37_FLASH,
    OPENAI_GPT_56_LUNA,
    CleanupRequest,
    CleanupService,
    GeminiAdapter,
    OpenAIAdapter,
    ProviderOutput,
    _validate_output,
)
from local_text.cleanup_contract import (
    SNAPSHOT_VERSION,
    build_cleanup_contract_snapshot,
    canonical_json,
)
from local_text.config import Profile, Settings
from local_text.prompts import effective_system_prompt

REPOSITORY_ROOT = Path(__file__).parent.parent


def _decode(artifact: dict[str, object]) -> bytes:
    return base64.b64decode(str(artifact["canonical_bytes_base64"]))


def test_snapshot_canonically_freezes_the_shipped_cleanup_contract() -> None:
    configured_prompt = "Apply synthetic copy-editing guidance.\n"
    lock_bytes = b"synthetic-lock\n"

    snapshot = build_cleanup_contract_snapshot(
        configured_prompt,
        configured_prompt_id="synthetic-prompt-v7",
        dependency_lock_bytes=lock_bytes,
    )

    assert snapshot["snapshot_version"] == SNAPSHOT_VERSION
    assert snapshot["protocol_id"] == "cleanup-evaluation-benchmark-v2"
    assert snapshot["configured_prompt_id"] == "synthetic-prompt-v7"
    assert snapshot["effective_prompt_id"].startswith("sha256:")
    artifacts = snapshot["artifacts"]
    assert _decode(artifacts["configured_prompt"]) == configured_prompt.encode()
    assert _decode(artifacts["effective_prompt"]) == effective_system_prompt(
        configured_prompt
    ).encode()
    assert _decode(artifacts["dependency_lock"]) == lock_bytes
    for artifact in artifacts.values():
        assert artifact["sha256"] == hashlib.sha256(_decode(artifact)).hexdigest()
    validator_implementation = json.loads(_decode(artifacts["validator_implementation"]))
    assert validator_implementation["python_source"]["_validate_output"] == inspect.getsource(
        _validate_output
    )
    adapter_implementation = json.loads(_decode(artifacts["adapter_implementation"]))
    assert set(adapter_implementation["python_source"]) >= {
        "GeminiAdapter.clean",
        "OpenAIAdapter.clean",
    }

    assert snapshot["execution"] == {
        "deadline_seconds": 30,
        "fallback": False,
        "requests_per_case_per_arm": 1,
        "retries": 0,
    }
    assert snapshot["execution"]["deadline_seconds"] == Settings(
        profile=Profile.DEVELOPMENT
    ).cleanup_timeout_seconds
    assert snapshot["arms"][0]["request"] == {
        "api_mode": "generateContent",
        "endpoint": (
            "https://generativelanguage.googleapis.com/v1beta/"
            "models/gemini-3.7-flash:generateContent"
        ),
        "model": GEMINI_37_FLASH,
        "settings": {
            "explicit_temperature": False,
            "response_mime_type": "application/json",
            "thinking_level": "low",
        },
    }
    assert snapshot["arms"][1]["request"] == {
        "api_mode": "responses",
        "endpoint": "https://api.openai.com/v1/responses",
        "model": OPENAI_GPT_56_LUNA,
        "settings": {"reasoning_effort": "none", "store": False},
    }


def test_snapshot_validator_and_deadline_are_used_by_the_shipped_service(monkeypatch) -> None:
    class UnsafeProvider:
        provider_id = "synthetic"
        model = "synthetic-model"

        async def clean(self, original_text: str, system_prompt: str) -> ProviderOutput:
            return ProviderOutput(
                text="Novel wording.",
                provider_id=self.provider_id,
                model_id=self.model,
                elapsed_ms=1,
            )

    observed_timeouts: list[float] = []
    real_wait_for = cleanup_module.asyncio.wait_for

    async def observe_wait_for(awaitable, timeout):
        observed_timeouts.append(timeout)
        return await real_wait_for(awaitable, timeout)

    monkeypatch.setattr(cleanup_module.asyncio, "wait_for", observe_wait_for)
    snapshot = build_cleanup_contract_snapshot(
        "Synthetic guidance.", configured_prompt_id="synthetic", dependency_lock_bytes=b"lock"
    )
    service = CleanupService(
        provider=UnsafeProvider(),
        model="synthetic-model",
        timeout_seconds=Settings(profile=Profile.DEVELOPMENT).cleanup_timeout_seconds,
    )
    result = asyncio.run(
        service.clean(CleanupRequest(original_text="source words"), "Synthetic guidance.")
    )

    assert result.prepared_text == "source words"
    assert result.status == "provider_error"
    assert observed_timeouts == [snapshot["execution"]["deadline_seconds"]]


def test_snapshot_settings_and_framing_are_the_adapter_request_settings() -> None:
    requests: dict[str, httpx.Request] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        provider = "gemini" if "googleapis" in request.url.host else "openai"
        requests[provider] = request
        payload = (
            {"candidates": [{"content": {"parts": [{"text": '{"prepared_text":"x"}'}]}}]}
            if provider == "gemini"
            else {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"prepared_text":"x"}'}
                        ],
                    }
                ],
            }
        )
        return httpx.Response(200, json=payload)

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            await GeminiAdapter("synthetic-key", GEMINI_37_FLASH, client).clean("x", "prompt")
            await OpenAIAdapter("synthetic-key", client).clean("x", "prompt")

    asyncio.run(exercise())
    snapshot = build_cleanup_contract_snapshot(
        "prompt", configured_prompt_id="synthetic", dependency_lock_bytes=b"lock"
    )
    arms = {arm["provider"]: arm for arm in snapshot["arms"]}
    gemini_body = json.loads(requests["gemini"].content)
    openai_body = json.loads(requests["openai"].content)

    assert str(requests["gemini"].url) == arms["gemini"]["request"]["endpoint"]
    assert gemini_body["contents"][0]["parts"][0]["text"] == "<SOURCE_TEXT>\nx\n</SOURCE_TEXT>"
    assert gemini_body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert "temperature" not in gemini_body["generationConfig"]
    assert gemini_body["generationConfig"]["responseJsonSchema"] == snapshot["schema"]
    assert gemini_body["generationConfig"]["maxOutputTokens"] == arms["gemini"][
        "output_cap_examples"
    ]["one_character_source"]

    assert str(requests["openai"].url) == arms["openai"]["request"]["endpoint"]
    assert openai_body["input"][1]["content"] == "<SOURCE_TEXT>\nx\n</SOURCE_TEXT>"
    assert openai_body["reasoning"] == {"effort": "none"}
    assert openai_body["store"] is False
    assert openai_body["text"]["format"]["schema"] == snapshot["schema"]
    assert openai_body["max_output_tokens"] == arms["openai"]["output_cap_examples"][
        "one_character_source"
    ]


def test_snapshot_command_is_provider_free_and_emits_no_diagnostics(tmp_path: Path) -> None:
    marker = tmp_path / "provider-or-database-was-accessed"
    environment = {
        **os.environ,
        "LOCAL_TEXT_DATABASE_PATH": str(marker),
        "LOCAL_TEXT_CORRECTION_BENCHMARK_CASES_PATH": str(marker),
        "LOCAL_TEXT_GEMINI_API_KEY": "must-not-be-read",
        "LOCAL_TEXT_OPENAI_API_KEY": "must-not-be-read",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_text.cleanup_contract",
            "--configured-prompt-id",
            "synthetic-v1",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        input=b"Synthetic configured prompt.\n",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == b""
    assert not marker.exists()
    snapshot = json.loads(result.stdout)
    assert result.stdout == canonical_json(snapshot) + b"\n"
    assert b"must-not-be-read" not in result.stdout
    assert str(tmp_path).encode() not in result.stdout
