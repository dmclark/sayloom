"""Process-local publication of the text selected for outgoing commands."""

from dataclasses import dataclass, replace
from enum import StrEnum
from threading import Lock

from pydantic import BaseModel, Field, model_validator


class OutgoingKind(StrEnum):
    EMPTY = "empty"
    RAW = "raw"
    CLEANED = "cleaned"


class PublishedStatus(StrEnum):
    UNCHANGED = "unchanged"
    WAITING = "waiting"
    CLEANING = "cleaning"
    CLEANED = "cleaned"
    DISABLED = "disabled"
    TIMEOUT = "timeout"
    ERROR = "error"
    STALE = "stale"


class OutgoingStateUpdate(BaseModel):
    cleanup_enabled: bool
    raw_text: str = Field(max_length=100_000)
    cleaned_text: str = Field(max_length=100_000)
    outgoing_text: str = Field(max_length=100_000)
    outgoing_kind: OutgoingKind
    status: PublishedStatus

    @model_validator(mode="after")
    def selected_text_is_current(self) -> "OutgoingStateUpdate":
        if not self.outgoing_text and self.outgoing_kind is not OutgoingKind.EMPTY:
            raise ValueError("empty outgoing text must use the empty kind")
        if self.outgoing_text and self.outgoing_kind is OutgoingKind.EMPTY:
            raise ValueError("non-empty outgoing text cannot use the empty kind")
        if self.outgoing_kind is OutgoingKind.RAW and self.outgoing_text != self.raw_text:
            raise ValueError("raw outgoing text must match the current Original")
        if self.outgoing_kind is OutgoingKind.CLEANED and self.outgoing_text != self.cleaned_text:
            raise ValueError("cleaned outgoing text must match the current Cleaned result")
        return self


@dataclass(frozen=True)
class OutgoingState:
    cleanup_enabled: bool = True
    raw_text: str = ""
    cleaned_text: str = ""
    outgoing_text: str = ""
    outgoing_kind: OutgoingKind = OutgoingKind.EMPTY
    status: PublishedStatus = PublishedStatus.UNCHANGED
    revision: int = 0


class OutgoingStateStore:
    def __init__(self, *, cleanup_enabled: bool) -> None:
        self._state = OutgoingState(cleanup_enabled=cleanup_enabled)
        self._lock = Lock()

    def read(self) -> OutgoingState:
        with self._lock:
            return self._state

    def update(self, update: OutgoingStateUpdate) -> OutgoingState:
        with self._lock:
            self._state = OutgoingState(**update.model_dump(), revision=self._state.revision + 1)
            return self._state

    def clear(self) -> OutgoingState:
        with self._lock:
            self._state = replace(
                OutgoingState(cleanup_enabled=self._state.cleanup_enabled),
                revision=self._state.revision + 1,
            )
            return self._state
