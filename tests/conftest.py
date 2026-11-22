import builtins
from pathlib import Path

import pytest
from alembic import command

from local_text.admin import _alembic_config
from local_text.config import Profile, Settings
from local_text.database import ApplicationDatabase
from local_text.prompt_store import PromptStore
from local_text.target_store import TargetStore


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if report.failed:
        reporter = item.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            # Exception messages, assertion values and parameter IDs can contain private text.
            # Only expose a known exception type and the test's source location immediately.
            error = "test failure"
            if call.excinfo is not None:
                kind = call.excinfo.type
                if getattr(builtins, kind.__name__, None) is kind:
                    error = kind.__name__
            filename, line, _ = report.location
            reporter.write_line(
                f"[pytest] FAILED {report.nodeid.split('[', 1)[0]} "
                f"({report.when}, {report.duration:.2f}s): {error} at {filename}:{line + 1}"
            )
            reporter.flush()
    return report


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
