# Personal Corrections execution guide

- **Status:** Current execution guide
- **Active phase:** 3 — Personal Corrections
- **Initial user:** One implicit private local user
- **Last confirmed:** 2026-10-02
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Architecture decision:** [ADR-0002](adr/0002-personal-corrections-ownership-and-state-portability.md)
- **Domain vocabulary:** [`GLOSSARY.md`](../GLOSSARY.md)

## Purpose

This guide is the single place to answer:

1. What correction work is active now?
2. What must be delivered next?
3. What proves that delivery is complete?
4. Which prompt should start the next focused piece of work?

The active goal is to deliver live Personal Corrections for one local user in
the confirmed order: state-root migration, Evidence Collection retirement,
Personal Corrections, then new-state inheritance. Hosted accounts, multi-user
operation, device sync, research, pilots, and broad efficacy claims do not
block this goal.

`PRODUCT.md` remains product authority. This guide controls current execution
order. Formal evaluation is deferred. Renewing it requires a new approved
evaluation purpose and contract; an older research document or open issue does
not authorize resumption.

## Live implementation surface

Use this map to enter the running product without treating product history as
runtime ownership. It is a navigation aid, not a second specification; follow
the linked current contract for behavior and acceptance criteria.

| Boundary | Live owner paths | Current responsibility |
| --- | --- | --- |
| Schema and migrations | [`migrations/env.py`](../migrations/env.py), [`migrations/versions/`](../migrations/versions/), [`src/local_text/models.py`](../src/local_text/models.py), [`src/local_text/database.py`](../src/local_text/database.py) | Alembic revision chain and SQLAlchemy table definitions; `ApplicationDatabase` reports schema readiness and never migrates during normal startup. Personal Corrections are introduced by [`0004_personal_corrections_foundation.py`](../migrations/versions/0004_personal_corrections_foundation.py) and [`0005_personal_correction_approval.py`](../migrations/versions/0005_personal_correction_approval.py). |
| Persistence and domain logic | [`src/local_text/personal_corrections.py`](../src/local_text/personal_corrections.py), [`src/local_text/prompt_store.py`](../src/local_text/prompt_store.py), [`src/local_text/cleanup.py`](../src/local_text/cleanup.py), [`src/local_text/prompts.py`](../src/local_text/prompts.py), [`src/local_text/state.py`](../src/local_text/state.py), [`src/local_text/target_store.py`](../src/local_text/target_store.py), and [`src/local_text/target_adapter.py`](../src/local_text/target_adapter.py) | Transactional stores and typed domain contracts for the local Personal Corrections profile and approval episode, prompt/default state, cleanup and Smart processing, outgoing state, and target lifecycle. |
| API and application composition | [`src/local_text/app.py`](../src/local_text/app.py) | FastAPI application, lifespan and provider wiring, privacy-safe API errors, static-file mount, and HTTP routes. Personal Corrections routes select the implicit `local` owner in the application/store boundary; callers do not submit profile rows or an owner. |
| Browser UI | [`src/local_text/static/index.html`](../src/local_text/static/index.html), [`src/local_text/static/app.js`](../src/local_text/static/app.js), and [`src/local_text/static/app.css`](../src/local_text/static/app.css) | Workspace and Settings markup, client-side draft/review invalidation and API calls, Personal Corrections controls, and responsive presentation. |
| Configuration and operations | [`src/local_text/config.py`](../src/local_text/config.py), [`src/local_text/admin.py`](../src/local_text/admin.py), [`scripts/dev.py`](../scripts/dev.py), [`scripts/development_state.py`](../scripts/development_state.py), [`scripts/run-development.py`](../scripts/run-development.py), [`launchd/local.local-text.development.plist.template`](../launchd/local.local-text.development.plist.template), and [`raycast/`](../raycast/) | Profile and environment validation, explicit schema/seed administration, checkout-scoped development-state lifecycle and controlled restart, launchd service template, and generated local Raycast delivery commands. Normal application startup does not migrate or seed. |
| Focused tests | [`tests/test_personal_corrections.py`](../tests/test_personal_corrections.py), [`tests/test_personal_correction_approval.py`](../tests/test_personal_correction_approval.py), [`tests/test_app.py`](../tests/test_app.py), [`tests/test_preparation_default_migration.py`](../tests/test_preparation_default_migration.py), and [`tests/conftest.py`](../tests/conftest.py) | Synthetic coverage for Personal Corrections schema, store, API, approval transaction, stale-state and browser behavior; broader API and migration regression coverage; and isolated database fixtures. |

### Historical and provenance boundary

The paths above are live runtime or focused-test surfaces. They are distinct
from [`docs/archive/`](archive/), which preserves superseded plans, benchmark
protocols, and research records, and from the retained
[Evidence Collection contract](intended-meaning-evidence-collection-contract.md).
Those documents—and relevant Git history—must be preserved when a task needs
provenance, but must not be read as active functionality or authority to restore
Evidence Collection, participant packages, collection, or evaluation. Consult
the [documentation map](README.md) for each document's lifecycle; retain
historical references rather than deleting or implementing them unless a new
approved current contract explicitly changes that boundary.

## Current position

Sayloom can generate Smart Prepared text, show its server-derived repair queue,
and manage a partial local Personal Corrections foundation. It cannot yet
complete the confirmed Personal Corrections flywheel or state-portability
contract:

```text
Smart misses wording
        │
        ▼
User edits Original
        │
        ▼
Review Original → Intended
        │
        ▼
Save a Personal Correction
        │
        ▼
Personal correction informs a later Smart request
        │
        ▼
Inspect recurrence and export private discovery data
```

The state-root migration and Evidence Collection retirement are complete.
Collection UI, APIs, arming, leases, receipts, delivery gates,
participant-package implementation, administration, configuration, and
dedicated tests are absent. Historical documents remain for provenance only.
The partial Personal Corrections foundation does not make the newly confirmed
sequence complete.

The local profile foundation and bound missed-repair review are complete. The
immediate next deliverable is [#13](https://github.com/dmclark/sayloom/issues/13):
explicit approval and durable save of the reviewed Personal Correction episode.
Evidence Collection must not be reintroduced as part of that work.

## Current contract

### Ownership and activation

- The constant durable owner ID `local` owns all Personal Corrections data.
- There is no account, login, owner selector, or owner-management UI.
- Accounts are deferred until multi-user, device-sync, or hosting boundaries
  create a real isolation requirement.
- A newly reviewed and saved entry is enabled by default.
- Saving authorizes that correction across later sessions until it is edited,
  disabled, or deleted.
- Editing ends the prior mapping's authorization. The edited Original →
  Intended mapping requires review and explicit save before reuse.
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
- The user explicitly reviews and approves Original → Intended before Sayloom
  can **save a Personal Correction**. The interface does not call this data
  collection.
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

### State portability and deletion

- Development states use independent Personal Corrections snapshots rather
  than one shared live database.
- A future new state inherits one verified transactional snapshot from the
  eligible source explicitly activated for creation.
- If that source exists and inheritance fails, initialization fails before
  activation. If no source exists, initialization reports an empty profile.
- Creation does not backfill existing states or start automatic synchronization;
  parallel states may diverge.
- UI deletion affects only the current state. A separate administration command
  may purge registered states only after preview and confirmation.
- Both deletion paths cover live databases only. Managed SQLite backup handling
  remains unresolved, and user-created exports are not removed. Complete
  durable deletion cannot be claimed until the backup policy is confirmed and
  verified.
- API keys remain in protected shared configuration and never enter a Personal
  Corrections database, snapshot, or export. Keychain is deferred.

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
of Personal Corrections and their content-minimized occurrence history. The
export supports user control and private portability; it does not authorize
research or evaluation. Its exact format is defined in the implementation
specification.

Saved corrections and episodes are live product state. They must never be
presented as evaluation evidence unless a new approved purpose and contract
explicitly qualifies them.

## Delivery map

Only one phase is active at a time. Advance the marker after the phase's exit
gate is met and its evidence is recorded in this guide or its linked issue.

| Phase | Status | Deliverable | Exit gate |
| ---: | --- | --- | --- |
| 1 | Complete | Development-state root migration | An explicit, verified migration moves registered state data to `${XDG_DATA_HOME:-~/.local/share}/local-text/dev-states/`; normal startup never migrates. |
| 2a | Complete | Evidence Collection Workspace/runtime retirement | UI, APIs, session behavior, arming, leases, receipts, delivery gates, runtime exposure, and dedicated runtime tests are removed while ordinary preparation, Copy, and delivery remain. |
| 2b | Complete | Participant-package retirement | Issue #143 removed package creation, validation, administration, configuration, and dedicated package tests while preserving historical docs and Git. |
| 3 | **Active** | Personal Corrections | Explicit Original → Intended review and approval, durable `local` ownership, cross-session Smart reuse, management, current-state deletion, registered-state purge, and private export work end to end. Complete durable-deletion acceptance additionally requires a confirmed managed-backup policy. |
| 4 | Blocked by phase 3 | New-state inheritance | A new state inherits and verifies a transactional snapshot from the explicitly activated eligible source; failures prevent activation, no-source creation reports empty, and existing states remain untouched. |

### Existing partial implementation evidence

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
- [#109](https://github.com/dmclark/sayloom/issues/109) binds one frozen
  pre-edit Original to its latest settled post-edit revision, derives ordered
  lexical candidates and bounded editable sentence evidence, invalidates stale
  reviews, and writes nothing. Focused API and browser checks cover asymmetric
  additions, removals, replacements, prompt-version changes, desktop and narrow
  layouts, and the 500-code-point review boundary.

This evidence describes current partial implementation only. It does not
satisfy phase 3 or justify skipping phases 1 and 2.

## Ticket status

This table records the active flywheel's current issue disposition.

| Issue | Current disposition |
| --- | --- |
| [#131](https://github.com/dmclark/sayloom/issues/131) | **In progress:** phase 3 umbrella; close only after the first usefulness demonstration. |
| [#109](https://github.com/dmclark/sayloom/issues/109) | **Complete:** bound missed-repair review and bounded observed/intended sentence evidence are delivered without approval writes. |
| [#12](https://github.com/dmclark/sayloom/issues/12) | **Complete:** durable owner `local`, Personal Corrections management, and the runtime profile boundary are delivered. |
| [#13](https://github.com/dmclark/sayloom/issues/13) | **Next:** explicitly approve and atomically save selected user-supplied mappings as one bounded Personal Correction episode. |
| [#45](https://github.com/dmclark/sayloom/issues/45) | Retain as later positive confirmation of model-proposed repairs. It does not block the personal flywheel. |
| [#9](https://github.com/dmclark/sayloom/issues/9) | Keep as broader Smart and personalization history; do not use its superseded fixed-arm sequence as the current path. |
| [#46](https://github.com/dmclark/sayloom/issues/46) | Keep open but defer the automatic-strategy evaluation path until a later explicit decision. |
| [#60](https://github.com/dmclark/sayloom/issues/60), [#112](https://github.com/dmclark/sayloom/issues/112), [#116](https://github.com/dmclark/sayloom/issues/116), [#117](https://github.com/dmclark/sayloom/issues/117) and their downstream evaluation work | Preserve but defer. Participant-package preparation, Cleanup qualification, and broad evaluation do not block single-user usefulness. |

## First usefulness gate

The personal flywheel is useful when all of the following are demonstrated in
the private local application:

1. Smart misses a real intended term.
2. The user edits Original and starts the correction review.
3. The user reviews Original → Intended, selects or edits the derived mapping,
   and explicitly saves a Personal Correction.
4. The mapping appears in Personal Corrections and can be edited, disabled, or
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
- participant-package preparation and formal intended-text evaluation, unless
  a new purpose and contract are approved;
- optional model-proposed repair confirmation and outcome feedback;
- hosted identity, cross-user isolation, and hosted persistence;
- pilots, partner demonstrations, and broad efficacy claims; and
- multi-user personalization or learning.

Resume one of these tracks only through a new explicit decision that updates
the active phase in this guide. Do not infer resumption from an existing open
issue.

## Risks and controls

| Risk | Required control |
| --- | --- |
| An exact alias is ambiguous | Treat mappings as evidence, allow Smart to abstain, and keep changes reviewable. |
| Exact retrieval misses variants | Record the miss; broaden normalization only from observed need. |
| Durable context contains sensitive text | Preview it, bound it, permit editing/removal, keep it local, and cascade deletion. |
| Usage events are mistaken for efficacy | Name only the observed event; never infer correctness or causation. |
| Saved corrections are repurposed for evaluation | Require a new approved evaluation purpose and contract; ordinary product authorization is insufficient. |
| Existing roadmaps distract from the active goal | Treat this guide as current execution authority and mark other tracks deferred. |
| Implementation silently widens scope | Stop at the current phase's exit gate; open a focused decision for any new behavior. |

## Copy-ready prompts

### Use now: implement explicit approval and save

```text
Use docs/personal-corrections-execution-guide.md and ADR-0002 as the confirmed
execution authority. Implement only #13: explicit approval and atomic durable
save of selected mappings from the bound #109 review as one Personal Correction
episode. Preserve #109's stale-state and no-write boundaries, the completed
development-state migration, and Evidence Collection retirement. Do not add
Smart retrieval, deletion/export, new-state inheritance, or evaluation behavior
in the same change. Follow the confirmed implementation specification and #13's
acceptance criteria.
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

### After each phase is authorized: implement the next phase

```text
Implement only the first ready phase in
docs/personal-corrections-execution-guide.md from its confirmed specification
and reconciled GitHub ticket. Work test-first on the risky persistence,
ownership, deletion, and stale-state boundaries. Keep all operating data and
private text outside Git, preserve one implicit local principal, perform schema
changes only through an explicit migration, and do not run migrations at normal
startup. Verify the affected automated and representative browser states, then
update the execution guide's phase marker and evidence only if the exit gate is
actually met. Do not begin the next phase in the same thread.
```

### Deferred: review formulaic readiness

```text
Do not run this work without a newly approved evaluation purpose and contract.
After that approval, review the private Personal Corrections flywheel for
formulaic-rule readiness using only content-free aggregate recurrence and
category summaries unless I separately authorize private-content access.
Determine whether repeated patterns justify one focused research question or
whether more ordinary use is needed.
Do not treat reactive correction episodes as held-out evaluation evidence, do
not weaken Cleanup's account-independent boundary, and do not start provider
calls, spending, formal evaluation, or implementation. Return the evidence for
the recommendation and a copy-ready prompt for the single next research task.
```

## Updating this guide

When a phase completes:

1. record its linked issue or specification and decisive verification evidence;
2. change that row to **Complete**;
3. mark exactly one unblocked row **Active**;
4. update **Active phase** and **Last confirmed** at the top; and
5. revise the copy-ready current prompt if the next deliverable changed.

Do not mark a phase complete from planning, mocked UI alone, or an unverified
implementation. Local edits and passing checks also do not imply that work is
committed, pushed, merged, deployed, or operating in the stable application.
