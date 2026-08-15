#!/bin/sh

# @raycast.schemaVersion 1
# @raycast.title Send to iTerm
# @raycast.mode compact
# @raycast.packageName Sayloom Development
# @raycast.icon 🧵
# @raycast.description Insert multiline Sayloom text into iTerm without submitting

set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$script_directory/lib.sh"

prepare_command
outgoing_file="$command_temp_directory/outgoing.txt"
fetch_outgoing_text "$outgoing_file"

/usr/bin/osascript - "$outgoing_file" <<'APPLESCRIPT'
on run argv
  set outgoingText to read POSIX file (item 1 of argv) as «class utf8»
  tell application "iTerm"
    activate
    if (count of windows) is 0 then error "iTerm has no open window"
    tell current session of current window to write text outgoingText newline NO
  end tell
end run
APPLESCRIPT

printf 'Sent to iTerm without submitting\n'
