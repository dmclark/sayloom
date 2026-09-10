"""Durable local blinded review for the completed paired cleanup benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from local_text.cleanup_contract import canonical_json
from local_text.cleanup_evaluation_execution import ARMS, _connect
from local_text.cleanup_evaluation_runner import CorpusSnapshot

INDIVIDUAL_DOMAIN = "local_text:cleanup-evaluation:individual-review-order:v1"
PAIR_DOMAIN = "local_text:cleanup-evaluation:pair-review-order:v1"
SIDE_DOMAIN = "local_text:cleanup-evaluation:pair-review-side:v1"
ACCEPTABILITY = {"acceptable", "unacceptable"}
SOURCE_VIOLATION = {"yes", "no"}
HARM_CATEGORIES = {
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
SEVERITIES = {"none", "non_severe", "severe"}
PAIR_CHOICES = {"a", "b", "tie", "neither"}


class ReviewError(ValueError):
    """A privacy-safe blinded review failure."""


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _ordered(values: list[str], seed: int, domain: str) -> list[str]:
    return sorted(values, key=lambda value: (_digest([domain, seed, value]), value))


def _create_schema(connection: Any) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS review_state (
            run_id TEXT PRIMARY KEY,
            manifest_sha256 TEXT NOT NULL,
            phase TEXT NOT NULL CHECK (
                phase IN ('individual', 'pair', 'frozen', 'unblinded')
            ),
            initialized_at TEXT NOT NULL,
            individual_frozen_at TEXT,
            review_frozen_at TEXT,
            review_sha256 TEXT,
            unblinded_at TEXT
        );
        CREATE TABLE IF NOT EXISTS individual_reviews (
            run_id TEXT NOT NULL,
            review_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            request_ordinal INTEGER NOT NULL,
            case_id TEXT NOT NULL,
            case_revision INTEGER NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0,
            acceptability TEXT,
            accepted_source_contract_violation TEXT,
            harmful_change_category TEXT,
            severity TEXT,
            local_rationale TEXT,
            updated_at TEXT,
            PRIMARY KEY (run_id, review_id),
            UNIQUE (run_id, position),
            UNIQUE (run_id, request_ordinal)
        );
        CREATE TABLE IF NOT EXISTS pair_reviews (
            run_id TEXT NOT NULL,
            review_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            case_id TEXT NOT NULL,
            case_revision INTEGER NOT NULL,
            original_text TEXT NOT NULL,
            a_request_ordinal INTEGER NOT NULL,
            b_request_ordinal INTEGER NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0,
            choice TEXT,
            updated_at TEXT,
            PRIMARY KEY (run_id, review_id),
            UNIQUE (run_id, position),
            UNIQUE (run_id, case_id)
        );
        CREATE TABLE IF NOT EXISTS review_events (
            event_index INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            event TEXT NOT NULL,
            at TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS frozen_individual_review_update
        BEFORE UPDATE ON individual_reviews
        WHEN (SELECT phase FROM review_state WHERE run_id = OLD.run_id) != 'individual'
        BEGIN SELECT RAISE(ABORT, 'frozen review'); END;
        CREATE TRIGGER IF NOT EXISTS frozen_individual_review_insert
        BEFORE INSERT ON individual_reviews
        WHEN (SELECT phase FROM review_state WHERE run_id = NEW.run_id) != 'individual'
        BEGIN SELECT RAISE(ABORT, 'frozen review'); END;
        CREATE TRIGGER IF NOT EXISTS frozen_individual_review_delete
        BEFORE DELETE ON individual_reviews
        WHEN (SELECT phase FROM review_state WHERE run_id = OLD.run_id) != 'individual'
        BEGIN SELECT RAISE(ABORT, 'frozen review'); END;
        CREATE TRIGGER IF NOT EXISTS frozen_pair_review_update
        BEFORE UPDATE ON pair_reviews
        WHEN (SELECT phase FROM review_state WHERE run_id = OLD.run_id)
            NOT IN ('individual', 'pair')
        BEGIN SELECT RAISE(ABORT, 'frozen review'); END;
        CREATE TRIGGER IF NOT EXISTS frozen_pair_review_insert
        BEFORE INSERT ON pair_reviews
        WHEN (SELECT phase FROM review_state WHERE run_id = NEW.run_id) != 'individual'
        BEGIN SELECT RAISE(ABORT, 'frozen review'); END;
        CREATE TRIGGER IF NOT EXISTS forward_only_review_phase
        BEFORE UPDATE ON review_state
        WHEN NOT (
            (OLD.phase = 'individual' AND NEW.phase = 'pair')
            OR (OLD.phase = 'pair' AND NEW.phase = 'frozen')
            OR (OLD.phase = 'frozen' AND NEW.phase = 'unblinded')
        )
        BEGIN SELECT RAISE(ABORT, 'invalid review transition'); END;
        CREATE TRIGGER IF NOT EXISTS durable_review_state
        BEFORE DELETE ON review_state
        BEGIN SELECT RAISE(ABORT, 'durable review state'); END;
        CREATE TRIGGER IF NOT EXISTS append_only_review_events_update
        BEFORE UPDATE ON review_events
        BEGIN SELECT RAISE(ABORT, 'append-only review event'); END;
        CREATE TRIGGER IF NOT EXISTS append_only_review_events_delete
        BEFORE DELETE ON review_events
        BEGIN SELECT RAISE(ABORT, 'append-only review event'); END;
        CREATE TRIGGER IF NOT EXISTS frozen_pair_review_delete
        BEFORE DELETE ON pair_reviews
        WHEN (SELECT phase FROM review_state WHERE run_id = OLD.run_id)
            NOT IN ('individual', 'pair')
        BEGIN SELECT RAISE(ABORT, 'frozen review'); END;
        """
    )


def _open(ledger_path: Path) -> Any:
    if not ledger_path.is_file():
        raise ReviewError("review storage is unavailable")
    try:
        connection = _connect(ledger_path)
        _create_schema(connection)
        return connection
    except (OSError, sqlite3.Error, ValueError):
        raise ReviewError("review storage is unavailable") from None


def _event(connection: Any, run_id: str, event: str, at: datetime) -> None:
    connection.execute(
        "INSERT INTO review_events(run_id, event, at) VALUES (?, ?, ?)",
        (run_id, event, at.astimezone(UTC).isoformat()),
    )


def _state(connection: Any, run_id: str) -> Any:
    row = connection.execute("SELECT * FROM review_state WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise ReviewError("blinded review is not initialized")
    return row


def initialize_blinded_review(
    registration: object,
    snapshot: object,
    ledger_path: Path,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Bind a complete execution and frozen corpus to deterministic blind review items."""
    if not isinstance(registration, dict) or not isinstance(registration.get("manifest"), dict):
        raise ReviewError("review inputs are invalid")
    manifest = registration["manifest"]
    manifest_sha256 = registration.get("manifest_sha256")
    try:
        manifest_matches = manifest_sha256 == _digest(manifest)
    except (TypeError, ValueError):
        manifest_matches = False
    corpus = manifest.get("corpus")
    review = manifest.get("review")
    if not manifest_matches or not isinstance(corpus, dict) or not isinstance(review, dict):
        raise ReviewError("review inputs are invalid")
    run_id = manifest.get("run_id")
    selected = corpus.get("selected_cases")
    seeds = (
        review.get("individual_order_seed"),
        review.get("pair_order_seed"),
        review.get("pair_side_seed"),
    )
    if (
        not isinstance(run_id, str)
        or not isinstance(selected, list)
        or len(selected) != 60
        or any(not isinstance(seed, int) or isinstance(seed, bool) for seed in seeds)
    ):
        raise ReviewError("review inputs are invalid")
    try:
        validated_snapshot = CorpusSnapshot.model_validate(snapshot)
    except ValidationError:
        raise ReviewError("review inputs are invalid") from None
    normalized_snapshot = validated_snapshot.model_dump(mode="json")
    if corpus.get("snapshot_sha256") != _digest(normalized_snapshot):
        raise ReviewError("review inputs are invalid")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("case_id"), str)
        or not isinstance(item.get("revision"), int)
        or isinstance(item.get("revision"), bool)
        for item in selected
    ):
        raise ReviewError("review inputs are invalid")
    selected_revisions = {
        item.get("case_id"): item.get("revision") for item in selected if isinstance(item, dict)
    }
    case_by_id = {
        item["case_id"]: item for item in normalized_snapshot["cases"]
    }
    if (
        len(selected_revisions) != 60
        or len(case_by_id) != len(snapshot["cases"])
        or any(
            case_by_id.get(case_id, {}).get("revision") != revision
            or not isinstance(case_by_id.get(case_id, {}).get("source_text"), str)
            for case_id, revision in selected_revisions.items()
        )
    ):
        raise ReviewError("review inputs are invalid")

    connection = _open(ledger_path)
    try:
        existing = connection.execute(
            "SELECT manifest_sha256 FROM review_state WHERE run_id = ?", (run_id,)
        ).fetchone()
        if existing is not None:
            if existing["manifest_sha256"] != manifest_sha256:
                raise ReviewError("review inputs changed after initialization")
            return review_status(ledger_path, run_id)
        run = connection.execute(
            "SELECT status, completed_request_count, manifest_sha256 FROM benchmark_run "
            "WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        requests = connection.execute(
            "SELECT ordinal, case_id, arm_id FROM benchmark_requests "
            "WHERE run_id = ? AND state = 'terminal' ORDER BY ordinal",
            (run_id,),
        ).fetchall()
        requests_by_case: dict[str, list[Any]] = {}
        for row in requests:
            requests_by_case.setdefault(row["case_id"], []).append(row)
        if (
            run is None
            or run["status"] != "completed"
            or run["completed_request_count"] != 120
            or run["manifest_sha256"] != manifest_sha256
            or len(requests) != 120
            or set(requests_by_case) != set(selected_revisions)
            or any(
                len(rows) != 2 or {row["arm_id"] for row in rows} != set(ARMS)
                for rows in requests_by_case.values()
            )
        ):
            raise ReviewError("completed benchmark is required")

        individual_order = _ordered(
            [str(row["ordinal"]) for row in requests], seeds[0], INDIVIDUAL_DOMAIN
        )
        pair_order = _ordered(list(selected_revisions), seeds[1], PAIR_DOMAIN)
        initialized_at = now().astimezone(UTC)
        with connection:
            connection.execute(
                "INSERT INTO review_state(run_id, manifest_sha256, phase, initialized_at) "
                "VALUES (?, ?, 'individual', ?)",
                (run_id, manifest_sha256, initialized_at.isoformat()),
            )
            for position, ordinal_text in enumerate(individual_order, 1):
                ordinal = int(ordinal_text)
                row = next(row for row in requests if row["ordinal"] == ordinal)
                connection.execute(
                    "INSERT INTO individual_reviews(run_id, review_id, position, request_ordinal, "
                    "case_id, case_revision) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        f"individual-{position:03}",
                        position,
                        ordinal,
                        row["case_id"],
                        selected_revisions[row["case_id"]],
                    ),
                )
            for position, case_id in enumerate(pair_order, 1):
                rows = sorted(requests_by_case[case_id], key=lambda row: row["arm_id"])
                side_key = _digest([SIDE_DOMAIN, seeds[2], case_id])
                a_row, b_row = rows if int(side_key, 16) % 2 == 0 else reversed(rows)
                connection.execute(
                    "INSERT INTO pair_reviews(run_id, review_id, position, case_id, case_revision, "
                    "original_text, a_request_ordinal, b_request_ordinal) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        f"pair-{position:03}",
                        position,
                        case_id,
                        selected_revisions[case_id],
                        case_by_id[case_id]["source_text"],
                        a_row["ordinal"],
                        b_row["ordinal"],
                    ),
                )
            _event(connection, run_id, "review_initialized", initialized_at)
        return review_status(ledger_path, run_id)
    finally:
        connection.close()


def review_status(ledger_path: Path, run_id: str) -> dict[str, object]:
    """Return private-safe progress without identities or content."""
    connection = _open(ledger_path)
    try:
        state = _state(connection, run_id)
        individual_completed = connection.execute(
            "SELECT COUNT(*) FROM individual_reviews WHERE run_id = ? AND revision > 0", (run_id,)
        ).fetchone()[0]
        pair_completed = connection.execute(
            "SELECT COUNT(*) FROM pair_reviews WHERE run_id = ? AND revision > 0", (run_id,)
        ).fetchone()[0]
        return {
            "run_id": run_id,
            "phase": state["phase"],
            "individual_completed": individual_completed,
            "individual_total": 120,
            "pair_completed": pair_completed,
            "pair_total": 60,
            "review_sha256": state["review_sha256"],
            "review_blocks_benchmark_passage": state["phase"] != "unblinded",
        }
    finally:
        connection.close()


def next_individual_review(ledger_path: Path, run_id: str) -> dict[str, object] | None:
    """Return the next unresolved output with no identity-bearing metadata."""
    connection = _open(ledger_path)
    try:
        _state(connection, run_id)
        row = connection.execute(
            "SELECT reviews.review_id, reviews.position, requests.user_visible_text "
            "FROM individual_reviews reviews JOIN benchmark_requests requests "
            "ON requests.ordinal = reviews.request_ordinal "
            "WHERE reviews.run_id = ? AND reviews.revision = 0 ORDER BY reviews.position LIMIT 1",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "review_id": row["review_id"],
            "position": row["position"],
            "total": 120,
            "user_visible_text": row["user_visible_text"],
        }
    finally:
        connection.close()


def _individual_values(response: object) -> tuple[object, ...]:
    required = {
        "review_id",
        "expected_revision",
        "acceptability",
        "accepted_source_contract_violation",
        "harmful_change_category",
        "severity",
        "local_rationale",
    }
    if not isinstance(response, dict) or set(response) != required:
        raise ReviewError("individual review is invalid")
    rationale = response["local_rationale"]
    category = response["harmful_change_category"]
    severity = response["severity"]
    if (
        not isinstance(response["review_id"], str)
        or not isinstance(response["expected_revision"], int)
        or isinstance(response["expected_revision"], bool)
        or response["expected_revision"] < 0
        or response["acceptability"] not in ACCEPTABILITY
        or response["accepted_source_contract_violation"] not in SOURCE_VIOLATION
        or category not in HARM_CATEGORIES
        or severity not in SEVERITIES
        or (category == "none") != (severity == "none")
        or not isinstance(rationale, str)
        or not rationale.strip()
        or "\x00" in rationale
    ):
        raise ReviewError("individual review is invalid")
    return (
        response["acceptability"],
        response["accepted_source_contract_violation"],
        category,
        severity,
        rationale,
    )


def record_individual_review(
    ledger_path: Path,
    run_id: str,
    response: object,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Create or revise one judgment using optimistic revision checking."""
    values = _individual_values(response)
    connection = _open(ledger_path)
    try:
        state = _state(connection, run_id)
        if state["phase"] != "individual":
            raise ReviewError("individual review is frozen")
        with connection:
            cursor = connection.execute(
                "UPDATE individual_reviews SET revision = revision + 1, acceptability = ?, "
                "accepted_source_contract_violation = ?, harmful_change_category = ?, "
                "severity = ?, "
                "local_rationale = ?, updated_at = ? WHERE run_id = ? AND review_id = ? "
                "AND revision = ?",
                (
                    *values,
                    now().astimezone(UTC).isoformat(),
                    run_id,
                    response["review_id"],
                    response["expected_revision"],
                ),
            )
            if cursor.rowcount != 1:
                raise ReviewError("individual review revision conflict")
        return {"review_id": response["review_id"], "revision": response["expected_revision"] + 1}
    finally:
        connection.close()


def freeze_individual_reviews(
    ledger_path: Path,
    run_id: str,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Freeze all 120 individual judgments before exposing any pair."""
    connection = _open(ledger_path)
    try:
        state = _state(connection, run_id)
        if state["phase"] != "individual":
            raise ReviewError("individual review is frozen")
        unresolved = connection.execute(
            "SELECT COUNT(*) FROM individual_reviews WHERE run_id = ? AND revision = 0", (run_id,)
        ).fetchone()[0]
        if unresolved:
            raise ReviewError("individual review has unresolved items")
        at = now().astimezone(UTC)
        with connection:
            connection.execute(
                "UPDATE review_state SET phase = 'pair', individual_frozen_at = ? WHERE run_id = ?",
                (at.isoformat(), run_id),
            )
            _event(connection, run_id, "individual_reviews_frozen", at)
        return review_status(ledger_path, run_id)
    finally:
        connection.close()


def next_pair_review(ledger_path: Path, run_id: str) -> dict[str, object] | None:
    """Return the next unresolved side-randomized pair after individual freeze."""
    connection = _open(ledger_path)
    try:
        state = _state(connection, run_id)
        if state["phase"] == "individual":
            return None
        row = connection.execute(
            "SELECT pairs.review_id, pairs.position, pairs.original_text, "
            "a.user_visible_text AS a, "
            "b.user_visible_text AS b FROM pair_reviews pairs "
            "JOIN benchmark_requests a ON a.ordinal = pairs.a_request_ordinal "
            "JOIN benchmark_requests b ON b.ordinal = pairs.b_request_ordinal "
            "WHERE pairs.run_id = ? AND pairs.revision = 0 ORDER BY pairs.position LIMIT 1",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "review_id": row["review_id"],
            "position": row["position"],
            "total": 60,
            "original_text": row["original_text"],
            "a": row["a"],
            "b": row["b"],
        }
    finally:
        connection.close()


def record_pair_review(
    ledger_path: Path,
    run_id: str,
    response: object,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Create or revise one pair preference using optimistic revision checking."""
    if (
        not isinstance(response, dict)
        or set(response) != {"review_id", "expected_revision", "choice"}
        or not isinstance(response["review_id"], str)
        or not isinstance(response["expected_revision"], int)
        or isinstance(response["expected_revision"], bool)
        or response["expected_revision"] < 0
        or response["choice"] not in PAIR_CHOICES
    ):
        raise ReviewError("pair review is invalid")
    connection = _open(ledger_path)
    try:
        state = _state(connection, run_id)
        if state["phase"] == "individual":
            raise ReviewError("individual review is not frozen")
        if state["phase"] != "pair":
            raise ReviewError("pair review is frozen")
        with connection:
            cursor = connection.execute(
                "UPDATE pair_reviews SET revision = revision + 1, choice = ?, updated_at = ? "
                "WHERE run_id = ? AND review_id = ? AND revision = ?",
                (
                    response["choice"],
                    now().astimezone(UTC).isoformat(),
                    run_id,
                    response["review_id"],
                    response["expected_revision"],
                ),
            )
            if cursor.rowcount != 1:
                raise ReviewError("pair review revision conflict")
        return {"review_id": response["review_id"], "revision": response["expected_revision"] + 1}
    finally:
        connection.close()


def _frozen_reviews(connection: Any, run_id: str) -> dict[str, object]:
    individuals = connection.execute(
        "SELECT review_id, position, revision, acceptability, "
        "accepted_source_contract_violation, harmful_change_category, severity, local_rationale "
        "FROM individual_reviews WHERE run_id = ? ORDER BY position",
        (run_id,),
    ).fetchall()
    pairs = connection.execute(
        "SELECT review_id, position, revision, choice FROM pair_reviews "
        "WHERE run_id = ? ORDER BY position",
        (run_id,),
    ).fetchall()
    return {
        "individual_reviews": [dict(row) for row in individuals],
        "pair_reviews": [dict(row) for row in pairs],
    }


def freeze_review(
    ledger_path: Path,
    run_id: str,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Freeze all pair choices and hash the complete still-blinded review."""
    connection = _open(ledger_path)
    try:
        state = _state(connection, run_id)
        if state["phase"] != "pair":
            raise ReviewError("pair review is not available")
        unresolved = connection.execute(
            "SELECT COUNT(*) FROM pair_reviews WHERE run_id = ? AND revision = 0", (run_id,)
        ).fetchone()[0]
        if unresolved:
            raise ReviewError("pair review has unresolved items")
        review_sha256 = _digest(_frozen_reviews(connection, run_id))
        at = now().astimezone(UTC)
        with connection:
            connection.execute(
                "UPDATE review_state SET phase = 'frozen', review_frozen_at = ?, review_sha256 = ? "
                "WHERE run_id = ?",
                (at.isoformat(), review_sha256, run_id),
            )
            _event(connection, run_id, "review_frozen", at)
        return {"run_id": run_id, "phase": "frozen", "review_sha256": review_sha256}
    finally:
        connection.close()


def unblind_review(
    ledger_path: Path,
    run_id: str,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Perform and record the sole identity-revealing transition."""
    connection = _open(ledger_path)
    try:
        state = _state(connection, run_id)
        if state["phase"] == "unblinded":
            raise ReviewError("review is already unblinded")
        if state["phase"] != "frozen":
            raise ReviewError("complete frozen review is required")
        blind = _frozen_reviews(connection, run_id)
        individuals = connection.execute(
            "SELECT reviews.review_id, reviews.position, reviews.case_id, reviews.case_revision, "
            "requests.arm_id, requests.provider, requests.model, reviews.acceptability, "
            "reviews.accepted_source_contract_violation, reviews.harmful_change_category, "
            "reviews.severity, reviews.local_rationale FROM individual_reviews reviews "
            "JOIN benchmark_requests requests ON requests.ordinal = reviews.request_ordinal "
            "WHERE reviews.run_id = ? ORDER BY reviews.position",
            (run_id,),
        ).fetchall()
        pairs = connection.execute(
            "SELECT pairs.review_id, pairs.position, pairs.case_id, pairs.case_revision, "
            "a.arm_id AS a_arm_id, b.arm_id AS b_arm_id, pairs.choice "
            "FROM pair_reviews pairs "
            "JOIN benchmark_requests a ON a.ordinal = pairs.a_request_ordinal "
            "JOIN benchmark_requests b ON b.ordinal = pairs.b_request_ordinal "
            "WHERE pairs.run_id = ? ORDER BY pairs.position",
            (run_id,),
        ).fetchall()
        if _digest(blind) != state["review_sha256"]:
            raise ReviewError("frozen review integrity check failed")
        at = now().astimezone(UTC)
        with connection:
            cursor = connection.execute(
                "UPDATE review_state SET phase = 'unblinded', unblinded_at = ? "
                "WHERE run_id = ? AND phase = 'frozen'",
                (at.isoformat(), run_id),
            )
            if cursor.rowcount != 1:
                raise ReviewError("review is already unblinded")
            _event(connection, run_id, "review_unblinded", at)
        return {
            "run_id": run_id,
            "review_sha256": state["review_sha256"],
            "unblinded_at": at.isoformat(),
            "individual_reviews": [dict(row) for row in individuals],
            "pair_reviews": [dict(row) for row in pairs],
        }
    finally:
        connection.close()


def _read_json(path: Path) -> object:
    return json.loads(path.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture the local blinded cleanup review")
    parser.add_argument(
        "action",
        choices=(
            "initialize",
            "status",
            "next-individual",
            "record-individual",
            "freeze-individual",
            "next-pair",
            "record-pair",
            "freeze",
            "unblind",
        ),
    )
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--registration", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--response", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "initialize":
            if args.registration is None or args.snapshot is None:
                raise ReviewError("review inputs are invalid")
            registration = _read_json(args.registration)
            result = initialize_blinded_review(
                registration, _read_json(args.snapshot), args.ledger
            )
        else:
            if not args.run_id:
                raise ReviewError("run identity is required")
            if args.action == "status":
                result = review_status(args.ledger, args.run_id)
            elif args.action == "next-individual":
                result = next_individual_review(args.ledger, args.run_id)
            elif args.action == "record-individual":
                if args.response is None:
                    raise ReviewError("individual review is invalid")
                result = record_individual_review(
                    args.ledger, args.run_id, _read_json(args.response)
                )
            elif args.action == "freeze-individual":
                result = freeze_individual_reviews(args.ledger, args.run_id)
            elif args.action == "next-pair":
                result = next_pair_review(args.ledger, args.run_id)
            elif args.action == "record-pair":
                if args.response is None:
                    raise ReviewError("pair review is invalid")
                result = record_pair_review(args.ledger, args.run_id, _read_json(args.response))
            elif args.action == "freeze":
                result = freeze_review(args.ledger, args.run_id)
            else:
                result = unblind_review(args.ledger, args.run_id)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ReviewError,
        KeyError,
        sqlite3.Error,
    ):
        print("error: cleanup benchmark review failed", file=sys.stderr)
        raise SystemExit(1) from None
    print(canonical_json(result).decode())


if __name__ == "__main__":
    main()
