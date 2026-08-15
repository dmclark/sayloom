#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

exec "$repository_root/.venv/bin/uvicorn" \
  local_text.app:app \
  --host 127.0.0.1 \
  --port 8877 \
  --app-dir "$repository_root/src"
