# Target definition and command management

Targets are durable authored destination definitions. The web manager saves definitions separately
from explicit generation and installation of one Sayloom-owned Raycast command per enabled target.

## Sub-features

- `TARGETS.LIST`: a responsive overview grid presents every target plus an Add target tile; each
  tile opens a focused modal editor, and written state remains independent of color.
- `TARGETS.DEFINITION`: create and edit validate the bounded application identity, icon, and send
  strategy, persist authored configuration, warn before discarding changes, and never install.
- `TARGETS.GENERATE`: preview and installed content use the same deterministic generator and fetch
  only current `outgoing_text` without submitting.
- `TARGETS.INSTALL`: explicit Install/Regenerate writes only a recognized Sayloom-owned artifact,
  is idempotent, reports needs-update, and refuses unrelated files and links without mutation.
- `TARGETS.READINESS`: installation is observed separately from conservative application and macOS
  permission states; unproven platform facts remain written as not verified on the affected target.
- `TARGETS.LIFECYCLE`: Disable removes the recognized generated command but retains the definition;
  Remove deletes both after confirmation; neither changes Outgoing.
- `TARGETS.ISOLATION`: Open Sayloom and the four fixed development commands remain intact, hotkeys
  remain Raycast/user-owned, and no predecessor identity or artifact is discovered or changed.

## How to get to it (user POV)

- Open an isolated Sayloom Development instance and choose **Targets** in the utility navigation.
- Select Amp, iTerm, Supacode, or VS Code, or choose **New target** and a common preset/manual
  bounded definition.
- Use **Save definition**, **Install command** / **Regenerate command**, **Disable target**,
  **Enable target**, or **Remove target** as separate actions.

## Driving and proof

Portable lane:

- Run target domain/API/adapter tests with a disposable database and command directory. Prove
  validation, deterministic shell syntax, preview byte parity, outgoing-only/no-submit behavior,
  save-versus-install, needs-update, idempotency, collision refusal, persistent safe errors,
  lifecycle consequences, and Outgoing independence.
- Run migration proof from revision `0001_gate2_prompt_core`, preserving synthetic prompt rows,
  then explicitly seed exactly four target definitions. Prove startup against the old revision does
  not migrate it.

Isolated browser lane:

- With a fresh migrated/seeded database and disposable Raycast directory, navigate by accessible
  name. Exercise selection, edit/dirty/discard, Save, Install, Disable, Enable, and Remove with
  synthetic definitions. Prove each mutation by API read and command-directory inspection.
- At desktop and narrow widths, record DOM/ARIA facts, keyboard operation, accessibility audit, and
  inspected screenshots of the overview grid and modal editor. Verify written status and
  target-local error.

macOS integration lane:

- On a dedicated verification-only Mac, use disposable Sayloom-owned command identities. For all
  four initial targets verify application absent/present, relevant permission absent/present,
  UTF-8/multiline insertion, no Return/submission, clipboard restoration where applicable,
  regeneration, disable, remove, and Raycast hotkey retention behavior.

## Gotchas

- Linux/orb generation and adapter success is Portable only. Raycast, destination applications,
  clipboard behavior, application availability, permissions, and hotkey retention remain macOS
  integration checks.
- Never point the disposable command directory at a stable Raycast scripts directory and never use
  an existing database, fixed service, predecessor checkout, predecessor command package, or real
  outgoing text.
- Save and preview state do not prove installation; installation does not prove application or
  permission readiness; command invocation cannot claim successful insertion when the adapter
  cannot report it.
