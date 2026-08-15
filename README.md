# Sayloom Development

A minimal, local-first FastAPI foundation. The Python package and machine-level identifiers are deliberately neutral and independent of the display brand.

## Setup

Requirements: macOS, Python 3.12+, and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
uv run uvicorn local_text.app:app --host 127.0.0.1 --port 8877
```

Open <http://127.0.0.1:8877/> or check <http://127.0.0.1:8877/health>.

The local default is the `development` profile and displays **Sayloom Development**. A release process can explicitly select release branding with `LOCAL_TEXT_PROFILE=release`. Application startup performs no database migrations.

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
- port: `8877`

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

## Privacy

Never commit credentials, API keys, dictated or cleaned text, databases, logs, local `.env` files, or machine-specific paths. Use synthetic text in tests and documentation.
