#!/bin/sh

# @raycast.schemaVersion 1
# @raycast.title Open Sayloom
# @raycast.mode compact
# @raycast.packageName Sayloom Development
# @raycast.icon 🧵
# @raycast.description Open or raise the isolated Sayloom development window

set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$script_directory/lib.sh"

health_file=$(/usr/bin/mktemp "${TMPDIR:-/tmp}/local-text-health.XXXXXX")
trap 'rm -f "$health_file"' EXIT HUP INT TERM

is_healthy() {
  /usr/bin/curl \
    --fail \
    --silent \
    --connect-timeout 1 \
    --max-time 2 \
    "$LOCAL_TEXT_BASE_URL/health" \
    --output "$health_file" \
    && /usr/bin/grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' "$health_file" \
    && /usr/bin/grep -Eq '"profile"[[:space:]]*:[[:space:]]*"development"' "$health_file"
}

if ! is_healthy; then
  /bin/launchctl kickstart "gui/$(/usr/bin/id -u)/local.local-text.development" \
    || fail_command "the development service could not be started"
  attempt=0
  while [ "$attempt" -lt 20 ] && ! is_healthy; do
    /bin/sleep 0.15
    attempt=$((attempt + 1))
  done
  is_healthy || fail_command "the development service is not healthy"
fi

/usr/bin/osascript <<'APPLESCRIPT'
set targetURL to "http://127.0.0.1:7523/"
set titleFragment to "Sayloom Development"

tell application "Google Chrome"
  set matchingWindow to missing value
  repeat with candidateWindow in windows
    if (title of candidateWindow contains titleFragment) then
      set matchingWindow to candidateWindow
      exit repeat
    end if
  end repeat

  if matchingWindow is missing value then
    set matchingWindow to make new window
    set URL of active tab of matchingWindow to targetURL
  else
    set index of matchingWindow to 1
  end if
  activate
end tell
APPLESCRIPT

printf 'Sayloom Development is ready\n'
