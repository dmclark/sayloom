"""SQLite connection and non-mutating schema status checks."""

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

SCHEMA_REVISION = "0003_unified_preparation_default"


class SchemaState(StrEnum):
    CURRENT = "current"
    MISSING = "missing"
    UNINITIALIZED = "uninitialized"
    MISMATCH = "mismatch"


@dataclass(frozen=True)
class SchemaStatus:
    state: SchemaState
    expected_revision: str
    current_revision: str | None = None

    @property
    def ready(self) -> bool:
        return self.state is SchemaState.CURRENT


class SchemaNotReadyError(RuntimeError):
    def __init__(self, status: SchemaStatus) -> None:
        super().__init__(
            f"database schema is {status.state}; expected revision {status.expected_revision}, "
            f"found {status.current_revision or 'none'}"
        )
        self.status = status


class ApplicationDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def url(self) -> str:
        return URL.create("sqlite+pysqlite", database=str(self.path)).render_as_string(
            hide_password=False
        )

    def schema_status(self) -> SchemaStatus:
        if not self.path.is_file():
            return SchemaStatus(SchemaState.MISSING, SCHEMA_REVISION)

        uri = f"file:{quote(str(self.path), safe='/')}?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True) as connection:
                row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.OperationalError:
            return SchemaStatus(SchemaState.UNINITIALIZED, SCHEMA_REVISION)

        current_revision = row[0] if row else None
        state = (
            SchemaState.CURRENT
            if current_revision == SCHEMA_REVISION
            else SchemaState.MISMATCH
        )
        return SchemaStatus(state, SCHEMA_REVISION, current_revision)

    def assert_ready(self) -> SchemaStatus:
        status = self.schema_status()
        if not status.ready:
            raise SchemaNotReadyError(status)
        return status

    @cached_property
    def engine(self) -> Engine:
        engine = create_engine(self.url)

        def enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        event.listen(engine, "connect", enable_foreign_keys)
        return engine

    @cached_property
    def session_factory(self) -> sessionmaker[Session]:
        return sessionmaker(self.engine, expire_on_commit=False)
