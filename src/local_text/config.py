"""Runtime profile and display branding configuration."""

import os
from dataclasses import dataclass, field
from enum import StrEnum


class Profile(StrEnum):
    DEVELOPMENT = "development"
    RELEASE = "release"


@dataclass(frozen=True)
class Settings:
    profile: Profile
    gemini_api_key: str | None = field(default=None, repr=False)
    gemini_model: str = "gemini-3.5-flash"
    cleanup_timeout_seconds: float = 8.0
    cleanup_enabled_by_default: bool = True

    @property
    def display_name(self) -> str:
        return "Sayloom Development" if self.profile is Profile.DEVELOPMENT else "Sayloom"


def _enabled(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "off", "no"}


def load_settings() -> Settings:
    profile = Profile(os.getenv("LOCAL_TEXT_PROFILE", Profile.DEVELOPMENT))
    api_key = (
        os.getenv("LOCAL_TEXT_GEMINI_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )
    return Settings(
        profile=profile,
        gemini_api_key=api_key,
        gemini_model=os.getenv("LOCAL_TEXT_GEMINI_MODEL", "gemini-3.5-flash"),
        cleanup_timeout_seconds=float(os.getenv("LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS", "8")),
        cleanup_enabled_by_default=_enabled(
            os.getenv("LOCAL_TEXT_CLEANUP_ENABLED"), default=True
        ),
    )
