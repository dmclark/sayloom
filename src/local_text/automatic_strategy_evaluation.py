"""Frozen, external-only harness for automatic correction strategy evaluation."""

from __future__ import annotations

import hashlib
import json
import re
import signal
import time
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

PIPELINE_VERSION = "automatic-strategy-evaluation-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_STOP_CONDITIONS = {
    "privacy_failure",
    "answer_leakage",
    "corpus_drift",
    "unplanned_candidate_change",
    "ceiling_exceeded",
}
METRIC_NAMES = (
    "editing_reduction",
    "correct_repair_rate",
    "preservation",
    "usable",
    "within_ten_seconds",
)


class EvaluationError(RuntimeError):
    pass


class _ExecutorTimeout(RuntimeError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderSnapshot(StrictModel):
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    settings: dict[str, object]


class Ceilings(StrictModel):
    provider_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd_micros: int = Field(ge=0)


class Candidate(StrictModel):
    candidate_id: str = Field(pattern=r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    kind: Literal["component", "strategy", "ablation"]
    family: str = Field(min_length=1, max_length=128)
    method_ids: list[str] = Field(min_length=1)
    executor: str = Field(min_length=1, max_length=128)
    provider: ProviderSnapshot
    prompt: str = Field(min_length=1, max_length=100_000)
    routing: dict[str, object]
    maximum_internal_retries: int = Field(ge=0, le=10)
    ceilings: Ceilings
    ablation_of: str | None = None

    @model_validator(mode="after")
    def methods_match_candidate_kind(self) -> Candidate:
        if self.kind == "component" and len(self.method_ids) != 1:
            raise ValueError("a component candidate must contain exactly one correction method")
        if self.kind in {"strategy", "ablation"} and len(self.method_ids) < 2:
            raise ValueError("an Automatic correction strategy must contain multiple methods")
        if self.kind == "ablation" and not self.ablation_of:
            raise ValueError("an ablation must identify its preregistered parent strategy")
        return self


class PrivacySnapshot(StrictModel):
    storage: Literal["user-controlled-external"]
    provider_data_use: str = Field(min_length=1, max_length=512)
    private_text_in_git: Literal[False]
    private_text_in_logs: Literal[False]
    private_text_in_application_state: Literal[False]


class ApprovalSnapshot(StrictModel):
    provider_calls: bool
    private_data: bool
    spending: bool


class RunConfiguration(StrictModel):
    pipeline_version: Literal[PIPELINE_VERSION]
    run_id: str = Field(pattern=r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    protocol_version: str = Field(min_length=1, max_length=128)
    software_version: str = Field(min_length=1, max_length=256)
    phase: Literal["development", "validation", "heldout"]
    synthetic_validation: bool
    schedule_seed: str = Field(min_length=1, max_length=256)
    bootstrap_seed: str = Field(min_length=1, max_length=256)
    bootstrap_resamples: int = Field(ge=100, le=100_000)
    required_strata: list[str] = Field(min_length=1)
    stratum_weights: dict[str, float]
    candidates: list[Candidate] = Field(min_length=1)
    privacy: PrivacySnapshot
    approvals: ApprovalSnapshot
    stop_conditions: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def protocol_invariants_are_frozen(self) -> RunConfiguration:
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate IDs must be unique")
        known = set(candidate_ids)
        if any(
            candidate.ablation_of not in known
            for candidate in self.candidates
            if candidate.ablation_of is not None
        ):
            raise ValueError("an ablation parent must be a preregistered candidate")
        if set(self.required_strata) != set(self.stratum_weights):
            raise ValueError("required strata and stratum weights must match")
        if abs(sum(self.stratum_weights.values()) - 1.0) > 1e-9 or any(
            weight <= 0 for weight in self.stratum_weights.values()
        ):
            raise ValueError("stratum weights must be positive and sum to one")
        if not REQUIRED_STOP_CONDITIONS.issubset(self.stop_conditions):
            raise ValueError("all required protocol stop conditions must be frozen")
        if self.phase == "heldout":
            strategies = [
                candidate for candidate in self.candidates if candidate.kind == "strategy"
            ]
            if len(strategies) > 3:
                raise ValueError("held-out evaluation permits at most three complete strategies")
            if any(candidate.kind == "component" for candidate in self.candidates):
                raise ValueError(
                    "held-out execution contains strategies and preregistered ablations only"
                )
        if not self.synthetic_validation and not all(self.approvals.model_dump().values()):
            raise ValueError("non-synthetic registration requires explicit owner approvals")
        return self


class EvaluationCase(StrictModel):
    case_id: str = Field(pattern=r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    group_id: str = Field(pattern=r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    partition: Literal["development", "validation", "heldout"]
    eligible: bool
    synthetic: bool
    stratum: str = Field(min_length=1, max_length=128)
    original: str = Field(min_length=1, max_length=100_000)
    intended_variants: list[str] = Field(min_length=1)
    context: str = Field(max_length=100_000)
    profile: list[str]

    @field_validator("intended_variants")
    @classmethod
    def intended_variants_are_nonempty(cls, value: list[str]) -> list[str]:
        if not all(value):
            raise ValueError("Intended text variants cannot be empty")
        return value


class RepairTrace(StrictModel):
    before: str = Field(max_length=100_000)
    after: str = Field(max_length=100_000)
    uncertain: bool


class ExecutionResult(StrictModel):
    outcome: Literal["success", "abstention", "failure"]
    prepared_text: str | None = Field(default=None, max_length=100_000)
    selected_method: str | None = Field(default=None, max_length=128)
    repairs: list[RepairTrace]
    internal_retries: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    provider_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd_micros: int = Field(ge=0)

    @model_validator(mode="after")
    def result_is_complete_and_reviewable(self) -> ExecutionResult:
        if self.outcome == "success" and (
            self.prepared_text is None or self.selected_method is None
        ):
            raise ValueError("a successful result requires Prepared and its selected method")
        if self.outcome != "success" and (
            self.prepared_text is not None or self.selected_method is not None or self.repairs
        ):
            raise ValueError("a failure or abstention must fail open without proposed repairs")
        return self


class ExecutionRequest:
    """Frozen input supplied to a candidate executor adapter."""

    def __init__(
        self,
        *,
        job_id: str,
        seed: str,
        candidate: Candidate,
        case: EvaluationCase,
        timeout_seconds: int = 30,
    ) -> None:
        self.job_id = job_id
        self.seed = seed
        self.candidate = candidate
        self.case = case
        self.timeout_seconds = timeout_seconds


class BlindAdjudication(StrictModel):
    review_id: str = Field(pattern=r"[a-f0-9]{24}")
    verdict: Literal["correct", "wrong", "equivalent"]


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"cannot read valid JSON from {path.name}") from exc


def _write_new(path: Path, value: object) -> None:
    try:
        with path.open("x") as output:
            json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
        path.chmod(0o600)
    except FileExistsError as exc:
        raise EvaluationError(f"frozen artifact already exists: {path.name}") from exc


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _external_path(path: Path, application_database_path: Path) -> Path:
    if not path.is_absolute():
        raise EvaluationError("evaluation paths must be absolute")
    resolved = path.resolve(strict=False)
    if _overlaps(resolved, PROJECT_ROOT.resolve()):
        raise EvaluationError("evaluation paths must be outside the repository")
    if _overlaps(resolved, application_database_path.resolve(strict=False).parent):
        raise EvaluationError("evaluation paths must be outside application operating data")
    return resolved


def _validated_cases(value: object, configuration: RunConfiguration) -> list[EvaluationCase]:
    if not isinstance(value, list) or not value:
        raise EvaluationError("at least one evaluation case is required")
    try:
        cases = [EvaluationCase.model_validate(item) for item in value]
    except ValidationError as exc:
        raise EvaluationError("evaluation cases do not match the pipeline schema") from exc
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise EvaluationError("evaluation case IDs must be unique")
    if any(case.partition != configuration.phase for case in cases):
        raise EvaluationError("every case must belong to the registered evaluation phase")
    if any(case.stratum not in configuration.required_strata for case in cases if case.eligible):
        raise EvaluationError("eligible cases contain an unregistered stratum")
    represented = {case.stratum for case in cases if case.eligible}
    if represented != set(configuration.required_strata):
        raise EvaluationError("eligible cases must represent every required stratum")
    if configuration.synthetic_validation:
        if any(not case.synthetic for case in cases):
            raise EvaluationError("synthetic harness validation cannot contain private cases")
    else:
        if any(case.synthetic for case in cases):
            raise EvaluationError("an evidence run cannot contain synthetic cases")
        if configuration.phase == "heldout" and sum(case.eligible for case in cases) < 200:
            raise EvaluationError("held-out acceptance requires at least 200 eligible cases")
    return cases


def _schedule(
    configuration: RunConfiguration, cases: list[EvaluationCase]
) -> list[dict[str, object]]:
    repetitions = 3 if configuration.phase == "development" else 1
    candidates = configuration.candidates
    rows: list[dict[str, object]] = []
    for repetition in range(1, repetitions + 1):
        case_order = sorted(
            (case for case in cases if case.eligible),
            key=lambda case: _digest(
                f"{configuration.schedule_seed}:case:{repetition}:{case.case_id}".encode()
            ),
        )
        for block, case in enumerate(case_order, start=1):
            candidate_order = sorted(
                candidates,
                key=lambda candidate: _digest(
                    (
                        f"{configuration.schedule_seed}:candidate:{repetition}:"
                        f"{case.case_id}:{candidate.candidate_id}"
                    ).encode()
                ),
            )
            rows.extend(
                {
                    "job_id": _digest(
                        f"{configuration.run_id}:{repetition}:{case.case_id}:{candidate.candidate_id}".encode()
                    )[:24],
                    "block": block,
                    "repetition": repetition,
                    "case_id": case.case_id,
                    "candidate_id": candidate.candidate_id,
                    "seed": _digest(
                        f"{configuration.schedule_seed}:attempt:{repetition}:{case.case_id}:{candidate.candidate_id}".encode()
                    ),
                }
                for candidate in candidate_order
            )
    return rows


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
        raise EvaluationError("run configuration does not match the pipeline schema") from exc
    cases = _validated_cases(_read_json(cases_path), configuration)
    configuration_value = configuration.model_dump(mode="json")
    cases_value = [case.model_dump(mode="json") for case in cases]
    schedule = _schedule(configuration, cases)
    run_directory = runs_directory / configuration.run_id
    try:
        run_directory.mkdir(parents=True, exist_ok=False)
        run_directory.chmod(0o700)
    except FileExistsError as exc:
        raise EvaluationError("run is already registered and cannot be replaced") from exc
    repetitions = 3 if configuration.phase == "development" else 1
    manifest = {
        "pipeline_version": PIPELINE_VERSION,
        "protocol_version": configuration.protocol_version,
        "software_version": configuration.software_version,
        "run_id": configuration.run_id,
        "phase": configuration.phase,
        "synthetic_validation": configuration.synthetic_validation,
        "configuration_sha256": _digest(_canonical(configuration_value)),
        "cases_sha256": _digest(_canonical(cases_value)),
        "schedule_sha256": _digest(_canonical(schedule)),
        "candidate_ids": [candidate.candidate_id for candidate in configuration.candidates],
        "candidate_sha256": {
            candidate.candidate_id: _digest(_canonical(candidate.model_dump(mode="json")))
            for candidate in configuration.candidates
        },
        "candidates": [candidate.model_dump(mode="json") for candidate in configuration.candidates],
        "worst_case_totals": {
            name: sum(getattr(candidate.ceilings, name) for candidate in configuration.candidates)
            for name in Ceilings.model_fields
        },
        "eligible_case_count": sum(case.eligible for case in cases),
        "stratum_counts": dict(Counter(case.stratum for case in cases if case.eligible)),
        "repetitions_per_case": repetitions,
        "scheduled_attempt_count": len(schedule),
        "privacy": configuration.privacy.model_dump(mode="json"),
        "approval_review": {
            **configuration.approvals.model_dump(mode="json"),
            "required_before_non_synthetic_execution": True,
        },
        "stop_conditions": configuration.stop_conditions,
    }
    _write_new(run_directory / "configuration.json", configuration_value)
    _write_new(run_directory / "cases.json", cases_value)
    _write_new(run_directory / "schedule.json", schedule)
    _write_new(run_directory / "manifest.json", manifest)
    return {
        "run_id": configuration.run_id,
        "candidate_count": len(configuration.candidates),
        "eligible_case_count": manifest["eligible_case_count"],
        "scheduled_attempt_count": len(schedule),
        "approval_required": configuration.synthetic_validation,
        "registration_sha256": _digest(_canonical(manifest)),
    }


def _load_run(
    run_directory: Path, application_database_path: Path
) -> tuple[dict[str, object], RunConfiguration, list[EvaluationCase], list[dict[str, object]]]:
    run_directory = _external_path(run_directory, application_database_path)
    manifest = _read_json(run_directory / "manifest.json")
    try:
        configuration = RunConfiguration.model_validate(
            _read_json(run_directory / "configuration.json")
        )
    except ValidationError as exc:
        raise EvaluationError("frozen run configuration is invalid") from exc
    cases = _validated_cases(_read_json(run_directory / "cases.json"), configuration)
    schedule = _read_json(run_directory / "schedule.json")
    if not isinstance(manifest, dict) or not isinstance(schedule, list):
        raise EvaluationError("frozen run manifest or schedule is invalid")
    configuration_value = configuration.model_dump(mode="json")
    cases_value = [case.model_dump(mode="json") for case in cases]
    checks = {
        "configuration_sha256": _digest(_canonical(configuration_value)),
        "cases_sha256": _digest(_canonical(cases_value)),
        "schedule_sha256": _digest(_canonical(schedule)),
    }
    if any(manifest.get(name) != digest for name, digest in checks.items()):
        raise EvaluationError("a frozen registration artifact changed after registration")
    if schedule != _schedule(configuration, cases):
        raise EvaluationError("the frozen execution schedule changed after registration")
    return manifest, configuration, cases, schedule


def _exceeds(used: Counter[str], ceilings: Ceilings) -> bool:
    return any(used[name] > value for name, value in ceilings.model_dump().items())


def _invoke_executor(
    executor: Callable[[ExecutionRequest], ExecutionResult], request: ExecutionRequest
) -> ExecutionResult:
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()

    def timeout_handler(_signum: int, _frame: object) -> None:
        raise _ExecutorTimeout

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, request.timeout_seconds)
    try:
        return executor(request)
    finally:
        elapsed = time.monotonic() - started
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] or previous_timer[1]:
            signal.setitimer(
                signal.ITIMER_REAL,
                max(0.000001, previous_timer[0] - elapsed),
                previous_timer[1],
            )


def _failed_result(*, latency_ms: int) -> ExecutionResult:
    return ExecutionResult(
        outcome="failure",
        prepared_text=None,
        selected_method=None,
        repairs=[],
        internal_retries=0,
        latency_ms=latency_ms,
        provider_calls=0,
        input_tokens=0,
        output_tokens=0,
        cost_usd_micros=0,
    )


def execute_run(
    *,
    run_directory: Path,
    executor: Callable[[ExecutionRequest], ExecutionResult],
    application_database_path: Path,
) -> dict[str, object]:
    manifest, configuration, cases, schedule = _load_run(
        run_directory, application_database_path
    )
    if not configuration.synthetic_validation and not all(
        configuration.approvals.model_dump().values()
    ):
        raise EvaluationError("non-synthetic execution requires explicit owner approvals")
    cases_by_id = {case.case_id: case for case in cases}
    candidates = {candidate.candidate_id: candidate for candidate in configuration.candidates}
    usage = {candidate_id: Counter() for candidate_id in candidates}
    stopped: set[str] = set()
    rows: list[dict[str, object]] = []
    review_rows: list[
        tuple[str, dict[str, object], EvaluationCase, int, RepairTrace]
    ] = []
    for job in schedule:
        candidate = candidates[str(job["candidate_id"])]
        case = cases_by_id[str(job["case_id"])]
        if candidate.candidate_id in stopped:
            result = _failed_result(latency_ms=0)
            failure_class = "branch_stopped"
        else:
            started = time.monotonic()
            try:
                result = ExecutionResult.model_validate(
                    _invoke_executor(
                        executor,
                        ExecutionRequest(
                            job_id=str(job["job_id"]),
                            seed=str(job["seed"]),
                            candidate=candidate,
                            case=case,
                        )
                    )
                )
            except _ExecutorTimeout:
                result = _failed_result(latency_ms=30_000)
                failure_class = "timeout"
            except Exception:
                result = _failed_result(
                    latency_ms=max(0, int((time.monotonic() - started) * 1000))
                )
                failure_class = "executor_exception"
            else:
                failure_class = None
                if (
                    result.selected_method not in candidate.method_ids
                    and result.outcome == "success"
                ):
                    failure_class = "unregistered_route"
                elif result.internal_retries > candidate.maximum_internal_retries:
                    failure_class = "retry_ceiling_exceeded"
                elif result.latency_ms >= 30_000:
                    failure_class = "timeout"
            for name in ("provider_calls", "input_tokens", "output_tokens", "cost_usd_micros"):
                usage[candidate.candidate_id][name] += int(getattr(result, name))
            if _exceeds(usage[candidate.candidate_id], candidate.ceilings):
                failure_class = "ceiling_exceeded"
                stopped.add(candidate.candidate_id)
            if failure_class:
                result = result.model_copy(
                    update={
                        "outcome": "failure",
                        "prepared_text": None,
                        "selected_method": None,
                        "repairs": [],
                    }
                )
        row = {
            **job,
            **result.model_dump(mode="json"),
            "failure_class": failure_class,
            "fail_open_to_original": result.outcome != "success",
        }
        rows.append(row)
        if (
            result.outcome == "success"
            and result.prepared_text not in case.intended_variants
            and result.prepared_text != case.original
        ):
            for repair_index, repair in enumerate(result.repairs):
                review_id = _digest(
                    (
                        f"{configuration.schedule_seed}:review:"
                        f"{job['job_id']}:{repair_index}"
                    ).encode()
                )[:24]
                review_rows.append((review_id, row, case, repair_index, repair))
    review_rows.sort(key=lambda item: _digest(f"blind:{item[0]}".encode()))
    packet = [
        {
            "review_id": review_id,
            "original": case.original,
            "intended_variants": case.intended_variants,
            "candidate_text": row["prepared_text"],
            "repair": repair.model_dump(mode="json"),
        }
        for review_id, row, case, _repair_index, repair in review_rows
    ]
    mapping = [
        {
            "review_id": review_id,
            "job_id": row["job_id"],
            "case_id": row["case_id"],
            "candidate_id": row["candidate_id"],
            "repair_index": repair_index,
        }
        for review_id, row, _case, repair_index, _repair in review_rows
    ]
    run_directory = run_directory.resolve()
    _write_new(run_directory / "executions.json", rows)
    _write_new(run_directory / "blind-review.json", packet)
    _write_new(run_directory / "blind-map.json", mapping)
    _write_new(
        run_directory / "execution-freeze.json",
        {
            "manifest_sha256": _digest(_canonical(manifest)),
            "executions_sha256": _digest(_canonical(rows)),
            "blind_review_sha256": _digest(_canonical(packet)),
            "blind_map_sha256": _digest(_canonical(mapping)),
        },
    )
    failures = sum(row["outcome"] == "failure" for row in rows)
    abstentions = sum(row["outcome"] == "abstention" for row in rows)
    return {
        "scheduled_attempt_count": len(schedule),
        "completed_attempt_count": len(rows),
        "failed_attempt_count": failures,
        "abstention_count": abstentions,
        "review_count": len(packet),
        "stopped_candidates": sorted(stopped),
    }


def _load_executions(
    run_directory: Path, application_database_path: Path
) -> tuple[
    RunConfiguration,
    list[EvaluationCase],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    manifest, configuration, cases, _schedule_rows = _load_run(
        run_directory, application_database_path
    )
    executions = _read_json(run_directory / "executions.json")
    packet = _read_json(run_directory / "blind-review.json")
    mapping = _read_json(run_directory / "blind-map.json")
    freeze = _read_json(run_directory / "execution-freeze.json")
    if not all(isinstance(value, list) for value in (executions, packet, mapping)):
        raise EvaluationError("frozen execution artifacts are invalid")
    expected = {
        "manifest_sha256": _digest(_canonical(manifest)),
        "executions_sha256": _digest(_canonical(executions)),
        "blind_review_sha256": _digest(_canonical(packet)),
        "blind_map_sha256": _digest(_canonical(mapping)),
    }
    if freeze != expected:
        raise EvaluationError("a frozen execution artifact changed after execution")
    return configuration, cases, executions, mapping


def import_adjudications(
    *,
    run_directory: Path,
    adjudications_path: Path,
    application_database_path: Path,
) -> dict[str, object]:
    adjudications_path = _external_path(adjudications_path, application_database_path)
    _configuration, _cases, _executions, mapping = _load_executions(
        run_directory, application_database_path
    )
    value = _read_json(adjudications_path)
    if not isinstance(value, list):
        raise EvaluationError("adjudications must be a JSON array")
    try:
        adjudications = [BlindAdjudication.model_validate(row) for row in value]
    except ValidationError as exc:
        raise EvaluationError("adjudications do not match the pipeline schema") from exc
    expected_ids = {str(row["review_id"]) for row in mapping}
    actual_ids = [row.review_id for row in adjudications]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
        raise EvaluationError("adjudications must cover every blind review exactly once")
    adjudication_values = [row.model_dump(mode="json") for row in adjudications]
    run_directory = run_directory.resolve()
    _write_new(run_directory / "adjudications.json", adjudication_values)
    _write_new(
        run_directory / "adjudication-freeze.json",
        {"adjudications_sha256": _digest(_canonical(adjudication_values))},
    )
    return {"adjudication_count": len(adjudications)}


def _tokens(text: str) -> list[str]:
    return re.findall(r"\w+|[^\w\s]", text.casefold(), flags=re.UNICODE)


def _distance(left: Sequence[str], right: Sequence[str]) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_value in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_value in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_value != right_value),
                )
            )
        previous = current
    return previous[-1]


def _matched_left_indices(left: Sequence[str], right: Sequence[str]) -> set[int]:
    lengths = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for i, left_value in enumerate(left, start=1):
        for j, right_value in enumerate(right, start=1):
            lengths[i][j] = (
                lengths[i - 1][j - 1] + 1
                if left_value == right_value
                else max(lengths[i - 1][j], lengths[i][j - 1])
            )
    matched: set[int] = set()
    i, j = len(left), len(right)
    while i and j:
        if left[i - 1] == right[j - 1]:
            matched.add(i - 1)
            i -= 1
            j -= 1
        elif lengths[i - 1][j] >= lengths[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return matched


def _case_metrics(
    case: EvaluationCase,
    row: dict[str, object],
    adjudications: dict[int, str] | None,
) -> dict[str, float]:
    if row["outcome"] != "success":
        return {
            "editing_reduction": 0.0,
            "correct_repair_rate": 1.0,
            "preservation": 1.0,
            "usable": float(row["outcome"] == "abstention"),
            "within_ten_seconds": float(int(row["latency_ms"]) < 10_000),
            "proposed_repairs": 0.0,
        }
    original = _tokens(case.original)
    prepared = _tokens(str(row["prepared_text"]))
    intended_variants = [_tokens(variant) for variant in case.intended_variants]
    original_intended = min(
        intended_variants,
        key=lambda variant: _distance(original, variant),
    )
    prepared_variants = [*intended_variants]
    if adjudications and all(verdict == "equivalent" for verdict in adjudications.values()):
        prepared_variants.append(prepared)
    prepared_intended = min(
        prepared_variants,
        key=lambda variant: _distance(prepared, variant),
    )
    original_distance = _distance(original, original_intended)
    prepared_distance = _distance(prepared, prepared_intended)
    proposed = _distance(original, prepared)
    improvement = original_distance - prepared_distance
    already_correct = _matched_left_indices(original, original_intended)
    retained = _matched_left_indices(original, prepared)
    calculated_correct_rate = (
        min(1.0, max(0.0, improvement / proposed)) if proposed else 1.0
    )
    repairs = row["repairs"]
    if adjudications and isinstance(repairs, list):
        calculated_correct_rate = (
            sum(
                adjudications.get(index) in {"correct", "equivalent"}
                for index in range(len(repairs))
            )
            / len(repairs)
            if repairs
            else calculated_correct_rate
        )
    return {
        "editing_reduction": (
            improvement / original_distance if original_distance else float(prepared_distance == 0)
        ),
        "correct_repair_rate": calculated_correct_rate,
        "preservation": (
            len(already_correct & retained) / len(already_correct) if already_correct else 1.0
        ),
        "usable": 1.0,
        "within_ten_seconds": float(int(row["latency_ms"]) < 10_000),
        "proposed_repairs": float(proposed),
    }


def _weighted_metrics(
    rows: Sequence[dict[str, object]], configuration: RunConfiguration
) -> dict[str, float]:
    active_strata = [
        stratum
        for stratum in configuration.required_strata
        if any(row["stratum"] == stratum for row in rows)
    ]
    if not active_strata:
        return dict.fromkeys(METRIC_NAMES, 0.0)
    active_weight = sum(configuration.stratum_weights[stratum] for stratum in active_strata)
    result: dict[str, float] = {}
    for name in METRIC_NAMES:
        result[name] = sum(
            configuration.stratum_weights[stratum]
            / active_weight
            * sum(float(row[name]) for row in rows if row["stratum"] == stratum)
            / sum(row["stratum"] == stratum for row in rows)
            for stratum in active_strata
        )
    return result


def _bootstrap_lower_bounds(
    rows: Sequence[dict[str, object]],
    configuration: RunConfiguration,
    family_size: int,
) -> dict[str, float]:
    by_stratum = {
        stratum: {
            str(row["case_id"]): [
                candidate_row
                for candidate_row in rows
                if candidate_row["case_id"] == row["case_id"]
            ]
            for row in rows
            if row["stratum"] == stratum
        }
        for stratum in configuration.required_strata
        if any(row["stratum"] == stratum for row in rows)
    }
    if not by_stratum:
        return dict.fromkeys(METRIC_NAMES, 0.0)
    samples: dict[str, list[float]] = {name: [] for name in METRIC_NAMES}
    for resample in range(configuration.bootstrap_resamples):
        selected: list[dict[str, object]] = []
        for stratum, stratum_cases in by_stratum.items():
            case_ids = sorted(stratum_cases)
            for draw in range(len(case_ids)):
                digest = _digest(
                    f"{configuration.bootstrap_seed}:{resample}:{stratum}:{draw}".encode()
                )
                selected.extend(stratum_cases[case_ids[int(digest[:16], 16) % len(case_ids)]])
        values = _weighted_metrics(selected, configuration)
        for name, value in values.items():
            samples[name].append(value)
    quantile = 0.05 / family_size
    index = max(0, int(configuration.bootstrap_resamples * quantile) - 1)
    return {name: sorted(values)[index] for name, values in samples.items()}


def build_report(*, run_directory: Path, application_database_path: Path) -> dict[str, object]:
    configuration, cases, executions, mapping = _load_executions(
        run_directory, application_database_path
    )
    adjudications_value = _read_json(run_directory / "adjudications.json")
    adjudication_freeze = _read_json(run_directory / "adjudication-freeze.json")
    if adjudication_freeze != {
        "adjudications_sha256": _digest(_canonical(adjudications_value))
    }:
        raise EvaluationError("frozen adjudications changed after import")
    try:
        adjudications = [BlindAdjudication.model_validate(row) for row in adjudications_value]
    except (ValidationError, TypeError) as exc:
        raise EvaluationError("frozen adjudications are invalid") from exc
    verdicts_by_job: dict[str, dict[int, str]] = {}
    for map_row in mapping:
        matching = next(
            adjudication
            for adjudication in adjudications
            if adjudication.review_id == map_row["review_id"]
        )
        verdicts_by_job.setdefault(str(map_row["job_id"]), {})[
            int(map_row["repair_index"])
        ] = matching.verdict
    family_size = max(
        1,
        sum(
            (3 if candidate.kind == "component" else 5) + 3 * len(candidate.method_ids)
            for candidate in configuration.candidates
        ),
    )
    cases_by_id = {case.case_id: case for case in cases}
    candidate_reports: dict[str, object] = {}
    for candidate in configuration.candidates:
        candidate_executions = [
            row for row in executions if row["candidate_id"] == candidate.candidate_id
        ]
        scored = [
            {
                **_case_metrics(
                    cases_by_id[str(row["case_id"])],
                    row,
                    verdicts_by_job.get(str(row["job_id"])),
                ),
                "case_id": row["case_id"],
                "stratum": cases_by_id[str(row["case_id"])].stratum,
                "selected_method": row["selected_method"],
            }
            for row in candidate_executions
        ]
        point = _weighted_metrics(scored, configuration)
        lower = _bootstrap_lower_bounds(scored, configuration, family_size)
        thresholds = {
            "editing_reduction": 0.25 if candidate.kind == "component" else 0.5,
            "correct_repair_rate": 0.95,
            "preservation": 0.99,
            **(
                {"usable": 0.95, "within_ten_seconds": 0.95}
                if candidate.kind != "component"
                else {}
            ),
        }
        routed_cases = len({str(row["case_id"]) for row in scored})
        proposed_repairs = sum(int(row["proposed_repairs"]) for row in scored)
        sufficient = candidate.kind != "component" or (
            routed_cases >= 30 and proposed_repairs >= 30
        )
        routed_methods = {}
        for method_id in candidate.method_ids:
            method_rows = [row for row in scored if row["selected_method"] == method_id]
            method_cases = len({str(row["case_id"]) for row in method_rows})
            method_repairs = sum(int(row["proposed_repairs"]) for row in method_rows)
            method_point = _weighted_metrics(method_rows, configuration)
            method_lower = _bootstrap_lower_bounds(method_rows, configuration, family_size)
            method_thresholds = {
                "editing_reduction": 0.25,
                "correct_repair_rate": 0.95,
                "preservation": 0.99,
            }
            method_sufficient = method_cases >= 30 and method_repairs >= 30
            method_confidence_pass = method_sufficient and all(
                method_lower[name] >= threshold
                for name, threshold in method_thresholds.items()
            )
            routed_methods[method_id] = {
                "attempts": len(method_rows),
                "routed_case_count": method_cases,
                "proposed_repair_count": method_repairs,
                "evidence_status": (
                    "decision_grade" if method_confidence_pass else "insufficient_evidence"
                ),
                "unweighted_metrics": {
                    name: (
                        sum(float(row[name]) for row in method_rows) / len(method_rows)
                        if method_rows
                        else 0.0
                    )
                    for name in point
                },
                "confidence_lower_bounds": method_lower,
                "gates": {
                    "sufficient_evidence": method_sufficient,
                    "point_estimates_pass": method_sufficient
                    and all(
                        method_point[name] >= threshold
                        for name, threshold in method_thresholds.items()
                    ),
                    "adjusted_confidence_bounds_pass": method_confidence_pass,
                    "thresholds": method_thresholds,
                },
            }
        candidate_reports[candidate.candidate_id] = {
            "kind": candidate.kind,
            "family": candidate.family,
            **point,
            "confidence_lower_bounds": lower,
            "attempts": len(candidate_executions),
            "failures": sum(row["outcome"] == "failure" for row in candidate_executions),
            "abstentions": sum(row["outcome"] == "abstention" for row in candidate_executions),
            "internal_retries": sum(int(row["internal_retries"]) for row in candidate_executions),
            "provider_calls": sum(int(row["provider_calls"]) for row in candidate_executions),
            "input_tokens": sum(int(row["input_tokens"]) for row in candidate_executions),
            "output_tokens": sum(int(row["output_tokens"]) for row in candidate_executions),
            "cost_usd_micros": sum(int(row["cost_usd_micros"]) for row in candidate_executions),
            "routed_case_count": routed_cases,
            "proposed_repair_count": proposed_repairs,
            "routed_methods": routed_methods,
            "strata": {
                stratum: {
                    name: sum(float(row[name]) for row in scored if row["stratum"] == stratum)
                    / sum(row["stratum"] == stratum for row in scored)
                    for name in point
                }
                for stratum in configuration.required_strata
            },
            "gates": {
                "sufficient_specialist_evidence": sufficient,
                "point_estimates_pass": sufficient
                and all(point[name] >= threshold for name, threshold in thresholds.items()),
                "adjusted_confidence_bounds_pass": sufficient
                and all(lower[name] >= threshold for name, threshold in thresholds.items()),
                "thresholds": thresholds,
            },
        }
    report = {
        "pipeline_version": PIPELINE_VERSION,
        "protocol_version": configuration.protocol_version,
        "software_version": configuration.software_version,
        "phase": configuration.phase,
        "evidence_status": (
            "synthetic_harness_validation_only"
            if configuration.synthetic_validation
            else "private_evidence_run"
        ),
        "candidate_count": len(configuration.candidates),
        "eligible_case_count": sum(case.eligible for case in cases),
        "scheduled_attempt_count": len(executions),
        "familywise_confidence": {
            "method": "case-clustered-stratum-weighted-bootstrap",
            "one_sided_level": 0.95,
            "adjustment": "bonferroni",
            "resamples": configuration.bootstrap_resamples,
        },
        "candidates": candidate_reports,
    }
    _write_new(run_directory.resolve() / "aggregate-report.json", report)
    return report
