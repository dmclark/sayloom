"""Durable, isolated execution of the registered paired cleanup benchmark."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from local_text.cleanup import (
    GeminiAdapter,
    OpenAIAdapter,
    ProviderFailure,
    ProviderFailureClass,
    ProviderOutput,
    ProviderRejectedOutputError,
    _validate_output,
)
from local_text.cleanup_contract import BENCHMARK_DEADLINE_SECONDS, canonical_json

ARMS = ("baseline_paid_gemini", "candidate_paid_openai")
PROTOCOL_ID = "cleanup-evaluation-benchmark-v2"
EVIDENCE_MAX_AGE = timedelta(hours=24)


class ExecutionError(ValueError):
    """A privacy-safe benchmark execution failure."""


@dataclass(frozen=True)
class ExecutionProviderResult:
    """Provider output plus execution-only evidence that adapters must expose."""

    output: ProviderOutput
    reported_model_version: str | None
    request_storage_control: str
    disclosure_detected: bool
    validator_bypassed: bool = False


class ExecutionProvider(Protocol):
    provider_id: str
    model: str

    async def clean(self, original_text: str, system_prompt: str) -> ExecutionProviderResult: ...


@dataclass(frozen=True)
class RunInvariants:
    """Current facts rechecked before every private provider request."""

    withdrawn: bool = False
    cancelled: bool = False
    consent_valid: bool = True
    hold_valid: bool = True
    selected_cases_unchanged: bool = True
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
            (not self.hold_valid, "hold_invalid"),
            (not self.selected_cases_unchanged, "selected_case_changed"),
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


def _utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ExecutionError("execution gate is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ExecutionError("execution gate is invalid") from None
    if parsed.tzinfo is None:
        raise ExecutionError("execution gate is invalid")
    return parsed.astimezone(UTC)


def _cost(tokens: int, rate: int) -> int:
    return (tokens * rate + 999_999) // 1_000_000


def _valid_count(value: object, maximum: object) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and isinstance(maximum, int)
        and not isinstance(maximum, bool)
        and 0 <= value <= maximum
    )


def _connect(path: Path) -> sqlite3.Connection:
    if (
        not path.parent.is_dir()
        or path.parent.stat().st_uid != os.getuid()
        or stat.S_IMODE(path.parent.stat().st_mode) & 0o077
        or path.is_symlink()
        or (path.exists() and not path.is_file())
        or (path.exists() and path.stat().st_uid != os.getuid())
        or (path.exists() and stat.S_IMODE(path.stat().st_mode) & 0o077)
    ):
        raise ExecutionError("execution storage is not private")
    connection = sqlite3.connect(path)
    os.chmod(path, 0o600)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS benchmark_run (
            run_id TEXT PRIMARY KEY,
            manifest_sha256 TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT NOT NULL,
            completed_request_count INTEGER NOT NULL,
            actual_cost_usd_micros INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS benchmark_requests (
            ordinal INTEGER PRIMARY KEY,
            run_id TEXT NOT NULL,
            case_id TEXT NOT NULL,
            arm_id TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('reserved', 'sent', 'terminal')),
            outcome TEXT,
            user_visible_text TEXT,
            validator_disposition TEXT,
            provider TEXT,
            model TEXT,
            reported_model_version TEXT,
            elapsed_ms INTEGER,
            input_tokens INTEGER,
            output_tokens INTEGER,
            actual_usd_micros INTEGER,
            failure_class TEXT,
            provider_code TEXT,
            http_status INTEGER,
            UNIQUE (run_id, case_id, arm_id),
            FOREIGN KEY (run_id) REFERENCES benchmark_run(run_id)
        );
        CREATE TABLE IF NOT EXISTS benchmark_events (
            event_index INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            event TEXT NOT NULL,
            case_id TEXT,
            arm_id TEXT,
            at TEXT NOT NULL
        );
        """
    )
    return connection


def _event(
    connection: sqlite3.Connection,
    run_id: str,
    event: str,
    at: datetime,
    case_id: str | None = None,
    arm_id: str | None = None,
) -> None:
    connection.execute(
        "INSERT INTO benchmark_events(run_id, event, case_id, arm_id, at) VALUES (?, ?, ?, ?, ?)",
        (run_id, event, case_id, arm_id, at.isoformat()),
    )


def _stop(connection: sqlite3.Connection, run_id: str, reason: str, at: datetime) -> None:
    with connection:
        connection.execute(
            "UPDATE benchmark_run SET status = 'stopped', reason = ? WHERE run_id = ?",
            (reason, run_id),
        )
        _event(connection, run_id, "stopped", at)


def _summary(connection: sqlite3.Connection, run_id: str) -> dict[str, object]:
    row = connection.execute(
        "SELECT * FROM benchmark_run WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        raise ExecutionError("execution ledger is invalid")
    return {
        "run_id": row["run_id"],
        "status": row["status"],
        "reason": row["reason"],
        "completed_request_count": row["completed_request_count"],
        "actual_cost_usd_micros": row["actual_cost_usd_micros"],
    }


def read_execution_results(ledger_path: Path, run_id: str) -> list[dict[str, object]]:
    """Read terminal requests in frozen order for later private scoring."""
    if not ledger_path.is_file():
        raise ExecutionError("execution ledger does not exist")
    connection = _connect(ledger_path)
    try:
        rows = connection.execute(
            "SELECT case_id, arm_id, outcome, user_visible_text, validator_disposition, "
            "provider, model, reported_model_version, elapsed_ms, input_tokens, output_tokens, "
            "actual_usd_micros, failure_class, provider_code, http_status "
            "FROM benchmark_requests WHERE run_id = ? AND state = 'terminal' ORDER BY ordinal",
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _validate_gate(
    registration: object,
    snapshot: object,
    smoke: object,
    providers: Mapping[str, ExecutionProvider],
    current_time: datetime,
) -> tuple[dict[str, object], dict[str, dict[str, object]], str]:
    if not isinstance(registration, dict) or not isinstance(registration.get("manifest"), dict):
        raise ExecutionError("registration is invalid")
    manifest = registration["manifest"]
    if registration.get("manifest_sha256") != _digest(manifest):
        raise ExecutionError("registered manifest changed")
    if not isinstance(snapshot, dict) or manifest.get("corpus", {}).get(
        "snapshot_sha256"
    ) != _digest(snapshot):
        raise ExecutionError("registered snapshot changed")
    if not isinstance(smoke, dict) or smoke.get("status") != "passed":
        raise ExecutionError("passing synthetic smoke is required")
    frozen_smoke = manifest.get("synthetic_smoke", {})
    for key in ("all_passed", "fixture_count", "call_count", "results_sha256"):
        if smoke.get(key) != frozen_smoke.get(key):
            raise ExecutionError("synthetic smoke does not match registration")
    if set(providers) != set(ARMS):
        raise ExecutionError("provider set does not match registration")
    evidence = manifest.get("provider_evidence", {})
    evidence_at = _utc(evidence.get("retrieved_at"))
    if (
        evidence.get("material_change") is not False
        or evidence_at > current_time
        or current_time - evidence_at > EVIDENCE_MAX_AGE
    ):
        raise ExecutionError("provider evidence is not current")
    confirmation = manifest.get("run_confirmation", {})
    selected = manifest.get("corpus", {}).get("selected_cases")
    expected_confirmation = [
        {"case_id": item["case_id"], "revision": item["revision"]} for item in selected
    ] if isinstance(selected, list) else None
    confirmed_at = _utc(confirmation.get("confirmed_at"))
    release_at = _utc(confirmation.get("hold_release_at"))
    storage = manifest.get("storage", {})
    budget = manifest.get("budget", {})
    prompt_sha256 = (
        manifest.get("request_contract", {})
        .get("artifacts", {})
        .get("effective_prompt", {})
        .get("sha256")
    )
    conservative_estimate = 60 * sum(
        budget.get("request_bound_usd_micros", {}).get(arm, -1) for arm in ARMS
    )
    if (
        confirmation.get("confirmed") is not True
        or confirmation.get("maximum_private_calls") != 120
        or confirmation.get("selected_cases") != expected_confirmation
        or confirmation.get("providers_models") != evidence.get("models")
        or confirmation.get("effective_prompt_sha256") != prompt_sha256
        or confirmation.get("conservative_estimate_usd_micros") != conservative_estimate
        or confirmation.get("total_cap_usd_micros") != 10_000_000
        or confirmation.get("benchmark_id") != PROTOCOL_ID
        or confirmation.get("storage_locations") != storage.get("locations")
        or not confirmation.get("disclosures")
        or release_at <= current_time
        or release_at > confirmed_at + timedelta(days=30)
        or storage.get("locations_confirmed") is not True
        or not storage.get("inventory")
        or not storage.get("locations")
        or manifest.get("lifecycle", {}).get("write_back_to_live_corpus") is not False
        or manifest.get("environment", {}).get("stable_resources_inaccessible") is not True
        or manifest.get("code", {}).get("clean_tree") is not True
    ):
        raise ExecutionError("run confirmation or isolation gate is invalid")
    cases = snapshot.get("cases")
    if not isinstance(cases, list) or len(selected or ()) != 60:
        raise ExecutionError("selected case set is invalid")
    case_by_id = {item.get("case_id"): item for item in cases if isinstance(item, dict)}
    for item in selected:
        case = case_by_id.get(item["case_id"])
        if (
            not case
            or case.get("revision") != item["revision"]
            or case.get("current_revision") != item["revision"]
            or case.get("record_sha256") != item["record_sha256"]
            or case.get("consent", {}).get("valid") is not True
            or case.get("hold", {}).get("benchmark_id") != PROTOCOL_ID
            or _utc(case.get("hold", {}).get("release_at")) != release_at
        ):
            raise ExecutionError("selected case consent, hold, or revision is invalid")
    ordering = manifest.get("ordering", {})
    case_order = ordering.get("case_order")
    arm_order = ordering.get("arm_order")
    if (
        not isinstance(case_order, list)
        or set(case_order) != set(case_by_id) & {item["case_id"] for item in selected}
        or len(case_order) != 60
        or not isinstance(arm_order, dict)
        or any(sorted(arm_order.get(case_id, ())) != sorted(ARMS) for case_id in case_order)
    ):
        raise ExecutionError("frozen execution order is invalid")
    try:
        prompt = base64.b64decode(
            manifest["request_contract"]["artifacts"]["effective_prompt"][
                "canonical_bytes_base64"
            ],
            validate=True,
        ).decode("utf-8")
    except (KeyError, TypeError, ValueError, UnicodeDecodeError):
        raise ExecutionError("request contract is invalid") from None
    return manifest, case_by_id, prompt


def _failure_outcome(error: Exception) -> tuple[str, str, bool]:
    if isinstance(error, ProviderRejectedOutputError):
        if error.failure_class == ProviderFailureClass.SAFETY_POLICY:
            return "refusal", "safety_refusal", False
        return "rejected_output", "rejected", False
    if isinstance(error, ProviderFailure):
        if error.failure_class in {
            ProviderFailureClass.PERMANENT_CONFIGURATION,
            ProviderFailureClass.PERMANENT_QUOTA,
        }:
            return "failure", str(error.failure_class), True
        if error.failure_class in {
            ProviderFailureClass.TRANSIENT_ROUTE,
            ProviderFailureClass.TEMPORARY_QUOTA,
            ProviderFailureClass.UNKNOWN,
        }:
            return "failure", str(error.failure_class), False
        return "malformed_output", str(error.failure_class), False
    return "failure", "unknown_system_failure", False


def _runtime_gate_reason(manifest: dict[str, object], current_time: datetime) -> str | None:
    confirmation = manifest["run_confirmation"]
    if _utc(confirmation["hold_release_at"]) <= current_time:
        return "hold_invalid"
    evidence_at = _utc(manifest["provider_evidence"]["retrieved_at"])
    if evidence_at > current_time or current_time - evidence_at > EVIDENCE_MAX_AGE:
        return "provider_evidence_expired"
    return None


async def run_cleanup_benchmark(
    registration: object,
    snapshot: object,
    smoke: object,
    providers: Mapping[str, ExecutionProvider],
    ledger_path: Path,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    invariants: Callable[[], RunInvariants] = RunInvariants,
    after_reservation: Callable[[str, str], None] | None = None,
    after_send: Callable[[str, str], None] | None = None,
    after_terminal: Callable[[str, str], None] | None = None,
) -> dict[str, object]:
    """Execute or safely resume one immutable 60-case paired benchmark."""
    current_time = now().astimezone(UTC)
    manifest, case_by_id, prompt = _validate_gate(
        registration, snapshot, smoke, providers, current_time
    )
    run_id = str(manifest["run_id"])
    connection = _connect(ledger_path)
    try:
        existing = connection.execute("SELECT * FROM benchmark_run").fetchall()
        if existing and (
            len(existing) != 1
            or existing[0]["run_id"] != run_id
            or existing[0]["manifest_sha256"] != registration["manifest_sha256"]
        ):
            raise ExecutionError("execution ledger does not match registration")
        if not existing:
            with connection:
                connection.execute(
                    "INSERT INTO benchmark_run VALUES (?, ?, 'running', 'pending', 0, 0)",
                    (run_id, registration["manifest_sha256"]),
                )
                _event(connection, run_id, "started", current_time)
        elif existing[0]["status"] != "running":
            return _summary(connection, run_id)
        ambiguous = connection.execute(
            "SELECT 1 FROM benchmark_requests WHERE state = 'sent' LIMIT 1"
        ).fetchone()
        if ambiguous:
            _stop(connection, run_id, "ambiguous_in_flight_request", current_time)
            return _summary(connection, run_id)

        failure_streak = {arm: 0 for arm in ARMS}
        terminal_rows = connection.execute(
            "SELECT arm_id, outcome, failure_class FROM benchmark_requests "
            "WHERE state = 'terminal' ORDER BY ordinal"
        ).fetchall()
        for row in terminal_rows:
            operational = row["outcome"] in {"timeout", "failure"} and row[
                "failure_class"
            ] in {
                "transient_route",
                "temporary_quota",
                "unknown",
                "unknown_system_failure",
            }
            failure_streak[row["arm_id"]] = failure_streak[row["arm_id"]] + 1 if operational else 0

        ordering = manifest["ordering"]
        planned = [
            (case_id, arm_id)
            for case_id in ordering["case_order"]
            for arm_id in ordering["arm_order"][case_id]
        ]
        budget = manifest["budget"]
        evidence = manifest["provider_evidence"]
        for ordinal, (case_id, arm_id) in enumerate(planned):
            row = connection.execute(
                "SELECT * FROM benchmark_requests WHERE ordinal = ?", (ordinal,)
            ).fetchone()
            if row is not None and row["state"] == "terminal":
                continue
            call_time = now().astimezone(UTC)
            reason = invariants().stop_reason() or _runtime_gate_reason(manifest, call_time)
            if reason:
                _stop(connection, run_id, reason, now().astimezone(UTC))
                return _summary(connection, run_id)
            run = connection.execute(
                "SELECT * FROM benchmark_run WHERE run_id = ?", (run_id,)
            ).fetchone()
            bound = budget["request_bound_usd_micros"][arm_id]
            ceiling = budget["total_usd_micros"]
            smoke_cost = smoke.get("smoke_cost_usd_micros", 0)
            if (
                not isinstance(bound, int)
                or isinstance(bound, bool)
                or bound < 0
                or run["completed_request_count"] >= 120
                or run["actual_cost_usd_micros"] + smoke_cost + bound > ceiling
            ):
                _stop(connection, run_id, "next_request_cannot_be_reserved", now().astimezone(UTC))
                return _summary(connection, run_id)
            if row is None:
                with connection:
                    connection.execute(
                        "INSERT INTO benchmark_requests(ordinal, run_id, case_id, arm_id, state) "
                        "VALUES (?, ?, ?, ?, 'reserved')",
                        (ordinal, run_id, case_id, arm_id),
                    )
                    _event(connection, run_id, "reserved", now().astimezone(UTC), case_id, arm_id)
                if after_reservation:
                    after_reservation(case_id, arm_id)
            with connection:
                connection.execute(
                    "UPDATE benchmark_requests SET state = 'sent' WHERE ordinal = ?", (ordinal,)
                )
                _event(connection, run_id, "sent", now().astimezone(UTC), case_id, arm_id)
            source = str(case_by_id[case_id]["source_text"])
            provider = providers[arm_id]
            result: ExecutionProviderResult | None = None
            error: Exception | None = None
            try:
                result = await asyncio.wait_for(
                    provider.clean(source, prompt), timeout=BENCHMARK_DEADLINE_SECONDS
                )
                if after_send:
                    after_send(case_id, arm_id)
            except TimeoutError as caught:
                error = caught
            except Exception as caught:
                error = caught

            terminal: dict[str, object] = {
                "outcome": "success",
                "user_visible_text": source,
                "validator_disposition": "accepted",
                "provider": provider.provider_id,
                "model": provider.model,
                "reported_model_version": None,
                "elapsed_ms": BENCHMARK_DEADLINE_SECONDS * 1_000 if error else 0,
                "input_tokens": None,
                "output_tokens": None,
                "actual_usd_micros": 0,
                "failure_class": None,
                "provider_code": None,
                "http_status": None,
            }
            hard_stop: str | None = None
            operational = False
            if isinstance(error, TimeoutError):
                terminal.update(outcome="timeout", validator_disposition="fail_open_timeout")
                terminal["failure_class"] = "transient_route"
                terminal["provider_code"] = "timeout"
                operational = True
            elif error is not None:
                outcome, failure_class, permanent = _failure_outcome(error)
                terminal.update(
                    outcome=outcome,
                    validator_disposition=f"fail_open_{outcome}",
                    failure_class=failure_class,
                )
                if isinstance(error, ProviderFailure):
                    terminal.update(
                        elapsed_ms=max(0, error.elapsed_ms),
                        input_tokens=error.input_tokens,
                        output_tokens=error.output_tokens,
                        provider_code=error.provider_code,
                        http_status=error.http_status,
                    )
                operational = outcome == "failure" and not permanent
                if permanent:
                    hard_stop = "permanent_provider_failure"
            elif not isinstance(result, ExecutionProviderResult):
                terminal.update(
                    outcome="malformed_output",
                    validator_disposition="fail_open_malformed_output",
                    failure_class="invalid_output",
                )
            else:
                output = result.output
                model_evidence = evidence["models"][arm_id]
                expected_storage = (
                    "store_false" if model_evidence["provider"] == "openai" else "provider_terms"
                )
                terminal.update(
                    provider=output.provider_id,
                    model=output.model_id,
                    reported_model_version=result.reported_model_version,
                    elapsed_ms=output.elapsed_ms,
                    input_tokens=output.input_tokens,
                    output_tokens=output.output_tokens,
                )
                if (
                    output.provider_id != model_evidence["provider"]
                    or output.model_id != model_evidence["model"]
                    or (
                        model_evidence.get("reported_version") is not None
                        and result.reported_model_version != model_evidence["reported_version"]
                    )
                ):
                    hard_stop = "provider_reported_model_mismatch"
                    terminal.update(
                        outcome="failure", validator_disposition="fail_open_attribution"
                    )
                elif result.request_storage_control != expected_storage:
                    hard_stop = "storage_violation"
                    terminal.update(outcome="failure", validator_disposition="fail_open_storage")
                elif result.disclosure_detected:
                    hard_stop = "disclosure_violation"
                    terminal.update(outcome="failure", validator_disposition="fail_open_disclosure")
                elif result.validator_bypassed:
                    hard_stop = "impermissible_output_bypassed_validator"
                    terminal.update(outcome="failure", validator_disposition="validator_bypassed")
                else:
                    try:
                        _validate_output(source, output.text)
                    except ProviderRejectedOutputError as rejected:
                        terminal.update(
                            outcome=(
                                "refusal"
                                if rejected.failure_class == ProviderFailureClass.SAFETY_POLICY
                                else "rejected_output"
                            ),
                            validator_disposition="rejected",
                        )
                    else:
                        terminal["user_visible_text"] = output.text

                if output.elapsed_ms > BENCHMARK_DEADLINE_SECONDS * 1_000:
                    terminal.update(
                        outcome="deadline_breach",
                        user_visible_text=source,
                        validator_disposition="fail_open_deadline_breach",
                        failure_class="transient_route",
                    )
                    operational = True

                maximum_input = budget["input_token_maximum"][arm_id]
                maximum_output = budget["output_token_maximum"][arm_id]
                if not _valid_count(output.input_tokens, maximum_input) or not _valid_count(
                    output.output_tokens, maximum_output
                ):
                    hard_stop = "missing_or_malformed_usage"
                else:
                    pricing = evidence["pricing"][arm_id]
                    actual = _cost(
                        output.input_tokens,
                        pricing["input_usd_micros_per_million_tokens"],
                    ) + _cost(
                        output.output_tokens,
                        pricing["output_usd_micros_per_million_tokens"],
                    )
                    terminal["actual_usd_micros"] = actual
                    if (
                        actual > bound
                        or run["actual_cost_usd_micros"] + smoke_cost + actual > ceiling
                    ):
                        hard_stop = "actual_budget_breach"

            with connection:
                connection.execute(
                    """UPDATE benchmark_requests SET
                    state = 'terminal', outcome = :outcome, user_visible_text = :user_visible_text,
                    validator_disposition = :validator_disposition, provider = :provider,
                    model = :model, reported_model_version = :reported_model_version,
                    elapsed_ms = :elapsed_ms, input_tokens = :input_tokens,
                    output_tokens = :output_tokens, actual_usd_micros = :actual_usd_micros,
                    failure_class = :failure_class, provider_code = :provider_code,
                    http_status = :http_status WHERE ordinal = :ordinal""",
                    {**terminal, "ordinal": ordinal},
                )
                connection.execute(
                    "UPDATE benchmark_run SET "
                    "completed_request_count = completed_request_count + 1, "
                    "actual_cost_usd_micros = actual_cost_usd_micros + ? WHERE run_id = ?",
                    (terminal["actual_usd_micros"], run_id),
                )
                _event(connection, run_id, "terminal", now().astimezone(UTC), case_id, arm_id)
            if after_terminal:
                after_terminal(case_id, arm_id)
            failure_streak[arm_id] = failure_streak[arm_id] + 1 if operational else 0
            if hard_stop:
                _stop(connection, run_id, hard_stop, now().astimezone(UTC))
                return _summary(connection, run_id)
            if failure_streak[arm_id] >= 3:
                _stop(
                    connection,
                    run_id,
                    "three_consecutive_operational_failures",
                    now().astimezone(UTC),
                )
                return _summary(connection, run_id)

        with connection:
            connection.execute(
                "UPDATE benchmark_run SET status = 'completed', reason = 'all_pairs_completed' "
                "WHERE run_id = ?",
                (run_id,),
            )
            _event(connection, run_id, "completed", now().astimezone(UTC))
        return _summary(connection, run_id)
    finally:
        connection.close()


@dataclass(frozen=True)
class _LiveExecutionProvider:
    adapter: GeminiAdapter | OpenAIAdapter

    @property
    def provider_id(self) -> str:
        return self.adapter.provider_id

    @property
    def model(self) -> str:
        return self.adapter.model

    async def clean(self, original_text: str, system_prompt: str) -> ExecutionProviderResult:
        output = await self.adapter.clean(original_text, system_prompt)
        return ExecutionProviderResult(
            output=output,
            reported_model_version=None,
            request_storage_control=(
                "store_false" if isinstance(self.adapter, OpenAIAdapter) else "provider_terms"
            ),
            disclosure_detected=False,
        )


def _verify_local_execution(manifest: dict[str, object], ledger_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        output_directory = ledger_path.parent.resolve(strict=True)
    except (OSError, subprocess.SubprocessError):
        raise ExecutionError("local execution preflight failed") from None
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
    code = manifest.get("code", {})
    if (
        commit != code.get("runner_commit")
        or dirty
        or repository.resolve() == output_directory
        or repository.resolve() in output_directory.parents
        or stable_configuration_present
        or not all(
            os.environ.get(name)
            for name in (
                "LOCAL_TEXT_BENCHMARK_GEMINI_API_KEY",
                "LOCAL_TEXT_BENCHMARK_OPENAI_API_KEY",
            )
        )
    ):
        raise ExecutionError("local execution preflight failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the isolated paired cleanup benchmark")
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--smoke", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--authorize-private-benchmark", action="store_true")
    args = parser.parse_args()
    if not args.authorize_private_benchmark:
        print(
            "error: separate explicit private-benchmark authorization is required",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        registration = json.loads(args.registration.read_bytes())
        snapshot = json.loads(args.snapshot.read_bytes())
        smoke = json.loads(args.smoke.read_bytes())
        manifest = registration["manifest"]
        _verify_local_execution(manifest, args.ledger)

        async def execute() -> dict[str, object]:
            import httpx

            async with httpx.AsyncClient(timeout=BENCHMARK_DEADLINE_SECONDS) as client:
                providers: dict[str, ExecutionProvider] = {
                    "baseline_paid_gemini": _LiveExecutionProvider(
                        GeminiAdapter(
                            os.environ.get("LOCAL_TEXT_BENCHMARK_GEMINI_API_KEY", ""),
                            "gemini-3.7-flash",
                            client,
                        )
                    ),
                    "candidate_paid_openai": _LiveExecutionProvider(
                        OpenAIAdapter(
                            os.environ.get("LOCAL_TEXT_BENCHMARK_OPENAI_API_KEY", ""), client
                        )
                    ),
                }
                return await run_cleanup_benchmark(
                    registration, snapshot, smoke, providers, args.ledger
                )

        result = asyncio.run(execute())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ExecutionError, KeyError):
        print("error: cleanup benchmark execution failed", file=sys.stderr)
        raise SystemExit(1) from None
    print(canonical_json(result).decode())


if __name__ == "__main__":
    main()
