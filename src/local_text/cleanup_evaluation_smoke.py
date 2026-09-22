"""Isolated preflight and synthetic smoke gate for the cleanup benchmark."""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from local_text.cleanup import (
    GeminiAdapter,
    OpenAIAdapter,
    ProviderOutput,
    ProviderRejectedOutputError,
    _validate_output,
    openai_request_payload,
)
from local_text.cleanup_contract import (
    BENCHMARK_DEADLINE_SECONDS,
    build_cleanup_contract_snapshot,
    canonical_json,
)

ARMS = ("baseline_paid_gemini", "candidate_paid_openai")
TOTAL_CALLS = 16
PRIVATE_CALLS_PER_ARM = 60
EVIDENCE_MAX_AGE = timedelta(hours=24)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LOWER_SHA256 = r"^[0-9a-f]{64}$"
SAFE_ID = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
REQUIRED_EVIDENCE = {
    "model_availability_and_version",
    "pricing",
    "retention_and_data_use",
    "account_controls",
    "openai_store_false",
}
PROVIDER_EVIDENCE_KINDS = {
    "gemini": REQUIRED_EVIDENCE - {"openai_store_false"} | {"quota_and_capacity"},
    "openai": REQUIRED_EVIDENCE | {"quota_and_capacity"},
}
OFFICIAL_HOSTS = {
    "gemini": frozenset({"ai.google.dev", "cloud.google.com", "support.google.com"}),
    "openai": frozenset({"openai.com", "platform.openai.com", "help.openai.com"}),
}

# These fixtures are public, invented, and deliberately unrelated to any operating corpus.
SYNTHETIC_FIXTURES = (
    ("unchanged", "The synthetic agenda is ready.", "The synthetic agenda is ready."),
    ("capitalization_only", "synthetic capitalization sample", "Synthetic capitalization sample"),
    ("punctuation_only", "Synthetic punctuation sample", "Synthetic punctuation sample."),
    ("apostrophe_only", "Its synthetic apostrophe sample", "It's synthetic apostrophe sample"),
    (
        "whitespace_or_paragraph_only",
        "Synthetic first line Synthetic second line",
        "Synthetic first line\n\nSynthetic second line",
    ),
    (
        "filler_presentation_only",
        "Um synthetic filler sample",
        "Um, synthetic filler sample.",
    ),
    ("mixed_permitted_transformations", "synthetic mixed sample", "Synthetic mixed sample."),
    (
        "combined_preservation_challenge",
        'Avery Chen said "do not send 47 units" to ID-X7 at https://example.test/x7.\n\n'
        "Morgan kept the second paragraph unchanged.",
        'Avery Chen said, "Do not send 47 units," to ID-X7 at https://example.test/x7.\n\n'
        "Morgan kept the second paragraph unchanged.",
    ),
)


class SmokeError(ValueError):
    """A privacy-safe synthetic smoke failure."""


class SmokeProvider(Protocol):
    provider_id: str
    model: str

    async def clean(self, original_text: str, system_prompt: str) -> SmokeProviderResult: ...


@dataclass(frozen=True)
class SmokeProviderResult:
    """Result plus explicit facts required by this safety-specific provider seam."""

    output: ProviderOutput
    request_contract_sha256: str
    request_storage_control: str
    reported_model_version: str | None
    disclosure_detected: bool


@dataclass(frozen=True)
class _LiveSmokeProvider:
    adapter: GeminiAdapter | OpenAIAdapter
    request_contract_sha256: str

    @property
    def provider_id(self) -> str:
        return self.adapter.provider_id

    @property
    def model(self) -> str:
        return self.adapter.model

    async def clean(self, original_text: str, system_prompt: str) -> SmokeProviderResult:
        if isinstance(self.adapter, OpenAIAdapter):
            payload = openai_request_payload(original_text, system_prompt, self.adapter.model)
            if payload.get("store") is not False:
                raise SmokeError("provider_contract_missing")
            storage_control = "store_false"
        else:
            storage_control = "provider_terms"
        output = await self.adapter.clean(original_text, system_prompt)
        _validate_output(original_text, output.text)
        return SmokeProviderResult(
            output=output,
            request_contract_sha256=self.request_contract_sha256,
            request_storage_control=storage_control,
            reported_model_version=None,
            disclosure_detected=False,
        )


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CodeRegistration(_StrictModel):
    expected_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    dependency_lock_sha256: str = Field(pattern=LOWER_SHA256)
    configuration_sha256: str = Field(pattern=LOWER_SHA256)
    clean_tree: bool


class EnvironmentRegistration(_StrictModel):
    isolated_storage: bool
    isolated_credentials: bool
    stable_resources_inaccessible: bool
    permissions_verified: bool
    deletion_path_verified: bool
    clock_verified: bool
    free_space_bytes: int = Field(ge=0)
    minimum_free_space_bytes: int = Field(ge=1)
    stable_inaccessibility_observation: FrozenObservation


class FrozenObservation(_StrictModel):
    method: str = Field(min_length=3, max_length=256)
    value: str = Field(min_length=1, max_length=2048)
    observed_at: datetime
    content_sha256: str = Field(pattern=LOWER_SHA256)


class EvidenceSource(_StrictModel):
    provider: str
    kind: str
    url: str
    retrieved_at: datetime
    content_sha256: str = Field(pattern=LOWER_SHA256)
    observation_method: str = Field(min_length=3, max_length=256)
    observed_fact: str = Field(min_length=1, max_length=2048)

    @field_validator("url")
    @classmethod
    def official_url_is_https(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("official evidence URL must use HTTPS")
        return value

    @model_validator(mode="after")
    def official_host_matches_provider(self) -> EvidenceSource:
        host = urlparse(self.url).hostname or ""
        if self.provider not in OFFICIAL_HOSTS or host not in OFFICIAL_HOSTS[self.provider]:
            raise ValueError("evidence source is not an official provider host")
        return self


class ModelEvidence(_StrictModel):
    provider: str = Field(pattern=SAFE_ID)
    model: str = Field(pattern=SAFE_ID)
    reported_version: str | None = Field(default=None, pattern=SAFE_ID)


class PriceEvidence(_StrictModel):
    input_usd_micros_per_million_tokens: int = Field(ge=0)
    output_usd_micros_per_million_tokens: int = Field(ge=0)


class ProviderEvidence(_StrictModel):
    material_change: bool
    sources: dict[str, dict[str, EvidenceSource]]
    models: dict[str, ModelEvidence]
    pricing: dict[str, PriceEvidence]
    quota_call_capacity: dict[str, int]

    @model_validator(mode="after")
    def complete(self) -> ProviderEvidence:
        if set(self.sources) != set(PROVIDER_EVIDENCE_KINDS):
            raise ValueError("provider evidence is incomplete")
        for provider, required_kinds in PROVIDER_EVIDENCE_KINDS.items():
            if set(self.sources[provider]) != required_kinds:
                raise ValueError("provider evidence sources are incomplete")
            for kind, source in self.sources[provider].items():
                if source.provider != provider or source.kind != kind:
                    raise ValueError("provider evidence attribution is invalid")
        if set(self.models) != set(ARMS) or set(self.pricing) != set(ARMS):
            raise ValueError("provider arm evidence is incomplete")
        if set(self.quota_call_capacity) != set(OFFICIAL_HOSTS) or any(
            isinstance(value, bool) or value < PRIVATE_CALLS_PER_ARM
            for value in self.quota_call_capacity.values()
        ):
            raise ValueError("provider quota evidence cannot cover 120 calls")
        return self


class BudgetRegistration(_StrictModel):
    total_usd_micros: int
    canary_usd_micros: int
    private_call_count: int
    input_token_maximum: dict[str, int]
    output_token_maximum: dict[str, int]
    request_bound_usd_micros: dict[str, int]

    @model_validator(mode="after")
    def protocol_limits(self) -> BudgetRegistration:
        if (
            self.total_usd_micros != 10_000_000
            or self.canary_usd_micros != 2_000_000
            or self.private_call_count != 120
        ):
            raise ValueError("budget limits do not match protocol")
        for values in (
            self.input_token_maximum,
            self.output_token_maximum,
            self.request_bound_usd_micros,
        ):
            if set(values) != set(ARMS) or any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in values.values()
            ):
                raise ValueError("request bounds are incomplete")
        return self


class SmokeRegistration(_StrictModel):
    suite_id: str = Field(pattern=SAFE_ID)
    registered_at: datetime
    ordering_seed: int
    code: CodeRegistration
    environment: EnvironmentRegistration
    provider_evidence: ProviderEvidence
    cleanup_contract: dict[str, Any]
    budget: BudgetRegistration


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise SmokeError("preflight_failed")
    return value.astimezone(UTC)


def _fixture_records() -> list[dict[str, str]]:
    return [
        {
            "fixture_id": f"synthetic-{index + 1}",
            "classification": classification,
            "source_sha256": _digest(source.encode()),
        }
        for index, (classification, source, _expected) in enumerate(SYNTHETIC_FIXTURES)
    ]


def _ordered_calls(seed: int) -> list[dict[str, str]]:
    fixture_ids = [f"synthetic-{index + 1}" for index in range(len(SYNTHETIC_FIXTURES))]
    fixture_ids.sort(
        key=lambda fixture_id: _digest(
            canonical_json(["local_text:cleanup-smoke-case-order:v1", seed, fixture_id])
        )
    )
    calls: list[dict[str, str]] = []
    for fixture_id in fixture_ids:
        arm_ids = sorted(
            ARMS,
            key=lambda arm_id: _digest(
                canonical_json(["local_text:cleanup-smoke-arm-order:v1", seed, fixture_id, arm_id])
            ),
        )
        calls.extend({"fixture_id": fixture_id, "arm_id": arm_id} for arm_id in arm_ids)
    return calls


def _validate_preflight(registration: SmokeRegistration, current_time: datetime) -> str:
    current_time = _utc(current_time)
    registered_at = _utc(registration.registered_at)
    if registered_at > current_time:
        raise SmokeError("preflight_failed")
    if registration.provider_evidence.material_change:
        raise SmokeError("preflight_failed")
    if any(
        not registered_at - EVIDENCE_MAX_AGE <= _utc(source.retrieved_at) <= registered_at
        or current_time - _utc(source.retrieved_at) > EVIDENCE_MAX_AGE
        for provider_sources in registration.provider_evidence.sources.values()
        for source in provider_sources.values()
    ):
        raise SmokeError("preflight_failed")
    environment = registration.environment
    if not all(
        (
            registration.code.clean_tree,
            environment.isolated_storage,
            environment.isolated_credentials,
            environment.stable_resources_inaccessible,
            environment.permissions_verified,
            environment.deletion_path_verified,
            environment.clock_verified,
        )
    ):
        raise SmokeError("preflight_failed")
    if environment.free_space_bytes < environment.minimum_free_space_bytes:
        raise SmokeError("preflight_failed")
    observation = environment.stable_inaccessibility_observation
    if (
        current_time - _utc(observation.observed_at) > EVIDENCE_MAX_AGE
        or _utc(observation.observed_at) > registered_at
    ):
        raise SmokeError("preflight_failed")

    try:
        artifacts = registration.cleanup_contract["artifacts"]
        prompt = base64.b64decode(
            artifacts["configured_prompt"]["canonical_bytes_base64"], validate=True
        ).decode()
        dependency_lock = base64.b64decode(
            artifacts["dependency_lock"]["canonical_bytes_base64"], validate=True
        )
        expected = build_cleanup_contract_snapshot(
            prompt,
            configured_prompt_id=registration.cleanup_contract["configured_prompt_id"],
            dependency_lock_bytes=dependency_lock,
        )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, binascii.Error):
        raise SmokeError("preflight_failed") from None
    if registration.cleanup_contract != expected:
        raise SmokeError("preflight_failed")
    if registration.code.dependency_lock_sha256 != _digest(dependency_lock):
        raise SmokeError("preflight_failed")
    if registration.code.configuration_sha256 != _digest(
        canonical_json(registration.cleanup_contract)
    ):
        raise SmokeError("preflight_failed")
    contract_arms = {arm["arm_id"]: arm for arm in registration.cleanup_contract["arms"]}
    for arm_id in ARMS:
        arm = contract_arms.get(arm_id)
        evidence = registration.provider_evidence.models[arm_id]
        if (
            not arm
            or arm["provider"] != evidence.provider
            or arm["request"]["model"] != evidence.model
            or arm["deadline_seconds"] != BENCHMARK_DEADLINE_SECONDS
        ):
            raise SmokeError("preflight_failed")
    if contract_arms["candidate_paid_openai"]["request"]["settings"].get("store") is not False:
        raise SmokeError("preflight_failed")

    for arm_id in ARMS:
        pricing = registration.provider_evidence.pricing[arm_id]
        derived_bound = _cost(
            registration.budget.input_token_maximum[arm_id],
            pricing.input_usd_micros_per_million_tokens,
        ) + _cost(
            registration.budget.output_token_maximum[arm_id],
            pricing.output_usd_micros_per_million_tokens,
        )
        if registration.budget.request_bound_usd_micros[arm_id] != derived_bound:
            raise SmokeError("preflight_failed")

    private_reservation = PRIVATE_CALLS_PER_ARM * sum(
        registration.budget.request_bound_usd_micros.values()
    )
    if private_reservation > registration.budget.total_usd_micros:
        raise SmokeError("preflight_failed")
    effective_prompt = base64.b64decode(
        artifacts["effective_prompt"]["canonical_bytes_base64"], validate=True
    ).decode()
    return effective_prompt


def _new_disposition(registration: SmokeRegistration) -> dict[str, Any]:
    fixtures = _fixture_records()
    private_reservation = PRIVATE_CALLS_PER_ARM * sum(
        registration.budget.request_bound_usd_micros.values()
    )
    return {
        "suite_id": registration.suite_id,
        "registration_sha256": _digest(canonical_json(registration.model_dump(mode="json"))),
        "status": "preflight",
        "reason": "pending",
        "private_execution_eligible": False,
        "smoke_prerequisite_satisfied": False,
        "fixture_count": len(fixtures),
        "call_count": 0,
        "all_passed": False,
        "fixtures_sha256": _digest(canonical_json(fixtures)),
        "results_sha256": _digest(canonical_json([])),
        "call_order": _ordered_calls(registration.ordering_seed),
        "private_call_count_reserved": 120,
        "private_cost_reserved_usd_micros": private_reservation,
        "smoke_cost_usd_micros": 0,
        "completed_call_count": 0,
        "calls": [],
    }


def _create_private(path: Path, value: dict[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(canonical_json(value) + b"\n")
        output.flush()
        os.fsync(output.fileno())
    _sync_directory(path.parent)


def _replace_private(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(canonical_json(value) + b"\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _verify_local_preflight(registration: SmokeRegistration, output_path: Path) -> None:
    """Measure local invariants without opening any stable resource or provider connection."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        output_directory = output_path.parent.resolve(strict=True)
        repository = REPOSITORY_ROOT.resolve(strict=True)
        mode = stat.S_IMODE(output_directory.stat().st_mode)
        stable_configuration_present = any(
            os.environ.get(name)
            for name in (
                "LOCAL_TEXT_DATABASE_PATH",
                "LOCAL_TEXT_EVALUATION_DATABASE_PATH",
                "LOCAL_TEXT_CORRECTION_BENCHMARK_CASES_PATH",
                "LOCAL_TEXT_GEMINI_API_KEY",
                "LOCAL_TEXT_OPENAI_API_KEY",
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
            )
        )
        dedicated_credentials_present = all(
            os.environ.get(name)
            for name in (
                "LOCAL_TEXT_BENCHMARK_GEMINI_API_KEY",
                "LOCAL_TEXT_BENCHMARK_OPENAI_API_KEY",
            )
        )
        with tempfile.NamedTemporaryFile(dir=output_directory, delete=True) as probe:
            probe.write(b"preflight")
            probe.flush()
            probe_path = Path(probe.name)
        deletion_verified = not probe_path.exists()
        free_space = shutil.disk_usage(output_directory).free
        dependency_lock_sha256 = _digest((REPOSITORY_ROOT / "uv.lock").read_bytes())
    except (OSError, subprocess.SubprocessError):
        raise SmokeError("preflight_failed") from None
    if (
        commit != registration.code.expected_commit
        or dirty
        or dependency_lock_sha256 != registration.code.dependency_lock_sha256
        or output_directory == repository
        or repository in output_directory.parents
        or mode & 0o077
        or stable_configuration_present
        or not dedicated_credentials_present
        or not deletion_verified
        or free_space < registration.environment.minimum_free_space_bytes
        or registration.environment.free_space_bytes > free_space
    ):
        raise SmokeError("preflight_failed")


def _cost(tokens: int, rate: int) -> int:
    return (tokens * rate + 999_999) // 1_000_000


def _valid_usage(value: object, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= maximum


def _request_contract_sha256(registration: SmokeRegistration, arm_id: str) -> str:
    arm = next(arm for arm in registration.cleanup_contract["arms"] if arm["arm_id"] == arm_id)
    return _digest(canonical_json(arm["request"]))


def _failure(disposition: dict[str, Any], reason: str, *, persist: Callable[[], None]) -> None:
    disposition["status"] = "failed"
    disposition["reason"] = reason
    disposition["private_execution_eligible"] = False
    persist()


async def run_synthetic_smoke(
    registration_value: object,
    providers: Mapping[str, SmokeProvider],
    output_path: Path,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    persist: bool = True,
    local_preflight: Callable[[SmokeRegistration], None] | None = None,
) -> dict[str, Any]:
    """Preflight and run one complete, non-resumable 16-call synthetic suite."""
    if persist and output_path.exists():
        raise SmokeError("suite_artifact_exists")
    try:
        registration = SmokeRegistration.model_validate(registration_value)
    except ValidationError:
        raise SmokeError("preflight_failed") from None
    if persist and output_path.name != f"{registration.suite_id}.json":
        raise SmokeError("suite_output_identity_mismatch")
    disposition = _new_disposition(registration)
    if persist:
        try:
            _create_private(output_path, disposition)
        except FileExistsError:
            raise SmokeError("suite_artifact_exists") from None

    def save() -> None:
        if persist:
            _replace_private(output_path, disposition)

    try:
        effective_prompt = _validate_preflight(registration, now())
        if local_preflight is not None:
            local_preflight(registration)
    except SmokeError:
        disposition["status"] = "blocked"
        disposition["reason"] = "preflight_failed"
        save()
        raise
    if set(providers) != set(ARMS):
        disposition["status"] = "blocked"
        disposition["reason"] = "preflight_failed"
        save()
        raise SmokeError("preflight_failed")

    disposition["status"] = "running"
    disposition["reason"] = "pending"
    save()
    smoke_limit = (
        registration.budget.total_usd_micros - disposition["private_cost_reserved_usd_micros"]
    )
    fixture_by_id = {
        f"synthetic-{index + 1}": (source, expected)
        for index, (_classification, source, expected) in enumerate(SYNTHETIC_FIXTURES)
    }
    for call_index, call in enumerate(disposition["call_order"]):
        arm_id = call["arm_id"]
        bound = registration.budget.request_bound_usd_micros[arm_id]
        if disposition["smoke_cost_usd_micros"] + bound > smoke_limit:
            _failure(disposition, "budget_reservation_failed", persist=save)
            return disposition
        call_record = {
            "call_index": call_index,
            "fixture_id": call["fixture_id"],
            "arm_id": arm_id,
            "status": "reserved",
            "reserved_usd_micros": bound,
        }
        disposition["calls"].append(call_record)
        save()
        provider = providers[arm_id]
        source, expected = fixture_by_id[call["fixture_id"]]
        try:
            provider_result = await asyncio.wait_for(
                provider.clean(source, effective_prompt), timeout=BENCHMARK_DEADLINE_SECONDS
            )
        except TimeoutError:
            _failure(disposition, "timeout", persist=save)
            return disposition
        except Exception:
            _failure(disposition, "provider_failure", persist=save)
            return disposition

        if not isinstance(provider_result, SmokeProviderResult):
            _failure(disposition, "provider_contract_missing", persist=save)
            return disposition
        output = provider_result.output
        evidence = registration.provider_evidence.models[arm_id]
        if output.provider_id != evidence.provider or output.model_id != evidence.model:
            _failure(disposition, "attribution_mismatch", persist=save)
            return disposition
        if (
            evidence.reported_version is not None
            and provider_result.reported_model_version != evidence.reported_version
        ):
            _failure(disposition, "attribution_mismatch", persist=save)
            return disposition
        if provider_result.request_contract_sha256 != _request_contract_sha256(
            registration, arm_id
        ):
            _failure(disposition, "request_contract_mismatch", persist=save)
            return disposition
        required_storage_control = (
            "store_false" if evidence.provider == "openai" else "provider_terms"
        )
        if provider_result.request_storage_control != required_storage_control:
            _failure(disposition, "storage_violation", persist=save)
            return disposition
        if not _valid_usage(
            output.input_tokens, registration.budget.input_token_maximum[arm_id]
        ) or not _valid_usage(
            output.output_tokens, registration.budget.output_token_maximum[arm_id]
        ):
            _failure(disposition, "malformed_usage", persist=save)
            return disposition
        try:
            _validate_output(source, output.text)
        except ProviderRejectedOutputError:
            _failure(disposition, "validator_rejection", persist=save)
            return disposition
        if provider_result.disclosure_detected:
            _failure(disposition, "disclosure_violation", persist=save)
            return disposition
        if output.text != expected:
            _failure(disposition, "severe_harm", persist=save)
            return disposition
        pricing = registration.provider_evidence.pricing[arm_id]
        actual_cost = _cost(
            output.input_tokens,
            pricing.input_usd_micros_per_million_tokens,  # type: ignore[arg-type]
        ) + _cost(
            output.output_tokens,
            pricing.output_usd_micros_per_million_tokens,  # type: ignore[arg-type]
        )
        if actual_cost > bound:
            _failure(disposition, "conservative_bound_exceeded", persist=save)
            return disposition
        if disposition["smoke_cost_usd_micros"] + actual_cost > smoke_limit:
            _failure(disposition, "actual_budget_breach", persist=save)
            return disposition
        disposition["smoke_cost_usd_micros"] += actual_cost
        disposition["completed_call_count"] += 1
        disposition["call_count"] += 1
        call_record.update(
            {
                "status": "passed",
                "elapsed_ms": output.elapsed_ms,
                "input_tokens": output.input_tokens,
                "output_tokens": output.output_tokens,
                "actual_usd_micros": actual_cost,
            }
        )
        save()

    disposition["status"] = "passed"
    disposition["reason"] = "all_calls_passed"
    disposition["smoke_prerequisite_satisfied"] = True
    disposition["all_passed"] = True
    disposition["results_sha256"] = _digest(canonical_json(disposition["calls"]))
    save()
    return disposition


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the isolated cleanup synthetic smoke suite")
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--authorize-live-smoke", action="store_true")
    args = parser.parse_args()
    if not args.authorize_live_smoke:
        print("error: separate explicit live-smoke authorization is required", file=sys.stderr)
        raise SystemExit(2)
    try:
        registration = json.loads(args.registration.read_bytes())
        validated_registration = SmokeRegistration.model_validate(registration)

        async def execute() -> dict[str, Any]:
            async with httpx.AsyncClient(timeout=BENCHMARK_DEADLINE_SECONDS) as client:
                providers: dict[str, SmokeProvider] = {
                    "baseline_paid_gemini": _LiveSmokeProvider(
                        GeminiAdapter(
                            os.environ.get("LOCAL_TEXT_BENCHMARK_GEMINI_API_KEY", ""),
                            "gemini-3.7-flash",
                            client,
                        ),
                        _request_contract_sha256(validated_registration, "baseline_paid_gemini"),
                    ),
                    "candidate_paid_openai": _LiveSmokeProvider(
                        OpenAIAdapter(
                            os.environ.get("LOCAL_TEXT_BENCHMARK_OPENAI_API_KEY", ""), client
                        ),
                        _request_contract_sha256(validated_registration, "candidate_paid_openai"),
                    ),
                }
                return await run_synthetic_smoke(
                    registration,
                    providers,
                    args.output,
                    local_preflight=lambda value: _verify_local_preflight(value, args.output),
                )

        result = asyncio.run(execute())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SmokeError):
        print("error: cleanup synthetic smoke failed", file=sys.stderr)
        raise SystemExit(1) from None
    print(
        canonical_json(
            {
                "suite_id": result["suite_id"],
                "status": result["status"],
                "completed_call_count": result["completed_call_count"],
                "smoke_prerequisite_satisfied": result["smoke_prerequisite_satisfied"],
            }
        ).decode()
    )


if __name__ == "__main__":
    main()
