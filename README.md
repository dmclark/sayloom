# Sayloom Development

A local-first text cleanup workspace for typing, paste, and compatible dictation input. The daily surface keeps an editable, collapsible Original field and a read-only Cleaned result, fails open to the original when Gemini is unavailable, publishes the selected outgoing text for Raycast, and manages immutable cleanup-prompt versions. The Python package and machine-level identifiers are deliberately neutral and independent of the display brand.

## Setup

Requirements: macOS, Python 3.12+, and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
uv run python -m local_text.admin migrate
uv run python -m local_text.admin seed
uv run uvicorn local_text.app:app --host 127.0.0.1 --port 7523
```

Open <http://127.0.0.1:7523/> or check <http://127.0.0.1:7523/health>.

The local default is the `development` profile and displays **Sayloom Development**. A release process can explicitly select release branding with `LOCAL_TEXT_PROFILE=release`. Application startup performs no database migrations or seed writes. If the database is absent or at the wrong schema revision, `/health` reports `setup_required` with HTTP 503 rather than changing it.

## Gemini cleanup

Cleanup is enabled by default for every Original update, regardless of whether it came from typing, ordinary paste, or compatible dictation. Cleaned remains blank while cleanup is waiting or running, while the outgoing state immediately fails open to the unchanged Original text. Reloading the page clears both editors and the process-local outgoing state without changing durable prompt or cleanup settings. Dictation tools that signal a write with an untrusted synthetic paste followed by a trusted input event receive compatible caret and focus handling, but that event sequence is not a required input API.

Configure the development LaunchAgent by creating the external, user-only file `~/Library/Application Support/local-text/development/environment`:

```sh
LOCAL_TEXT_GEMINI_API_KEY=replace-with-your-key
# Optional:
# LOCAL_TEXT_GEMINI_MODEL=gemini-3.5-flash
# LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS=30
# LOCAL_TEXT_DATABASE_PATH=/an/external/state/location/local-text.sqlite3
```

Set its permissions to `0600`, then use the verified restart workflow below. The file and key must never enter Git. The cleanup toggle is a durable application setting managed by the UI and SQLite.

## Durable prompt configuration

SQLite in the external profile state directory is authoritative for the seeded prompt, immutable custom prompt versions, exact active-version selection, the cleanup default, seed state, and one-time import status. The Cleaned header provides a compact active-prompt selector; **Prompts** in the contained dark workspace rail opens a full-width version-management dialog for reading history, basing a new version on an earlier version, saving and activating a new immutable version, or reactivating an exact earlier version. Original and Cleaned are vertically stacked and share an accessible draggable divider with a 65/35 default split and keyboard-adjustable 45–80% Original range. Original can collapse while retaining text-entry focus so Cleaned fills the canvas. At narrower widths the workspace rail becomes a horizontal navigation strip. Original uses the browser's native insertion point; Cleaned is read-only.

Normal startup only checks schema state. The administration commands are explicit:

```sh
uv run python -m local_text.admin schema
uv run python -m local_text.admin migrate
uv run python -m local_text.admin seed
```

Use `scripts/verify-then-restart.sh` for a real update rather than running migration steps individually. It runs all checks, makes an online SQLite backup when a database exists, migrates, applies the deterministic seed release, restarts only `local.local-text.development`, and requires a healthy response from port 7523.

### One-time configuration import

The importer reads an explicitly supplied directory and never discovers, modifies, or deletes a source. Only these optional files are allowlisted:

- `cleanup-prompt.txt`: UTF-8 cleanup instruction, imported as a new active immutable version.
- `preferences.json`: a JSON object whose only supported key is the boolean `cleanup_enabled_by_default`.

Other files—including databases, history, text content, diagnostics, logs, and recordings—are ignored. Preview prints the exact imported values and a confirmation digest:

```sh
uv run python -m local_text.admin import-preview /path/to/configuration-directory
uv run python -m local_text.admin import-confirm /path/to/configuration-directory \
  --digest COPY_THE_PREVIEW_DIGEST_HERE
```

Confirmation rereads the allowlisted source and rejects a stale digest. The write is one transaction, records completion, and rejects every later import attempt.

## Development

```sh
uv run ruff check .
uv run pytest
```

Do not use hot reload for validated coding tasks. After the user-level service is installed, use the controlled `scripts/verify-then-restart.sh` workflow described above.

## User-level launchd service

The user-level launchd service uses these neutral identifiers:

- label: `local.local-text.development`
- state: `~/Library/Application Support/local-text/development`
- port: `7523`

Render a plist for review without changing machine state:

```sh
uv run python scripts/render-launchd-plist.py > /tmp/local-text-development.plist
plutil -lint /tmp/local-text-development.plist
```

After reviewing it, install or safely reload only this user agent:

```sh
uv sync --locked
scripts/install-launchd.sh
```

The installer creates the external state and log directories with user-only permissions. To stop the agent and remove its installed plist while preserving external state:

```sh
scripts/uninstall-launchd.sh
```

Runtime logs and all future operating data belong in the external state directory, never in this repository.

## Raycast commands

Add this repository's `raycast/` directory as a Raycast Script Commands directory. It contains exactly five user-facing commands:

- **Open Sayloom Development**
- **Send to Amp — Sayloom Development**
- **Send to iTerm — Sayloom Development**
- **Send to Supacode — Sayloom Development**
- **Send to VS Code — Sayloom Development**

Raycast owns global hotkeys; no hotkey values are committed. Assign the familiar hotkeys to these development-branded commands in Raycast settings. Send commands refuse empty, malformed, or unavailable outgoing state and never press Return. Amp, Supacode, and VS Code use a Sticky-Keys-safe synthetic paste and restore the prior text clipboard. iTerm inserts multiline text directly without using the clipboard.

The five Gate 1 command surfaces remain intact through the durable prompt core. Real-device Gate 2 verification adds prompt-history rendering, new-version activation, exact rollback to an earlier version, cleanup with the selected version, durable cleanup-toggle state, controlled backup/migrate/restart health, and one-time importer preview/confirm behavior.

## Privacy

Never commit credentials, API keys, dictated or cleaned text, databases, logs, local `.env` files, or machine-specific paths. Use synthetic text in tests and documentation.
