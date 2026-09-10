import asyncio
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from local_text.cleanup import ProviderOutput
from local_text.cleanup_contract import build_cleanup_contract_snapshot, canonical_json
from local_text.cleanup_evaluation_smoke import (
    ARMS,
    SYNTHETIC_FIXTURES,
    SmokeError,
    SmokeProviderResult,
    run_synthetic_smoke,
)

NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class FakeProvider:
    def __init__(self, provider_id: str, model: str, contract_sha256: str) -> None:
        self.provider_id = provider_id
        self.model = model
        self.contract_sha256 = contract_sha256
        self.calls: list[str] = []
        self.results: list[SmokeProviderResult | Exception] = []

    async def clean(self, original_text: str, system_prompt: str) -> SmokeProviderResult:
        del system_prompt
        self.calls.append(original_text)
        if self.results:
            result = self.results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        expected = next(
            expected for _, source, expected in SYNTHETIC_FIXTURES if source == original_text
        )
        return self.result(expected)

    def result(self, text: str, **changes: object) -> SmokeProviderResult:
        value = SmokeProviderResult(
            output=ProviderOutput(
                text, self.provider_id, self.model, 1, input_tokens=10, output_tokens=5
            ),
            request_contract_sha256=self.contract_sha256,
            request_storage_control=(
                "store_false" if self.provider_id == "openai" else "provider_terms"
            ),
            reported_model_version=None,
            disclosure_detected=False,
        )
        return replace(value, **changes)


def registration(*, suite_id: str = "smoke-1") -> dict[str, object]:
    contract = build_cleanup_contract_snapshot(
        "Preserve every synthetic word.",
        configured_prompt_id="prompt-1",
        dependency_lock_bytes=b"locked",
    )
    evidence_time = (NOW - timedelta(hours=1)).isoformat()

    def source(provider: str, kind: str) -> dict[str, object]:
        host = "ai.google.dev" if provider == "gemini" else "platform.openai.com"
        return {
            "provider": provider,
            "kind": kind,
            "url": f"https://{host}/docs/{kind}",
            "retrieved_at": evidence_time,
            "content_sha256": sha256(f"{provider}:{kind}".encode()),
            "observation_method": "frozen official documentation or account console observation",
            "observed_fact": f"Registered {provider} {kind} fact and value.",
        }

    evidence_kinds = {
        "gemini": {
            "model_availability_and_version",
            "pricing",
            "retention_and_data_use",
            "account_controls",
            "quota_and_capacity",
        },
        "openai": {
            "model_availability_and_version",
            "pricing",
            "retention_and_data_use",
            "account_controls",
            "openai_store_false",
            "quota_and_capacity",
        },
    }
    token_maximum = {arm: 10_000 for arm in ARMS}
    output_maximum = {arm: 5_000 for arm in ARMS}
    pricing = {
        arm: {
            "input_usd_micros_per_million_tokens": 1_000,
            "output_usd_micros_per_million_tokens": 2_000,
        }
        for arm in ARMS
    }
    return {
        "suite_id": suite_id,
        "registered_at": NOW.isoformat(),
        "ordering_seed": 73,
        "code": {
            "expected_commit": "a" * 40,
            "dependency_lock_sha256": sha256(b"locked"),
            "configuration_sha256": sha256(canonical_json(contract)),
            "clean_tree": True,
        },
        "environment": {
            "isolated_storage": True,
            "isolated_credentials": True,
            "stable_resources_inaccessible": True,
            "permissions_verified": True,
            "deletion_path_verified": True,
            "clock_verified": True,
            "free_space_bytes": 10_000_000,
            "minimum_free_space_bytes": 1_000_000,
            "stable_inaccessibility_observation": {
                "method": "isolated runner configuration review",
                "value": "stable resources absent from runner configuration",
                "observed_at": evidence_time,
                "content_sha256": sha256(b"isolated runner configuration"),
            },
        },
        "provider_evidence": {
            "material_change": False,
            "sources": {
                provider: {kind: source(provider, kind) for kind in kinds}
                for provider, kinds in evidence_kinds.items()
            },
            "models": {
                "baseline_paid_gemini": {"provider": "gemini", "model": "gemini-3.7-flash"},
                "candidate_paid_openai": {"provider": "openai", "model": "gpt-5.6-luna"},
            },
            "pricing": pricing,
            "quota_call_capacity": {"gemini": 60, "openai": 60},
        },
        "cleanup_contract": contract,
        "budget": {
            "total_usd_micros": 10_000_000,
            "canary_usd_micros": 2_000_000,
            "private_call_count": 120,
            "input_token_maximum": token_maximum,
            "output_token_maximum": output_maximum,
            "request_bound_usd_micros": {arm: 20 for arm in ARMS},
        },
    }


def providers(value: dict[str, object]) -> dict[str, FakeProvider]:
    contracts = {
        arm["arm_id"]: sha256(canonical_json(arm["request"]))
        for arm in value["cleanup_contract"]["arms"]
    }
    return {
        "baseline_paid_gemini": FakeProvider(
            "gemini", "gemini-3.7-flash", contracts["baseline_paid_gemini"]
        ),
        "candidate_paid_openai": FakeProvider(
            "openai", "gpt-5.6-luna", contracts["candidate_paid_openai"]
        ),
    }


def run(value: dict[str, object], provider_map: dict[str, FakeProvider], output: Path):
    canonical_output = output.parent / f"{value['suite_id']}.json"
    return asyncio.run(
        run_synthetic_smoke(value, provider_map, canonical_output, now=lambda: NOW)
    )


def first_provider(value: dict[str, object]) -> FakeProvider:
    provider_map = providers(value)
    probe = asyncio.run(
        run_synthetic_smoke(value, provider_map, Path("unused"), now=lambda: NOW, persist=False)
    )
    return provider_map[probe["call_order"][0]["arm_id"]]


def test_passes_exact_frozen_suite_and_writes_registration_compatible_private_disposition(
    tmp_path: Path,
):
    value = registration()
    provider_map = providers(value)
    result = run(value, provider_map, tmp_path / "result.json")

    assert result["status"] == "passed"
    assert result["fixture_count"] == 8
    assert result["call_count"] == 16
    assert result["all_passed"] is True
    assert result["fixtures_sha256"] and result["results_sha256"]
    assert sum(len(provider.calls) for provider in provider_map.values()) == 16
    assert (tmp_path / "smoke-1.json").stat().st_mode & 0o777 == 0o600
    serialized = (tmp_path / "smoke-1.json").read_text()
    assert all(source not in serialized for _, source, _ in SYNTHETIC_FIXTURES)


@pytest.mark.parametrize("usage", [None, -1, True, "1", 10_001])
def test_rejects_missing_negative_boolean_malformed_or_over_max_usage(
    tmp_path: Path, usage: object
):
    value = registration(suite_id=f"usage-{usage}")
    provider_map = providers(value)
    provider = first_provider(value)
    target = provider_map[
        next(arm for arm, item in provider_map.items() if item.provider_id == provider.provider_id)
    ]
    target.results.append(
        target.result("safe", output=replace(target.result("safe").output, input_tokens=usage))
    )
    result = run(value, provider_map, tmp_path / f"usage-{usage}.json")
    assert result["reason"] == "malformed_usage"
    assert sum(len(item.calls) for item in provider_map.values()) == 1


def test_derived_bounds_and_both_protocol_ceilings_are_required(tmp_path: Path):
    for index, mutate in enumerate(("bound", "total", "canary")):
        value = registration(suite_id=mutate)
        if mutate == "bound":
            value["budget"]["request_bound_usd_micros"][ARMS[0]] = 21
        elif mutate == "total":
            value["budget"]["total_usd_micros"] = 9_999_999
        else:
            value["budget"]["canary_usd_micros"] = 1_999_999
        with pytest.raises(SmokeError, match="preflight_failed"):
            run(value, providers(value), tmp_path / f"budget-{index}.json")


def test_full_private_reservation_blocks_before_first_send(tmp_path: Path):
    value = registration()
    value["budget"]["input_token_maximum"] = {arm: 100_000_000 for arm in ARMS}
    value["budget"]["request_bound_usd_micros"] = {arm: 100_010 for arm in ARMS}
    provider_map = providers(value)
    with pytest.raises(SmokeError, match="preflight_failed"):
        run(value, provider_map, tmp_path / "budget.json")
    assert sum(len(item.calls) for item in provider_map.values()) == 0


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("timeout", "timeout"),
        ("attribution", "attribution_mismatch"),
        ("contract", "request_contract_mismatch"),
        ("validator", "validator_rejection"),
        ("harm", "severe_harm"),
        ("disclosure", "disclosure_violation"),
        ("storage", "storage_violation"),
    ],
)
def test_public_provider_seam_blocks_each_call_failure(tmp_path: Path, mutation: str, reason: str):
    value = registration(suite_id=mutation)
    provider_map = providers(value)
    first = first_provider(value)
    provider = next(item for item in provider_map.values() if item.provider_id == first.provider_id)
    first_source = first.calls[0]
    first_expected = next(
        expected for _, source, expected in SYNTHETIC_FIXTURES if source == first_source
    )
    if mutation == "timeout":
        provider.results.append(TimeoutError("private detail"))
    elif mutation == "attribution":
        provider.results.append(
            provider.result(
                "safe",
                output=ProviderOutput("safe", "other", "other", 1, input_tokens=1, output_tokens=1),
            )
        )
    elif mutation == "contract":
        provider.results.append(provider.result("safe", request_contract_sha256="0" * 64))
    elif mutation == "validator":
        provider.results.append(provider.result("invented words"))
    elif mutation == "harm":
        provider.results.append(provider.result(first_expected + "!"))
    elif mutation == "disclosure":
        provider.results.append(provider.result(first_expected, disclosure_detected=True))
    else:
        provider.results.append(provider.result("safe", request_storage_control="unknown"))
    result = run(value, provider_map, tmp_path / f"{mutation}.json")
    assert result["reason"] == reason
    assert "private detail" not in json.dumps(result)


def test_official_evidence_requires_provider_host_hash_fact_and_fresh_unchanged_content(
    tmp_path: Path,
):
    mutations = ("host", "stale", "changed", "bare")
    for mutation in mutations:
        value = registration(suite_id=mutation)
        evidence = value["provider_evidence"]
        item = evidence["sources"]["openai"]["pricing"]
        if mutation == "host":
            item["url"] = "https://example.test/pricing"
        elif mutation == "stale":
            item["retrieved_at"] = (NOW - timedelta(hours=25)).isoformat()
        elif mutation == "changed":
            evidence["material_change"] = True
        else:
            item["observed_fact"] = ""
        provider_map = providers(value)
        with pytest.raises(SmokeError, match="preflight_failed"):
            run(value, provider_map, tmp_path / f"evidence-{mutation}.json")
        assert sum(len(provider.calls) for provider in provider_map.values()) == 0


def test_registered_quota_must_cover_all_120_calls(tmp_path: Path):
    value = registration(suite_id="quota")
    value["provider_evidence"]["quota_call_capacity"]["openai"] = 59
    with pytest.raises(SmokeError, match="preflight_failed"):
        run(value, providers(value), tmp_path / "quota.json")


def test_reported_version_is_checked_when_registered(tmp_path: Path):
    value = registration()
    for model in value["provider_evidence"]["models"].values():
        model["reported_version"] = "v-frozen"
    provider_map = providers(value)
    provider = first_provider(value)
    target = next(
        item for item in provider_map.values() if item.provider_id == provider.provider_id
    )
    target.results.append(target.result("safe", reported_model_version="v-other"))
    assert run(value, provider_map, tmp_path / "version.json")["reason"] == "attribution_mismatch"


def test_failed_suite_cannot_resume_and_restart_requires_distinct_registration(tmp_path: Path):
    value = registration()
    output = tmp_path / "result.json"
    failed = providers(value)
    first = first_provider(value)
    next(item for item in failed.values() if item.provider_id == first.provider_id).results.append(
        TimeoutError()
    )
    assert run(value, failed, output)["status"] == "failed"
    with pytest.raises(SmokeError, match="suite_artifact_exists"):
        run(value, providers(value), output)
    restarted_value = registration(suite_id="smoke-2")
    restarted = run(restarted_value, providers(restarted_value), tmp_path / "result-2.json")
    assert restarted["status"] == "passed" and restarted["completed_call_count"] == 16

    with pytest.raises(SmokeError, match="suite_output_identity_mismatch"):
        asyncio.run(
            run_synthetic_smoke(
                registration(suite_id="smoke-3"),
                providers(registration(suite_id="smoke-3")),
                tmp_path / "renamed-retry.json",
                now=lambda: NOW,
            )
        )


def test_cli_refuses_before_reading_registration_or_constructing_providers(tmp_path: Path):
    missing = tmp_path / "does-not-exist.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_text.cleanup_evaluation_smoke",
            "--registration",
            str(missing),
            "--output",
            str(tmp_path / "out.json"),
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "LOCAL_TEXT_BENCHMARK_GEMINI_API_KEY": "",
            "LOCAL_TEXT_BENCHMARK_OPENAI_API_KEY": "",
        },
        check=False,
    )
    assert result.returncode == 2
    assert "authorization is required" in result.stderr
    assert not (tmp_path / "out.json").exists()
