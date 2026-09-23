"""Durable prompt versions, activation, settings, seed, and import writes."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from local_text.cleanup import PreparationMode
from local_text.database import ApplicationDatabase
from local_text.models import (
    ActivePrompt,
    AppSetting,
    ImportRun,
    PromptVersion,
    SeedRelease,
    utc_now,
)
from local_text.prompts import DEFAULT_PROMPT_TITLE, DEFAULT_SEED_RELEASE, DEFAULT_SYSTEM_PROMPT

PREPARATION_DEFAULT_SETTING = "preparation_default"


class PromptNotFoundError(LookupError):
    pass


class SeedStateError(RuntimeError):
    pass


class ImportAlreadyCompletedError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromptRecord:
    id: int
    version: int
    title: str
    system_text: str
    source: str
    content_sha256: str
    created_at: datetime


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _record(prompt: PromptVersion) -> PromptRecord:
    return PromptRecord(
        id=prompt.id,
        version=prompt.version,
        title=prompt.title,
        system_text=prompt.system_text,
        source=prompt.source,
        content_sha256=prompt.content_sha256,
        created_at=prompt.created_at,
    )


class PromptStore:
    def __init__(self, database: ApplicationDatabase) -> None:
        self.database = database

    def seed_default(self) -> bool:
        digest = content_sha256(DEFAULT_SYSTEM_PROMPT)
        with self.database.session_factory.begin() as session:
            release = session.get(SeedRelease, DEFAULT_SEED_RELEASE)
            if release is not None:
                if release.content_sha256 != digest:
                    raise SeedStateError("seed release content does not match the bundled release")
                seeded_prompt = session.get(PromptVersion, release.prompt_version_id)
                if seeded_prompt is None or seeded_prompt.content_sha256 != digest:
                    raise SeedStateError("seed release prompt is missing or invalid")
                return False

            count = session.scalar(select(func.count()).select_from(PromptVersion))
            if count:
                raise SeedStateError("default seed cannot be applied after prompt versions exist")

            prompt = PromptVersion(
                version=1,
                title=DEFAULT_PROMPT_TITLE,
                system_text=DEFAULT_SYSTEM_PROMPT,
                source="seed",
                content_sha256=digest,
                created_at=utc_now(),
            )
            session.add(prompt)
            session.flush()
            session.add(
                ActivePrompt(
                    id=1,
                    prompt_version_id=prompt.id,
                    activated_at=utc_now(),
                )
            )
            session.add(
                AppSetting(
                    key=PREPARATION_DEFAULT_SETTING,
                    value_json=json.dumps(PreparationMode.CONSERVATIVE.value),
                    updated_at=utc_now(),
                )
            )
            session.add(
                SeedRelease(
                    release_id=DEFAULT_SEED_RELEASE,
                    prompt_version_id=prompt.id,
                    content_sha256=digest,
                    applied_at=utc_now(),
                )
            )
        return True

    def history(self) -> tuple[list[PromptRecord], int]:
        with self.database.session_factory() as session:
            prompts = session.scalars(
                select(PromptVersion).order_by(PromptVersion.version.desc())
            ).all()
            active = session.get(ActivePrompt, 1)
            if active is None:
                raise SeedStateError("active prompt selection is missing")
            return [_record(prompt) for prompt in prompts], active.prompt_version_id

    def active(self) -> PromptRecord:
        with self.database.session_factory() as session:
            active = session.get(ActivePrompt, 1)
            if active is None:
                raise SeedStateError("active prompt selection is missing")
            prompt = session.get(PromptVersion, active.prompt_version_id)
            if prompt is None:
                raise SeedStateError("active prompt version is missing")
            return _record(prompt)

    def get(self, prompt_version_id: int) -> PromptRecord:
        with self.database.session_factory() as session:
            prompt = session.get(PromptVersion, prompt_version_id)
            if prompt is None:
                raise PromptNotFoundError(f"prompt version {prompt_version_id} does not exist")
            return _record(prompt)

    def create(self, *, title: str, system_text: str, activate: bool) -> PromptRecord:
        with self.database.session_factory.begin() as session:
            next_version = (session.scalar(select(func.max(PromptVersion.version))) or 0) + 1
            prompt = PromptVersion(
                version=next_version,
                title=title,
                system_text=system_text,
                source="custom",
                content_sha256=content_sha256(system_text),
                created_at=utc_now(),
            )
            session.add(prompt)
            session.flush()
            if activate:
                self._activate(session, prompt.id)
            record = _record(prompt)
        return record

    def activate(self, prompt_version_id: int) -> PromptRecord:
        with self.database.session_factory.begin() as session:
            prompt = session.get(PromptVersion, prompt_version_id)
            if prompt is None:
                raise PromptNotFoundError(f"prompt version {prompt_version_id} does not exist")
            self._activate(session, prompt.id)
            record = _record(prompt)
        return record

    def preparation_default(self) -> PreparationMode:
        with self.database.session_factory() as session:
            setting = session.get(AppSetting, PREPARATION_DEFAULT_SETTING)
            if setting is None:
                raise SeedStateError("preparation default setting is missing")
            try:
                return PreparationMode(json.loads(setting.value_json))
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                raise SeedStateError("preparation default setting is invalid") from exc

    def set_preparation_default(self, value: PreparationMode) -> None:
        with self.database.session_factory.begin() as session:
            setting = session.get(AppSetting, PREPARATION_DEFAULT_SETTING)
            if setting is None:
                raise SeedStateError("preparation default setting is missing")
            setting.value_json = json.dumps(value.value)
            setting.updated_at = utc_now()

    def import_configuration(
        self,
        *,
        source_fingerprint: str,
        preview_digest: str,
        prompt_text: str | None,
        preparation_default: PreparationMode | None,
    ) -> PromptRecord | None:
        with self.database.session_factory.begin() as session:
            if session.get(ActivePrompt, 1) is None:
                raise SeedStateError("default seed must be applied before configuration import")
            setting = session.get(AppSetting, PREPARATION_DEFAULT_SETTING)
            if setting is None:
                raise SeedStateError("default seed must be applied before configuration import")
            if session.scalar(select(func.count()).select_from(ImportRun)):
                raise ImportAlreadyCompletedError("legacy configuration import is already complete")

            imported_prompt: PromptVersion | None = None
            if prompt_text is not None:
                next_version = (session.scalar(select(func.max(PromptVersion.version))) or 0) + 1
                imported_prompt = PromptVersion(
                    version=next_version,
                    title="Imported configuration",
                    system_text=prompt_text,
                    source="import",
                    content_sha256=content_sha256(prompt_text),
                    created_at=utc_now(),
                )
                session.add(imported_prompt)
                session.flush()
                self._activate(session, imported_prompt.id)

            if preparation_default is not None:
                setting.value_json = json.dumps(preparation_default.value)
                setting.updated_at = utc_now()

            session.add(
                ImportRun(
                    id=1,
                    source_fingerprint=source_fingerprint,
                    preview_digest=preview_digest,
                    completed_at=utc_now(),
                )
            )
            record = _record(imported_prompt) if imported_prompt is not None else None
        return record

    @staticmethod
    def _activate(session: Session, prompt_version_id: int) -> None:
        active = session.get(ActivePrompt, 1)
        if active is None:
            session.add(
                ActivePrompt(
                    id=1,
                    prompt_version_id=prompt_version_id,
                    activated_at=utc_now(),
                )
            )
        else:
            active.prompt_version_id = prompt_version_id
            active.activated_at = utc_now()
