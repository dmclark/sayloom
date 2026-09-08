"""Versioned, external-only pipeline for the private correction benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections.abc import Sequence
from itertools import product
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from local_text.config import load_settings

PIPELINE_VERSION = "correction-benchmark-pipeline-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONDITIONS = tuple(
    f"P{int(prompt)}E{int(context)}K{int(knowledge)}"
    for prompt, context, knowledge in product((False, True), repeat=3)
)


class BenchmarkError(RuntimeError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelSnapshot(StrictModel):
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    settings: dict[str, object]


class GateSnapshot(StrictModel):
    require_all_meaning_faithful: Literal[True]
    minimum_win_rate: float = Field(ge=0, le=1)
    maximum_failure_rate: float = Field(ge=0, le=1)


class RunConfiguration(StrictModel):
    pipeline_version: Literal[PIPELINE_VERSION]
    run_id: str = Field(pattern=r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    corpus_version: str = Field(min_length=1, max_length=128)
    arm_order_seed: str = Field(min_length=1, max_length=256)
    model: ModelSnapshot
    prompts: dict[Literal["minimal", "frozen_contract"], str]
    scoring_rubric: dict[str, object]
    gates: GateSnapshot
    practice_contract_revisions: int = Field(ge=0, le=2)

    @field_validator("prompts")
    @classmethod
    def both_prompts_are_frozen(
        cls, value: dict[Literal["minimal", "frozen_contract"], str]
    ) -> dict[Literal["minimal", "frozen_contract"], str]:
        if set(value) != {"minimal", "frozen_contract"} or not all(value.values()):
            raise ValueError("minimal and frozen-contract prompt text are required")
        return value


class BenchmarkCase(StrictModel):
    case_id: str = Field(pattern=r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    set: Literal["practice", "unseen"]
    eligible: bool
    source_text: str = Field(min_length=1, max_length=100_000)
    intended_text: str = Field(min_length=1, max_length=100_000)
    authorized_task_context: str = Field(max_length=100_000)
    curated_knowledge: list[str]


class ExecutionOutput(StrictModel):
    case_id: str
    condition_id: str
    attempt: Literal[1]
    outcome: Literal["success", "failure"]
    output_text: str | None = Field(default=None, max_length=100_000)
    failure_class: str | None = Field(default=None, max_length=128)
    latency_ms: int = Field(ge=0)
    provider_calls: Literal[1]
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd_micros: int = Field(ge=0)

    @model_validator(mode="after")
    def outcome_has_exactly_one_result(self) -> ExecutionOutput:
        if self.outcome == "success" and self.output_text is None:
            raise ValueError("successful execution requires output_text")
        if self.outcome == "failure" and self.failure_class is None:
            raise ValueError("failed execution requires failure_class")
        if self.outcome == "failure" and self.output_text is not None:
            raise ValueError("failed execution cannot include output_text")
        return self


class BlindScore(StrictModel):
    review_id: str
    meaning_faithful: bool
    verdict: Literal["win", "loss", "tie"]
    lexical_repair_spans: int = Field(ge=0)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot read valid JSON from {path.name}") from exc


def _write_new(path: Path, value: object) -> None:
    try:
        with path.open("x") as output:
            json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
        path.chmod(0o600)
    except FileExistsError as exc:
        raise BenchmarkError(f"frozen artifact already exists: {path.name}") from exc


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _external_path(path: Path, application_database_path: Path) -> Path:
    if not path.is_absolute():
        raise BenchmarkError("benchmark paths must be absolute")
    resolved = path.resolve(strict=False)
    if _overlaps(resolved, PROJECT_ROOT.resolve()):
        raise BenchmarkError("benchmark paths must be outside the repository")
    if _overlaps(resolved, application_database_path.resolve(strict=False).parent):
        raise BenchmarkError("benchmark paths must be outside application operating data")
    return resolved


def _validate_cases(value: object) -> list[BenchmarkCase]:
    if not isinstance(value, list) or not value:
        raise BenchmarkError("at least one benchmark case is required")
    cases = _validate_case_records(value)
    if {case.set for case in cases if case.eligible} != {"practice", "unseen"}:
        raise BenchmarkError("benchmark cases must include separate practice and unseen sets")
    return cases


def _validate_case_records(value: object) -> list[BenchmarkCase]:
    if not isinstance(value, list):
        raise BenchmarkError("benchmark cases must be a JSON array")
    try:
        cases = [BenchmarkCase.model_validate(item) for item in value]
    except ValidationError as exc:
        raise BenchmarkError("benchmark cases do not match the pipeline schema") from exc
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise BenchmarkError("benchmark case IDs must be unique")
    return cases


def capture_example(
    *,
    cases_path: Path,
    application_database_path: Path,
    source_text: str,
    intended_text: str,
) -> None:
    """Append one user-confirmed pair as an ineligible practice candidate."""
    cases_path = _external_path(cases_path, application_database_path)
    try:
        cases_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        cases_path.parent.chmod(0o700)
        existing = _validate_case_records(_read_json(cases_path)) if cases_path.exists() else []
        captured = BenchmarkCase(
            case_id=f"captured-{uuid4().hex}",
            set="practice",
            eligible=False,
            source_text=source_text,
            intended_text=intended_text,
            authorized_task_context="",
            curated_knowledge=[],
        )
        value = [case.model_dump(mode="json") for case in (*existing, captured)]
        temporary_path = cases_path.with_name(f".{cases_path.name}.{uuid4().hex}.tmp")
        with temporary_path.open("x") as output:
            json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
        temporary_path.chmod(0o600)
        temporary_path.replace(cases_path)
    except (OSError, ValidationError) as exc:
        if "temporary_path" in locals():
            temporary_path.unlink(missing_ok=True)
        if isinstance(exc, ValidationError):
            raise BenchmarkError("benchmark example does not match the pipeline schema") from exc
        raise BenchmarkError("benchmark example could not be written") from exc


def _condition_order(seed: str, case_id: str) -> list[str]:
    return sorted(CONDITIONS, key=lambda item: _digest(f"{seed}:{case_id}:{item}".encode()))


def register_run(
    *,
    configuration_path: Path,
    cases_path: Path,
    runs_directory: Path,
    application_database_path: Path,
) -> dict[str, object]:
    configuration_path = _external_path(configuration_path, application_database_path)
    cases_path = _external_path(cases_path, application_database_path)
    runs_directory = _external_path(runs_directory, application_database_path)
    try:
        configuration = RunConfiguration.model_validate(_read_json(configuration_path))
    except ValidationError as exc:
        raise BenchmarkError("run configuration does not match the pipeline schema") from exc
    cases = _validate_cases(_read_json(cases_path))
    configuration_value = configuration.model_dump(mode="json")
    cases_value = [case.model_dump(mode="json") for case in cases]
    eligible_cases = [case for case in cases if case.eligible]
    run_directory = runs_directory / configuration.run_id
    try:
        run_directory.mkdir(parents=True, exist_ok=False)
        run_directory.chmod(0o700)
    except FileExistsError as exc:
        raise BenchmarkError("run is already registered and cannot be replaced") from exc
    manifest = {
        "pipeline_version": PIPELINE_VERSION,
        "run_id": configuration.run_id,
        "configuration_sha256": _digest(_canonical(configuration_value)),
        "cases_sha256": _digest(_canonical(cases_value)),
        "case_count": len(cases),
        "eligible_case_count": len(eligible_cases),
        "set_counts": {
            name: sum(case.set == name for case in cases) for name in ("practice", "unseen")
        },
        "condition_ids": list(CONDITIONS),
        "arm_order": {
            case.case_id: _condition_order(configuration.arm_order_seed, case.case_id)
            for case in eligible_cases
        },
    }
    _write_new(run_directory / "configuration.json", configuration_value)
    _write_new(run_directory / "cases.json", cases_value)
    _write_new(run_directory / "manifest.json", manifest)
    return {
        "run_id": configuration.run_id,
        "case_count": len(cases),
        "eligible_case_count": len(eligible_cases),
        "condition_count": len(CONDITIONS),
        "registration_sha256": _digest(_canonical(manifest)),
    }


def _load_run(
    run_directory: Path, application_database_path: Path
) -> tuple[dict[str, object], RunConfiguration, list[BenchmarkCase]]:
    run_directory = _external_path(run_directory, application_database_path)
    manifest = _read_json(run_directory / "manifest.json")
    if not isinstance(manifest, dict):
        raise BenchmarkError("invalid run manifest")
    try:
        configuration = RunConfiguration.model_validate(
            _read_json(run_directory / "configuration.json")
        )
    except ValidationError as exc:
        raise BenchmarkError("frozen run configuration is invalid") from exc
    cases = _validate_cases(_read_json(run_directory / "cases.json"))
    configuration_value = configuration.model_dump(mode="json")
    cases_value = [case.model_dump(mode="json") for case in cases]
    eligible_cases = [case for case in cases if case.eligible]
    if manifest.get("configuration_sha256") != _digest(_canonical(configuration_value)):
        raise BenchmarkError("frozen run configuration changed after registration")
    if manifest.get("cases_sha256") != _digest(_canonical(cases_value)):
        raise BenchmarkError("frozen cases changed after registration")
    expected_metadata = {
        "pipeline_version": PIPELINE_VERSION,
        "run_id": configuration.run_id,
        "case_count": len(cases),
        "eligible_case_count": len(eligible_cases),
        "set_counts": {
            name: sum(case.set == name for case in cases) for name in ("practice", "unseen")
        },
        "condition_ids": list(CONDITIONS),
    }
    if any(manifest.get(key) != value for key, value in expected_metadata.items()):
        raise BenchmarkError("frozen run manifest changed after registration")
    expected_order = {
        case.case_id: _condition_order(configuration.arm_order_seed, case.case_id)
        for case in eligible_cases
    }
    if manifest.get("arm_order") != expected_order:
        raise BenchmarkError("frozen arm order changed after registration")
    return manifest, configuration, cases


def import_outputs(
    *, run_directory: Path, outputs_path: Path, application_database_path: Path
) -> dict[str, object]:
    outputs_path = _external_path(outputs_path, application_database_path)
    manifest, configuration, cases = _load_run(run_directory, application_database_path)
    value = _read_json(outputs_path)
    if not isinstance(value, list):
        raise BenchmarkError("outputs must be a JSON array")
    try:
        outputs = [ExecutionOutput.model_validate(item) for item in value]
    except ValidationError as exc:
        raise BenchmarkError("outputs do not match the pipeline schema") from exc
    expected = [
        (case.case_id, condition_id)
        for case in cases
        if case.eligible
        for condition_id in manifest["arm_order"][case.case_id]
    ]
    actual = [(output.case_id, output.condition_id) for output in outputs]
    if actual != expected:
        raise BenchmarkError("outputs must contain each frozen case-condition once, in arm order")
    run_directory = run_directory.resolve()
    output_values = [output.model_dump(mode="json") for output in outputs]
    _write_new(run_directory / "outputs.json", output_values)
    successful = [output for output in outputs if output.outcome == "success"]
    cases_by_id = {case.case_id: case for case in cases}
    review_rows: list[tuple[str, ExecutionOutput]] = []
    for output in successful:
        review_id = _digest(
            f"{configuration.arm_order_seed}:review:{output.case_id}:{output.condition_id}".encode()
        )[:24]
        review_rows.append((review_id, output))
    review_rows.sort(key=lambda row: _digest(f"blind:{row[0]}".encode()))
    packet = [
        {
            "review_id": review_id,
            "source_text": cases_by_id[output.case_id].source_text,
            "user_confirmed_intended_text": cases_by_id[output.case_id].intended_text,
            "candidate_text": output.output_text,
        }
        for review_id, output in review_rows
    ]
    mapping = [
        {
            "review_id": review_id,
            "case_id": output.case_id,
            "condition_id": output.condition_id,
        }
        for review_id, output in review_rows
    ]
    _write_new(run_directory / "blind-review.json", packet)
    _write_new(run_directory / "blind-map.json", mapping)
    _write_new(
        run_directory / "output-freeze.json",
        {
            "outputs_sha256": _digest(_canonical(output_values)),
            "blind_review_sha256": _digest(_canonical(packet)),
            "blind_map_sha256": _digest(_canonical(mapping)),
        },
    )
    return {
        "output_count": len(outputs),
        "successful_output_count": len(successful),
        "failed_output_count": len(outputs) - len(successful),
        "review_count": len(packet),
    }


def import_scores(
    *, run_directory: Path, scores_path: Path, application_database_path: Path
) -> dict[str, object]:
    scores_path = _external_path(scores_path, application_database_path)
    _load_run(run_directory, application_database_path)
    run_directory = run_directory.resolve()
    outputs = _read_json(run_directory / "outputs.json")
    packet = _read_json(run_directory / "blind-review.json")
    mapping = _read_json(run_directory / "blind-map.json")
    freeze = _read_json(run_directory / "output-freeze.json")
    if not isinstance(freeze, dict) or freeze != {
        "outputs_sha256": _digest(_canonical(outputs)),
        "blind_review_sha256": _digest(_canonical(packet)),
        "blind_map_sha256": _digest(_canonical(mapping)),
    }:
        raise BenchmarkError("frozen outputs or blind-review artifacts changed after import")
    value = _read_json(scores_path)
    if not isinstance(mapping, list) or not isinstance(value, list):
        raise BenchmarkError("blind map and scores must be JSON arrays")
    try:
        scores = [BlindScore.model_validate(item) for item in value]
    except ValidationError as exc:
        raise BenchmarkError("scores do not match the pipeline schema") from exc
    expected_ids = {row["review_id"] for row in mapping}
    actual_ids = [score.review_id for score in scores]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
        raise BenchmarkError("scores must cover every blinded output exactly once")
    score_values = [score.model_dump(mode="json") for score in scores]
    _write_new(run_directory / "scores.json", score_values)
    _write_new(
        run_directory / "score-freeze.json",
        {"scores_sha256": _digest(_canonical(score_values))},
    )
    return {"score_count": len(scores)}


def _condition_report(
    condition_id: str,
    outputs: Sequence[ExecutionOutput],
    scores: Sequence[BlindScore],
) -> dict[str, object]:
    successes = [output for output in outputs if output.outcome == "success"]
    failures = len(outputs) - len(successes)
    wins = sum(score.verdict == "win" for score in scores)
    losses = sum(score.verdict == "loss" for score in scores)
    ties = sum(score.verdict == "tie" for score in scores)
    decisive = wins + losses
    return {
        "condition_id": condition_id,
        "executions": len(outputs),
        "successes": len(successes),
        "failures": failures,
        "meaning_fidelity_failures": sum(not score.meaning_faithful for score in scores),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_rate": wins / decisive if decisive else 0.0,
        "lexical_repair_spans": sum(score.lexical_repair_spans for score in scores),
        "mean_latency_ms": (
            statistics.fmean(output.latency_ms for output in outputs) if outputs else 0.0
        ),
        "provider_calls": sum(output.provider_calls for output in outputs),
        "input_tokens": sum(output.input_tokens for output in outputs),
        "output_tokens": sum(output.output_tokens for output in outputs),
        "cost_usd_micros": sum(output.cost_usd_micros for output in outputs),
    }


def _summary(condition_reports: Sequence[dict[str, object]]) -> dict[str, object]:
    execution_count = sum(int(report["executions"]) for report in condition_reports)
    failure_count = sum(int(report["failures"]) for report in condition_reports)
    fidelity_failures = sum(
        int(report["meaning_fidelity_failures"]) for report in condition_reports
    )
    wins = sum(int(report["wins"]) for report in condition_reports)
    losses = sum(int(report["losses"]) for report in condition_reports)
    decisive = wins + losses
    return {
        "execution_count": execution_count,
        "failure_count": failure_count,
        "meaning_fidelity_failures": fidelity_failures,
        "win_rate": wins / decisive if decisive else 0.0,
        "failure_rate": failure_count / execution_count if execution_count else 0.0,
    }


def build_report(*, run_directory: Path, application_database_path: Path) -> dict[str, object]:
    _manifest, configuration, cases = _load_run(run_directory, application_database_path)
    run_directory = run_directory.resolve()
    outputs_value = _read_json(run_directory / "outputs.json")
    packet_value = _read_json(run_directory / "blind-review.json")
    mapping_value = _read_json(run_directory / "blind-map.json")
    output_freeze = _read_json(run_directory / "output-freeze.json")
    scores_value = _read_json(run_directory / "scores.json")
    score_freeze = _read_json(run_directory / "score-freeze.json")
    if not isinstance(output_freeze, dict) or output_freeze != {
        "outputs_sha256": _digest(_canonical(outputs_value)),
        "blind_review_sha256": _digest(_canonical(packet_value)),
        "blind_map_sha256": _digest(_canonical(mapping_value)),
    }:
        raise BenchmarkError("frozen outputs or blind-review artifacts changed after import")
    if not isinstance(score_freeze, dict) or score_freeze != {
        "scores_sha256": _digest(_canonical(scores_value))
    }:
        raise BenchmarkError("frozen scores changed after import")
    try:
        outputs = [ExecutionOutput.model_validate(item) for item in outputs_value]
        scores = [BlindScore.model_validate(item) for item in scores_value]
    except (ValidationError, TypeError) as exc:
        raise BenchmarkError("run outputs or scores are invalid") from exc
    if not isinstance(mapping_value, list):
        raise BenchmarkError("blind map is invalid")
    mapping = {row["review_id"]: row for row in mapping_value}
    case_sets = {case.case_id: case.set for case in cases}
    scores_by_condition: dict[str, list[BlindScore]] = {condition: [] for condition in CONDITIONS}
    for score in scores:
        scores_by_condition[mapping[score.review_id]["condition_id"]].append(score)
    condition_reports = [
        _condition_report(
            condition,
            [output for output in outputs if output.condition_id == condition],
            scores_by_condition[condition],
        )
        for condition in CONDITIONS
    ]
    set_reports: dict[str, dict[str, object]] = {}
    for set_name in ("practice", "unseen"):
        set_outputs = [output for output in outputs if case_sets[output.case_id] == set_name]
        set_scores_by_condition = {
            condition: [
                score
                for score in scores_by_condition[condition]
                if case_sets[mapping[score.review_id]["case_id"]] == set_name
            ]
            for condition in CONDITIONS
        }
        reports = [
            _condition_report(
                condition,
                [output for output in set_outputs if output.condition_id == condition],
                set_scores_by_condition[condition],
            )
            for condition in CONDITIONS
        ]
        set_reports[set_name] = {"summary": _summary(reports), "conditions": reports}
    gate_summary = set_reports["unseen"]["summary"]
    gate_checks = {
        "meaning_fidelity": gate_summary["meaning_fidelity_failures"] == 0,
        "minimum_win_rate": gate_summary["win_rate"] >= configuration.gates.minimum_win_rate,
        "maximum_failure_rate": (
            gate_summary["failure_rate"] <= configuration.gates.maximum_failure_rate
        ),
    }
    summary = _summary(condition_reports)
    report = {
        "pipeline_version": PIPELINE_VERSION,
        "corpus_version": configuration.corpus_version,
        "case_count": sum(case.eligible for case in cases),
        "condition_count": len(CONDITIONS),
        **summary,
        "conditions": condition_reports,
        "sets": set_reports,
        "gate": {
            "scope": "unseen",
            "passed": all(gate_checks.values()),
            "checks": gate_checks,
        },
    }
    _write_new(run_directory / "aggregate-report.json", report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="correction-benchmark")
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register")
    register.add_argument("--configuration", type=Path, required=True)
    register.add_argument("--cases", type=Path, required=True)
    register.add_argument("--runs-directory", type=Path, required=True)
    for name, option in (("import-outputs", "outputs"), ("import-scores", "scores")):
        command = commands.add_parser(name)
        command.add_argument("--run-directory", type=Path, required=True)
        command.add_argument(f"--{option}", type=Path, required=True)
    report = commands.add_parser("report")
    report.add_argument("--run-directory", type=Path, required=True)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    application_database_path = load_settings().resolved_database_path
    if args.command == "register":
        return register_run(
            configuration_path=args.configuration,
            cases_path=args.cases,
            runs_directory=args.runs_directory,
            application_database_path=application_database_path,
        )
    if args.command == "import-outputs":
        return import_outputs(
            run_directory=args.run_directory,
            outputs_path=args.outputs,
            application_database_path=application_database_path,
        )
    if args.command == "import-scores":
        return import_scores(
            run_directory=args.run_directory,
            scores_path=args.scores,
            application_database_path=application_database_path,
        )
    return build_report(
        run_directory=args.run_directory,
        application_database_path=application_database_path,
    )


def main() -> None:
    try:
        print(json.dumps(_run(_parser().parse_args()), indent=2, sort_keys=True))
    except BenchmarkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
