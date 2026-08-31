"""Explicit administration for the external cleanup evaluation database."""

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig

from local_text.config import load_settings
from local_text.evaluation import EvaluationStore
from local_text.evaluation_database import EvaluationConfigurationError, EvaluationDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _evaluation_alembic_config(database_url: str) -> AlembicConfig:
    config = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "evaluation_migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _database(*, for_migration: bool) -> EvaluationDatabase:
    settings = load_settings()
    database = EvaluationDatabase.for_migration(
        settings.evaluation_data_directory,
        application_database_path=settings.resolved_database_path,
    )
    if not for_migration:
        database.validate_file_permissions()
    return database


def _print(value: dict[str, object]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _run(args: argparse.Namespace) -> int:
    database = _database(for_migration=args.command == "migrate")
    if args.command == "schema":
        status = database.schema_status()
        _print(asdict(status))
        return 0 if status.ready else 1
    if args.command == "migrate":
        previous_umask = os.umask(0o077)
        try:
            database.prepare_directory()
            command.upgrade(_evaluation_alembic_config(database.url), "head")
            database.secure_database_file()
        finally:
            os.umask(previous_umask)
        _print(asdict(database.assert_ready()))
        return 0
    if args.command == "expire":
        database.assert_ready()
        _print({"expired_cases_deleted": EvaluationStore(database).purge_expired()})
        return 0
    raise RuntimeError("unsupported evaluation administration command")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local-text-evaluation-admin")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("schema", help="report evaluation schema state without changing it")
    commands.add_parser("migrate", help="explicitly apply evaluation database migrations")
    commands.add_parser("expire", help="transactionally delete expired evaluation cases")
    return parser


def main() -> None:
    try:
        raise SystemExit(_run(_parser().parse_args()))
    except (EvaluationConfigurationError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
