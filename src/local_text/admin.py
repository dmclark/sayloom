"""Explicit administration commands for controlled durable-state changes."""

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig

from local_text.config import Settings, load_settings
from local_text.database import ApplicationDatabase
from local_text.legacy_import import LegacyImportError, preview_legacy_configuration
from local_text.prompt_store import PromptStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(database_url: str) -> AlembicConfig:
    alembic_config = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    alembic_config.set_main_option("sqlalchemy.url", database_url)
    return alembic_config


def _database(config: Settings) -> ApplicationDatabase:
    return ApplicationDatabase(config.resolved_database_path)


def _print(value: dict[str, object]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _run(args: argparse.Namespace) -> int:
    config = load_settings()
    database = _database(config)

    if args.command == "schema":
        state = database.schema_status()
        _print(asdict(state))
        return 0 if state.ready else 1

    if args.command == "migrate":
        previous_umask = os.umask(0o077)
        try:
            config.resolved_database_path.parent.mkdir(parents=True, exist_ok=True)
            command.upgrade(_alembic_config(database.url), "head")
        finally:
            os.umask(previous_umask)
        state = database.assert_ready()
        _print(asdict(state))
        return 0

    if args.command == "seed":
        database.assert_ready()
        created = PromptStore(database).seed_default()
        _print({"seeded": created})
        return 0

    if args.command in {"import-preview", "import-confirm"}:
        preview = preview_legacy_configuration(args.source)
        if args.command == "import-preview":
            _print(preview.to_dict())
            return 0
        if args.digest != preview.preview_digest:
            raise LegacyImportError(
                "confirmation digest does not match the current preview; preview again"
            )
        database.assert_ready()
        prompt = PromptStore(database).import_configuration(
            source_fingerprint=preview.source_fingerprint,
            preview_digest=preview.preview_digest,
            prompt_text=preview.prompt_text,
            cleanup_enabled=preview.cleanup_enabled_by_default,
        )
        _print(
            {
                "imported": True,
                "prompt_version_id": prompt.id if prompt is not None else None,
                "preview_digest": preview.preview_digest,
            }
        )
        return 0

    raise RuntimeError(f"unsupported command: {args.command}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local-text-admin")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("schema", help="report schema state without changing it")
    subparsers.add_parser("migrate", help="apply migrations; use the controlled update script")
    subparsers.add_parser("seed", help="apply the deterministic seed release")

    preview = subparsers.add_parser("import-preview", help="preview allowlisted configuration")
    preview.add_argument("source", type=Path)

    confirm = subparsers.add_parser("import-confirm", help="confirm an unchanged preview")
    confirm.add_argument("source", type=Path)
    confirm.add_argument("--digest", required=True)
    return parser


def main() -> None:
    try:
        raise SystemExit(_run(_parser().parse_args()))
    except (
        LegacyImportError,
        RuntimeError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
