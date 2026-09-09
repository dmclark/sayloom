import hashlib
import json
import os
import stat
import subprocess
import sys
import traceback
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from local_text.cleanup_contract import build_cleanup_contract_snapshot, canonical_json
from local_text.cleanup_evaluation_runner import (
    CHALLENGE_MINIMA,
    PRIMARY_QUOTAS,
    PROTOCOL_ID,
    SNAPSHOT_VERSION,
    RegistrationError,
    _nfc_lf,
    register_cleanup_benchmark,
    validate_registration,
)

NOW = datetime(2026, 9, 9, 12, tzinfo=UTC)
ALL_TAGS = list(CHALLENGE_MINIMA)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def rehash_record(value: dict[str, object]) -> None:
    record = {
        key: item for key, item in value.items() if key not in {"record_sha256", "current_revision"}
    }
    value["record_sha256"] = digest(canonical_json(record))


def text_for(stratum: str, index: int) -> tuple[str, str]:
    values = {
        "unchanged": (f"Unchanged example {index}", f"Unchanged example {index}"),
        "capitalization_only": (
            f"capitalization example {index}",
            f"Capitalization example {index}",
        ),
        "punctuation_only": (f"Punctuation example {index}", f"Punctuation example {index}."),
        "apostrophe_only": (f"Its apostrophe example {index}", f"It's apostrophe example {index}"),
        "whitespace_or_paragraph_only": (
            f"Whitespace example {index}",
            f"Whitespace  example {index}",
        ),
        "leading_filler_only": (f"Um filler example {index}", f"filler example {index}"),
        "mixed_permitted_transformations": (
            f"mixed example {index}",
            f"Mixed example {index}.",
        ),
    }
    return values[stratum]


def case(stratum: str, index: int, *, case_id: str | None = None) -> dict[str, object]:
    source, expected = text_for(stratum, index)
    prompt = "Synthetic source-preserving prompt."
    value: dict[str, object] = {
        "case_id": case_id or f"case-{stratum}-{index:03}",
        "contract_version": "cleanup-evaluation-corpus-v1",
        "purpose": "polished-cleanup-evaluation-only",
        "revision": 2,
        "current_revision": 2,
        "source_category": "dictation",
        "source_text": source,
        "expected_cleanup": expected,
        "source_sha256": digest(source.encode()),
        "expected_cleanup_sha256": digest(expected.encode()),
        "captured_at": (NOW - timedelta(days=2)).isoformat(),
        "confirmed_at": (NOW - timedelta(days=2)).isoformat(),
        "expires_at": (NOW + timedelta(days=20)).isoformat(),
        "original_user_confirmed": True,
        "expected_cleanup_user_confirmed": True,
        "consent": {
            "version": "cleanup-evaluation-consent-v1",
            "scope": "polished-cleanup-evaluation-only",
            "confirmed_at": (NOW - timedelta(days=2)).isoformat(),
        },
        "hold": {
            "benchmark_id": PROTOCOL_ID,
            "confirmed_at": (NOW - timedelta(hours=1)).isoformat(),
            "release_at": (NOW + timedelta(days=20)).isoformat(),
        },
        "prompt": {
            "version_id": "prompt-v1",
            "content_sha256": digest(prompt.encode()),
            "text": prompt,
        },
        "annotations": {
            "primary_stratum": stratum,
            "challenge_tags": ALL_TAGS,
            "ambiguous": False,
            "transcript_truth_dependent": False,
            "frozen_at": (NOW - timedelta(hours=2)).isoformat(),
            "corpus_owner": "owner-1",
        },
    }
    rehash_record(value)
    return value


def snapshot(*, extras_per_stratum: int = 1) -> dict[str, object]:
    cases = [
        case(stratum, index)
        for stratum, quota in PRIMARY_QUOTAS.items()
        for index in range(quota + extras_per_stratum)
    ]
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "frozen_at": (NOW - timedelta(hours=1)).isoformat(),
        "cases": cases,
    }


def registration_inputs() -> dict[str, object]:
    contract = build_cleanup_contract_snapshot(
        "Synthetic source-preserving prompt.",
        configured_prompt_id="prompt-v1",
        dependency_lock_bytes=b"synthetic-lock",
    )
    return {
        "run_id": "synthetic-run",
        "registered_at": NOW.isoformat(),
        "selection_seed": 101,
        "case_order_seed": 102,
        "arm_order_seed": 103,
        "bootstrap_seed": 104,
        "review_order_seed": 105,
        "pair_order_seed": 106,
        "pair_side_seed": 107,
        "roles": {
            "protocol_owner": "owner-1",
            "corpus_owner": "owner-1",
            "run_operator": "operator-1",
        },
        "environment": {"identity": "isolated-pilot-1", "stable_resources_inaccessible": True},
        "code": {
            "runner_commit": "a" * 40,
            "scoring_commit": "b" * 40,
            "dependency_lock_sha256": contract["artifacts"]["dependency_lock"]["sha256"],
            "clean_tree": True,
        },
        "cleanup_contract": contract,
        "provider_evidence": {
            "retrieved_at": NOW.isoformat(),
            "material_change": False,
            "official_urls": ["https://example.test/provider"],
            "availability": {"gemini": True, "openai": True},
            "pricing_usd_micros": {"gemini": 1, "openai": 2},
            "retention_and_data_use": "synthetic disclosure",
            "account_controls": "synthetic controls",
            "openai_store_false": "verified",
        },
        "smoke": {
            "fixture_count": 8,
            "call_count": 16,
            "all_passed": True,
            "fixtures_sha256": "d" * 64,
            "results_sha256": "e" * 64,
        },
        "scoring": {"normalization": ["unicode_nfc", "lf_line_endings"]},
        "review": {"rubric_sha256": "f" * 64, "harm_taxonomy": ["none", "meaning"]},
        "budget": {
            "total_usd_micros": 10_000_000,
            "private_call_reservation": 120,
            "conservative_bound_usd_micros": 9_000_000,
            "pre_send_stop": True,
        },
        "run_confirmation": {
            "confirmed": True,
            "confirmed_at": NOW.isoformat(),
            "hold_release_at": (NOW + timedelta(days=20)).isoformat(),
            "disclosures": "synthetic-current-disclosures",
        },
        "storage": {"inventory": ["snapshot", "run", "report"], "locations_confirmed": True},
        "lifecycle": {"write_back_to_live_corpus": False, "delete_at_fixed_release": True},
    }


def test_registration_is_deterministic_and_satisfies_every_exact_and_overlapping_quota() -> None:
    corpus = snapshot(extras_per_stratum=2)
    inputs = registration_inputs()

    first = register_cleanup_benchmark(corpus, inputs)
    second = register_cleanup_benchmark(deepcopy(corpus), deepcopy(inputs))

    assert first == second
    assert first["manifest_sha256"] == digest(canonical_json(first["manifest"]))
    selected = first["manifest"]["corpus"]["selected_cases"]
    assert len(selected) == 60
    assert Counter(item["primary_stratum"] for item in selected) == Counter(PRIMARY_QUOTAS)
    challenge_counts = Counter(tag for item in selected for tag in item["challenge_tags"])
    assert all(challenge_counts[tag] >= minimum for tag, minimum in CHALLENGE_MINIMA.items())
    assert first["manifest"]["request_contract"] == inputs["cleanup_contract"]
    assert len(first["manifest"]["ordering"]["case_order"]) == 60
    assert all(
        sorted(order) == ["baseline_paid_gemini", "candidate_paid_openai"]
        for order in first["manifest"]["ordering"]["arm_order"].values()
    )


def test_registration_rejects_an_incomplete_or_modified_cleanup_contract() -> None:
    corpus = snapshot()
    incomplete = registration_inputs()
    incomplete["cleanup_contract"] = {"protocol_id": PROTOCOL_ID}
    modified = registration_inputs()
    modified["cleanup_contract"]["arms"][0]["request"]["model"] = "other-model"

    with pytest.raises(RegistrationError, match="frozen protocol schema"):
        register_cleanup_benchmark(corpus, incomplete)
    with pytest.raises(RegistrationError, match="frozen protocol schema"):
        register_cleanup_benchmark(corpus, modified)


def test_duplicate_nfc_lf_tie_uses_lowest_id_but_preserves_selected_record_hash() -> None:
    corpus = snapshot(extras_per_stratum=0)
    original = corpus["cases"][0]
    duplicate = deepcopy(original)
    duplicate["case_id"] = "000-lowest-opaque-id"
    record = {
        key: value
        for key, value in duplicate.items()
        if key not in {"record_sha256", "current_revision"}
    }
    duplicate["record_sha256"] = digest(canonical_json(record))
    corpus["cases"].append(duplicate)

    registration = register_cleanup_benchmark(corpus, registration_inputs())
    selected = registration["manifest"]["corpus"]["selected_cases"]

    selected_ids = {item["case_id"] for item in selected}
    assert duplicate["case_id"] in selected_ids
    assert original["case_id"] not in selected_ids
    selected_duplicate = next(item for item in selected if item["case_id"] == duplicate["case_id"])
    assert selected_duplicate["record_sha256"] == duplicate["record_sha256"]


def test_duplicate_detection_canonicalizes_only_nfc_and_line_endings() -> None:
    corpus = snapshot(extras_per_stratum=1)
    first = case("whitespace_or_paragraph_only", 700, case_id="canonical-z")
    first["source_text"] = "Canonical\r\nexample 700"
    first["expected_cleanup"] = "Canonical example 700"
    first["source_sha256"] = digest(first["source_text"].encode())
    first["expected_cleanup_sha256"] = digest(first["expected_cleanup"].encode())
    rehash_record(first)
    second = deepcopy(first)
    second["case_id"] = "canonical-a"
    second["source_text"] = "Canonical\nexample 700"
    second["source_sha256"] = digest(second["source_text"].encode())
    rehash_record(second)
    corpus["cases"].extend([first, second])

    registration = register_cleanup_benchmark(corpus, registration_inputs())
    duplicate = next(
        decision
        for decision in registration["manifest"]["corpus"]["duplicate_decisions"]
        if decision.get("representative_case_id") == "canonical-a"
    )

    assert duplicate["case_ids"] == ["canonical-a", "canonical-z"]
    assert _nfc_lf("Cafe\u0301\r\n") == "Café\n"


def test_duplicate_detection_does_not_canonicalize_case_or_whitespace() -> None:
    corpus = snapshot(extras_per_stratum=1)
    for case_id, text in (
        ("boundary-upper", "Boundary value"),
        ("boundary-lower", "boundary value"),
        ("boundary-spaces", "Boundary  value"),
    ):
        item = case("unchanged", 701, case_id=case_id)
        item["source_text"] = text
        item["expected_cleanup"] = text
        item["source_sha256"] = digest(text.encode())
        item["expected_cleanup_sha256"] = digest(text.encode())
        rehash_record(item)
        corpus["cases"].append(item)

    registration = register_cleanup_benchmark(corpus, registration_inputs())
    decisions = registration["manifest"]["corpus"]["duplicate_decisions"]

    boundary_groups = [
        decision["case_ids"]
        for decision in decisions
        if any(case_id.startswith("boundary-") for case_id in decision["case_ids"])
    ]
    assert sorted(boundary_groups) == [
        ["boundary-lower"],
        ["boundary-spaces"],
        ["boundary-upper"],
    ]


def test_asymmetric_challenge_pool_forces_feasible_cases_without_relaxing_quotas() -> None:
    corpus = snapshot(extras_per_stratum=1)
    required = [
        item
        for item in corpus["cases"]
        if int(item["case_id"].rsplit("-", 1)[1])
        < PRIMARY_QUOTAS[item["annotations"]["primary_stratum"]]
    ][:12]
    for item in corpus["cases"]:
        item["annotations"]["challenge_tags"] = []
        rehash_record(item)
    for item in required:
        item["annotations"]["challenge_tags"] = ALL_TAGS
        rehash_record(item)

    registration = register_cleanup_benchmark(corpus, registration_inputs())
    selected_ids = {
        item["case_id"] for item in registration["manifest"]["corpus"]["selected_cases"]
    }

    assert {item["case_id"] for item in required} <= selected_ids


def test_conflicting_duplicate_group_is_excluded_and_infeasible_quota_blocks_registration() -> None:
    corpus = snapshot(extras_per_stratum=0)
    original = next(
        item
        for item in corpus["cases"]
        if item["annotations"]["primary_stratum"] == "punctuation_only"
    )
    conflicting = deepcopy(original)
    conflicting["case_id"] = "conflicting-copy"
    conflicting["expected_cleanup"] = conflicting["source_text"] + "!"
    conflicting["expected_cleanup_sha256"] = digest(conflicting["expected_cleanup"].encode())
    record = {
        key: value
        for key, value in conflicting.items()
        if key not in {"record_sha256", "current_revision"}
    }
    conflicting["record_sha256"] = digest(canonical_json(record))
    corpus["cases"].append(conflicting)

    with pytest.raises(RegistrationError, match="cannot satisfy"):
        register_cleanup_benchmark(corpus, registration_inputs())


@pytest.mark.parametrize(
    ("expected", "reason"),
    [
        ("Novel addition here", "impermissible_word_or_symbol_operation"),
        ("Example unchanged 900", "impermissible_word_or_symbol_operation"),
        ("900 example Unchanged", "impermissible_word_or_symbol_operation"),
        ("Unchanged example", "impermissible_word_or_symbol_operation"),
    ],
)
def test_word_addition_substitution_reordering_and_nonleading_removal_are_ineligible(
    expected: str, reason: str
) -> None:
    corpus = snapshot(extras_per_stratum=1)
    rejected = case("unchanged", 900, case_id="rejected-case")
    rejected["expected_cleanup"] = expected
    rejected["expected_cleanup_sha256"] = digest(expected.encode())
    record = {
        key: value
        for key, value in rejected.items()
        if key not in {"record_sha256", "current_revision"}
    }
    rejected["record_sha256"] = digest(canonical_json(record))
    corpus["cases"].append(rejected)

    registration = register_cleanup_benchmark(corpus, registration_inputs())

    decisions = registration["manifest"]["corpus"]["eligibility_decisions"]
    assert {"case_id": "rejected-case", "decision": reason} in decisions


def test_unchanged_symbols_are_eligible_but_symbol_changes_are_not() -> None:
    corpus = snapshot(extras_per_stratum=1)
    unchanged = case("unchanged", 901, case_id="unchanged-symbols")
    unchanged_text = "Keep https://example.test?a=1 and total=$5"
    unchanged["source_text"] = unchanged_text
    unchanged["expected_cleanup"] = unchanged_text
    unchanged["source_sha256"] = digest(unchanged_text.encode())
    unchanged["expected_cleanup_sha256"] = digest(unchanged_text.encode())
    rehash_record(unchanged)
    changed = case("unchanged", 902, case_id="changed-symbol")
    changed["source_text"] = "Identifier x=1"
    changed["expected_cleanup"] = "Identifier x+1"
    changed["source_sha256"] = digest(changed["source_text"].encode())
    changed["expected_cleanup_sha256"] = digest(changed["expected_cleanup"].encode())
    rehash_record(changed)
    corpus["cases"].extend([unchanged, changed])

    registration = register_cleanup_benchmark(corpus, registration_inputs())
    decisions = registration["manifest"]["corpus"]["eligibility_decisions"]

    assert {"case_id": "unchanged-symbols", "decision": "eligible"} in decisions
    assert {
        "case_id": "changed-symbol",
        "decision": "impermissible_word_or_symbol_operation",
    } in decisions


def test_snapshot_change_invalidates_before_calls_and_stops_after_a_call() -> None:
    corpus = snapshot()
    registration = register_cleanup_benchmark(corpus, registration_inputs())
    changed = deepcopy(corpus)
    changed["frozen_at"] = (NOW - timedelta(minutes=30)).isoformat()

    assert validate_registration(registration, corpus) == {"status": "valid", "reason": "unchanged"}
    assert validate_registration(registration, changed) == {
        "status": "invalidate_and_reregister",
        "reason": "corpus_changed_after_registration",
    }
    assert validate_registration(registration, changed, provider_call_count=1) == {
        "status": "stop_and_invalidate",
        "reason": "corpus_changed_after_registration",
    }


def test_registration_errors_never_echo_private_inputs() -> None:
    corpus = snapshot(extras_per_stratum=0)
    private_text = "PRIVATE CORPUS SENTINEL"
    corpus["cases"][0]["source_text"] = private_text

    with pytest.raises(RegistrationError) as caught:
        register_cleanup_benchmark(corpus, registration_inputs())

    assert private_text not in str(caught.value)
    assert private_text not in "".join(traceback.format_exception(caught.value))


def test_command_is_provider_free_private_and_emits_only_safe_metadata(tmp_path: Path) -> None:
    private_text = "PRIVATE CORPUS SENTINEL"
    corpus = snapshot(extras_per_stratum=0)
    corpus["cases"][0]["source_text"] = private_text
    corpus["cases"][0]["expected_cleanup"] = private_text
    corpus["cases"][0]["source_sha256"] = digest(private_text.encode())
    corpus["cases"][0]["expected_cleanup_sha256"] = digest(private_text.encode())
    rehash_record(corpus["cases"][0])
    snapshot_path = tmp_path / "private-snapshot.json"
    inputs_path = tmp_path / "private-inputs.json"
    output_path = tmp_path / "private-manifest.json"
    snapshot_path.write_text(json.dumps(corpus))
    inputs_path.write_text(json.dumps(registration_inputs()))
    provider_marker = tmp_path / "provider-was-accessed"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "local_text.cleanup_evaluation_runner",
            "--snapshot",
            str(snapshot_path),
            "--inputs",
            str(inputs_path),
            "--output",
            str(output_path),
        ],
        env={
            **os.environ,
            "LOCAL_TEXT_GEMINI_API_KEY": str(provider_marker),
            "LOCAL_TEXT_OPENAI_API_KEY": str(provider_marker),
        },
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stderr == b""
    assert private_text.encode() not in result.stdout
    assert str(tmp_path).encode() not in result.stdout
    assert not provider_marker.exists()
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600
    assert json.loads(output_path.read_text())["manifest_sha256"]
