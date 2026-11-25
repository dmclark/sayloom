"""Owner-scoped persistence for the local Personal corrections profile."""

import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError

from local_text.cleanup import lexical_repairs
from local_text.database import ApplicationDatabase
from local_text.models import (
    PersonalCorrectionAlias,
    PersonalCorrectionEntry,
    PersonalCorrectionEpisode,
    PersonalCorrectionEpisodeMapping,
    PersonalCorrectionEvent,
    PersonalCorrectionProfile,
    utc_now,
)

LOCAL_OWNER_ID = "local"


class PersonalCorrectionError(ValueError):
    pass


class PersonalCorrectionNotFoundError(PersonalCorrectionError):
    pass


class PersonalCorrectionRevisionConflictError(PersonalCorrectionError):
    pass


class PersonalCorrectionConflictError(PersonalCorrectionError):
    pass


class ApprovalSpan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    start: int = Field(ge=0, le=200)
    end: int = Field(ge=0, le=200)


class ReviewedReplacement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation: Literal["replacement"]
    reusable_before_text: str
    reusable_intended_text: str
    before_change_span: ApprovalSpan
    after_change_span: ApprovalSpan
    source_start: int | None = Field(default=None, ge=0, le=100_000)
    source_end: int | None = Field(default=None, ge=0, le=100_000)

    @model_validator(mode="after")
    def validate_replacement(self):
        before = _validated_text(self.reusable_before_text, maximum=200, field="before phrase")
        after = _validated_text(self.reusable_intended_text, maximum=200, field="intended phrase")
        repairs = lexical_repairs(before, after)
        if self.operation != "replacement" or len(repairs) != 1:
            raise ValueError("one replacement is required")
        repair = repairs[0]
        b, a = self.before_change_span, self.after_change_span
        if (
            repair.operation != "replacement"
            or not 0 <= b.start < b.end <= len(before)
            or not 0 <= a.start < a.end <= len(after)
            or b.start > repair.original_span.start
            or b.end < repair.original_span.end
            or a.start > repair.prepared_span.start
            or a.end < repair.prepared_span.end
            or before[: b.start] != after[: a.start]
            or before[b.end :] != after[a.end :]
            or before[: b.start] + after[a.start : a.end] + before[b.end :] != after
        ):
            raise ValueError("invalid replacement spans")
        if (self.source_start is None) != (self.source_end is None):
            raise ValueError("incomplete source range")
        if self.source_start is not None and self.source_end - self.source_start != len(before):
            raise ValueError("source range must match before phrase length")
        return self


class ReviewedApproval(BaseModel):
    """Bounded immutable v2 input, validated equally at HTTP and store boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    approval_id: str
    review_id: str
    correction_contract_version: Literal["personal-correction-v2"]
    source_kind: Literal["original_selection", "manual_prepared"]
    source_mode: Literal["user_confirmed"]
    prompt_version_id: None = None
    application_instance_id: str
    expected_authorization_generation: int = Field(ge=0)
    passage_id: str
    draft_revision: int = Field(ge=0, le=2**63 - 1)
    selection_start: int | None = Field(default=None, ge=0, le=100_000)
    selection_end: int | None = Field(default=None, ge=0, le=100_000)
    prepared_id: str | None = None
    prepared_generation: int | None = Field(default=None, ge=0, le=2**63 - 1)
    confirmation_id: str | None = None
    mappings: tuple[ReviewedReplacement, ...] = Field(min_length=1, max_length=20, strict=False)
    applicability_context: str | None = None
    observed_sentence: str | None = None
    intended_sentence: str | None = None

    @model_validator(mode="after")
    def validate_approval(self):
        for value in (
            self.approval_id,
            self.review_id,
            self.application_instance_id,
            self.passage_id,
            self.prepared_id,
            self.confirmation_id,
        ):
            if value is not None and (len(value) != 36 or str(UUID(value)) != value):
                raise ValueError("binding identifiers must be canonical UUIDs")
        if self.source_kind == "original_selection":
            if (
                self.selection_start is None
                or self.selection_end is None
                or self.selection_end <= self.selection_start
                or self.prepared_id is not None
                or self.prepared_generation is not None
                or self.confirmation_id is not None
            ):
                raise ValueError("invalid Original binding")
            previous_end = 0
            for mapping in self.mappings:
                if (
                    mapping.source_start is None
                    or mapping.source_end is None
                    or mapping.source_start < previous_end
                    or mapping.source_start < self.selection_start
                    or mapping.source_end > self.selection_end
                ):
                    raise ValueError("invalid ordered Original source ranges")
                previous_end = mapping.source_end
        elif self.source_kind == "manual_prepared":
            if (
                self.selection_start is not None
                or self.selection_end is not None
                or self.prepared_id is None
                or self.prepared_generation is None
                or self.confirmation_id is None
                or any(m.source_start is not None for m in self.mappings)
            ):
                raise ValueError("invalid Prepared binding")
        keys = [
            (
                normalize_correction_text(m.reusable_before_text),
                normalize_correction_text(m.reusable_intended_text),
            )
            for m in self.mappings
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("equivalent selected mappings require review")
        for field in ("applicability_context", "observed_sentence", "intended_sentence"):
            value = getattr(self, field)
            if value is not None:
                _bounded_optional_text(value, field=field)
        return self


@dataclass(frozen=True)
class PersonalCorrectionAliasRecord:
    id: str
    observed_alias: str
    ambiguous: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PersonalCorrectionEntryRecord:
    id: str
    intended_term: str
    applicability_context: str | None
    enabled: bool
    revision: int
    created_at: datetime
    updated_at: datetime
    aliases: tuple[PersonalCorrectionAliasRecord, ...]


@dataclass(frozen=True)
class PersonalCorrectionProfileRecord:
    enabled: bool
    entries: tuple[PersonalCorrectionEntryRecord, ...] = ()
    authorization_generation: int = 0


@dataclass(frozen=True)
class PersonalCorrectionMappingRecord:
    ordinal: int
    operation: str
    observed_text: str
    intended_text: str


@dataclass(frozen=True)
class PersonalCorrectionApprovalRecord:
    id: str
    approval_id: str
    observed_sentence: str | None
    intended_sentence: str | None
    source_mode: str
    prompt_version_id: int | None
    correction_contract_version: str
    created_at: datetime
    mappings: tuple[PersonalCorrectionMappingRecord, ...]
    corrections: tuple[PersonalCorrectionEntryRecord, ...]


def normalize_correction_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("’", "'").casefold()
    return " ".join(normalized.split())


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _validated_text(value: str, *, maximum: int, field: str) -> str:
    if not isinstance(value, str) or not normalize_correction_text(value):
        raise PersonalCorrectionError(f"{field} must not be blank")
    if len(value) > maximum:
        raise PersonalCorrectionError(f"{field} is too long")
    if any(unicodedata.category(character) in {"Cc", "Cs"} for character in value):
        raise PersonalCorrectionError(f"{field} contains a control character")
    return value


def _bounded_optional_text(value: str | None, *, field: str) -> str | None:
    if value is None:
        return None
    if len(value) > 500 or any(unicodedata.category(c) in {"Cc", "Cs"} for c in value):
        raise PersonalCorrectionError(f"{field} is invalid")
    return value if value.strip() else None


def _validated_entry(
    intended_term: str, aliases: tuple[str, ...], applicability_context: str | None
) -> tuple[str, str, tuple[tuple[str, str], ...], str | None]:
    intended_term = _validated_text(intended_term, maximum=200, field="intended term")
    if not aliases:
        raise PersonalCorrectionError("at least one alias is required")
    validated_aliases = tuple(
        (alias, normalize_correction_text(_validated_text(alias, maximum=200, field="alias")))
        for alias in aliases
    )
    if len({key for _alias, key in validated_aliases}) != len(validated_aliases):
        raise PersonalCorrectionError("aliases must be distinct after normalization")
    context = applicability_context
    if context is not None:
        if not normalize_correction_text(context):
            context = None
        else:
            context = _validated_text(context, maximum=500, field="applicability context")
    return intended_term, normalize_correction_text(intended_term), validated_aliases, context


def _optional_text(value: str | None, *, maximum: int, field: str) -> str | None:
    if value is None or not normalize_correction_text(value):
        return None
    return _validated_text(value, maximum=maximum, field=field)


class PersonalCorrectionStore:
    def __init__(self, database: ApplicationDatabase) -> None:
        self.database = database
        self.application_instance_id = str(uuid4())

    def read(self) -> PersonalCorrectionProfileRecord:
        with self.database.session_factory() as session:
            profile = session.get(PersonalCorrectionProfile, LOCAL_OWNER_ID)
            if profile is None:
                return PersonalCorrectionProfileRecord(enabled=False)
            entries = session.scalars(
                select(PersonalCorrectionEntry)
                .where(PersonalCorrectionEntry.owner_id == LOCAL_OWNER_ID)
                .order_by(PersonalCorrectionEntry.created_at, PersonalCorrectionEntry.id)
            ).all()
            return PersonalCorrectionProfileRecord(
                enabled=profile.enabled,
                entries=self._entry_records(session, entries),
                authorization_generation=profile.authorization_generation,
            )

    def set_profile_enabled(
        self, enabled: bool, *, expected_authorization_generation: int
    ) -> PersonalCorrectionProfileRecord:
        if type(enabled) is not bool or type(expected_authorization_generation) is not int:
            raise PersonalCorrectionError("invalid profile preconditions")
        with self.database.session_factory.begin() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            profile = session.get(PersonalCorrectionProfile, LOCAL_OWNER_ID)
            if profile is None:
                raise PersonalCorrectionConflictError("profile does not exist")
            if profile.authorization_generation != expected_authorization_generation:
                raise PersonalCorrectionRevisionConflictError("profile changed")
            profile.enabled = enabled
            profile.authorization_generation += 1
            profile.updated_at = utc_now()
            session.flush()
            entries = session.scalars(
                select(PersonalCorrectionEntry)
                .where(PersonalCorrectionEntry.owner_id == LOCAL_OWNER_ID)
                .order_by(PersonalCorrectionEntry.created_at, PersonalCorrectionEntry.id)
            ).all()
            return PersonalCorrectionProfileRecord(
                enabled=profile.enabled,
                entries=self._entry_records(session, entries),
                authorization_generation=profile.authorization_generation,
            )

    def approve_reviewed_replacements(self, approval: ReviewedApproval) -> dict[str, object]:
        # Revalidate even model_construct/unchecked models at the store boundary.
        try:
            approval = ReviewedApproval.model_validate(approval.model_dump())
        except (ValidationError, PersonalCorrectionError) as exc:
            raise PersonalCorrectionError("invalid reviewed approval") from exc
        context = _bounded_optional_text(approval.applicability_context, field="restriction")
        # Canonical JSON-compatible approved fields, not normalized mapping identity.
        submitted = approval.model_dump(mode="json")
        submitted["applicability_context"] = context
        for field in ("observed_sentence", "intended_sentence"):
            # Only blank restrictions normalize to absence; sentence display wording
            # remains exact (an empty field is omitted).
            submitted[field] = submitted[field] or None
        with self.database.session_factory.begin() as session:
            # Reserve the SQLite writer before UUID, generation or identity reads.
            session.execute(text("BEGIN IMMEDIATE"))
            existing = session.scalar(
                select(PersonalCorrectionEpisode).where(
                    PersonalCorrectionEpisode.owner_id == LOCAL_OWNER_ID,
                    PersonalCorrectionEpisode.approval_id == approval.approval_id,
                )
            )
            if existing is not None:
                receipt = self._reviewed_receipt(session, existing)
                if receipt is None:
                    raise PersonalCorrectionConflictError("approval payload changed")
                # Compare only approved fields, excluding server-assigned references.
                stored = receipt["approval"]
                historical = {field: stored[field] for field in submitted if field != "mappings"}
                historical["mappings"] = [
                    {field: mapping[field] for field in ReviewedReplacement.model_fields}
                    for mapping in stored["mappings"]
                ]
                if submitted != historical:
                    raise PersonalCorrectionConflictError("approval payload changed")
                return receipt
            if approval.application_instance_id != self.application_instance_id:
                raise PersonalCorrectionConflictError("application instance changed")
            profile = session.get(PersonalCorrectionProfile, LOCAL_OWNER_ID)
            generation = profile.authorization_generation if profile else 0
            if generation != approval.expected_authorization_generation:
                raise PersonalCorrectionRevisionConflictError("authorization changed")
            now = utc_now()
            if profile is None:
                profile = PersonalCorrectionProfile(
                    owner_id=LOCAL_OWNER_ID,
                    enabled=True,
                    authorization_generation=0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(profile)
                session.flush()
            fields = {
                field: value
                for field, value in submitted.items()
                if field not in {"mappings", "expected_authorization_generation"}
            }
            episode = PersonalCorrectionEpisode(
                id=str(uuid4()),
                owner_id=LOCAL_OWNER_ID,
                created_at=now,
                authorization_generation=generation,
                **fields,
            )
            session.add(episode)
            session.flush()
            for ordinal, mapping in enumerate(approval.mappings, start=1):
                before, intended = mapping.reusable_before_text, mapping.reusable_intended_text
                before_key, intended_key = map(normalize_correction_text, (before, intended))
                entry = session.scalar(
                    select(PersonalCorrectionEntry).where(
                        PersonalCorrectionEntry.owner_id == LOCAL_OWNER_ID,
                        PersonalCorrectionEntry.operation == "replacement",
                        PersonalCorrectionEntry.before_key == before_key,
                        PersonalCorrectionEntry.intended_key == intended_key,
                        PersonalCorrectionEntry.applicability_context == context,
                    )
                )
                if entry is None:
                    entry = PersonalCorrectionEntry(
                        id=str(uuid4()),
                        owner_id=LOCAL_OWNER_ID,
                        operation="replacement",
                        reusable_before_text=before,
                        before_key=before_key,
                        intended_term=intended,
                        intended_key=intended_key,
                        applicability_context=context,
                        enabled=True,
                        revision=1,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(entry)
                    session.flush()
                    alias = PersonalCorrectionAlias(
                        id=str(uuid4()),
                        owner_id=LOCAL_OWNER_ID,
                        entry_id=entry.id,
                        observed_alias=before,
                        alias_key=before_key,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(alias)
                    session.flush()
                else:
                    alias = session.scalar(
                        select(PersonalCorrectionAlias).where(
                            PersonalCorrectionAlias.owner_id == LOCAL_OWNER_ID,
                            PersonalCorrectionAlias.entry_id == entry.id,
                            PersonalCorrectionAlias.alias_key == before_key,
                        )
                    )
                    if alias is None:
                        raise PersonalCorrectionConflictError("mapping alias changed")
                session.add(
                    PersonalCorrectionEpisodeMapping(
                        id=str(uuid4()),
                        owner_id=LOCAL_OWNER_ID,
                        episode_id=episode.id,
                        ordinal=ordinal,
                        operation="replacement",
                        observed_text=before,
                        intended_text=intended,
                        entry_id=entry.id,
                        alias_id=alias.id,
                        before_change_start=mapping.before_change_span.start,
                        before_change_end=mapping.before_change_span.end,
                        after_change_start=mapping.after_change_span.start,
                        after_change_end=mapping.after_change_span.end,
                        source_start=mapping.source_start,
                        source_end=mapping.source_end,
                    )
                )
                session.add(
                    PersonalCorrectionEvent(
                        owner_id=LOCAL_OWNER_ID,
                        entry_id=entry.id,
                        alias_id=alias.id,
                        episode_id=episode.id,
                        use_id=approval.approval_id,
                        event_type="alias_observed",
                        occurred_at=now,
                    )
                )
            session.flush()
            return self._reviewed_receipt(session, episode)

    def approval_detail(self, approval_id: str) -> dict[str, object]:
        """Read a committed v2 approval by its client UUID, not its episode ID.

        Absence only describes this database now; it cannot establish that a save
        never happened (for example, its history may have been deleted).
        """
        with self.database.session_factory() as session:
            session.execute(text("BEGIN"))
            episode = session.scalar(
                select(PersonalCorrectionEpisode).where(
                    PersonalCorrectionEpisode.owner_id == LOCAL_OWNER_ID,
                    PersonalCorrectionEpisode.approval_id == approval_id,
                )
            )
            receipt = self._reviewed_receipt(session, episode) if episode else None
            if receipt is None:
                raise PersonalCorrectionNotFoundError("approval not available")
            return receipt

    def _reviewed_receipt(self, session, episode) -> dict[str, object] | None:
        if episode.correction_contract_version != "personal-correction-v2":
            return None
        mappings = session.scalars(
            select(PersonalCorrectionEpisodeMapping)
            .where(
                PersonalCorrectionEpisodeMapping.owner_id == LOCAL_OWNER_ID,
                PersonalCorrectionEpisodeMapping.episode_id == episode.id,
            )
            .order_by(PersonalCorrectionEpisodeMapping.ordinal)
        ).all()
        fields = {
            field: getattr(episode, field)
            for field in ReviewedApproval.model_fields
            if field not in {"mappings", "expected_authorization_generation"}
        }
        entries = session.scalars(
            select(PersonalCorrectionEntry).where(
                PersonalCorrectionEntry.owner_id == LOCAL_OWNER_ID,
                PersonalCorrectionEntry.id.in_([mapping.entry_id for mapping in mappings]),
            )
        ).all()
        entries_by_id = {entry.id: entry for entry in entries}
        profile = session.get(PersonalCorrectionProfile, LOCAL_OWNER_ID)
        return {
            "approval": {
                **fields,
                "expected_authorization_generation": episode.authorization_generation,
                "id": episode.id,
                "created_at": _utc(episode.created_at),
                "mappings": [
                    {
                        "ordinal": mapping.ordinal,
                        "operation": mapping.operation,
                        "reusable_before_text": mapping.observed_text,
                        "reusable_intended_text": mapping.intended_text,
                        "before_change_span": {
                            "start": mapping.before_change_start,
                            "end": mapping.before_change_end,
                        },
                        "after_change_span": {
                            "start": mapping.after_change_start,
                            "end": mapping.after_change_end,
                        },
                        "source_start": mapping.source_start,
                        "source_end": mapping.source_end,
                        "entry_id": mapping.entry_id,
                        "alias_id": mapping.alias_id,
                    }
                    for mapping in mappings
                ],
            },
            "profile": {
                "enabled": profile.enabled if profile else False,
                "authorization_generation": profile.authorization_generation if profile else 0,
            },
            "corrections": [
                asdict(record)
                for record in self._entry_records(
                    session,
                    [entries_by_id[m.entry_id] for m in mappings if m.entry_id in entries_by_id],
                )
            ],
        }

    def create_entry(
        self,
        *,
        intended_term: str,
        aliases: tuple[str, ...],
        applicability_context: str | None,
    ) -> PersonalCorrectionEntryRecord:
        term, intended_key, validated_aliases, context = _validated_entry(
            intended_term, aliases, applicability_context
        )
        now = utc_now()
        entry = PersonalCorrectionEntry(
            id=str(uuid4()),
            owner_id=LOCAL_OWNER_ID,
            intended_term=term,
            intended_key=intended_key,
            applicability_context=context,
            enabled=True,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        try:
            with self.database.session_factory.begin() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                profile = session.get(PersonalCorrectionProfile, LOCAL_OWNER_ID)
                if profile is None:
                    raise PersonalCorrectionError("Personal corrections must be enabled first")
                profile.authorization_generation += 1
                session.add(entry)
                session.flush()
                for alias, alias_key in validated_aliases:
                    session.add(
                        PersonalCorrectionAlias(
                            id=str(uuid4()),
                            owner_id=LOCAL_OWNER_ID,
                            entry_id=entry.id,
                            observed_alias=alias,
                            alias_key=alias_key,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                session.flush()
                return self._entry_records(session, [entry])[0]
        except IntegrityError as exc:
            raise PersonalCorrectionConflictError(
                "an entry with the same normalized intended term already exists"
            ) from exc

    def approve_replacements(
        self,
        *,
        approval_id: str,
        mappings: tuple[tuple[str, str], ...],
        observed_sentence: str | None,
        intended_sentence: str | None,
        applicability_context: str | None,
        source_mode: str,
        prompt_version_id: int | None,
        correction_contract_version: str,
    ) -> tuple[PersonalCorrectionApprovalRecord, bool]:
        try:
            approval_id = str(UUID(approval_id))
        except (TypeError, ValueError) as exc:
            raise PersonalCorrectionError("approval ID must be a UUID") from exc
        if not mappings:
            raise PersonalCorrectionError("at least one replacement is required")
        mappings = tuple(
            (
                _validated_text(observed, maximum=200, field="observed text"),
                _validated_text(intended, maximum=200, field="intended text"),
            )
            for observed, intended in mappings
        )
        # Repeated occurrences authorize one reusable mapping, not duplicate events.
        unique_mappings = {}
        for observed, intended in mappings:
            key = (normalize_correction_text(observed), normalize_correction_text(intended))
            unique_mappings.setdefault(key, (observed, intended))
        mappings = tuple(unique_mappings.values())
        observed_sentence = _optional_text(
            observed_sentence, maximum=500, field="observed sentence"
        )
        intended_sentence = _optional_text(
            intended_sentence, maximum=500, field="intended sentence"
        )
        context = _optional_text(applicability_context, maximum=500, field="applicability context")
        if source_mode not in {"conservative", "smart", "user_confirmed"}:
            raise PersonalCorrectionError("source mode is invalid")
        if (source_mode == "user_confirmed" and prompt_version_id is not None) or (
            source_mode != "user_confirmed" and (prompt_version_id is None or prompt_version_id < 1)
        ):
            raise PersonalCorrectionError("prompt version is invalid")
        if correction_contract_version != "personal-correction-v1":
            raise PersonalCorrectionError("correction contract version is invalid")

        with self.database.session_factory.begin() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            existing_episode = session.scalar(
                select(PersonalCorrectionEpisode).where(
                    PersonalCorrectionEpisode.owner_id == LOCAL_OWNER_ID,
                    PersonalCorrectionEpisode.approval_id == approval_id,
                )
            )
            if existing_episode is not None:
                record = self._approval_record(session, existing_episode)
                expected = (
                    observed_sentence,
                    intended_sentence,
                    source_mode,
                    prompt_version_id,
                    correction_contract_version,
                    mappings,
                )
                actual = (
                    record.observed_sentence,
                    record.intended_sentence,
                    record.source_mode,
                    record.prompt_version_id,
                    record.correction_contract_version,
                    tuple((m.observed_text, m.intended_text) for m in record.mappings),
                )
                if actual != expected or any(
                    context and correction.applicability_context != context
                    for correction in record.corrections
                ):
                    raise PersonalCorrectionConflictError(
                        "approval ID is already bound to another correction"
                    )
                return record, False

            now = utc_now()
            profile = session.get(PersonalCorrectionProfile, LOCAL_OWNER_ID)
            if profile is None:
                profile = PersonalCorrectionProfile(
                    owner_id=LOCAL_OWNER_ID,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
                session.add(profile)
                session.flush()

            episode = PersonalCorrectionEpisode(
                id=str(uuid4()),
                owner_id=LOCAL_OWNER_ID,
                approval_id=approval_id,
                observed_sentence=observed_sentence,
                intended_sentence=intended_sentence,
                source_mode=source_mode,
                prompt_version_id=prompt_version_id,
                correction_contract_version=correction_contract_version,
                created_at=now,
            )
            session.add(episode)
            session.flush()
            for ordinal, (observed_text, intended_text) in enumerate(mappings, start=1):
                intended_key = normalize_correction_text(intended_text)
                alias_key = normalize_correction_text(observed_text)
                entry = session.scalar(
                    select(PersonalCorrectionEntry).where(
                        PersonalCorrectionEntry.owner_id == LOCAL_OWNER_ID,
                        PersonalCorrectionEntry.operation.is_(None),
                        PersonalCorrectionEntry.intended_key == intended_key,
                    )
                )
                if entry is None:
                    entry = PersonalCorrectionEntry(
                        id=str(uuid4()),
                        owner_id=LOCAL_OWNER_ID,
                        intended_term=intended_text,
                        intended_key=intended_key,
                        applicability_context=context,
                        enabled=True,
                        revision=1,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(entry)
                    session.flush()
                elif (
                    entry.applicability_context
                    and context
                    and entry.applicability_context != context
                ):
                    raise PersonalCorrectionConflictError(
                        "existing applicability context requires explicit resolution"
                    )
                elif entry.applicability_context is None and context is not None:
                    entry.applicability_context = context
                    entry.revision += 1
                    entry.updated_at = now

                alias = session.scalar(
                    select(PersonalCorrectionAlias).where(
                        PersonalCorrectionAlias.owner_id == LOCAL_OWNER_ID,
                        PersonalCorrectionAlias.entry_id == entry.id,
                        PersonalCorrectionAlias.alias_key == alias_key,
                    )
                )
                if alias is None:
                    alias = PersonalCorrectionAlias(
                        id=str(uuid4()),
                        owner_id=LOCAL_OWNER_ID,
                        entry_id=entry.id,
                        observed_alias=observed_text,
                        alias_key=alias_key,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(alias)
                    session.flush()
                session.add(
                    PersonalCorrectionEpisodeMapping(
                        id=str(uuid4()),
                        owner_id=LOCAL_OWNER_ID,
                        episode_id=episode.id,
                        ordinal=ordinal,
                        operation="replacement",
                        observed_text=observed_text,
                        intended_text=intended_text,
                        entry_id=entry.id,
                        alias_id=alias.id,
                    )
                )
                session.add(
                    PersonalCorrectionEvent(
                        owner_id=LOCAL_OWNER_ID,
                        entry_id=entry.id,
                        alias_id=alias.id,
                        episode_id=episode.id,
                        use_id=approval_id,
                        event_type="alias_observed",
                        occurred_at=now,
                    )
                )
            session.flush()
            return self._approval_record(session, episode), True

    def _approval_record(self, session, episode) -> PersonalCorrectionApprovalRecord:
        mappings = session.scalars(
            select(PersonalCorrectionEpisodeMapping)
            .where(
                PersonalCorrectionEpisodeMapping.owner_id == LOCAL_OWNER_ID,
                PersonalCorrectionEpisodeMapping.episode_id == episode.id,
            )
            .order_by(PersonalCorrectionEpisodeMapping.ordinal)
        ).all()
        entries = [session.get(PersonalCorrectionEntry, mapping.entry_id) for mapping in mappings]
        return PersonalCorrectionApprovalRecord(
            id=episode.id,
            approval_id=episode.approval_id,
            observed_sentence=episode.observed_sentence,
            intended_sentence=episode.intended_sentence,
            source_mode=episode.source_mode,
            prompt_version_id=episode.prompt_version_id,
            correction_contract_version=episode.correction_contract_version,
            created_at=_utc(episode.created_at),
            mappings=tuple(
                PersonalCorrectionMappingRecord(
                    ordinal=mapping.ordinal,
                    operation=mapping.operation,
                    observed_text=mapping.observed_text,
                    intended_text=mapping.intended_text,
                )
                for mapping in mappings
            ),
            corrections=self._entry_records(session, entries),
        )

    def update_entry(
        self,
        entry_id: str,
        *,
        expected_revision: int,
        intended_term: str,
        aliases: tuple[str, ...],
        applicability_context: str | None,
        enabled: bool,
    ) -> PersonalCorrectionEntryRecord:
        term, intended_key, validated_aliases, context = _validated_entry(
            intended_term, aliases, applicability_context
        )
        try:
            with self.database.session_factory.begin() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                existing = session.scalar(
                    select(PersonalCorrectionEntry).where(
                        PersonalCorrectionEntry.id == entry_id,
                        PersonalCorrectionEntry.owner_id == LOCAL_OWNER_ID,
                    )
                )
                if existing is not None and existing.operation is not None:
                    raise PersonalCorrectionConflictError("reviewed mapping cannot use legacy edit")
                now = utc_now()
                result = session.execute(
                    update(PersonalCorrectionEntry)
                    .where(
                        PersonalCorrectionEntry.id == entry_id,
                        PersonalCorrectionEntry.owner_id == LOCAL_OWNER_ID,
                        PersonalCorrectionEntry.revision == expected_revision,
                    )
                    .values(
                        intended_term=term,
                        intended_key=intended_key,
                        applicability_context=context,
                        enabled=enabled,
                        revision=expected_revision + 1,
                        updated_at=now,
                    )
                )
                if result.rowcount != 1:
                    entry_exists = session.scalar(
                        select(PersonalCorrectionEntry.id).where(
                            PersonalCorrectionEntry.id == entry_id,
                            PersonalCorrectionEntry.owner_id == LOCAL_OWNER_ID,
                        )
                    )
                    if entry_exists is None:
                        raise PersonalCorrectionNotFoundError(entry_id)
                    raise PersonalCorrectionRevisionConflictError(entry_id)
                profile = session.get(PersonalCorrectionProfile, LOCAL_OWNER_ID)
                profile.authorization_generation += 1
                session.execute(
                    delete(PersonalCorrectionAlias).where(
                        PersonalCorrectionAlias.entry_id == entry_id,
                        PersonalCorrectionAlias.owner_id == LOCAL_OWNER_ID,
                    )
                )
                for alias, alias_key in validated_aliases:
                    session.add(
                        PersonalCorrectionAlias(
                            id=str(uuid4()),
                            owner_id=LOCAL_OWNER_ID,
                            entry_id=entry_id,
                            observed_alias=alias,
                            alias_key=alias_key,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                session.flush()
                entry = session.scalar(
                    select(PersonalCorrectionEntry).where(
                        PersonalCorrectionEntry.id == entry_id,
                        PersonalCorrectionEntry.owner_id == LOCAL_OWNER_ID,
                    )
                )
                assert entry is not None
                return self._entry_records(session, [entry])[0]
        except IntegrityError as exc:
            raise PersonalCorrectionConflictError(
                "an entry with the same normalized intended term already exists"
            ) from exc

    @staticmethod
    def _entry_records(session, entries) -> tuple[PersonalCorrectionEntryRecord, ...]:
        if not entries:
            return ()
        entry_ids = [entry.id for entry in entries]
        aliases = session.scalars(
            select(PersonalCorrectionAlias)
            .where(
                PersonalCorrectionAlias.owner_id == LOCAL_OWNER_ID,
                PersonalCorrectionAlias.entry_id.in_(entry_ids),
            )
            .order_by(PersonalCorrectionAlias.created_at, PersonalCorrectionAlias.id)
        ).all()
        alias_counts = Counter(
            alias.alias_key
            for alias in session.scalars(
                select(PersonalCorrectionAlias).where(
                    PersonalCorrectionAlias.owner_id == LOCAL_OWNER_ID
                )
            ).all()
        )
        aliases_by_entry: dict[str, list[PersonalCorrectionAliasRecord]] = {
            entry_id: [] for entry_id in entry_ids
        }
        for alias in aliases:
            aliases_by_entry[alias.entry_id].append(
                PersonalCorrectionAliasRecord(
                    id=alias.id,
                    observed_alias=alias.observed_alias,
                    ambiguous=alias_counts[alias.alias_key] > 1,
                    created_at=_utc(alias.created_at),
                    updated_at=_utc(alias.updated_at),
                )
            )
        return tuple(
            PersonalCorrectionEntryRecord(
                id=entry.id,
                intended_term=entry.intended_term,
                applicability_context=entry.applicability_context,
                enabled=entry.enabled,
                revision=entry.revision,
                created_at=_utc(entry.created_at),
                updated_at=_utc(entry.updated_at),
                aliases=tuple(aliases_by_entry[entry.id]),
            )
            for entry in entries
        )
