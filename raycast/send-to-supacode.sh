#!/bin/sh

# @raycast.schemaVersion 1
# @raycast.title Send to Supacode — Sayloom Development
# @raycast.mode compact
# @raycast.packageName Sayloom Development
# @raycast.icon 🧵
# @raycast.description Insert Sayloom outgoing text into Supacode without submitting

set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$script_directory/lib.sh"

prepare_command
outgoing_file="$command_temp_directory/outgoing.txt"
fetch_outgoing_text "$outgoing_file"
paste_outgoing_text "app.supabit.supacode" "$outgoing_file"
printf 'Sent to Supacode\n'
