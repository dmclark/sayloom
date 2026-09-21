"""Process-local publication of the text selected for outgoing commands."""

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from threading import Lock
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from local_text.cleanup import CorrectionMode


class OutgoingKind(StrEnum):
    EMPTY = "empty"
    ORIGINAL = "original"
    PREPARED = "prepared"


class PublishedStatus(StrEnum):
    UNCHANGED = "unchanged"
    WAITING = "waiting"
    CLEANING = "cleaning"
    PREPARED = "prepared"
    DISABLED = "disabled"
    TIMEOUT = "timeout"
    ERROR = "error"
    STALE = "stale"


class OutgoingStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cleanup_enabled: bool
    original_text: str = Field(max_length=100_000)
    prepared_text: str = Field(max_length=100_000)
    outgoing_text: str = Field(max_length=100_000)
    outgoing_kind: OutgoingKind
    status: PublishedStatus
    correction_mode: CorrectionMode = CorrectionMode.CONSERVATIVE
    evidence_lease_token: UUID | None = None
    evidence_receipt: UUID | None = None

    @model_validator(mode="after")
    def selected_text_is_current(self) -> "OutgoingStateUpdate":
        if not self.outgoing_text and self.outgoing_kind is not OutgoingKind.EMPTY:
            raise ValueError("empty outgoing text must use the empty kind")
        if self.outgoing_text and self.outgoing_kind is OutgoingKind.EMPTY:
            raise ValueError("non-empty outgoing text cannot use the empty kind")
        if (
            self.outgoing_kind is OutgoingKind.ORIGINAL
            and self.outgoing_text != self.original_text
        ):
            raise ValueError("Original outgoing text must match the current Original")
        if (
            self.outgoing_kind is OutgoingKind.PREPARED
            and self.outgoing_text != self.prepared_text
        ):
            raise ValueError("Prepared outgoing text must match the current Prepared result")
        return self


@dataclass(frozen=True)
class OutgoingState:
    cleanup_enabled: bool = True
    original_text: str = ""
    prepared_text: str = ""
    outgoing_text: str = ""
    outgoing_kind: OutgoingKind = OutgoingKind.EMPTY
    status: PublishedStatus = PublishedStatus.UNCHANGED
    correction_mode: CorrectionMode = CorrectionMode.CONSERVATIVE
    evidence_lease_token: UUID | None = None
    evidence_receipt: UUID | None = None
    revision: int = 0

    def public(self) -> dict[str, object]:
        value = asdict(self)
        if self.evidence_lease_token is None:
            value.pop("evidence_lease_token")
        if self.evidence_receipt is None:
            value.pop("evidence_receipt")
        return value


class OutgoingStateStore:
    def __init__(
        self,
        *,
        cleanup_enabled: bool,
        correction_mode: CorrectionMode = CorrectionMode.CONSERVATIVE,
    ) -> None:
        self._state = OutgoingState(
            cleanup_enabled=cleanup_enabled,
            correction_mode=correction_mode,
        )
        self._lock = Lock()

    def read(self) -> OutgoingState:
        with self._lock:
            return self._state

    def update(self, update: OutgoingStateUpdate) -> OutgoingState:
        with self._lock:
            self._state = OutgoingState(**update.model_dump(), revision=self._state.revision + 1)
            return self._state

    def clear(self, *, correction_mode: CorrectionMode | None = None) -> OutgoingState:
        with self._lock:
            self._state = replace(
                OutgoingState(
                    cleanup_enabled=self._state.cleanup_enabled,
                    correction_mode=correction_mode or self._state.correction_mode,
                ),
                revision=self._state.revision + 1,
            )
            return self._state


@dataclass(frozen=True)
class DeliveryRequest:
    id: UUID
    lease_token: UUID
    created_at: datetime
    outgoing_text: str | None = None

    @property
    def status(self) -> str:
        return "ready" if self.outgoing_text is not None else "waiting_for_evidence"


class DeliveryRequestStore:
    def __init__(self) -> None:
        self._requests: dict[UUID, DeliveryRequest] = {}
        self._lock = Lock()

    def create(self, *, lease_token: UUID) -> DeliveryRequest:
        with self._lock:
            self._expire()
            request = DeliveryRequest(
                id=uuid4(),
                lease_token=lease_token,
                created_at=datetime.now(UTC),
            )
            self._requests[request.id] = request
            return request

    def pending(self, *, lease_token: UUID) -> DeliveryRequest | None:
        with self._lock:
            self._expire()
            return next(
                (
                    request
                    for request in self._requests.values()
                    if request.lease_token == lease_token and request.outgoing_text is None
                ),
                None,
            )

    def complete(
        self,
        *,
        request_id: UUID,
        lease_token: UUID,
        outgoing_text: str,
    ) -> DeliveryRequest:
        with self._lock:
            self._expire()
            request = self._requests.get(request_id)
            if request is None or request.lease_token != lease_token:
                raise KeyError(request_id)
            completed = replace(request, outgoing_text=outgoing_text)
            self._requests[request_id] = completed
            return completed

    def read(self, request_id: UUID) -> DeliveryRequest:
        with self._lock:
            self._expire()
            request = self._requests.get(request_id)
            if request is None:
                raise KeyError(request_id)
            return request

    def _expire(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(minutes=30)
        self._requests = {
            request_id: request
            for request_id, request in self._requests.items()
            if request.created_at >= cutoff
        }
