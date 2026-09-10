import hashlib
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from local_text.cleanup_contract import canonical_json
from local_text.cleanup_evaluation_review import (
    ReviewError,
    freeze_individual_reviews,
    freeze_review,
    initialize_blinded_review,
    next_individual_review,
    next_pair_review,
    record_individual_review,
    record_pair_review,
    review_status,
    unblind_review,
)
from local_text.cleanup_evaluation_runner import CorpusSnapshot

NOW = datetime(2026, 9, 10, 16, tzinfo=UTC)
ARMS = ("baseline_paid_gemini", "candidate_paid_openai")


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def completed_run(
    tmp_path: Path, *, review_seed: int = 41, side_seed: int = 97
) -> tuple[dict, dict, Path]:
    cases = []
    for index in range(60):
        source = f"Original {index}"
        expected = f"Expected {index}"
        case = {
            "case_id": f"case-{index:02}",
            "contract_version": "cleanup-evaluation-corpus-v1",
            "purpose": "polished-cleanup-evaluation-only",
            "revision": index + 1,
            "current_revision": index + 1,
            "source_category": "dictation",
            "source_text": source,
            "expected_cleanup": expected,
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "expected_cleanup_sha256": hashlib.sha256(expected.encode()).hexdigest(),
            "captured_at": NOW.isoformat(),
            "confirmed_at": NOW.isoformat(),
            "expires_at": NOW.isoformat(),
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
                "release_at": NOW.isoformat(),
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
                "corpus_owner": "owner-1",
            },
        }
        record = {key: value for key, value in case.items() if key != "current_revision"}
        case["record_sha256"] = digest(record)
        cases.append(case)
    selected = [
        {"case_id": case["case_id"], "revision": case["revision"], "record_sha256": "a" * 64}
        for case in cases
    ]
    snapshot = {
        "snapshot_version": "cleanup-evaluation-registration-corpus-v1",
        "frozen_at": NOW.isoformat(),
        "cases": cases,
    }
    manifest = {
        "run_id": "run-29",
        "corpus": {
            "selected_cases": selected,
            "snapshot_sha256": digest(
                CorpusSnapshot.model_validate(snapshot).model_dump(mode="json")
            ),
        },
        "review": {
            "individual_order_seed": review_seed,
            "pair_order_seed": 73,
            "pair_side_seed": side_seed,
        },
    }
    registration = {"manifest": manifest, "manifest_sha256": digest(manifest)}
    ledger = tmp_path / f"review-{review_seed}-{side_seed}.sqlite3"
    connection = sqlite3.connect(ledger)
    connection.executescript(
        """
        CREATE TABLE benchmark_run (
            run_id TEXT PRIMARY KEY, manifest_sha256 TEXT NOT NULL, status TEXT NOT NULL,
            reason TEXT NOT NULL, completed_request_count INTEGER NOT NULL,
            actual_cost_usd_micros INTEGER NOT NULL
        );
        CREATE TABLE benchmark_requests (
            ordinal INTEGER PRIMARY KEY, run_id TEXT NOT NULL, case_id TEXT NOT NULL,
            arm_id TEXT NOT NULL, state TEXT NOT NULL, outcome TEXT, user_visible_text TEXT,
            validator_disposition TEXT, provider TEXT, model TEXT, reported_model_version TEXT,
            elapsed_ms INTEGER, input_tokens INTEGER, output_tokens INTEGER,
            actual_usd_micros INTEGER, failure_class TEXT, provider_code TEXT, http_status INTEGER
        );
        """
    )
    connection.execute(
        "INSERT INTO benchmark_run VALUES (?, ?, 'completed', 'all_pairs_completed', 120, 0)",
        ("run-29", registration["manifest_sha256"]),
    )
    ordinal = 0
    for case in cases:
        for arm_index, arm in enumerate(ARMS):
            connection.execute(
                "INSERT INTO benchmark_requests(ordinal, run_id, case_id, arm_id, state, outcome, "
                "user_visible_text, provider, model) VALUES (?, ?, ?, ?, 'terminal', 'success', "
                "?, ?, ?)",
                (
                    ordinal,
                    "run-29",
                    case["case_id"],
                    arm,
                    f"Output {case['case_id']} variant {arm_index}",
                    "gemini" if arm_index == 0 else "openai",
                    "model-g" if arm_index == 0 else "model-o",
                ),
            )
            ordinal += 1
    connection.commit()
    connection.close()
    ledger.chmod(0o600)
    return registration, snapshot, ledger


def acceptable_review(review_id: str, expected_revision: int = 0) -> dict[str, object]:
    return {
        "review_id": review_id,
        "expected_revision": expected_revision,
        "acceptability": "acceptable",
        "accepted_source_contract_violation": "no",
        "harmful_change_category": "none",
        "severity": "none",
        "local_rationale": "Meaning and structure are preserved.",
    }


def complete_individuals(ledger: Path) -> list[dict[str, object]]:
    seen = []
    while item := next_individual_review(ledger, "run-29"):
        seen.append(item)
        record_individual_review(ledger, "run-29", acceptable_review(item["review_id"]))
    return seen


def complete_pairs(ledger: Path) -> list[dict[str, object]]:
    seen = []
    while item := next_pair_review(ledger, "run-29"):
        seen.append(item)
        record_pair_review(
            ledger,
            "run-29",
            {"review_id": item["review_id"], "expected_revision": 0, "choice": "tie"},
        )
    return seen


def test_individual_review_is_seeded_complete_blind_and_resumable(tmp_path: Path) -> None:
    registration, snapshot, ledger = completed_run(tmp_path)
    initialized = initialize_blinded_review(registration, snapshot, ledger, now=lambda: NOW)
    first = next_individual_review(ledger, "run-29")

    assert initialized["individual_total"] == 120
    assert first is not None
    assert set(first) == {"review_id", "position", "total", "user_visible_text"}
    assert not any(
        word in canonical_json(first).decode().lower()
        for word in ("baseline", "candidate", "gemini", "openai", "arm_id", "provider")
    )
    record_individual_review(ledger, "run-29", acceptable_review(first["review_id"]))
    resumed = initialize_blinded_review(registration, snapshot, ledger, now=lambda: NOW)
    assert resumed["individual_completed"] == 1
    assert next_individual_review(ledger, "run-29")["review_id"] != first["review_id"]

    remaining = complete_individuals(ledger)
    assert len(remaining) == 119
    assert len({item["user_visible_text"] for item in [first, *remaining]}) == 120


def test_individual_order_uses_review_seed_not_execution_order(tmp_path: Path) -> None:
    first_registration, first_snapshot, first_ledger = completed_run(tmp_path, review_seed=41)
    second_registration, second_snapshot, second_ledger = completed_run(tmp_path, review_seed=42)
    initialize_blinded_review(first_registration, first_snapshot, first_ledger, now=lambda: NOW)
    initialize_blinded_review(second_registration, second_snapshot, second_ledger, now=lambda: NOW)

    first_order = [item["user_visible_text"] for item in complete_individuals(first_ledger)]
    second_order = [item["user_visible_text"] for item in complete_individuals(second_ledger)]

    assert first_order != second_order
    assert first_order[:2] != ["Output case-00 variant 0", "Output case-00 variant 1"]


def test_same_seeds_reproduce_exact_individual_and_pair_presentation(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir(mode=0o700)
    second_dir.mkdir(mode=0o700)
    first_registration, first_snapshot, first_ledger = completed_run(first_dir)
    second_registration, second_snapshot, second_ledger = completed_run(second_dir)
    presentations = []
    for registration, snapshot, ledger in (
        (first_registration, first_snapshot, first_ledger),
        (second_registration, second_snapshot, second_ledger),
    ):
        initialize_blinded_review(registration, snapshot, ledger, now=lambda: NOW)
        individuals = complete_individuals(ledger)
        freeze_individual_reviews(ledger, "run-29", now=lambda: NOW)
        pairs = complete_pairs(ledger)
        presentations.append((individuals, pairs))

    assert presentations[0] == presentations[1]


@pytest.mark.parametrize(
    "changes",
    [
        {"acceptability": "maybe"},
        {"accepted_source_contract_violation": "unknown"},
        {"harmful_change_category": "style"},
        {"severity": "minor"},
        {"local_rationale": "   "},
        {"harmful_change_category": "meaning", "severity": "none"},
        {"harmful_change_category": "none", "severity": "severe"},
    ],
)
def test_individual_rubric_rejects_missing_invalid_and_conflicting_values(
    tmp_path: Path, changes: dict[str, str]
) -> None:
    registration, snapshot, ledger = completed_run(tmp_path)
    initialize_blinded_review(registration, snapshot, ledger, now=lambda: NOW)
    item = next_individual_review(ledger, "run-29")
    response = acceptable_review(item["review_id"])
    response.update(changes)

    with pytest.raises(ReviewError, match="individual review is invalid"):
        record_individual_review(ledger, "run-29", response)


def test_all_protocol_review_vocabulary_is_accepted_without_mutating_rationale(
    tmp_path: Path,
) -> None:
    registration, snapshot, ledger = completed_run(tmp_path)
    initialize_blinded_review(registration, snapshot, ledger, now=lambda: NOW)
    item = next_individual_review(ledger, "run-29")
    categories = (
        "meaning",
        "invented_content",
        "qualification_or_negation",
        "number_or_date",
        "name_or_technical_term",
        "link_code_or_identifier",
        "quotation",
        "layout",
    )
    revision = 0
    for acceptability in ("acceptable", "unacceptable"):
        for violation in ("yes", "no"):
            for category in categories:
                for severity in ("non_severe", "severe"):
                    rationale = f"  {acceptability} {violation} {category} {severity}  "
                    response = acceptable_review(item["review_id"], expected_revision=revision)
                    response.update(
                        acceptability=acceptability,
                        accepted_source_contract_violation=violation,
                        harmful_change_category=category,
                        severity=severity,
                        local_rationale=rationale,
                    )
                    revision = record_individual_review(
                        ledger, "run-29", response, now=lambda: NOW
                    )["revision"]

    connection = sqlite3.connect(ledger)
    stored = connection.execute(
        "SELECT local_rationale FROM individual_reviews WHERE review_id = ?", (item["review_id"],)
    ).fetchone()[0]
    connection.close()
    assert stored.startswith("  ") and stored.endswith("  ")


def test_revision_conflict_and_unresolved_items_block_phase_freeze(tmp_path: Path) -> None:
    registration, snapshot, ledger = completed_run(tmp_path)
    initialize_blinded_review(registration, snapshot, ledger, now=lambda: NOW)
    item = next_individual_review(ledger, "run-29")
    record_individual_review(ledger, "run-29", acceptable_review(item["review_id"]))

    with pytest.raises(ReviewError, match="revision conflict"):
        record_individual_review(ledger, "run-29", acceptable_review(item["review_id"]))
    with pytest.raises(ReviewError, match="unresolved"):
        freeze_individual_reviews(ledger, "run-29", now=lambda: NOW)
    assert review_status(ledger, "run-29")["review_blocks_benchmark_passage"] is True


def test_pairs_start_after_individual_freeze_with_independent_order_and_sides(
    tmp_path: Path,
) -> None:
    registration, snapshot, ledger = completed_run(tmp_path)
    initialize_blinded_review(registration, snapshot, ledger, now=lambda: NOW)
    assert next_pair_review(ledger, "run-29") is None
    complete_individuals(ledger)
    freeze_individual_reviews(ledger, "run-29", now=lambda: NOW)

    pairs = complete_pairs(ledger)

    assert len(pairs) == 60
    assert set(pairs[0]) == {"review_id", "position", "total", "original_text", "a", "b"}
    assert [pair["original_text"] for pair in pairs[:2]] != ["Original 0", "Original 1"]
    assert {pair["a"].rsplit(" ", 1)[-1] for pair in pairs} == {"0", "1"}
    assert not any(
        word in canonical_json(pairs).decode().lower()
        for word in ("baseline", "candidate", "gemini", "openai", "arm_id", "provider")
    )


def test_pair_side_seed_changes_sides_without_changing_pair_order(tmp_path: Path) -> None:
    first_registration, first_snapshot, first_ledger = completed_run(tmp_path, side_seed=97)
    second_registration, second_snapshot, second_ledger = completed_run(tmp_path, side_seed=98)
    for registration, snapshot, ledger in (
        (first_registration, first_snapshot, first_ledger),
        (second_registration, second_snapshot, second_ledger),
    ):
        initialize_blinded_review(registration, snapshot, ledger, now=lambda: NOW)
        complete_individuals(ledger)
        freeze_individual_reviews(ledger, "run-29", now=lambda: NOW)

    first_pairs = complete_pairs(first_ledger)
    second_pairs = complete_pairs(second_ledger)

    assert [item["original_text"] for item in first_pairs] == [
        item["original_text"] for item in second_pairs
    ]
    assert [item["a"] for item in first_pairs] != [item["a"] for item in second_pairs]


def test_frozen_review_is_immutable_and_unblinds_exactly_once(tmp_path: Path) -> None:
    registration, snapshot, ledger = completed_run(tmp_path)
    initialize_blinded_review(registration, snapshot, ledger, now=lambda: NOW)
    individuals = complete_individuals(ledger)
    freeze_individual_reviews(ledger, "run-29", now=lambda: NOW)
    pairs = complete_pairs(ledger)
    frozen = freeze_review(ledger, "run-29", now=lambda: NOW)

    with pytest.raises(ReviewError, match="frozen"):
        record_individual_review(
            ledger, "run-29", acceptable_review(individuals[0]["review_id"], expected_revision=1)
        )
    with pytest.raises(ReviewError, match="frozen"):
        record_pair_review(
            ledger,
            "run-29",
            {"review_id": pairs[0]["review_id"], "expected_revision": 1, "choice": "a"},
        )

    revealed = unblind_review(ledger, "run-29", now=lambda: NOW)
    assert frozen["review_sha256"] == revealed["review_sha256"]
    assert len(revealed["individual_reviews"]) == 120
    assert len(revealed["pair_reviews"]) == 60
    assert {item["arm_id"] for item in revealed["individual_reviews"]} == set(ARMS)
    assert review_status(ledger, "run-29")["review_blocks_benchmark_passage"] is False
    with pytest.raises(ReviewError, match="already unblinded"):
        unblind_review(ledger, "run-29", now=lambda: NOW)

    connection = sqlite3.connect(ledger)
    with pytest.raises(sqlite3.IntegrityError, match="invalid review transition"):
        connection.execute("UPDATE review_state SET phase = 'individual' WHERE run_id = 'run-29'")
    with pytest.raises(sqlite3.IntegrityError, match="frozen review"):
        connection.execute(
            "INSERT INTO individual_reviews(run_id, review_id, position, request_ordinal, "
            "case_id, case_revision) VALUES ('run-29', 'extra', 121, 121, 'extra', 1)"
        )
    connection.close()


def test_invalid_or_unresolved_pair_blocks_freeze_and_unblinding(tmp_path: Path) -> None:
    registration, snapshot, ledger = completed_run(tmp_path)
    initialize_blinded_review(registration, snapshot, ledger, now=lambda: NOW)
    complete_individuals(ledger)
    freeze_individual_reviews(ledger, "run-29", now=lambda: NOW)
    pair = next_pair_review(ledger, "run-29")

    with pytest.raises(ReviewError, match="pair review is invalid"):
        record_pair_review(
            ledger,
            "run-29",
            {"review_id": pair["review_id"], "expected_revision": 0, "choice": "undecided"},
        )
    with pytest.raises(ReviewError, match="unresolved"):
        freeze_review(ledger, "run-29", now=lambda: NOW)
    with pytest.raises(ReviewError, match="complete frozen review"):
        unblind_review(ledger, "run-29", now=lambda: NOW)


def test_incomplete_execution_and_private_values_never_appear_in_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registration, snapshot, ledger = completed_run(tmp_path)
    connection = sqlite3.connect(ledger)
    connection.execute("UPDATE benchmark_run SET status = 'stopped'")
    connection.commit()
    connection.close()

    with pytest.raises(ReviewError, match="completed benchmark is required") as error:
        initialize_blinded_review(registration, snapshot, ledger, now=lambda: NOW)

    captured = capsys.readouterr()
    combined = f"{error.value}{captured.out}{captured.err}"
    assert "Original 0" not in combined
    assert "Expected 0" not in combined
    assert str(ledger) not in combined


def test_cli_errors_do_not_reveal_private_paths(tmp_path: Path) -> None:
    private_path = tmp_path / "PRIVATE-ACCOUNT-SENTINEL.sqlite3"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_text.cleanup_evaluation_review",
            "status",
            "--ledger",
            str(private_path),
            "--run-id",
            "run-29",
        ],
        env=os.environ,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stderr == "error: cleanup benchmark review failed\n"
    assert "PRIVATE-ACCOUNT-SENTINEL" not in result.stdout + result.stderr
    assert not private_path.exists()


def test_cli_invalid_response_does_not_echo_any_private_class(tmp_path: Path) -> None:
    registration, snapshot, ledger = completed_run(tmp_path)
    initialize_blinded_review(registration, snapshot, ledger, now=lambda: NOW)
    response = tmp_path / "response.json"
    sentinels = (
        "ORIGINAL EXPECTED OUTPUT RATIONALE PROMPT PAYLOAD CREDENTIAL ACCOUNT PRIVATE-PATH"
    )
    response.write_text(canonical_json({"private": sentinels}).decode())

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_text.cleanup_evaluation_review",
            "record-individual",
            "--ledger",
            str(ledger),
            "--run-id",
            "run-29",
            "--response",
            str(response),
        ],
        env=os.environ,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stderr == "error: cleanup benchmark review failed\n"
    assert all(value not in result.stdout + result.stderr for value in sentinels.split())
