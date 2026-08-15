# Sayloom Development

A local-first Voiceitt dictation workspace. The minimal daily surface keeps editable Original and Cleaned text, fails open to the original when Gemini is unavailable, and publishes the selected outgoing text for Raycast. The Python package and machine-level identifiers are deliberately neutral and independent of the display brand.

## Setup

Requirements: macOS, Python 3.12+, and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
uv run uvicorn local_text.app:app --host 127.0.0.1 --port 7523
```

Open <http://127.0.0.1:7523/> or check <http://127.0.0.1:7523/health>.

The local default is the `development` profile and displays **Sayloom Development**. A release process can explicitly select release branding with `LOCAL_TEXT_PROFILE=release`. Application startup performs no database migrations.

## Gemini cleanup

Cleanup is enabled by default and always fails open to the unchanged Original text. Configure the development LaunchAgent by creating the external, user-only file `~/Library/Application Support/local-text/development/environment`:

```sh
LOCAL_TEXT_GEMINI_API_KEY=replace-with-your-key
# Optional:
# LOCAL_TEXT_GEMINI_MODEL=gemini-3.5-flash
# LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS=8
# LOCAL_TEXT_CLEANUP_ENABLED=0
```

Set its permissions to `0600`, then use the verified restart workflow below. The file and key must never enter Git. For one launch, `?cleanup=off` (or `?ai=0`) disables cleanup in the browser without changing configuration.

## Development

```sh
uv run ruff check .
uv run pytest
```

Do not use hot reload for validated coding tasks. After the user-level service is installed, use `scripts/verify-then-restart.sh`: it updates the locked environment, runs checks, and only then asks launchd to restart the service.

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

- **Open Sayloom**
- **Send to Amp**
- **Send to iTerm**
- **Send to Supacode**
- **Send to VS Code**

Raycast owns global hotkeys; no hotkey values are committed. Assign the familiar hotkeys to these development-branded commands in Raycast settings. Send commands refuse empty, malformed, or unavailable outgoing state and never press Return. Amp, Supacode, and VS Code use a Sticky-Keys-safe synthetic paste and restore the prior text clipboard. iTerm inserts multiline text directly without using the clipboard.

Gate 1 is complete only after testing Voiceitt dictation and all five bound commands on the real Mac. Confirm Open Sayloom both creates and raises the **Sayloom Development** Chrome window, Gemini success and fail-open status, cancellation, multiline iTerm insertion, target-app insertion without submission, clipboard restoration, and refusal of empty/unavailable state.

## Privacy

Never commit credentials, API keys, dictated or cleaned text, databases, logs, local `.env` files, or machine-specific paths. Use synthetic text in tests and documentation.
