import asyncio
import hashlib
import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from local_text.cleanup import ProviderOutput, ProviderTimeoutError
from local_text.cleanup_contract import build_cleanup_contract_snapshot, canonical_json
from local_text.cleanup_evaluation_execution import (
    ExecutionProviderResult,
    RunInvariants,
    read_execution_results,
    run_cleanup_benchmark,
)

NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)
ARMS = ("baseline_paid_gemini", "candidate_paid_openai")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class FakeProvider:
    def __init__(self, provider_id: str, model: str, events: list[tuple[str, str]]) -> None:
        self.provider_id = provider_id
        self.model = model
        self.calls: list[str] = []
        self.events = events
        self.results: list[ExecutionProviderResult | Exception] = []

    async def clean(self, original_text: str, system_prompt: str) -> ExecutionProviderResult:
        del system_prompt
        self.calls.append(original_text)
        self.events.append((original_text, self.provider_id))
        if self.results:
            result = self.results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return self.result(original_text)

    def result(self, text: str, **changes: object) -> ExecutionProviderResult:
        value = ExecutionProviderResult(
            output=ProviderOutput(
                text=text,
                provider_id=self.provider_id,
                model_id=self.model,
                elapsed_ms=4,
                input_tokens=10,
                output_tokens=5,
            ),
            reported_model_version=None,
            request_storage_control=(
                "store_false" if self.provider_id == "openai" else "provider_terms"
            ),
            disclosure_detected=False,
        )
        return replace(value, **changes)


def provider_map(events: list[tuple[str, str]] | None = None) -> dict[str, FakeProvider]:
    events = events if events is not None else []
    return {
        "baseline_paid_gemini": FakeProvider("gemini", "gemini-3.7-flash", events),
        "candidate_paid_openai": FakeProvider("openai", "gpt-5.6-luna", events),
    }


def execution_inputs() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    cases = [
        {
            "case_id": f"case-{index:02}",
            "revision": 1,
            "current_revision": 1,
            "record_sha256": f"{index:064x}",
            "source_text": f"Private source {index}",
            "consent": {"valid": True},
            "hold": {
                "benchmark_id": "cleanup-evaluation-benchmark-v2",
                "release_at": (NOW + timedelta(days=10)).isoformat(),
            },
        }
        for index in range(60)
    ]
    snapshot = {"frozen_at": (NOW - timedelta(hours=2)).isoformat(), "cases": cases}
    contract = build_cleanup_contract_snapshot(
        "Preserve every word.", configured_prompt_id="prompt-1", dependency_lock_bytes=b"locked"
    )
    case_order = [case["case_id"] for case in reversed(cases)]
    arm_order = {
        case_id: list(ARMS if index % 2 else reversed(ARMS))
        for index, case_id in enumerate(case_order)
    }
    selected = [
        {
            "case_id": case["case_id"],
            "revision": case["revision"],
            "record_sha256": case["record_sha256"],
        }
        for case in cases
    ]
    smoke = {
        "status": "passed",
        "all_passed": True,
        "fixture_count": 8,
        "call_count": 16,
        "results_sha256": "e" * 64,
        "smoke_cost_usd_micros": 160,
    }
    manifest = {
        "run_id": "run-28",
        "registered_at": NOW.isoformat(),
        "environment": {"stable_resources_inaccessible": True},
        "code": {"clean_tree": True},
        "corpus": {"snapshot_sha256": digest(snapshot), "selected_cases": selected},
        "ordering": {"case_order": case_order, "arm_order": arm_order},
        "request_contract": contract,
        "provider_evidence": {
            "retrieved_at": (NOW - timedelta(hours=1)).isoformat(),
            "material_change": False,
            "models": {
                "baseline_paid_gemini": {"provider": "gemini", "model": "gemini-3.7-flash"},
                "candidate_paid_openai": {"provider": "openai", "model": "gpt-5.6-luna"},
            },
            "pricing": {
                arm: {
                    "input_usd_micros_per_million_tokens": 1_000,
                    "output_usd_micros_per_million_tokens": 2_000,
                }
                for arm in ARMS
            },
        },
        "synthetic_smoke": {
            key: smoke[key]
            for key in ("all_passed", "fixture_count", "call_count", "results_sha256")
        },
        "budget": {
            "total_usd_micros": 10_000_000,
            "request_bound_usd_micros": {arm: 20 for arm in ARMS},
            "input_token_maximum": {arm: 100 for arm in ARMS},
            "output_token_maximum": {arm: 100 for arm in ARMS},
            "pre_send_stop": True,
        },
        "run_confirmation": {
            "confirmed": True,
            "confirmed_at": NOW.isoformat(),
            "hold_release_at": (NOW + timedelta(days=10)).isoformat(),
            "disclosures": "current disclosures",
            "providers_models": {
                "baseline_paid_gemini": {"provider": "gemini", "model": "gemini-3.7-flash"},
                "candidate_paid_openai": {"provider": "openai", "model": "gpt-5.6-luna"},
            },
            "effective_prompt_sha256": contract["artifacts"]["effective_prompt"]["sha256"],
            "conservative_estimate_usd_micros": 2_400,
            "total_cap_usd_micros": 10_000_000,
            "benchmark_id": "cleanup-evaluation-benchmark-v2",
            "storage_locations": ["snapshot", "run", "report"],
            "selected_cases": [
                {"case_id": item["case_id"], "revision": item["revision"]}
                for item in selected
            ],
            "maximum_private_calls": 120,
        },
        "storage": {
            "inventory": ["snapshot", "run", "report"],
            "locations": ["snapshot", "run", "report"],
            "locations_confirmed": True,
        },
        "lifecycle": {"write_back_to_live_corpus": False},
    }
    registration = {"manifest": manifest, "manifest_sha256": digest(manifest)}
    return registration, snapshot, smoke


def test_executes_frozen_case_and_arm_order_with_complete_pairs(tmp_path: Path) -> None:
    registration, snapshot, smoke = execution_inputs()
    events: list[tuple[str, str]] = []
    providers = provider_map(events)

    result = asyncio.run(
        run_cleanup_benchmark(
            registration,
            snapshot,
            smoke,
            providers,
            tmp_path / "run-28.sqlite3",
            now=lambda: NOW,
        )
    )

    assert result == {
        "run_id": "run-28",
        "status": "completed",
        "reason": "all_pairs_completed",
        "completed_request_count": 120,
        "actual_cost_usd_micros": 120 * 2,
    }
    expected = [
        (case_id, arm_id)
        for case_id in registration["manifest"]["ordering"]["case_order"]
        for arm_id in registration["manifest"]["ordering"]["arm_order"][case_id]
    ]
    source_by_id = {case["case_id"]: case["source_text"] for case in snapshot["cases"]}
    assert events == [
        (source_by_id[case_id], providers[arm_id].provider_id) for case_id, arm_id in expected
    ]
    assert len(read_execution_results(tmp_path / "run-28.sqlite3", "run-28")) == 120


def test_resumes_a_proven_unsent_reservation_without_duplicate_send(tmp_path: Path) -> None:
    registration, snapshot, smoke = execution_inputs()
    ledger = tmp_path / "run-28.sqlite3"
    providers = provider_map()
    interrupted = False

    def crash_once(_case_id: str, _arm_id: str) -> None:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise RuntimeError("simulated pre-send interruption")

    with pytest.raises(RuntimeError, match="pre-send"):
        asyncio.run(
            run_cleanup_benchmark(
                registration,
                snapshot,
                smoke,
                providers,
                ledger,
                now=lambda: NOW,
                after_reservation=crash_once,
            )
        )

    result = asyncio.run(
        run_cleanup_benchmark(
            registration, snapshot, smoke, providers, ledger, now=lambda: NOW
        )
    )
    assert result["status"] == "completed"
    assert sum(len(provider.calls) for provider in providers.values()) == 120


def test_ambiguous_post_send_interruption_invalidates_without_resend(tmp_path: Path) -> None:
    registration, snapshot, smoke = execution_inputs()
    ledger = tmp_path / "run-28.sqlite3"
    providers = provider_map()

    def crash(_case_id: str, _arm_id: str) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        asyncio.run(
            run_cleanup_benchmark(
                registration,
                snapshot,
                smoke,
                providers,
                ledger,
                now=lambda: NOW,
                after_send=crash,
            )
        )
    calls = sum(len(provider.calls) for provider in providers.values())
    resumed = asyncio.run(
        run_cleanup_benchmark(
            registration, snapshot, smoke, providers, ledger, now=lambda: NOW
        )
    )
    assert resumed["reason"] == "ambiguous_in_flight_request"
    assert sum(len(provider.calls) for provider in providers.values()) == calls == 1


def test_post_terminal_interruption_resumes_without_repeating_completed_request(
    tmp_path: Path,
) -> None:
    registration, snapshot, smoke = execution_inputs()
    ledger = tmp_path / "run-28.sqlite3"
    providers = provider_map()
    crashed = False

    def crash_once(_case_id: str, _arm_id: str) -> None:
        nonlocal crashed
        if not crashed:
            crashed = True
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        asyncio.run(
            run_cleanup_benchmark(
                registration,
                snapshot,
                smoke,
                providers,
                ledger,
                now=lambda: NOW,
                after_terminal=crash_once,
            )
        )
    assert sum(len(provider.calls) for provider in providers.values()) == 1
    result = asyncio.run(
        run_cleanup_benchmark(
            registration, snapshot, smoke, providers, ledger, now=lambda: NOW
        )
    )
    assert result["status"] == "completed"
    assert sum(len(provider.calls) for provider in providers.values()) == 120


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        (RunInvariants(withdrawn=True), "withdrawn"),
        (RunInvariants(consent_valid=False), "consent_invalid"),
        (RunInvariants(selected_cases_unchanged=False), "selected_case_changed"),
        (RunInvariants(code_unchanged=False), "code_changed"),
        (RunInvariants(isolation_intact=False), "isolation_violation"),
        (RunInvariants(text_logging_safe=False), "text_logging_violation"),
        (RunInvariants(write_back_disabled=False), "write_back_violation"),
    ],
)
def test_current_invariant_failures_stop_before_send(
    tmp_path: Path, state: RunInvariants, reason: str
) -> None:
    registration, snapshot, smoke = execution_inputs()
    providers = provider_map()
    result = asyncio.run(
        run_cleanup_benchmark(
            registration,
            snapshot,
            smoke,
            providers,
            tmp_path / f"{reason}.sqlite3",
            now=lambda: NOW,
            invariants=lambda: state,
        )
    )
    assert result["reason"] == reason
    assert sum(len(provider.calls) for provider in providers.values()) == 0


def test_pre_send_bound_and_three_operational_failures_stop_new_calls(tmp_path: Path) -> None:
    registration, snapshot, smoke = execution_inputs()
    registration["manifest"]["budget"]["total_usd_micros"] = 179
    registration["manifest_sha256"] = digest(registration["manifest"])
    providers = provider_map()
    blocked = asyncio.run(
        run_cleanup_benchmark(
            registration,
            snapshot,
            smoke,
            providers,
            tmp_path / "budget.sqlite3",
            now=lambda: NOW,
        )
    )
    assert blocked["reason"] == "next_request_cannot_be_reserved"
    assert sum(len(provider.calls) for provider in providers.values()) == 0

    registration, snapshot, smoke = execution_inputs()
    providers = provider_map()
    for provider in providers.values():
        provider.results.extend(ProviderTimeoutError("safe timeout") for _ in range(3))
    stopped = asyncio.run(
        run_cleanup_benchmark(
            registration,
            snapshot,
            smoke,
            providers,
            tmp_path / "failures.sqlite3",
            now=lambda: NOW,
        )
    )
    assert stopped["reason"] == "three_consecutive_operational_failures"
    assert stopped["completed_request_count"] == 5


def test_terminal_result_captures_rejection_and_usage_breach_without_private_logs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registration, snapshot, smoke = execution_inputs()
    providers = provider_map()
    first_arm = registration["manifest"]["ordering"]["arm_order"][
        registration["manifest"]["ordering"]["case_order"][0]
    ][0]
    provider = providers[first_arm]
    provider.results.append(provider.result("invented private words"))
    second = provider.result("safe")
    provider.results.append(
        replace(second, output=replace(second.output, input_tokens=None))
    )
    result = asyncio.run(
        run_cleanup_benchmark(
            registration,
            snapshot,
            smoke,
            providers,
            tmp_path / "terminal.sqlite3",
            now=lambda: NOW,
        )
    )
    rows = read_execution_results(tmp_path / "terminal.sqlite3", "run-28")
    assert rows[0]["outcome"] == "rejected_output"
    assert rows[0]["user_visible_text"].startswith("Private source")
    assert result["reason"] == "missing_or_malformed_usage"
    assert "Private source" not in capsys.readouterr().out


def test_cli_refuses_before_reading_private_inputs_or_constructing_providers(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_text.cleanup_evaluation_execution",
            "--registration",
            str(tmp_path / "PRIVATE-SENTINEL-missing.json"),
            "--snapshot",
            str(tmp_path / "missing-snapshot.json"),
            "--smoke",
            str(tmp_path / "missing-smoke.json"),
            "--ledger",
            str(tmp_path / "missing.sqlite3"),
        ],
        env={**os.environ, "LOCAL_TEXT_BENCHMARK_GEMINI_API_KEY": ""},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "authorization is required" in result.stderr
    assert "PRIVATE-SENTINEL" not in result.stderr
    assert not (tmp_path / "missing.sqlite3").exists()
