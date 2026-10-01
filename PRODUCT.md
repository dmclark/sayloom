# Sayloom product contract

<!-- impeccable:product-schema 1 -->

- **Status:** Confirmed product authority
- **Audience:** Product, design, engineering, research, and delivery contributors
- **Authority:** This document is the sole authority for Sayloom's product
  vision, positioning, roadmap direction, audience, and scope.
- **Confirmed:** 2026-10-01

## Authority and supersession

This document supersedes every earlier statement of Sayloom product vision,
positioning, roadmap, audience, long-term outcome, or feature scope in the
repository and in Mandrel. Earlier product narratives are historical evidence
only. They do not authorize work or override this contract.

Technical, operational, evaluation, and design documentation remains
authoritative for verified current implementation facts within its stated
domain. When current behavior differs from this contract, describe the
difference explicitly as an implementation gap; do not weaken the product
direction to match the code.

## Platform

web

## Product Purpose

Sayloom helps people with non-standard speech turn imperfect Voiceitt-generated
text—including words Voiceitt misunderstood—into the text they intended, then
prepare that text for copying or delivery to another application.

Sayloom receives text, never voice recordings. It cannot verify what a person
said against audio. It instead uses the supplied text, surrounding context,
user-controlled preferences, and user-specific knowledge to infer likely
recognition errors. The user remains the authority on intended meaning.

Sayloom is the product. Voiceitt Bridge is its predecessor. Sayloom is an
independent, unaffiliated companion to Voiceitt; it is not part of the Voiceitt
company or product.

## Positioning

Sayloom is the intended-text correction and preparation layer between Voiceitt
and the applications where a user communicates. It complements Voiceitt rather
than replacing speech recognition, and it does not claim access to the original
speech.

## Users

The primary audience is Voiceitt users with non-standard speech, beginning with
one local macOS deployment and growing toward a public hosted service.

Sayloom is Voiceitt-first, not Voiceitt-exclusive. Its processing boundary
accepts text, so typed or pasted input from another source can use the same
workflow. Product claims and optimization remain focused on Voiceitt users
until broader support is demonstrated.

## Core text model

Sayloom uses three distinct values:

- **Original:** The editable text received from Voiceitt, typing, or paste.
- **Prepared:** Sayloom's generated result for the selected correction or
  polishing mode.
- **Outgoing:** The exact Original or Prepared value currently selected for
  copying or delivery.

The primary correction loop is:

1. Voiceitt places text in Original.
2. Sayloom generates Prepared text.
3. The user reviews the result when needed.
4. If Sayloom inferred the wrong wording, the user edits Original.
5. Sayloom regenerates Prepared from the edited Original.

This loop avoids requiring approval for every changed word while keeping the
user in control of intended meaning.

## Correction and polishing modes

The product supports two correction stages. A user may select Cleanup alone or
Smart followed by Cleanup. A remembered default and per-text override are
future product behavior.

- **Cleanup:** The account-independent, proven baseline. Each version freezes
  determinate eligibility and abstention rules for presentation fixes, spelling,
  and contextually obvious, effectively unambiguous misrecognitions. Cleanup
  may use a model, but its permitted behavior does not depend on a user account,
  Private correction profile, or Correction memory.
- **Smart correction:** The versioned moving frontier for less-determinate,
  contextual, or user-dependent repair. It may add, remove, or replace words,
  then passes its result through the same Cleanup baseline. Meaning-bearing
  changes remain reviewable, and uncertain changes receive additional emphasis.
- **Broader polishing — Deferred:** Future modes may change grammar, tone, or
  wording beyond recognition-error correction. Their exact boundaries are not
  yet decided.

The current source-preserving **Conservative preparation** is an incomplete
implementation stage of Cleanup, not a permanent third mode. A Smart behavior
may graduate into a new Cleanup version only after a separately frozen rule,
evidence slice, safety thresholds, and Cleanup regression coverage establish
that it is determinate and account-independent. Cleanup and Smart versions do
not change during a registered evaluation or silently inside a released result.

## Personal Corrections and research boundary

**Personal Corrections** serve live personalization for one local user. Sayloom
saves a Personal Correction only after the user explicitly reviews and approves
an **Original → Intended** mapping. Saving authorizes that correction for use in
later sessions until the user edits, disables, or deletes it. Ordinary editing,
processing, copying, delivery, dismissal, or inaction saves nothing.
Editing a saved mapping ends its prior authorization; the edited Original →
Intended mapping must be reviewed and explicitly saved before live reuse.

The durable owner ID is the internal constant `local`. The local product has no
account, login, owner selector, or owner-management interface. Accounts remain
deferred until multi-user, device-sync, or hosting boundaries exist.

Personal Corrections are product state, not research collection. Product copy
says **save a Personal Correction**, not “data collection.” Formal evaluation
is deferred. Any renewed research requires a new explicitly approved evaluation
purpose and contract; ordinary use and saved corrections do not authorize
research reuse.

Evidence Collection is superseded direction and is scheduled for removal from
the Workspace, runtime APIs, arming and lease logic, participant-package
tooling, and dedicated tests. Historical documentation and Git history remain.
These surfaces still exist in the current runtime until that later retirement
phase is implemented.

## Review and CART display

When Original is visible, the review experience identifies every word addition,
removal, or replacement and emphasizes uncertainty. AI confidence is assistance,
not proof; the user can always edit Original and regenerate.

When Original is hidden, the workspace is in CART-style display mode. Prepared
or fail-open text uses the available output space without inline correction
markings. Hiding Original changes presentation only: it does not change the
selected correction mode or silently switch processing behavior.

## User-specific personalization

Personalization belongs exclusively to one user. Information learned from one
person must never affect another person's corrections.

Users can inspect, edit, disable, or delete each saved Personal Correction.
Only an explicitly reviewed and approved Original → Intended mapping becomes
durable personalization. Its authorization persists across sessions until the
user edits, disables, or deletes it. A reviewed and explicitly saved edit starts
new authorization for the edited mapping.

Private correction profiles and Correction memory inform Smart only in the
initial product contract. Core Cleanup remains independently usable and
evaluable without an account or user-specific state. Any future profile-backed
Cleanup extension requires its own versioned contract and evaluation and may
not weaken the anonymous Cleanup baseline.

In the local application, personalization stays in private state owned by
`local`. Personalization does not imply model training, cross-user learning,
evaluation, or consent to use private text for another purpose. Hosted identity
and account isolation remain future decisions for a real hosting boundary.

## Operating Context

The hosted service is the intended primary public offering. The local
application remains available as a privacy-focused option. Both forms implement
the same product purpose but may use different delivery and provider adapters.

### Local application

- Optimized initially for a personal macOS workflow.
- May use user-supplied provider credentials.
- Can publish Outgoing text to local integrations such as Raycast commands.
- Keeps operating data and personalization outside Git in private local state.
- Moves development-state data to
  `${XDG_DATA_HOME:-~/.local/share}/local-text/dev-states/` only through an
  explicit migration; normal startup never migrates it.
- Gives each development state an independent Personal Corrections snapshot.
  New states inherit and verify a transactional snapshot from the eligible
  source explicitly activated for creation before activation.
- Fails initialization when an eligible source exists but inheritance fails;
  when no source exists, reports an empty profile explicitly.
- Performs no post-creation synchronization or backfill, so parallel states may
  diverge.
- Limits UI deletion to the current state. Cross-state purge is a separate
  preview-and-confirm administration action over registered states only.

### Initial hosted service

- Provides correction, review, personalization, and copying of Prepared text.
- May launch without automated delivery into target applications.
- Requires a separate account and isolation design once hosting creates that
  boundary; the local Personal Corrections contract does not pre-decide it.
- Uses Sayloom-managed third-party AI provider access by default, with clear
  disclosure, appropriate privacy terms, and no provider training on user
  content.
- May support bring-your-own provider keys later.
- Keeps Original and Prepared text ephemeral. It persists only the account
  configuration and user-specific personalization needed for the service.

## Delivery

Local delivery currently uses one explicit command per target and never presses
Return automatically. Outgoing must remain inspectable so the user knows the
exact value an integration will consume.

The initial hosted service may stop at copying Prepared text. Automated hosted
delivery is a future integration problem and does not block the core hosted
offering.

## Success

Sayloom succeeds when it:

- produces text that more often matches what the user intended;
- reduces the manual edits and time needed to prepare usable text;
- makes meaning-bearing changes and uncertainty reviewable without disrupting
  CART display;
- prevents confident but harmful corrections from becoming invisible; and
- keeps personalization private, controllable, and isolated to one user.

Accuracy and efficiency are joint outcomes. Speed without intended-meaning
accuracy does not solve the problem.

## Capabilities and Constraints

### Current implementation boundary

The current checkout is a useful local-first stage, not the complete product
described above. It provides an editable Original, a generated result named
**Prepared**, explicit outgoing selection, fail-open behavior, prompt
versions, inspectable failures, and local target commands.

Current automatic Cleanup is the Conservative implementation stage and rejects
lexical additions, removals, substitutions, duplication, or reordering. The
checkout also contains a single-method experimental Smart path and review
machinery, but not the evidence-selected automatic Smart strategy described by
this contract. The expanded Cleanup baseline, user-scoped learning, hosted
accounts, hosted provider management, and the hosted service are not
implemented unless later technical evidence says otherwise.

The checkout still contains Evidence Collection Workspace and runtime APIs,
arming and lease logic, participant-package tooling, dedicated tests, and
development-state paths under macOS Application Support. Their presence is a
current implementation fact pending the ordered migration and retirement work;
it does not make Evidence Collection current product direction.

Implementation and product design use **Prepared** for the generated result and
reserve **Outgoing** for the exact selected delivery value.

### Durable constraints

- **Never block the user:** Original remains available, and unavailable or
  failed processing must leave a usable path forward.
- **User authority:** Sayloom proposes intended wording; it does not claim to
  know what was spoken or override the user's correction.
- **Private by default:** Dictated text, generated text, credentials, databases,
  logs, and other operating data never enter Git.
- **Local ownership:** The durable local owner ID is `local`; no local account,
  login, or owner UI exists.
- **State isolation:** Development states hold independent Personal Corrections
  snapshots and may diverge after creation; they do not share one live database.
- **Credential separation:** API keys remain in protected shared configuration,
  never in a Personal Corrections database or export. Keychain is deferred.
- **Explicit learning control:** No cross-user learning, model training, or
  repurposing of private text follows from ordinary product use.
- **Repository hygiene:** Commit project context deliberately; never add
  credentials, private machine paths, or copied predecessor implementation.
- **Neutral technical identity:** Package and machine-level identifiers remain
  decoupled from the Sayloom display brand.
- **No startup migrations:** Normal application startup checks schema state but
  does not migrate or seed databases and does not move development-state files.
- **Controlled local lifecycle:** Validated changes use the controlled
  verify-then-restart workflow rather than hot reload.
- **Predecessor isolation:** Sayloom never inspects, modifies, stops, or reuses
  the predecessor's private runtime state.

## Deferred decisions

The following remain open and must not be presented as committed behavior:

- Exact future correction and polishing modes beyond Cleanup and Smart
  correction.
- Exact Cleanup lexical eligibility, abstention, and graduation thresholds.
- The technical method for detecting and presenting uncertainty.
- The hosted target-integration mechanism.
- Optional private text history; initial hosted text remains ephemeral.
- Timing and design of hosted bring-your-own-key support.
- Personalization methods and retention controls beyond the confirmed first
  Personal Corrections contract.
- Hosted accounts, device sync, and their ownership boundary until a real
  multi-user, synchronization, or hosting requirement exists.
- Keychain storage for API keys.
- Any renewed research or evaluation purpose and contract.

## Evidence on Hand

- The confirmed product interview and decision ledger in
  https://ampcode.com/threads/T-01a05f4e-9fac-71ec-96dc-2fea35b0d4e4.
- The accepted Personal Corrections ownership and state-portability decision in
  [`docs/adr/0002-personal-corrections-ownership-and-state-portability.md`](docs/adr/0002-personal-corrections-ownership-and-state-portability.md).
- The confirmed Cleanup, Smart, evaluation, and participant-boundary ledger in
  https://ampcode.com/threads/T-3a6a2274-45b0-4568-ae30-9f2f8845818b.
- `ref:sayloom-product-contract` in the existing `voiceitt-bridge` Mandrel
  project.
- The current repository implementation and its technical documentation for
  verified shipped behavior.
- Superseded roadmap, UX-shape, and transcript-fidelity documents retained as
  historical evidence only.

## Product Principles

1. **Correct intended text, not speech.** Sayloom works from imperfect text and
   never claims to verify audio it does not receive.
2. **Keep the user authoritative.** Users can edit Original, regenerate
   Prepared, choose a correction mode, and control personalization.
3. **Make meaning-bearing changes reviewable.** Review supports trust without
   interrupting CART display.
4. **Never mix users' learning.** Personalization remains isolated, inspectable,
   and deletable.
5. **Separate current behavior from product direction.** Verified implementation
   facts do not silently narrow the confirmed product outcome.

## Documentation rule

Handoffs, plans, specifications, and Mandrel records should link to this file
and quote only the clauses that constrain their bounded task. They must not
restate a competing product narrative. Current implementation behavior,
proposed work, and confirmed product direction must always be labeled
separately.
