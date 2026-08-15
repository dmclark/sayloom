#!/bin/sh
set -eu

label="local.local-text.development"
domain="gui/$(id -u)"
plist="$HOME/Library/LaunchAgents/$label.plist"

if launchctl print "$domain/$label" >/dev/null 2>&1; then
  launchctl bootout "$domain/$label"
fi
rm -f "$plist"

echo "Stopped and removed $label; external state was preserved."
