"""Evaluation-only adapters for automatic correction strategy candidates."""

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from local_text.automatic_strategy_evaluation import AdapterRequest, ExecutionResult, RepairTrace


@dataclass(frozen=True)
class _Word:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class _Proposal:
    before: str
    after: str
    original_start: int
    original_end: int
    distance: int
    profile_index: int


def _no_change(outcome: Literal["abstention", "failure"]) -> ExecutionResult:
    return ExecutionResult(
        outcome=outcome,
        prepared_text=None,
        selected_method=None,
        repairs=[],
        internal_retries=0,
        latency_ms=0,
        provider_calls=0,
        input_tokens=0,
        output_tokens=0,
        cost_usd_micros=0,
    )


def abstain(_request: AdapterRequest) -> ExecutionResult:
    """Deterministically preserve Original through the harness fail-open path."""

    return _no_change("abstention")


def _configured_integer(request: AdapterRequest, name: str, *, minimum: int) -> int:
    value = request.candidate_configuration.routing.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"invalid lexical candidate setting: {name}")
    return value


def _words(text: str) -> list[_Word]:
    return [
        _Word(match.group(), match.start(), match.end())
        for match in re.finditer(r"\w+(?:[’']\w+)*", text, flags=re.UNICODE)
    ]


def _normalized(text: str) -> str:
    return " ".join(word.text.casefold() for word in _words(text))


def _distance(left: str, right: str) -> int:
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


def _lexical_proposals(request: AdapterRequest) -> list[_Proposal]:
    maximum_profile_terms = _configured_integer(request, "maximum_profile_terms", minimum=1)
    maximum_term_tokens = _configured_integer(request, "maximum_term_tokens", minimum=1)
    maximum_term_characters = _configured_integer(
        request, "maximum_term_characters", minimum=1
    )
    maximum_edit_distance = _configured_integer(request, "maximum_edit_distance", minimum=0)
    minimum_term_characters = _configured_integer(request, "minimum_term_characters", minimum=1)
    maximum_repairs = _configured_integer(request, "maximum_repairs", minimum=1)
    original_words = _words(request.original)
    by_span: dict[tuple[int, int], list[_Proposal]] = {}
    seen_terms: set[str] = set()

    for profile_index, preferred_term in enumerate(
        request.enabled_profile_evidence[:maximum_profile_terms]
    ):
        if len(preferred_term) > maximum_term_characters:
            continue
        normalized_term = _normalized(preferred_term)
        term_words = _words(preferred_term)
        if (
            not normalized_term
            or normalized_term in seen_terms
            or len(normalized_term.replace(" ", "")) < minimum_term_characters
            or len(term_words) > maximum_term_tokens
        ):
            continue
        seen_terms.add(normalized_term)
        width = len(term_words)
        for start_index in range(len(original_words) - width + 1):
            end_index = start_index + width
            original_start = original_words[start_index].start
            original_end = original_words[end_index - 1].end
            before = request.original[original_start:original_end]
            if len(before) > maximum_term_characters or before == preferred_term:
                continue
            distance = _distance(_normalized(before), normalized_term)
            if distance <= maximum_edit_distance:
                by_span.setdefault((original_start, original_end), []).append(
                    _Proposal(
                        before=before,
                        after=preferred_term,
                        original_start=original_start,
                        original_end=original_end,
                        distance=distance,
                        profile_index=profile_index,
                    )
                )

    unambiguous: list[_Proposal] = []
    for proposals in by_span.values():
        best_distance = min(proposal.distance for proposal in proposals)
        best = [proposal for proposal in proposals if proposal.distance == best_distance]
        if len({proposal.after for proposal in best}) == 1:
            unambiguous.append(min(best, key=lambda proposal: proposal.profile_index))
    selected: list[_Proposal] = []
    for proposal in sorted(
        unambiguous,
        key=lambda item: (item.distance, item.original_start, item.profile_index),
    ):
        if any(
            proposal.original_start < existing.original_end
            and existing.original_start < proposal.original_end
            for existing in selected
        ):
            continue
        selected.append(proposal)
        if len(selected) == maximum_repairs:
            break
    return sorted(selected, key=lambda proposal: proposal.original_start)


def deterministic_lexical(request: AdapterRequest) -> ExecutionResult:
    """Repair unambiguous lexical matches using only explicitly enabled preferred terms."""

    candidate = request.candidate_configuration
    if (
        candidate.kind != "component"
        or len(candidate.method_ids) != 1
        or candidate.routing.get("policy") != "deterministic_lexical"
        or candidate.routing.get("version") != "v1"
    ):
        return _no_change("failure")
    try:
        proposals = _lexical_proposals(request)
    except (TypeError, ValueError):
        return _no_change("failure")
    if not proposals:
        return _no_change("abstention")

    prepared_parts: list[str] = []
    repairs: list[RepairTrace] = []
    original_cursor = 0
    prepared_cursor = 0
    for proposal in proposals:
        unchanged = request.original[original_cursor : proposal.original_start]
        prepared_parts.extend((unchanged, proposal.after))
        prepared_start = prepared_cursor + len(unchanged)
        repairs.append(
            RepairTrace(
                before=proposal.before,
                after=proposal.after,
                original_start=proposal.original_start,
                original_end=proposal.original_end,
                prepared_start=prepared_start,
                prepared_end=prepared_start + len(proposal.after),
                uncertain=False,
            )
        )
        original_cursor = proposal.original_end
        prepared_cursor = prepared_start + len(proposal.after)
    prepared_parts.append(request.original[original_cursor:])
    return ExecutionResult(
        outcome="success",
        prepared_text="".join(prepared_parts),
        selected_method=candidate.method_ids[0],
        repairs=repairs,
        internal_retries=0,
        latency_ms=0,
        provider_calls=0,
        input_tokens=0,
        output_tokens=0,
        cost_usd_micros=0,
    )


EVALUATION_ADAPTERS = MappingProxyType(
    {
        "abstention-v1": abstain,
        "deterministic-lexical-v1": deterministic_lexical,
    }
)
