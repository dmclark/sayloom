# Personal Corrections execution guide

- **Status:** Current execution guide
- **Active phase:** 3 — Personal Corrections
- **Initial user:** One implicit private local user
- **Last confirmed:** 2026-10-11 — complete-loop design; acceptance unverified
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
Smart repairs wording / user corrects a missed repair
        │
        ▼
Separate review from Smart repair, Prepared edit, or bound Original edit
        │
        ▼
Review selected before → intended mappings and applicability restrictions
        │
        ▼
Explicitly save selected Personal Corrections atomically
        │
        ▼
Exact trigger match supplies candidates for contextual Smart reuse / abstention
        │
        ▼
Manage corrections, inspect minimized history, and download private export
```

The state-root migration and Evidence Collection retirement are complete.
Collection UI, APIs, arming, leases, receipts, delivery gates,
participant-package implementation, administration, configuration, and
dedicated tests are absent. Historical documents remain for provenance only.
The partial Personal Corrections foundation does not make the newly confirmed
sequence complete.

The local profile foundation and bound missed-repair review are recorded
delivered. The [merged Prepared-confirmation delivery](https://github.com/dmclark/sayloom/pull/167)
adds exact confirmation and optional atomic selected-replacement saving. It
does not complete [ordered mixed mappings](https://github.com/dmclark/sayloom/issues/150)
or contextual reuse. The [complete-loop design](https://github.com/dmclark/sayloom/issues/163)
is owner-agreed in [this design session](https://ampcode.com/threads/T-01a12c59-2533-768a-810a-3458f41436b1).
Its resolution record owns document-delivery links and closure status. Neither design
agreement nor bounded delivery establishes runtime or complete-loop acceptance.

The dependable-preparation evidence gate is agreed, but actual acceptance
remains unverified. Do not advance implementation from this guide's older issue
table or prompts. Live issues own actionable state. This reconciliation selects
no build tickets, authorizes no operations, and retains Personal Corrections
before new-state inheritance. Evidence Collection must not be reintroduced.

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
- Beginning a management edit suspends reuse; cancellation retains the old
  wording disabled. Explicit re-enable of an unchanged correction restores its
  existing authorization. Management does not silently rewrite Prepared.
- Every entry remains inspectable, editable, disableable, and deletable.
- Deleting an entry also deletes its linked occurrence history from durable
  local storage and future exports.

### Capture and approval

- Ordinary editing, Copy, target delivery, and inaction save nothing and imply
  no approval.
- After Cleanup or Smart misses wording, the user edits Original and may choose
  **This is what I meant** for the exact pre-edit and post-edit revisions.
- A successful Smart repair can open a separate Personal Correction review
  without retyping. Judging it correct saves nothing.
- Correct Prepared starts only from current Prepared. Its optional save review
  compares frozen starting Prepared with confirmed wording, not unrelated
  generated changes. Original-seeded Prepared confirmation is deferred.
- Sayloom derives candidate additions, removals, and replacements. The user
  selects and may edit initially unchecked mappings to save. Additions/removals
  require explicitly reviewed short, nonempty anchored before → intended
  phrase pairs; without an anchor they remain unsaveable for reuse.
- The user explicitly reviews and approves Original → Intended before Sayloom
  can **save a Personal Correction**. The interface does not call this data
  collection.
- All three paths identify their before/after source and converge on one
  separate review. One Save selected atomically saves 1–20 selected mappings;
  saving, dismissal, and failure do not change confirmed Prepared or Outgoing.
- The save interaction visibly previews all durable private text and allows the
  user to edit or remove bounded context before approval.

### Active personal corrections

One user-visible **Personal corrections** area owns:

- approved before → intended phrase pairs for all three repair operations;
- individual changes and their reusable triggers;
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
- source and correction-version metadata, with no invented processing prompt
  for user-confirmed wording;
- timestamps; and
- content-minimized occurrence and runtime-use events.

The observed and intended sentences are first-class private discovery data.
They never include the surrounding document. Sayloom must pre-fill only the
containing sentence, display both versions before saving, and allow either to be
edited or removed.

The specification bounds each optional sentence to 500 Unicode code points.
Review permits independent editing/removal; storage enforces the limit.

### Runtime reuse

- Personal corrections initially inform Smart only. Cleanup remains
  account-independent.
- Request-time retrieval uses exact normalized trigger matching against
  Original, including approved anchored addition/removal phrases. Fuzzy and
  semantic matching remain deferred.
- Smart receives only those selected mappings and their approved applicability
  context. It does not receive historical observed or intended sentences.
- A mapping is user-owned evidence, not an unconditional replacement command.
  Smart judges applicability using the current draft, selected Writing domain,
  and approved restriction. Literal, contradictory, inappropriate, or unresolved
  ambiguous uses require abstention; correctly recognized intended wording
  remains unchanged. The red-cat/Raycast example is discussion evidence only.
- Different meanings or restrictions remain separate. Equivalent mappings may
  be deduplicated; another mapping is never overwritten or broadened silently.
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

1. an approved trigger was observed;
2. its profile entry was supplied to Smart; and
3. Prepared produced the intended repair, including anchored addition/removal.

These events do not prove that the entry caused the result or that the result
was correct. Copy and delivery never count as approval. Optional **helped** or
**wrong** feedback is a later measurement deliverable.

### Export

The first useful release includes a documented, machine-readable private export
of Personal Corrections and their content-minimized occurrence history. The
management area offers Download private export without a retained server copy.
The export supports user control and private portability; it does not authorize
research or evaluation. Its exact format is defined in the implementation
specification; adapting its replacement-oriented representation to anchored
operations and distinct restrictions remains technical design work.

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

## Earlier ticket dispositions — not live status

This table preserves the earlier planning checkpoint, not current issue status
or authority to choose the next build. In particular, its “Next” marker and
deferred model-proposed-repair path predate bounded Prepared delivery and the
agreed complete-loop design. Successful Smart-repair saving is now a target
requirement; separate outcome feedback remains deferred. Recheck live issues
before any separately authorized implementation or tracker reconciliation.

| Issue | Earlier recorded disposition |
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

The following is a capability checklist, not an executed or sufficient
complete-loop acceptance result. The owner agreed the assessment design below
in [the usefulness design session](https://ampcode.com/threads/T-01a12ca2-46cb-736b-87ab-ffa97de2c104).
[The usefulness acceptance decision](https://github.com/dmclark/sayloom/issues/164)
remains open pending reviewed, separately authorized document publication and
tracker reconciliation. Design agreement does not establish usefulness
acceptance or authorize execution.

1. Smart puts an inferred repair directly into Prepared, or the user supplies
   intended wording for a missed repair.
2. The appropriate bound entry path opens the separate correction review.
3. The user reviews Original → Intended, selects or edits the derived mapping,
   and explicitly saves a Personal Correction.
4. The mapping appears in Personal Corrections and can be edited, disabled, or
   deleted.
5. A later Original contains the approved trigger, including an anchored
   addition/removal phrase where applicable.
6. Retrieval supplies the enabled mapping to Smart.
7. Smart applies an appropriate repair directly in Prepared as a reviewable
   change, and abstains in contrasting inappropriate or ambiguous contexts.
8. The occurrence history distinguishes what was observed, supplied, and
   produced without claiming correctness or causation.
9. The private export contains the approved entry and linked content-minimized
   history, and no unrelated document text.

Formal accuracy statistics are not part of this gate.
All three repair types and management authorization boundaries are requirements;
one replacement-only demonstration does not establish complete-loop acceptance.

### Agreed single-user usefulness assessment

This is the single home of the agreed assessment design. It is bounded
single-user engineering evidence, not a pilot, statistical efficacy claim, or
resumed formal evaluation.

**Execution prerequisites — not established:** both a working complete loop and
an owner-accepted [dependable-preparation evidence gate](https://github.com/dmclark/sayloom/issues/162#issuecomment-6112233798)
are required. Gate agreement, passing repository checks, and the bounded
Prepared-confirmation/replacement-saving delivery establish neither prerequisite
and do not complete ordered mixed mappings. The
[complete-loop resolution](https://github.com/dmclark/sayloom/issues/163#issuecomment-6113213278)
remains binding. Execution requires separate authorization.

#### Paired comparisons

Compare manual preparation without automatic correction with automatic help.
Also compare Smart without saved Personal Corrections with the same candidate
using explicitly saved corrections. Keep Original, Writing domain, settings,
and candidate version equivalent within each paired comparison. Allow direct
Prepared editing wherever available. Report whole-workflow savings separately
from incremental personalization benefit; do not attribute all Smart improvement
to saved mappings.

#### Frozen scenarios and repetitions

Before later authorized execution, freeze ten owner-approved synthetic scenario
groups:

1. Replacement repair/save/reuse chain.
2. Anchored addition repair/save/reuse chain.
3. Anchored removal repair/save/reuse chain.
4. Literal-use control.
5. Contradictory-context control.
6. Unresolved ambiguity/conflicting-mappings control.
7. Already-correct wording control.
8. Longer mixed passage.
9. Rejected-repair and recovery interaction.
10. Management sequence: disable, edit/cancel, reviewed revision, explicit
    re-enable.

The three chains collectively cover successful Smart repair, Prepared edit,
and valid bound Original-edit save-review entry paths. Each includes initial
repair/save and two later drafts with different surrounding wording and the
exact normalized trigger, including cross-session reuse. Distribute short
communication with people, application/assistant instructions, and Writing
domains across the groups.

Run three paired repetitions reset to equivalent starting conditions. Retain
all attempts, including failures, rather than selecting successful runs. These
repetitions are a small engineering repeatability check, not statistical proof.

#### Observations and acceptance requirements

Record:

- purposeful repair operations, not individual keystrokes, and amount of
  wording changed in Original and Prepared separately and combined;
- regeneration rounds after initial preparation;
- time to owner-acceptable wording ready for explicit copying/delivery;
- review, saving, management, and recovery effort;
- expected versus observed repairs and abstentions; and
- owner judgments of intended meaning and whether savings are worthwhile.

Require fewer Original corrections and fewer regeneration rounds across the
correction-required set, allowing equality where the applicable baseline is
already zero. A nonzero measure must improve; neither measure may worsen to buy
improvement in the other. Combined editing burden must not increase. Moving
work into direct Prepared edits cannot manufacture improvement.

Keep setup costs visible and separately reported. Judge their payoff against
only the two later drafts actually assessed, not hypothetical future savings.
The owner must judge savings worthwhile after review/setup/recovery effort.
No percentage-savings threshold was agreed.

Every required repair/reuse and control expectation must pass independently.
Meaning violations and inappropriate reuse cannot be averaged away. Retain the
five-second preparation ceiling and additionally require owner judgment that
the whole interaction is responsive enough for people and applications.

Missing prerequisites or incomplete evidence mean **not assessable**. An unmet
requirement means **fail**. Changing a requirement needs an explicit new
decision, not an exception made during assessment. Final acceptance requires
owner review and explicit approval of the complete evidence package for the
exact candidate revision and relevant working state. Confidence in a positive
effect is an expectation, not evidence; report unexpected failures.

Use synthetic scenario identities and content-minimized observations. Trigger
observed, mapping supplied, and intended repair produced events prove neither
correctness nor causation. Keep private text, exports, and raw provider payloads
out of repository and tracker evidence. Ordinary use and saved corrections do
not authorize research reuse; discussion examples are not replacement rules.

ADR-0002's local ownership, independent states, live-database deletion scope,
and Personal-Corrections-before-inheritance sequence remain unchanged.
Managed-backup policy stays deferred, not a new prerequisite for this assessment
design; this assessment cannot establish complete durable deletion.

## Deferred tracks

The following work remains valid but inactive:

- account-independent lexical Cleanup discovery and qualification;
- automatic Smart strategy comparison and held-out selection;
- participant-package preparation and formal intended-text evaluation, unless
  a new purpose and contract are approved;
- optional standalone model-repair confirmation and outcome feedback, not the
  agreed successful Smart-repair save path;
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

### Earlier approval-only prompt — do not use as the next deliverable

This prompt predates bounded Prepared delivery and the complete-loop design.
It is retained for provenance, not implementation authority or current issue
selection. Review the agreed contract and live issues before separately
authorizing any implementation; do not execute or decompose work in this design
session.

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

### Earlier ticket-reconciliation prompt — separately authorized work only

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
committed, pushed, merged, deployed, or running.
