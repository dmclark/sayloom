import json
import stat
from pathlib import Path

import pytest

from local_text.intended_meaning_collection import (
    REQUIRED_STRATA,
    CollectionError,
    EvidenceCase,
    initialize_collection,
    record_case,
)


def eligible_case() -> EvidenceCase:
    return EvidenceCase(
        case_id="a" * 32,
        group_id="b" * 32,
        group_relationships=["near_duplicate"],
        original_observed_at="2026-09-15T14:00:00-04:00",
        original="Synthetic Voiceitt wording alpha.",
        intended_variants=["Synthetic intended wording alpha."],
        context="Synthetic context alpha.",
        profile=["Synthetic profile alpha"],
        input_situations=["conversational_message"],
        difficulty="difficult",
        error_classes=["lexical_substitution"],
        context_condition="with_useful_context",
        profile_condition="profile_assisted",
        high_stakes=False,
        producer_confirmed=True,
        intended_captured_before_candidate_exposure=True,
        context_snapshot_time_appropriate=True,
        profile_snapshot_time_appropriate=True,
        eligible=True,
    )


def test_collection_is_external_private_and_frozen(tmp_path: Path) -> None:
    package = tmp_path / "approved-external" / "collection"
    application_database = tmp_path / "application-state" / "local-text.sqlite3"

    result = initialize_collection(
        package_directory=package,
        application_database_path=application_database,
    )

    assert result["initialized"] is True
    assert result["case_count"] == 0
    assert stat.S_IMODE(package.stat().st_mode) == 0o700
    assert stat.S_IMODE((package / "cases").stat().st_mode) == 0o700
    assert stat.S_IMODE((package / "manifest.json").stat().st_mode) == 0o600
    assert stat.S_IMODE((package / "manifest.sha256").stat().st_mode) == 0o600

    with pytest.raises(CollectionError, match="already exists"):
        initialize_collection(
            package_directory=package,
            application_database_path=application_database,
        )


def test_record_case_is_write_once_hashed_and_returns_no_private_text(tmp_path: Path) -> None:
    package = tmp_path / "approved-external" / "collection"
    application_database = tmp_path / "application-state" / "local-text.sqlite3"
    initialize_collection(
        package_directory=package,
        application_database_path=application_database,
    )
    case = eligible_case()

    result = record_case(
        package_directory=package,
        application_database_path=application_database,
        case=case,
    )

    case_directory = package / "cases" / ("a" * 32)
    frozen = json.loads((case_directory / "case.json").read_text())
    assert frozen["source"] == "voiceitt_generated_english"
    assert frozen["producer_scope"] == "primary_user"
    assert frozen["synthetic"] is False
    assert frozen["typed_or_pasted"] is False
    assert frozen["practice_case"] is False
    assert frozen["strata"] == [
        "conversational_message",
        "difficult",
        "lexical_substitution",
        "with_useful_context",
        "profile_assisted",
    ]
    assert stat.S_IMODE(case_directory.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in case_directory.iterdir())
    assert "Synthetic Voiceitt wording alpha." not in json.dumps(result)
    assert "Synthetic intended wording alpha." not in json.dumps(result)
    assert result == {
        "recorded": True,
        "eligible": True,
        "group_id": "b" * 32,
        "case_sha256": (case_directory / "case.sha256").read_text().strip(),
    }

    with pytest.raises(CollectionError, match="already exists"):
        record_case(
            package_directory=package,
            application_database_path=application_database,
            case=case,
        )


def test_collection_rejects_repository_and_application_state_paths(tmp_path: Path) -> None:
    application_database = tmp_path / "application-state" / "local-text.sqlite3"

    with pytest.raises(CollectionError, match="outside the repository"):
        initialize_collection(
            package_directory=Path(__file__).parent / "private-evidence",
            application_database_path=application_database,
        )
    with pytest.raises(CollectionError, match="outside application operating data"):
        initialize_collection(
            package_directory=application_database.parent / "evidence",
            application_database_path=application_database,
        )


def test_case_requires_pre_exposure_confirmation_and_time_appropriate_provenance() -> None:
    value = eligible_case().model_dump(exclude_computed_fields=True)
    value["intended_captured_before_candidate_exposure"] = False

    with pytest.raises(ValueError, match="before candidate exposure"):
        EvidenceCase.model_validate(value)

    value = eligible_case().model_dump(exclude_computed_fields=True)
    value["context_snapshot_time_appropriate"] = False
    with pytest.raises(ValueError, match="time-appropriate"):
        EvidenceCase.model_validate(value)

    value = eligible_case().model_dump(exclude_computed_fields=True)
    value["original_observed_at"] = "2026-09-15T14:00:00"
    with pytest.raises(ValueError, match="timezone"):
        EvidenceCase.model_validate(value)


def test_eligible_case_metadata_matches_context_profile_and_error_conditions() -> None:
    value = eligible_case().model_dump(exclude_computed_fields=True)
    value["context"] = ""
    with pytest.raises(ValueError, match="useful context"):
        EvidenceCase.model_validate(value)

    value = eligible_case().model_dump(exclude_computed_fields=True)
    value["profile"] = []
    with pytest.raises(ValueError, match="profile-assisted"):
        EvidenceCase.model_validate(value)

    value = eligible_case().model_dump(exclude_computed_fields=True)
    value["difficulty"] = "already_correct"
    with pytest.raises(ValueError, match="cannot have recognition-error classes"):
        EvidenceCase.model_validate(value)


def test_collection_freezes_all_required_boundary_strata_and_checks_permissions(
    tmp_path: Path,
) -> None:
    assert len(REQUIRED_STRATA) == 23
    assert len(set(REQUIRED_STRATA)) == 23
    package = tmp_path / "approved-external" / "collection"
    application_database = tmp_path / "application-state" / "local-text.sqlite3"
    initialize_collection(
        package_directory=package,
        application_database_path=application_database,
    )
    (package / "manifest.json").chmod(0o644)

    with pytest.raises(CollectionError, match="permissions"):
        record_case(
            package_directory=package,
            application_database_path=application_database,
            case=eligible_case(),
        )
