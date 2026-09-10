"""Provider-free registration for the source-preserving cleanup benchmark."""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from local_text.cleanup import LEXICAL_WORD, REMOVABLE_LEADING_FILLERS
from local_text.cleanup_contract import build_cleanup_contract_snapshot, canonical_json
from local_text.evaluation import CONSENT_VERSION, CONTRACT_VERSION, PURPOSE

MANIFEST_VERSION = "cleanup-evaluation-registration-v1"
SNAPSHOT_VERSION = "cleanup-evaluation-registration-corpus-v1"
PROTOCOL_ID = "cleanup-evaluation-benchmark-v2"
SELECTION_ALGORITHM = "cleanup-feasible-lexicographic-sha256-v1"
SELECTION_DOMAIN = "local_text:cleanup-evaluation:selection:v1"
CASE_ORDER_ALGORITHM = "cleanup-case-order-sha256-v1"
ARM_ORDER_ALGORITHM = "cleanup-arm-order-sha256-v1"
PRIMARY_QUOTAS = {
    "unchanged": 10,
    "capitalization_only": 8,
    "punctuation_only": 8,
    "apostrophe_only": 8,
    "whitespace_or_paragraph_only": 8,
    "leading_filler_only": 8,
    "mixed_permitted_transformations": 10,
}
CHALLENGE_MINIMA = {
    "names_or_technical_terms": 12,
    "numbers_or_dates": 12,
    "negation_or_modality": 12,
    "links_code_or_identifiers": 8,
    "quotations": 8,
    "line_or_paragraph_structures": 8,
}
ARMS = ("baseline_paid_gemini", "candidate_paid_openai")
LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class RegistrationError(ValueError):
    """A privacy-safe registration failure."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Consent(_StrictModel):
    version: Literal[CONSENT_VERSION]
    scope: Literal[PURPOSE]
    confirmed_at: datetime


class Hold(_StrictModel):
    benchmark_id: str = Field(pattern=SAFE_ID.pattern)
    confirmed_at: datetime
    release_at: datetime


class PromptProvenance(_StrictModel):
    version_id: str = Field(pattern=SAFE_ID.pattern)
    content_sha256: str = Field(pattern=LOWER_SHA256.pattern)
    text: str = Field(max_length=100_000)

    @model_validator(mode="after")
    def checksum_matches(self) -> PromptProvenance:
        if _digest(self.text.encode()) != self.content_sha256:
            raise ValueError("prompt checksum does not match")
        return self


class FrozenAnnotations(_StrictModel):
    primary_stratum: Literal[
        "unchanged",
        "capitalization_only",
        "punctuation_only",
        "apostrophe_only",
        "whitespace_or_paragraph_only",
        "leading_filler_only",
        "mixed_permitted_transformations",
    ]
    challenge_tags: list[
        Literal[
            "names_or_technical_terms",
            "numbers_or_dates",
            "negation_or_modality",
            "links_code_or_identifiers",
            "quotations",
            "line_or_paragraph_structures",
        ]
    ]
    ambiguous: bool
    transcript_truth_dependent: bool
    frozen_at: datetime
    corpus_owner: str = Field(pattern=SAFE_ID.pattern)

    @field_validator("challenge_tags")
    @classmethod
    def unique_tags(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("challenge tags must be unique")
        return value


class CorpusCase(_StrictModel):
    case_id: str = Field(pattern=SAFE_ID.pattern)
    contract_version: Literal[CONTRACT_VERSION]
    purpose: Literal[PURPOSE]
    revision: int = Field(ge=1)
    current_revision: int = Field(ge=1)
    source_category: Literal["dictation", "typed", "pasted", "unknown"]
    source_text: str = Field(min_length=1, max_length=100_000)
    expected_cleanup: str = Field(min_length=1, max_length=100_000)
    source_sha256: str = Field(pattern=LOWER_SHA256.pattern)
    expected_cleanup_sha256: str = Field(pattern=LOWER_SHA256.pattern)
    record_sha256: str = Field(pattern=LOWER_SHA256.pattern)
    captured_at: datetime
    confirmed_at: datetime
    expires_at: datetime
    original_user_confirmed: bool
    expected_cleanup_user_confirmed: bool
    consent: Consent
    hold: Hold
    prompt: PromptProvenance
    annotations: FrozenAnnotations

    @model_validator(mode="before")
    @classmethod
    def record_checksum_matches_input(cls, value: Any) -> Any:
        if isinstance(value, dict) and isinstance(value.get("record_sha256"), str):
            record = {
                key: item
                for key, item in value.items()
                if key not in {"record_sha256", "current_revision"}
            }
            if _digest(canonical_json(record)) != value["record_sha256"]:
                raise ValueError("record checksum does not match")
        return value

    @model_validator(mode="after")
    def checksums_match(self) -> CorpusCase:
        if _digest(self.source_text.encode()) != self.source_sha256:
            raise ValueError("source checksum does not match")
        if _digest(self.expected_cleanup.encode()) != self.expected_cleanup_sha256:
            raise ValueError("expected-cleanup checksum does not match")
        return self


class CorpusSnapshot(_StrictModel):
    snapshot_version: Literal[SNAPSHOT_VERSION]
    frozen_at: datetime
    cases: list[CorpusCase]

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> CorpusSnapshot:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case IDs must be unique")
        return self


class RegistrationInputs(_StrictModel):
    run_id: str = Field(pattern=SAFE_ID.pattern)
    registered_at: datetime
    selection_seed: int
    case_order_seed: int
    arm_order_seed: int
    bootstrap_seed: int
    review_order_seed: int
    pair_order_seed: int
    pair_side_seed: int
    roles: dict[str, Any]
    environment: dict[str, Any]
    code: dict[str, Any]
    cleanup_contract: dict[str, Any]
    provider_evidence: dict[str, Any]
    smoke: dict[str, Any]
    scoring: dict[str, Any]
    review: dict[str, Any]
    budget: dict[str, Any]
    run_confirmation: dict[str, Any]
    storage: dict[str, Any]
    lifecycle: dict[str, Any]

    @model_validator(mode="after")
    def fixed_contract_is_complete(self) -> RegistrationInputs:
        required_roles = {"protocol_owner", "corpus_owner", "run_operator"}
        if set(self.roles) != required_roles or not all(self.roles.values()):
            raise ValueError("all benchmark roles must be assigned")
        if self.cleanup_contract.get("protocol_id") != PROTOCOL_ID:
            raise ValueError("cleanup contract protocol does not match")
        try:
            artifacts = self.cleanup_contract["artifacts"]
            configured_prompt = base64.b64decode(
                artifacts["configured_prompt"]["canonical_bytes_base64"], validate=True
            ).decode("utf-8")
            dependency_lock = base64.b64decode(
                artifacts["dependency_lock"]["canonical_bytes_base64"], validate=True
            )
            expected_contract = build_cleanup_contract_snapshot(
                configured_prompt,
                configured_prompt_id=self.cleanup_contract["configured_prompt_id"],
                dependency_lock_bytes=dependency_lock,
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, binascii.Error):
            raise ValueError("cleanup contract is incomplete") from None
        if self.cleanup_contract != expected_contract:
            raise ValueError("cleanup contract does not match the shipped contract")
        if self.code.get("clean_tree") is not True:
            raise ValueError("runner code must be an immutable clean tree")
        for name in ("runner_commit", "scoring_commit"):
            if not re.fullmatch(r"[0-9a-f]{40,64}", str(self.code.get(name, ""))):
                raise ValueError("code identity is incomplete")
        if not LOWER_SHA256.fullmatch(str(self.code.get("dependency_lock_sha256", ""))):
            raise ValueError("dependency lock identity is incomplete")
        if self.code["dependency_lock_sha256"] != artifacts["dependency_lock"]["sha256"]:
            raise ValueError("code and cleanup contract dependency locks do not match")
        if self.environment.get("stable_resources_inaccessible") is not True:
            raise ValueError("stable resources must be inaccessible")
        evidence_at = _utc(self.provider_evidence.get("retrieved_at", ""))
        if not self.registered_at - timedelta(hours=24) <= evidence_at <= self.registered_at:
            raise ValueError("provider evidence must be current within 24 hours")
        if self.provider_evidence.get("material_change") is not False:
            raise ValueError("material provider change blocks registration")
        for name in (
            "official_urls",
            "availability",
            "pricing_usd_micros",
            "retention_and_data_use",
            "account_controls",
            "openai_store_false",
        ):
            if not self.provider_evidence.get(name):
                raise ValueError("provider evidence is incomplete")
        if self.smoke.get("fixture_count") != 8 or self.smoke.get("call_count") != 16:
            raise ValueError("complete synthetic smoke evidence is required")
        if self.smoke.get("all_passed") is not True:
            raise ValueError("synthetic smoke must pass before registration")
        if self.scoring.get("normalization") != ["unicode_nfc", "lf_line_endings"]:
            raise ValueError("scoring normalization does not match the protocol")
        if not LOWER_SHA256.fullmatch(str(self.review.get("rubric_sha256", ""))):
            raise ValueError("review rubric identity is incomplete")
        if self.budget.get("total_usd_micros") != 10_000_000:
            raise ValueError("benchmark budget must be exactly 10 USD")
        if self.budget.get("private_call_reservation") != 120:
            raise ValueError("budget must reserve all 120 private calls")
        if self.budget.get("pre_send_stop") is not True:
            raise ValueError("pre-send budget stop must be enabled")
        conservative_bound = self.budget.get("conservative_bound_usd_micros")
        if not isinstance(conservative_bound, int) or not 0 <= conservative_bound <= 10_000_000:
            raise ValueError("conservative budget bound is invalid")
        if self.run_confirmation.get("confirmed") is not True:
            raise ValueError("exact run confirmation is required")
        for name in ("confirmed_at", "hold_release_at", "disclosures"):
            if not self.run_confirmation.get(name):
                raise ValueError("exact run confirmation is incomplete")
        if self.lifecycle.get("write_back_to_live_corpus") is not False:
            raise ValueError("live-corpus write-back must be disabled")
        if not self.storage.get("inventory") or self.storage.get("locations_confirmed") is not True:
            raise ValueError("storage inventory and locations are incomplete")
        for name in (
            "environment",
            "provider_evidence",
            "smoke",
            "scoring",
            "review",
            "storage",
        ):
            if not getattr(self, name):
                raise ValueError(f"{name} inputs are required")
        return self


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _nfc_lf(value: str) -> str:
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RegistrationError("registration timestamp is invalid") from exc
    if value.tzinfo is None:
        raise RegistrationError("registration timestamps must include a UTC offset")
    return value.astimezone(UTC)


def _word_parts(value: str) -> tuple[list[str], list[str]]:
    matches = list(LEXICAL_WORD.finditer(value))
    words = [match.group() for match in matches]
    gaps: list[str] = []
    start = 0
    for match in matches:
        gaps.append(value[start : match.start()])
        start = match.end()
    gaps.append(value[start:])
    return words, gaps


def _word_base(value: str) -> str:
    return value.casefold().replace("'", "").replace("’", "")


def _strip_kind(value: str, prefix: str) -> str:
    return "".join(
        character for character in value if not unicodedata.category(character).startswith(prefix)
    )


def _transformation_categories(original: str, expected: str) -> set[str] | None:
    original_words, original_gaps = _word_parts(original)
    expected_words, expected_gaps = _word_parts(expected)
    removed_fillers = 0
    while (
        removed_fillers < len(original_words)
        and _word_base(original_words[removed_fillers]) in REMOVABLE_LEADING_FILLERS
        and len(original_words) - removed_fillers > len(expected_words)
    ):
        removed_fillers += 1
    if len(original_words) - removed_fillers != len(expected_words):
        return None
    categories: set[str] = set()
    if removed_fillers:
        categories.add("leading_filler")
        original_words = original_words[removed_fillers:]
        original_gaps = [original_gaps[0], *original_gaps[removed_fillers + 1 :]]
    for source, target in zip(original_words, expected_words, strict=True):
        if _word_base(source) != _word_base(target):
            return None
        if source != target:
            if source.casefold().replace("’", "'") != target.casefold().replace("’", "'"):
                categories.add("apostrophe")
            source_without_apostrophes = source.replace("'", "").replace("’", "")
            target_without_apostrophes = target.replace("'", "").replace("’", "")
            if (
                source_without_apostrophes.casefold() == target_without_apostrophes.casefold()
                and source_without_apostrophes != target_without_apostrophes
            ):
                categories.add("capitalization")
    for source, target in zip(original_gaps, expected_gaps, strict=True):
        source_symbols = "".join(
            character
            for character in source
            if not (character.isspace() or unicodedata.category(character).startswith("P"))
        )
        target_symbols = "".join(
            character
            for character in target
            if not (character.isspace() or unicodedata.category(character).startswith("P"))
        )
        if source_symbols != target_symbols:
            return None
        if _strip_kind(source, "P") != _strip_kind(target, "P"):
            categories.add("whitespace_or_paragraph")
        if "".join(source.split()) != "".join(target.split()):
            categories.add("punctuation")
    return categories


def _eligible(
    case: CorpusCase,
    registered_at: datetime,
    snapshot_frozen_at: datetime,
    corpus_owner: str,
    hold_release_at: datetime,
) -> tuple[bool, str]:
    if case.revision != case.current_revision:
        return False, "not_current_revision"
    if case.source_category != "dictation":
        return False, "not_dictation_derived"
    if not case.original_user_confirmed or not case.expected_cleanup_user_confirmed:
        return False, "user_confirmation_incomplete"
    if case.annotations.ambiguous:
        return False, "ambiguous"
    if case.annotations.transcript_truth_dependent:
        return False, "transcript_truth_dependent"
    if (
        _utc(case.confirmed_at) > snapshot_frozen_at
        or _utc(case.consent.confirmed_at) > snapshot_frozen_at
        or _utc(case.annotations.frozen_at) > snapshot_frozen_at
        or _utc(case.hold.confirmed_at) > registered_at
    ):
        return False, "confirmation_or_annotation_not_frozen"
    if case.annotations.corpus_owner != corpus_owner:
        return False, "annotation_owner_mismatch"
    if _utc(case.expires_at) <= registered_at or _utc(case.hold.release_at) <= registered_at:
        return False, "retention_or_hold_inactive"
    if case.hold.benchmark_id != PROTOCOL_ID or _utc(case.hold.release_at) != hold_release_at:
        return False, "benchmark_hold_mismatch"
    categories = _transformation_categories(case.source_text, case.expected_cleanup)
    if categories is None:
        return False, "impermissible_word_or_symbol_operation"
    expected_stratum = (
        "unchanged"
        if not categories
        else {
            "capitalization": "capitalization_only",
            "punctuation": "punctuation_only",
            "apostrophe": "apostrophe_only",
            "whitespace_or_paragraph": "whitespace_or_paragraph_only",
            "leading_filler": "leading_filler_only",
        }.get(next(iter(categories)))
        if len(categories) == 1
        else "mixed_permitted_transformations"
    )
    if case.annotations.primary_stratum != expected_stratum:
        return False, "primary_stratum_mismatch"
    return True, "eligible"


def _case_metadata(case: CorpusCase) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "revision": case.revision,
        "record_sha256": case.record_sha256,
        "source_sha256": case.source_sha256,
        "expected_cleanup_sha256": case.expected_cleanup_sha256,
        "primary_stratum": case.annotations.primary_stratum,
        "challenge_tags": sorted(case.annotations.challenge_tags),
        "annotation_sha256": _digest(canonical_json(case.annotations.model_dump(mode="json"))),
    }


def _selection_key(seed: int, pool_sha256: str, case_id: str) -> str:
    return _digest(canonical_json([SELECTION_DOMAIN, seed, pool_sha256, case_id]))


def _select(cases: list[CorpusCase], seed: int, pool_sha256: str) -> list[CorpusCase]:
    ordered = sorted(
        cases, key=lambda case: (_selection_key(seed, pool_sha256, case.case_id), case.case_id)
    )
    suffix_strata: list[Counter[str]] = [Counter() for _ in range(len(ordered) + 1)]
    suffix_tags: list[Counter[str]] = [Counter() for _ in range(len(ordered) + 1)]
    for index in range(len(ordered) - 1, -1, -1):
        suffix_strata[index] = suffix_strata[index + 1].copy()
        suffix_strata[index][ordered[index].annotations.primary_stratum] += 1
        suffix_tags[index] = suffix_tags[index + 1].copy()
        suffix_tags[index].update(ordered[index].annotations.challenge_tags)

    def search(
        index: int, chosen: list[CorpusCase], strata: Counter[str], tags: Counter[str]
    ) -> list[CorpusCase] | None:
        if any(strata[name] > quota for name, quota in PRIMARY_QUOTAS.items()):
            return None
        if any(
            strata[name] + suffix_strata[index][name] < quota
            for name, quota in PRIMARY_QUOTAS.items()
        ):
            return None
        if any(
            tags[name] + suffix_tags[index][name] < minimum
            for name, minimum in CHALLENGE_MINIMA.items()
        ):
            return None
        if len(chosen) == 60:
            if strata == Counter(PRIMARY_QUOTAS) and all(
                tags[name] >= minimum for name, minimum in CHALLENGE_MINIMA.items()
            ):
                return chosen
            return None
        if index == len(ordered) or len(chosen) + len(ordered) - index < 60:
            return None
        case = ordered[index]
        included = search(
            index + 1,
            [*chosen, case],
            strata + Counter([case.annotations.primary_stratum]),
            tags + Counter(case.annotations.challenge_tags),
        )
        if included is not None:
            return included
        return search(index + 1, chosen, strata, tags)

    selected = search(0, [], Counter(), Counter())
    if selected is None:
        raise RegistrationError("eligible corpus cannot satisfy every fixed benchmark quota")
    return selected


def _seeded_order(seed: int, domain: str, ids: list[str]) -> list[str]:
    return sorted(ids, key=lambda value: (_digest(canonical_json([domain, seed, value])), value))


def register_cleanup_benchmark(snapshot_value: object, inputs_value: object) -> dict[str, Any]:
    """Validate, select, and canonically register one benchmark without external access."""
    try:
        snapshot = CorpusSnapshot.model_validate(snapshot_value)
        inputs = RegistrationInputs.model_validate(inputs_value)
    except ValidationError:
        raise RegistrationError(
            "registration input does not match the frozen protocol schema"
        ) from None
    registered_at = _utc(inputs.registered_at)
    if _utc(snapshot.frozen_at) > registered_at:
        raise RegistrationError("corpus snapshot freeze is later than registration")
    if _utc(inputs.run_confirmation["confirmed_at"]) > registered_at:
        raise RegistrationError("run confirmation is later than registration")
    release_at = _utc(inputs.run_confirmation["hold_release_at"])
    if release_at <= registered_at or release_at > registered_at + timedelta(days=30):
        raise RegistrationError("benchmark hold release must be within 30 days")

    snapshot_frozen_at = _utc(snapshot.frozen_at)
    decisions: list[dict[str, Any]] = []
    eligible: list[CorpusCase] = []
    for case in snapshot.cases:
        accepted, reason = _eligible(
            case,
            registered_at,
            snapshot_frozen_at,
            str(inputs.roles["corpus_owner"]),
            release_at,
        )
        decisions.append({"case_id": case.case_id, "decision": reason})
        if accepted:
            eligible.append(case)

    grouped: dict[str, list[CorpusCase]] = defaultdict(list)
    for case in eligible:
        grouped[_nfc_lf(case.source_text)].append(case)
    representatives: list[CorpusCase] = []
    duplicate_decisions: list[dict[str, Any]] = []
    for canonical_original, group in grouped.items():
        ordered_group = sorted(group, key=lambda case: case.case_id)
        conflict = (
            len({case.expected_cleanup for case in group}) > 1
            or len({case.annotations.primary_stratum for case in group}) > 1
        )
        canonical_sha256 = _digest(canonical_original.encode())
        if conflict:
            duplicate_decisions.append(
                {
                    "canonical_original_sha256": canonical_sha256,
                    "case_ids": [case.case_id for case in ordered_group],
                    "decision": "excluded_conflict",
                }
            )
            continue
        representative = ordered_group[0]
        representatives.append(representative)
        duplicate_decisions.append(
            {
                "canonical_original_sha256": canonical_sha256,
                "case_ids": [case.case_id for case in ordered_group],
                "decision": "lowest_case_id_representative",
                "representative_case_id": representative.case_id,
            }
        )
    pool_value = {
        "cases": sorted(
            (_case_metadata(case) for case in representatives), key=lambda item: item["case_id"]
        ),
        "duplicate_decisions": sorted(
            duplicate_decisions, key=lambda item: item["canonical_original_sha256"]
        ),
    }
    pool_sha256 = _digest(canonical_json(pool_value))
    selected = _select(representatives, inputs.selection_seed, pool_sha256)
    selected_ids = [case.case_id for case in selected]
    case_order = _seeded_order(
        inputs.case_order_seed, "local_text:cleanup-evaluation:case-order:v1", selected_ids
    )
    arm_order = {
        case_id: _seeded_order(
            inputs.arm_order_seed,
            f"local_text:cleanup-evaluation:arm-order:v1:{case_id}",
            list(ARMS),
        )
        for case_id in selected_ids
    }
    selected_metadata = sorted(
        (_case_metadata(case) for case in selected), key=lambda item: item["case_id"]
    )
    snapshot_sha256 = _digest(canonical_json(snapshot.model_dump(mode="json")))
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "protocol": {
            "protocol_id": PROTOCOL_ID,
            "status": "approved_protocol_only_no_implementation_or_operation_authorized",
            "sha256": _digest(
                (
                    Path(__file__).resolve().parents[2]
                    / "docs/cleanup-evaluation-benchmark-v2.json"
                ).read_bytes()
            ),
            "supersedes": "cleanup-evaluation-benchmark-v1",
        },
        "run_id": inputs.run_id,
        "registered_at": inputs.registered_at.isoformat(),
        "roles": inputs.roles,
        "environment": inputs.environment,
        "code": inputs.code,
        "corpus": {
            "snapshot_version": SNAPSHOT_VERSION,
            "snapshot_frozen_at": snapshot.frozen_at.isoformat(),
            "snapshot_sha256": snapshot_sha256,
            "eligibility_decisions": decisions,
            "eligible_pool_sha256": pool_sha256,
            "eligible_representative_count": len(representatives),
            "duplicate_canonicalization": ["unicode_nfc", "lf_line_endings"],
            "duplicate_decisions": pool_value["duplicate_decisions"],
            "selected_cases": selected_metadata,
        },
        "selection": {
            "seed": inputs.selection_seed,
            "algorithm": SELECTION_ALGORITHM,
            "domain_separator": SELECTION_DOMAIN,
            "primary_quotas": PRIMARY_QUOTAS,
            "challenge_minima": CHALLENGE_MINIMA,
            "selected_key_order": [
                {
                    "case_id": case.case_id,
                    "key": _selection_key(inputs.selection_seed, pool_sha256, case.case_id),
                }
                for case in selected
            ],
            "quota_relaxation": False,
            "manual_override": False,
            "post_result_expansion": False,
        },
        "ordering": {
            "case_seed": inputs.case_order_seed,
            "case_algorithm": CASE_ORDER_ALGORITHM,
            "case_order": case_order,
            "arm_seed": inputs.arm_order_seed,
            "arm_algorithm": ARM_ORDER_ALGORITHM,
            "arm_order": arm_order,
        },
        "request_contract": inputs.cleanup_contract,
        "provider_evidence": inputs.provider_evidence,
        "synthetic_smoke": inputs.smoke,
        "scoring": {
            **inputs.scoring,
            "bootstrap_seed": inputs.bootstrap_seed,
            "bootstrap_resamples": 10_000,
        },
        "review": {
            **inputs.review,
            "individual_order_seed": inputs.review_order_seed,
            "pair_order_seed": inputs.pair_order_seed,
            "pair_side_seed": inputs.pair_side_seed,
        },
        "budget": inputs.budget,
        "run_confirmation": {
            **inputs.run_confirmation,
            "selected_cases": [
                {"case_id": item["case_id"], "revision": item["revision"]}
                for item in selected_metadata
            ],
            "maximum_private_calls": 120,
        },
        "storage": inputs.storage,
        "lifecycle": inputs.lifecycle,
        "execution_ledger": [{"event": "registered", "at": inputs.registered_at.isoformat()}],
    }
    return {"manifest": manifest, "manifest_sha256": _digest(canonical_json(manifest))}


def validate_registration(
    registration: object,
    current_snapshot_value: object,
    *,
    provider_call_count: int = 0,
) -> dict[str, str]:
    """Check immutable registration and report protocol lifecycle disposition."""
    if not isinstance(registration, dict) or not isinstance(registration.get("manifest"), dict):
        raise RegistrationError("registration manifest is invalid")
    manifest = registration["manifest"]
    if registration.get("manifest_sha256") != _digest(canonical_json(manifest)):
        raise RegistrationError("registration manifest changed after registration")
    try:
        snapshot = CorpusSnapshot.model_validate(current_snapshot_value)
    except ValidationError:
        raise RegistrationError("current corpus snapshot is invalid") from None
    current_sha256 = _digest(canonical_json(snapshot.model_dump(mode="json")))
    if current_sha256 != manifest.get("corpus", {}).get("snapshot_sha256"):
        return {
            "status": "stop_and_invalidate" if provider_call_count else "invalidate_and_reregister",
            "reason": "corpus_changed_after_registration",
        }
    return {"status": "valid", "reason": "unchanged"}


def _write_private(path: Path, value: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Register the provider-free cleanup benchmark")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_bytes())
        inputs = json.loads(args.inputs.read_bytes())
        registration = register_cleanup_benchmark(snapshot, inputs)
        _write_private(args.output, canonical_json(registration) + b"\n")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RegistrationError):
        print("error: cleanup benchmark registration failed", file=sys.stderr)
        raise SystemExit(1) from None
    print(
        canonical_json(
            {
                "manifest_sha256": registration["manifest_sha256"],
                "selected_case_count": 60,
                "status": "registered_no_execution_authorized",
            }
        ).decode()
    )


if __name__ == "__main__":
    main()
