"""Runtime profile and display branding configuration."""

import fcntl
import os
import stat
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Profile(StrEnum):
    DEVELOPMENT = "development"
    RELEASE = "release"


@dataclass(frozen=True)
class Settings:
    profile: Profile
    development_state_name: str | None = None
    gemini_api_key: str | None = field(default=None, repr=False)
    gemini_api_key_is_explicit: bool = True
    gemini_model: str = "gemini-3.5-flash"
    openai_api_key: str | None = field(default=None, repr=False)
    openai_model: str | None = None
    openrouter_api_key: str | None = field(default=None, repr=False)
    openrouter_models: tuple[str, ...] = ()
    openrouter_endpoints: tuple[str, ...] = ()
    cleanup_route_order: str | None = None
    gemini_quota_group_id: str | None = None
    openai_quota_group_id: str | None = None
    paid_data_acknowledgement: str | None = None
    cleanup_timeout_seconds: float = 30.0
    cleanup_route_attempt_seconds: tuple[float, ...] | None = None
    database_path: Path | None = None
    raycast_directory: Path | None = None
    provider_traffic_diagnostics_file: Path | None = field(default=None, repr=False)

    @property
    def display_name(self) -> str:
        return "Sayloom Development" if self.profile is Profile.DEVELOPMENT else "Sayloom"

    @property
    def page_title(self) -> str:
        if self.profile is Profile.DEVELOPMENT and self.development_state_name:
            return f"{self.display_name} — {self.development_state_name}"
        return self.display_name

    @property
    def resolved_database_path(self) -> Path:
        if self.database_path is not None:
            return self.database_path
        return (
            Path.home()
            / "Library/Application Support/local-text"
            / self.profile
            / "local-text.sqlite3"
        )

    @property
    def resolved_raycast_directory(self) -> Path:
        if self.raycast_directory is not None:
            return self.raycast_directory
        return Path.home() / ".config/raycast/scripts"

    def provider_traffic_diagnostics_enabled(self) -> bool:
        path = self.provider_traffic_diagnostics_file
        if self.profile is not Profile.DEVELOPMENT or path is None:
            return False
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            return False
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                return False
            try:
                fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return False
        except OSError:
            return False
        finally:
            os.close(descriptor)


def load_settings() -> Settings:
    profile = Profile(os.getenv("LOCAL_TEXT_PROFILE", Profile.DEVELOPMENT))
    state_directory = Path(
        os.getenv(
            "LOCAL_TEXT_STATE_DIRECTORY",
            Path.home() / "Library/Application Support/local-text" / profile,
        )
    )
    explicit_gemini_api_key = os.getenv("LOCAL_TEXT_GEMINI_API_KEY")
    api_key = explicit_gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    return Settings(
        profile=profile,
        development_state_name=os.getenv("LOCAL_TEXT_DEVELOPMENT_STATE_NAME"),
        gemini_api_key=api_key,
        gemini_api_key_is_explicit=bool(explicit_gemini_api_key),
        gemini_model=os.getenv("LOCAL_TEXT_GEMINI_MODEL", "gemini-3.5-flash"),
        openai_api_key=os.getenv("LOCAL_TEXT_OPENAI_API_KEY"),
        openai_model=os.getenv("LOCAL_TEXT_OPENAI_MODEL"),
        openrouter_api_key=os.getenv("LOCAL_TEXT_OPENROUTER_API_KEY"),
        openrouter_models=tuple(
            part.strip()
            for part in os.getenv("LOCAL_TEXT_OPENROUTER_MODELS", "").split(",")
            if part.strip()
        ),
        openrouter_endpoints=tuple(
            part.strip()
            for part in os.getenv("LOCAL_TEXT_OPENROUTER_ENDPOINTS", "").split(",")
            if part.strip()
        ),
        cleanup_route_order=os.getenv("LOCAL_TEXT_CLEANUP_ROUTE_ORDER"),
        gemini_quota_group_id=os.getenv("LOCAL_TEXT_GEMINI_QUOTA_GROUP_ID"),
        openai_quota_group_id=os.getenv("LOCAL_TEXT_OPENAI_QUOTA_GROUP_ID"),
        paid_data_acknowledgement=os.getenv("LOCAL_TEXT_CLEANUP_PAID_DATA_ACKNOWLEDGEMENT"),
        cleanup_timeout_seconds=float(os.getenv("LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS", "30")),
        cleanup_route_attempt_seconds=_route_attempt_seconds(
            os.getenv("LOCAL_TEXT_CLEANUP_ROUTE_ATTEMPT_SECONDS")
        ),
        database_path=Path(
            os.getenv("LOCAL_TEXT_DATABASE_PATH", state_directory / "local-text.sqlite3")
        ),
        raycast_directory=(
            Path(value) if (value := os.getenv("LOCAL_TEXT_RAYCAST_DIRECTORY")) else None
        ),
        provider_traffic_diagnostics_file=(
            Path(value)
            if profile is Profile.DEVELOPMENT
            and (value := os.getenv("LOCAL_TEXT_PROVIDER_TRAFFIC_DIAGNOSTICS_FILE"))
            else None
        ),
    )


def _route_attempt_seconds(value: str | None) -> tuple[float, ...] | None:
    if value is None:
        return None
    try:
        allocations = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise ValueError(
            "LOCAL_TEXT_CLEANUP_ROUTE_ATTEMPT_SECONDS must be comma-separated numbers"
        ) from exc
    if not allocations:
        raise ValueError("LOCAL_TEXT_CLEANUP_ROUTE_ATTEMPT_SECONDS must not be empty")
    return allocations
