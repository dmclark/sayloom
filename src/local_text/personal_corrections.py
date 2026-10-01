"""Owner-scoped persistence for the local Personal corrections profile."""

import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from local_text.database import ApplicationDatabase
from local_text.models import (
    PersonalCorrectionAlias,
    PersonalCorrectionEntry,
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
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise PersonalCorrectionError(f"{field} contains a control character")
    return value


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


class PersonalCorrectionStore:
    def __init__(self, database: ApplicationDatabase) -> None:
        self.database = database

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
            )

    def set_profile_enabled(self, enabled: bool) -> PersonalCorrectionProfileRecord:
        with self.database.session_factory.begin() as session:
            profile = session.get(PersonalCorrectionProfile, LOCAL_OWNER_ID)
            if profile is None:
                if not enabled:
                    return PersonalCorrectionProfileRecord(enabled=False)
                now = utc_now()
                profile = PersonalCorrectionProfile(
                    owner_id=LOCAL_OWNER_ID,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
                session.add(profile)
            else:
                profile.enabled = enabled
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
            )

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
                if session.get(PersonalCorrectionProfile, LOCAL_OWNER_ID) is None:
                    raise PersonalCorrectionError("Personal corrections must be enabled first")
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
