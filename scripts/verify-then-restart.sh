#!/bin/sh
set -eu

repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
state_directory=${LOCAL_TEXT_STATE_DIRECTORY:-"$HOME/Library/Application Support/local-text/development"}
environment_file="$state_directory/environment"
cd "$repository_root"

unset LOCAL_TEXT_GEMINI_API_KEY GEMINI_API_KEY GOOGLE_API_KEY
uv sync --locked
uv run ruff check .
uv run pytest
/usr/bin/env node --check src/local_text/static/app.js
for shell_file in scripts/*.sh raycast/*.sh; do
  /bin/sh -n "$shell_file"
done
git diff --check

if [ -f "$environment_file" ]; then
  set -a
  # Load only after verification so checks never inherit application credentials.
  # shellcheck disable=SC1090
  . "$environment_file"
  set +a
  unset LOCAL_TEXT_GEMINI_API_KEY GEMINI_API_KEY GOOGLE_API_KEY
fi

database_path=${LOCAL_TEXT_DATABASE_PATH:-"$state_directory/local-text.sqlite3"}
backup_directory="$state_directory/backups"

umask 077
mkdir -p "$state_directory" "$backup_directory"
chmod 700 "$state_directory" "$backup_directory"
if [ -f "$database_path" ]; then
  backup_path="$backup_directory/local-text-$(date -u +%Y%m%dT%H%M%SZ)-$$.sqlite3"
  LOCAL_TEXT_BACKUP_SOURCE="$database_path" LOCAL_TEXT_BACKUP_DESTINATION="$backup_path" \
    uv run python -c 'import os, sqlite3
source = sqlite3.connect(os.environ["LOCAL_TEXT_BACKUP_SOURCE"])
destination = sqlite3.connect(os.environ["LOCAL_TEXT_BACKUP_DESTINATION"])
with destination:
    source.backup(destination)
destination.close()
source.close()'
  chmod 600 "$backup_path"
  echo "Backed up the development database to $backup_path"
fi

uv run python -m local_text.admin migrate
uv run python -m local_text.admin seed

launchctl kickstart -k "gui/$(id -u)/local.local-text.development"

attempt=0
while [ "$attempt" -lt 30 ]; do
  if health=$(/usr/bin/curl --fail --silent --show-error http://127.0.0.1:7523/health 2>/dev/null); then
    case "$health" in
      *'"status":"ok"'*|*'"status": "ok"'*)
        echo "Verified local.local-text.development health on 127.0.0.1:7523"
        exit 0
        ;;
    esac
  fi
  attempt=$((attempt + 1))
  sleep 1
done

echo "Development service did not become healthy after restart." >&2
exit 1
