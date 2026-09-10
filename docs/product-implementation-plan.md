# Sayloom product implementation plan

- **Status:** Approved
- **Audience:** Product, design, engineering, research, and delivery contributors
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Evaluation and milestone authority:** [`evaluation-mvp-map.md`](evaluation-mvp-map.md)

## Purpose

This plan sequences the implementation gaps between the current local-first
application and the confirmed Sayloom product contract. It does not replace or
reinterpret `PRODUCT.md`. Each capability area has observable exit criteria;
implementation follows the issue order below and completes affected checks
before advancing.

The Current product already provides Conservative source-preserving preparation, provider
routing, editable Original text, a generated result named Prepared,
explicit Outgoing selection, fail-open behavior, prompt versions, inspectable
failures, and local Raycast delivery. Smart correction, meaning-bearing change
review, user-scoped personalization, hosted identity, managed hosted provider
access, and the hosted service remain implementation gaps.

## Sequencing

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
#14 product-bound Smart benchmark acceptance
           ▼
Smart MVP candidate
           ▼
#15 separately approved private run and pass
           ▼
Evidence-backed Smart MVP
           ▼
#13 optional memory + #16 local self-pilot
           ▼
Locally proven Smart product
           ▼
#17 Partner-demo ready
```

Issue [#9](https://github.com/dmclark/sayloom/issues/9) coordinates the Smart work. The linked
[evaluation and Smart MVP map](evaluation-mvp-map.md) defines milestone evidence and keeps cleanup
evaluation independent from Smart evaluation. The capability sections below describe scope; they do
not override this issue order. Memory and the full memory-inclusive self-pilot are outside the MVP.

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

The local proof uses an explicit Smart path for least-change intended-word
repairs and then applies Conservative preparation. Original, optional
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

The controlled local proof uses Voiceitt Chrome insertion into Original, with
paste as a labeled fallback. Its private text-only benchmark freezes cases,
prompts, context, knowledge, model settings, arm order, rubric, and gates before
execution; compares the prompt/context/knowledge arms blindly; permits no paid
retry or output selection; and treats any introduced meaning error as a hard
failure. Private cases, outputs, profile data, and judgments remain outside Git,
Mandrel, and routine logs. Provider privacy posture, participant consent, and
any new or increased spend require verification and explicit approval before a
run. Automatic latency and lexical repair spans are diagnostics; personal
review time is not measured.

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

## Capability area: Controllable personalization

### Outcome

Add later user-specific learning that remains private, inspectable, editable,
and deletable. This memory-inclusive scope belongs to issues #13 and #16 after
the Evidence-backed Smart MVP; it is not required for the MVP.

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

## Capability area: Hosted offering

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

## Capability area: Smart evaluation and release verification

### Outcome

Verify independently that Smart correction improves intended-text accuracy and
efficiency without hiding harmful changes or weakening privacy and fail-open
guarantees.

### In scope

- In issue #14, bind the generic Smart benchmark scaffold to the real Smart
  generation and Private correction profile contracts, then complete synthetic
  and product acceptance.
- In issue #15, obtain separate approval before any private corpus or provider
  operation, then run the frozen Smart benchmark and require its gates to pass.
- Keep the cleanup benchmark runner, corpus, protocol, and evidence separate;
  none validates Smart correction.
- Define release thresholds for intended-text accuracy, harmful corrections,
  manual-edit reduction, latency, and fail-open reliability before launch.
- Run one dedicated integration and release-verification phase after all
  constituent implementation and affected checks are resolved.
- Use the controlled migrate, verify, and restart workflow for local releases.

### Exit criteria

- Frozen Smart thresholds pass on the separately approved private Smart corpus,
  producing the Evidence-backed Smart MVP.
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
