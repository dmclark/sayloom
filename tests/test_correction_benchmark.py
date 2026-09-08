import json
import stat
from pathlib import Path

import pytest

from local_text.correction_benchmark import (
    CONDITIONS,
    PIPELINE_VERSION,
    BenchmarkError,
    build_report,
    capture_example,
    import_outputs,
    import_scores,
    register_run,
)


def write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def configuration(run_id: str = "synthetic-proof") -> dict[str, object]:
    return {
        "pipeline_version": PIPELINE_VERSION,
        "run_id": run_id,
        "corpus_version": "synthetic-corpus-v1",
        "arm_order_seed": "synthetic-frozen-seed",
        "model": {
            "provider": "synthetic-provider",
            "model": "synthetic-model",
            "settings": {"temperature": 0},
        },
        "prompts": {
            "minimal": "Synthetic minimal prompt.",
            "frozen_contract": "Synthetic frozen contract prompt.",
        },
        "scoring_rubric": {
            "meaning_fidelity": "Candidate preserves the user-confirmed intended meaning.",
            "preference": ["win", "loss", "tie"],
        },
        "gates": {
            "require_all_meaning_faithful": True,
            "minimum_win_rate": 0.5,
            "maximum_failure_rate": 0,
        },
        "practice_contract_revisions": 2,
    }


def synthetic_cases() -> list[dict[str, object]]:
    return [
        {
            "case_id": f"synthetic-{index:02}",
            "set": "practice" if index < 3 else "unseen",
            "eligible": True,
            "source_text": f"Synthetic source {index}.",
            "intended_text": f"Synthetic intended {index}.",
            "authorized_task_context": f"Synthetic context {index}.",
            "curated_knowledge": [f"synthetic-term-{index}"],
        }
        for index in range(10)
    ]


def register_synthetic_run(tmp_path: Path) -> tuple[Path, Path]:
    private = tmp_path / "private"
    app_database = tmp_path / "application-state" / "local-text.sqlite3"
    result = register_run(
        configuration_path=write_json(private / "configuration.json", configuration()),
        cases_path=write_json(private / "cases.json", synthetic_cases()),
        runs_directory=private / "runs",
        application_database_path=app_database,
    )
    assert result["case_count"] == 10
    assert result["eligible_case_count"] == 10
    assert result["condition_count"] == 8
    return private / "runs" / "synthetic-proof", app_database


def synthetic_outputs(run_directory: Path) -> list[dict[str, object]]:
    manifest = json.loads((run_directory / "manifest.json").read_text())
    return [
        {
            "case_id": case["case_id"],
            "condition_id": condition_id,
            "attempt": 1,
            "outcome": "success",
            "output_text": f"Synthetic candidate for {case['case_id']}.",
            "latency_ms": 10,
            "provider_calls": 1,
            "input_tokens": 12,
            "output_tokens": 6,
            "cost_usd_micros": 3,
        }
        for case in synthetic_cases()
        for condition_id in manifest["arm_order"][case["case_id"]]
    ]


def test_ten_case_pipeline_freezes_orders_blinds_scores_and_reports(tmp_path: Path) -> None:
    run_directory, app_database = register_synthetic_run(tmp_path)
    first_manifest = json.loads((run_directory / "manifest.json").read_text())
    assert first_manifest["set_counts"] == {"practice": 3, "unseen": 7}
    assert sorted(first_manifest["condition_ids"]) == [
        "P0E0K0",
        "P0E0K1",
        "P0E1K0",
        "P0E1K1",
        "P1E0K0",
        "P1E0K1",
        "P1E1K0",
        "P1E1K1",
    ]
    assert stat.S_IMODE(run_directory.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in run_directory.iterdir())
    assert all(
        sorted(order) == sorted(CONDITIONS) for order in first_manifest["arm_order"].values()
    )
    assert len({tuple(order) for order in first_manifest["arm_order"].values()}) > 1

    second_private = tmp_path / "second-private"
    register_run(
        configuration_path=write_json(
            second_private / "configuration.json", configuration("second")
        ),
        cases_path=write_json(second_private / "cases.json", synthetic_cases()),
        runs_directory=second_private / "runs",
        application_database_path=app_database,
    )
    second_manifest = json.loads((second_private / "runs" / "second" / "manifest.json").read_text())
    assert first_manifest["arm_order"] == second_manifest["arm_order"]

    outputs_path = write_json(
        tmp_path / "private" / "outputs-import.json", synthetic_outputs(run_directory)
    )
    imported = import_outputs(
        run_directory=run_directory,
        outputs_path=outputs_path,
        application_database_path=app_database,
    )
    assert imported == {
        "output_count": 80,
        "successful_output_count": 80,
        "failed_output_count": 0,
        "review_count": 80,
    }
    packet = json.loads((run_directory / "blind-review.json").read_text())
    assert len(packet) == 80
    assert not ({"case_id", "condition_id"} & packet[0].keys())
    assert "user_confirmed_intended_text" in packet[0]

    scores = [
        {
            "review_id": row["review_id"],
            "meaning_faithful": True,
            "verdict": "win",
            "lexical_repair_spans": 1,
        }
        for row in packet
    ]
    imported_scores = import_scores(
        run_directory=run_directory,
        scores_path=write_json(tmp_path / "private" / "scores-import.json", scores),
        application_database_path=app_database,
    )
    assert imported_scores == {"score_count": 80}
    report = build_report(run_directory=run_directory, application_database_path=app_database)
    assert report["gate"] == {
        "scope": "unseen",
        "passed": True,
        "checks": {
            "meaning_fidelity": True,
            "minimum_win_rate": True,
            "maximum_failure_rate": True,
        },
    }
    assert report["case_count"] == 10
    assert report["execution_count"] == 80
    assert all(condition["provider_calls"] == 10 for condition in report["conditions"])
    serialized = json.dumps(report)
    for case in synthetic_cases():
        assert case["case_id"] not in serialized
        assert case["source_text"] not in serialized
        assert case["intended_text"] not in serialized


def test_pipeline_rejects_retries_cherry_picking_and_frozen_input_changes(tmp_path: Path) -> None:
    run_directory, app_database = register_synthetic_run(tmp_path)
    outputs = synthetic_outputs(run_directory)
    outputs.pop()
    with pytest.raises(BenchmarkError, match="each frozen case-condition once"):
        import_outputs(
            run_directory=run_directory,
            outputs_path=write_json(tmp_path / "private" / "incomplete.json", outputs),
            application_database_path=app_database,
        )

    outputs = synthetic_outputs(run_directory)
    outputs[0]["attempt"] = 2
    with pytest.raises(BenchmarkError, match="outputs do not match"):
        import_outputs(
            run_directory=run_directory,
            outputs_path=write_json(tmp_path / "private" / "retry.json", outputs),
            application_database_path=app_database,
        )

    frozen_cases = json.loads((run_directory / "cases.json").read_text())
    frozen_cases[0]["source_text"] = "Changed after registration."
    (run_directory / "cases.json").write_text(json.dumps(frozen_cases))
    with pytest.raises(BenchmarkError, match="changed after registration"):
        import_outputs(
            run_directory=run_directory,
            outputs_path=write_json(
                tmp_path / "private" / "complete.json", synthetic_outputs(run_directory)
            ),
            application_database_path=app_database,
        )


def test_one_unfaithful_blind_score_hard_fails_gate(tmp_path: Path) -> None:
    run_directory, app_database = register_synthetic_run(tmp_path)
    import_outputs(
        run_directory=run_directory,
        outputs_path=write_json(
            tmp_path / "private" / "outputs-import.json", synthetic_outputs(run_directory)
        ),
        application_database_path=app_database,
    )
    packet = json.loads((run_directory / "blind-review.json").read_text())
    mapping = json.loads((run_directory / "blind-map.json").read_text())
    unseen_review_id = next(row["review_id"] for row in mapping if row["case_id"] == "synthetic-03")
    scores = [
        {
            "review_id": row["review_id"],
            "meaning_faithful": row["review_id"] != unseen_review_id,
            "verdict": "win",
            "lexical_repair_spans": 1,
        }
        for row in packet
    ]
    import_scores(
        run_directory=run_directory,
        scores_path=write_json(tmp_path / "private" / "scores-import.json", scores),
        application_database_path=app_database,
    )
    report = build_report(run_directory=run_directory, application_database_path=app_database)
    assert report["meaning_fidelity_failures"] == 1
    assert report["sets"]["practice"]["summary"]["meaning_fidelity_failures"] == 0
    assert report["sets"]["unseen"]["summary"]["meaning_fidelity_failures"] == 1
    assert report["gate"]["scope"] == "unseen"
    assert report["gate"]["checks"]["meaning_fidelity"] is False
    assert report["gate"]["checks"]["minimum_win_rate"] is True
    assert report["gate"]["passed"] is False


def test_pipeline_rejects_repository_and_application_state_paths(tmp_path: Path) -> None:
    app_database = tmp_path / "application-state" / "local-text.sqlite3"
    private = tmp_path / "private"
    with pytest.raises(BenchmarkError, match="repository"):
        register_run(
            configuration_path=Path(__file__),
            cases_path=write_json(private / "cases.json", synthetic_cases()),
            runs_directory=private / "runs",
            application_database_path=app_database,
        )
    with pytest.raises(BenchmarkError, match="operating data"):
        register_run(
            configuration_path=write_json(private / "configuration.json", configuration()),
            cases_path=write_json(private / "cases.json", synthetic_cases()),
            runs_directory=app_database.parent / "benchmark-runs",
            application_database_path=app_database,
        )

    invalid_configuration = configuration("too-many-practice-revisions")
    invalid_configuration["practice_contract_revisions"] = 3
    with pytest.raises(BenchmarkError, match="configuration does not match"):
        register_run(
            configuration_path=write_json(
                private / "invalid-configuration.json", invalid_configuration
            ),
            cases_path=write_json(private / "valid-cases.json", synthetic_cases()),
            runs_directory=private / "other-runs",
            application_database_path=app_database,
        )


def test_capture_example_writes_exact_pair_through_benchmark_schema(tmp_path: Path) -> None:
    app_database = tmp_path / "application-state" / "local-text.sqlite3"
    cases_path = tmp_path / "private" / "candidate-cases.json"

    capture_example(
        cases_path=cases_path,
        application_database_path=app_database,
        source_text="Synthetic source wording.",
        intended_text="Synthetic intended wording.",
    )

    assert stat.S_IMODE(cases_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(cases_path.stat().st_mode) == 0o600
    saved = json.loads(cases_path.read_text())
    assert len(saved) == 1
    assert saved[0].pop("case_id").startswith("captured-")
    assert saved == [{
        "authorized_task_context": "",
        "curated_knowledge": [],
        "eligible": False,
        "intended_text": "Synthetic intended wording.",
        "set": "practice",
        "source_text": "Synthetic source wording.",
    }]


@pytest.mark.parametrize("path_kind", ["repository", "application-state"])
def test_capture_example_rejects_non_external_paths(tmp_path: Path, path_kind: str) -> None:
    app_database = tmp_path / "application-state" / "local-text.sqlite3"
    cases_path = (
        Path(__file__).parent / "candidate-cases.json"
        if path_kind == "repository"
        else app_database.parent / "candidate-cases.json"
    )

    with pytest.raises(BenchmarkError, match="repository|operating data"):
        capture_example(
            cases_path=cases_path,
            application_database_path=app_database,
            source_text="Synthetic source wording.",
            intended_text="Synthetic intended wording.",
        )

    assert not cases_path.exists()
