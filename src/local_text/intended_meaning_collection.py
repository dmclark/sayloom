"""Private, external-only collection of producer-confirmed Intended text."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import stat
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    computed_field,
    field_validator,
    model_validator,
)

from local_text.config import load_settings

COLLECTION_VERSION = "intended-meaning-collection-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_APPLICATION_ROOT = Path.home() / "Library/Application Support/local-text"
IDENTIFIER_PATTERN = r"^[a-f0-9]{32}$"

InputSituation = Literal[
    "short_command_or_fragment",
    "conversational_message",
    "longer_multi_sentence",
    "names_specialized_or_user_specific",
]
Difficulty = Literal["easy", "difficult", "already_correct", "presentation_only"]
ErrorClass = Literal[
    "lexical_substitution",
    "omission",
    "insertion",
    "boundary_error",
    "duplication",
    "reordering",
    "inflection",
    "function_word",
    "proper_noun",
    "homophone",
    "context_or_private_vocabulary",
]
ContextCondition = Literal["with_useful_context", "without_useful_context"]
ProfileCondition = Literal["cold_start", "profile_assisted"]
GroupRelationship = Literal["repeated_phrase", "related_version", "near_duplicate"]
ExclusionReason = Literal[
    "producer_cannot_reconstruct",
    "audio_based_recovery",
    "broader_rewriting",
    "unsupported_language_or_code_switching",
    "empty_or_non_text",
    "corrupt_capture_artifact",
]

INPUT_SITUATIONS = list(InputSituation.__args__)
DIFFICULTIES = list(Difficulty.__args__)
ERROR_CLASSES = list(ErrorClass.__args__)
CONTEXT_CONDITIONS = list(ContextCondition.__args__)
PROFILE_CONDITIONS = list(ProfileCondition.__args__)
GROUP_RELATIONSHIPS = list(GroupRelationship.__args__)
EXCLUSION_REASONS = list(ExclusionReason.__args__)
REQUIRED_STRATA = [
    *INPUT_SITUATIONS,
    *DIFFICULTIES,
    *ERROR_CLASSES,
    *CONTEXT_CONDITIONS,
    *PROFILE_CONDITIONS,
]


class CollectionError(RuntimeError):
    pass


class EvidenceCase(BaseModel):
    """One private prospective observation, frozen before candidate exposure."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=IDENTIFIER_PATTERN)
    group_id: str = Field(pattern=IDENTIFIER_PATTERN)
    group_relationships: list[GroupRelationship] = Field(default_factory=list)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    original_observed_at: datetime
    source: Literal["voiceitt_generated_english"] = "voiceitt_generated_english"
    producer_scope: Literal["primary_user"] = "primary_user"
    original: str = Field(max_length=100_000)
    intended_variants: list[str] = Field(max_length=20)
    context: str = Field(max_length=100_000)
    profile: list[str] = Field(max_length=10_000)
    input_situations: list[InputSituation] = Field(min_length=1)
    difficulty: Difficulty
    error_classes: list[ErrorClass]
    context_condition: ContextCondition
    profile_condition: ProfileCondition
    high_stakes: bool
    producer_confirmed: bool
    intended_captured_before_candidate_exposure: bool
    context_snapshot_time_appropriate: bool
    profile_snapshot_time_appropriate: bool
    eligible: bool
    exclusion_reason: ExclusionReason | None = None
    synthetic: Literal[False] = False
    typed_or_pasted: Literal[False] = False
    practice_case: Literal[False] = False

    @field_validator("original_observed_at")
    @classmethod
    def original_observation_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Original observation time requires a timezone")
        return value

    @computed_field
    @property
    def strata(self) -> list[str]:
        return [
            *self.input_situations,
            self.difficulty,
            *self.error_classes,
            self.context_condition,
            self.profile_condition,
        ]

    @model_validator(mode="after")
    def evidence_boundary_is_satisfied(self) -> EvidenceCase:
        if self.eligible:
            if self.exclusion_reason is not None:
                raise ValueError("an eligible case cannot have an exclusion reason")
            if not self.original:
                raise ValueError("an eligible case requires Original")
            if not self.intended_variants or not all(self.intended_variants):
                raise ValueError("an eligible case requires nonempty Intended variants")
            if not self.producer_confirmed:
                raise ValueError("Intended variants require producer confirmation")
            if not self.intended_captured_before_candidate_exposure:
                raise ValueError("Intended variants must be captured before candidate exposure")
            if not (
                self.context_snapshot_time_appropriate and self.profile_snapshot_time_appropriate
            ):
                raise ValueError("context and profile provenance must be time-appropriate")
        elif self.exclusion_reason is None:
            raise ValueError("an ineligible case requires an exclusion reason")

        if self.context_condition == "with_useful_context" and not self.context:
            raise ValueError("a case with useful context requires a context snapshot")
        if self.context_condition == "without_useful_context" and self.context:
            raise ValueError("a case without useful context cannot contain a context snapshot")
        if self.profile_condition == "profile_assisted" and not self.profile:
            raise ValueError("a profile-assisted case requires a profile snapshot")
        if self.profile_condition == "cold_start" and self.profile:
            raise ValueError("a cold-start case cannot contain a profile snapshot")
        if self.difficulty in {"already_correct", "presentation_only"} and self.error_classes:
            raise ValueError(
                "already-correct and presentation-only cases cannot have recognition-error classes"
            )
        if (
            self.difficulty not in {"already_correct", "presentation_only"}
            and not self.error_classes
        ):
            raise ValueError("a recognition-error case requires at least one error class")
        return self


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _external_path(path: Path, application_database_path: Path) -> Path:
    if not path.is_absolute():
        raise CollectionError("collection paths must be absolute")
    resolved = path.resolve(strict=False)
    if _overlaps(resolved, PROJECT_ROOT.resolve()):
        raise CollectionError("collection paths must be outside the repository")
    application_paths = {
        DEFAULT_APPLICATION_ROOT.resolve(strict=False),
        application_database_path.resolve(strict=False).parent,
    }
    if any(_overlaps(resolved, application_path) for application_path in application_paths):
        raise CollectionError("collection paths must be outside application operating data")
    return resolved


def _write_new(path: Path, value: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CollectionError(f"frozen artifact already exists: {path.name}") from exc
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(value)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _mkdir_private(path: Path, *, parents: bool = False) -> None:
    previous_umask = os.umask(0o077)
    try:
        path.mkdir(mode=0o700, parents=parents, exist_ok=False)
    finally:
        os.umask(previous_umask)


def initialize_collection(
    *, package_directory: Path, application_database_path: Path
) -> dict[str, object]:
    """Create a new collection package; never adopt or alter an existing directory."""

    package_directory = _external_path(package_directory, application_database_path)
    try:
        _mkdir_private(package_directory, parents=True)
    except FileExistsError as exc:
        raise CollectionError("collection package already exists and cannot be adopted") from exc
    try:
        cases_directory = package_directory / "cases"
        _mkdir_private(cases_directory)
        manifest = {
            "collection_version": COLLECTION_VERSION,
            "claim_scope": "one_primary_voiceitt_user",
            "source": "actual_voiceitt_generated_english",
            "intended_authority": "producer_confirmed_before_candidate_exposure",
            "private_storage": "user_controlled_external_only",
            "partitions": "deferred_until_grouped_collection_is_frozen",
            "required_strata": REQUIRED_STRATA,
            "acceptance_exclusions": ["typed_or_pasted", "synthetic", "practice"],
        }
        manifest_bytes = _canonical(manifest) + b"\n"
        _write_new(package_directory / "manifest.json", manifest_bytes)
        _write_new(
            package_directory / "manifest.sha256",
            (_digest(manifest_bytes) + "\n").encode(),
        )
    except BaseException:
        for path in package_directory.rglob("*"):
            if path.is_file():
                path.unlink()
        for path in sorted(package_directory.rglob("*"), reverse=True):
            if path.is_dir():
                path.rmdir()
        package_directory.rmdir()
        raise
    return {"initialized": True, "case_count": 0, "manifest_sha256": _digest(manifest_bytes)}


def _verify_collection(package_directory: Path) -> None:
    manifest_path = package_directory / "manifest.json"
    digest_path = package_directory / "manifest.sha256"
    cases_directory = package_directory / "cases"
    try:
        manifest_bytes = manifest_path.read_bytes()
        expected_digest = digest_path.read_text().strip()
        manifest = json.loads(manifest_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise CollectionError("collection package is missing a valid frozen manifest") from exc
    if manifest.get("collection_version") != COLLECTION_VERSION:
        raise CollectionError("collection package version is not supported")
    if _digest(manifest_bytes) != expected_digest:
        raise CollectionError("collection manifest changed after initialization")
    if not cases_directory.is_dir():
        raise CollectionError("collection package is missing its cases directory")
    expected_modes = {
        package_directory: 0o700,
        cases_directory: 0o700,
        manifest_path: 0o600,
        digest_path: 0o600,
    }
    if any(stat.S_IMODE(path.stat().st_mode) != mode for path, mode in expected_modes.items()):
        raise CollectionError("collection package permissions are not restrictive")


def record_case(
    *, package_directory: Path, application_database_path: Path, case: EvidenceCase
) -> dict[str, object]:
    """Freeze one case and its exact-content hash without returning private text."""

    package_directory = _external_path(package_directory, application_database_path)
    _verify_collection(package_directory)
    case_directory = package_directory / "cases" / case.case_id
    try:
        _mkdir_private(case_directory)
    except FileExistsError as exc:
        raise CollectionError("evidence case already exists and cannot be replaced") from exc
    case_bytes = _canonical(case.model_dump(mode="json")) + b"\n"
    case_digest = _digest(case_bytes)
    try:
        _write_new(case_directory / "case.json", case_bytes)
        _write_new(case_directory / "case.sha256", (case_digest + "\n").encode())
    except BaseException:
        # Keep any partially written case directory: its ID remains burned rather than mutable.
        raise
    return {
        "recorded": True,
        "eligible": case.eligible,
        "group_id": case.group_id,
        "case_sha256": case_digest,
    }


def _confirm(prompt: str) -> bool:
    while True:
        answer = input(f"{prompt} [yes/no]: ").strip().lower()
        if answer in {"yes", "y"}:
            return True
        if answer in {"no", "n"}:
            return False
        print("Enter yes or no.")


def _choose(prompt: str, options: list[str]) -> str:
    print(prompt)
    for number, option in enumerate(options, start=1):
        print(f"  {number}. {option}")
    while True:
        answer = input("Selection: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        print("Enter one listed number.")


def _choose_many(prompt: str, options: list[str], *, required: bool) -> list[str]:
    print(prompt)
    for number, option in enumerate(options, start=1):
        print(f"  {number}. {option}")
    while True:
        answer = input("Selections (comma-separated; blank for none): ").strip()
        if not answer and not required:
            return []
        try:
            indexes = [int(value.strip()) for value in answer.split(",")]
        except ValueError:
            indexes = []
        if (
            indexes
            and len(indexes) == len(set(indexes))
            and all(1 <= index <= len(options) for index in indexes)
        ):
            return [options[index - 1] for index in indexes]
        print("Enter unique listed numbers separated by commas.")


def _secret_values(prompt: str, *, required: bool) -> list[str]:
    values: list[str] = []
    while True:
        value = getpass.getpass(f"{prompt} (blank to finish): ")
        if not value:
            if values or not required:
                return values
            print("At least one value is required.")
            continue
        values.append(value)


def _capture_interactively() -> EvidenceCase:
    if not sys.stdin.isatty():
        raise CollectionError("capture requires an interactive terminal with hidden input")
    print(
        "Private values are entered without terminal echo. This command never loads or shows "
        "candidate output."
    )
    if not _confirm("Was Original generated by Voiceitt in English by the primary user?"):
        raise CollectionError("only primary-user Voiceitt-generated English may be collected")
    if not _confirm("Did this arise from actual use rather than practice or testing?"):
        raise CollectionError("practice and test cases cannot enter this collection")
    case_id = uuid.uuid4().hex
    group_id = (
        input("Existing neutral related-group ID (blank starts a new group): ").strip() or case_id
    )
    relationships = (
        []
        if group_id == case_id
        else _choose_many(
            "Why does this case share that group?", GROUP_RELATIONSHIPS, required=True
        )
    )
    observed_at = input("When was Original observed? (ISO 8601 with timezone): ").strip()
    original = getpass.getpass("Original: ")
    eligible = _confirm("Can the producer confidently reconstruct Intended text?")
    intended = _secret_values("Intended acceptable variant", required=True) if eligible else []
    producer_confirmed = eligible and _confirm("Did the producer confirm every Intended variant?")
    before_exposure = eligible and _confirm(
        "Was Intended captured before any candidate Prepared output was shown?"
    )
    exclusion_reason = None if eligible else _choose("Exclusion reason", EXCLUSION_REASONS)
    situations = _choose_many("Input situation(s)", INPUT_SITUATIONS, required=True)
    difficulty = _choose("Difficulty/input condition", DIFFICULTIES)
    errors = _choose_many(
        "Recognition-error class(es)",
        ERROR_CLASSES,
        required=difficulty not in {"already_correct", "presentation_only"},
    )
    context_condition = _choose("Surrounding-context condition", CONTEXT_CONDITIONS)
    context = (
        getpass.getpass("Time-appropriate surrounding context: ")
        if context_condition == "with_useful_context"
        else ""
    )
    context_provenance = _confirm("Is that context exactly what was available at correction time?")
    profile_condition = _choose("Profile condition", PROFILE_CONDITIONS)
    profile = (
        _secret_values("Time-appropriate profile item", required=True)
        if profile_condition == "profile_assisted"
        else []
    )
    profile_provenance = _confirm("Is that profile exactly what was available at correction time?")
    high_stakes = _confirm("Is this naturally occurring high-stakes text?")
    try:
        return EvidenceCase(
            case_id=case_id,
            group_id=group_id,
            group_relationships=relationships,
            original_observed_at=observed_at,
            original=original,
            intended_variants=intended,
            context=context,
            profile=profile,
            input_situations=situations,
            difficulty=difficulty,
            error_classes=errors,
            context_condition=context_condition,
            profile_condition=profile_condition,
            high_stakes=high_stakes,
            producer_confirmed=producer_confirmed,
            intended_captured_before_candidate_exposure=before_exposure,
            context_snapshot_time_appropriate=context_provenance,
            profile_snapshot_time_appropriate=profile_provenance,
            eligible=eligible,
            exclusion_reason=exclusion_reason,
        )
    except ValidationError as exc:
        raise CollectionError(
            "case was not recorded because its answers violate the frozen evidence boundary"
        ) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="intended-meaning-collection",
        description="Collect private Intended evidence into a new approved external package",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "capture"):
        command = commands.add_parser(name)
        command.add_argument("--package-directory", type=Path, required=True)
    return parser


def _run(arguments: argparse.Namespace) -> dict[str, object]:
    application_database_path = load_settings().resolved_database_path
    if arguments.command == "init":
        return initialize_collection(
            package_directory=arguments.package_directory,
            application_database_path=application_database_path,
        )
    return record_case(
        package_directory=arguments.package_directory,
        application_database_path=application_database_path,
        case=_capture_interactively(),
    )


def main() -> None:
    try:
        print(json.dumps(_run(_parser().parse_args()), indent=2, sort_keys=True))
    except CollectionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
