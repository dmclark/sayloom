#!/bin/sh
set -eu

label="local.local-text.development"
repository_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
state_root="$HOME/Library/Application Support/local-text"
state_directory="$state_root/development"
log_directory="$state_directory/logs"
agent_directory="$HOME/Library/LaunchAgents"
plist="$agent_directory/$label.plist"
domain="gui/$(id -u)"

if [ ! -x "$repository_root/.venv/bin/uvicorn" ]; then
  echo "Locked environment is missing; run 'uv sync --locked' first." >&2
  exit 1
fi

umask 077
mkdir -p "$state_root" "$state_directory" "$log_directory" "$agent_directory"
chmod 700 "$state_root" "$state_directory" "$log_directory"
touch "$log_directory/service.log" "$log_directory/service-error.log"
chmod 600 "$log_directory/service.log" "$log_directory/service-error.log"

temporary_plist=$(mktemp "$agent_directory/.$label.XXXXXX")
trap 'rm -f "$temporary_plist"' EXIT HUP INT TERM
"$repository_root/.venv/bin/python" "$repository_root/scripts/render-launchd-plist.py" \
  > "$temporary_plist"
plutil -lint "$temporary_plist"
chmod 600 "$temporary_plist"
mv -f "$temporary_plist" "$plist"
trap - EXIT HUP INT TERM

if launchctl print "$domain/$label" >/dev/null 2>&1; then
  launchctl bootout "$domain/$label"
  sleep 1
fi
launchctl bootstrap "$domain" "$plist"

echo "Installed and loaded $label"
