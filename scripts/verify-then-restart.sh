#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repository_root"

uv sync --locked
uv run ruff check .
uv run pytest

launchctl kickstart -k "gui/$(id -u)/local.local-text.development"
