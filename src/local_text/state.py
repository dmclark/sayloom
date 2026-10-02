"""Process-local publication of the text selected for outgoing commands."""

from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from threading import Lock

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
    revision: int = 0

    def public(self) -> dict[str, object]:
        return asdict(self)


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

    def clear(
        self,
        *,
        cleanup_enabled: bool | None = None,
        correction_mode: CorrectionMode | None = None,
    ) -> OutgoingState:
        with self._lock:
            self._state = replace(
                OutgoingState(
                    cleanup_enabled=(
                        self._state.cleanup_enabled
                        if cleanup_enabled is None
                        else cleanup_enabled
                    ),
                    correction_mode=correction_mode or self._state.correction_mode,
                ),
                revision=self._state.revision + 1,
            )
            return self._state
