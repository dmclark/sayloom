# Raycast publication destinations

Five Raycast commands open the isolated development workspace or insert current outgoing text into
Amp, iTerm, Supacode, and VS Code without submitting it.

## Sub-features

- `RAYCAST.INSTALL`: the standalone installer creates idempotent `dev-*` aliases in
  `~/.config/raycast/scripts` by default, accepts an explicit directory, recovers broken managed
  aliases after a disposable checkout is removed, and refuses to replace existing files or
  unrelated links.
- `RAYCAST.OPEN`: Open Sayloom raises an existing matching development window or creates one only
  after development health and profile checks pass.
- `RAYCAST.AMP`, `RAYCAST.SUPACODE`, `RAYCAST.VSCODE`: safe synthetic paste inserts without Return,
  releases sticky modifiers, and restores the prior clipboard.
- `RAYCAST.ITERM`: multiline insertion uses iTerm's direct write path and does not press Return.
- `RAYCAST.FAILURES`: unavailable, malformed, empty, and whitespace-only outgoing state fail safely.

## How to get to it (user POV)

- Run `scripts/install-raycast.py` or pass `--directory PATH` to install the command aliases.
- Invoke each of the five **Dev: …** commands from Raycast on a dedicated
  verification-only macOS host.
- For destination commands, first publish synthetic outgoing text through the isolated workspace,
  focus a disposable destination input, and preserve a synthetic clipboard sentinel.

## Driving and proof

Portable lane:

- Run the installer twice, recover a broken managed alias, and prove a conflicting destination
  leaves all broken managed aliases intact against a temporary directory; also run shell syntax
  and `tests/test_raycast.py`. Record exactly which installation and command contracts those tests
  exercise. This does not prove macOS interaction.

macOS integration lane:

- Point `LOCAL_TEXT_BASE_URL` only at the run-owned isolated service and verify its identity first.
- Exercise every command separately. Prove inserted text and cursor state, no submission, clipboard
  restoration for paste destinations, unchanged clipboard for iTerm, and no leaked temporary files.
- Exercise empty, whitespace, malformed, and unavailable state. Prove a safe error and no
  destination or clipboard mutation.
- Capture a sanitized transcript and visible destination result without real user text, private
  paths, or unrelated window contents.

## Gotchas

- Linux/orb success in `tests/test_raycast.py` is Portable `passed`; real Raycast and destination
  apps are macOS `unavailable` unless exercised on the dedicated host.
- Never repoint commands at the fixed stable development port for verification.
- Clipboard screenshots can expose unrelated private data. Use a synthetic sentinel and crop to
  the disposable destination input.
