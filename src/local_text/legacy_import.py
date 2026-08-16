"""Read-only preview of an explicitly selected legacy configuration directory."""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

PROMPT_FILENAME = "cleanup-prompt.txt"
PREFERENCES_FILENAME = "preferences.json"
ALLOWED_PREFERENCES = {"cleanup_enabled_by_default"}


class LegacyImportError(ValueError):
    pass


@dataclass(frozen=True)
class LegacyImportPreview:
    source_fingerprint: str
    prompt_text: str | None
    cleanup_enabled_by_default: bool | None
    preview_digest: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _read_regular_file(path: Path, maximum_bytes: int) -> bytes:
    if path.is_symlink():
        raise LegacyImportError(f"refusing symbolic link: {path.name}")
    if not path.is_file():
        raise LegacyImportError(f"expected a regular file: {path.name}")
    if path.stat().st_size > maximum_bytes:
        raise LegacyImportError(f"file is too large: {path.name}")
    return path.read_bytes()


def preview_legacy_configuration(source: Path) -> LegacyImportPreview:
    if source.is_symlink() or not source.is_dir():
        raise LegacyImportError("source must be a regular configuration directory")

    prompt_path = source / PROMPT_FILENAME
    preferences_path = source / PREFERENCES_FILENAME
    source_parts: list[bytes] = []
    prompt_text: str | None = None
    cleanup_enabled: bool | None = None

    if prompt_path.exists() or prompt_path.is_symlink():
        prompt_bytes = _read_regular_file(prompt_path, 100_000)
        try:
            prompt_text = prompt_bytes.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise LegacyImportError(f"{PROMPT_FILENAME} must be UTF-8") from exc
        if not prompt_text:
            raise LegacyImportError(f"{PROMPT_FILENAME} must not be empty")
        source_parts.extend([PROMPT_FILENAME.encode(), b"\0", prompt_bytes, b"\0"])

    if preferences_path.exists() or preferences_path.is_symlink():
        preferences_bytes = _read_regular_file(preferences_path, 16_384)
        try:
            preferences = json.loads(preferences_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LegacyImportError(f"{PREFERENCES_FILENAME} must be valid UTF-8 JSON") from exc
        if not isinstance(preferences, dict):
            raise LegacyImportError(f"{PREFERENCES_FILENAME} must contain a JSON object")
        unknown = set(preferences) - ALLOWED_PREFERENCES
        if unknown:
            names = ", ".join(sorted(unknown))
            raise LegacyImportError(f"unsupported preference keys: {names}")
        if "cleanup_enabled_by_default" in preferences:
            cleanup_enabled = preferences["cleanup_enabled_by_default"]
            if not isinstance(cleanup_enabled, bool):
                raise LegacyImportError("cleanup_enabled_by_default must be a boolean")
        source_parts.extend(
            [PREFERENCES_FILENAME.encode(), b"\0", preferences_bytes, b"\0"]
        )

    if prompt_text is None and cleanup_enabled is None:
        raise LegacyImportError(
            f"no importable {PROMPT_FILENAME} or {PREFERENCES_FILENAME} configuration found"
        )

    source_fingerprint = hashlib.sha256(b"".join(source_parts)).hexdigest()
    preview_content = {
        "cleanup_enabled_by_default": cleanup_enabled,
        "prompt_text": prompt_text,
        "source_fingerprint": source_fingerprint,
    }
    preview_digest = hashlib.sha256(
        json.dumps(preview_content, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return LegacyImportPreview(
        source_fingerprint=source_fingerprint,
        prompt_text=prompt_text,
        cleanup_enabled_by_default=cleanup_enabled,
        preview_digest=preview_digest,
    )
