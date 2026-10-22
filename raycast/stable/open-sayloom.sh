#!/bin/sh

# @raycast.schemaVersion 1
# @raycast.title Stable: Open Sayloom
# @raycast.mode compact
# @raycast.packageName Sayloom Stable
# @raycast.icon 🧵
# @raycast.description Open the independently installed daily-use Sayloom Stable window

set -eu
health=$(/usr/bin/curl --fail --silent --connect-timeout 1 --max-time 2 http://127.0.0.1:7532/health) \
  || { printf 'Sayloom Stable is unavailable; check local.local-text.stable\n' >&2; exit 1; }
printf '%s' "$health" | /usr/bin/grep -Eq '"profile"[[:space:]]*:[[:space:]]*"release"' \
  || { printf 'Port 7532 is not the release instance\n' >&2; exit 1; }
/usr/bin/osascript <<'APPLESCRIPT'
set targetURL to "http://127.0.0.1:7532/"
tell application "Google Chrome"
  set matchingWindow to missing value
  repeat with candidateWindow in windows
    if title of candidateWindow contains "Sayloom Stable" then
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
