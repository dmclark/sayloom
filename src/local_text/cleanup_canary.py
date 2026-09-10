"""Isolated, explicitly authorized execution of the finite cleanup canary."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
import stat
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from local_text.cleanup import (
    OPENAI_GPT_56_LUNA,
    ProviderFailure,
    ProviderFailureClass,
    ProviderOutput,
    ProviderRejectedOutputError,
    _validate_output,
)
from local_text.cleanup_contract import BENCHMARK_DEADLINE_SECONDS, canonical_json

PACKET_VERSION = "cleanup-canary-eligibility-v1"
CANARY_VERSION = "cleanup-canary-v1"
PACKET_AUTHORIZATION = "request_separate_explicit_10_cleanup_canary_confirmation_only"
MAXIMUM_ATTEMPTS = 10
CANARY_BUDGET_USD_MICROS = 2_000_000
EVIDENCE_MAX_AGE = timedelta(hours=24)
WINDOW = timedelta(days=14)
REQUIRED_BENCHMARK_GATES = {
    "candidate_mean_effort_relative_decrease",
    "paired_bootstrap_relative_degradation_upper_bound",
    "candidate_valid_output_rate_absolute_drop",
    "candidate_accepted_source_contract_violations",
    "candidate_severe_harmful_changes",
    "candidate_p95_latency_increase_ms",
}


class CanaryError(ValueError):
    """A content-free canary validation or execution error."""


@dataclass(frozen=True)
class CanaryProviderResult:
    output: ProviderOutput
    reported_model_version: str | None
    request_storage_control: str
    disclosure_detected: bool
    validator_bypassed: bool = False


class CanaryProvider(Protocol):
    provider_id: str
    model: str
    candidate_contract_sha256: str

    async def clean(self, original_text: str, system_prompt: str) -> CanaryProviderResult: ...


@dataclass(frozen=True)
class CanaryAttempt:
    original: str
    newly_user_initiated_in_pilot: bool
    explicitly_confirmed_dictation_derived: bool
    locally_valid: bool
    manually_candidate_selected: bool

    def eligible(self) -> bool:
        return (
            self.newly_user_initiated_in_pilot
            and self.explicitly_confirmed_dictation_derived
            and self.locally_valid
            and self.manually_candidate_selected
            and bool(self.original.strip())
            and len(self.original) <= 100_000
        )


@dataclass(frozen=True)
class CanaryInvariants:
    withdrawn: bool = False
    cancelled: bool = False
    consent_valid: bool = True
    manifest_unchanged: bool = True
    code_unchanged: bool = True
    configuration_unchanged: bool = True
    isolation_intact: bool = True
    disclosure_intact: bool = True
    text_logging_safe: bool = True
    storage_intact: bool = True
    write_back_disabled: bool = True
    stable_resources_inaccessible: bool = True

    def stop_reason(self) -> str | None:
        checks = (
            (self.withdrawn, "withdrawn"),
            (self.cancelled, "cancelled"),
            (not self.consent_valid, "consent_invalid"),
            (not self.manifest_unchanged, "manifest_changed"),
            (not self.code_unchanged, "code_changed"),
            (not self.configuration_unchanged, "configuration_changed"),
            (not self.isolation_intact, "isolation_violation"),
            (not self.disclosure_intact, "disclosure_violation"),
            (not self.text_logging_safe, "text_logging_violation"),
            (not self.storage_intact, "storage_violation"),
            (not self.write_back_disabled, "write_back_violation"),
            (not self.stable_resources_inaccessible, "stable_resource_violation"),
        )
        return next((reason for failed, reason in checks if failed), None)


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _utc(value: object, message: str) -> datetime:
    if not isinstance(value, str):
        raise CanaryError(message)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CanaryError(message) from None
    if parsed.tzinfo is None:
        raise CanaryError(message)
    return parsed.astimezone(UTC)


def _candidate_arm(contract: object) -> dict[str, object] | None:
    if not isinstance(contract, dict) or not isinstance(contract.get("arms"), list):
        return None
    matches = [arm for arm in contract["arms"] if arm.get("arm_id") == "candidate_paid_openai"]
    return matches[0] if len(matches) == 1 else None


def _valid_artifact(artifact: object, *, version: str | None = None) -> bool:
    if not isinstance(artifact, dict) or not isinstance(artifact.get("sha256"), str):
        return False
    if version is not None and artifact.get("version") != version:
        return False
    try:
        value = base64.b64decode(artifact["canonical_bytes_base64"], validate=True)
    except (KeyError, TypeError, ValueError):
        return False
    return hashlib.sha256(value).hexdigest() == artifact["sha256"]


def _validate_candidate_contract(contract: object) -> None:
    arm = _candidate_arm(contract)
    execution = contract.get("execution", {}) if isinstance(contract, dict) else {}
    artifacts = contract.get("artifacts", {}) if isinstance(contract, dict) else {}
    request = arm.get("request", {}) if arm else {}
    settings = request.get("settings", {}) if isinstance(request, dict) else {}
    output_cap = arm.get("output_cap", {}) if arm else {}
    if (
        not isinstance(contract, dict)
        or contract.get("snapshot_version") != "cleanup-execution-contract-v1"
        or not _valid_artifact(artifacts.get("effective_prompt"))
        or not _valid_artifact(artifacts.get("schema"), version="cleanup-result-v1")
        or not _valid_artifact(
            artifacts.get("validator_implementation"), version="source-preserving-validator-v1"
        )
        or arm is None
        or arm.get("provider") != "openai"
        or arm.get("deadline_seconds") != BENCHMARK_DEADLINE_SECONDS
        or request.get("api_mode") != "responses"
        or request.get("model") != OPENAI_GPT_56_LUNA
        or settings.get("reasoning_effort") != "none"
        or settings.get("store") is not False
        or output_cap.get("version") != "input-dependent-output-cap-v1"
        or output_cap.get("thinking_headroom_tokens") != 0
        or execution.get("deadline_seconds") != BENCHMARK_DEADLINE_SECONDS
        or execution.get("retries") != 0
        or execution.get("fallback") is not False
    ):
        raise CanaryError("candidate contract is invalid")


def register_cleanup_canary(
    eligibility: object,
    signing_key: bytes,
    request_contract: object,
    provider_evidence: object,
    confirmation: object,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Validate benchmark eligibility and freeze one separately confirmed canary."""
    if not isinstance(eligibility, dict) or not isinstance(eligibility.get("packet"), dict):
        raise CanaryError("eligibility packet is invalid")
    packet = eligibility["packet"]
    signature = eligibility.get("signature")
    expected_signature = hmac.new(signing_key, canonical_json(packet), hashlib.sha256).hexdigest()
    if (
        not signing_key
        or not isinstance(signature, dict)
        or signature.get("algorithm") != "hmac-sha256"
        or not hmac.compare_digest(str(signature.get("value", "")), expected_signature)
    ):
        raise CanaryError("eligibility packet signature is invalid")
    gates = packet.get("gates")
    receipt = packet.get("deletion_receipt")
    candidate = packet.get("candidate_configuration")
    if (
        packet.get("packet_version") != PACKET_VERSION
        or packet.get("authorizes") != PACKET_AUTHORIZATION
        or not isinstance(gates, list)
        or {gate.get("gate") for gate in gates if isinstance(gate, dict)}
        != REQUIRED_BENCHMARK_GATES
        or len(gates) != len(REQUIRED_BENCHMARK_GATES)
        or any(not isinstance(gate, dict) or gate.get("disposition") != "pass" for gate in gates)
        or packet.get("protocol_deviations") != []
        or not isinstance(receipt, dict)
        or receipt.get("protocol_or_run_id") != packet.get("run_id")
        or receipt.get("disposition") != "completion"
        or not isinstance(receipt.get("counts"), dict)
        or not isinstance(candidate, dict)
        or candidate.get("deadline_seconds") != BENCHMARK_DEADLINE_SECONDS
        or candidate.get("request_contract") != request_contract
    ):
        raise CanaryError("eligibility packet does not authorize this candidate contract")
    _validate_candidate_contract(request_contract)
    if not isinstance(provider_evidence, dict):
        raise CanaryError("provider evidence is invalid")
    current_time = now().astimezone(UTC)
    retrieved_at = _utc(provider_evidence.get("retrieved_at"), "provider evidence is invalid")
    model = provider_evidence.get("model")
    if (
        retrieved_at > current_time
        or current_time - retrieved_at > EVIDENCE_MAX_AGE
        or provider_evidence.get("material_change") is not False
        or model != candidate.get("model")
        or not provider_evidence.get("official_sources")
        or not provider_evidence.get("retention_and_data_use")
        or not provider_evidence.get("account_controls")
        or not isinstance(provider_evidence.get("pricing"), dict)
    ):
        raise CanaryError("provider evidence is not current and complete")
    if not isinstance(confirmation, dict):
        raise CanaryError("canary confirmation is invalid")
    confirmed_at = _utc(confirmation.get("confirmed_at"), "canary confirmation is invalid")
    starts_at = _utc(confirmation.get("starts_at"), "canary confirmation is invalid")
    ends_at = _utc(confirmation.get("ends_at"), "canary confirmation is invalid")
    release_at = _utc(confirmation.get("evidence_release_at"), "canary confirmation is invalid")
    locations = confirmation.get("storage_locations")
    location_paths = (
        [Path(location) for location in locations]
        if isinstance(locations, list) and all(isinstance(location, str) for location in locations)
        else []
    )
    if (
        confirmation.get("confirmed") is not True
        or not confirmation.get("canary_run_id")
        or confirmation.get("benchmark_manifest_sha256") != packet.get("manifest_sha256")
        or confirmation.get("benchmark_report_sha256") != packet.get("report_sha256")
        or confirmation.get("candidate_configuration") != candidate
        or confirmation.get("provider_evidence_sha256") != _digest(provider_evidence)
        or confirmation.get("maximum_calls") != MAXIMUM_ATTEMPTS
        or confirmation.get("candidate_only") is not True
        or confirmation.get("manual_selection_only") is not True
        or confirmation.get("requests_per_attempt") != 1
        or confirmation.get("baseline_duplication_retry_fallback_routing_shadow_or_resend")
        is not False
        or confirmation.get("budget_cap_usd_micros") != CANARY_BUDGET_USD_MICROS
        or not isinstance(confirmation.get("budget_estimate_usd_micros"), int)
        or confirmation["budget_estimate_usd_micros"] > CANARY_BUDGET_USD_MICROS
        or confirmation.get("pre_send_budget_enforcement") is not True
        or confirmed_at != starts_at
        or ends_at != confirmed_at + WINDOW
        or release_at != ends_at
        or not isinstance(locations, list)
        or not locations
        or any(not isinstance(location, str) for location in locations)
        or len(set(locations)) != len(locations)
        or any(
            not Path(location).is_absolute()
            or Path(location) == Path(Path(location).anchor)
            for location in locations
        )
        or any(
            left != right and left.is_relative_to(right)
            for left in location_paths
            for right in location_paths
        )
        or confirmation.get("managed_deletion") is not True
        or confirmation.get("optional_private_export_before_deletion") is not True
        or confirmation.get("withdrawal_stops_and_deletes") is not True
        or confirmation.get("provider_requests_irretractable") is not True
    ):
        raise CanaryError("canary confirmation is invalid")
    manifest = {
        "canary_version": CANARY_VERSION,
        "run_id": confirmation["canary_run_id"],
        "registered_at": current_time.isoformat(),
        "eligibility": {
            "benchmark_run_id": packet["run_id"],
            "manifest_sha256": packet["manifest_sha256"],
            "report_sha256": packet["report_sha256"],
            "packet_sha256": _digest(packet),
        },
        "candidate_configuration": candidate,
        "provider_evidence": provider_evidence,
        "provider_evidence_sha256": _digest(provider_evidence),
        "confirmation": confirmation,
        "budget": {
            "total_usd_micros": CANARY_BUDGET_USD_MICROS,
            "request_bound_usd_micros": provider_evidence.get("request_bound_usd_micros"),
            "pre_send_stop": True,
        },
        "storage": {"locations": locations, "write_back_to_live_corpus": False},
    }
    return {"manifest": manifest, "manifest_sha256": _digest(manifest)}


def _connect(path: Path) -> sqlite3.Connection:
    if (
        not path.parent.is_dir()
        or path.parent.stat().st_uid != os.getuid()
        or stat.S_IMODE(path.parent.stat().st_mode) & 0o077
        or path.is_symlink()
        or (path.exists() and (not path.is_file() or path.stat().st_uid != os.getuid()))
        or (path.exists() and stat.S_IMODE(path.stat().st_mode) & 0o077)
    ):
        raise CanaryError("canary storage is not private")
    connection = sqlite3.connect(path)
    os.chmod(path, 0o600)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA synchronous=FULL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS canary_run (
            run_id TEXT PRIMARY KEY,
            manifest_sha256 TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT NOT NULL,
            completed_attempt_count INTEGER NOT NULL,
            unsuccessful_attempt_count INTEGER NOT NULL,
            actual_cost_usd_micros INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS canary_attempts (
            attempt_number INTEGER PRIMARY KEY,
            original TEXT NOT NULL,
            user_visible_result TEXT,
            attempt_status TEXT NOT NULL,
            validator_disposition TEXT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            reported_model_version TEXT,
            prompt_sha256 TEXT NOT NULL,
            schema_sha256 TEXT NOT NULL,
            validator_sha256 TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            elapsed_ms INTEGER,
            input_tokens INTEGER,
            output_tokens INTEGER,
            usd_micros INTEGER,
            duplicate_hash TEXT NOT NULL UNIQUE,
            review_json TEXT
        );
        """
    )
    return connection


def _receipt_path(ledger_path: Path) -> Path:
    return Path(f"{ledger_path}.deletion-receipt.json")


def _manifest(registration: object, ledger_path: Path) -> dict[str, object]:
    if _receipt_path(ledger_path).exists():
        raise CanaryError("canary is terminal")
    if not isinstance(registration, dict) or not isinstance(registration.get("manifest"), dict):
        raise CanaryError("canary registration is invalid")
    manifest = registration["manifest"]
    if (
        registration.get("manifest_sha256") != _digest(manifest)
        or manifest.get("canary_version") != CANARY_VERSION
        or str(ledger_path) not in manifest.get("storage", {}).get("locations", [])
    ):
        raise CanaryError("canary registration changed")
    return manifest


def _summary(connection: sqlite3.Connection) -> dict[str, object]:
    row = connection.execute("SELECT * FROM canary_run").fetchone()
    if row is None:
        raise CanaryError("canary ledger is invalid")
    return dict(row)


def _terminal_report(
    connection: sqlite3.Connection,
    registration: dict[str, object],
    disposition: str,
    reason: str,
    at: datetime,
) -> dict[str, object]:
    summary = _summary(connection)
    rows = connection.execute(
        "SELECT validator_disposition, elapsed_ms, input_tokens, output_tokens, usd_micros, "
        "review_json FROM canary_attempts ORDER BY attempt_number"
    ).fetchall()
    reviews = [json.loads(row["review_json"]) for row in rows if row["review_json"] is not None]
    validator_dispositions: dict[str, int] = {}
    for row in rows:
        value = row["validator_disposition"]
        if value is not None:
            validator_dispositions[value] = validator_dispositions.get(value, 0) + 1
    failure_classes = {
        value: count for value, count in validator_dispositions.items() if value != "accepted"
    }
    return {
        "report_version": "cleanup-canary-terminal-report-v1",
        "run_id": registration["manifest"]["run_id"],
        "disposition": disposition,
        "reason": reason,
        "terminal_at": at.isoformat(),
        "visibility": "private_local",
        "attempts": {
            "counted": summary["completed_attempt_count"],
            "valid_outputs": summary["completed_attempt_count"]
            - summary["unsuccessful_attempt_count"],
            "unsuccessful": summary["unsuccessful_attempt_count"],
            "validator_dispositions": validator_dispositions,
            "failure_classes": failure_classes,
        },
        "reviews": {
            "resolved": len(reviews),
            "acceptable": sum(review["acceptability"] == "acceptable" for review in reviews),
            "unacceptable": sum(review["acceptability"] == "unacceptable" for review in reviews),
            "accepted_source_contract_violations": sum(
                review["accepted_source_contract_violation"] for review in reviews
            ),
            "severe_harmful_changes": sum(review["severity"] == "severe" for review in reviews),
            "non_severe_harmful_changes": sum(
                review["severity"] == "non_severe" for review in reviews
            ),
            "rationales": [review["rationale"] for review in reviews],
        },
        "latency_ms": [row["elapsed_ms"] for row in rows],
        "usage": {
            "input_tokens": [row["input_tokens"] for row in rows],
            "output_tokens": [row["output_tokens"] for row in rows],
        },
        "cost": {
            "usd_micros": [row["usd_micros"] for row in rows],
            "total_usd_micros": summary["actual_cost_usd_micros"],
        },
        "claims": "descriptive_only_no_baseline_or_inference",
        "authorizes": "nothing_further",
        "does_not_authorize": [
            "continuation",
            "repeat_canary",
            "automatic_routing_or_fallback",
            "stable_default_change",
            "provider_promotion",
            "effectiveness_claim",
        ],
    }


def _managed_artifact_counts(paths: list[Path]) -> dict[str, int]:
    files = 0
    directories = 0
    for path in paths:
        if path.is_symlink() or path.is_file():
            files += 1
        elif path.is_dir():
            directories += 1
            for child in path.rglob("*"):
                if child.is_symlink() or child.is_file():
                    files += 1
                elif child.is_dir():
                    directories += 1
    return {"files": files, "directories": directories}


def _delete_managed_artifacts(paths: list[Path]) -> None:
    for path in sorted(paths, key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)


def _terminal_result(
    registration: dict[str, object],
    ledger_path: Path,
    disposition: str,
    reason: str,
    at: datetime,
    *,
    terminal_report: dict[str, object],
    private_export_path: Path | None = None,
) -> dict[str, object]:
    managed_paths = [Path(path) for path in registration["manifest"]["storage"]["locations"]]
    managed_paths.extend(
        Path(f"{ledger_path}{suffix}") for suffix in ("-journal", "-shm", "-wal")
    )
    managed_paths = list(dict.fromkeys(managed_paths))
    receipt_path = _receipt_path(ledger_path)
    if private_export_path is not None:
        if (
            private_export_path.exists()
            or not private_export_path.parent.is_dir()
            or private_export_path == receipt_path
            or any(
                private_export_path == path or private_export_path.is_relative_to(path)
                for path in managed_paths
            )
        ):
            raise CanaryError("private export location is invalid")
        shutil.copy2(ledger_path, private_export_path)
        os.chmod(private_export_path, 0o600)
    counts = _managed_artifact_counts(managed_paths)
    _delete_managed_artifacts(managed_paths)
    receipt = {
        "protocol_or_run_id": registration["manifest"]["run_id"],
        "disposition": disposition,
        "deletion_timestamp": at.isoformat(),
        "counts": counts,
    }
    receipt_descriptor = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(receipt_descriptor, "w", encoding="utf-8") as receipt_file:
        receipt_file.write(canonical_json(receipt).decode("utf-8"))
        receipt_file.flush()
        os.fsync(receipt_file.fileno())
    return {
        "run_id": registration["manifest"]["run_id"],
        "status": disposition,
        "reason": reason,
        "terminal_report": terminal_report,
        "deletion_receipt": receipt,
    }


def _stop(
    connection: sqlite3.Connection,
    registration: dict[str, object],
    ledger_path: Path,
    reason: str,
    at: datetime,
    *,
    private_export_path: Path | None = None,
) -> dict[str, object]:
    summary = _summary(connection)
    with connection:
        connection.execute("UPDATE canary_run SET status = 'stopped', reason = ?", (reason,))
    report = _terminal_report(connection, registration, "stopped", reason, at)
    connection.close()
    return {
        **summary,
        **_terminal_result(
            registration,
            ledger_path,
            "stopped",
            reason,
            at,
            terminal_report=report,
            private_export_path=private_export_path,
        ),
    }


def _expire(
    connection: sqlite3.Connection,
    registration: dict[str, object],
    ledger_path: Path,
    at: datetime,
    *,
    private_export_path: Path | None = None,
) -> dict[str, object]:
    summary = _summary(connection)
    with connection:
        connection.execute(
            "UPDATE canary_run SET status = 'expired', reason = 'incomplete_non_passing'"
        )
    report = _terminal_report(
        connection, registration, "expired", "incomplete_non_passing", at
    )
    connection.close()
    return {
        **summary,
        **_terminal_result(
            registration,
            ledger_path,
            "expired",
            "incomplete_non_passing",
            at,
            terminal_report=report,
            private_export_path=private_export_path,
        ),
    }


def _cost(tokens: int, rate: int) -> int:
    return (tokens * rate + 999_999) // 1_000_000


def _valid_usage(value: object, maximum: object) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and isinstance(maximum, int)
        and not isinstance(maximum, bool)
        and 0 <= value <= maximum
    )


def _ensure_run(
    connection: sqlite3.Connection,
    registration: dict[str, object],
    manifest: dict[str, object],
) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM canary_run").fetchone()
    if row is None:
        with connection:
            connection.execute(
                "INSERT INTO canary_run VALUES (?, ?, 'running', 'pending', 0, 0, 0)",
                (manifest["run_id"], registration["manifest_sha256"]),
            )
        row = connection.execute("SELECT * FROM canary_run").fetchone()
    if (
        row is None
        or row["run_id"] != manifest["run_id"]
        or row["manifest_sha256"] != registration["manifest_sha256"]
    ):
        raise CanaryError("canary ledger does not match registration")
    return row


def check_cleanup_canary(
    registration: object,
    ledger_path: Path,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    invariants: Callable[[], CanaryInvariants] = CanaryInvariants,
    private_export_path: Path | None = None,
) -> dict[str, object]:
    """Initialize or inspect the canary, enforcing stops that do not require a new attempt."""
    manifest = _manifest(registration, ledger_path)
    current_time = now().astimezone(UTC)
    connection = _connect(ledger_path)
    try:
        row = _ensure_run(connection, registration, manifest)
        if row["status"] != "running":
            return dict(row)
        if connection.execute(
            "SELECT 1 FROM canary_attempts WHERE attempt_status = 'sent'"
        ).fetchone():
            return _stop(
                connection, registration, ledger_path, "ambiguous_in_flight_request", current_time
            )
        reason = invariants().stop_reason()
        if reason is not None:
            return _stop(
                connection,
                registration,
                ledger_path,
                reason,
                current_time,
                private_export_path=private_export_path,
            )
        confirmation = manifest["confirmation"]
        if current_time >= _utc(confirmation["ends_at"], "canary window is invalid"):
            return _expire(
                connection,
                registration,
                ledger_path,
                current_time,
                private_export_path=private_export_path,
            )
        return _summary(connection)
    finally:
        try:
            connection.close()
        except sqlite3.ProgrammingError:
            pass


async def run_canary_attempt(
    registration: object,
    provider: CanaryProvider,
    ledger_path: Path,
    attempt: CanaryAttempt,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    invariants: Callable[[], CanaryInvariants] = CanaryInvariants,
    after_reservation: Callable[[], None] | None = None,
    after_send: Callable[[], None] | None = None,
    private_export_path: Path | None = None,
) -> dict[str, object]:
    """Accept one local attempt and make at most one candidate request."""
    manifest = _manifest(registration, ledger_path)
    current_time = now().astimezone(UTC)
    connection = _connect(ledger_path)
    try:
        row = _ensure_run(connection, registration, manifest)
        if row["status"] != "running":
            return dict(row)

        if connection.execute(
            "SELECT 1 FROM canary_attempts WHERE attempt_status = 'sent'"
        ).fetchone():
            return _stop(
                connection, registration, ledger_path, "ambiguous_in_flight_request", current_time
            )
        reason = invariants().stop_reason()
        confirmation = manifest["confirmation"]
        if reason is None and current_time >= _utc(
            confirmation["ends_at"], "canary window is invalid"
        ):
            reason = "incomplete_non_passing"
        if reason:
            if reason == "incomplete_non_passing":
                return _expire(
                    connection,
                    registration,
                    ledger_path,
                    current_time,
                    private_export_path=private_export_path,
                )
            return _stop(
                connection,
                registration,
                ledger_path,
                reason,
                current_time,
                private_export_path=private_export_path,
            )
        pending_review = connection.execute(
            "SELECT 1 FROM canary_attempts "
            "WHERE attempt_status = 'terminal' AND review_json IS NULL"
        ).fetchone()
        if pending_review:
            return _stop(connection, registration, ledger_path, "unresolved_review", current_time)
        if not attempt.eligible():
            return {**_summary(connection), "accepted": False, "reason": "ineligible_local_input"}
        duplicate_hash = hashlib.sha256(
            unicodedata.normalize("NFC", attempt.original.replace("\r\n", "\n")).encode("utf-8")
        ).hexdigest()
        duplicate = connection.execute(
            "SELECT attempt_number, original, attempt_status FROM canary_attempts "
            "WHERE duplicate_hash = ?",
            (duplicate_hash,),
        ).fetchone()
        resuming_reservation = (
            duplicate is not None
            and duplicate["attempt_status"] == "reserved"
            and duplicate["original"] == attempt.original
        )
        if duplicate is not None and not resuming_reservation:
            return {**_summary(connection), "accepted": False, "reason": "duplicate_original"}
        run = _summary(connection)
        bound = manifest["budget"]["request_bound_usd_micros"]
        if (
            run["completed_attempt_count"] >= MAXIMUM_ATTEMPTS
            or not isinstance(bound, int)
            or isinstance(bound, bool)
            or bound < 0
            or run["actual_cost_usd_micros"] + bound > CANARY_BUDGET_USD_MICROS
        ):
            return _stop(
                connection,
                registration,
                ledger_path,
                "next_request_cannot_be_reserved",
                current_time,
            )
        candidate = manifest["candidate_configuration"]
        model_evidence = manifest["provider_evidence"]["model"]
        if (
            provider.provider_id != "openai"
            or provider.model != OPENAI_GPT_56_LUNA
            or getattr(provider, "candidate_contract_sha256", None)
            != _digest(candidate["request_contract"])
            or model_evidence.get("provider") != provider.provider_id
            or model_evidence.get("model") != provider.model
        ):
            return _stop(
                connection, registration, ledger_path, "configuration_changed", current_time
            )
        artifacts = candidate["request_contract"]["artifacts"]
        try:
            prompt = base64.b64decode(
                artifacts["effective_prompt"]["canonical_bytes_base64"], validate=True
            ).decode("utf-8")
        except (KeyError, TypeError, ValueError, UnicodeDecodeError):
            raise CanaryError("candidate contract is invalid") from None
        attempt_number = (
            duplicate["attempt_number"]
            if resuming_reservation
            else run["completed_attempt_count"] + 1
        )
        if not resuming_reservation:
            with connection:
                connection.execute(
                    "INSERT INTO canary_attempts VALUES "
                    "(?, ?, NULL, 'reserved', NULL, 'openai', ?, NULL, ?, ?, ?, ?, NULL, "
                    "NULL, NULL, NULL, NULL, ?, NULL)",
                    (
                        attempt_number,
                        attempt.original,
                        OPENAI_GPT_56_LUNA,
                        artifacts["effective_prompt"]["sha256"],
                        artifacts["schema"]["sha256"],
                        artifacts["validator_implementation"]["sha256"],
                        current_time.isoformat(),
                        duplicate_hash,
                    ),
                )
            if after_reservation:
                after_reservation()
        with connection:
            connection.execute(
                "UPDATE canary_attempts SET attempt_status = 'sent' WHERE attempt_number = ?",
                (attempt_number,),
            )

        result: CanaryProviderResult | None = None
        error: Exception | None = None
        try:
            result = await asyncio.wait_for(
                provider.clean(attempt.original, prompt), timeout=BENCHMARK_DEADLINE_SECONDS
            )
        except TimeoutError as caught:
            error = caught
        except Exception as caught:
            error = caught
        if after_send:
            after_send()
        outcome = "success"
        visible = attempt.original
        validator_disposition = "accepted"
        reported_version = None
        elapsed_ms = BENCHMARK_DEADLINE_SECONDS * 1_000 if error else 0
        input_tokens = output_tokens = None
        hard_stop: str | None = None
        if isinstance(error, TimeoutError):
            outcome, validator_disposition = "timeout", "fail_open_timeout"
        elif isinstance(error, ProviderRejectedOutputError):
            outcome = (
                "refusal"
                if error.failure_class == ProviderFailureClass.SAFETY_POLICY
                else "rejection"
            )
            validator_disposition = f"fail_open_{outcome}"
            elapsed_ms, input_tokens, output_tokens = (
                error.elapsed_ms,
                error.input_tokens,
                error.output_tokens,
            )
        elif isinstance(error, ProviderFailure):
            outcome = "failure"
            validator_disposition = f"fail_open_failure_{error.failure_class.value}"
            elapsed_ms, input_tokens, output_tokens = (
                error.elapsed_ms,
                error.input_tokens,
                error.output_tokens,
            )
            if error.failure_class in {
                ProviderFailureClass.PERMANENT_CONFIGURATION,
                ProviderFailureClass.PERMANENT_QUOTA,
            }:
                hard_stop = "permanent_provider_failure"
        elif error is not None or not isinstance(result, CanaryProviderResult):
            outcome, validator_disposition = "failure", "fail_open_failure"
        else:
            output = result.output
            reported_version = result.reported_model_version
            elapsed_ms, input_tokens, output_tokens = (
                output.elapsed_ms,
                output.input_tokens,
                output.output_tokens,
            )
            if (
                output.provider_id != "openai"
                or output.model_id != OPENAI_GPT_56_LUNA
                or reported_version != model_evidence.get("reported_version")
            ):
                hard_stop = "reported_model_mismatch"
                outcome, validator_disposition = "failure", "fail_open_attribution"
            elif result.request_storage_control != "store_false":
                hard_stop = "storage_violation"
                outcome, validator_disposition = "failure", "fail_open_storage"
            elif result.disclosure_detected:
                hard_stop = "disclosure_violation"
                outcome, validator_disposition = "failure", "fail_open_disclosure"
            elif result.validator_bypassed:
                hard_stop = "accepted_source_contract_violation"
                outcome, validator_disposition = "failure", "validator_bypassed"
            else:
                try:
                    _validate_output(attempt.original, output.text)
                except ProviderRejectedOutputError:
                    outcome, validator_disposition = "rejection", "rejected"
                else:
                    visible = output.text
            if output.elapsed_ms > BENCHMARK_DEADLINE_SECONDS * 1_000:
                outcome, visible, validator_disposition = (
                    "timeout",
                    attempt.original,
                    "fail_open_deadline_breach",
                )
        evidence = manifest["provider_evidence"]
        actual = 0
        if hard_stop is None and isinstance(error, (TimeoutError, ProviderRejectedOutputError)):
            actual = bound
        elif hard_stop is None:
            if not _valid_usage(
                input_tokens, evidence.get("input_token_maximum")
            ) or not _valid_usage(output_tokens, evidence.get("output_token_maximum")):
                hard_stop = "missing_or_malformed_usage"
            else:
                pricing = evidence["pricing"]
                actual = _cost(
                    input_tokens, pricing["input_usd_micros_per_million_tokens"]
                ) + _cost(output_tokens, pricing["output_usd_micros_per_million_tokens"])
                if (
                    actual > bound
                    or run["actual_cost_usd_micros"] + actual > CANARY_BUDGET_USD_MICROS
                ):
                    hard_stop = "actual_budget_breach"
        unsuccessful = outcome != "success"
        completed_at = now().astimezone(UTC)
        with connection:
            connection.execute(
                "UPDATE canary_attempts SET attempt_status = 'terminal', user_visible_result = ?, "
                "validator_disposition = ?, reported_model_version = ?, completed_at = ?, "
                "elapsed_ms = ?, input_tokens = ?, output_tokens = ?, usd_micros = ? "
                "WHERE attempt_number = ?",
                (
                    visible,
                    validator_disposition,
                    reported_version,
                    completed_at.isoformat(),
                    elapsed_ms,
                    input_tokens,
                    output_tokens,
                    actual,
                    attempt_number,
                ),
            )
            connection.execute(
                "UPDATE canary_run SET completed_attempt_count = completed_attempt_count + 1, "
                "unsuccessful_attempt_count = unsuccessful_attempt_count + ?, "
                "actual_cost_usd_micros = actual_cost_usd_micros + ?",
                (int(unsuccessful), actual),
            )
        summary = _summary(connection)
        if hard_stop:
            return _stop(
                connection,
                registration,
                ledger_path,
                hard_stop,
                completed_at,
                private_export_path=private_export_path,
            )
        if summary["unsuccessful_attempt_count"] >= 2:
            return _stop(
                connection,
                registration,
                ledger_path,
                "second_unsuccessful_attempt",
                completed_at,
                private_export_path=private_export_path,
            )
        return {**summary, "accepted": True, "attempt_number": attempt_number, "outcome": outcome}
    finally:
        try:
            connection.close()
        except sqlite3.ProgrammingError:
            pass


def freeze_canary_review(
    registration: object,
    ledger_path: Path,
    attempt_number: int,
    review: object,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    invariants: Callable[[], CanaryInvariants] = CanaryInvariants,
    private_export_path: Path | None = None,
) -> dict[str, object]:
    """Freeze the corpus owner's required review before another call is eligible."""
    manifest = _manifest(registration, ledger_path)
    connection = _connect(ledger_path)
    try:
        _ensure_run(connection, registration, manifest)
        current_time = now().astimezone(UTC)
        reason = invariants().stop_reason()
        if reason is not None:
            return _stop(
                connection,
                registration,
                ledger_path,
                reason,
                current_time,
                private_export_path=private_export_path,
            )
        if current_time >= _utc(
            manifest["confirmation"]["ends_at"], "canary window is invalid"
        ):
            return _expire(
                connection,
                registration,
                ledger_path,
                current_time,
                private_export_path=private_export_path,
            )
        if not isinstance(review, dict) or set(review) != {
            "acceptability",
            "accepted_source_contract_violation",
            "harmful_change_category",
            "severity",
            "rationale",
        }:
            raise CanaryError("canary review is invalid")
        if (
            review["acceptability"] not in {"acceptable", "unacceptable"}
            or not isinstance(review["accepted_source_contract_violation"], bool)
            or review["harmful_change_category"]
            not in {
                "none",
                "meaning",
                "invented_content",
                "qualification_or_negation",
                "number_or_date",
                "name_or_technical_term",
                "link_code_or_identifier",
                "quotation",
                "layout",
            }
            or review["severity"] not in {"none", "non_severe", "severe"}
            or (review["harmful_change_category"] == "none")
            != (review["severity"] == "none")
            or not isinstance(review["rationale"], str)
            or not review["rationale"].strip()
        ):
            raise CanaryError("canary review is invalid")
        row = connection.execute(
            "SELECT attempt_status, review_json FROM canary_attempts WHERE attempt_number = ?",
            (attempt_number,),
        ).fetchone()
        if row is None or row["attempt_status"] != "terminal" or row["review_json"] is not None:
            raise CanaryError("canary review cannot be frozen")
        frozen = {**review, "frozen_at": current_time.isoformat()}
        with connection:
            connection.execute(
                "UPDATE canary_attempts SET review_json = ? WHERE attempt_number = ?",
                (canonical_json(frozen).decode("utf-8"), attempt_number),
            )
        if review["accepted_source_contract_violation"]:
            return _stop(
                connection,
                registration,
                ledger_path,
                "accepted_source_contract_violation",
                current_time,
                private_export_path=private_export_path,
            )
        if review["severity"] == "severe":
            return _stop(
                connection,
                registration,
                ledger_path,
                "severe_harmful_change",
                current_time,
                private_export_path=private_export_path,
            )
        summary = _summary(connection)
        rows = connection.execute(
            "SELECT review_json FROM canary_attempts WHERE review_json IS NOT NULL "
            "ORDER BY attempt_number"
        ).fetchall()
        reviews = [json.loads(row["review_json"]) for row in rows]
        unacceptable = sum(item["acceptability"] == "unacceptable" for item in reviews)
        non_severe = sum(item["severity"] == "non_severe" for item in reviews)
        impossible_reason = None
        if unacceptable > 1:
            impossible_reason = "acceptable_result_limit_exceeded"
        elif non_severe > 1:
            impossible_reason = "non_severe_harm_limit_exceeded"
        if impossible_reason is not None:
            with connection:
                connection.execute(
                    "UPDATE canary_run SET status = 'fail', reason = ?", (impossible_reason,)
                )
            report = _terminal_report(
                connection, registration, "fail", impossible_reason, current_time
            )
            connection.close()
            return {
                **summary,
                **_terminal_result(
                    registration,
                    ledger_path,
                    "fail",
                    impossible_reason,
                    current_time,
                    terminal_report=report,
                    private_export_path=private_export_path,
                ),
            }
        if summary["completed_attempt_count"] == MAXIMUM_ATTEMPTS:
            acceptable = sum(item["acceptability"] == "acceptable" for item in reviews)
            disposition = (
                "success"
                if summary["unsuccessful_attempt_count"] <= 1
                and acceptable >= 9
                and non_severe <= 1
                else "fail"
            )
            with connection:
                connection.execute(
                    "UPDATE canary_run SET status = ?, reason = 'canary_complete'",
                    (disposition,),
                )
            report = _terminal_report(
                connection, registration, disposition, "canary_complete", current_time
            )
            connection.close()
            return {
                **summary,
                **_terminal_result(
                    registration,
                    ledger_path,
                    disposition,
                    "canary_complete",
                    current_time,
                    terminal_report=report,
                    private_export_path=private_export_path,
                ),
            }
        return summary
    finally:
        try:
            connection.close()
        except sqlite3.ProgrammingError:
            pass


def terminate_cleanup_canary(
    registration: object,
    ledger_path: Path,
    disposition: str,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    private_export_path: Path | None = None,
) -> dict[str, object]:
    """Withdraw or cancel a canary and delete its managed storage."""
    _manifest(registration, ledger_path)
    if disposition not in {"withdrawn", "cancelled"}:
        raise CanaryError("terminal disposition is invalid")
    if not ledger_path.is_file():
        raise CanaryError("canary ledger does not exist")
    connection = _connect(ledger_path)
    try:
        _ensure_run(connection, registration, registration["manifest"])
        terminal_at = now().astimezone(UTC)
        if terminal_at >= _utc(
            registration["manifest"]["confirmation"]["ends_at"],
            "canary window is invalid",
        ):
            return _expire(
                connection,
                registration,
                ledger_path,
                terminal_at,
                private_export_path=private_export_path,
            )
        terminal_disposition = "withdrawn" if disposition == "withdrawn" else "stopped"
        reason = disposition
        with connection:
            connection.execute(
                "UPDATE canary_run SET status = ?, reason = ?",
                (terminal_disposition, reason),
            )
        summary = _summary(connection)
        report = _terminal_report(
            connection, registration, terminal_disposition, reason, terminal_at
        )
        connection.close()
        return {
            **summary,
            **_terminal_result(
                registration,
                ledger_path,
                terminal_disposition,
                reason,
                terminal_at,
                terminal_report=report,
                private_export_path=private_export_path,
            ),
        }
    finally:
        try:
            connection.close()
        except sqlite3.ProgrammingError:
            pass
