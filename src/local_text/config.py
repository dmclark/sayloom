"""Runtime profile and display branding configuration."""

import os
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
    gemini_model: str = "gemini-3.5-flash"
    cleanup_timeout_seconds: float = 30.0
    database_path: Path | None = None

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


def load_settings() -> Settings:
    profile = Profile(os.getenv("LOCAL_TEXT_PROFILE", Profile.DEVELOPMENT))
    state_directory = Path(
        os.getenv(
            "LOCAL_TEXT_STATE_DIRECTORY",
            Path.home() / "Library/Application Support/local-text" / profile,
        )
    )
    api_key = (
        os.getenv("LOCAL_TEXT_GEMINI_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )
    return Settings(
        profile=profile,
        development_state_name=os.getenv("LOCAL_TEXT_DEVELOPMENT_STATE_NAME"),
        gemini_api_key=api_key,
        gemini_model=os.getenv("LOCAL_TEXT_GEMINI_MODEL", "gemini-3.5-flash"),
        cleanup_timeout_seconds=float(os.getenv("LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS", "30")),
        database_path=Path(
            os.getenv("LOCAL_TEXT_DATABASE_PATH", state_directory / "local-text.sqlite3")
        ),
    )
