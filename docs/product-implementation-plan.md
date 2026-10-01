# Sayloom product implementation plan

- **Status:** Approved sequence; implementation pending
- **Audience:** Product, design, engineering, research, and delivery contributors
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Architecture decision:** [ADR-0002](adr/0002-personal-corrections-ownership-and-state-portability.md)
- **Execution authority:** [Personal Corrections execution guide](personal-corrections-execution-guide.md)

## Purpose

This plan sequences the implementation gaps between the current local-first
application and the confirmed Sayloom product contract. It does not replace or
reinterpret `PRODUCT.md`. Each capability area has observable exit criteria;
implementation follows the issue order below and completes affected checks
before advancing.

The current product already provides Conservative source-preserving preparation, provider
routing, editable Original text, a generated result named Prepared,
explicit Outgoing selection, fail-open behavior, prompt versions, inspectable
failures, local Raycast delivery, and a bounded single-method Smart path with
server-derived repair metadata. A partial local Personal Corrections foundation
also exists. Complete meaning-bearing change review, live Personal Corrections,
state portability, hosted identity, managed hosted provider access, and the
hosted service remain implementation gaps.

The current runtime still contains Evidence Collection Workspace and runtime
APIs, arming and lease logic, participant-package tooling, dedicated tests, and
development-state paths under macOS Application Support. Those are current
implementation facts pending migration and retirement, not target direction.

## Current implementation sequence

Implementation proceeds in this order:

1. **State-root migration:** explicitly migrate registered development-state
   data to `${XDG_DATA_HOME:-~/.local/share}/local-text/dev-states/`. Normal
   startup never migrates files or schemas.
2. **Evidence Collection retirement:** remove it from the Workspace and runtime
   APIs, including arming and lease logic, participant-package tooling, and
   dedicated tests. Preserve historical documentation and Git history.
3. **Personal Corrections:** implement explicit Original → Intended review and
   approval, durable `owner_id = "local"`, cross-session live Smart use,
   management, state-scoped deletion, registered-state purge, and export.
4. **New-state inheritance:** copy and verify a transactional Personal
   Corrections snapshot from the eligible source explicitly activated for
   creation before activating the destination.

An eligible-source inheritance failure fails initialization before activation.
No source is an explicitly reported empty profile. Existing states receive no
backfill, no automatic post-creation synchronization occurs, and parallel
states may diverge. One shared live Personal Corrections database is rejected
because it would break parallel debugging-state isolation.

Accounts remain deferred until multi-user, device-sync, or hosting boundaries
exist. API keys remain in protected shared configuration and never enter a
Personal Corrections database or export; Keychain storage is deferred.

## Historical correction and evaluation sequence

The deferred automatic-correction prototype is documented in the staged plan in the
[focused specification](automatic-correction-prototype-spec.md), coordinated by
[the automatic-correction initiative](https://github.com/dmclark/sayloom/issues/46).
It preserves prior technical context but does not authorize evaluation,
provider execution, or runtime integration. Renewed research requires a new
approved evaluation purpose and contract.

The historical sequence below remains useful for the broader production Smart
and personalization path. Its fixed single-Smart-prompt evidence steps are
superseded and are not the current prototype strategy or acceptance authority.

```text
#6 vocabulary
    │
    ▼
#10 Smart Prepared generation
    │
    ├──────────────┐
    ▼              ▼
#11 repair review  #12 Private correction profile
    └──────┬───────┘
           ▼
#14 fixed-arm benchmark (superseded)
           ▼
Historical Smart MVP candidate
           ▼
#15 fixed-arm private run (superseded)
           ▼
Historical evidence-backed Smart MVP
           ▼
#13 optional memory + #16 local self-pilot
           ▼
Locally proven Smart product
           ▼
#17 Partner-demo ready
```

Issue [#9](https://github.com/dmclark/sayloom/issues/9) preserves broader
production Smart and personalization history. The linked
[evaluation map](evaluation-mvp-map.md) and focused prototype specification are
deferred references. They do not override the current four-phase sequence or
authorize collection, evaluation, provider execution, or pilot work.

## Capability area: Prepared vocabulary and mode foundation

### Outcome

Align the existing local product with the confirmed domain model without
changing conservative correction behavior.

### In scope

- Use Prepared and Original consistently across the application API, state
  model, interface, and tests.
- Add the confirmed `conservative` and `smart` correction modes to the domain
  contract.
- Persist the user's default mode and allow an override for the current text.
- Make output validation mode-aware while retaining the existing conservative
  rejection of lexical additions, removals, substitutions, duplication, and
  reordering.
- Preserve Original fail-open behavior and exact Outgoing selection.
- Add an explicit database migration; normal startup must remain non-mutating.

### Exit criteria

- Conservative mode has no behavioral regression from the current cleanup
  contract.
- The default mode survives reload, and a per-text override does not overwrite
  that default.
- Hiding Original changes presentation only and never changes the selected
  mode.
- Model, route, UI, migration, and affected browser tests pass.

## Capability area: Smart correction and review

### Outcome

Deliver the primary intended-text correction loop with reviewable lexical
changes and uncertainty assistance.

### Confirmed local-proof contract

The implemented baseline uses an explicit Smart path for least-change
intended-word repairs and then applies Conservative preparation. The automatic
prototype may replace that implementation with the evidence-selected
multi-method strategy without adding a new user-visible mode. Original, optional
request-scoped task context, and approved user knowledge are untrusted evidence,
not instructions. Ambiguous wording is preserved instead of guessed, and any
provider, deadline, validation, or malformed-response failure leaves Original
usable. Smart correction never widens Conservative mode's source-preserving
lexical boundary.

The review interaction follows these rules:

- Every Smart lexical repair starts **Not reviewed**.
- **Looks right** confirms only that repair and its current result.
- Copying the result or taking no action never confirms a repair or authorizes
  learning from it.
- Every lexical addition, removal, and replacement appears in Prepared and in a
  compact repair queue with sentence context and a short inspection reason.
- The review signal makes no claim about model confidence or source audio.
- Editing or regenerating Original invalidates obsolete repairs, confirmations,
  and memory proposals.
- Prepared remains copyable before review is complete, and Outgoing remains the
  exact visible Original or Prepared selection.

Task context is bounded to one request and is never retained in durable state
or logs. The Private correction profile in the Smart MVP contains curated
preferred terms and known confusions. It is disabled by default, owned by the
local principal, inspectable, editable, deletable, and supplied only when
relevant and explicitly enabled. It is not Correction memory. A later confirmed
repair may produce a conservative memory proposal, but saving it requires a
separate explicit approval; confirmation, copying, dismissal, and ordinary
preparation save nothing.

The current prototype protocol supersedes the older fixed
prompt/context/knowledge-arm experiment. It compares correction methods and
complete automatic strategies under the gates in the
[focused specification](automatic-correction-prototype-spec.md). Private cases,
outputs, profile data, and judgments remain outside Git, GitHub, Mandrel, orbs,
application operating state, and routine logs. Provider privacy posture,
participant consent, private-data access, and any spend require verification and
explicit approval before a run.

Legacy source: Mandrel record `ec7191dc`; qualifying Sayloom evidence: explicit
`sayloom` tag. This is a provisional local-proof contract, not an ADR or a
claim about current implementation.

Additional legacy sources: Mandrel records `18411a92`, `a534b682`, `f289d8d3`,
`94f93120`, `d782f58e`, `d458148f`, `0259247a`, `35c6341e`, `42d56bd7`, and
`64d4aa31`. Qualifying Sayloom evidence is the approved explicit `sayloom` tag,
selected Sayloom completion, or approved Sayloom dependency recorded for each
source. This summary preserves only the approved current contract; private
benchmark material and superseded alternatives remain in read-only Mandrel.

### In scope

- Return Prepared text and bounded uncertainty metadata from Smart correction.
- Compute the complete word-level additions, removals, and replacements on the
  server instead of trusting a provider-supplied diff.
- Permit bounded lexical changes only in Smart mode.
- When Original is visible, identify every lexical change and add further
  emphasis to uncertain changes.
- When Original is hidden, render plain Prepared or fail-open Original using
  the available output space without inline markings.
- Invalidate stale review data when Original changes, then regenerate Prepared.
- Preserve a usable Original path for timeout, provider, validation, and
  malformed-response failures.

### Exit criteria

- Automated and browser tests cover additions, removals, replacements,
  uncertainty emphasis, stale responses, malformed metadata, CART display, and
  fail-open behavior.
- Smart correction never changes Conservative mode's lexical boundary.
- A user can edit Original and regenerate after rejecting an inferred wording.

## Capability area: Identity and tenant isolation

### Outcome

Preserve the accepted local ownership boundary and defer tenant identity until
a real multi-user, device-sync, or hosting boundary exists.

### In scope

- Use the constant durable owner ID `local` for Personal Corrections.
- Add no local account, login, owner selector, or owner-management UI.
- Select and document hosted authentication, tenant storage, sessions, and
  anonymous-rate-limit mechanisms only when hosting work begins.
- Enforce ownership in persistence queries rather than only in route handlers.
- Add explicit migration and rollback procedures.
- Keep Original and Prepared out of durable application tables.

### Exit criteria

- Local tests prove every Personal Corrections query uses `owner_id = "local"`.
- A separately approved hosted design defines cross-user acceptance evidence.
- Normal startup still checks schema state without migrating or seeding.

## Capability area: Controllable personalization

### Outcome

Add live Personal Corrections that remain private, inspectable, editable,
disableable, and deletable for one local user.

### In scope

- Save only an explicitly reviewed and approved Original → Intended mapping.
- Treat save as authorization for live use across sessions until edit,
  disablement, or deletion.
- Let users inspect, edit, disable, and delete saved Personal Corrections.
- Supply only enabled knowledge owned by `local` during Smart preparation.
- Scope UI deletion to the current state and provide a separate preview/confirm
  administration command for purging registered states only.
- Keep API keys in protected shared configuration, never in Personal
  Corrections storage or export.

### Exit criteria

- Create, inspect, edit, delete, disablement, and inference tests pass.
- Owner-scoping tests prove no non-`local` row can be returned or mutated.
- Disabling or deleting information prevents its later use.

## Capability area: Hosted offering

### Outcome

Provide the initial hosted offering defined by the product contract.

### In scope

- Run the same preparation and review core behind hosted deployment adapters.
- Design accounts and isolation when hosting creates that boundary. Any limited
  anonymous evaluation requires its own approved evaluation purpose and contract.
- Use Sayloom-managed provider credentials and disclose third-party processing
  and provider-training terms clearly.
- Keep Original and Prepared request-scoped and out of databases, logs,
  analytics, and error payloads.
- Provide copying of Prepared text.
- Exclude local Raycast targets and automated hosted target delivery from the
  hosted surface.

### Exit criteria

- Anonymous limits, authentication, account isolation, provider failure,
  copying, ephemerality, and disclosure flows pass integration and browser
  verification.
- Hosted failures leave Original available and never persist operating text.

## Capability area: Smart evaluation and release verification

**Deferred:** This capability area is historical planning context, not active
work. Renewed research requires a new approved evaluation purpose and contract.

### Outcome

Verify independently that the complete automatic implementation of Smart
improves intended-text accuracy and efficiency without hiding harmful changes
or weakening privacy and fail-open guarantees.

### In scope

- After a new evaluation contract is approved, reconcile the candidate,
  development-comparison, held-out-selection, integration, verification, and
  pilot stages rather than assuming the prior issue #46 graph remains valid.
- Treat issues #14 and #15 as superseded fixed-arm history; compatible isolated
  mechanics moved to the automatic-strategy harness and evidence path.
- Keep the provider-neutral automatic-strategy harness and its approved evidence
  independent of the retired Cleanup benchmark and archived protocols; neither
  archived Cleanup material nor any legacy observation validates Smart correction.
- Apply the frozen prototype thresholds for intended-text accuracy, harmful
  corrections, manual-edit reduction, latency, and fail-open reliability.
- Run one dedicated integration and release-verification phase after all
  constituent implementation and affected checks are resolved.
- Use the controlled verify-then-restart workflow for any later authorized
  local release; prototype verification does not authorize runtime operation.

### Exit criteria

- Frozen automatic-strategy thresholds pass on the separately approved private
  evidence, producing an evidence-selected winner for Smart integration.
- Feature-mapped verification covers the selected runtime boundary; the limited
  pilot remains a separate operational gate and is not production hosting.
- Remaining limitations and deferred scope are documented before release.

## Recommended implementation choice

Keep the two confirmed user-visible modes. Conservative remains unchanged;
automatic method selection is implemented inside Smart if the evidence selects
a qualifying strategy. Do not expose experimental methods or a separate
Automatic mode without a new approved product decision.

## Deferred scope

The following remain outside this implementation plan until separately
decided:

- correction or polishing modes beyond Conservative and Smart correction;
- hosted target delivery;
- private Original or Prepared history;
- hosted bring-your-own-key support; and
- voice or audio ingestion, storage, or verification.

## Durable constraints for every capability area

- Original remains usable whenever processing is unavailable or fails.
- The user remains authoritative about intended meaning.
- Operating text, generated text, credentials, databases, and logs never enter
  Git.
- Hosted durable data is isolated by authenticated account.
- Ordinary product use never implies model training, cross-user learning, or
  repurposing private text.
- Machine-level identifiers remain neutral and decoupled from the display
  brand.
- Normal startup never runs migrations or seed writes.
- Local changes use the controlled verify-then-restart lifecycle.
- Sayloom never interacts with predecessor runtime state.
