# Sayloom product implementation plan

- **Status:** Approved
- **Audience:** Product, design, engineering, research, and delivery contributors
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Current implementation evidence:** Repository at `8d52b63`

## Purpose

This plan sequences the implementation gaps between the current local-first
application and the confirmed Sayloom product contract. It does not replace or
reinterpret `PRODUCT.md`. Each gate is one bounded deliverable with observable
exit criteria; implementation should complete affected checks before moving to
the next gate.

The current application already provides conservative cleanup, provider
routing, editable Original text, a generated result currently named Cleaned,
explicit Outgoing selection, fail-open behavior, prompt versions, inspectable
failures, and local Raycast delivery. Smart correction, meaning-bearing change
review, user-scoped personalization, hosted identity, managed hosted provider
access, and the hosted service remain implementation gaps.

## Sequencing

```text
Gate 1: Vocabulary and modes
              │
              ▼
Gate 2: Smart correction and review
              │
              ▼
Gate 3: Identity and tenant isolation
              │
              ▼
Gate 4: Personalization
              │
              ▼
Gate 5: Hosted MVP
              │
              ▼
Gate 6: Evaluation and release verification
```

The uncertainty contract must be decided before Gate 2 implementation. The
personalization schema, approval signal, inference method, and retention rules
must be decided before Gate 4 implementation.

## Gate 1: Prepared vocabulary and mode foundation

### Outcome

Align the existing local product with the confirmed domain model without
changing conservative correction behavior.

### In scope

- Rename current Cleaned and raw concepts to Prepared and Original across the
  application API, state model, interface, and tests.
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

## Gate 2: Smart correction and review

### Outcome

Deliver the primary intended-text correction loop with reviewable lexical
changes and uncertainty assistance.

### Decision required before implementation

Select the technical contract for reporting and presenting uncertainty. AI
confidence remains assistance rather than proof, and malformed or unverifiable
metadata must not bypass fail-open behavior.

### Provisional local-proof review contract

This contract is approved for self-pilot validation and may revise the visible
interaction before Gate 2 implementation:

- Every Smart lexical repair starts **Not reviewed**.
- **Looks right** confirms only that repair and its current result.
- Copying the result or taking no action never confirms a repair or authorizes
  learning from it.
- The review signal makes no claim about model confidence or what the source
  audio contained.
- Self-pilot findings may refine the interaction, but implicit acceptance must
  remain impossible.

Legacy source: Mandrel record `ec7191dc`; qualifying Sayloom evidence: explicit
`sayloom` tag. This is a provisional local-proof contract, not an ADR or a
claim about current implementation.

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

## Gate 3: Identity and tenant isolation

### Outcome

Establish the ownership boundary required for hosted configuration and
personalization.

### In scope

- Introduce one implicit local principal and authenticated hosted accounts.
- Scope durable user settings by principal.
- Select and document the hosted authentication, database, session, and
  anonymous-rate-limit mechanisms before implementation.
- Enforce ownership in persistence queries rather than only in route handlers.
- Add explicit migration and rollback procedures.
- Keep Original and Prepared out of durable application tables.

### Exit criteria

- Cross-user tests prove durable configuration isolation.
- Anonymous requests cannot create durable personalization.
- Normal startup still checks schema state without migrating or seeding.

## Gate 4: Controllable personalization

### Outcome

Add user-specific learning that remains private, inspectable, editable, and
deletable.

### Decision required before implementation

Confirm the initial personalization schema, what constitutes user approval,
how approved knowledge affects inference, and the retention controls. These
details remain deferred in `PRODUCT.md` and this plan does not decide them.

### In scope after that decision

- Let users enable or disable automatic personalization.
- Let users inspect, edit, and delete learned information.
- Learn only from the confirmed approval signal; ordinary processing must not
  silently retain text.
- Supply only the current principal's enabled knowledge during preparation.
- Store personalization in private local state locally and authenticated,
  account-scoped storage when hosted.

### Exit criteria

- Create, inspect, edit, delete, disablement, and inference tests pass.
- Cross-user tests demonstrate that one user's information cannot affect
  another user's correction.
- Disabling or deleting information prevents its later use.

## Gate 5: Hosted MVP

### Outcome

Provide the initial hosted offering defined by the product contract.

### In scope

- Run the same preparation and review core behind hosted deployment adapters.
- Allow limited anonymous evaluation, then require an account for continued use
  and personalization.
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

## Gate 6: Product evaluation and release verification

### Outcome

Verify that Smart correction improves intended-text accuracy and efficiency
without hiding harmful changes or weakening privacy and fail-open guarantees.

### In scope

- Extend the existing private evaluation workflow to compare Conservative and
  Smart modes.
- Define release thresholds for intended-text accuracy, harmful corrections,
  manual-edit reduction, latency, and fail-open reliability before launch.
- Run one dedicated integration and release-verification phase after all
  constituent implementation and affected checks are resolved.
- Use the controlled migrate, verify, and restart workflow for local releases.

### Exit criteria

- Confirmed release thresholds pass on the approved private evaluation corpus.
- Full feature-mapped integration evidence covers local and hosted boundaries.
- Remaining limitations and deferred scope are documented before release.

## Recommended implementation choice

Implement the two confirmed modes directly instead of shipping a temporary
combined mode. Conservative behavior already exists, so adding Smart as a
distinct mode avoids a disposable API, persistence, and interface migration.
This is the approved implementation approach.

## Deferred scope

The following remain outside this implementation plan until separately
decided:

- correction or polishing modes beyond Conservative and Smart correction;
- hosted target delivery;
- private Original or Prepared history;
- hosted bring-your-own-key support; and
- voice or audio ingestion, storage, or verification.

## Durable constraints for every gate

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
