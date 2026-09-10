"""Deterministic scoring and terminal disposition for the cleanup benchmark."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import shutil
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from local_text.cleanup_contract import BENCHMARK_DEADLINE_SECONDS, canonical_json
from local_text.cleanup_evaluation_execution import ARMS, _connect
from local_text.cleanup_evaluation_runner import CorpusSnapshot

BASELINE_ARM = "baseline_paid_gemini"
CANDIDATE_ARM = "candidate_paid_openai"
CASE_COUNT = 60
BOOTSTRAP_RESAMPLES = 10_000


class ScoringError(ValueError):
    """A privacy-safe scoring or disposition failure."""


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def normalize_scoring_text(value: str) -> str:
    """Apply only the protocol's NFC and LF scoring normalization."""
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def unicode_levenshtein(left: str, right: str) -> int:
    """Return Levenshtein distance over Python Unicode code points."""
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, 1):
        current = [left_index]
        for right_index, right_character in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def normalized_effort(result: str, expected: str) -> float:
    normalized_result = normalize_scoring_text(result)
    normalized_expected = normalize_scoring_text(expected)
    return unicode_levenshtein(normalized_result, normalized_expected) / max(
        len(normalized_expected), 1
    )


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _nearest_rank(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ScoringError("benchmark accounting is incomplete")
    return sorted(values)[math.ceil(percentile * len(values)) - 1]


def paired_bootstrap_upper_bound(
    baseline: Sequence[float], candidate: Sequence[float], seed: int
) -> float:
    """Compute the frozen one-sided p95 paired-bootstrap statistic."""
    if len(baseline) != CASE_COUNT or len(candidate) != CASE_COUNT:
        raise ScoringError("paired bootstrap requires the frozen 60 cases")
    statistics: list[float] = []
    for resample in range(BOOTSTRAP_RESAMPLES):
        indices = [
            int.from_bytes(
                hashlib.sha256(
                    canonical_json(
                        ["local_text:cleanup-evaluation:paired-bootstrap:v1", seed, resample, draw]
                    )
                ).digest()[:8],
                "big",
            )
            % CASE_COUNT
            for draw in range(CASE_COUNT)
        ]
        baseline_mean = sum(baseline[index] for index in indices) / CASE_COUNT
        candidate_mean = sum(candidate[index] for index in indices) / CASE_COUNT
        if baseline_mean == 0:
            statistic = 0.0 if candidate_mean == 0 else math.inf
        else:
            statistic = (candidate_mean - baseline_mean) / baseline_mean
        statistics.append(statistic)
    return _nearest_rank(statistics, 0.95)


def _validated_inputs(
    registration: object, snapshot: object
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], int]:
    if not isinstance(registration, dict) or not isinstance(registration.get("manifest"), dict):
        raise ScoringError("scoring inputs are invalid")
    manifest = registration["manifest"]
    if registration.get("manifest_sha256") != _digest(manifest):
        raise ScoringError("registered manifest changed")
    try:
        validated_snapshot = CorpusSnapshot.model_validate(snapshot).model_dump(mode="json")
    except ValidationError:
        raise ScoringError("scoring inputs are invalid") from None
    if manifest.get("corpus", {}).get("snapshot_sha256") != _digest(validated_snapshot):
        raise ScoringError("registered snapshot changed")
    selected = manifest.get("corpus", {}).get("selected_cases")
    if not isinstance(selected, list) or len(selected) != CASE_COUNT:
        raise ScoringError("frozen case set is invalid")
    case_by_id = {case["case_id"]: case for case in validated_snapshot["cases"]}
    selected_ids: list[str] = []
    for item in selected:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
            raise ScoringError("frozen case set is invalid")
        case = case_by_id.get(item["case_id"])
        if (
            case is None
            or case.get("revision") != item.get("revision")
            or case.get("record_sha256") != item.get("record_sha256")
        ):
            raise ScoringError("frozen case set changed")
        selected_ids.append(item["case_id"])
    if len(set(selected_ids)) != CASE_COUNT:
        raise ScoringError("frozen case set is invalid")
    seed = manifest.get("scoring", {}).get("bootstrap_seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ScoringError("frozen bootstrap seed is invalid")
    return manifest, {case_id: case_by_id[case_id] for case_id in selected_ids}, seed


def _ledger_rows(
    ledger_path: Path, run_id: str, manifest_sha256: str
) -> tuple[Any, Any, list[Any], list[Any], list[Any], list[Any]]:
    if not ledger_path.is_file():
        raise ScoringError("benchmark ledger is unavailable")
    try:
        connection = _connect(ledger_path)
        run = connection.execute(
            "SELECT * FROM benchmark_run WHERE run_id = ?", (run_id,)
        ).fetchone()
        requests = connection.execute(
            "SELECT * FROM benchmark_requests WHERE run_id = ? ORDER BY ordinal", (run_id,)
        ).fetchall()
        events = connection.execute(
            "SELECT event, at FROM benchmark_events WHERE run_id = ? ORDER BY event_index",
            (run_id,),
        ).fetchall()
        state = connection.execute(
            "SELECT * FROM review_state WHERE run_id = ?", (run_id,)
        ).fetchone()
        individual = connection.execute(
            "SELECT reviews.*, requests.arm_id FROM individual_reviews reviews "
            "JOIN benchmark_requests requests ON requests.ordinal = reviews.request_ordinal "
            "WHERE reviews.run_id = ? ORDER BY reviews.position",
            (run_id,),
        ).fetchall()
        pairs = connection.execute(
            "SELECT pairs.*, a.arm_id AS a_arm_id, b.arm_id AS b_arm_id "
            "FROM pair_reviews pairs "
            "JOIN benchmark_requests a ON a.ordinal = pairs.a_request_ordinal "
            "JOIN benchmark_requests b ON b.ordinal = pairs.b_request_ordinal "
            "WHERE pairs.run_id = ? ORDER BY pairs.position",
            (run_id,),
        ).fetchall()
    except (OSError, sqlite3.Error, ValueError):
        raise ScoringError("benchmark ledger is unavailable") from None
    finally:
        if "connection" in locals():
            connection.close()
    if (
        run is None
        or run["status"] != "completed"
        or run["reason"] != "all_pairs_completed"
        or run["completed_request_count"] != len(ARMS) * CASE_COUNT
        or run["manifest_sha256"] != manifest_sha256
        or state is None
        or state["phase"] != "unblinded"
        or len(requests) != len(ARMS) * CASE_COUNT
        or len(individual) != len(ARMS) * CASE_COUNT
        or len(pairs) != CASE_COUNT
        or any(row["revision"] <= 0 for row in [*individual, *pairs])
    ):
        raise ScoringError("completed frozen unblinded benchmark is required")
    frozen_review = {
        "individual_reviews": [
            {
                name: row[name]
                for name in (
                    "review_id",
                    "position",
                    "revision",
                    "acceptability",
                    "accepted_source_contract_violation",
                    "harmful_change_category",
                    "severity",
                    "local_rationale",
                )
            }
            for row in individual
        ],
        "pair_reviews": [
            {name: row[name] for name in ("review_id", "position", "revision", "choice")}
            for row in pairs
        ],
    }
    if _digest(frozen_review) != state["review_sha256"]:
        raise ScoringError("frozen review integrity check failed")
    return run, state, requests, events, individual, pairs


def _gate(
    gate_id: str,
    numerator: float | int,
    denominator: float | int,
    value: float | str | None,
    threshold: float | int,
    passes: bool,
    comparison: str,
) -> dict[str, object]:
    return {
        "gate": gate_id,
        "numerator": numerator,
        "denominator": denominator,
        "value": value,
        "threshold": threshold,
        "comparison": comparison,
        "disposition": "pass" if passes else "fail",
    }


def _finite_json(value: float) -> float | str:
    return "positive_infinity" if math.isinf(value) and value > 0 else value


def score_cleanup_benchmark(
    registration: object,
    snapshot: object,
    ledger_path: Path,
    *,
    deviations: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Score exactly one complete frozen benchmark and return a canonical report value."""
    manifest, cases, bootstrap_seed = _validated_inputs(registration, snapshot)
    run_id = str(manifest["run_id"])
    manifest_sha256 = str(registration["manifest_sha256"])
    run, review_state, requests, events, individual, pairs = _ledger_rows(
        ledger_path, run_id, manifest_sha256
    )
    if any(not isinstance(item, Mapping) for item in deviations):
        raise ScoringError("protocol deviations are invalid")
    request_by_pair: dict[tuple[str, str], Any] = {}
    for row in requests:
        key = (row["case_id"], row["arm_id"])
        if (
            row["state"] != "terminal"
            or row["case_id"] not in cases
            or row["arm_id"] not in ARMS
            or key in request_by_pair
        ):
            raise ScoringError("benchmark accounting is incomplete")
        request_by_pair[key] = row
    expected_pairs = {(case_id, arm) for case_id in cases for arm in ARMS}
    if set(request_by_pair) != expected_pairs:
        raise ScoringError("benchmark accounting is incomplete")
    frozen_results = [
        {
            name: row[name]
            for name in (
                "ordinal",
                "case_id",
                "arm_id",
                "outcome",
                "user_visible_text",
                "validator_disposition",
                "provider",
                "model",
                "reported_model_version",
                "elapsed_ms",
                "input_tokens",
                "output_tokens",
                "actual_usd_micros",
                "failure_class",
                "provider_code",
                "http_status",
            )
        }
        for row in requests
    ]
    if _digest(frozen_results) != review_state["results_sha256"]:
        raise ScoringError("frozen result integrity check failed")

    effort: dict[str, list[float]] = {arm: [] for arm in ARMS}
    valid: Counter[str] = Counter()
    latency: dict[str, list[float]] = {arm: [] for arm in ARMS}
    outcomes: dict[str, Counter[str]] = {arm: Counter() for arm in ARMS}
    failures: dict[str, Counter[str]] = {arm: Counter() for arm in ARMS}
    usage: dict[str, Counter[str]] = {arm: Counter() for arm in ARMS}
    strata: dict[str, dict[str, list[float]]] = defaultdict(lambda: {arm: [] for arm in ARMS})
    case_order = list(cases)
    for case_id in case_order:
        case = cases[case_id]
        for arm in ARMS:
            row = request_by_pair[(case_id, arm)]
            elapsed_ms = row["elapsed_ms"]
            if not isinstance(elapsed_ms, int) or elapsed_ms < 0:
                raise ScoringError("benchmark accounting is incomplete")
            is_valid = (
                row["outcome"] == "success"
                and row["validator_disposition"] == "accepted"
                and elapsed_ms <= BENCHMARK_DEADLINE_SECONDS * 1_000
            )
            result = row["user_visible_text"] if is_valid else case["source_text"]
            if not isinstance(result, str):
                raise ScoringError("benchmark accounting is incomplete")
            value = normalized_effort(result, case["expected_cleanup"])
            effort[arm].append(value)
            strata[case["annotations"]["primary_stratum"]][arm].append(value)
            valid[arm] += is_valid
            latency[arm].append(
                BENCHMARK_DEADLINE_SECONDS * 1_000
                if row["outcome"] == "timeout"
                else elapsed_ms
            )
            outcomes[arm][row["outcome"]] += 1
            if row["failure_class"]:
                failures[arm][row["failure_class"]] += 1
            usage[arm]["input_tokens"] += row["input_tokens"] or 0
            usage[arm]["output_tokens"] += row["output_tokens"] or 0
            usage[arm]["cost_usd_micros"] += row["actual_usd_micros"] or 0

    reviews_by_arm: dict[str, list[Any]] = {arm: [] for arm in ARMS}
    for row in individual:
        if row["arm_id"] not in ARMS:
            raise ScoringError("review accounting is incomplete")
        reviews_by_arm[row["arm_id"]].append(row)
    violations = {
        arm: sum(row["accepted_source_contract_violation"] == "yes" for row in rows)
        for arm, rows in reviews_by_arm.items()
    }
    severe = {
        arm: sum(row["severity"] == "severe" for row in rows)
        for arm, rows in reviews_by_arm.items()
    }
    harms = {
        arm: dict(Counter(row["harmful_change_category"] for row in rows))
        for arm, rows in reviews_by_arm.items()
    }
    acceptable = {
        arm: sum(row["acceptability"] == "acceptable" for row in rows)
        for arm, rows in reviews_by_arm.items()
    }
    preference: Counter[str] = Counter()
    for row in pairs:
        choice = row["choice"]
        if choice in {"tie", "neither"}:
            preference[choice] += 1
        else:
            chosen_arm = row[f"{choice}_arm_id"]
            preference["candidate" if chosen_arm == CANDIDATE_ARM else "baseline"] += 1

    baseline_mean = _mean(effort[BASELINE_ARM])
    candidate_mean = _mean(effort[CANDIDATE_ARM])
    relative_decrease = (
        (baseline_mean - candidate_mean) / baseline_mean if baseline_mean else -math.inf
    )
    bootstrap = paired_bootstrap_upper_bound(
        effort[BASELINE_ARM], effort[CANDIDATE_ARM], bootstrap_seed
    )
    baseline_rate = valid[BASELINE_ARM] / CASE_COUNT
    candidate_rate = valid[CANDIDATE_ARM] / CASE_COUNT
    valid_drop = baseline_rate - candidate_rate
    baseline_p95 = _nearest_rank(latency[BASELINE_ARM], 0.95)
    candidate_p95 = _nearest_rank(latency[CANDIDATE_ARM], 0.95)
    latency_increase = candidate_p95 - baseline_p95
    latency_allowance = max(0.2 * baseline_p95, 1_000.0)
    gates = [
        _gate(
            "candidate_mean_effort_relative_decrease",
            baseline_mean - candidate_mean,
            baseline_mean,
            None if baseline_mean == 0 else relative_decrease,
            0.1,
            baseline_mean > 0
            and (relative_decrease >= 0.1 or math.isclose(relative_decrease, 0.1)),
            ">=",
        ),
        _gate(
            "paired_bootstrap_relative_degradation_upper_bound",
            _finite_json(bootstrap),
            1,
            bootstrap,
            0.05,
            baseline_mean > 0 and (bootstrap <= 0.05 or math.isclose(bootstrap, 0.05)),
            "<=",
        ),
        _gate(
            "candidate_valid_output_rate_absolute_drop",
            valid[BASELINE_ARM] - valid[CANDIDATE_ARM],
            CASE_COUNT,
            valid_drop,
            0.05,
            valid[BASELINE_ARM] - valid[CANDIDATE_ARM] <= 3,
            "<=",
        ),
        _gate(
            "candidate_accepted_source_contract_violations",
            violations[CANDIDATE_ARM],
            CASE_COUNT,
            float(violations[CANDIDATE_ARM]),
            0,
            violations[CANDIDATE_ARM] == 0,
            "<=",
        ),
        _gate(
            "candidate_severe_harmful_changes",
            severe[CANDIDATE_ARM],
            CASE_COUNT,
            float(severe[CANDIDATE_ARM]),
            0,
            severe[CANDIDATE_ARM] == 0,
            "<=",
        ),
        _gate(
            "candidate_p95_latency_increase_ms",
            latency_increase,
            1,
            latency_increase,
            latency_allowance,
            latency_increase <= latency_allowance,
            "<=",
        ),
    ]
    event_counts = Counter(row["event"] for row in events)
    expected_event_counts = {
        "started": 1,
        "reserved": len(ARMS) * CASE_COUNT,
        "sent": len(ARMS) * CASE_COUNT,
        "terminal": len(ARMS) * CASE_COUNT,
        "completed": 1,
    }
    if event_counts != expected_event_counts:
        raise ScoringError("benchmark accounting is incomplete")
    completed_at = next(row["at"] for row in events if row["event"] == "completed")
    try:
        datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ScoringError("benchmark accounting is incomplete") from None
    all_gates_pass = all(gate["disposition"] == "pass" for gate in gates)
    arm_metrics = {
        arm: {
            "case_count": CASE_COUNT,
            "mean_effort": _mean(effort[arm]),
            "valid_output": {
                "numerator": valid[arm],
                "denominator": CASE_COUNT,
                "rate": valid[arm] / CASE_COUNT,
            },
            "p95_latency_ms": _nearest_rank(latency[arm], 0.95),
            "latency_count": CASE_COUNT,
            "usage": dict(usage[arm]),
            "outcomes": dict(sorted(outcomes[arm].items())),
            "failures": dict(sorted(failures[arm].items())),
            "accepted": {"numerator": acceptable[arm], "denominator": CASE_COUNT},
            "accepted_source_contract_violations": violations[arm],
            "severe_harmful_changes": severe[arm],
            "harmful_change_categories": dict(sorted(harms[arm].items())),
        }
        for arm in ARMS
    }
    report = {
        "report_version": "cleanup-evaluation-report-v1",
        "protocol_id": "cleanup-evaluation-benchmark-v2",
        "run_id": run_id,
        "manifest_sha256": manifest_sha256,
        "review_sha256": review_state["review_sha256"],
        "flow_accounting": {
            "selected_cases": CASE_COUNT,
            "planned_requests": len(ARMS) * CASE_COUNT,
            "terminal_requests": len(requests),
            "individual_reviews": len(individual),
            "pair_reviews": len(pairs),
            "event_counts": dict(sorted(event_counts.items())),
        },
        "arm_metrics": arm_metrics,
        "paired_primary": {
            "case_count": CASE_COUNT,
            "baseline_mean_effort": baseline_mean,
            "candidate_mean_effort": candidate_mean,
            "candidate_relative_decrease": None if baseline_mean == 0 else relative_decrease,
            "bootstrap": {
                "resamples": BOOTSTRAP_RESAMPLES,
                "seed": bootstrap_seed,
                "algorithm": "paired-bootstrap-sha256-v1",
                "statistic": "(candidate_mean-baseline_mean)/baseline_mean",
                "one_sided_percentile": 0.95,
                "upper_bound": _finite_json(bootstrap),
                "zero_baseline_rule": "zero_if_candidate_zero_else_positive_infinity",
            },
        },
        "descriptive_strata": {
            name: {
                "case_count": len(values[BASELINE_ARM]),
                "baseline_mean_effort": _mean(values[BASELINE_ARM]),
                "candidate_mean_effort": _mean(values[CANDIDATE_ARM]),
            }
            for name, values in sorted(strata.items())
        },
        "pair_preference": {
            "denominator": CASE_COUNT,
            **{name: preference[name] for name in ("baseline", "candidate", "tie", "neither")},
        },
        "protocol_deviations": [dict(item) for item in deviations],
        "gates": gates,
        "secondary_results_may_compensate": False,
        "all_gates_pass": all_gates_pass,
        "disposition": "eligible" if all_gates_pass else "no_canary",
        "disposition_reason": (
            "all_gates_passed"
            if all_gates_pass
            else "observed_zero_baseline_mean"
            if baseline_mean == 0
            else "one_or_more_gates_failed"
        ),
        "lifecycle": {
            "write_back_to_live_corpus": False,
            "managed_deletion_required": True,
            "execution_completed_at": completed_at,
        },
    }
    return report


def _private_write(path: Path, value: object) -> None:
    if path.exists() or path.is_symlink() or not path.parent.is_dir():
        raise ScoringError("private export location is invalid")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(canonical_json(value) + b"\n")


def _delete(paths: Iterable[Path]) -> dict[str, int]:
    files = 0
    directories = 0
    for path in paths:
        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
                files += 1
            elif path.is_dir():
                shutil.rmtree(path)
                directories += 1
            elif path.exists():
                raise ScoringError("managed artifact deletion failed")
        except OSError:
            raise ScoringError("managed artifact deletion failed") from None
    return {"files": files, "directories": directories}


def _export_managed_artifacts(paths: Sequence[Path], destination: Path) -> None:
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        raise ScoringError("private export location is invalid")
    destination.mkdir(mode=0o700)
    try:
        for index, source in enumerate(paths):
            target = destination / f"{index:03}-{source.name}"
            if source.is_symlink() or source.is_file():
                shutil.copyfile(source, target, follow_symlinks=False)
                target.chmod(0o600)
            elif source.is_dir():
                shutil.copytree(source, target, symlinks=True)
    except OSError:
        shutil.rmtree(destination, ignore_errors=True)
        raise ScoringError("private artifact export failed") from None


def disposition_cleanup_benchmark(
    registration: object,
    managed_paths: Sequence[Path],
    *,
    snapshot: object | None = None,
    ledger_path: Path | None = None,
    completed_at: datetime | None = None,
    cancelled_at: datetime | None = None,
    withdrawn_at: datetime | None = None,
    stopped_at: datetime | None = None,
    invalidated_at: datetime | None = None,
    unresolved_at: datetime | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    report: Mapping[str, object] | None = None,
    artifact_export_path: Path | None = None,
    report_export_path: Path | None = None,
    eligibility_export_path: Path | None = None,
    signing_key: bytes | None = None,
) -> dict[str, object]:
    """Apply the earliest terminal event, export if explicit, and delete managed artifacts."""
    if not isinstance(registration, dict) or not isinstance(registration.get("manifest"), dict):
        raise ScoringError("disposition inputs are invalid")
    manifest = registration["manifest"]
    if registration.get("manifest_sha256") != _digest(manifest):
        raise ScoringError("registered manifest changed")
    current_time = now().astimezone(UTC)
    try:
        fixed_release = datetime.fromisoformat(
            str(manifest["run_confirmation"]["hold_release_at"]).replace("Z", "+00:00")
        ).astimezone(UTC)
    except (KeyError, ValueError):
        raise ScoringError("disposition inputs are invalid") from None
    events = {
        "completion": None,
        "cancellation": cancelled_at,
        "withdrawal": withdrawn_at,
        "stopped": stopped_at,
        "invalid": invalidated_at,
        "unresolved": unresolved_at,
        "fixed_release": fixed_release if fixed_release <= current_time else None,
    }
    if report is not None:
        events["completion"] = (
            completed_at.astimezone(UTC) if completed_at is not None else current_time
        )
    elif completed_at is not None:
        raise ScoringError("completed benchmark report is required")
    present = {
        name: value.astimezone(UTC) for name, value in events.items() if value is not None
    }
    if not present:
        raise ScoringError("no terminal lifecycle event has occurred")
    terminal_event, terminal_at = min(present.items(), key=lambda item: (item[1], item[0]))
    passing_completion = (
        terminal_event == "completion"
        and report is not None
        and report.get("all_gates_pass") is True
    )
    if terminal_event == "completion":
        if (
            report is None
            or snapshot is None
            or ledger_path is None
            or report.get("run_id") != manifest.get("run_id")
        ):
            raise ScoringError("completed benchmark report is required")
        authoritative_report = score_cleanup_benchmark(
            registration,
            snapshot,
            ledger_path,
            deviations=report.get("protocol_deviations", ()),
        )
        if _digest(authoritative_report) != _digest(report):
            raise ScoringError("completed benchmark report does not match frozen evidence")
        if passing_completion and (
            signing_key is None or len(signing_key) < 32
        ):
            raise ScoringError("local signing key is required for passing benchmark")
    elif report_export_path is not None or eligibility_export_path is not None:
        raise ScoringError("non-completion disposition cannot export benchmark results")

    export_paths = {
        path.resolve()
        for path in (artifact_export_path, report_export_path, eligibility_export_path)
        if path
    }
    managed_resolved = {path.resolve() for path in managed_paths}
    if export_paths & managed_resolved:
        raise ScoringError("private exports cannot be managed artifacts")
    frozen_locations = manifest.get("storage", {}).get("locations")
    if (
        not isinstance(frozen_locations, list)
        or not frozen_locations
        or not all(isinstance(path, str) and path for path in frozen_locations)
        or not {Path(path).resolve() for path in frozen_locations} <= managed_resolved
    ):
        raise ScoringError("managed artifact inventory is incomplete")
    if artifact_export_path is not None:
        _export_managed_artifacts(managed_paths, artifact_export_path)
    if report_export_path is not None and report is not None:
        _private_write(report_export_path, report)

    counts = _delete(managed_paths)
    receipt = {
        "protocol_or_run_id": manifest["run_id"],
        "disposition": terminal_event,
        "deletion_timestamp": current_time.isoformat(),
        "counts": counts,
    }
    eligibility: dict[str, object] | None = None
    if (
        passing_completion
        and report is not None
        and signing_key
    ):
        packet = {
            "packet_version": "cleanup-canary-eligibility-v1",
            "run_id": manifest["run_id"],
            "manifest_sha256": registration["manifest_sha256"],
            "report_sha256": _digest(report),
            "candidate_configuration": {
                "model": manifest.get("provider_evidence", {}).get("models", {}).get(CANDIDATE_ARM),
                "request_contract": manifest.get("request_contract"),
                "deadline_seconds": BENCHMARK_DEADLINE_SECONDS,
            },
            "protocol_deviations": report.get("protocol_deviations"),
            "gates": report.get("gates"),
            "deletion_receipt": receipt,
            "authorizes": "request_separate_explicit_10_cleanup_canary_confirmation_only",
        }
        eligibility = {
            "packet": packet,
            "signature": {
                "algorithm": "hmac-sha256",
                "value": hmac.new(signing_key, canonical_json(packet), hashlib.sha256).hexdigest(),
            },
        }
        if eligibility_export_path is not None:
            _private_write(eligibility_export_path, eligibility)
    return {
        "run_id": manifest["run_id"],
        "terminal_event": terminal_event,
        "terminal_at": terminal_at.isoformat(),
        "canary_eligible": eligibility is not None,
        "deletion_receipt": receipt,
        "eligibility": eligibility,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score and disposition the cleanup benchmark")
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--managed-path", action="append", type=Path, required=True)
    parser.add_argument("--report-export", type=Path)
    parser.add_argument("--artifact-export", type=Path)
    parser.add_argument("--eligibility-export", type=Path)
    parser.add_argument("--signing-key-file", type=Path)
    parser.add_argument("--cancelled-at", type=datetime.fromisoformat)
    parser.add_argument("--withdrawn-at", type=datetime.fromisoformat)
    parser.add_argument("--stopped-at", type=datetime.fromisoformat)
    parser.add_argument("--invalidated-at", type=datetime.fromisoformat)
    parser.add_argument("--unresolved-at", type=datetime.fromisoformat)
    args = parser.parse_args()
    try:
        registration = json.loads(args.registration.read_bytes())
        snapshot = json.loads(args.snapshot.read_bytes())
        current_time = datetime.now(UTC)
        fixed_release = datetime.fromisoformat(
            registration["manifest"]["run_confirmation"]["hold_release_at"].replace(
                "Z", "+00:00"
            )
        ).astimezone(UTC)
        earlier_terminal = any(
            value is not None and value.astimezone(UTC) <= current_time
            for value in (
                args.cancelled_at,
                args.withdrawn_at,
                args.stopped_at,
                args.invalidated_at,
                args.unresolved_at,
            )
        ) or fixed_release <= current_time
        report = (
            None
            if earlier_terminal
            else score_cleanup_benchmark(registration, snapshot, args.ledger)
        )
        signing_key = args.signing_key_file.read_bytes() if args.signing_key_file else None
        result = disposition_cleanup_benchmark(
            registration,
            args.managed_path,
            snapshot=snapshot,
            ledger_path=args.ledger,
            report=report,
            cancelled_at=args.cancelled_at,
            withdrawn_at=args.withdrawn_at,
            stopped_at=args.stopped_at,
            invalidated_at=args.invalidated_at,
            unresolved_at=args.unresolved_at,
            now=lambda: current_time,
            artifact_export_path=args.artifact_export,
            report_export_path=args.report_export,
            eligibility_export_path=args.eligibility_export,
            signing_key=signing_key,
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ScoringError,
        sqlite3.Error,
        KeyError,
        ValueError,
    ):
        print("error: cleanup benchmark scoring failed", file=sys.stderr)
        raise SystemExit(1) from None
    print(
        canonical_json(
            {
                "run_id": result["run_id"],
                "terminal_event": result["terminal_event"],
                "canary_eligible": result["canary_eligible"],
                "deletion_receipt": result["deletion_receipt"],
            }
        ).decode()
    )


if __name__ == "__main__":
    main()
