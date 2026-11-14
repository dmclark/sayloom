#!/bin/sh

# @raycast.schemaVersion 1
# @raycast.title Stable: Open Sayloom
# @raycast.mode compact
# @raycast.packageName Sayloom Stable
# @raycast.icon 🧵
# @raycast.description Open the installed Stable release without updating it
# sayloom-owned-stable-opener: 1

set -eu

health_file=$(/usr/bin/mktemp "${TMPDIR:-/tmp}/local-text-stable-health.XXXXXX")
trap 'rm -f "$health_file"' EXIT HUP INT TERM

if ! /usr/bin/curl --fail --silent --connect-timeout 1 --max-time 2 \
  http://127.0.0.1:7532/health --output "$health_file" || \
  [ "$(/usr/bin/plutil -extract status raw -o - "$health_file")" != "ok" ] || \
  [ "$(/usr/bin/plutil -extract profile raw -o - "$health_file")" != "release" ]; then
  printf 'Sayloom: Stable is not healthy; use the Stable status/start command\n' >&2
  exit 1
fi

/usr/bin/osascript <<'APPLESCRIPT'
set targetURL to "http://127.0.0.1:7532/"
tell application "Google Chrome"
  set matchingWindow to missing value
  repeat with candidateWindow in windows
    if (URL of active tab of candidateWindow starts with targetURL) then
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

printf 'Sayloom Stable is ready\n'
