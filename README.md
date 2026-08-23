# Sayloom Development

A local-first text cleanup workspace for typing, paste, and compatible dictation input. The daily surface keeps an editable, collapsible Original field and a read-only Cleaned result, fails open to the original when Gemini is unavailable, publishes the selected outgoing text for Raycast, and manages immutable cleanup-prompt versions. The Python package and machine-level identifiers are deliberately neutral and independent of the display brand.

![Sayloom Development workspace](docs/images/sayloom-development.png)

## Development states

Requirements: macOS, Python 3.12+, and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
scripts/dev.py create feature-workflow
scripts/dev.py initialize --state feature-workflow
scripts/dev.py status
```

Every development runtime must use an explicit named external state. `create`
prints its state directory, database, service label, and fixed development port;
no command falls
back to a shared state. Put optional credentials in the shared development
configuration file, then run
`scripts/dev.py restart --state feature-workflow`.
Restart verifies, backs up, explicitly migrates/seeds, and health-checks only
the selected state-scoped service. State manifests bind the canonical checkout
and state paths to a checkout-specific service label and the fixed loopback
port. Missing, changed, cross-checkout, and path-escaping manifests are rejected
before an operation can use them.

`scripts/dev.py status` reports every registered development state in name order.
Pass `--state NAME` to report only one state.

Development always uses `127.0.0.1:7523`, so Raycast commands have one stable
endpoint. A controlled restart stops any registered named development state on
that port before starting the selected state. It refuses to stop an unregistered
listener. Only one named development state runs at a time; production remains
separate on port 7532.

The local default is the `development` profile and displays **Sayloom Development**. A release process can explicitly select release branding with `LOCAL_TEXT_PROFILE=release`. Application startup performs no database migrations or seed writes. If the database is absent or at the wrong schema revision, `/health` reports `setup_required` with HTTP 503 rather than changing it.

## Gemini cleanup

Cleanup is enabled by default for every Original update, regardless of whether it came from typing, ordinary paste, or compatible dictation. Replacing a fully selected Original clears the previous Cleaned result for the new session; incremental input keeps the last result visible while cleanup is waiting or running. During either kind of reprocessing, outgoing state immediately fails open to the current Original text. Reloading the page clears both editors and the process-local outgoing state without changing durable prompt or cleanup settings. Dictation tools that signal a write with an untrusted synthetic paste followed by a trusted input event receive compatible caret and focus handling, but that event sequence is not a required input API.

Development configuration uses two external, user-only files under `~/.config`:

```text
~/.config/local-text/development/environment
~/.config/local-text/development/states/CHECKOUT_ID/STATE_NAME/environment
```

The shared file is loaded first. The checkout-and-state-specific file is loaded
second and may override shared values. `scripts/dev.py status --state NAME`
prints the exact paths and a sanitized effective status without displaying
credential values. Each file uses unquoted `KEY=value` entries:

```sh
LOCAL_TEXT_GEMINI_API_KEY=replace-with-your-key
# Optional:
# LOCAL_TEXT_GEMINI_MODEL=gemini-3.5-flash
# LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS=30
```

Create the shared file with an editor so the credential does not enter shell
history or command arguments:

```sh
install -d -m 700 "$HOME/.config/local-text/development"
"${EDITOR:?Set EDITOR first}" "$HOME/.config/local-text/development/environment"
chmod 600 "$HOME/.config/local-text/development/environment"
scripts/dev.py restart --state NAME
```

The files and keys must never enter Git. Only the three keys shown above are
accepted; files must be regular, non-symlink files with mode `0600`, are parsed
as data, and are never sourced as shell code. Database path, state directory,
profile, service label, and port overrides are rejected: those routing values
remain exclusively bound by the selected state manifest.

## Durable prompt configuration

SQLite in the external profile state directory is authoritative for the seeded prompt, immutable custom prompt versions, exact durable default selection, the cleanup default, seed state, and one-time import status. The Cleaned header provides a compact prompt-version selector for the current page session. Selecting a version sends its exact identifier with cleanup requests but does not change the durable default; clearing text preserves the selection, while a full reload restores the configured default. Expanded prompt management is intentionally outside the Workspace surface.

Original and Cleaned are vertically stacked and share an accessible draggable divider with a 65/35 default split and keyboard-adjustable 45–80% Original range. Original can collapse while retaining text-entry focus so Cleaned fills the canvas. Original uses the browser's native insertion point; Cleaned is read-only. The Outgoing strip explicitly selects Cleaned or Original. Cleaned becomes the default after a current successful cleanup; pending, stale, disabled, timed-out, and failed cleanup states fall back to Original, and an explicit per-draft Original selection survives reruns until Clear or reload. Cleanup and publication failures provide persistent, expandable, copyable safe details without including operating text, provider payloads, credentials, stack traces, or private paths.

Normal startup only checks schema state. Development-state administration is explicit:

```sh
scripts/dev.py status --state NAME
scripts/dev.py initialize --state NAME
```

Use `scripts/dev.py restart --state NAME` for a real update rather than running
migration steps individually. It runs all checks, makes an online SQLite backup,
migrates, applies the deterministic seed release, and restarts only the selected
state-scoped service.

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

Do not use hot reload for validated coding tasks. Use the controlled
`scripts/dev.py restart --state NAME` workflow described above.

## State-scoped launchd service

Render a selected state's plist for review without changing machine state:

```sh
uv run python scripts/render-launchd-plist.py \
  --state feature-workflow > /tmp/local-text-development.plist
plutil -lint /tmp/local-text-development.plist
```

`restart` installs or reloads only the selected state's user agent. Runtime logs
and all future operating data belong in that external state directory, never in
this repository.

End-user Preferences and Keychain-backed credential management are deferred;
this developer-safety gate intentionally provides no Preferences or Keychain UI.

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
