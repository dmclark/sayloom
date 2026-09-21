#!/bin/sh

LOCAL_TEXT_BASE_URL=${LOCAL_TEXT_BASE_URL:-http://127.0.0.1:7523}
command_temp_directory=""
clipboard_backup=""
clipboard_changed=0

copy_utf8_to_clipboard() {
  LC_ALL=en_US.UTF-8 /usr/bin/pbcopy
}

read_utf8_clipboard() {
  LC_ALL=en_US.UTF-8 /usr/bin/pbpaste
}

finish_command() {
  if [ "$clipboard_changed" -eq 1 ] && [ -n "$clipboard_backup" ]; then
    copy_utf8_to_clipboard < "$clipboard_backup" || true
  fi
  if [ -n "$command_temp_directory" ]; then
    /bin/rm -rf "$command_temp_directory"
  fi
}

trap finish_command EXIT HUP INT TERM

fail_command() {
  printf 'Sayloom: %s\n' "$1" >&2
  exit 1
}

prepare_command() {
  command_temp_directory=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/local-text-raycast.XXXXXX") \
    || fail_command "could not create temporary files"
}

fetch_outgoing_text() {
  destination=$1
  state_file="$command_temp_directory/outgoing-delivery.json"

  /usr/bin/curl \
    --fail \
    --silent \
    --show-error \
    --connect-timeout 1 \
    --max-time 3 \
    --request POST \
    "$LOCAL_TEXT_BASE_URL/api/outgoing-delivery" \
    --output "$state_file" \
    || fail_command "outgoing state is unavailable"

  status_type=$(/usr/bin/plutil -type status "$state_file" 2>/dev/null) \
    || fail_command "outgoing state is malformed"
  [ "$status_type" = "string" ] || fail_command "outgoing state is malformed"
  delivery_status=$(/usr/bin/plutil -extract status raw -o - "$state_file" 2>/dev/null) \
    || fail_command "outgoing state is malformed"
  if [ "$delivery_status" = "waiting_for_evidence" ]; then
    request_id=$(/usr/bin/plutil -extract request_id raw -o - "$state_file" 2>/dev/null) \
      || fail_command "outgoing state is malformed"
    attempts=0
    while [ "$delivery_status" = "waiting_for_evidence" ] && [ "$attempts" -lt 7200 ]; do
      /bin/sleep 0.25
      attempts=$((attempts + 1))
      /usr/bin/curl \
        --fail \
        --silent \
        --show-error \
        --connect-timeout 1 \
        --max-time 3 \
        "$LOCAL_TEXT_BASE_URL/api/outgoing-delivery/$request_id" \
        --output "$state_file" \
        || fail_command "outgoing state is unavailable"
      delivery_status=$(/usr/bin/plutil -extract status raw -o - "$state_file" 2>/dev/null) \
        || fail_command "outgoing state is malformed"
    done
  fi
  [ "$delivery_status" = "ready" ] \
    || fail_command "timed out waiting for Evidence Collection"

  value_type=$(/usr/bin/plutil -type outgoing_text "$state_file" 2>/dev/null) \
    || fail_command "outgoing state is malformed"
  [ "$value_type" = "string" ] || fail_command "outgoing state is malformed"
  /usr/bin/plutil -extract outgoing_text raw -o "$destination" "$state_file" 2>/dev/null \
    || fail_command "outgoing state is malformed"
  [ -s "$destination" ] || fail_command "there is no outgoing text"
  LC_ALL=C /usr/bin/grep -q '[^[:space:]]' "$destination" \
    || fail_command "there is no outgoing text"
}

paste_outgoing_text() {
  bundle_id=$1
  outgoing_file=$2
  cliclick=${CLICLICK_PATH:-}
  if [ -z "$cliclick" ]; then
    cliclick=$(command -v cliclick 2>/dev/null || true)
  fi
  if [ -z "$cliclick" ] && [ -x /opt/homebrew/bin/cliclick ]; then
    cliclick=/opt/homebrew/bin/cliclick
  fi
  [ -x "$cliclick" ] || fail_command "cliclick is not installed"

  /usr/bin/open -b "$bundle_id" || fail_command "the destination application is unavailable"
  /bin/sleep 0.3

  clipboard_backup="$command_temp_directory/clipboard.txt"
  read_utf8_clipboard > "$clipboard_backup" 2>/dev/null || : > "$clipboard_backup"
  copy_utf8_to_clipboard < "$outgoing_file" || fail_command "could not prepare the clipboard"
  clipboard_changed=1

  "$cliclick" \
    "ku:cmd,ctrl,alt,shift,fn" \
    "w:80" \
    "kd:cmd" \
    "t:v" \
    "ku:cmd" \
    || fail_command "synthetic paste failed"

  /bin/sleep 0.15
  copy_utf8_to_clipboard < "$clipboard_backup" || fail_command "could not restore the clipboard"
  clipboard_changed=0
}
