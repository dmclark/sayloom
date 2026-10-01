# Personal Corrections implementation specification

- **Status:** Confirmed target contract; implementation pending
- **Scope:** Private, single-user Personal Corrections flywheel
- **Execution authority:** [Personal corrections execution guide](personal-corrections-execution-guide.md)
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Architecture decision:** [ADR-0002](adr/0002-personal-corrections-ownership-and-state-portability.md)
- **Domain vocabulary:** [`CONTEXT.md`](../CONTEXT.md)
- **Confirmed:** 2026-10-01

## Purpose

This specification defines the Personal Corrections phase of the ordered work
in the execution guide. It defines the smallest durable model, review and
approval lifecycle, Smart-only retrieval boundary, occurrence history,
state-local deletion, private export, migration, and acceptance evidence needed
for the first usefulness gate.

This document does not authorize implementation, migration, private-data
access, provider traffic, GitHub mutation, or operation of the stable
application. Evidence Collection and current Application Support state paths
still exist until the preceding retirement and state-root migration phases are
separately implemented and verified.

## Confirmed outcome and non-goals

The first release serves one implicit private local principal with durable
`owner_id = "local"`. It adds no account, login, owner selector, or owner UI.
The user can:

1. turn a missed Cleanup or Smart repair into a reviewed correction episode;
2. explicitly review and approve an Original → Intended mapping;
3. save a Personal Correction for live use in later sessions;
4. inspect, edit, disable, or delete a Personal correction;
5. have matching enabled aliases supplied only to a later Smart request;
6. inspect content-minimized recurrence events; and
7. export the current private state in a versioned machine-readable format.

The release does not add hosted identity, multiple users, device sync, model
training, cross-user learning, automatic approval, outcome claims, `helped` or
`wrong` feedback, formulaic Cleanup rules, or evaluation evidence. Accounts
remain deferred until multi-user, device-sync, or hosting boundaries exist.
Any renewed research requires a new approved evaluation purpose and contract.

Core Cleanup remains account-independent. No Personal correction setting,
entry, alias, episode, event, lookup, failure, or export may change Cleanup's
eligibility, prompt, request, result validation, or fallback behavior.

## Current implementation seams

The implementation must extend, rather than bypass, these current boundaries:

- `ApplicationDatabase` and Alembic own the SQLite schema. Startup compares the
  database revision with `SCHEMA_REVISION`; it does not migrate or seed.
- Stores use short SQLAlchemy transactions and the database enables SQLite
  foreign keys on every connection.
- `/api/cleanup` resolves the active prompt and delegates to `CleanupService`.
  `CleanupService` already accepts request-scoped Smart context and curated
  knowledge, while Conservative requests reject either form of evidence.
- Smart evidence is framed as untrusted JSON for the provider. Personal
  corrections must become typed server-selected evidence within that frame;
  historical sentences must not enter it.
- The browser's `draftRevision`, request sequence, abort controller, exact
  Original, mode, and task-context comparisons reject stale processing results.
  Missed-repair state must use the same invalidation boundary.
- Existing lexical review uses ordered additions, removals, and replacements
  with validated spans. Candidate derivation should share that vocabulary and
  implementation rather than introduce a second diff contract.

Ordinary `/api/cleanup` callers must not submit profile rows or select an owner.
The application route owns local-principal selection and retrieval before it
constructs the internal Smart request. Evidence Collection is superseded and
must be retired before this phase; it is not a Personal Corrections write path.

## Terms used here

- **Local principal:** The constant internal owner key `local`. It is not a
  hosted account or display name.
- **Profile:** The local principal's persisted Personal Corrections enablement
  state and entries.
- **Entry:** One intended canonical term, optional approved applicability
  context, enabled state, and one or more observed aliases.
- **Episode:** One explicit approval containing selected before/after mappings
  and optional bounded observed and intended sentences.
- **Use ID:** A random UUID identifying one capture approval or one Smart
  request for idempotent event recording. It contains no text.

## Durable model

All content lives in the existing private application SQLite database. IDs are
random UUID strings. Timestamps are UTC. Every content-bearing table carries
`owner_id`, and every store query includes `owner_id = "local"`; route-only
filtering is insufficient.

### `personal_correction_profiles`

| Column | Contract |
| --- | --- |
| `owner_id` | Primary key; `CHECK (owner_id = 'local')`. |
| `enabled` | Required boolean. |
| `created_at`, `updated_at` | Required UTC timestamps. |

No row means no saved Personal Corrections and therefore disabled. The first
approved save creates the profile row and an enabled entry in the same
transaction. Later global disablement changes `enabled` but does not alter
individual entries. The migration creates no profile row or other seed data.

### `personal_correction_entries`

| Column | Contract |
| --- | --- |
| `id` | UUID primary key. |
| `owner_id` | Required foreign key to the profile, with delete cascade. |
| `intended_term` | User-visible canonical term; 1–200 Unicode code points. |
| `intended_key` | Server-derived normalization key. |
| `applicability_context` | Nullable approved context; at most 500 Unicode code points. |
| `enabled` | Required boolean; newly approved entries are enabled. |
| `revision` | Positive integer for optimistic concurrency. |
| `created_at`, `updated_at` | Required UTC timestamps. |

`(owner_id, intended_key)` is unique. `(id, owner_id)` is also unique so child
foreign keys can enforce ownership. Empty context is stored as `NULL`.

### `personal_correction_aliases`

| Column | Contract |
| --- | --- |
| `id` | UUID primary key. |
| `owner_id`, `entry_id` | Composite foreign key to the owned entry, with delete cascade. |
| `observed_alias` | User-visible alias; 1–200 Unicode code points. |
| `alias_key` | Server-derived normalization key. |
| `created_at`, `updated_at` | Required UTC timestamps. |

`(owner_id, entry_id, alias_key)` is unique. The same normalized alias may
belong to multiple intended terms because an observed form can be ambiguous;
deterministic retrieval supplies all matching candidates and Smart may abstain.
The management UI must disclose such ambiguity rather than silently replacing
one entry.

### `personal_correction_episodes`

| Column | Contract |
| --- | --- |
| `id` | UUID primary key. |
| `owner_id` | Required owned-profile foreign key, with delete cascade. |
| `approval_id` | Client-generated UUID, unique per owner for retry idempotency. |
| `observed_sentence` | Nullable approved pre-edit sentence; at most 500 Unicode code points. |
| `intended_sentence` | Nullable approved post-edit sentence; at most 500 Unicode code points. |
| `source_mode` | `conservative` or `smart`. |
| `prompt_version_id` | The prompt version used by the bound missed result. |
| `correction_contract_version` | Fixed value `personal-correction-v1`. |
| `created_at` | Required UTC timestamp. |

Either or both sentence fields may be removed before approval. The surrounding
Original, Prepared, Outgoing, task context, provider payload, and model output
are never stored in these tables.

### `personal_correction_episode_mappings`

| Column | Contract |
| --- | --- |
| `id` | UUID primary key. |
| `owner_id`, `episode_id` | Composite owned-episode foreign key, with delete cascade. |
| `ordinal` | One-based display order, unique within the episode. |
| `operation` | `addition`, `removal`, or `replacement`. |
| `observed_text` | Nullable selected before text; at most 200 code points. |
| `intended_text` | Nullable selected after text; at most 200 code points. |
| `entry_id`, `alias_id` | Nullable owned profile references for a reusable replacement. |

The save boundary accepts 1–20 selected mappings. A replacement has non-empty
observed and intended text and links to an entry and alias. Addition and removal
mappings remain episode-only discovery evidence because an empty alias or empty
canonical term cannot participate in exact alias retrieval.

Storage checks enforce the shapes: addition has null observed and non-empty
intended text; removal has non-empty observed and null intended text;
replacement has both values; only a replacement may have entry and alias IDs.

**Proposed product choice requiring confirmation:** Stage 1 displays and may
save additions and removals in the episode, but only non-empty replacements
become reusable profile entries. If additions or removals must affect future
Smart requests, their trigger and management model must be decided before
implementation; they must not be forced into alias-to-term rows.

### `personal_correction_events`

| Column | Contract |
| --- | --- |
| `id` | Integer primary key. |
| `owner_id`, `entry_id`, `alias_id` | Required owned profile references, with delete cascade. |
| `episode_id` | Nullable owned episode reference; set only for capture recurrence. |
| `use_id` | UUID for one approval or Smart request. |
| `event_type` | `alias_observed`, `profile_supplied`, or `intended_produced`. |
| `occurred_at` | Required UTC timestamp. |

`(owner_id, use_id, entry_id, alias_id, event_type)` is unique. Events store no
sentence, Original, Prepared, context, matched offset, provider, model, prompt,
or correctness field. Counts are derived from events; duplicate counters are
not stored.

An episode approval records `alias_observed` for each reusable selected
replacement. A later Smart request may record:

1. `alias_observed` when retrieval finds the enabled alias;
2. `profile_supplied` when the selected mapping is committed to the internal
   Smart request boundary; and
3. `intended_produced` only when a valid Smart result contains a lexical repair
   overlapping the matched alias span whose prepared span normalizes to the
   intended term.

These names describe observations only. They do not assert that profile
evidence caused the output or that the output was correct.

## Validation and normalization

Length limits are measured in Unicode code points in both request validation
and SQLite `CHECK` constraints. Text must be valid UTF-8 after JSON decoding,
must not contain NUL or other disallowed control characters, and is stored in
the exact user-approved display form.

The initial normalization key is deterministic and locale-independent:

1. Unicode NFKC normalization;
2. replace curly apostrophe `’` with ASCII apostrophe `'`;
3. Unicode `casefold`;
4. collapse every run of Unicode whitespace to one ASCII space; and
5. trim leading and trailing whitespace.

Stage 1 performs no stemming, phonetic matching, punctuation deletion, fuzzy
matching, or synonym expansion. Any broadening requires evidence from observed
misses and a later explicit decision.

## Bounded observed and intended sentences

When editing begins after a current Cleanup or Smart result, the browser freezes
the exact pre-edit Original in memory. During the same editing session, each
input refreshes the prospective post-edit Original and restarts the existing
cleanup debounce. The latest revision becomes the exact post-edit Original when
the edit settles or the user invokes **This is what I meant**. The browser
derives the changed range from the two bound revisions' common prefix and
suffix, then prefills the sentence containing that range on each side. Sentence
boundaries are the nearest preceding and following `.`, `?`, `!`, or line
break; the start or end of the value is the fallback. Delimiters remain in the
preview.

The preview never includes a neighboring sentence. A sentence longer than 500
code points may be shown ephemerally, but approval remains disabled until the
user edits it to at most 500 code points or removes it. The API and database
independently reject an over-limit value. Truncation is never silent. Both
observed and intended values are visible and independently editable/removable
before save.

This deliberately simple segmentation is an implementation boundary, not a
linguistic claim. Abbreviations and punctuation-free dictation may produce a
larger preview, but the storage limit remains absolute.

## Capture and approval state machine

```text
┌──────┐  current result  ┌──────────┐  first Original edit  ┌───────────┐
│ Idle │─────────────────▶│ Eligible │───────────────────────▶│ Available │
└──────┘                  └──────────┘                        └─────┬─────┘
                                                                  │ explicit
                                                                  │ action
                                                                  ▼
                                                            ┌───────────┐
                                                            │ Reviewing │
                                                            └─────┬─────┘
                                                                  │ save
                                                                  ▼
                                                            ┌──────────┐
                                                            │ Saving  │
                                                            └──┬────┬──┘
                                                       retryable │    │ success
                                                          failure│    ▼
                                                                 │ ┌─────┐
                                                                 └▶│Saved│
                                                                   └─────┘

Any invalidating action: Eligible / Available / Reviewing / Saving → Stale → Idle
Dismissal: Available / Reviewing → Idle, with no write
```

### Binding a missed result

`Eligible` exists only for a current Cleanup or Smart result and snapshots:

- result/request sequence;
- draft revision and exact pre-edit Original;
- mode, task context, prompt version, and correction contract version; and
- Prepared-result identity needed to prove that the result was current.

The first Original input starts one editing session. Further input before review
updates its post-edit revision rather than making the interaction stale; this is
required for ordinary multi-keystroke and dictation edits. `Available` begins
when that editing session settles for the cleanup debounce interval, or when the
user invokes the action, and binds the latest exact post-edit revision. The
automatic regeneration for that same revision may complete without invalidating
`Available`; otherwise the interaction could disappear before use. That
response must match the exact post-edit revision and transformation inputs.
After review opens, any further edit is a new revision and makes the review
stale. Any unrelated result replacement is also stale.

### Review and save

**This is what I meant** derives ordered addition, removal, and replacement
candidates from the frozen pre/post revisions. It does not alter Original or
Prepared. Review shows every candidate unselected by default, both bounded
sentences, and all durable text. The user may select 1–20 mappings, edit the
mapping text, edit or remove either sentence, and edit/remove applicability
context.

The interface describes this action as **save a Personal Correction**, never as
“data collection.” Save requires explicit review and approval of the displayed
Original → Intended mapping. That approval authorizes the saved correction for
live Smart use across later sessions until it is edited, disabled, or deleted.
An edit ends the prior mapping's authorization; the edited Original → Intended
mapping must be reviewed and explicitly saved before it is enabled for reuse.

Save is one database transaction. For each selected reusable replacement it:

1. normalizes intended and observed values;
2. reuses the existing owned entry with the same `intended_key`, or creates an
   enabled entry;
3. reuses the existing owned alias on that entry, or creates it;
4. creates the episode and ordered mapping rows; and
5. creates idempotent capture `alias_observed` events.

The unique `approval_id` makes a retry after a lost response return the original
saved episode rather than duplicate it. An equivalent mapping adds recurrence
to the existing entry; it does not create a duplicate entry. Save never merges
or overwrites differing non-empty applicability context silently. If an
existing entry's context differs, review must ask whether to keep the existing
context or replace it.

Ordinary editing, regeneration, Copy, target delivery, Outgoing selection,
inaction, dismissal, closing the dialog, or leaving the page writes nothing.

### Invalidation

The following make a bound review or in-flight save stale immediately:

- another Original edit after review binds the post-edit revision;
- Clear, a new draft, or replace-all input;
- mode or task-context change;
- prompt/version change;
- manual regeneration not bound to the exact post-edit revision;
- a stale or out-of-order response;
- result replacement for different inputs;
- page reload or application restart; or
- deletion or revision change of an entry being edited in management.

A stale Save is rejected before a request is sent. Server responses carry the
saved entry revisions; management writes use `expected_revision` and return
HTTP 409 on conflict. A 409 never overwrites or deletes newer state.

## API boundary

The first release adds this local API surface. All routes select the constant
local principal internally, call `require_configuration`, use privacy-safe
validation errors, and return `Cache-Control: no-store` for content-bearing
responses.

| Method and route | Contract |
| --- | --- |
| `GET /api/personal-corrections` | Return global state, entries, aliases, bounded episodes, and content-minimized history for management. |
| `PUT /api/personal-corrections/profile` | Globally disable or re-enable an existing local profile. Accept only `enabled`; it cannot create an absent profile. |
| `PUT /api/personal-corrections/entries/{id}` | Revision-checked save of a reviewed edit to intended term, aliases, context, or enabled state; changed mapping text is not reusable before this explicit save. |
| `DELETE /api/personal-corrections/entries/{id}` | Revision-checked hard deletion with the disclosed cascade. |
| `POST /api/personal-corrections/candidates` | Derive ordered lexical mappings and sentence prefills from exact pre/post revisions without writing them. |
| `POST /api/personal-corrections/episodes` | Idempotently approve bounded sentences and 1–20 selected mappings in one transaction. |
| `GET /api/personal-corrections/export` | Stream the version 1 private export from one read transaction. |

The candidate request accepts the same 100,000-code-point maximum per full
revision as current cleanup input, plus bound result metadata. Full revisions
exist only for request processing and are not retained or echoed in errors. The
response contains candidates and sentence prefills but no durable ID. The
episode request contains `approval_id`, bound mode/version metadata, only the
reviewed bounded fields, selected mappings, and explicit context-conflict
choice when needed; it never resubmits the surrounding documents.

Ordinary `/api/cleanup` remains the only processing route. Its public input
keeps Original, mode, and optional Smart task context but does not accept
Personal corrections payloads or owner IDs. The route performs server-owned
retrieval and constructs the internal request described below.

## Deterministic Smart retrieval

Retrieval runs only when all of these are true:

- mode is Smart;
- the local profile row exists and is globally enabled;
- the entry and alias are enabled by virtue of the entry being enabled; and
- the normalized alias occurs in normalized Original at a lexical boundary.

A lexical boundary means an alias beginning or ending with a Unicode letter,
number, mark, or underscore cannot be adjacent to the same class in Original.
Punctuation otherwise remains significant. Matching retains normalized offsets
only in memory for result comparison; offsets are not persisted.

Matches sort by:

1. earliest normalized start offset;
2. longest normalized alias first;
3. `alias_key`;
4. `intended_key`; and
5. entry UUID.

Duplicate occurrences of the same alias-entry pair in one Original produce one
retrieval item and one event of each applicable type. Up to 50 unique mappings
may be supplied, matching the current bounded Smart-knowledge request limit. A
51st match causes profile retrieval to fail open as a whole: Smart continues
without Personal corrections, no occurrence rows are written for that request,
and the UI exposes a content-free safe diagnostic. It must not send a silently
partial or order-dependent profile.

Each retrieved item keeps entry and alias IDs only in local request state for
event correlation. The typed object serialized inside the existing untrusted
Smart-evidence JSON frame contains only intended term, matched alias, and
approved applicability context. Observed/intended sentences, local IDs, other
aliases, disabled entries, recurrence counts, and events are never sent to the
provider. The Smart prompt treats mappings as user-owned evidence and may
abstain when context is ambiguous.

The public cleanup request model must no longer accept ordinary caller-supplied
profile content. The route builds a separate internal Smart request after
server-side retrieval. Conservative mode reaches `CleanupService` with no task
context or profile evidence exactly as it does now.

## Failure behavior

Personal corrections must never remove access to Original, block Copy or
delivery, or convert a Cleanup request into Smart.

| Failure | Required behavior |
| --- | --- |
| Profile read, normalization, or retrieval fails | Run Smart without profile evidence; show a content-free retryable diagnostic. |
| Occurrence write fails before Smart handoff | Do not supply profile evidence; run Smart without it so `profile_supplied` is not falsely claimed. |
| Provider, timeout, or result validation fails | Preserve existing fail-open-to-Original behavior; retain only successfully committed observed/supplied events. |
| `intended_produced` write fails after a valid result | Keep the Prepared result and review queue; show history as incomplete without logging text. |
| Candidate derivation fails | Keep ordinary edited Original and regeneration behavior; save remains unavailable. |
| Approval validation fails | Keep current review state in browser memory and identify fields to fix; write nothing. |
| Approval transaction fails | Roll back every entry, alias, episode, mapping, and event write; allow idempotent retry while current. |
| Management/export read fails | Leave durable state unchanged and return a content-free safe error. |
| Export is interrupted | Leave no server-side artifact; a partial browser download is not a successful export. |

Validation handlers for Personal corrections routes must not echo request
bodies or private text. Routine logs may contain operation, safe error code,
row counts, durations, and content lengths, but not terms, aliases, context,
sentences, profile JSON, exports, or provider payloads.

## Management and deletion

Personal corrections is one user-visible management area. It shows global
enablement, entries, aliases, approved context, per-entry enabled state,
content-minimized event counts/history, and linked bounded episode evidence.
Exact layout is an implementation choice; hiding any durable field is not.

An entry update is transactional, owner-scoped, and revision-checked. Disabling
an entry prevents future retrieval but preserves its episodes and history.
Global disablement prevents all retrieval but preserves entries.

UI deletion is scoped to the currently active development state. It must not
claim to remove the correction from another state. A separate administration
command may purge Personal Corrections across registered states only. Before
writing, that command must preview the affected registered states and require
explicit confirmation; unregistered directories are outside its scope.

Entry deletion is a hard delete. In one transaction it deletes:

- the entry and every alias;
- every linked occurrence event;
- every episode containing a mapping linked to that entry, including that
  episode's other mapping rows and sentence fields; and
- no unrelated entry.

Deleting the whole shared episode is intentionally privacy-favoring: sentence
evidence that supported a deleted entry must not remain indirectly reachable
through another mapping. Surviving profile entries remain, but recurrence from
that shared episode disappears. The confirmation states this consequence.
Deleted content is absent from all later API responses and exports; there are
no tombstones or application audit copies.

Removing an individual alias uses the same privacy rule at alias scope: it
deletes that alias, its events, and every episode containing a mapping linked to
it, while preserving the entry and its other aliases. Editing alias text is a
revision-checked entry update; episode mapping text remains the exact approved
historical value, while future retrieval uses the edited alias. The management
confirmation distinguishes edit from deletion and states the deletion cascade.

Deletion claims must name their scope: current-state UI deletion or confirmed
purge across the previewed registered states. Neither flow claims deletion from
unregistered directories or user-created exports.

## Versioned private export

`GET /api/personal-corrections/export` produces UTF-8 JSON with
`Content-Disposition: attachment`, `Cache-Control: no-store`, and media type
`application/vnd.local-text.personal-corrections+json;version=1`. The server
does not retain an export file.

The top-level object is:

```json
{
  "schema_version": "personal-corrections-export-v1",
  "exported_at": "<UTC RFC 3339 timestamp>",
  "profile": {
    "enabled": true,
    "entries": [],
    "episodes": [],
    "events": []
  }
}
```

Entries contain ID, intended term, approved context, enabled state, revision,
timestamps, and aliases with IDs and timestamps. Episodes contain ID, approval
ID, optional sentences, source mode, prompt version ID, contract version,
timestamp, and ordered mappings. Events contain ID, linked IDs, use ID, event
type, and timestamp. Normalization keys and `owner_id` are internal and omitted.

Arrays sort by creation time then ID; mappings sort by ordinal. The export is a
snapshot from one read transaction. Empty or never-enabled state still exports
the version, timestamp, `enabled: false`, and empty arrays. Deleted rows and
unrelated application configuration are absent. Import is not part of stage 1.

**Unresolved delivery choice — non-blocking for the schema:** The first release
may expose this endpoint through a management-area Download action or an
explicit admin command. Whichever surface is selected must emit the exact same
schema and must not write a second server-managed copy.

## Development-state location and inheritance

The development-state root moves from the current macOS Application Support
location to `${XDG_DATA_HOME:-~/.local/share}/local-text/dev-states/`. A
dedicated administration operation performs and verifies that migration before
activation. Normal startup never moves state files or runs database migrations.

After Personal Corrections are implemented, creation of a new development
state must inherit them when an eligible source was explicitly activated for
that creation. The source is read in one transaction, copied as a coherent
snapshot, and verified in the destination before activation. API keys and other
protected shared configuration are not part of the Personal Corrections
snapshot.

If an eligible source exists and snapshot creation, copy, or verification
fails, initialization fails before activation and preserves the source. It must
not silently substitute an empty profile. If no eligible source exists,
initialization reports an explicitly empty Personal Corrections profile and may
activate the state. Creation performs no backfill into existing states and no
post-creation synchronization; parallel states may diverge.

## Database migration and rollback

Add one Alembic revision after `0003_unified_preparation_default`. Upgrade:

1. creates the six tables, ownership-aware foreign keys, checks, unique
   constraints, and retrieval/history indexes;
2. creates no profile, entry, setting, event, or seed row; and
3. updates `SCHEMA_REVISION` so an old database reports `mismatch` until the
   explicit controlled migration runs.

The explicit administration path owns database migration. Normal application
startup remains read-only with respect to schema, seed state, and state-root
location and returns `setup_required` on a missing or mismatched revision.

Downgrade to `0003_unified_preparation_default` drops child tables before
parents. It is intentionally data-destructive and must refuse to proceed when
Personal corrections rows exist unless the operator passes an explicit
destructive-downgrade acknowledgement after creating and verifying a private
export. The exact acknowledgement flag belongs to the admin CLI, not normal
startup. Rollback requires the matching pre-feature application version; schema
downgrade alone is not a supported mixed-version runtime.

Migration tests must cover fresh upgrade, predecessor upgrade with unrelated
configuration preserved, no row creation, foreign-key enforcement, all checks
and uniqueness rules, refused non-empty downgrade, acknowledged downgrade, and
re-upgrade. Startup tests must prove that missing and predecessor schemas are
not mutated.

## Privacy invariants

1. One implicit local principal owns every Personal corrections query and row.
   No API accepts an owner selector.
2. Only explicit approval writes knowledge. Editing, Copy, delivery, Outgoing,
   inaction, dismissal, and model-repair review do not.
3. Full Original, Prepared, Outgoing, task context, and surrounding documents
   never enter Personal corrections tables, exports, errors, or routine logs.
4. Both optional sentence fields are previewed, editable/removable, bounded to
   500 code points, and enforced at API and storage boundaries.
5. Historical sentences and occurrence history never enter a provider request.
6. Only matching enabled aliases from an enabled profile inform Smart. Personal
   corrections never inform Cleanup.
7. Profile evidence is advice, not an automatic replacement command. Every
   resulting lexical change remains under the Smart review contract.
8. Disablement is reversible retention. Deletion is hard removal within its
   declared current-state or confirmed registered-state purge scope.
9. Export contains only Personal corrections state and writes no server-side
   copy. It is private data, not a support artifact or Git attachment.
10. Reactive episodes are excluded from held-out evaluation unless a future
    approved evaluation purpose and contract independently qualifies them.
11. API keys remain in protected shared configuration and never enter Personal
    Corrections tables, snapshots, or exports. Keychain storage is deferred.
12. Each development state owns an independent snapshot. New-state inheritance
    is transactional and verified, never silently empty when a source exists,
    and never followed by automatic synchronization.

## Acceptance checks

Implementation is complete only when the following evidence passes with
synthetic text.

### Persistence and migration

- A fresh migration creates an empty, disabled-by-absence profile with no seed
  write; predecessor configuration survives upgrade and rollback tests.
- Database checks reject over-limit/private-invalid text even when API
  validation is bypassed.
- Store tests prove every read/write/delete includes the local owner and that a
  foreign-owner fixture cannot be returned or mutated.
- Equivalent normalized replacements reuse one entry and alias while creating
  a distinct episode/event; differing context is never overwritten silently.
- Revision conflicts and repeated `approval_id` requests are deterministic.

### Capture and stale state

- Browser/API tests cover asymmetric addition, removal, and replacement
  examples whose expected mappings are not derived from production diff code.
- One Cleanup miss and one Smart miss reach review with exact pre/post binding
  and bounded editable sentences.
- A multi-keystroke edit retains one frozen pre-edit revision and binds the
  latest settled post-edit revision. Same-revision automatic regeneration
  preserves availability; every listed invalidating action makes review/save
  stale.
- Dismissal, ordinary edit without the explicit action, Copy, delivery,
  Outgoing selection, model-repair review, and inaction produce no write.
- A lost save response followed by retry creates one episode only; a failed
  transaction creates no partial row.

### Retrieval and correction isolation

- Case, Unicode, apostrophe, whitespace, punctuation, lexical-boundary,
  duplicate-occurrence, ambiguous-alias, disabled-entry, and globally disabled
  cases prove the exact normalization and ordering contract.
- Fifty matches are deterministic; 51 fail open without partial evidence or
  occurrence rows.
- Smart provider payload inspection contains only matched mapping fields and
  approved context. It excludes sentences, other aliases, events, counts, and
  unrelated entries.
- Conservative/Cleanup requests and outputs are byte-for-byte unchanged by
  profile state, including when retrieval fails.
- Provider failure, timeout, malformed output, and event-write failure preserve
  the existing usable Original path.

### Events, deletion, and export

- Events distinguish observed, supplied, and intended-produced. An unchanged
  result, unrelated canonical text elsewhere, or invalid result does not create
  `intended_produced`.
- Deleting an entry removes aliases, linked events, and every linked episode
  while retaining unrelated entries; future export cannot reveal deleted text.
- Current-state deletion and preview/confirm cross-state purge scopes are
  exercised separately; neither claims to purge unregistered locations.
- Export validates against a checked-in v1 schema/fixture, has stable ordering,
  includes all approved fields and only content-minimized events, and emits no
  server-side artifact.

### Representative UI

- Desktop and narrow-browser checks cover disabled/empty, capture available,
  review with over-limit sentence, save failure/retry, ambiguous alias warning,
  disabled entry, delete confirmation, history, and export.
- DOM/accessibility checks prove Original remains editable, Prepared remains
  read-only, and capture or Personal corrections failures do not gate Copy,
  Outgoing, or target delivery.

## Unresolved choices

The following must be confirmed or deliberately deferred before the affected
ticket is marked ready for implementation:

1. **Addition/removal reuse:** Confirm stage 1's proposed episode-only storage
   for additions and removals, with replacement-only runtime reuse.
2. **Export surface:** Choose browser Download or admin command. This does not
   block schema/store work.
3. **Exact management composition:** Navigation and component layout remain an
   implementation choice, but every durable field and destructive consequence
   must stay inspectable.

Fuzzy aliases, outcome feedback, import, hosted ownership, device sync,
retention windows, automatic formulaic rules, Keychain storage, and any use of
episodes in evaluation are deferred product work, not implementation choices.

## Exact ticket-reconciliation proposal

This section proposes tracker mutations only. Do not apply them without
separate authorization.

### Create umbrella

**Title:** `Deliver the private single-user Personal corrections flywheel`

**Labels:** `enhancement`, `ready-for-agent` only after this specification and
the two blocking product choices are confirmed.

**Body:** Link this specification and the execution guide. State that the
umbrella owns stages 2–8 for one implicit local principal; Cleanup remains
account-independent; startup never migrates; ordinary use never approves; and
reactive episodes are not held-out evidence. Use the child graph below as the
definition of sequence. Close only after the first usefulness demonstration,
not after schema or UI completion.

### Revise existing issues

| Issue | Exact mutation | Blocking edges after reconciliation |
| --- | --- | --- |
| [#12](https://github.com/dmclark/sayloom/issues/12) | Retitle **Create the local Personal Corrections profile and management boundary**. Replace acceptance criteria with: the first explicitly approved save creates the profile row and enabled entry; schema and owner-scoped store; management read/edit/disable/delete without an unreviewed create path; optimistic revisions; explicit migration/downgrade; no startup migration/seed; no Original/Prepared retention; synthetic persistence/API/UI checks. Link this specification. Remove `#10` as a blocker because hosted identity is deferred; state that `local` is the only principal. | Umbrella only. |
| [#109](https://github.com/dmclark/sayloom/issues/109) | Retitle **Capture a bound missed repair for Personal corrections review**. Replace the claim that capture cannot lead to personalization with the state machine in this specification. Add bounded editable/removable observed/intended sentences and shared lexical candidates. Preserve no-write behavior for ordinary actions. Bind a normal edit session from one frozen pre-edit revision to its latest settled post-edit revision; allow exact post-edit automatic regeneration, then invalidate any edit after review opens or any changed transformation input. Remove #45 as blocker and remove `needs-triage`; add `ready-for-agent` only after the addition/removal choice is confirmed. | #12. |
| [#13](https://github.com/dmclark/sayloom/issues/13) | Retitle **Approve and save a Personal correction episode**. Replace model-confirmation-only input with selected user-supplied mappings from #109. Require replacement dedupe, idempotent `approval_id`, atomic episode/mapping/event write, context conflict review, bounded sentence enforcement, and no writes from dismissal/Copy/delivery/inaction. Remove #11 and #12 as direct blockers; #12 remains transitive through #109. | #109. |
| [#45](https://github.com/dmclark/sayloom/issues/45) | Keep title and current-result browser-local scope. Add a note: this is optional later positive confirmation of model-proposed repairs; it neither blocks #109 nor authorizes Personal corrections persistence. Do not close it and do not add it to the active flywheel's blocking path. | Keep #11 only. |

### Create tracer-bullet children

1. **`Retrieve matching Personal corrections for Smart only`** — Implement
   server-owned normalization, exact lexical-boundary matching, deterministic
   ordering, 50-item bound, typed Smart evidence, observed/supplied/produced
   events, and every fail-open path. Prove Cleanup isolation. **Blocked by #13.**
2. **`Complete Personal Corrections deletion, history, and private export`** —
   Implement inspectable content-minimized history, hard cascade semantics,
   current-state UI deletion, preview/confirm purge across registered states,
   and export v1 with no server artifact. **Blocked by the Smart retrieval
   child.**
3. **`Demonstrate the first private Personal corrections usefulness loop`** —
   Record the execution guide's nine-step gate with one real private mapping,
   using only content-free evidence in the issue. Do not paste private text or
   claim general efficacy. **Blocked by deletion/history/export.**
4. **`Add optional helped or wrong feedback for a produced correction`** —
   Define a separate explicit outcome signal; Copy, delivery, and inaction stay
   neutral. Keep it out of the first usefulness gate. **Blocked by the first
   usefulness demonstration; not blocked by #45 unless later design merges the
   two explicit review interactions.**
5. **`Review content-free Personal corrections patterns for formulaic research`** —
   Review aggregate recurrence and category summaries only and either open one
   focused formulaic-rule research question or record that more ordinary use is
   needed. Never graduate behavior into Cleanup without a separate versioned
   Cleanup contract and evidence. **Blocked by the first usefulness
   demonstration; recurring thereafter.**

### Preserve and defer

- Keep #9 as historical broader Smart/personalization context; add no blocking
  edge from its superseded fixed-arm sequence.
- Keep #46 open and mark its automatic-strategy path deferred; do not close it
  as completed by Personal corrections.
- Keep #60, #112, #116, #117 and downstream Cleanup/evaluation work open but
  deferred. They do not block this umbrella.
- Add no hosted-account, participant-package, formal-evaluation, or pilot issue
  to the active blocking graph.

The resulting active graph is exact:

```text
Umbrella
  └─ #12 local profile foundation
       └─ #109 bound missed-repair capture
            └─ #13 explicit approval and save
                 └─ New: Smart-only retrieval and events
                      └─ New: deletion, history, and export
                           └─ New: first usefulness demonstration
                                ├─ New: optional helped/wrong feedback
                                └─ New: recurring formulaic-readiness review

#45 remains on its separate #11 model-proposed-repair review path.
```
