import json
import signal
import stat
from pathlib import Path

import pytest

from local_text.automatic_strategy_evaluation import (
    PIPELINE_VERSION,
    ExecutionRequest,
    ExecutionResult,
    build_report,
    execute_run,
    import_adjudications,
    register_run,
)


def write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def candidate(
    candidate_id: str,
    *,
    kind: str,
    family: str,
    methods: list[str],
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "kind": kind,
        "family": family,
        "method_ids": methods,
        "executor": "synthetic-v1",
        "provider": {
            "provider": "synthetic-provider",
            "model": "synthetic-model-v1",
            "settings": {"temperature": 0},
        },
        "prompt": "Correct only synthetic recognition errors.",
        "routing": {"policy": family, "version": "v1"},
        "maximum_internal_retries": 1,
        "ceilings": {
            "provider_calls": 12,
            "input_tokens": 1200,
            "output_tokens": 600,
            "cost_usd_micros": 120,
        },
    }


def configuration(run_id: str = "synthetic-automatic-v1") -> dict[str, object]:
    return {
        "pipeline_version": PIPELINE_VERSION,
        "run_id": run_id,
        "protocol_version": "automatic-protocol-v1",
        "software_version": "test-revision",
        "phase": "development",
        "synthetic_validation": True,
        "schedule_seed": "schedule-seed-v1",
        "bootstrap_seed": "bootstrap-seed-v1",
        "bootstrap_resamples": 200,
        "required_strata": ["conversation", "command"],
        "stratum_weights": {"conversation": 0.75, "command": 0.25},
        "candidates": [
            candidate(
                "lexical",
                kind="component",
                family="deterministic_lexical",
                methods=["lexical"],
            ),
            candidate(
                "model",
                kind="component",
                family="constrained_general_model",
                methods=["model"],
            ),
            candidate(
                "cascade",
                kind="strategy",
                family="fixed_cascade",
                methods=["lexical", "model"],
            ),
            candidate(
                "router",
                kind="strategy",
                family="evidence_router",
                methods=["lexical", "model"],
            ),
        ],
        "privacy": {
            "storage": "user-controlled-external",
            "provider_data_use": "synthetic-only",
            "private_text_in_git": False,
            "private_text_in_logs": False,
            "private_text_in_application_state": False,
        },
        "approvals": {
            "provider_calls": False,
            "private_data": False,
            "spending": False,
        },
        "stop_conditions": [
            "privacy_failure",
            "answer_leakage",
            "corpus_drift",
            "unplanned_candidate_change",
            "ceiling_exceeded",
        ],
    }


def synthetic_cases() -> list[dict[str, object]]:
    return [
        {
            "case_id": "conversation-1",
            "group_id": "group-1",
            "partition": "development",
            "eligible": True,
            "synthetic": True,
            "stratum": "conversation",
            "original": "Synthetic wrong alpha.",
            "intended_variants": ["Synthetic right alpha."],
            "context": "Synthetic conversation context.",
            "profile": ["alpha"],
        },
        {
            "case_id": "command-1",
            "group_id": "group-2",
            "partition": "development",
            "eligible": True,
            "synthetic": True,
            "stratum": "command",
            "original": "Synthetic wrong beta.",
            "intended_variants": ["Synthetic right beta."],
            "context": "",
            "profile": [],
        },
    ]


def register_synthetic_run(tmp_path: Path) -> tuple[Path, Path]:
    private = tmp_path / "private"
    app_database = tmp_path / "application-state" / "local-text.sqlite3"
    register_run(
        configuration_path=write_json(private / "configuration.json", configuration()),
        cases_path=write_json(private / "cases.json", synthetic_cases()),
        runs_directory=private / "runs",
        application_database_path=app_database,
    )
    return private / "runs" / "synthetic-automatic-v1", app_database


def test_registration_freezes_dynamic_candidates_and_approval_manifest(tmp_path: Path) -> None:
    private = tmp_path / "private"
    app_database = tmp_path / "application-state" / "local-text.sqlite3"

    result = register_run(
        configuration_path=write_json(private / "configuration.json", configuration()),
        cases_path=write_json(private / "cases.json", synthetic_cases()),
        runs_directory=private / "runs",
        application_database_path=app_database,
    )

    run_directory = private / "runs" / "synthetic-automatic-v1"
    manifest = json.loads((run_directory / "manifest.json").read_text())
    schedule = json.loads((run_directory / "schedule.json").read_text())
    assert result == {
        "run_id": "synthetic-automatic-v1",
        "candidate_count": 4,
        "eligible_case_count": 2,
        "scheduled_attempt_count": 24,
        "approval_required": True,
        "registration_sha256": result["registration_sha256"],
    }
    assert manifest["candidate_ids"] == ["lexical", "model", "cascade", "router"]
    assert manifest["repetitions_per_case"] == 3
    assert manifest["approval_review"] == {
        "provider_calls": False,
        "private_data": False,
        "spending": False,
        "required_before_non_synthetic_execution": True,
    }
    assert manifest["privacy"]["storage"] == "user-controlled-external"
    assert manifest["stop_conditions"][-1] == "ceiling_exceeded"
    assert manifest["candidates"][2]["routing"]["policy"] == "fixed_cascade"
    assert manifest["worst_case_totals"] == {
        "provider_calls": 48,
        "input_tokens": 4800,
        "output_tokens": 2400,
        "cost_usd_micros": 480,
    }
    assert len(schedule) == 24
    assert {row["candidate_id"] for row in schedule} == {
        "lexical",
        "model",
        "cascade",
        "router",
    }
    assert {row["repetition"] for row in schedule} == {1, 2, 3}
    assert not any("condition_id" in row for row in schedule)
    assert stat.S_IMODE(run_directory.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in run_directory.iterdir())


class SyntheticExecutor:
    def __call__(self, request: ExecutionRequest) -> ExecutionResult:
        intended = request.case.intended_variants[0]
        prepared = (
            intended.replace("right", "correct")
            if request.candidate.candidate_id == "cascade"
            else intended
        )
        return ExecutionResult(
            outcome="success",
            prepared_text=prepared,
            selected_method=request.candidate.method_ids[-1],
            repairs=[
                {
                    "before": "wrong",
                    "after": "correct" if request.candidate.candidate_id == "cascade" else "right",
                    "uncertain": request.candidate.candidate_id == "cascade",
                }
            ],
            internal_retries=1 if request.candidate.candidate_id == "router" else 0,
            latency_ms=40,
            provider_calls=2 if request.candidate.candidate_id == "router" else 1,
            input_tokens=10,
            output_tokens=5,
            cost_usd_micros=1,
        )


def test_synthetic_execution_blinds_review_and_reports_without_text(tmp_path: Path) -> None:
    run_directory, app_database = register_synthetic_run(tmp_path)

    execution = execute_run(
        run_directory=run_directory,
        executor=SyntheticExecutor(),
        application_database_path=app_database,
    )

    assert execution == {
        "scheduled_attempt_count": 24,
        "completed_attempt_count": 24,
        "failed_attempt_count": 0,
        "abstention_count": 0,
        "review_count": 6,
        "stopped_candidates": [],
    }
    packet = json.loads((run_directory / "blind-review.json").read_text())
    mapping = json.loads((run_directory / "blind-map.json").read_text())
    assert len(packet) == len(mapping) == 6
    assert not ({"case_id", "candidate_id", "method_id"} & packet[0].keys())
    assert {"original", "intended_variants", "candidate_text"} <= packet[0].keys()

    adjudications = [
        {"review_id": row["review_id"], "verdict": "equivalent"} for row in packet
    ]
    assert import_adjudications(
        run_directory=run_directory,
        adjudications_path=write_json(
            tmp_path / "private" / "adjudications.json", adjudications
        ),
        application_database_path=app_database,
    ) == {"adjudication_count": 6}

    report = build_report(
        run_directory=run_directory,
        application_database_path=app_database,
    )
    assert report["evidence_status"] == "synthetic_harness_validation_only"
    assert report["candidate_count"] == 4
    assert report["scheduled_attempt_count"] == 24
    assert report["candidates"]["cascade"]["editing_reduction"] == 1.0
    assert report["candidates"]["router"]["provider_calls"] == 12
    assert report["candidates"]["router"]["internal_retries"] == 6
    assert report["candidates"]["router"]["routed_methods"]["model"]["attempts"] == 6
    assert report["candidates"]["router"]["gates"]["point_estimates_pass"] is True
    serialized = json.dumps(report)
    for case in synthetic_cases():
        assert case["case_id"] not in serialized
        assert case["original"] not in serialized
        assert case["intended_variants"][0] not in serialized


def test_candidate_ceiling_stops_only_its_branch_and_fails_open(tmp_path: Path) -> None:
    config = configuration("ceiling-stop")
    config["candidates"][0]["ceilings"]["provider_calls"] = 0
    private = tmp_path / "private"
    app_database = tmp_path / "application-state" / "local-text.sqlite3"
    register_run(
        configuration_path=write_json(private / "configuration.json", config),
        cases_path=write_json(private / "cases.json", synthetic_cases()),
        runs_directory=private / "runs",
        application_database_path=app_database,
    )
    run_directory = private / "runs" / "ceiling-stop"

    result = execute_run(
        run_directory=run_directory,
        executor=SyntheticExecutor(),
        application_database_path=app_database,
    )

    assert result["stopped_candidates"] == ["lexical"]
    executions = json.loads((run_directory / "executions.json").read_text())
    lexical = [row for row in executions if row["candidate_id"] == "lexical"]
    assert len(lexical) == 6
    assert all(row["outcome"] == "failure" for row in lexical)
    assert all(row["fail_open_to_original"] is True for row in lexical)
    assert {row["failure_class"] for row in lexical} == {
        "ceiling_exceeded",
        "branch_stopped",
    }


def test_executor_exceptions_fail_open_without_aborting_the_run(tmp_path: Path) -> None:
    run_directory, app_database = register_synthetic_run(tmp_path)

    def failing_executor(_request: ExecutionRequest) -> ExecutionResult:
        raise RuntimeError("synthetic executor failure")

    result = execute_run(
        run_directory=run_directory,
        executor=failing_executor,
        application_database_path=app_database,
    )

    assert result["completed_attempt_count"] == 24
    assert result["failed_attempt_count"] == 24
    executions = json.loads((run_directory / "executions.json").read_text())
    assert {row["failure_class"] for row in executions} == {"executor_exception"}
    assert all(row["fail_open_to_original"] is True for row in executions)


def test_executor_timeout_is_enforced_and_signal_state_is_restored(tmp_path: Path) -> None:
    run_directory, app_database = register_synthetic_run(tmp_path)
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def timed_out_executor(_request: ExecutionRequest) -> ExecutionResult:
        signal.raise_signal(signal.SIGALRM)
        raise AssertionError("the timeout signal should interrupt the executor")

    result = execute_run(
        run_directory=run_directory,
        executor=timed_out_executor,
        application_database_path=app_database,
    )

    assert result["completed_attempt_count"] == 24
    assert result["failed_attempt_count"] == 24
    executions = json.loads((run_directory / "executions.json").read_text())
    assert {row["failure_class"] for row in executions} == {"timeout"}
    assert {row["latency_ms"] for row in executions} == {30_000}
    assert signal.getsignal(signal.SIGALRM) == previous_handler
    assert signal.getitimer(signal.ITIMER_REAL) == previous_timer


def test_bootstrap_resamples_cases_and_abstention_latency_uses_recorded_time(
    tmp_path: Path,
) -> None:
    run_directory, app_database = register_synthetic_run(tmp_path)
    attempts: dict[tuple[str, str], int] = {}

    def repeated_executor(request: ExecutionRequest) -> ExecutionResult:
        key = (request.candidate.candidate_id, request.case.case_id)
        attempts[key] = attempts.get(key, 0) + 1
        if attempts[key] > 1:
            return ExecutionResult(
                outcome="abstention",
                repairs=[],
                internal_retries=0,
                latency_ms=15_000,
                provider_calls=0,
                input_tokens=0,
                output_tokens=0,
                cost_usd_micros=0,
            )
        return ExecutionResult(
            outcome="success",
            prepared_text=request.case.intended_variants[0],
            selected_method=request.candidate.method_ids[-1],
            repairs=[{"before": "wrong", "after": "right", "uncertain": False}],
            internal_retries=0,
            latency_ms=40,
            provider_calls=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd_micros=0,
        )

    execute_run(
        run_directory=run_directory,
        executor=repeated_executor,
        application_database_path=app_database,
    )
    import_adjudications(
        run_directory=run_directory,
        adjudications_path=write_json(tmp_path / "private" / "adjudications.json", []),
        application_database_path=app_database,
    )
    report = build_report(run_directory=run_directory, application_database_path=app_database)
    lexical = report["candidates"]["lexical"]

    assert lexical["within_ten_seconds"] == pytest.approx(1 / 3)
    assert lexical["confidence_lower_bounds"]["within_ten_seconds"] == pytest.approx(1 / 3)


def test_repair_level_adjudication_preserves_mixed_correctness(tmp_path: Path) -> None:
    run_directory, app_database = register_synthetic_run(tmp_path)

    def mixed_executor(request: ExecutionRequest) -> ExecutionResult:
        if request.candidate.candidate_id != "cascade":
            return SyntheticExecutor()(request)
        intended = request.case.intended_variants[0]
        final_word = intended.split()[-1].rstrip(".")
        return ExecutionResult(
            outcome="success",
            prepared_text=intended.replace(final_word, "gamma"),
            selected_method="model",
            repairs=[
                {"before": "wrong", "after": "right", "uncertain": False},
                {"before": final_word, "after": "gamma", "uncertain": False},
            ],
            internal_retries=0,
            latency_ms=40,
            provider_calls=1,
            input_tokens=10,
            output_tokens=5,
            cost_usd_micros=1,
        )

    execution = execute_run(
        run_directory=run_directory,
        executor=mixed_executor,
        application_database_path=app_database,
    )
    mapping = json.loads((run_directory / "blind-map.json").read_text())
    assert execution["review_count"] == 12
    assert {row["repair_index"] for row in mapping} == {0, 1}
    import_adjudications(
        run_directory=run_directory,
        adjudications_path=write_json(
            tmp_path / "private" / "adjudications.json",
            [
                {
                    "review_id": row["review_id"],
                    "verdict": "correct" if row["repair_index"] == 0 else "wrong",
                }
                for row in mapping
            ],
        ),
        application_database_path=app_database,
    )

    report = build_report(run_directory=run_directory, application_database_path=app_database)
    assert report["candidates"]["cascade"]["correct_repair_rate"] == 0.5


def test_routed_method_needs_adjusted_component_confidence_to_be_decision_grade(
    tmp_path: Path,
) -> None:
    private = tmp_path / "private"
    app_database = tmp_path / "application-state" / "local-text.sqlite3"
    config = configuration("routed-confidence")
    config["phase"] = "validation"
    config["candidates"] = [
        candidate(
            "router",
            kind="strategy",
            family="evidence_router",
            methods=["lexical", "model"],
        )
    ]
    config["candidates"][0]["ceilings"] = {
        "provider_calls": 30,
        "input_tokens": 30,
        "output_tokens": 30,
        "cost_usd_micros": 30,
    }
    cases = [
        {
            "case_id": f"case-{index}",
            "group_id": f"group-{index}",
            "partition": "validation",
            "eligible": True,
            "synthetic": True,
            "stratum": "conversation" if index < 15 else "command",
            "original": f"Synthetic wrong token {index}.",
            "intended_variants": [f"Synthetic right token {index}."],
            "context": "",
            "profile": [],
        }
        for index in range(30)
    ]
    register_run(
        configuration_path=write_json(private / "configuration.json", config),
        cases_path=write_json(private / "cases.json", cases),
        runs_directory=private / "runs",
        application_database_path=app_database,
    )
    run_directory = private / "runs" / "routed-confidence"

    def wrong_executor(request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(
            outcome="success",
            prepared_text=request.case.original.replace("wrong", "worse"),
            selected_method="lexical",
            repairs=[{"before": "wrong", "after": "worse", "uncertain": False}],
            internal_retries=0,
            latency_ms=40,
            provider_calls=1,
            input_tokens=1,
            output_tokens=1,
            cost_usd_micros=1,
        )

    execute_run(
        run_directory=run_directory,
        executor=wrong_executor,
        application_database_path=app_database,
    )
    mapping = json.loads((run_directory / "blind-map.json").read_text())
    import_adjudications(
        run_directory=run_directory,
        adjudications_path=write_json(
            private / "adjudications.json",
            [{"review_id": row["review_id"], "verdict": "wrong"} for row in mapping],
        ),
        application_database_path=app_database,
    )
    report = build_report(run_directory=run_directory, application_database_path=app_database)
    routed = report["candidates"]["router"]["routed_methods"]["lexical"]

    assert routed["routed_case_count"] == 30
    assert routed["proposed_repair_count"] == 30
    assert routed["gates"]["adjusted_confidence_bounds_pass"] is False
    assert routed["evidence_status"] == "insufficient_evidence"
