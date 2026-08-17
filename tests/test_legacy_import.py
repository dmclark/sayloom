from pathlib import Path

import pytest
from alembic import command
from conftest import initialize_database
from sqlalchemy import func, select

from local_text.admin import _alembic_config
from local_text.database import ApplicationDatabase
from local_text.legacy_import import LegacyImportError, preview_legacy_configuration
from local_text.models import PromptVersion
from local_text.prompt_store import (
    ImportAlreadyCompletedError,
    PromptStore,
    SeedStateError,
)


def write_configuration(source: Path) -> None:
    source.mkdir()
    (source / "cleanup-prompt.txt").write_text("Return synthetic text only.\n")
    (source / "preferences.json").write_text(
        '{"cleanup_enabled_by_default": false}\n'
    )


def test_preview_reads_only_allowlisted_configuration_without_changing_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy-configuration"
    write_configuration(source)
    unrelated = source / "history.json"
    unrelated.write_text('{"private_content": "must not be read"}')
    before = {path.name: path.read_bytes() for path in source.iterdir()}

    preview = preview_legacy_configuration(source)

    assert preview.prompt_text == "Return synthetic text only."
    assert preview.cleanup_enabled_by_default is False
    assert len(preview.source_fingerprint) == 64
    assert len(preview.preview_digest) == 64
    assert {path.name: path.read_bytes() for path in source.iterdir()} == before


def test_preview_rejects_unknown_preferences_and_symbolic_links(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown"
    unknown.mkdir()
    (unknown / "preferences.json").write_text('{"future_setting": true}')
    with pytest.raises(LegacyImportError, match="unsupported preference"):
        preview_legacy_configuration(unknown)

    linked = tmp_path / "linked"
    linked.mkdir()
    target = tmp_path / "prompt.txt"
    target.write_text("Synthetic prompt")
    (linked / "cleanup-prompt.txt").symlink_to(target)
    with pytest.raises(LegacyImportError, match="symbolic link"):
        preview_legacy_configuration(linked)


def test_confirmed_import_is_atomic_durable_and_one_time(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "local-text.sqlite3")
    source = tmp_path / "legacy-configuration"
    write_configuration(source)
    preview = preview_legacy_configuration(source)
    store = PromptStore(database)

    imported = store.import_configuration(
        source_fingerprint=preview.source_fingerprint,
        preview_digest=preview.preview_digest,
        prompt_text=preview.prompt_text,
        cleanup_enabled=preview.cleanup_enabled_by_default,
    )

    assert imported is not None
    assert imported.source == "import"
    assert store.active().id == imported.id
    assert store.cleanup_enabled_by_default() is False
    with pytest.raises(ImportAlreadyCompletedError, match="already complete"):
        store.import_configuration(
            source_fingerprint=preview.source_fingerprint,
            preview_digest=preview.preview_digest,
            prompt_text=preview.prompt_text,
            cleanup_enabled=preview.cleanup_enabled_by_default,
        )


def test_import_requires_seed_and_leaves_migrated_database_unchanged(tmp_path: Path) -> None:
    database = ApplicationDatabase(tmp_path / "local-text.sqlite3")
    command.upgrade(_alembic_config(database.url), "head")
    store = PromptStore(database)

    with pytest.raises(SeedStateError, match="seed must be applied"):
        store.import_configuration(
            source_fingerprint="a" * 64,
            preview_digest="b" * 64,
            prompt_text="Synthetic imported instruction.",
            cleanup_enabled=None,
        )

    with database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PromptVersion)) == 0


def test_preview_digest_changes_when_source_changes(tmp_path: Path) -> None:
    source = tmp_path / "legacy-configuration"
    write_configuration(source)
    first = preview_legacy_configuration(source)

    (source / "cleanup-prompt.txt").write_text("A different synthetic prompt.\n")
    second = preview_legacy_configuration(source)

    assert second.preview_digest != first.preview_digest
    assert second.source_fingerprint != first.source_fingerprint
