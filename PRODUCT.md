# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

People with non-standard voices who use Voiceitt for dictation and cannot
rely on mainstream voice input tools. They need post-transcription cleanup
that Voiceitt does not provide natively. Currently a single personal user on
macOS; the long-term audience includes other Voiceitt users who handle
hotkey integration in their own way.

## Product Purpose

Sayloom is a local-first text cleanup workspace that takes raw input from
typing, paste, or compatible dictation, applies configurable provider-guided
copy-editing with immutable prompt versions and optional vocabulary profiles,
and publishes the selected outgoing text for delivery into other applications.
Current cleanup is source-preserving: it may normalize capitalization,
punctuation, apostrophes, and whitespace or remove leading filler words, but it
does not rewrite grammar, tone, or wording.

It fills the gap between Voiceitt — which transcribes non-standard voices but
does not clean up its output — and mainstream tools that clean up natively but
cannot serve these users. Success means a person with a non-standard voice can
dictate, copy-edit, and send trustworthy text as efficiently as someone using
a mainstream tool.

## Positioning

Mainstream voice input tools (built-in dictation, Otter, etc.) clean up
transcripts natively but fail for non-standard voices. Voiceitt serves those
voices but offers no cleanup. Sayloom is the layer that makes Voiceitt output
usable as trustworthy outgoing text, with prompt-managed cleanup, vocabulary
disambiguation, and one-action delivery to target applications.

## Operating Context

- **Current:** macOS desktop. Voiceitt runs as a Chrome extension and
  transcribes dictation into text fields. Raycast provides global hotkeys that
  send Sayloom's outgoing text into Amp, iTerm, Supacode, and VS Code without
  pressing Return.
- **Interim:** A downloadable version others can install and run on their own
  systems, handling hotkeys in their own way.
- **Future:** A hosted website offering cleanup processing, where users bring
  their own hotkey or delivery integration.
- **Predecessor:** Sayloom is the successor to Voiceitt Bridge, an independent,
  unaffiliated companion system. The parity doc
  (`docs/feature-workflow-parity.md`) reconstructs predecessor workflows as
  design evidence, not binding requirements.
- **Cross-project coordination:** The `voiceitt-orchestration` repository
  tracks architecture, decisions, boundaries, and compatibility milestones
  across related projects. Sayloom aligns with its privacy, boundary, and
  contract rules.

## Capabilities and Constraints

### Present in current code (validation status varies)

This list reports what is visible in the checkout. It does not imply that each
interaction has been fully exercised, accepted, or proven in regular use.

- Editable, collapsible Original field and read-only Cleaned result, vertically
  stacked with a resizable divider.
- Automatic source-preserving copy-editing on every Original update with a 700
  ms debounce. Provider output that adds, substitutes, reorders, or removes
  source words other than leading fillers is rejected and fails open to
  Original, as do unavailable or timed-out providers.
- Immutable cleanup-prompt versions with exact active-version selection,
  version history, and a full management dialog.
- Compact prompt selector in the Cleaned header. The control is present and
  currently writes the durable active version, but that behavior has not been
  validated through regular use. The desired UX instead distinguishes a
  durable default from a page-session selection.
- Outgoing text published via HTTP for Raycast commands to fetch and insert.
- Generic timeout, error, and unavailable states are visible, but the browser
  currently discards API response details. Inspectable error details are not
  implemented.
- SQLite-first persistence for authored configuration only (prompts, settings,
  seed state). No operating data in Git.
- Controlled verify-then-restart workflow; no migrations or seeds at normal
  startup.

### Proposed (not implemented or user-validated)

- Vocabulary profiles: durable local profiles with canonical terms and
  recognition aliases, independently activated, framed as untrusted
  disambiguation data during cleanup. No vocabulary model, API, or UI is present
  in the current checkout.
- Vocabulary suggestions: derive candidate recognition-alias → canonical-term
  pairs from meaningful differences between a successful Original and Cleaned
  result. Suggestions remain ephemeral until the user reviews and accepts or
  edits them; Sayloom never writes vocabulary automatically from model output.

### Version-one priority boundary

- Expanded prompt-version management is low priority and outside version one.
  Version one needs only the compact workspace selector and its page-session
  behavior; prompt authoring, history management, and changing the configured
  default do not need new UI work in this phase.

### Known gaps from parity analysis

- **Target management in web UI:** not implemented. Predecessor had a dedicated
  editable master-detail target manager.
- **Recording review and preparation:** not implemented. Predecessor had audio
  playback, transcript review, re-recording, and import staging.
- **Prompt model and lifecycle:** current code stores one global history of
  immutable cleanup-instruction versions and activates one exact version. The
  predecessor additionally modeled multiple stable logical prompts, each with
  versions, plus archive, conflict panels, owner overlays, and target-scoped
  activation. Those capabilities are not implemented in Sayloom.
- **Inspectable API errors:** current generic status labels do not expose which
  operation failed, the safe server-provided reason, or actionable detail.

### Open decisions

- The current main page is a positive reference, but its visual and interaction
  details remain open to redesign. Predecessor interactions are evidence rather
  than requirements unless confirmed separately.
- Whether Sayloom will continue to have one evolving cleanup instruction with a
  global version history, or eventually support multiple named prompts, each
  with its own history. The simpler single-history model should remain until a
  concrete workflow requires multiple prompt families.
- How vocabulary selection should behave. The recommended current-phase model
  keeps prompt selection and zero-or-more vocabulary-profile selection separate
  because they have different cardinality and trust semantics, while applying
  both to the same cleanup request.
- Whether recording review belongs in Sayloom or is deferred. If included,
  Sayloom would own the review and neutral snapshot export; training-specific
  conversion would remain in the `model-training` project. The cost and rework
  tradeoff of adding it now versus preserving extension points for later is
  evaluated in the UX shape plan.
- Whether Sayloom ever needs the predecessor's multiple logical prompts, owner
  overlays, target-scoped activation, and archive lifecycle. None is required
  for the current single-user phase without a concrete workflow that needs it.

### Durable constraints

- **Local-first and private:** All operating data (dictated text, cleaned text,
  databases, logs, API keys) stays on the machine and never enters Git. Only
  authored configuration is persisted.
- **Neutral identifiers:** The Python package and machine-level service use
  `local_text` / `local.local-text.development`, deliberately decoupled from
  the display brand "Sayloom."
- **No migrations at startup:** Normal app startup only checks schema state;
  migrations and seeds are explicit admin commands.
- **Controlled restarts:** Use `scripts/verify-then-restart.sh` for validated
  changes, not hot reload.
- **Fails open:** If cleanup is unavailable, times out, or returns output beyond
  the source-preserving copy-edit contract, outgoing text falls back to the
  original raw input. The user is never blocked.
- **Visible and inspectable failures:** API failures show a concise summary at
  the affected workflow and offer persistent, expandable safe details. Details
  may include the operation, time, HTTP status, stable error code, sanitized
  server message, and recovery action, but never credentials, request headers,
  raw or cleaned text, private paths, provider payloads, or stack traces.
- **Prompt selection scope:** One prompt version is the durable configured
  default. Choosing another version in the workspace creates a page-session
  selection that continues across cleanup runs, drafts, and in-app navigation.
  A full page reload ends that selection and restores the configured default.
- **Adaptable text workspace:** The Original/Cleaned split remains resizable,
  and Original can be collapsed without discarding its contents. Collapsing it
  is the CART-style open-caption interaction: the current cleaned or fail-open
  text receives the available output space without creating persisted caption
  history. This behavior remains in version one.
- **One hotkey per target (current phase):** Sending to Amp/iTerm/Supacode/VS
  Code is one fixed Raycast command per target, not a dispatcher. This is a
  current-phase constraint, not a permanent product decision — the future
  hosted version leaves hotkey integration to the user.
- **Predecessor coexistence:** The predecessor continues to run locally on its
  own port while it remains needed. Sayloom must use distinct service, port,
  storage, window, Raycast-package, and command identities and must never
  inspect, modify, stop, or reuse the predecessor's private runtime state.
- **Public-safe from first commit:** The repository is local-first and
  public-safe from its first commit. Never add real user content, credentials,
  private machine paths, or copied legacy implementation.
- **Independent identity:** Sayloom is an independent, unaffiliated companion
  system that works with Voiceitt. It is not part of the Voiceitt company or
  product. Voiceitt accounts, subscriptions, services, and branding remain
  under Voiceitt's control.

## Evidence on Hand

- `docs/feature-workflow-parity.md`: parity inventory reconstructing
  predecessor workflows from Amp threads, Mandrel records, and screenshots.
  Treated as design evidence, not binding requirements.
- `voiceitt-orchestration` README: cross-project architecture, repository
  boundaries, privacy rules, and contract/data-flow decisions.
- Committed code in this repository: current prompt core, cleanup, and UI
  implementation.
- Predecessor Amp threads and Mandrel records referenced in the parity doc.
- No real user content, transcripts, recordings, or credentials are in this
  repository. Future work must not fabricate testimonials, customers, or
  deployment claims.

## Product Principles

1. **Never block the user.** Cleanup is optional and fails open. The user
   always has their original text and can send it at any time.
2. **Persist only what the user authored.** Prompts, settings, and vocabulary
   profiles are durable. Dictated text, cleaned output, and transcripts are
   ephemeral and private. A generated vocabulary suggestion becomes authored
   configuration only after explicit user acceptance or editing.
3. **Clean for non-standard voices.** Every design decision should serve users
   whose voices mainstream tools cannot handle. Do not assume clean source
   input.
4. **Bridge, don't replace.** Sayloom sits between Voiceitt and the user's
   target applications. It enhances transcription output without replacing
   Voiceitt or the downstream tools.
5. **Progressive delivery.** Start as a personal local tool, grow into a
   downloadable version, then a hosted service. “Standalone” means that an
   earlier phase has no runtime dependency on a later one; it does not mean
   building separate copies. Reuse the same domain logic, contracts, and UI
   components wherever their behavior is genuinely shared, with thin
   platform-specific adapters at local delivery and hosting boundaries.
