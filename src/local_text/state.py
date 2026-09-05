"""Process-local publication of the text selected for outgoing commands."""

from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from threading import Lock

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from local_text.cleanup import CorrectionMode


class OutgoingKind(StrEnum):
    EMPTY = "empty"
    ORIGINAL = "original"
    PREPARED = "prepared"


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
    original_text: str = Field(
        max_length=100_000,
        validation_alias=AliasChoices("original_text", "raw_text"),
    )
    prepared_text: str = Field(
        max_length=100_000,
        validation_alias=AliasChoices("prepared_text", "cleaned_text"),
    )
    outgoing_text: str = Field(max_length=100_000)
    outgoing_kind: OutgoingKind
    status: PublishedStatus
    correction_mode: CorrectionMode = CorrectionMode.CONSERVATIVE

    @field_validator("outgoing_kind", mode="before")
    @classmethod
    def accept_legacy_outgoing_kind(cls, value: object) -> object:
        return {"raw": OutgoingKind.ORIGINAL, "cleaned": OutgoingKind.PREPARED}.get(
            value, value
        )

    @property
    def raw_text(self) -> str:
        """Temporary domain compatibility for callers using the former name."""
        return self.original_text

    @property
    def cleaned_text(self) -> str:
        """Temporary domain compatibility for callers using the former name."""
        return self.prepared_text

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

    @property
    def raw_text(self) -> str:
        """Temporary domain compatibility for callers using the former name."""
        return self.original_text

    @property
    def cleaned_text(self) -> str:
        """Temporary domain compatibility for callers using the former name."""
        return self.prepared_text

    def public(self) -> dict[str, object]:
        state = asdict(self)
        state["raw_text"] = self.original_text
        state["cleaned_text"] = self.prepared_text
        return state


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
