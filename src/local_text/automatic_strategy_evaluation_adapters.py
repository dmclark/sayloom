"""Evaluation-only adapters for automatic correction strategy candidates."""

import re
import unicodedata
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from local_text.automatic_strategy_evaluation import (
    AdapterRequest,
    ExecutionResult,
    ProposalScoreTrace,
    RepairTrace,
)


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


@dataclass(frozen=True)
class _PhoneticProposal:
    before: str
    after: str
    normalized_after: str
    original_start: int
    original_end: int
    phonetic: int
    context: int
    profile: int
    edit_penalty: int
    total: int


def _no_change(
    outcome: Literal["abstention", "failure"],
    *,
    proposal_scores: list[ProposalScoreTrace] | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        outcome=outcome,
        prepared_text=None,
        selected_method=None,
        repairs=[],
        proposal_scores=proposal_scores or [],
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


def _configured_boolean(request: AdapterRequest, name: str) -> bool:
    value = request.candidate_configuration.routing.get(name)
    if not isinstance(value, bool):
        raise ValueError(f"invalid phonetic candidate setting: {name}")
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


_PHONETIC_ROUTING_KEYS = {
    "policy",
    "version",
    "use_context",
    "use_profile",
    "maximum_original_words",
    "maximum_context_words",
    "maximum_profile_entries",
    "maximum_term_characters",
    "maximum_edit_distance",
    "maximum_proposals",
    "maximum_context_occurrences",
    "phonetic_weight",
    "context_weight",
    "profile_weight",
    "edit_distance_weight",
    "minimum_score",
    "minimum_score_margin",
    "maximum_repairs",
}


def _phonetic_normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character) and "a" <= character <= "z"
    )


def _soundex(text: str) -> str | None:
    normalized = _phonetic_normalized(text)
    if not normalized:
        return None
    codes = {
        **dict.fromkeys("bfpv", "1"),
        **dict.fromkeys("cgjkqsxz", "2"),
        **dict.fromkeys("dt", "3"),
        "l": "4",
        **dict.fromkeys("mn", "5"),
        "r": "6",
    }
    previous = codes.get(normalized[0], "0")
    emitted: list[str] = []
    for character in normalized[1:]:
        code = codes.get(character, "0")
        if code != "0" and code != previous:
            emitted.append(code)
        previous = code
    return normalized[0] + "".join(emitted[:3]).ljust(3, "0")


def _score_trace(proposal: _PhoneticProposal) -> ProposalScoreTrace:
    return ProposalScoreTrace(
        after=proposal.after,
        original_start=proposal.original_start,
        original_end=proposal.original_end,
        phonetic=proposal.phonetic,
        context=proposal.context,
        profile=proposal.profile,
        edit_penalty=proposal.edit_penalty,
        total=proposal.total,
    )


def _phonetic_proposals(request: AdapterRequest) -> list[_PhoneticProposal] | None:
    routing = request.candidate_configuration.routing
    if set(routing) != _PHONETIC_ROUTING_KEYS:
        raise ValueError("phonetic candidate settings must be complete and exact")
    use_context = _configured_boolean(request, "use_context")
    use_profile = _configured_boolean(request, "use_profile")
    maximum_original_words = _configured_integer(request, "maximum_original_words", minimum=1)
    maximum_context_words = _configured_integer(request, "maximum_context_words", minimum=1)
    maximum_profile_entries = _configured_integer(
        request, "maximum_profile_entries", minimum=1
    )
    maximum_term_characters = _configured_integer(
        request, "maximum_term_characters", minimum=1
    )
    maximum_edit_distance = _configured_integer(request, "maximum_edit_distance", minimum=0)
    maximum_proposals = _configured_integer(request, "maximum_proposals", minimum=1)
    if maximum_proposals > 64:
        raise ValueError("phonetic proposal trace permits at most 64 proposals")
    maximum_context_occurrences = _configured_integer(
        request, "maximum_context_occurrences", minimum=1
    )
    phonetic_weight = _configured_integer(request, "phonetic_weight", minimum=1)
    context_weight = _configured_integer(request, "context_weight", minimum=1)
    profile_weight = _configured_integer(request, "profile_weight", minimum=1)
    edit_distance_weight = _configured_integer(request, "edit_distance_weight", minimum=1)
    minimum_score = _configured_integer(request, "minimum_score", minimum=0)
    _configured_integer(request, "minimum_score_margin", minimum=1)
    if _configured_integer(request, "maximum_repairs", minimum=1) != 1:
        raise ValueError("phonetic candidate emits exactly one repair")

    original_words = _words(request.original)
    context_words = _words(request.request_context) if use_context else []
    profile_entries = request.enabled_profile_evidence if use_profile else ()
    if (
        not original_words
        or len(original_words) > maximum_original_words
        or (use_context and (not context_words or len(context_words) > maximum_context_words))
        or (
            use_profile
            and (not profile_entries or len(profile_entries) > maximum_profile_entries)
        )
        or not (use_context or use_profile)
    ):
        return None

    context_by_term: dict[str, tuple[str, int]] = {}
    for word in context_words:
        normalized = _phonetic_normalized(word.text)
        if not normalized or len(word.text) > maximum_term_characters:
            return None
        spelling, count = context_by_term.get(normalized, (word.text, 0))
        context_by_term[normalized] = (spelling, count + 1)

    profile_by_term: dict[str, str] = {}
    for entry in profile_entries:
        entry_words = _words(entry)
        if len(entry_words) != 1 or len(entry) > maximum_term_characters:
            return None
        normalized = _phonetic_normalized(entry_words[0].text)
        if not normalized:
            return None
        profile_by_term.setdefault(normalized, entry_words[0].text)

    corpus = {
        normalized: profile_by_term.get(normalized, spelling)
        for normalized, (spelling, _count) in context_by_term.items()
    }
    corpus.update(profile_by_term)
    proposals: list[_PhoneticProposal] = []
    for original in original_words:
        normalized_original = _phonetic_normalized(original.text)
        original_code = _soundex(original.text)
        if (
            not normalized_original
            or original_code is None
            or len(original.text) > maximum_term_characters
        ):
            return None
        for normalized_after, after in corpus.items():
            if normalized_after == normalized_original or _soundex(after) != original_code:
                continue
            distance = _distance(normalized_original, normalized_after)
            if distance > maximum_edit_distance:
                continue
            context_occurrences = context_by_term.get(normalized_after, ("", 0))[1]
            context_score = (
                context_weight
                * min(context_occurrences, maximum_context_occurrences)
                if use_context
                else 0
            )
            profile_score = (
                profile_weight if use_profile and normalized_after in profile_by_term else 0
            )
            if not (context_score or profile_score):
                continue
            edit_penalty = edit_distance_weight * distance
            total = phonetic_weight + context_score + profile_score - edit_penalty
            if total < minimum_score:
                continue
            proposals.append(
                _PhoneticProposal(
                    before=original.text,
                    after=after,
                    normalized_after=normalized_after,
                    original_start=original.start,
                    original_end=original.end,
                    phonetic=phonetic_weight,
                    context=context_score,
                    profile=profile_score,
                    edit_penalty=edit_penalty,
                    total=total,
                )
            )
            if len(proposals) > maximum_proposals:
                return None
    return proposals


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


def bounded_phonetic_contextual(request: AdapterRequest) -> ExecutionResult:
    """Rank one bounded phonetic repair from frozen context and profile evidence."""

    candidate = request.candidate_configuration
    if (
        candidate.kind != "component"
        or len(candidate.method_ids) != 1
        or candidate.routing.get("policy") != "bounded_phonetic_contextual"
        or candidate.routing.get("version") != "v1"
    ):
        return _no_change("failure")
    try:
        proposals = _phonetic_proposals(request)
    except (TypeError, ValueError):
        return _no_change("failure")
    if not proposals:
        return _no_change("abstention")

    ranked = sorted(
        proposals,
        key=lambda proposal: (
            -proposal.total,
            proposal.original_start,
            proposal.normalized_after,
        ),
    )
    score_trace = [_score_trace(proposal) for proposal in ranked]
    best = ranked[0]
    minimum_margin = int(candidate.routing["minimum_score_margin"])
    if (
        sum(proposal.total == best.total for proposal in ranked) > 1
        or (len(ranked) > 1 and best.total - ranked[1].total < minimum_margin)
    ):
        return _no_change("abstention", proposal_scores=score_trace)

    prepared = (
        request.original[: best.original_start]
        + best.after
        + request.original[best.original_end :]
    )
    return ExecutionResult(
        outcome="success",
        prepared_text=prepared,
        selected_method=candidate.method_ids[0],
        repairs=[
            RepairTrace(
                before=best.before,
                after=best.after,
                original_start=best.original_start,
                original_end=best.original_end,
                prepared_start=best.original_start,
                prepared_end=best.original_start + len(best.after),
                uncertain=False,
            )
        ],
        proposal_scores=score_trace,
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
        "bounded-phonetic-contextual-v1": bounded_phonetic_contextual,
        "deterministic-lexical-v1": deterministic_lexical,
    }
)
