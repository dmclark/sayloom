"""External evaluation SQLite configuration and non-mutating schema checks."""

from __future__ import annotations

import os
import sqlite3
import stat
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from local_text.database import SchemaState, SchemaStatus

EVALUATION_DATABASE_NAME = "cleanup-evaluation.sqlite3"
EVALUATION_SCHEMA_REVISION = "0002_evaluation_lifecycle"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class EvaluationConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvaluationConfiguration:
    status: str
    database: EvaluationDatabase | None = None
    current_revision: str | None = None

    @property
    def available(self) -> bool:
        return self.status == "current" and self.database is not None

    def public(self) -> dict[str, object]:
        return {
            "status": self.status,
            "available": self.available,
            "schema_revision": self.current_revision,
            "expected_schema_revision": EVALUATION_SCHEMA_REVISION,
            "retention_days": 90,
            "storage": "external_local_directory" if self.database is not None else None,
        }


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _validate_directory_path(
    directory: Path,
    *,
    application_database_path: Path,
    permit_insecure_permissions: bool,
) -> Path:
    if not directory.is_absolute():
        raise EvaluationConfigurationError("evaluation_directory_must_be_absolute")
    if directory.is_symlink():
        raise EvaluationConfigurationError("evaluation_directory_must_not_be_a_link")
    resolved = directory.resolve(strict=False)
    if _overlaps(resolved, PROJECT_ROOT.resolve()):
        raise EvaluationConfigurationError("evaluation_directory_overlaps_repository")
    if _overlaps(resolved, application_database_path.resolve(strict=False).parent):
        raise EvaluationConfigurationError("evaluation_directory_overlaps_application_state")
    if resolved.exists():
        metadata = resolved.stat()
        if not resolved.is_dir() or metadata.st_uid != os.getuid():
            raise EvaluationConfigurationError("evaluation_directory_must_be_user_owned")
        if not permit_insecure_permissions and stat.S_IMODE(metadata.st_mode) & 0o077:
            raise EvaluationConfigurationError("evaluation_directory_permissions_are_not_private")
    return resolved


def evaluation_configuration(
    directory: Path | None,
    *,
    application_database_path: Path,
) -> EvaluationConfiguration:
    if directory is None:
        return EvaluationConfiguration("unconfigured")
    try:
        resolved = _validate_directory_path(
            directory,
            application_database_path=application_database_path,
            permit_insecure_permissions=False,
        )
        database = EvaluationDatabase(resolved / EVALUATION_DATABASE_NAME)
        database.validate_file_permissions()
    except EvaluationConfigurationError:
        return EvaluationConfiguration("invalid")
    schema = database.schema_status()
    return EvaluationConfiguration(str(schema.state), database, schema.current_revision)


class EvaluationDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def for_migration(
        cls, directory: Path | None, *, application_database_path: Path
    ) -> EvaluationDatabase:
        if directory is None:
            raise EvaluationConfigurationError("evaluation_directory_is_not_configured")
        resolved = _validate_directory_path(
            directory,
            application_database_path=application_database_path,
            permit_insecure_permissions=True,
        )
        return cls(resolved / EVALUATION_DATABASE_NAME)

    @property
    def url(self) -> str:
        return URL.create("sqlite+pysqlite", database=str(self.path)).render_as_string(
            hide_password=False
        )

    def prepare_directory(self) -> None:
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.path.parent.stat().st_uid != os.getuid():
            raise EvaluationConfigurationError("evaluation_directory_must_be_user_owned")
        self.path.parent.chmod(0o700)
        if self.path.is_symlink() or (self.path.exists() and not self.path.is_file()):
            raise EvaluationConfigurationError("evaluation_database_must_be_a_regular_file")
        if self.path.exists():
            if self.path.stat().st_uid != os.getuid():
                raise EvaluationConfigurationError(
                    "evaluation_database_must_be_user_owned"
                )
            self.path.chmod(0o600)

    def secure_database_file(self) -> None:
        if self.path.exists():
            self.path.chmod(0o600)

    def validate_file_permissions(self) -> None:
        if self.path.parent.exists():
            metadata = self.path.parent.stat()
            if not self.path.parent.is_dir() or metadata.st_uid != os.getuid():
                raise EvaluationConfigurationError(
                    "evaluation_directory_must_be_user_owned"
                )
            if stat.S_IMODE(metadata.st_mode) & 0o077:
                raise EvaluationConfigurationError(
                    "evaluation_directory_permissions_are_not_private"
                )
        if not self.path.exists():
            return
        if self.path.is_symlink() or not self.path.is_file():
            raise EvaluationConfigurationError("evaluation_database_must_be_a_regular_file")
        metadata = self.path.stat()
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise EvaluationConfigurationError("evaluation_database_permissions_are_not_private")

    def schema_status(self) -> SchemaStatus:
        if not self.path.is_file():
            return SchemaStatus(SchemaState.MISSING, EVALUATION_SCHEMA_REVISION)
        uri = f"file:{quote(str(self.path), safe='/')}?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True) as connection:
                row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.OperationalError:
            return SchemaStatus(SchemaState.UNINITIALIZED, EVALUATION_SCHEMA_REVISION)
        revision = row[0] if row else None
        state = (
            SchemaState.CURRENT
            if revision == EVALUATION_SCHEMA_REVISION
            else SchemaState.MISMATCH
        )
        return SchemaStatus(state, EVALUATION_SCHEMA_REVISION, revision)

    def assert_ready(self) -> SchemaStatus:
        status = self.schema_status()
        if not status.ready:
            raise EvaluationConfigurationError("evaluation_schema_is_not_current")
        return status

    @cached_property
    def engine(self) -> Engine:
        engine = create_engine(self.url)

        def configure_sqlite(dbapi_connection: object, _connection_record: object) -> None:
            cursor = dbapi_connection.cursor()
            for statement in (
                "PRAGMA foreign_keys=ON",
                "PRAGMA secure_delete=ON",
                "PRAGMA temp_store=MEMORY",
                "PRAGMA journal_mode=DELETE",
                "PRAGMA journal_size_limit=0",
            ):
                cursor.execute(statement)
            cursor.close()

        event.listen(engine, "connect", configure_sqlite)
        return engine

    @cached_property
    def session_factory(self) -> sessionmaker[Session]:
        return sessionmaker(self.engine, expire_on_commit=False)
