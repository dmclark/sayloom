import hashlib
import hmac
import json
import math
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from local_text.cleanup_contract import canonical_json
from local_text.cleanup_evaluation_runner import CorpusSnapshot
from local_text.cleanup_evaluation_scoring import (
    ScoringError,
    disposition_cleanup_benchmark,
    normalize_scoring_text,
    normalized_effort,
    paired_bootstrap_upper_bound,
    score_cleanup_benchmark,
    unicode_levenshtein,
)

NOW = datetime(2026, 9, 10, 18, tzinfo=UTC)
ARMS = ("baseline_paid_gemini", "candidate_paid_openai")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def scoring_run(tmp_path: Path) -> tuple[dict, dict, Path]:
    cases = []
    for index in range(60):
        case = {
            "case_id": f"case-{index:02}",
            "contract_version": "cleanup-evaluation-corpus-v1",
            "purpose": "polished-cleanup-evaluation-only",
            "revision": 1,
            "current_revision": 1,
            "source_category": "dictation",
            "source_text": "b",
            "expected_cleanup": "a",
            "source_sha256": hashlib.sha256(b"b").hexdigest(),
            "expected_cleanup_sha256": hashlib.sha256(b"a").hexdigest(),
            "captured_at": NOW.isoformat(),
            "confirmed_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(days=10)).isoformat(),
            "original_user_confirmed": True,
            "expected_cleanup_user_confirmed": True,
            "consent": {
                "version": "cleanup-evaluation-consent-v1",
                "scope": "polished-cleanup-evaluation-only",
                "confirmed_at": NOW.isoformat(),
            },
            "hold": {
                "benchmark_id": "cleanup-evaluation-benchmark-v2",
                "confirmed_at": NOW.isoformat(),
                "release_at": (NOW + timedelta(days=2)).isoformat(),
            },
            "prompt": {
                "version_id": "prompt-1",
                "content_sha256": hashlib.sha256(b"prompt").hexdigest(),
                "text": "prompt",
            },
            "annotations": {
                "primary_stratum": "unchanged",
                "challenge_tags": [],
                "ambiguous": False,
                "transcript_truth_dependent": False,
                "frozen_at": NOW.isoformat(),
                "corpus_owner": "owner",
            },
        }
        record = {key: value for key, value in case.items() if key != "current_revision"}
        case["record_sha256"] = digest(record)
        cases.append(case)
    snapshot = {
        "snapshot_version": "cleanup-evaluation-registration-corpus-v1",
        "frozen_at": NOW.isoformat(),
        "cases": cases,
    }
    normalized_snapshot = CorpusSnapshot.model_validate(snapshot).model_dump(mode="json")
    manifest = {
        "run_id": "run-30",
        "corpus": {
            "snapshot_sha256": digest(normalized_snapshot),
            "selected_cases": [
                {
                    "case_id": case["case_id"],
                    "revision": 1,
                    "record_sha256": case["record_sha256"],
                }
                for case in cases
            ],
        },
        "scoring": {"bootstrap_seed": 1234, "bootstrap_resamples": 10_000},
        "provider_evidence": {
            "models": {
                "candidate_paid_openai": {
                    "provider": "openai",
                    "model": "gpt-5.6-luna",
                    "reported_version": "2026-09-01",
                }
            }
        },
        "request_contract": {"frozen": True},
        "run_confirmation": {"hold_release_at": (NOW + timedelta(days=2)).isoformat()},
        "lifecycle": {"write_back_to_live_corpus": False},
    }
    registration = {"manifest": manifest, "manifest_sha256": digest(manifest)}
    ledger = tmp_path / "run.sqlite3"
    manifest["storage"] = {"locations": [str(ledger)]}
    registration["manifest_sha256"] = digest(manifest)
    connection = sqlite3.connect(ledger)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE benchmark_run (
            run_id TEXT PRIMARY KEY, manifest_sha256 TEXT, status TEXT, reason TEXT,
            completed_request_count INTEGER, actual_cost_usd_micros INTEGER
        );
        CREATE TABLE benchmark_requests (
            ordinal INTEGER PRIMARY KEY, run_id TEXT, case_id TEXT, arm_id TEXT, state TEXT,
            outcome TEXT, user_visible_text TEXT, validator_disposition TEXT, provider TEXT,
            model TEXT, reported_model_version TEXT, elapsed_ms INTEGER, input_tokens INTEGER,
            output_tokens INTEGER, actual_usd_micros INTEGER, failure_class TEXT,
            provider_code TEXT, http_status INTEGER
        );
        CREATE TABLE benchmark_events (
            event_index INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, event TEXT,
            case_id TEXT, arm_id TEXT, at TEXT
        );
        CREATE TABLE review_state (
            run_id TEXT PRIMARY KEY, manifest_sha256 TEXT, phase TEXT, initialized_at TEXT,
            individual_frozen_at TEXT, review_frozen_at TEXT, review_sha256 TEXT,
            results_sha256 TEXT, unblinded_at TEXT
        );
        CREATE TABLE individual_reviews (
            run_id TEXT, review_id TEXT, position INTEGER, request_ordinal INTEGER,
            case_id TEXT, case_revision INTEGER, revision INTEGER, acceptability TEXT,
            accepted_source_contract_violation TEXT, harmful_change_category TEXT,
            severity TEXT, local_rationale TEXT, updated_at TEXT
        );
        CREATE TABLE pair_reviews (
            run_id TEXT, review_id TEXT, position INTEGER, case_id TEXT, case_revision INTEGER,
            original_text TEXT, a_request_ordinal INTEGER, b_request_ordinal INTEGER,
            revision INTEGER, choice TEXT, updated_at TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO benchmark_run VALUES (?, ?, 'completed', 'all_pairs_completed', 120, 180)",
        ("run-30", registration["manifest_sha256"]),
    )
    connection.execute(
        "INSERT INTO review_state VALUES (?, ?, 'unblinded', ?, ?, ?, ?, ?, ?)",
        (
            "run-30",
            registration["manifest_sha256"],
            *([NOW.isoformat()] * 3),
            "pending",
            "pending",
            NOW.isoformat(),
        ),
    )
    ordinal = 0
    for index, case in enumerate(cases):
        ordinals = []
        for arm in ARMS:
            output = "b" if arm == ARMS[0] else "a"
            connection.execute(
                "INSERT INTO benchmark_requests VALUES (?, 'run-30', ?, ?, 'terminal', "
                "'success', ?, 'accepted', ?, ?, NULL, 1000, 10, 5, 1, NULL, NULL, NULL)",
                (
                    ordinal,
                    case["case_id"],
                    arm,
                    output,
                    "gemini" if arm == ARMS[0] else "openai",
                    "baseline" if arm == ARMS[0] else "candidate",
                ),
            )
            connection.execute(
                "INSERT INTO individual_reviews VALUES ('run-30', ?, ?, ?, ?, 1, 1, "
                "'acceptable', 'no', 'none', 'none', 'ok', ?)",
                (
                    f"individual-{ordinal:03}",
                    ordinal + 1,
                    ordinal,
                    case["case_id"],
                    NOW.isoformat(),
                ),
            )
            connection.execute(
                "INSERT INTO benchmark_events(run_id, event, case_id, arm_id, at) "
                "VALUES ('run-30', 'reserved', ?, ?, ?), ('run-30', 'sent', ?, ?, ?), "
                "('run-30', 'terminal', ?, ?, ?)",
                (
                    case["case_id"], arm, NOW.isoformat(),
                    case["case_id"], arm, NOW.isoformat(),
                    case["case_id"], arm, NOW.isoformat(),
                ),
            )
            ordinals.append(ordinal)
            ordinal += 1
        connection.execute(
            "INSERT INTO pair_reviews VALUES ('run-30', ?, ?, ?, 1, 'b', ?, ?, 1, 'b', ?)",
            (f"pair-{index:03}", index + 1, case["case_id"], *ordinals, NOW.isoformat()),
        )
    connection.execute(
        "INSERT INTO benchmark_events(run_id, event, at) VALUES ('run-30', 'started', ?)",
        (NOW.isoformat(),),
    )
    connection.execute(
        "INSERT INTO benchmark_events(run_id, event, at) VALUES ('run-30', 'completed', ?)",
        (NOW.isoformat(),),
    )
    frozen_review = {
        "individual_reviews": [
            dict(row)
            for row in connection.execute(
                "SELECT review_id, position, revision, acceptability, "
                "accepted_source_contract_violation, harmful_change_category, severity, "
                "local_rationale FROM individual_reviews ORDER BY position"
            )
        ],
        "pair_reviews": [
            dict(row)
            for row in connection.execute(
                "SELECT review_id, position, revision, choice FROM pair_reviews ORDER BY position"
            )
        ],
    }
    connection.execute(
        "UPDATE review_state SET review_sha256 = ?", (digest(frozen_review),)
    )
    frozen_results = [
        dict(row)
        for row in connection.execute(
            "SELECT ordinal, case_id, arm_id, outcome, user_visible_text, validator_disposition, "
            "provider, model, reported_model_version, elapsed_ms, input_tokens, output_tokens, "
            "actual_usd_micros, failure_class, provider_code, http_status "
            "FROM benchmark_requests ORDER BY ordinal"
        )
    ]
    connection.execute(
        "UPDATE review_state SET results_sha256 = ?", (digest(frozen_results),)
    )
    connection.commit()
    connection.close()
    ledger.chmod(0o600)
    return registration, snapshot, ledger


def update_request(ledger: Path, where: str, **values: object) -> None:
    connection = sqlite3.connect(ledger)
    assignments = ", ".join(f"{name} = ?" for name in values)
    connection.execute(
        f"UPDATE benchmark_requests SET {assignments} WHERE {where}",  # noqa: S608
        tuple(values.values()),
    )
    connection.commit()
    connection.close()
    refresh_result_hash(ledger)


def refresh_result_hash(ledger: Path) -> None:
    connection = sqlite3.connect(ledger)
    connection.row_factory = sqlite3.Row
    frozen_results = [
        dict(row)
        for row in connection.execute(
            "SELECT ordinal, case_id, arm_id, outcome, user_visible_text, validator_disposition, "
            "provider, model, reported_model_version, elapsed_ms, input_tokens, output_tokens, "
            "actual_usd_micros, failure_class, provider_code, http_status "
            "FROM benchmark_requests ORDER BY ordinal"
        )
    ]
    connection.execute(
        "UPDATE review_state SET results_sha256 = ?", (digest(frozen_results),)
    )
    connection.commit()
    connection.close()


def refresh_review_hash(ledger: Path) -> None:
    connection = sqlite3.connect(ledger)
    connection.row_factory = sqlite3.Row
    frozen_review = {
        "individual_reviews": [
            dict(row)
            for row in connection.execute(
                "SELECT review_id, position, revision, acceptability, "
                "accepted_source_contract_violation, harmful_change_category, severity, "
                "local_rationale FROM individual_reviews ORDER BY position"
            )
        ],
        "pair_reviews": [
            dict(row)
            for row in connection.execute(
                "SELECT review_id, position, revision, choice FROM pair_reviews ORDER BY position"
            )
        ],
    }
    connection.execute("UPDATE review_state SET review_sha256 = ?", (digest(frozen_review),))
    connection.commit()
    connection.close()


def test_normalization_and_asymmetric_code_point_effort_boundaries() -> None:
    assert normalize_scoring_text("e\u0301\r\n x\r") == "é\n x\n"
    assert normalize_scoring_text(" A  B ") == " A  B "
    assert unicode_levenshtein("😀a", "😀b") == 1
    assert normalized_effort("ab", "a") == 1
    assert normalized_effort("a", "ab") == 0.5
    assert normalized_effort("x", "") == 1


def test_bootstrap_is_deterministic_paired_and_applies_zero_rules() -> None:
    baseline = [1.0] * 60
    candidate = [0.0] * 59 + [30.0]
    first = paired_bootstrap_upper_bound(baseline, candidate, 99)

    assert first == paired_bootstrap_upper_bound(baseline, candidate, 99)
    assert first > 0.05
    assert paired_bootstrap_upper_bound([0.0] * 60, [0.0] * 60, 99) == 0
    assert math.isinf(paired_bootstrap_upper_bound([0.0] * 60, [1.0] * 60, 99))


def test_complete_report_scores_fail_open_and_timeout_latency(tmp_path: Path) -> None:
    registration, snapshot, ledger = scoring_run(tmp_path)
    update_request(
        ledger,
        "arm_id = 'candidate_paid_openai' AND case_id = 'case-00'",
        outcome="timeout",
        user_visible_text="a",
        validator_disposition="fail_open_timeout",
        elapsed_ms=17,
    )

    report = score_cleanup_benchmark(
        registration, snapshot, ledger, deviations=[{"id": "none", "present": False}]
    )

    candidate = report["arm_metrics"]["candidate_paid_openai"]
    assert candidate["mean_effort"] == pytest.approx(1 / 60)
    assert candidate["valid_output"] == {"numerator": 59, "denominator": 60, "rate": 59 / 60}
    assert candidate["p95_latency_ms"] == 1000
    assert candidate["outcomes"] == {"success": 59, "timeout": 1}
    assert report["flow_accounting"] == {
        "selected_cases": 60,
        "planned_requests": 120,
        "terminal_requests": 120,
        "individual_reviews": 120,
        "pair_reviews": 60,
        "event_counts": {
            "completed": 1,
            "reserved": 120,
            "sent": 120,
            "started": 1,
            "terminal": 120,
        },
    }
    assert len(report["gates"]) == 6
    assert all(
        {"gate", "numerator", "denominator", "value", "threshold", "comparison", "disposition"}
        == set(gate)
        for gate in report["gates"]
    )
    assert report["secondary_results_may_compensate"] is False
    assert report["review_sha256"] == digest(
        {
            "individual_reviews": [
                {
                    "review_id": f"individual-{ordinal:03}",
                    "position": ordinal + 1,
                    "revision": 1,
                    "acceptability": "acceptable",
                    "accepted_source_contract_violation": "no",
                    "harmful_change_category": "none",
                    "severity": "none",
                    "local_rationale": "ok",
                }
                for ordinal in range(120)
            ],
            "pair_reviews": [
                {
                    "review_id": f"pair-{index:03}",
                    "position": index + 1,
                    "revision": 1,
                    "choice": "b",
                }
                for index in range(60)
            ],
        }
    )


@pytest.mark.parametrize(
    ("gate", "mutation"),
    [
        ("candidate_mean_effort_relative_decrease", "effort"),
        ("paired_bootstrap_relative_degradation_upper_bound", "bootstrap"),
        ("candidate_valid_output_rate_absolute_drop", "validity"),
        ("candidate_accepted_source_contract_violations", "violation"),
        ("candidate_severe_harmful_changes", "severe"),
        ("candidate_p95_latency_increase_ms", "latency"),
    ],
)
def test_each_frozen_gate_fails_independently(
    tmp_path: Path, gate: str, mutation: str
) -> None:
    registration, snapshot, ledger = scoring_run(tmp_path)
    if mutation == "effort":
        update_request(ledger, "arm_id = 'candidate_paid_openai'", user_visible_text="b")
    elif mutation == "bootstrap":
        update_request(
            ledger,
            "arm_id = 'candidate_paid_openai' AND case_id = 'case-00'",
            user_visible_text="x" * 30,
        )
    elif mutation == "validity":
        update_request(
            ledger,
            "arm_id = 'candidate_paid_openai' AND case_id IN "
            "('case-00', 'case-01', 'case-02', 'case-03')",
            outcome="failure",
            validator_disposition="fail_open_failure",
        )
    elif mutation in {"violation", "severe"}:
        connection = sqlite3.connect(ledger)
        column = "accepted_source_contract_violation" if mutation == "violation" else "severity"
        value = "yes" if mutation == "violation" else "severe"
        connection.execute(
            f"UPDATE individual_reviews SET {column} = ? WHERE request_ordinal = 1",  # noqa: S608
            (value,),
        )
        connection.commit()
        connection.close()
        refresh_review_hash(ledger)
    else:
        update_request(ledger, "arm_id = 'candidate_paid_openai'", elapsed_ms=2001)

    report = score_cleanup_benchmark(registration, snapshot, ledger)
    disposition = {item["gate"]: item["disposition"] for item in report["gates"]}

    assert disposition[gate] == "fail"
    assert report["all_gates_pass"] is False
    assert report["disposition"] == "no_canary"


def test_zero_observed_baseline_and_selective_omission_never_pass(tmp_path: Path) -> None:
    registration, snapshot, ledger = scoring_run(tmp_path)
    update_request(ledger, "arm_id = 'baseline_paid_gemini'", user_visible_text="a")
    report = score_cleanup_benchmark(registration, snapshot, ledger)
    assert report["disposition_reason"] == "observed_zero_baseline_mean"
    assert report["all_gates_pass"] is False

    connection = sqlite3.connect(ledger)
    connection.execute("DELETE FROM benchmark_requests WHERE ordinal = 0")
    connection.commit()
    connection.close()
    with pytest.raises(ScoringError, match="completed frozen unblinded"):
        score_cleanup_benchmark(registration, snapshot, ledger)


def test_post_freeze_result_replacement_is_rejected(tmp_path: Path) -> None:
    registration, snapshot, ledger = scoring_run(tmp_path)
    connection = sqlite3.connect(ledger)
    connection.execute("UPDATE benchmark_requests SET user_visible_text = 'a' WHERE ordinal = 0")
    connection.commit()
    connection.close()

    with pytest.raises(ScoringError, match="frozen result integrity"):
        score_cleanup_benchmark(registration, snapshot, ledger)


def test_only_pass_exports_signed_packet_after_managed_deletion(tmp_path: Path) -> None:
    registration, snapshot, ledger = scoring_run(tmp_path)
    report = score_cleanup_benchmark(registration, snapshot, ledger)
    managed = tmp_path / "managed"
    managed.mkdir()
    (managed / "private.txt").write_text("private")
    report_export = tmp_path / "report.json"
    packet_export = tmp_path / "packet.json"

    result = disposition_cleanup_benchmark(
        registration,
        [ledger, managed],
        snapshot=snapshot,
        ledger_path=ledger,
        now=lambda: NOW + timedelta(hours=1),
        report=report,
        report_export_path=report_export,
        eligibility_export_path=packet_export,
        signing_key=b"local signing key with 32 bytes!!",
    )

    assert result["canary_eligible"] is True
    assert not ledger.exists() and not managed.exists()
    assert report_export.stat().st_mode & 0o777 == 0o600
    exported = json.loads(packet_export.read_bytes())
    assert exported["packet"]["manifest_sha256"] == registration["manifest_sha256"]
    assert exported["packet"]["report_sha256"] == digest(report)
    assert exported["packet"]["deletion_receipt"]["counts"] == {"files": 1, "directories": 1}
    expected = hmac.new(
        b"local signing key with 32 bytes!!",
        canonical_json(exported["packet"]),
        hashlib.sha256,
    ).hexdigest()
    assert exported["signature"] == {"algorithm": "hmac-sha256", "value": expected}


@pytest.mark.parametrize(
    ("event_name", "event_time", "now_offset"),
    [
        ("withdrawn_at", NOW + timedelta(hours=1), timedelta(hours=2)),
        ("cancelled_at", NOW + timedelta(hours=1), timedelta(hours=2)),
        (None, None, timedelta(days=3)),
    ],
)
def test_withdrawal_cancellation_and_fixed_release_delete_without_private_receipt(
    tmp_path: Path, event_name: str | None, event_time: datetime | None, now_offset: timedelta
) -> None:
    registration, _, ledger = scoring_run(tmp_path)
    arguments = {event_name: event_time} if event_name else {}

    result = disposition_cleanup_benchmark(
        registration, [ledger], now=lambda: NOW + now_offset, **arguments
    )

    expected = {"withdrawn_at": "withdrawal", "cancelled_at": "cancellation"}.get(
        event_name, "fixed_release"
    )
    assert result["terminal_event"] == expected
    assert result["canary_eligible"] is False
    assert result["eligibility"] is None
    assert set(result["deletion_receipt"]) == {
        "protocol_or_run_id",
        "disposition",
        "deletion_timestamp",
        "counts",
    }
    assert not ledger.exists()


def test_earlier_withdrawal_overrides_a_later_completed_report(tmp_path: Path) -> None:
    registration, snapshot, ledger = scoring_run(tmp_path)
    report = score_cleanup_benchmark(registration, snapshot, ledger)

    result = disposition_cleanup_benchmark(
        registration,
        [ledger],
        snapshot=snapshot,
        ledger_path=ledger,
        report=report,
        completed_at=NOW + timedelta(hours=2),
        withdrawn_at=NOW + timedelta(hours=1),
        now=lambda: NOW + timedelta(hours=3),
    )

    assert result["terminal_event"] == "withdrawal"
    assert result["canary_eligible"] is False
    assert not ledger.exists()


def test_fabricated_passing_report_is_never_signed_or_deleted(tmp_path: Path) -> None:
    registration, snapshot, ledger = scoring_run(tmp_path)
    report = score_cleanup_benchmark(registration, snapshot, ledger)
    report["gates"][0]["threshold"] = 99

    with pytest.raises(ScoringError, match="does not match frozen evidence"):
        disposition_cleanup_benchmark(
            registration,
            [ledger],
            snapshot=snapshot,
            ledger_path=ledger,
            report=report,
            now=lambda: NOW + timedelta(hours=1),
            signing_key=b"local signing key with 32 bytes!!",
        )
    assert ledger.exists()


def test_stopped_run_can_export_then_delete_all_frozen_managed_locations(
    tmp_path: Path,
) -> None:
    registration, _, ledger = scoring_run(tmp_path)
    export = tmp_path / "private-export"

    result = disposition_cleanup_benchmark(
        registration,
        [ledger],
        stopped_at=NOW + timedelta(hours=1),
        now=lambda: NOW + timedelta(hours=2),
        artifact_export_path=export,
    )

    assert result["terminal_event"] == "stopped"
    assert not ledger.exists()
    assert len(list(export.iterdir())) == 1
