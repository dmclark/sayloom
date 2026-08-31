"""Explicit consent, retention, deletion, and export for the private evaluation corpus."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, exists, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from local_text.evaluation_database import EvaluationDatabase
from local_text.evaluation_models import (
    BenchmarkHold,
    EvaluationAnnotation,
    EvaluationAttempt,
    EvaluationCase,
    EvaluationConsent,
)

CONTRACT_VERSION = "cleanup-evaluation-corpus-v1"
CONSENT_VERSION = "cleanup-evaluation-consent-v1"
EXPORT_VERSION = "cleanup-evaluation-export-v1"
CLEANUP_SCHEMA_VERSION = "cleanup-result-v1"
PURPOSE = "polished-cleanup-evaluation-only"
CAPTURE_PROOF_LIFETIME = timedelta(minutes=30)
EXPORT_PREVIEW_LIFETIME = timedelta(minutes=10)
RETENTION_PERIOD = timedelta(days=90)
UPCOMING_EXPIRY_PERIOD = timedelta(days=14)
SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
LOWERCASE_SHA256 = re.compile(r"[0-9a-f]{64}")
EXPORT_FIELDS = (
    "export_version",
    "contract_version",
    "case_id",
    "captured_at",
    "confirmed_at",
    "expires_at",
    "source_category",
    "source_text",
    "provider_output",
    "expected_cleanup",
    "cleanup",
    "consent",
    "annotations",
    "record_sha256",
)
EXPORT_WARNING = (
    "This JSONL export contains sensitive source text, provider output, expected cleanup, and "
    "prompt text. Save it only to a private local destination. Export does not share or upload it."
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _rfc3339(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_text(value: str) -> str:
    if any(ord(character) < 32 and character not in "\n\r\t" for character in value):
        raise ValueError("contains a disallowed control character")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConsentCapture(StrictModel):
    version: Literal[CONSENT_VERSION]
    scope: Literal[PURPOSE]
    confirmed: Literal[True]


class AttemptCapture(StrictModel):
    route_index: int = Field(ge=0)
    provider: str = Field(pattern=SAFE_IDENTIFIER.pattern)
    model: str = Field(pattern=SAFE_IDENTIFIER.pattern)
    outcome: Literal["success", "failure"]
    failure_class: str | None = Field(default=None, pattern=SAFE_IDENTIFIER.pattern)
    provider_code: str | None = Field(default=None, pattern=SAFE_IDENTIFIER.pattern)
    http_status: int | None = Field(default=None, ge=100, le=599)
    retry_after_seconds: int | None = Field(default=None, ge=0)
    elapsed_ms: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd_micros: int | None = Field(default=None, ge=0)
    pricing_snapshot_id: str | None = Field(default=None, pattern=SAFE_IDENTIFIER.pattern)

    @model_validator(mode="after")
    def cost_has_pricing_snapshot(self) -> AttemptCapture:
        if (self.cost_usd_micros is None) != (self.pricing_snapshot_id is None):
            raise ValueError("cost and pricing snapshot must be supplied together")
        return self


class CleanupCapture(StrictModel):
    completed_at: datetime
    provider: str = Field(pattern=SAFE_IDENTIFIER.pattern)
    model: str = Field(pattern=SAFE_IDENTIFIER.pattern)
    attempts: list[AttemptCapture]
    prompt_version_id: int = Field(ge=1)
    prompt_content_sha256: str = Field(pattern=LOWERCASE_SHA256.pattern)
    prompt_text: str = Field(max_length=100_000)
    cleanup_schema_version: Literal[CLEANUP_SCHEMA_VERSION]

    @field_validator("completed_at")
    @classmethod
    def completed_at_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("must be an RFC3339 UTC instant")
        return value.astimezone(UTC)

    @field_validator("prompt_text")
    @classmethod
    def prompt_text_is_safe(cls, value: str) -> str:
        return _validate_text(value)

    @model_validator(mode="after")
    def attempts_are_ordered_and_unique(self) -> CleanupCapture:
        route_indexes = [attempt.route_index for attempt in self.attempts]
        if route_indexes != sorted(set(route_indexes)):
            raise ValueError("attempt route indexes must be ordered and unique")
        if not any(
            attempt.outcome == "success"
            and attempt.provider == self.provider
            and attempt.model == self.model
            for attempt in self.attempts
        ):
            raise ValueError("attempts must identify the winning provider and model")
        return self


class CaseCaptureRequest(StrictModel):
    contract_version: Literal[CONTRACT_VERSION]
    capture_proof: str = Field(min_length=20, max_length=4_096)
    consent: ConsentCapture
    source_category: Literal["dictation", "typed", "pasted", "unknown"]
    source_text: str = Field(max_length=100_000)
    provider_output: str = Field(max_length=100_000)
    expected_cleanup: str = Field(max_length=100_000)
    cleanup: CleanupCapture

    @field_validator("source_text", "provider_output", "expected_cleanup")
    @classmethod
    def corpus_text_is_safe(cls, value: str) -> str:
        return _validate_text(value)


class RetentionRequest(StrictModel):
    revision: int = Field(ge=1)
    expires_at: datetime | None = None
    benchmark_id: str | None = Field(default=None, pattern=SAFE_IDENTIFIER.pattern)
    release_at: datetime | None = None

    @field_validator("expires_at", "release_at")
    @classmethod
    def timestamp_is_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("must be an RFC3339 UTC instant")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def select_one_retention_change(self) -> RetentionRequest:
        expiry_change = self.expires_at is not None
        hold_change = self.benchmark_id is not None or self.release_at is not None
        if expiry_change == hold_change:
            raise ValueError("select either an earlier expiry or one fixed benchmark hold")
        if hold_change and (self.benchmark_id is None or self.release_at is None):
            raise ValueError("benchmark ID and fixed release time are both required")
        return self


class DeleteCaseRequest(StrictModel):
    revision: int = Field(ge=1)
    confirmed: Literal[True]


class ExportSelection(StrictModel):
    case_id: UUID
    revision: int = Field(ge=1)


class ExportPreviewRequest(StrictModel):
    cases: list[ExportSelection] = Field(min_length=1)

    @model_validator(mode="after")
    def cases_are_unique(self) -> ExportPreviewRequest:
        case_ids = [selection.case_id for selection in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("export selection contains a duplicate case")
        return self


class ExportConfirmRequest(StrictModel):
    preview_token: str = Field(min_length=20, max_length=8_192)
    confirmed: Literal[True]


class EvaluationError(RuntimeError):
    def __init__(
        self, code: str, message: str, recovery_action: str, *, status_code: int = 409
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.recovery_action = recovery_action
        self.status_code = status_code

    def detail(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "retry_action": self.recovery_action,
        }


class _SignedSingleUseTokens:
    def __init__(
        self, *, secret: bytes | None = None, now: Callable[[], datetime] = utc_now
    ) -> None:
        self._secret = secret or os.urandom(32)
        self._now = now
        self._used: set[str] = set()
        self._lock = Lock()

    def _issue(self, kind: str, lifetime: timedelta, payload: dict[str, object]) -> str:
        now = self._now()
        body = {
            "kind": kind,
            "nonce": secrets.token_urlsafe(18),
            "expires_at": int((now + lifetime).timestamp()),
            **payload,
        }
        encoded = base64.urlsafe_b64encode(_canonical(body)).rstrip(b"=").decode("ascii")
        signature = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"

    def _verify_and_consume(self, token: str, kind: str) -> dict[str, object]:
        try:
            encoded, signature = token.split(".", 1)
            expected = hmac.new(
                self._secret, encoded.encode("ascii"), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            padding = "=" * (-len(encoded) % 4)
            payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
            if not isinstance(payload, dict) or payload.get("kind") != kind:
                raise ValueError
            expires_at = payload.get("expires_at")
            if not isinstance(expires_at, int) or self._now().timestamp() >= expires_at:
                raise ValueError
        except (ValueError, TypeError, json.JSONDecodeError):
            raise EvaluationError(
                "stale_confirmation",
                "The confirmation is invalid or has expired.",
                "Preview the current operation again.",
            ) from None
        with self._lock:
            if token in self._used:
                raise EvaluationError(
                    "stale_confirmation",
                    "The confirmation was already used.",
                    "Preview the current operation again.",
                )
            self._used.add(token)
        return payload


class CaptureProofs(_SignedSingleUseTokens):
    def issue(self, source_text: str, provider_output: str, cleanup: CleanupCapture) -> str:
        return self._issue(
            "capture",
            CAPTURE_PROOF_LIFETIME,
            {
                "source_sha256": _sha256_text(source_text),
                "provider_output_sha256": _sha256_text(provider_output),
                "cleanup_sha256": hashlib.sha256(
                    _canonical(cleanup.model_dump(mode="json"))
                ).hexdigest(),
            },
        )

    def verify_and_consume(self, request: CaseCaptureRequest) -> None:
        payload = self._verify_and_consume(request.capture_proof, "capture")
        expected = {
            "source_sha256": _sha256_text(request.source_text),
            "provider_output_sha256": _sha256_text(request.provider_output),
            "cleanup_sha256": hashlib.sha256(
                _canonical(request.cleanup.model_dump(mode="json"))
            ).hexdigest(),
        }
        if not all(
            isinstance(payload.get(key), str)
            and hmac.compare_digest(str(payload[key]), value)
            for key, value in expected.items()
        ):
            raise EvaluationError(
                "capture_proof_mismatch",
                "The cleanup changed after its capture proof was issued.",
                "Run cleanup again, then review the current result.",
            )


class ExportTokens(_SignedSingleUseTokens):
    def issue(self, selections: list[ExportSelection]) -> str:
        normalized = sorted(
            (
                {"case_id": str(selection.case_id), "revision": selection.revision}
                for selection in selections
            ),
            key=lambda item: item["case_id"],
        )
        return self._issue("export", EXPORT_PREVIEW_LIFETIME, {"cases": normalized})

    def verify_and_consume(self, token: str) -> list[ExportSelection]:
        payload = self._verify_and_consume(token, "export")
        try:
            cases = payload["cases"]
            if not isinstance(cases, list):
                raise ValueError
            return [ExportSelection.model_validate(item) for item in cases]
        except (KeyError, TypeError, ValueError):
            raise EvaluationError(
                "stale_confirmation",
                "The export preview is invalid.",
                "Preview the current selection again.",
            ) from None


@dataclass(frozen=True)
class ExportMaterial:
    content: bytes
    minimum_expiry: datetime
    maximum_expiry: datetime


class EvaluationStore:
    def __init__(
        self, database: EvaluationDatabase, *, now: Callable[[], datetime] = utc_now
    ) -> None:
        self.database = database
        self._now = now

    @staticmethod
    def _purge(session: Session, now: datetime) -> int:
        active_hold = exists().where(
            BenchmarkHold.case_id == EvaluationCase.id,
            BenchmarkHold.release_at > now,
        )
        result = session.execute(
            delete(EvaluationCase).where(
                EvaluationCase.expires_at <= now,
                ~active_hold,
            )
        )
        session.execute(delete(BenchmarkHold).where(BenchmarkHold.release_at <= now))
        return result.rowcount

    def purge_expired(self) -> int:
        try:
            with self.database.session_factory.begin() as session:
                return self._purge(session, self._now())
        except SQLAlchemyError:
            raise self._storage_error() from None

    def capture(self, request: CaseCaptureRequest) -> dict[str, object]:
        captured_at = self._now()
        expires_at = captured_at + RETENTION_PERIOD
        case = EvaluationCase(
            id=str(uuid4()),
            contract_version=CONTRACT_VERSION,
            purpose=PURPOSE,
            source_category=request.source_category,
            source_text=request.source_text,
            provider_output=request.provider_output,
            expected_cleanup=request.expected_cleanup,
            source_sha256=_sha256_text(request.source_text),
            provider_output_sha256=_sha256_text(request.provider_output),
            expected_cleanup_sha256=_sha256_text(request.expected_cleanup),
            prompt_version_id=str(request.cleanup.prompt_version_id),
            prompt_content_sha256=request.cleanup.prompt_content_sha256,
            prompt_text=request.cleanup.prompt_text,
            cleanup_schema_version=request.cleanup.cleanup_schema_version,
            provider=request.cleanup.provider,
            model=request.cleanup.model,
            captured_at=captured_at,
            confirmed_at=captured_at,
            cleanup_completed_at=request.cleanup.completed_at,
            original_expires_at=expires_at,
            expires_at=expires_at,
            revision=1,
        )
        case.consent = EvaluationConsent(
            version=request.consent.version,
            scope=request.consent.scope,
            confirmed_at=captured_at,
        )
        case.attempts = [
            EvaluationAttempt(**attempt.model_dump(mode="python"))
            for attempt in request.cleanup.attempts
        ]
        try:
            with self.database.session_factory.begin() as session:
                self._purge(session, captured_at)
                session.add(case)
        except SQLAlchemyError:
            raise self._storage_error() from None
        return {
            "case_id": case.id,
            "revision": case.revision,
            "captured_at": _rfc3339(case.captured_at),
            "expires_at": _rfc3339(case.expires_at),
            "actions": ["review", "delete", "export", "retention"],
        }

    def list_metadata(self) -> list[dict[str, object]]:
        now = self._now()
        try:
            with self.database.session_factory.begin() as session:
                self._purge(session, now)
                cases = session.scalars(
                    select(EvaluationCase)
                    .options(selectinload(EvaluationCase.hold))
                    .order_by(EvaluationCase.captured_at.desc(), EvaluationCase.id)
                ).all()
                return [self._metadata(case, now) for case in cases]
        except SQLAlchemyError:
            raise self._storage_error() from None

    def review(self, case_id: str) -> dict[str, object]:
        now = self._now()
        try:
            with self.database.session_factory.begin() as session:
                self._purge(session, now)
                case = session.scalar(
                    select(EvaluationCase)
                    .where(EvaluationCase.id == case_id)
                    .options(
                        selectinload(EvaluationCase.consent),
                        selectinload(EvaluationCase.attempts),
                        selectinload(EvaluationCase.annotations),
                        selectinload(EvaluationCase.hold),
                    )
                )
                if case is None:
                    raise self._not_found()
                return self._complete(case, now)
        except EvaluationError:
            raise
        except SQLAlchemyError:
            raise self._storage_error() from None

    def change_retention(
        self, case_id: str, request: RetentionRequest
    ) -> dict[str, object]:
        now = self._now()
        try:
            with self.database.session_factory.begin() as session:
                self._purge(session, now)
                case = session.get(EvaluationCase, case_id)
                if case is None:
                    raise self._not_found()
                self._require_revision(case, request.revision)
                if request.expires_at is not None:
                    current_expiry = _utc(case.expires_at)
                    if request.expires_at <= now or request.expires_at >= current_expiry:
                        raise EvaluationError(
                            "invalid_expiry",
                            (
                                "The new expiry must be in the future and earlier than the "
                                "current expiry."
                            ),
                            "Choose an earlier future UTC expiry.",
                            status_code=422,
                        )
                    case.expires_at = request.expires_at
                else:
                    assert request.benchmark_id is not None and request.release_at is not None
                    if request.release_at <= now:
                        raise EvaluationError(
                            "invalid_benchmark_release",
                            "A benchmark hold requires a future fixed release time.",
                            "Choose a future UTC release time.",
                            status_code=422,
                        )
                    if case.hold is None:
                        case.hold = BenchmarkHold(
                            benchmark_id=request.benchmark_id,
                            confirmed_at=now,
                            release_at=request.release_at,
                        )
                    else:
                        case.hold.benchmark_id = request.benchmark_id
                        case.hold.confirmed_at = now
                        case.hold.release_at = request.release_at
                case.revision += 1
                session.flush()
                return self._metadata(case, now)
        except EvaluationError:
            raise
        except SQLAlchemyError:
            raise self._storage_error() from None

    def delete(self, case_id: str, revision: int) -> dict[str, str]:
        now = self._now()
        try:
            with self.database.session_factory.begin() as session:
                self._purge(session, now)
                case = session.get(EvaluationCase, case_id)
                if case is not None:
                    self._require_revision(case, revision)
                    session.delete(case)
            return {"deleted_case_id": case_id}
        except EvaluationError:
            raise
        except SQLAlchemyError:
            raise self._storage_error() from None

    def export_material(self, selections: list[ExportSelection]) -> ExportMaterial:
        now = self._now()
        normalized = sorted(selections, key=lambda selection: str(selection.case_id))
        try:
            with self.database.session_factory.begin() as session:
                self._purge(session, now)
                cases: list[EvaluationCase] = []
                for selection in normalized:
                    case = session.scalar(
                        select(EvaluationCase)
                        .where(EvaluationCase.id == str(selection.case_id))
                        .options(
                            selectinload(EvaluationCase.consent),
                            selectinload(EvaluationCase.attempts),
                            selectinload(EvaluationCase.annotations),
                        )
                    )
                    if case is None or case.revision != selection.revision:
                        raise EvaluationError(
                            "stale_export_preview",
                            "The selected cases changed after export preview.",
                            "Review the corpus and preview the selection again.",
                        )
                    cases.append(case)
                lines = [self._export_line(case) for case in cases]
                expiries = [_utc(case.expires_at) for case in cases]
                return ExportMaterial(
                    content=b"".join(lines),
                    minimum_expiry=min(expiries),
                    maximum_expiry=max(expiries),
                )
        except EvaluationError:
            raise
        except SQLAlchemyError:
            raise self._storage_error() from None

    @staticmethod
    def _metadata(case: EvaluationCase, now: datetime) -> dict[str, object]:
        expires_at = _utc(case.expires_at)
        hold = case.hold
        active_hold = hold is not None and _utc(hold.release_at) > now
        return {
            "case_id": case.id,
            "revision": case.revision,
            "captured_at": _rfc3339(case.captured_at),
            "confirmed_at": _rfc3339(case.confirmed_at),
            "expires_at": _rfc3339(case.expires_at),
            "original_expires_at": _rfc3339(case.original_expires_at),
            "source_category": case.source_category,
            "provider": case.provider,
            "model": case.model,
            "prompt_version_id": case.prompt_version_id,
            "hold": (
                {
                    "benchmark_id": hold.benchmark_id,
                    "confirmed_at": _rfc3339(hold.confirmed_at),
                    "release_at": _rfc3339(hold.release_at),
                }
                if active_hold
                else None
            ),
            "upcoming_expiry": not active_hold
            and expires_at - now <= UPCOMING_EXPIRY_PERIOD,
            "actions": ["review", "delete", "export", "retention"],
        }

    def _complete(self, case: EvaluationCase, now: datetime) -> dict[str, object]:
        return {
            **self._metadata(case, now),
            "contract_version": case.contract_version,
            "purpose": case.purpose,
            "source_text": case.source_text,
            "provider_output": case.provider_output,
            "expected_cleanup": case.expected_cleanup,
            "cleanup": self._cleanup(case),
            "consent": {
                "version": case.consent.version,
                "scope": case.consent.scope,
                "confirmed_at": _rfc3339(case.consent.confirmed_at),
            },
            "annotations": [self._annotation(annotation) for annotation in case.annotations],
        }

    @staticmethod
    def _cleanup(case: EvaluationCase) -> dict[str, object]:
        return {
            "completed_at": _rfc3339(case.cleanup_completed_at),
            "provider": case.provider,
            "model": case.model,
            "attempts": [EvaluationStore._attempt(attempt) for attempt in case.attempts],
            "prompt_version_id": case.prompt_version_id,
            "prompt_content_sha256": case.prompt_content_sha256,
            "prompt_text": case.prompt_text,
            "cleanup_schema_version": case.cleanup_schema_version,
        }

    @staticmethod
    def _attempt(attempt: EvaluationAttempt) -> dict[str, object]:
        return {
            "route_index": attempt.route_index,
            "provider": attempt.provider,
            "model": attempt.model,
            "outcome": attempt.outcome,
            "failure_class": attempt.failure_class,
            "provider_code": attempt.provider_code,
            "http_status": attempt.http_status,
            "retry_after_seconds": attempt.retry_after_seconds,
            "elapsed_ms": attempt.elapsed_ms,
            "input_tokens": attempt.input_tokens,
            "output_tokens": attempt.output_tokens,
            "cost_usd_micros": attempt.cost_usd_micros,
            "pricing_snapshot_id": attempt.pricing_snapshot_id,
        }

    @staticmethod
    def _annotation(annotation: EvaluationAnnotation) -> dict[str, object]:
        return {
            "protocol_tag": annotation.protocol_tag,
            "category": annotation.category,
            "source_span": [annotation.source_start, annotation.source_end],
            "acceptable_values": json.loads(annotation.acceptable_values_json),
        }

    def _export_line(self, case: EvaluationCase) -> bytes:
        record: dict[str, object] = {
            "export_version": EXPORT_VERSION,
            "contract_version": case.contract_version,
            "case_id": case.id,
            "captured_at": _rfc3339(case.captured_at),
            "confirmed_at": _rfc3339(case.confirmed_at),
            "expires_at": _rfc3339(case.expires_at),
            "source_category": case.source_category,
            "source_text": case.source_text,
            "provider_output": case.provider_output,
            "expected_cleanup": case.expected_cleanup,
            "cleanup": self._cleanup(case),
            "consent": {
                "version": case.consent.version,
                "scope": case.consent.scope,
                "confirmed_at": _rfc3339(case.consent.confirmed_at),
            },
            "annotations": [self._annotation(annotation) for annotation in case.annotations],
        }
        record["record_sha256"] = hashlib.sha256(_canonical(record)).hexdigest()
        return json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"

    @staticmethod
    def _require_revision(case: EvaluationCase, revision: int) -> None:
        if case.revision != revision:
            raise EvaluationError(
                "revision_conflict",
                "The case changed after it was reviewed.",
                "Reload the case before changing it.",
            )

    @staticmethod
    def _not_found() -> EvaluationError:
        return EvaluationError(
            "case_not_found",
            "The evaluation case is no longer available.",
            "Reload the evaluation case list.",
            status_code=404,
        )

    @staticmethod
    def _storage_error() -> EvaluationError:
        return EvaluationError(
            "evaluation_storage_error",
            "The private evaluation database could not complete the operation.",
            "Retry the operation or check the evaluation database with the explicit admin command.",
            status_code=503,
        )
