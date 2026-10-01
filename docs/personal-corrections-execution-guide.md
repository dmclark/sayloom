# Personal corrections execution guide

- **Status:** Current execution guide
- **Active stage:** 3 — Missed-repair capture and explicit save
- **Initial user:** One implicit private local user
- **Last confirmed:** 2026-09-30
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Domain vocabulary:** [`CONTEXT.md`](../CONTEXT.md)

## Purpose

This guide is the single place to answer:

1. What correction work is active now?
2. What must be delivered next?
3. What proves that delivery is complete?
4. Which prompt should start the next focused piece of work?

The active goal is to improve one private user's correction accuracy and speed
now while collecting structured, private data that can support formulaic work
later. Hosted accounts, multi-user operation, pilots, and broad efficacy claims
do not block this goal.

`PRODUCT.md` remains product authority. This guide controls current execution
order. The formal Cleanup and Smart evaluation documents retain their contracts
but do not determine the next deliverable while that work is deferred.

## Current position

Sayloom can generate Smart Prepared text, show its server-derived repair queue,
and manage the explicitly enabled local Personal corrections foundation. It
cannot yet capture a missed repair or complete the personal correction flywheel:

```text
Smart misses wording
        │
        ▼
User edits Original
        │
        ▼
"This is what I meant"
        │
        ▼
Review and save selected mapping
        │
        ▼
Personal correction informs a later Smart request
        │
        ▼
Inspect recurrence and export private discovery data
```

The immediate next deliverable is stage 3 missed-repair capture and explicit
save. Stage 2 did not begin capture, episodes, Smart retrieval, events, export,
or hard deletion.

## Current contract

### Ownership and activation

- One implicit local principal owns all Personal corrections data.
- Hosted authentication is deferred until hosting or a second user creates a
  real isolation requirement.
- The user explicitly enables Personal corrections once.
- A newly reviewed and saved entry is enabled by default.
- Every entry remains inspectable, editable, disableable, and deletable.
- Deleting an entry also deletes its linked occurrence history from durable
  local storage and future exports.

### Capture and approval

- Ordinary editing, Copy, target delivery, and inaction save nothing and imply
  no approval.
- After Cleanup or Smart misses wording, the user edits Original and may choose
  **This is what I meant** for the exact pre-edit and post-edit revisions.
- Sayloom derives candidate additions, removals, and replacements. The user
  selects and may edit the mappings to save.
- Multiple selected mappings may belong to one correction episode.
- The save interaction visibly previews all durable private text and allows the
  user to edit or remove bounded context before approval.

### Active personal corrections

One user-visible **Personal corrections** area owns:

- an intended canonical term;
- one or more misheard aliases;
- optional, approved applicability context;
- enabled state; and
- linked occurrence history.

Internally, curated entries form the Private correction profile. Explicit save
and linked occurrence history implement Correction memory. The product need not
expose those two internal names as separate management areas.

### Correction episodes

Each explicitly saved episode may retain:

- the bounded pre-edit observed sentence;
- the bounded post-edit intended sentence;
- the user-selected derived mappings;
- mode and correction-version metadata;
- timestamps; and
- content-minimized occurrence and runtime-use events.

The observed and intended sentences are first-class private discovery data.
They never include the surrounding document. Sayloom must pre-fill only the
containing sentence, display both versions before saving, and allow either to be
edited or removed.

The exact sentence-length limit is **Deferred** until the implementation
specification. It must be short, explicit, and enforced at the storage boundary.

### Runtime reuse

- Personal corrections initially inform Smart only. Cleanup remains
  account-independent.
- Request-time retrieval deterministically selects enabled entries whose alias
  occurs in Original.
- Smart receives only those selected mappings and their approved applicability
  context. It does not receive historical observed or intended sentences.
- A mapping is user-owned evidence, not an unconditional replacement command.
  Smart may apply it when context fits and abstain when wording is ambiguous.
- Every resulting lexical change remains reviewable through the existing Smart
  repair contract.

Exact alias normalization beyond the initial bounded match is **Deferred**.
Broaden retrieval only in response to observed misses.

### Occurrence history and claims

Equivalent repeated corrections update recurrence information rather than
creating duplicate profile entries. Content-minimized history distinguishes:

1. an alias was observed;
2. its profile entry was supplied to Smart; and
3. Prepared contained the intended replacement.

These events do not prove that the entry caused the result or that the result
was correct. Copy and delivery never count as approval. Optional **helped** or
**wrong** feedback is a later measurement deliverable.

### Export

The first useful release includes a documented, machine-readable private export
of Personal corrections and their content-minimized occurrence history. The
export may support private recurrence analysis and future formulaic-rule
research. Its exact file format and versioned schema are **Deferred** until the
implementation specification.

Reactive correction episodes are development and discovery evidence because
they are supplied after a correction result was visible. They must never be
presented as unbiased held-out evaluation evidence.

## Delivery map

Only one stage is active at a time. Advance the marker after the stage's exit
gate is met and its evidence is recorded in this guide or its linked issue.

| Stage | Status | Deliverable | Exit gate |
| ---: | --- | --- | --- |
| 1 | **Complete** | Focused implementation specification and exact ticket-reconciliation plan | Storage boundaries, interactions, failure behavior, migrations, export contract, and tracer-bullet tickets are executable without inventing product decisions. |
| 2 | **Complete** | Local Personal corrections foundation | The implicit local principal can explicitly enable the feature and create, inspect, revision-check edit, and globally or individually disable canonical terms and aliases. Startup performs no migration or seed write. Hard deletion remains in the later deletion/history/export stage under the reconciled issue boundary. |
| 3 | **Active** | Missed-repair capture and explicit save | A bound pre/post edit produces reviewable candidates and bounded observed/intended sentences; only selected mappings and approved context persist. |
| 4 | Blocked by stage 3 | Smart retrieval and reuse | Only deterministically relevant enabled entries reach Smart; ambiguity may abstain; stale and failure paths remain fail-open and content-free. |
| 5 | Blocked by stage 4 | History, management, and private export | Recurrence and runtime-use events remain claim-safe; edit, disable, deletion, and a versioned export work end to end. |
| 6 | Blocked by stage 5 | Personal usefulness demonstration | One real mapping is saved, encountered again, used to produce the intended Smart correction, and visible in local recurrence history. |
| 7 | Later | Optional outcome feedback | The user can mark an applied correction helped or wrong without Copy, delivery, or inaction becoming implicit feedback. |
| 8 | Recurring after stage 6 | Content-free readiness review | Aggregate recurrence and category patterns justify a focused formulaic-rule research question, or the review records that more ordinary use is needed. |

### Stage 2 completion evidence

- Reconciled issue: [#12](https://github.com/dmclark/sayloom/issues/12).
- Alembic revision `0004_personal_corrections_foundation` creates the empty
  owner-scoped profile, entry, and alias foundation without a profile row or
  seed write; synthetic tests cover predecessor preservation, storage checks,
  foreign-key ownership, downgrade, and re-upgrade.
- Store and API tests cover explicit first enablement, local-owner filtering,
  normalized uniqueness, ambiguous alias disclosure, create/read/edit,
  global and per-entry disablement, and stale revision conflicts.
- Isolated synthetic browser checks cover disabled/empty and populated states,
  ambiguity, edit and disable behavior, and representative desktop and narrow
  layouts. Normal startup against the predecessor schema remains non-mutating
  and reports `setup_required`.

## Ticket reconciliation plan

This table records intended disposition, not completed GitHub mutation. Creating
or editing issues requires a separately authorized tracker operation.

| Issue | Intended disposition |
| --- | --- |
| New Personal correction flywheel umbrella | **Proposed:** create it to own stages 1–8 and their blocking edges. |
| [#109](https://github.com/dmclark/sayloom/issues/109) | Revise around missed-repair capture and bounded observed/intended correction episodes. Remove #45 as a blocker. |
| [#12](https://github.com/dmclark/sayloom/issues/12) | Revise around the implicit local principal, Personal corrections management, one-time enablement, and runtime profile boundary. |
| [#13](https://github.com/dmclark/sayloom/issues/13) | Revise or split around explicit save, deduplication, occurrence history, deletion, and export. It must accept user-supplied missed repairs rather than require model-proposed confirmation. |
| [#45](https://github.com/dmclark/sayloom/issues/45) | Retain as later positive confirmation of model-proposed repairs. It does not block the personal flywheel. |
| [#9](https://github.com/dmclark/sayloom/issues/9) | Keep as broader Smart and personalization history; do not use its superseded fixed-arm sequence as the current path. |
| [#46](https://github.com/dmclark/sayloom/issues/46) | Keep open but defer the automatic-strategy evaluation path until a later explicit decision. |
| [#60](https://github.com/dmclark/sayloom/issues/60), [#112](https://github.com/dmclark/sayloom/issues/112), [#116](https://github.com/dmclark/sayloom/issues/116), [#117](https://github.com/dmclark/sayloom/issues/117) and their downstream evaluation work | Preserve but defer. Participant-package preparation, Cleanup qualification, and broad evaluation do not block single-user usefulness. |

## First usefulness gate

The personal flywheel is useful when all of the following are demonstrated in
the private local application:

1. Smart misses a real intended term.
2. The user edits Original and explicitly starts **This is what I meant**.
3. The user reviews the bounded observed and intended sentences, selects or
   edits the derived mapping, and saves it.
4. The mapping appears in Personal corrections and can be edited, disabled, or
   deleted.
5. A later Original contains the alias.
6. Retrieval supplies the enabled mapping to Smart.
7. Prepared contains the intended correction as a reviewable lexical change.
8. The occurrence history distinguishes what was observed, supplied, and
   produced without claiming correctness or causation.
9. The private export contains the approved entry and linked content-minimized
   history, and no unrelated document text.

Formal accuracy statistics are not part of this gate.

## Deferred tracks

The following work remains valid but inactive:

- account-independent lexical Cleanup discovery and qualification;
- automatic Smart strategy comparison and held-out selection;
- participant-package preparation and formal intended-text evaluation;
- optional model-proposed repair confirmation and outcome feedback;
- hosted identity, cross-user isolation, and hosted persistence;
- pilots, partner demonstrations, and broad efficacy claims; and
- multi-user personalization or learning.

Resume one of these tracks only through a new explicit decision that updates
the active stage in this guide. Do not infer resumption from an existing open
issue.

## Risks and controls

| Risk | Required control |
| --- | --- |
| An exact alias is ambiguous | Treat mappings as evidence, allow Smart to abstain, and keep changes reviewable. |
| Exact retrieval misses variants | Record the miss; broaden normalization only from observed need. |
| Durable context contains sensitive text | Preview it, bound it, permit editing/removal, keep it local, and cascade deletion. |
| Usage events are mistaken for efficacy | Name only the observed event; never infer correctness or causation. |
| Reactive episodes leak into held-out evaluation | Label them discovery evidence and maintain a separate prospective held-out path. |
| Existing roadmaps distract from the active goal | Treat this guide as current execution authority and mark other tracks deferred. |
| Implementation silently widens scope | Stop at the current stage's exit gate; open a focused decision for any new behavior. |

## Copy-ready prompts

### Use now: specify stage 1

```text
Use docs/personal-corrections-execution-guide.md as the confirmed current
execution authority and PRODUCT.md as product authority. Produce the focused
implementation specification for stage 1 of the private, single-user Personal
corrections flywheel. Inspect the current code and existing issues #12, #13,
#45, and #109 before proposing boundaries. Specify the smallest executable data
model, explicit migration and rollback, capture and approval state machine,
bounded observed/intended sentence handling, deterministic alias retrieval,
failure and stale-state behavior, deletion semantics, occurrence events,
versioned private export, privacy invariants, and acceptance checks. Preserve
Cleanup's account independence and normal startup's no-migration rule. Mark
unresolved implementation choices rather than silently deciding product
behavior. End with an exact ticket-reconciliation proposal, but do not mutate
GitHub or implement code without separate authorization.
```

### After the specification is confirmed: reconcile tickets

```text
Using the confirmed Personal corrections implementation specification and
docs/personal-corrections-execution-guide.md, reconcile the GitHub work for the
active flywheel. Propose one focused umbrella and tracer-bullet children with
blocking edges. Preserve useful history in #12, #13, #45, and #109; remove #45
as a blocker for missed-repair capture; keep #45 as later positive-feedback
work; and mark #46 plus Cleanup/evaluation work as deferred rather than closed.
Show the exact proposed issue mutations and ask for approval before changing
GitHub.
```

### After tickets are authorized: implement the next stage

```text
Implement only the first ready stage in
docs/personal-corrections-execution-guide.md from its confirmed specification
and reconciled GitHub ticket. Work test-first on the risky persistence,
ownership, deletion, and stale-state boundaries. Keep all operating data and
private text outside Git, preserve one implicit local principal, perform schema
changes only through an explicit migration, and do not run migrations at normal
startup. Verify the affected automated and representative browser states, then
update the execution guide's stage marker and evidence only if the exit gate is
actually met. Do not begin the next stage in the same thread.
```

### After the first usefulness gate: review formulaic readiness

```text
Review the private Personal corrections flywheel for formulaic-rule readiness
using only content-free aggregate recurrence and category summaries unless I
separately authorize private-content access. Determine whether repeated patterns
justify one focused research question or whether more ordinary use is needed.
Do not treat reactive correction episodes as held-out evaluation evidence, do
not weaken Cleanup's account-independent boundary, and do not start provider
calls, spending, formal evaluation, or implementation. Return the evidence for
the recommendation and a copy-ready prompt for the single next research task.
```

## Updating this guide

When a stage completes:

1. record its linked issue or specification and decisive verification evidence;
2. change that row to **Complete**;
3. mark exactly one unblocked row **Active**;
4. update **Active stage** and **Last confirmed** at the top; and
5. revise the copy-ready current prompt if the next deliverable changed.

Do not mark a stage complete from planning, mocked UI alone, or an unverified
implementation. Local edits and passing checks also do not imply that work is
committed, pushed, merged, deployed, or operating in the stable application.
