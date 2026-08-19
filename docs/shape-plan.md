# Sayloom UX shape plan

Status: proposed design brief for review. This document shapes behavior and
information architecture only; it is not an implementation specification.

## Assumptions used for this shape

The supplied product brief supports a concrete interaction recommendation, but
the current code has not been fully validated through regular use and the
visual direction remains open. These decisions should be confirmed before
implementation:

- The personal macOS workflow is the current optimization target; the
  downloadable and hosted forms must remain possible without weakening that
  workflow now.
- The current main page is a positive reference, not a fixed design contract.
  Its useful hierarchy may be retained even if a later visual-direction round
  changes its styling or composition.
- Preparing live text is the dominant, repeated job. Prompt, vocabulary, and
  target management are lower-frequency setup jobs.
- A target is selected by its dedicated external hotkey, not inside the text
  workspace.
- A prompt selected in the workspace remains selected for subsequent cleanup
  and drafts until a full page reload restores the configured default.
- Resizing the Original/Cleaned split and collapsing Original are required
  workspace behaviors, not incidental details of the current page.
- Recording review is valuable predecessor evidence, but it is not required to
  complete the current text-cleanup workflow.
- Sayloom and the predecessor must continue to run side by side under distinct
  local identities until the predecessor is no longer needed.

The predecessor is the **Voiceitt Bridge** project. Its Mandrel records help by
preserving historical workflow, implementation, and boundary decisions—most
notably for prompt management, target management, and recording review. They
are useful evidence for understanding what was tried and why, but their trust
status still matters and they do not make predecessor behavior a Sayloom
requirement. The parity inventory that assembles this evidence was read from
the `feat/gate-2-durable-prompt-core` branch because it is not present in this
checkout. No predecessor runtime, private checkout, data, or configuration was
accessed.

## 1. Job and audience

Sayloom is an **Operate-mode** workspace for a person with a non-standard voice
who needs to turn imperfect transcription into usable outgoing text without
breaking concentration. The primary user may arrive repeatedly throughout the
day, often with another application already waiting for the result.

The jobs, in priority order, are:

1. **Prepare text:** type, paste, or dictate raw text and obtain a cleaned
   candidate.
2. **Verify the outgoing value:** compare Original and Cleaned, understand any
   failure, and know exactly which one an external command will use.
3. **Deliver it:** invoke the fixed hotkey for the intended target without
   submitting the text automatically.
4. **Tune cleanup:** choose a prompt version for the current page session and
   maintain vocabulary when the default behavior is insufficient. Expanded
   prompt authoring and history management come later.
5. **Maintain destinations:** configure and repair the local commands that
   deliver outgoing text.
6. **Review recordings:** inspect and prepare audio/transcript pairs. This is a
   distinct, deferred workflow rather than part of live text preparation.

The daily path must remain faster and more prominent than every setup path.

## 2. Outcome and proof

The primary outcome is a prepared outgoing value that the user can trust and
send immediately. Success is visible when the workspace answers all of these
questions without opening a manager:

- What did I provide?
- What did cleanup produce?
- Which prompt and vocabulary affected that result?
- Is the result current, still processing, or unavailable?
- If an operation failed, what failed, why, and what can I safely do next?
- Will the next target hotkey use Original or Cleaned?
- Is the outgoing state available to the delivery integration?

Sayloom-specific proof is the complete, legible chain from imperfect source to
outgoing value, including raw fail-open behavior. A generic two-pane editor is
not enough; the current transformation context and outgoing selection must be
part of the visible state.

## 3. Selected direction

### Visual authority

The incumbent interface is evidence, not a locked visual system. The main page
has a useful task hierarchy—numbered navigation, vertically stacked text
panels, and compact operational status—and the user likes its general look.
Those strengths are worth preserving unless a proposed replacement improves
the daily workflow, but its palette, typography, materials, navigation form,
and detailed composition remain open.

This plan selects an information architecture and interaction model only. A
visual-direction decision must precede UI implementation; a builder must not
mistake the current CSS for an approved durable design system.

### Structural thesis

Use **one live workspace and two version-one setup areas**:

```text
Workspace                 Vocabulary                    Targets
─────────                 ──────────                    ───────
Original                  Profiles                      Definitions
  ↓                       Terms + aliases               Install status
Session prompt + vocabulary                             Permissions
  ↓
Cleaned
  ↓
Outgoing selection ───────────────────────────────▶ fixed target hotkeys
```

Original, Cleaned, and Outgoing remain the visual spine. Prompt and vocabulary
are shown at the point where they affect Cleaned, while their detailed editing
stays out of the daily canvas. Version one provides detailed editing for
Vocabulary, but not for prompt versions. Targets consume Outgoing but do not
change how it is prepared.

The focal moment is the outgoing strip: it must show both the selected source
and publication readiness. Processing status and delivery readiness are
separate facts and must not be collapsed into one success indicator.

The workspace must retain its **resizable split** and **Hide input** behavior.
Collapsing Original preserves its contents and expands the output-focused
experience; a persistent, obvious control restores the input. This existing
interaction is the **CART-style open-caption display** and remains in version
one. It is not a separate future feature, and it does not imply persisted
caption history or a new content-retention model.

### Product object model

| Object | Meaning | Editable? | Persistence | Relationship |
| --- | --- | --- | --- | --- |
| Original | Current raw source and dictation target | Yes | Ephemeral | Input to cleanup and fail-open outgoing value |
| Prompt version | One exact immutable version in the current global cleanup-instruction history | New versions only | Version and configured default are durable; workspace override is session-only | One configured default plus an optional page-session selection |
| Vocabulary | Canonical terms plus recognition aliases | Yes | Durable | Zero or more active profiles, independent of prompt |
| Cleaned | Candidate generated from the current Original, prompt, and vocabulary | No | Ephemeral | Valid only for the transformation context that produced it |
| Outgoing | The exact value exposed to delivery integrations | Selection only | Ephemeral | Uses a current Cleaned result or Original |
| Target | A local destination command and its installation state | Yes | Durable local configuration | Reads Outgoing; never owns prompt or vocabulary selection |
| Recording review item | Audio plus review-specific transcript state | Later | Private operating data outside Git | Separate from live Original, Cleaned, and Outgoing |

This model deliberately rejects an editable third “final text” field for the
current phase. Manual correction happens in Original followed by cleanup, or
the user explicitly chooses Original as outgoing. That keeps one editable text
source and one generated candidate.

The current prompt model is one cleanup instruction evolving through a single
global version history. It is not yet a collection of named logical prompts,
each with its own versions. Keep that simpler model for the current phase unless
a concrete recurring need for multiple cleanup modes is identified; otherwise
the UI would imply a domain model the storage and API do not have.

## 4. Scope and boundaries

### Current personal-macOS phase

In scope for the shaped surface:

- Preserve the existing Original → Cleaned workflow, automatic cleanup,
  manual rerun, collapse, resize, clear, and raw fail-open behavior. Collapse
  and resize are explicit product requirements.
- Make outgoing source selection explicit and unambiguous.
- Make every API failure visible and provide inspectable, privacy-safe details.
- Keep exact cleanup-instruction version selection visible in the workspace.
- Add the proposed independently active vocabulary profiles and their
  management surface; no vocabulary implementation exists yet.
- Generate reviewable vocabulary suggestions from meaningful Original →
  Cleaned differences without automatically changing a profile.
- Replace the placeholder utility item with local target management while
  preserving one hotkey per target.

### Deferred

- Expanded prompt-version management, including authoring, history browsing,
  changing the configured default, archive, and conflict handling. The existing
  unvalidated dialog is code evidence, not a version-one requirement.
- Recording review, re-recording, and neutral snapshot export.
- Training-specific conversion or model-training orchestration.
- Prompt owner overlays and target-scoped activation.
- Per-target prompt or vocabulary settings.
- A target chooser, default target, last-used target, or send button in the web
  workspace.
- Persisted text sessions, transcripts, cleaned output, recordings, send
  history, or queue state.
- Hosted-service destination management. The hosted form should expose its
  outgoing integration contract, while users own delivery and hotkeys.

### Predecessor decisions

Treat these predecessor behaviors as requirements or strong constraints:

- Cleanup never blocks the user and fails open to Original.
- Prompt activation identifies an exact immutable version.
- The current phase retains one dedicated hotkey per target.
- Target setup distinguishes definition, installation, availability, and
  operating-system permission states.
- Any future recording workflow keeps private media and review artifacts
  outside Git and separates review from training-specific conversion.

Treat these as references that may be redesigned:

- The predecessor's exact master-detail layouts and “More” navigation.
- An editable final-text field.
- Target-scoped prompt activation, owner overlays, archive controls, and
  conflict panels.
- Manifest-first recording entry, exact filters, and exact re-recording control
  arrangement.

## 5. Navigation and workflow decisions

### Top-level navigation

Use three persistent destinations in this order:

1. **Workspace** — live text preparation.
2. **Vocabulary** — profiles, canonical terms, and recognition aliases.
3. **Targets** — local delivery setup and health.

Do not show a disabled “More” item or a speculative Recordings item. When
recording review earns implementation, add **Recordings** as a separate
top-level destination. Do not create a generic “Data preparation” section
until more than one preparation workflow exists.

Do not reserve version-one navigation for expanded prompt management. If it is
prioritized later, group Prompt versions and Vocabulary under Cleanup at that
time rather than shipping an empty or low-value section now.

On desktop, preserve the compact utility rail. On narrow screens, use the same
order in a horizontal or compact navigation treatment. Navigation changes must
not discard unsaved authored configuration without confirmation.

### Workspace: text cleanup

- Keep Original above Cleaned. This follows the task sequence and works better
  for long dictation than a narrow side-by-side comparison.
- Preserve pointer and keyboard resizing between Original and Cleaned where the
  viewport can support a meaningful split.
- **Hide input** collapses Original into an output-focused state without
  clearing it. **Show input** restores the prior text and returns to the
  editable source. Neither action changes the selected prompt, vocabulary,
  Cleaned result, or Outgoing value.
- Treat this collapsed state as the CART-style open-caption interaction, not a
  conversation view or a deferred dedicated mode. The current cleaned or
  fail-open text uses the available output canvas, while **Show input** remains
  an obvious keyboard-operable exit.
- Keep Original editable and Cleaned selectable but read-only. The user can
  copy either, but only Original is an authoring surface.
- Place the active prompt selector and active vocabulary summary together in
  the Cleaned header because both are inputs to that result. Prompt is a
  single-select exact version; Vocabulary opens a zero-to-many profile chooser.
- Keep a durable configured prompt default separate from the prompt selected for
  the current page session. Choosing another version in the workspace persists
  across cleanup runs, clearing Original, subsequent drafts, and in-app
  navigation. Only a full page reload clears the session selection and restores
  the configured default.
- Prompt selection and vocabulary activation are independent and are not target
  scoped. Changing either invalidates the prior Cleaned result and reruns
  cleanup when automatic cleanup is enabled.
- Preserve keyboard focus and selection in Original while cleanup and
  publication update in the background.
- Show the active transformation context with the result. A Cleaned value is
  “current” only when it matches the present Original, prompt version, and
  active vocabulary set.

#### Outgoing selection

- Add an explicit **Outgoing: Cleaned / Original** control to the outgoing
  strip. It selects between the two existing values; it is not a third editor.
- After a current successful cleanup, Cleaned is the default. During waiting,
  cleanup, disabled, timeout, provider error, or a stale result, Cleaned is
  unavailable and Outgoing falls back immediately to Original.
- If the user explicitly chooses Original for the current draft, do not switch
  it back after a later rerun. Clear or reload resets this ephemeral override.
- If Cleaned was selected and Original changes, temporarily use Original while
  the replacement result is pending, then return to Cleaned on success.
- Label the fallback reason next to the selection; do not rely on color or a
  distant status pill.
- Sending through an external hotkey does not clear or archive the draft. The
  web app cannot claim delivery success unless an integration can report it.

#### API errors and details

Generic status alone is insufficient. Every failed API operation must expose
both an immediate summary and a way to inspect useful details without blocking
Original, raw fail-open, or sending.

- Show the summary at the control or status region that owns the operation:
  cleanup errors with cleanup status, publication errors with Outgoing,
  vocabulary errors with the affected profile or suggestion, and target errors
  with the affected target.
- Keep an error visible until the operation succeeds, the underlying state
  changes, or the user explicitly dismisses it. Do not use a transient toast as
  the only record of failure.
- Provide **View details** beside the summary. Its expandable panel shows the
  operation, local time, HTTP status when available, stable error code,
  sanitized server-provided message, and a concrete retry or setup action.
- Provide **Copy details** for support and debugging. The copied form uses the
  same sanitized fields shown on screen; it must not silently include more.
- Distinguish at least cleanup/provider, outgoing publication, configuration,
  vocabulary, and target-management failures. Multiple simultaneous failures
  remain separately identifiable rather than overwriting one generic status.
- Network failure, timeout, malformed response, and server rejection need
  distinct summaries even when they share the same retry action.
- Never display or copy API keys, authorization or request headers, Original or
  Cleaned text, full provider responses, stack traces, database contents,
  private paths, or other operating data. If the backend cannot provide safe
  detail, show the status/code and say that no additional safe detail is
  available rather than inventing a cause.
- Fail-open behavior remains independent: an error can be fully inspectable
  while Outgoing continues to use Original.

This requires a structured safe-error contract from the API. The browser must
not parse arbitrary exception text, and the server must sanitize provider and
configuration failures before returning user-visible detail.

### Future: expanded prompt-version management (not version one)

Version one keeps only the compact workspace selector and its page-session
behavior. Do not spend version-one work replacing, expanding, or promoting the
current unvalidated management dialog. When prompt management is prioritized:

- Use a list/detail surface that can grow beyond a modal. The list shows
  version, title, source, creation time, and active state; selecting a version
  previews it without activating it.
- Historical versions remain read-only. “Use this version” is explicit and
  separate from list selection; it selects the version for the current page
  session without changing the configured default.
- “Create version from this” copies the chosen version into a draft. Saving
  creates a new immutable version and selects it for the current page session.
  It does not silently replace the durable default.
- Provide a separate, explicit **Make default** action. The configured default
  is the version restored by a full page reload.
- Warn before navigation discards an unsaved draft. This is ordinary authored
  data protection, not the predecessor's deferred multi-writer conflict model.
- Keep the configured default global to the workspace and the temporary
  selection scoped to the page session. Do not expose target scope, owner
  scope, overlays, archive, or conflict resolution in this phase.
- A prompt change reruns live text only when Original is non-empty, and the
  workspace must make the resulting invalidation visible.
- Label this as a history of **Prompt versions** or **Cleanup instruction
  versions**, not as a library of independent prompts. If multiple named
  prompt families become a real requirement, change the domain model before
  reshaping the UI around them.

### Vocabulary management (version one)

- Give Vocabulary its own version-one setup area. Preserve the distinct model:
  prompt versions are immutable instructions; vocabulary profiles are editable,
  untrusted disambiguation data. If expanded prompt management is added later,
  both may be grouped under Cleanup without merging their data models.
- The profile list shows name, term count, and active state. Multiple profiles
  may be active at once.
- The detail view edits canonical terms and their recognition aliases. Make
  the canonical value visually primary and aliases subordinate.
- Support add, edit, remove, validation, duplicate detection, empty profiles,
  and a clear saved/error state. Never store example dictated passages merely
  to explain a term.
- Activation is available both in management and from the compact workspace
  chooser. Both update the same durable workspace default.
- Any vocabulary sent to cleanup must be framed as data, never as executable
  prompt instruction. The UI should explain that profiles help disambiguate
  recognition; they do not replace the cleanup prompt.

#### Vocabulary suggestions from Original → Cleaned

Use successful cleanup differences as a fast way to author vocabulary, not as
ground truth. The cleanup model may also change punctuation, grammar, tone, or
wording, so Sayloom must never add every difference or write a profile without
review.

- After a current successful cleanup, identify differences that plausibly map
  an observed source word or phrase to an intended canonical term. Ignore
  formatting-only changes and suppress generic rewrites that are not useful
  recognition aliases.
- Show a quiet **Vocabulary suggestions** affordance only when candidates
  exist. It must not interrupt dictation, cleanup, outgoing selection, or send
  hotkeys.
- Present each candidate as **Heard/Original** → **Canonical/Cleaned**, with a
  destination profile. The user can edit either side, choose a profile, accept,
  or dismiss.
- Acceptance creates ordinary authored vocabulary using the reviewed canonical
  term and alias. Dedupe against existing canonical terms and aliases before
  saving, and explain whether the candidate will add an alias or create a term.
- Suggestions and the source/cleaned fragments that produced them are
  page-session state. Persist only the accepted vocabulary entry; never persist
  the full Original, Cleaned result, surrounding passage, rejected candidate,
  or dismissal history.
- Do not generate suggestions from unchanged, pending, stale, disabled,
  timeout, provider-error, or raw fail-open results.

The UX contract does not require one extraction technique. A focused
implementation gate should compare deterministic phrase diffing with narrowly
framed model-assisted candidate classification, then choose the simplest
approach that suppresses punctuation and prose rewrites reliably. Both paths
must produce the same review-before-save interaction.

#### Why vocabulary remains separate

The recommended current-phase choice is one selected prompt version—the durable
default or a page-session override—plus zero or more active vocabulary profiles,
combined when cleanup runs. Folding vocabulary into prompt versions would
duplicate terms across immutable versions and turn a small vocabulary
correction into unnecessary prompt-version churn. Making vocabulary
request-scoped now would add per-draft state and persistence ambiguity before a
workflow has demonstrated the need.

Deferring request-scoped overrides is inexpensive if the future cleanup
contract accepts explicit profile identifiers rather than reading UI state
implicitly. When a second real consumer such as Recording review appears,
extract and reuse the selection control and cleanup-context contract; do not
copy the workspace implementation or build a speculative shared framework now.

### Targets: local delivery management

- Use a master list plus selected-target detail on desktop; use list-to-detail
  navigation on narrow screens. The pattern is appropriate, but the
  predecessor's visual implementation is not binding.
- The list groups production and development only when both environments
  actually exist. Each row shows display name, application identity, and one
  state: installed, needs update, disabled, unavailable, or needs permission.
- “New target” starts with discovered applications and common presets, with a
  manual path for an application that cannot be discovered.
- The detail view separates:
  1. authored definition (name, application identity, icon, send strategy),
  2. derived command preview, and
  3. current installation/permission state.
- Keep **Save definition** separate from **Install/Regenerate command** so a
  configuration edit does not silently alter Raycast.
- Provide explicit Disable and Remove actions with consequences stated before
  confirmation. Removing a target never changes or clears Outgoing.
- Explain required macOS automation permissions at the failing target, with a
  retry/check action. Do not show a global success state when only the command
  definition is valid.
- Do not add target ordering, default/last-used state, or workspace target
  selection. The target hotkey itself expresses destination intent.
- Generate command previews and installed commands from one target definition
  and generation path. Do not maintain separate UI and Raycast copies of target
  behavior.
- Never discover, import, alter, or disable the predecessor's target commands,
  service, port, storage, or Raycast package. Similar capabilities do not make
  its private runtime a reusable integration surface.

### Recording review: deferred shape

Recording review does belong within Sayloom's long-term product boundary only
as **local review and neutral snapshot export**. The recommendation is to defer
its implementation, not to design it out.

Adding it now would settle navigation and shared controls earlier, but it would
also require a recording model, private media locations, audio permissions,
playback and replacement safety, interrupted-review recovery, retention rules,
and an export contract. That is a second operating-data domain with materially
more privacy and failure-state work than the current text workflow. Building it
before those decisions are known risks preserving the wrong predecessor model
and delays validation of the core cleanup path.

Deferring it means adding a fourth navigation destination and a new backend
domain later. That rework is bounded if the navigation can accept another item
and cleanup context is passed through explicit contracts. It does **not**
justify adding empty recording routes, tables, generic data-preparation models,
or abstractions now. The later implementation should reuse proven prompt,
vocabulary, status, and accessibility components where behavior is genuinely
shared, while keeping recording lifecycle code separate.

When separately shaped and implemented:

- Give it a top-level **Recordings** destination rather than placing it in the
  live workspace or under Cleanup.
- Treat a recording as its own review item, not as another way to populate the
  ephemeral Original field.
- Use recording-specific labels such as Imported transcript and Expected
  transcript rather than Original and Cleaned.
- It may reuse prompt inventory and vocabulary controls for request-scoped
  assistance, but it must not silently change the live workspace defaults.
- Keep playback, re-recording, review status, and neutral snapshot export in
  Sayloom. Keep training-format conversion and training runs in the
  `model-training` project.
- Do not connect reviewed recordings to text Outgoing or the target hotkeys.

### Reuse across product phases

- Personal, downloadable, and hosted forms should share cleanup, prompt-version,
  vocabulary, validation, and outgoing-state domain logic rather than fork into
  separate applications.
- Keep platform-specific behavior at explicit adapters: local service control,
  Raycast generation, and macOS permissions are local concerns; hosted
  authentication and delivery contracts are hosted concerns.
- Reuse existing behavior before adding wrappers. Extract a shared component or
  service when a second real consumer needs the same contract, not merely
  because a future consumer is imaginable.
- Reuse does not cross the predecessor boundary. Sayloom may reproduce a
  confirmed workflow from public-safe evidence, but it must not link to or copy
  the predecessor's private code, data, configuration, or runtime state.

## 6. States, content ranges, and feedback

### Workspace states

Cover empty, waiting for debounce, cleaning, changed result, unchanged result,
automatic cleanup disabled, timeout, provider error, stale result, publication
pending, publication ready, and publication unavailable. None may prevent
editing or choosing Original.

For every API-backed workflow, also cover network unavailable, timeout,
non-success HTTP status, structured safe detail, malformed/unknown response,
retrying, resolved, and dismissed. Error summaries and their detail controls
must remain keyboard accessible and must not be conveyed by color alone.

The source API currently accepts 0–100,000 characters. Design for a typical
short message through several paragraphs without making the maximum case
unusable. Character limits and overflow must be stated before submission, not
only after an API error.

### Authored configuration states

- The compact prompt selector must handle the available immutable versions, but
  version one does not need to optimize a full history-management surface.
- Future prompt manager, when prioritized: at least one seeded version, one
  configured default, dozens of ordinary historical versions, and a
  long-history case in the hundreds. Titles are up to 120 characters and
  instructions up to 100,000 characters.
- Vocabulary (provisional until its contract is confirmed): zero profiles,
  typically a small set of profiles with tens to hundreds of terms, and a
  stress case around 1,000 terms in one profile. Search/filter should appear
  when scanning the list would become slower than typing a query.
- Vocabulary suggestions: no candidates, analyzing, candidates available,
  duplicate detected, candidate edited, accepted, dismissed, and save failed.
  Analysis must not block cleanup or outgoing text.
- Targets: zero configured targets, the current set of four, and a larger local
  set around twenty. Empty discovery and manual setup must remain possible.

For every authored configuration surface, cover initial loading, empty,
selected, dirty, saving, saved, validation failure, storage failure, and
discard confirmation. Normal application startup must report setup-required
schema state rather than running migrations.

### Responsive and accessible behavior

- Preserve the vertically stacked text sequence at every width.
- On narrow screens, list/detail managers become sequential rather than
  compressing both columns.
- Keep all cleanup, selection, resize, navigation, and manager actions keyboard
  operable. Preserve the existing separator semantics when resizing remains
  present.
- Announce cleanup and publication changes without moving focus. Avoid repeated
  live-region announcements for each debounce tick.
- Do not encode active, stale, failed, installed, or disabled states by color
  alone.
- Respect reduced motion and text scaling. Status, prompt, and vocabulary
  controls must remain readable when labels wrap.

## 7. Constraints and decisions a builder must not invent

- All operating text, cleaned output, recordings, databases, logs, credentials,
  and generated private artifacts remain outside Git.
- The display brand is Sayloom; package and service identifiers remain neutral
  `local_text` identifiers.
- Normal startup does not migrate or seed the database.
- Cleanup fails open to Original, including while a result is pending.
- API errors remain visible and provide expandable, copyable, sanitized details
  at the affected workflow. Error reporting never exposes credentials,
  operating text, provider payloads, stack traces, database contents, or
  private paths.
- The Original/Cleaned workspace remains resizable and Original remains
  collapsible without content loss. That collapsed state is the version-one
  CART-style open-caption interaction and does not persist text or caption
  history.
- The prompt has one durable configured default and an optional page-session
  selection. The session selection survives reruns, drafts, clearing, and
  in-app navigation; only a full page reload restores the default.
- Vocabulary activation is a durable workspace default in this phase. Neither
  prompt nor vocabulary selection is target scoped.
- Vocabulary suggestions derived from Original/Cleaned differences are
  ephemeral and advisory. Only an explicitly reviewed acceptance may create
  durable vocabulary; no source passage or rejected suggestion is persisted.
- Target hotkeys choose the destination; the web workspace chooses only the
  outgoing text source.
- Sayloom must coexist with the running predecessor through distinct ports,
  services, storage, windows, Raycast packages, and command identities.
- Shared product logic should have one implementation with thin platform
  adapters; do not fork the personal, downloadable, and hosted phases.
- Recording review is not a hidden extension of the canvas. It requires a
  separate future shape covering storage locations, permissions, interruption
  recovery, retention, and export contracts.
- Do not implement predecessor-only owner, archive, conflict, manifest, or
  target-scope behavior without a new product decision.

Remaining validation before implementation:

1. Confirm the explicit Original/Cleaned outgoing selector and its per-draft
   override behavior with the current daily workflow.
2. Confirm vocabulary profile scale and editing constraints when its data
   contract is finalized.
3. Confirm which target installation and permission states the local runtime
   can observe reliably; the UI must not promise states it cannot verify.
4. Define the stable safe-error codes and sanitized detail available from each
   version-one API operation.
5. Run a visual-direction decision for the surface; the present main page is a
   liked reference, not a locked design.
6. Revisit Recording review only when its private storage, retention, recovery,
   and neutral-export contract can be shaped together.
