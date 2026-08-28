from pathlib import Path

import pytest
from alembic import command

from local_text.admin import _alembic_config
from local_text.config import Profile, Settings
from local_text.database import ApplicationDatabase
from local_text.prompt_store import PromptStore
from local_text.target_store import TargetStore


def initialize_database(path: Path) -> ApplicationDatabase:
    database = ApplicationDatabase(path)
    command.upgrade(_alembic_config(database.url), "head")
    PromptStore(database).seed_default()
    TargetStore(database).seed_defaults()
    return database


@pytest.fixture
def initialized_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "local-text.sqlite3"
    initialize_database(database_path)
    return Settings(Profile.DEVELOPMENT, database_path=database_path)
