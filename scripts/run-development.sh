#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
state_directory=${LOCAL_TEXT_STATE_DIRECTORY:-"$HOME/Library/Application Support/local-text/development"}
environment_file="$state_directory/environment"

if [ -f "$environment_file" ]; then
  set -a
  # This user-owned file lives outside Git and contains only shell-style assignments.
  # shellcheck disable=SC1090
  . "$environment_file"
  set +a
fi

exec "$repository_root/.venv/bin/uvicorn" \
  local_text.app:app \
  --host 127.0.0.1 \
  --port 7523 \
  --app-dir "$repository_root/src"
