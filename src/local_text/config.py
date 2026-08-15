"""Runtime profile and display branding configuration."""

import os
from dataclasses import dataclass
from enum import StrEnum


class Profile(StrEnum):
    DEVELOPMENT = "development"
    RELEASE = "release"


@dataclass(frozen=True)
class Settings:
    profile: Profile

    @property
    def display_name(self) -> str:
        return "Sayloom Development" if self.profile is Profile.DEVELOPMENT else "Sayloom"


def load_settings() -> Settings:
    profile = Profile(os.getenv("LOCAL_TEXT_PROFILE", Profile.DEVELOPMENT))
    return Settings(profile=profile)
