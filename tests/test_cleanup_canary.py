import asyncio
import base64
import hashlib
import hmac
import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from local_text.cleanup import (
    ProviderFailure,
    ProviderFailureClass,
    ProviderOutput,
    ProviderRejectedOutputError,
)
from local_text.cleanup_canary import (
    CanaryAttempt,
    CanaryError,
    CanaryProviderResult,
    check_cleanup_canary,
    freeze_canary_review,
    register_cleanup_canary,
    run_canary_attempt,
    terminate_cleanup_canary,
)
from local_text.cleanup_contract import canonical_json

NOW = datetime(2026, 9, 10, 18, tzinfo=UTC)
SIGNING_KEY = b"local signing key with 32 bytes!!"


def run(coroutine):
    return asyncio.run(coroutine)


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def contract() -> dict:
    def artifact(value: bytes, version: str | None = None) -> dict:
        result = {
            "canonical_bytes_base64": base64.b64encode(value).decode("ascii"),
            "sha256": hashlib.sha256(value).hexdigest(),
        }
        if version:
            result["version"] = version
        return result

    return {
        "snapshot_version": "cleanup-execution-contract-v1",
        "artifacts": {
            "effective_prompt": artifact(b"prompt"),
            "schema": artifact(b"schema", "cleanup-result-v1"),
            "validator_implementation": artifact(b"validator", "source-preserving-validator-v1"),
        },
        "execution": {"deadline_seconds": 30, "fallback": False, "retries": 0},
        "arms": [
            {
                "arm_id": "candidate_paid_openai",
                "provider": "openai",
                "deadline_seconds": 30,
                "request": {
                    "api_mode": "responses",
                    "model": "gpt-5.6-luna",
                    "settings": {"reasoning_effort": "none", "store": False},
                },
                "output_cap": {
                    "version": "input-dependent-output-cap-v1",
                    "thinking_headroom_tokens": 0,
                },
            }
        ],
    }


def eligibility(request_contract: dict | None = None) -> dict:
    candidate = {
        "provider": "openai",
        "model": "gpt-5.6-luna",
        "reported_version": "2026-09-01",
    }
    packet = {
        "packet_version": "cleanup-canary-eligibility-v1",
        "run_id": "benchmark-30",
        "manifest_sha256": "a" * 64,
        "report_sha256": "b" * 64,
        "candidate_configuration": {
            "model": candidate,
            "request_contract": request_contract or contract(),
            "deadline_seconds": 30,
        },
        "protocol_deviations": [],
        "gates": [
            {"gate": name, "disposition": "pass"}
            for name in (
                "candidate_mean_effort_relative_decrease",
                "paired_bootstrap_relative_degradation_upper_bound",
                "candidate_valid_output_rate_absolute_drop",
                "candidate_accepted_source_contract_violations",
                "candidate_severe_harmful_changes",
                "candidate_p95_latency_increase_ms",
            )
        ],
        "deletion_receipt": {
            "protocol_or_run_id": "benchmark-30",
            "disposition": "completion",
            "deletion_timestamp": NOW.isoformat(),
            "counts": {"files": 1, "directories": 0},
        },
        "authorizes": "request_separate_explicit_10_cleanup_canary_confirmation_only",
    }
    return {
        "packet": packet,
        "signature": {
            "algorithm": "hmac-sha256",
            "value": hmac.new(SIGNING_KEY, canonical_json(packet), hashlib.sha256).hexdigest(),
        },
    }


def provider_evidence() -> dict:
    return {
        "retrieved_at": NOW.isoformat(),
        "material_change": False,
        "model": {
            "provider": "openai",
            "model": "gpt-5.6-luna",
            "reported_version": "2026-09-01",
        },
        "official_sources": ["https://platform.openai.com/docs/models/gpt-5.6-luna"],
        "retention_and_data_use": {"store_false": "confirmed"},
        "account_controls": {"training_disabled": True},
        "pricing": {
            "input_usd_micros_per_million_tokens": 1_000_000,
            "output_usd_micros_per_million_tokens": 2_000_000,
        },
        "input_token_maximum": 1_000,
        "output_token_maximum": 1_000,
        "request_bound_usd_micros": 100_000,
    }


def confirmation(ledger: Path, *managed_locations: Path) -> dict:
    return {
        "confirmed": True,
        "confirmed_at": NOW.isoformat(),
        "canary_run_id": "canary-31",
        "benchmark_manifest_sha256": "a" * 64,
        "benchmark_report_sha256": "b" * 64,
        "candidate_configuration": eligibility()["packet"]["candidate_configuration"],
        "provider_evidence_sha256": digest(provider_evidence()),
        "maximum_calls": 10,
        "candidate_only": True,
        "manual_selection_only": True,
        "requests_per_attempt": 1,
        "baseline_duplication_retry_fallback_routing_shadow_or_resend": False,
        "budget_estimate_usd_micros": 1_000_000,
        "budget_cap_usd_micros": 2_000_000,
        "pre_send_budget_enforcement": True,
        "starts_at": NOW.isoformat(),
        "ends_at": (NOW + timedelta(days=14)).isoformat(),
        "evidence_release_at": (NOW + timedelta(days=14)).isoformat(),
        "storage_locations": [str(ledger), *(str(path) for path in managed_locations)],
        "managed_deletion": True,
        "optional_private_export_before_deletion": True,
        "withdrawal_stops_and_deletes": True,
        "provider_requests_irretractable": True,
    }


def registration(tmp_path: Path) -> tuple[dict, Path]:
    ledger = tmp_path / "canary.sqlite3"
    result = register_cleanup_canary(
        eligibility(),
        SIGNING_KEY,
        contract(),
        provider_evidence(),
        confirmation(ledger),
        now=lambda: NOW,
    )
    return result, ledger


class FakeProvider:
    provider_id = "openai"
    model = "gpt-5.6-luna"
    candidate_contract_sha256 = digest(contract())

    def __init__(self, results: list[CanaryProviderResult | Exception] | None = None) -> None:
        self.results = results or []
        self.calls: list[tuple[str, str]] = []

    async def clean(self, original_text: str, system_prompt: str) -> CanaryProviderResult:
        self.calls.append((original_text, system_prompt))
        result = (
            self.results.pop(0)
            if self.results
            else CanaryProviderResult(
                output=ProviderOutput(
                    text=original_text.capitalize(),
                    provider_id="openai",
                    model_id="gpt-5.6-luna",
                    elapsed_ms=100,
                    input_tokens=10,
                    output_tokens=5,
                ),
                reported_model_version="2026-09-01",
                request_storage_control="store_false",
                disclosure_detected=False,
            )
        )
        if isinstance(result, Exception):
            raise result
        return result


def attempt(text: str = "hello") -> CanaryAttempt:
    return CanaryAttempt(
        original=text,
        newly_user_initiated_in_pilot=True,
        explicitly_confirmed_dictation_derived=True,
        locally_valid=True,
        manually_candidate_selected=True,
    )


def review(
    *,
    acceptable: bool = True,
    category: str = "none",
    severity: str = "none",
    violation: bool = False,
) -> dict:
    return {
        "acceptability": "acceptable" if acceptable else "unacceptable",
        "accepted_source_contract_violation": violation,
        "harmful_change_category": category,
        "severity": severity,
        "rationale": "frozen local review",
    }


def test_registration_rejects_bad_signature_failed_gate_stale_evidence_and_changed_contract(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "canary.sqlite3"
    cases = []
    bad_signature = eligibility()
    bad_signature["signature"]["value"] = "0" * 64
    cases.append(bad_signature)
    failed_gate = eligibility()
    failed_gate["packet"]["gates"][0]["disposition"] = "fail"
    failed_gate["signature"]["value"] = hmac.new(
        SIGNING_KEY, canonical_json(failed_gate["packet"]), hashlib.sha256
    ).hexdigest()
    cases.append(failed_gate)
    for packet in cases:
        with pytest.raises(CanaryError):
            register_cleanup_canary(
                packet,
                SIGNING_KEY,
                contract(),
                provider_evidence(),
                confirmation(ledger),
                now=lambda: NOW,
            )

    stale = provider_evidence()
    stale["retrieved_at"] = (NOW - timedelta(hours=25)).isoformat()
    with pytest.raises(CanaryError, match="provider evidence"):
        register_cleanup_canary(
            eligibility(), SIGNING_KEY, contract(), stale, confirmation(ledger), now=lambda: NOW
        )

    changed = contract()
    changed["execution"]["retries"] = 1
    with pytest.raises(CanaryError, match="candidate contract"):
        register_cleanup_canary(
            eligibility(),
            SIGNING_KEY,
            changed,
            provider_evidence(),
            confirmation(ledger),
            now=lambda: NOW,
        )


def test_invalid_and_duplicate_input_send_nothing_and_do_not_count(tmp_path: Path) -> None:
    registered, ledger = registration(tmp_path)
    provider = FakeProvider()

    invalid = run(
        run_canary_attempt(
            registered, provider, ledger, replace(attempt(), locally_valid=False), now=lambda: NOW
        )
    )
    first = run(
        run_canary_attempt(
            registered, provider, ledger, attempt("e\u0301\r\ntext"), now=lambda: NOW
        )
    )
    freeze_canary_review(registered, ledger, 1, review(), now=lambda: NOW)
    duplicate = run(
        run_canary_attempt(registered, provider, ledger, attempt("é\ntext"), now=lambda: NOW)
    )

    assert invalid["reason"] == "ineligible_local_input"
    assert duplicate["reason"] == "duplicate_original"
    assert len(provider.calls) == 1
    assert first["completed_attempt_count"] == 1
    assert duplicate["completed_attempt_count"] == 1


def test_exactly_one_send_is_reserved_and_ambiguous_recovery_stops_and_deletes(
    tmp_path: Path,
) -> None:
    registered, ledger = registration(tmp_path)
    provider = FakeProvider()

    def interrupt_before_send() -> None:
        raise RuntimeError("process interrupted")

    with pytest.raises(RuntimeError, match="interrupted"):
        run(
            run_canary_attempt(
                registered,
                provider,
                ledger,
                attempt(),
                now=lambda: NOW,
                after_reservation=interrupt_before_send,
            )
        )
    resumed = run(run_canary_attempt(registered, provider, ledger, attempt(), now=lambda: NOW))
    assert resumed["completed_attempt_count"] == 1
    assert len(provider.calls) == 1

    ledger.unlink()
    registered, ledger = registration(tmp_path)
    provider = FakeProvider()

    def interrupt() -> None:
        raise RuntimeError("process interrupted")

    with pytest.raises(RuntimeError, match="interrupted"):
        run(
            run_canary_attempt(
                registered, provider, ledger, attempt(), now=lambda: NOW, after_send=interrupt
            )
        )
    assert len(provider.calls) == 1

    result = run(run_canary_attempt(registered, provider, ledger, attempt(), now=lambda: NOW))
    assert result["status"] == "stopped"
    assert result["reason"] == "ambiguous_in_flight_request"
    assert len(provider.calls) == 1
    assert not ledger.exists()
    assert set(result["deletion_receipt"]) == {
        "protocol_or_run_id",
        "disposition",
        "deletion_timestamp",
        "counts",
    }


def test_budget_boundary_and_review_blocking(tmp_path: Path) -> None:
    registered, ledger = registration(tmp_path)
    provider = FakeProvider()
    first = run(run_canary_attempt(registered, provider, ledger, attempt("one"), now=lambda: NOW))
    assert first["status"] == "running"

    blocked = run(run_canary_attempt(registered, provider, ledger, attempt("two"), now=lambda: NOW))
    assert blocked["status"] == "stopped"
    assert blocked["reason"] == "unresolved_review"
    assert len(provider.calls) == 1
    assert not ledger.exists()

    budget_path = tmp_path / "budget"
    budget_path.mkdir(mode=0o700)
    registered, ledger = registration(budget_path)
    registered["manifest"]["budget"]["request_bound_usd_micros"] = 2_000_001
    registered["manifest_sha256"] = digest(registered["manifest"])
    budget = run(run_canary_attempt(registered, FakeProvider(), ledger, attempt(), now=lambda: NOW))
    assert budget["reason"] == "next_request_cannot_be_reserved"
    assert not ledger.exists()


def test_failure_counts_once_second_unsuccessful_hard_stops(tmp_path: Path) -> None:
    registered, ledger = registration(tmp_path)
    failures = [
        ProviderFailure(
            "failed",
            failure_class=ProviderFailureClass.TRANSIENT_ROUTE,
            input_tokens=0,
            output_tokens=0,
        ),
        ProviderFailure(
            "failed",
            failure_class=ProviderFailureClass.TRANSIENT_ROUTE,
            input_tokens=0,
            output_tokens=0,
        ),
    ]
    provider = FakeProvider(failures)

    first = run(run_canary_attempt(registered, provider, ledger, attempt("one"), now=lambda: NOW))
    assert first["completed_attempt_count"] == 1
    freeze_canary_review(registered, ledger, 1, review(acceptable=False), now=lambda: NOW)
    second = run(run_canary_attempt(registered, provider, ledger, attempt("two"), now=lambda: NOW))

    assert second["completed_attempt_count"] == 2
    assert second["status"] == "stopped"
    assert second["reason"] == "second_unsuccessful_attempt"
    assert len(provider.calls) == 2
    assert not ledger.exists()


@pytest.mark.parametrize(
    ("provider_result", "outcome"),
    [
        (TimeoutError(), "timeout"),
        (
            ProviderFailure(
                "failed",
                failure_class=ProviderFailureClass.TRANSIENT_ROUTE,
                input_tokens=0,
                output_tokens=0,
            ),
            "failure",
        ),
        (
            ProviderRejectedOutputError(
                "refused",
                safety_policy=True,
            ),
            "refusal",
        ),
        (
            ProviderRejectedOutputError("rejected"),
            "rejection",
        ),
    ],
)
def test_every_unsuccessful_outcome_counts_once(
    tmp_path: Path, provider_result: Exception, outcome: str
) -> None:
    registered, ledger = registration(tmp_path)
    provider = FakeProvider([provider_result])

    result = run(run_canary_attempt(registered, provider, ledger, attempt(), now=lambda: NOW))

    assert result["status"] == "running"
    assert result["outcome"] == outcome
    assert result["completed_attempt_count"] == 1
    assert result["unsuccessful_attempt_count"] == 1
    assert len(provider.calls) == 1


@pytest.mark.parametrize(("first_failure", "second_failure"), [(1, 9), (5, 10)])
def test_second_failure_stops_at_its_position(
    tmp_path: Path, first_failure: int, second_failure: int
) -> None:
    registered, ledger = registration(tmp_path)
    failures = {first_failure, second_failure}
    provider = FakeProvider(
        [
            ProviderFailure(
                "failed",
                failure_class=ProviderFailureClass.TRANSIENT_ROUTE,
                input_tokens=0,
                output_tokens=0,
            )
            if index in failures
            else CanaryProviderResult(
                output=ProviderOutput(
                    text=f"Attempt {index}",
                    provider_id="openai",
                    model_id="gpt-5.6-luna",
                    elapsed_ms=100,
                    input_tokens=10,
                    output_tokens=5,
                ),
                reported_model_version="2026-09-01",
                request_storage_control="store_false",
                disclosure_detected=False,
            )
            for index in range(1, second_failure + 1)
        ]
    )

    for index in range(1, second_failure + 1):
        result = run(
            run_canary_attempt(
                registered, provider, ledger, attempt(f"attempt {index}"), now=lambda: NOW
            )
        )
        if index < second_failure:
            freeze_canary_review(
                registered,
                ledger,
                index,
                review(acceptable=index != first_failure),
                now=lambda: NOW,
            )

    assert result["status"] == "stopped"
    assert result["reason"] == "second_unsuccessful_attempt"
    assert result["completed_attempt_count"] == second_failure
    assert len(provider.calls) == second_failure
    assert not ledger.exists()


def test_storage_has_only_approved_attempt_fields_and_review_hard_stop_deletes(
    tmp_path: Path,
) -> None:
    registered, ledger = registration(tmp_path)
    run(run_canary_attempt(registered, FakeProvider(), ledger, attempt(), now=lambda: NOW))

    connection = sqlite3.connect(ledger)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(canary_attempts)")}
    connection.close()
    assert columns == {
        "attempt_number",
        "original",
        "user_visible_result",
        "attempt_status",
        "validator_disposition",
        "provider",
        "model",
        "reported_model_version",
        "prompt_sha256",
        "schema_sha256",
        "validator_sha256",
        "started_at",
        "completed_at",
        "elapsed_ms",
        "input_tokens",
        "output_tokens",
        "usd_micros",
        "duplicate_hash",
        "review_json",
    }
    assert not ({"raw_request", "raw_response", "rejected_provider_text", "credentials"} & columns)

    result = freeze_canary_review(
        registered,
        ledger,
        1,
        review(category="meaning", severity="severe"),
        now=lambda: NOW,
    )
    assert result["status"] == "stopped"
    assert result["reason"] == "severe_harmful_change"
    assert not ledger.exists()


def test_withdrawal_exports_then_deletes_managed_storage(tmp_path: Path) -> None:
    registered, ledger = registration(tmp_path)
    run(run_canary_attempt(registered, FakeProvider(), ledger, attempt(), now=lambda: NOW))
    export = tmp_path / "private-export.sqlite3"

    result = terminate_cleanup_canary(
        registered, ledger, "withdrawn", now=lambda: NOW, private_export_path=export
    )

    assert result["status"] == "withdrawn"
    assert export.is_file() and export.stat().st_mode & 0o777 == 0o600
    assert not ledger.exists()


def test_ten_reviewed_eligible_attempts_finish_and_delete(tmp_path: Path) -> None:
    registered, ledger = registration(tmp_path)
    provider = FakeProvider()

    for index in range(10):
        result = run(
            run_canary_attempt(
                registered, provider, ledger, attempt(f"attempt {index}"), now=lambda: NOW
            )
        )
        result = freeze_canary_review(
            registered,
            ledger,
            index + 1,
            review(
                acceptable=index != 0,
                category="meaning" if index == 0 else "none",
                severity="non_severe" if index == 0 else "none",
            ),
            now=lambda: NOW,
        )

    assert len(provider.calls) == 10
    assert result["status"] == "success"
    assert result["reason"] == "canary_complete"
    assert result["terminal_report"]["authorizes"] == "nothing_further"
    assert result["terminal_report"]["claims"] == "descriptive_only_no_baseline_or_inference"
    assert result["terminal_report"]["attempts"]["counted"] == 10
    assert result["terminal_report"]["reviews"]["acceptable"] == 9
    assert not ledger.exists()
    receipt = Path(f"{ledger}.deletion-receipt.json")
    assert receipt.is_file() and receipt.stat().st_mode & 0o777 == 0o600
    assert set(json.loads(receipt.read_text())) == {
        "protocol_or_run_id",
        "disposition",
        "deletion_timestamp",
        "counts",
    }
    with pytest.raises(CanaryError, match="terminal"):
        run(
            run_canary_attempt(
                registered, provider, ledger, attempt("attempt 11"), now=lambda: NOW
            )
        )
    assert len(provider.calls) == 10


def test_nine_successes_and_one_failure_passes_at_either_failure_position(
    tmp_path: Path,
) -> None:
    for failure_position in (1, 10):
        case_path = tmp_path / str(failure_position)
        case_path.mkdir(mode=0o700)
        registered, ledger = registration(case_path)
        failed = ProviderFailure(
            "failed",
            failure_class=ProviderFailureClass.TRANSIENT_ROUTE,
            input_tokens=0,
            output_tokens=0,
        )
        provider = FakeProvider()
        provider.results = [
            failed
            if index == failure_position
            else CanaryProviderResult(
                output=ProviderOutput(
                    text=f"Attempt {index}",
                    provider_id="openai",
                    model_id="gpt-5.6-luna",
                    elapsed_ms=100,
                    input_tokens=10,
                    output_tokens=5,
                ),
                reported_model_version="2026-09-01",
                request_storage_control="store_false",
                disclosure_detected=False,
            )
            for index in range(1, 11)
        ]

        for index in range(1, 11):
            result = run(
                run_canary_attempt(
                    registered, provider, ledger, attempt(f"attempt {index}"), now=lambda: NOW
                )
            )
            result = freeze_canary_review(
                registered,
                ledger,
                index,
                review(acceptable=index != failure_position),
                now=lambda: NOW,
            )

        assert result["status"] == "success"
        assert result["terminal_report"]["attempts"]["valid_outputs"] == 9


def test_second_non_severe_harm_fails_at_earliest_impossible_review(tmp_path: Path) -> None:
    registered, ledger = registration(tmp_path)
    provider = FakeProvider()

    for index in range(1, 3):
        run(
            run_canary_attempt(
                registered, provider, ledger, attempt(f"attempt {index}"), now=lambda: NOW
            )
        )
        result = freeze_canary_review(
            registered,
            ledger,
            index,
            review(category="meaning", severity="non_severe"),
            now=lambda: NOW,
        )

    assert result["status"] == "fail"
    assert result["reason"] == "non_severe_harm_limit_exceeded"
    assert len(provider.calls) == 2
    assert not ledger.exists()


def test_exact_deadline_expires_without_sending_and_before_deadline_remains_running(
    tmp_path: Path,
) -> None:
    before_path = tmp_path / "before"
    before_path.mkdir(mode=0o700)
    registered, ledger = registration(before_path)
    before = check_cleanup_canary(
        registered, ledger, now=lambda: NOW + timedelta(days=14) - timedelta(microseconds=1)
    )
    assert before["status"] == "running"
    assert ledger.exists()

    at_path = tmp_path / "at"
    at_path.mkdir(mode=0o700)
    registered, ledger = registration(at_path)
    provider = FakeProvider()
    expired = run(
        run_canary_attempt(
            registered, provider, ledger, attempt(), now=lambda: NOW + timedelta(days=14)
        )
    )
    assert expired["status"] == "expired"
    assert expired["reason"] == "incomplete_non_passing"
    assert expired["terminal_report"]["attempts"]["counted"] == 0
    assert provider.calls == []
    assert not ledger.exists()

    review_path = tmp_path / "review"
    review_path.mkdir(mode=0o700)
    registered, ledger = registration(review_path)
    run(run_canary_attempt(registered, FakeProvider(), ledger, attempt(), now=lambda: NOW))
    expired = freeze_canary_review(
        registered,
        ledger,
        1,
        review(),
        now=lambda: NOW + timedelta(days=14),
    )
    assert expired["status"] == "expired"
    assert expired["terminal_report"]["reviews"]["resolved"] == 0
    assert not ledger.exists()


def test_cancellation_is_a_stopped_terminal_disposition(tmp_path: Path) -> None:
    registered, ledger = registration(tmp_path)
    check_cleanup_canary(registered, ledger, now=lambda: NOW)

    result = terminate_cleanup_canary(registered, ledger, "cancelled", now=lambda: NOW)

    assert result["status"] == "stopped"
    assert result["reason"] == "cancelled"
    assert result["deletion_receipt"]["disposition"] == "stopped"


def test_cumulative_integer_micro_budget_allows_exact_boundary_then_stops(tmp_path: Path) -> None:
    ledger = tmp_path / "canary.sqlite3"
    evidence = provider_evidence()
    evidence["pricing"] = {
        "input_usd_micros_per_million_tokens": 1_000_000_000,
        "output_usd_micros_per_million_tokens": 0,
    }
    evidence["request_bound_usd_micros"] = 1_000_000
    confirmed = confirmation(ledger)
    confirmed["provider_evidence_sha256"] = digest(evidence)
    confirmed["budget_estimate_usd_micros"] = 2_000_000
    registered = register_cleanup_canary(
        eligibility(), SIGNING_KEY, contract(), evidence, confirmed, now=lambda: NOW
    )
    provider = FakeProvider(
        [
            CanaryProviderResult(
                output=ProviderOutput(
                    text=f"Attempt {index}",
                    provider_id="openai",
                    model_id="gpt-5.6-luna",
                    elapsed_ms=100,
                    input_tokens=1_000,
                    output_tokens=0,
                ),
                reported_model_version="2026-09-01",
                request_storage_control="store_false",
                disclosure_detected=False,
            )
            for index in range(1, 3)
        ]
    )

    for index in range(1, 3):
        result = run(
            run_canary_attempt(
                registered, provider, ledger, attempt(f"attempt {index}"), now=lambda: NOW
            )
        )
        assert result["actual_cost_usd_micros"] == index * 1_000_000
        freeze_canary_review(registered, ledger, index, review(), now=lambda: NOW)

    stopped = run(
        run_canary_attempt(registered, provider, ledger, attempt("attempt 3"), now=lambda: NOW)
    )
    assert stopped["status"] == "stopped"
    assert stopped["reason"] == "next_request_cannot_be_reserved"
    assert len(provider.calls) == 2


def test_terminal_deletion_removes_every_managed_artifact(tmp_path: Path) -> None:
    ledger = tmp_path / "canary.sqlite3"
    log = tmp_path / "canary.log"
    cache = tmp_path / "cache"
    cache.mkdir(mode=0o700)
    (cache / "response.cache").write_text("managed")
    log.write_text("content-free log")
    registered = register_cleanup_canary(
        eligibility(),
        SIGNING_KEY,
        contract(),
        provider_evidence(),
        confirmation(ledger, log, cache),
        now=lambda: NOW,
    )
    check_cleanup_canary(registered, ledger, now=lambda: NOW)
    Path(f"{ledger}-wal").write_text("managed sqlite sidecar")

    result = terminate_cleanup_canary(registered, ledger, "withdrawn", now=lambda: NOW)

    assert not ledger.exists()
    assert not Path(f"{ledger}-wal").exists()
    assert not log.exists()
    assert not cache.exists()
    assert result["deletion_receipt"]["counts"] == {"files": 3, "directories": 1}
    assert set(result["deletion_receipt"]) == {
        "protocol_or_run_id",
        "disposition",
        "deletion_timestamp",
        "counts",
    }


def test_confirmation_evidence_supports_full_window_but_missing_usage_stops(
    tmp_path: Path,
) -> None:
    registered, ledger = registration(tmp_path)
    day_thirteen = NOW + timedelta(days=13)
    result = run(
        run_canary_attempt(registered, FakeProvider(), ledger, attempt(), now=lambda: day_thirteen)
    )
    assert result["completed_attempt_count"] == 1

    ledger.unlink()
    registered, ledger = registration(tmp_path)
    provider = FakeProvider(
        [ProviderFailure("failed", failure_class=ProviderFailureClass.TRANSIENT_ROUTE)]
    )
    result = run(run_canary_attempt(registered, provider, ledger, attempt(), now=lambda: NOW))
    assert result["completed_attempt_count"] == 1
    assert result["status"] == "stopped"
    assert result["reason"] == "missing_or_malformed_usage"
    assert not ledger.exists()
