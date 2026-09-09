"""Provider-free snapshot of the shipped source-preserving cleanup contract."""

from __future__ import annotations

import argparse
import base64
import hashlib
import inspect
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from local_text.cleanup import (
    GEMINI_37_FLASH,
    GEMINI_ENDPOINT,
    GEMINI_MAX_OUTPUT_TOKENS,
    LEXICAL_WORD,
    MAX_PREPARED_TEXT_CHARACTERS,
    OPENAI_ENDPOINT,
    OPENAI_GPT_56_LUNA,
    OPENAI_MAX_OUTPUT_TOKENS,
    PREPARED_TEXT_SCHEMA,
    REMOVABLE_LEADING_FILLERS,
    SOURCE_TEXT_FRAME,
    GeminiAdapter,
    OpenAIAdapter,
    _lexical_word_forms,
    _output_token_cap,
    _thinking_config,
    _validate_output,
    frame_source_text,
    gemini_request_payload,
    openai_request_payload,
)
from local_text.prompts import effective_system_prompt

SNAPSHOT_VERSION = "cleanup-execution-contract-v1"
SCHEMA_VERSION = "cleanup-result-v1"
VALIDATOR_VERSION = "source-preserving-validator-v1"
OUTPUT_CAP_VERSION = "input-dependent-output-cap-v1"
REQUEST_IMPLEMENTATION_VERSION = "cleanup-provider-requests-v1"
PROMPT_IMPLEMENTATION_VERSION = "source-preserving-effective-prompt-v1"
SOURCE_FRAMING_VERSION = "source-text-xml-frame-v1"
BENCHMARK_DEADLINE_SECONDS = 30
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def canonical_json(value: object) -> bytes:
    """Encode canonical JSON used for every structured contract digest."""
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _artifact(value: bytes, *, version: str | None = None) -> dict[str, object]:
    artifact: dict[str, object] = {
        "canonical_bytes_base64": base64.b64encode(value).decode("ascii"),
        "encoding": "base64",
        "sha256": hashlib.sha256(value).hexdigest(),
    }
    if version is not None:
        artifact["version"] = version
    return artifact


def _implementation_bytes(
    functions: Sequence[Callable[..., object]],
    *,
    constants: dict[str, object],
) -> bytes:
    return canonical_json(
        {
            "constants": constants,
            "python_source": {
                function.__qualname__: inspect.getsource(function) for function in functions
            },
        }
    )


def build_cleanup_contract_snapshot(
    configured_prompt: str,
    *,
    configured_prompt_id: str,
    dependency_lock_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Build the benchmark contract without loading settings, state, or providers."""
    lock_bytes = (
        dependency_lock_bytes
        if dependency_lock_bytes is not None
        else (REPOSITORY_ROOT / "uv.lock").read_bytes()
    )
    effective_prompt = effective_system_prompt(configured_prompt)
    schema_bytes = canonical_json(PREPARED_TEXT_SCHEMA)
    validator_bytes = _implementation_bytes(
        (_validate_output, _lexical_word_forms),
        constants={
            "lexical_word_pattern": LEXICAL_WORD.pattern,
            "maximum_prepared_text_characters": MAX_PREPARED_TEXT_CHARACTERS,
            "removable_leading_fillers": sorted(REMOVABLE_LEADING_FILLERS),
        },
    )
    output_cap_bytes = _implementation_bytes(
        (_output_token_cap,),
        constants={"maximum_prepared_text_characters": MAX_PREPARED_TEXT_CHARACTERS},
    )
    request_implementation_bytes = _implementation_bytes(
        (
            frame_source_text,
            _thinking_config,
            gemini_request_payload,
            openai_request_payload,
            GeminiAdapter.clean,
            OpenAIAdapter.clean,
        ),
        constants={
            "gemini_endpoint": GEMINI_ENDPOINT,
            "gemini_max_output_tokens": GEMINI_MAX_OUTPUT_TOKENS,
            "openai_endpoint": OPENAI_ENDPOINT,
            "openai_max_output_tokens": OPENAI_MAX_OUTPUT_TOKENS,
            "source_text_frame": SOURCE_TEXT_FRAME,
        },
    )
    prompt_implementation_bytes = inspect.getsource(effective_system_prompt).encode("utf-8")
    configured_prompt_artifact = _artifact(configured_prompt.encode("utf-8"))
    effective_prompt_artifact = _artifact(effective_prompt.encode("utf-8"))
    gemini_payload = gemini_request_payload("x", effective_prompt, GEMINI_37_FLASH)
    gemini_generation = gemini_payload["generationConfig"]
    openai_payload = openai_request_payload("x", effective_prompt, OPENAI_GPT_56_LUNA)

    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "protocol_id": "cleanup-evaluation-benchmark-v2",
        "configured_prompt_id": configured_prompt_id,
        "effective_prompt_id": f"sha256:{effective_prompt_artifact['sha256']}",
        "artifacts": {
            "configured_prompt": configured_prompt_artifact,
            "dependency_lock": _artifact(lock_bytes),
            "effective_prompt": effective_prompt_artifact,
            "output_cap_implementation": _artifact(
                output_cap_bytes, version=OUTPUT_CAP_VERSION
            ),
            "prompt_implementation": _artifact(
                prompt_implementation_bytes, version=PROMPT_IMPLEMENTATION_VERSION
            ),
            "adapter_implementation": _artifact(
                request_implementation_bytes, version=REQUEST_IMPLEMENTATION_VERSION
            ),
            "schema": _artifact(schema_bytes, version=SCHEMA_VERSION),
            "source_framing": _artifact(
                SOURCE_TEXT_FRAME.encode("utf-8"), version=SOURCE_FRAMING_VERSION
            ),
            "validator_implementation": _artifact(
                validator_bytes, version=VALIDATOR_VERSION
            ),
        },
        "schema": PREPARED_TEXT_SCHEMA,
        "execution": {
            "deadline_seconds": BENCHMARK_DEADLINE_SECONDS,
            "fallback": False,
            "requests_per_case_per_arm": 1,
            "retries": 0,
        },
        "arms": [
            {
                "arm_id": "baseline_paid_gemini",
                "provider": "gemini",
                "deadline_seconds": BENCHMARK_DEADLINE_SECONDS,
                "provider_reported_version": None,
                "request": {
                    "api_mode": "generateContent",
                    "endpoint": f"{GEMINI_ENDPOINT}/models/{GEMINI_37_FLASH}:generateContent",
                    "model": GEMINI_37_FLASH,
                    "settings": {
                        "explicit_temperature": "temperature" in gemini_generation,
                        "response_mime_type": gemini_generation["responseMimeType"],
                        "thinking_level": gemini_generation["thinkingConfig"]["thinkingLevel"],
                    },
                },
                "output_cap": {
                    "provider_max_tokens": GEMINI_MAX_OUTPUT_TOKENS,
                    "thinking_headroom_tokens": 2_048,
                    "version": OUTPUT_CAP_VERSION,
                },
                "output_cap_examples": {
                    "one_character_source": gemini_generation["maxOutputTokens"]
                },
            },
            {
                "arm_id": "candidate_paid_openai",
                "provider": "openai",
                "deadline_seconds": BENCHMARK_DEADLINE_SECONDS,
                "provider_reported_version": None,
                "request": {
                    "api_mode": "responses",
                    "endpoint": OPENAI_ENDPOINT,
                    "model": OPENAI_GPT_56_LUNA,
                    "settings": {
                        "reasoning_effort": openai_payload["reasoning"]["effort"],
                        "store": openai_payload["store"],
                    },
                },
                "output_cap": {
                    "provider_max_tokens": OPENAI_MAX_OUTPUT_TOKENS,
                    "thinking_headroom_tokens": 0,
                    "version": OUTPUT_CAP_VERSION,
                },
                "output_cap_examples": {
                    "one_character_source": openai_payload["max_output_tokens"]
                },
            },
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanup-contract",
        description="Emit the provider-free canonical cleanup execution contract snapshot.",
    )
    parser.add_argument(
        "--configured-prompt-id",
        required=True,
        help="opaque identifier for the configured prompt bytes read from stdin",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        configured_prompt = sys.stdin.buffer.read().decode("utf-8")
        snapshot = build_cleanup_contract_snapshot(
            configured_prompt,
            configured_prompt_id=args.configured_prompt_id,
        )
    except (OSError, UnicodeDecodeError):
        print("error: unable to read canonical UTF-8 contract inputs", file=sys.stderr)
        raise SystemExit(1) from None
    sys.stdout.buffer.write(canonical_json(snapshot) + b"\n")


if __name__ == "__main__":
    main()
