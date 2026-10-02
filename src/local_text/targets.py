"""Validated target definitions and deterministic Raycast command generation."""

import hashlib
import re
import shlex
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class SendStrategy(StrEnum):
    SYNTHETIC_PASTE = "synthetic_paste"
    ITERM_WRITE = "iterm_write"


class TargetDefinition(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    application_name: str = Field(min_length=1, max_length=80)
    application_bundle_id: str = Field(min_length=3, max_length=255)
    icon: str = Field(default="🧵", min_length=1, max_length=16)
    send_strategy: SendStrategy

    @field_validator("display_name", "application_name", "application_bundle_id", "icon")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        if any(character in value for character in "\r\n\0"):
            raise ValueError("must be a single line")
        return value

    @field_validator("application_bundle_id")
    @classmethod
    def valid_bundle_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", value) or "." not in value:
            raise ValueError("must be a macOS application bundle identifier")
        return value


@dataclass(frozen=True)
class GeneratedCommand:
    content: str
    sha256: str


def command_filename(target_id: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,35}", target_id):
        raise ValueError("invalid target identifier")
    return f"sayloom-target-{target_id}.sh"


def _fetch_and_clipboard_library() -> str:
    return """LOCAL_TEXT_BASE_URL=${LOCAL_TEXT_BASE_URL:-http://127.0.0.1:7523}
command_temp_directory=""
clipboard_backup=""
clipboard_changed=0

copy_utf8_to_clipboard() { LC_ALL=en_US.UTF-8 /usr/bin/pbcopy; }
read_utf8_clipboard() { LC_ALL=en_US.UTF-8 /usr/bin/pbpaste; }
finish_command() {
  if [ "$clipboard_changed" -eq 1 ] && [ -n "$clipboard_backup" ]; then
    copy_utf8_to_clipboard < "$clipboard_backup" || true
  fi
  [ -z "$command_temp_directory" ] || /bin/rm -rf "$command_temp_directory"
}
trap finish_command EXIT HUP INT TERM
fail_command() { printf 'Sayloom: %s\\n' "$1" >&2; exit 1; }
command_temp_directory=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/local-text-raycast.XXXXXX") \\
  || fail_command "could not create temporary files"
outgoing_file="$command_temp_directory/outgoing.txt"
state_file="$command_temp_directory/outgoing-state.json"
http_status=$(/usr/bin/curl --silent --show-error --connect-timeout 1 --max-time 3 \\
  --output "$state_file" --write-out '%{http_code}' \\
  "$LOCAL_TEXT_BASE_URL/api/outgoing-state") \\
  || fail_command "outgoing state is unavailable"
[ "$http_status" = "200" ] || fail_command "outgoing state is unavailable"
value_type=$(/usr/bin/plutil -type outgoing_text "$state_file" 2>/dev/null) \\
  || fail_command "outgoing state is malformed"
[ "$value_type" = "string" ] || fail_command "outgoing state is malformed"
/usr/bin/plutil -extract outgoing_text raw -o "$outgoing_file" "$state_file" 2>/dev/null \\
  || fail_command "outgoing state is malformed"
[ -s "$outgoing_file" ] || fail_command "there is no outgoing text"
LC_ALL=C /usr/bin/grep -q '[^[:space:]]' "$outgoing_file" \\
  || fail_command "there is no outgoing text"
"""


def generate_command(target_id: str, definition: TargetDefinition) -> GeneratedCommand:
    filename = command_filename(target_id)
    title = definition.display_name.replace("\n", " ")
    app_name = definition.application_name.replace("\\", "\\\\").replace('"', '\\"')
    bundle_id = shlex.quote(definition.application_bundle_id)
    header = f"""#!/bin/sh

# @raycast.schemaVersion 1
# @raycast.title Send to {title}
# @raycast.mode compact
# @raycast.packageName Sayloom Targets
# @raycast.icon {definition.icon}
# @raycast.description Insert Sayloom outgoing text into {title} without submitting
# sayloom-owned-target: {target_id}
# sayloom-generated-file: {filename}

set -eu

"""
    if definition.send_strategy is SendStrategy.SYNTHETIC_PASTE:
        delivery = f"""cliclick=${{CLICLICK_PATH:-}}
[ -n "$cliclick" ] || cliclick=$(command -v cliclick 2>/dev/null || true)
[ -n "$cliclick" ] || [ ! -x /opt/homebrew/bin/cliclick ] || cliclick=/opt/homebrew/bin/cliclick
[ -x "$cliclick" ] || fail_command "cliclick is not installed"
/usr/bin/open -b {bundle_id} || fail_command "the destination application is unavailable"
/bin/sleep 0.3
clipboard_backup="$command_temp_directory/clipboard.txt"
read_utf8_clipboard > "$clipboard_backup" 2>/dev/null || : > "$clipboard_backup"
copy_utf8_to_clipboard < "$outgoing_file" || fail_command "could not prepare the clipboard"
clipboard_changed=1
"$cliclick" "ku:cmd,ctrl,alt,shift,fn" "w:80" "kd:cmd" "t:v" "ku:cmd" \\
  || fail_command "synthetic paste failed"
/bin/sleep 0.15
copy_utf8_to_clipboard < "$clipboard_backup" || fail_command "could not restore the clipboard"
clipboard_changed=0
"""
    else:
        delivery = f"""/usr/bin/osascript - "$outgoing_file" <<'APPLESCRIPT'
on run argv
  set outgoingText to read POSIX file (item 1 of argv) as «class utf8»
  tell application "{app_name}"
    activate
    if (count of windows) is 0 then error "destination has no open window"
    tell current session of current window to write text outgoingText newline NO
  end tell
end run
APPLESCRIPT
"""
    success_message = shlex.quote(f"Sent to {title} without submitting")
    content = header + _fetch_and_clipboard_library() + delivery
    content += f"printf '%s\\n' {success_message}\n"
    return GeneratedCommand(content=content, sha256=hashlib.sha256(content.encode()).hexdigest())


INITIAL_TARGETS: tuple[tuple[str, TargetDefinition], ...] = (
    (
        "amp",
        TargetDefinition(
            display_name="Amp",
            application_name="Amp",
            application_bundle_id="com.google.Chrome.app.bpgpkfmeagdpdcenbogglipmfkalmple",
            send_strategy=SendStrategy.SYNTHETIC_PASTE,
        ),
    ),
    (
        "iterm",
        TargetDefinition(
            display_name="iTerm",
            application_name="iTerm",
            application_bundle_id="com.googlecode.iterm2",
            send_strategy=SendStrategy.ITERM_WRITE,
        ),
    ),
    (
        "supacode",
        TargetDefinition(
            display_name="Supacode",
            application_name="Supacode",
            application_bundle_id="app.supabit.supacode",
            send_strategy=SendStrategy.SYNTHETIC_PASTE,
        ),
    ),
    (
        "vs-code",
        TargetDefinition(
            display_name="VS Code",
            application_name="Visual Studio Code",
            application_bundle_id="com.microsoft.VSCode",
            send_strategy=SendStrategy.SYNTHETIC_PASTE,
        ),
    ),
)
