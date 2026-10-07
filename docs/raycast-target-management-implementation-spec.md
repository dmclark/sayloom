# Raycast Target Management redesign implementation specification

- **Status:** Ready for implementation review
- **Scope:** Local macOS Raycast Target Management in Settings
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Current implementation reference:** [`README.md`](../README.md)
- **Prepared:** 2026-09-30

## Purpose

This specification replaces manually authored delivery targets with a catalog
of installed, launchable macOS applications. It defines the storage reset,
application discovery, internal adapter registry, generated-command lifecycle,
readiness and user-confirmed testing model, Settings behavior, safety
boundaries, staged implementation, and acceptance evidence.

The reader's next action is to review this contract, verify the two bundle IDs
called out below on the isolated acceptance Mac, and then implement the stages
in order. This document does not authorize application-code changes, migration
execution, or changes to Raycast.

## Confirmed outcome

After the explicit migration, **Targets** begins empty. A user searches a
catalog of installed applications, selects one, and receives a durable Target
whose name, icon, bundle ID, version, and location came from that application's
bundle metadata. The user cannot type or edit a bundle ID, script, command
body, or adapter.

An internal registry maps known bundle IDs to Sayloom-tested integrations and
adapters. Every unknown bundle ID uses the Generic focused-paste adapter. A
Generic Target may become **Verified on this Mac**, but remains **Generic**;
integration support and local readiness are independent facts.

Every Target has one generated Raycast Script Command. Installation does not
assign a hotkey and delivery does not choose a destination conversation,
thread, recipient, terminal session, editor, or input. The user prepares and
focuses the intended input before invoking the command. Delivery inserts the
current Outgoing value and never submits it.

## Non-goals

This redesign does not add:

- a Workspace Target chooser or send button;
- automatic recipient, conversation, thread, tab, session, or input selection;
- arbitrary user scripts, adapter selection, or editable command templates;
- Return, Enter, send, or submit behavior;
- automatic Raycast configuration, private Raycast-data inspection, or hotkey
  management;
- Accessibility inspection of destination text to infer success;
- CLI, URL-scheme, browser-tab, plugin, or application-specific adapters beyond
  focused paste and iTerm direct write;
- hosted delivery or non-macOS target management; or
- migration of legacy target definitions.

The five fixed `Dev:` commands under `raycast/` and their
`scripts/install-raycast.py` symlink installer remain permanently separate.
Target Management must neither enumerate them as managed Targets nor alter
them.

## Current implementation seams

The redesign replaces behavior at these existing boundaries rather than
building a parallel subsystem:

- `src/local_text/targets.py` owns validated definitions, the two current send
  strategies, deterministic command generation, ownership headers, and the
  four demo definitions.
- `src/local_text/target_store.py` owns target CRUD, default seeding, and
  operation-error persistence.
- `src/local_text/target_adapter.py` owns collision-safe, atomic filesystem
  observation, installation, and removal. A later unmerged branch also proves
  that bundle discovery can live behind a test-injectable macOS boundary.
- `src/local_text/app.py` composes storage, generation, filesystem observation,
  and `/api/targets` routes. `create_app(..., target_adapter=...)` is the current
  isolation seam.
- `src/local_text/static/index.html`, `app.js`, and `app.css` implement the
  current manual modal editor and target overview in Settings.
- `migrations/versions/0002_target_management.py` created `targets` and
  `target_operation_errors`; `0003_unified_preparation_default` is the current
  schema head.
- `src/local_text/admin.py` applies migrations and then deterministic seeds.
  Normal startup only checks `SCHEMA_REVISION` and must remain non-mutating.
- `tests/test_targets.py` covers generation, lifecycle, collision safety,
  storage, API, migration, and static UI contracts. `tests/test_raycast.py`
  separately protects the fixed development commands.

The current `Settings.raycast_directory` environment/default value is runtime
configuration. This redesign replaces it for managed Targets with one durable
application setting. Test injection may remain, but production Target
Management must read the persisted setting.

## Terms

- **Catalog application:** An application currently discovered and validated
  from macOS bundle metadata. It is ephemeral and read-only.
- **Target:** One user-selected catalog application persisted for managed
  delivery.
- **Integration support:** `sayloom_tested` for a registry match or `generic`
  for fallback. This never describes current machine readiness.
- **Adapter:** Internal, versioned delivery behavior chosen by the registry.
- **Command file state:** Filesystem observation of the expected generated
  command: not installed, current, stale, or collision.
- **Raycast discovery:** User confirmation that the current command appeared in
  Raycast. It is never inferred from command-file presence.
- **Local verification:** User confirmation that **Test Target** inserted its
  marker into the intended input on this Mac.
- **Orphaned command:** A recognized Sayloom-owned managed command whose Target
  no longer exists after the reset or a later inconsistency.
- **Fingerprint:** The exact inputs that make a local verification or Raycast
  discovery current.

## Ownership boundaries

| Boundary | Owns | Must not own |
| --- | --- | --- |
| Application catalog | Bundle enumeration, metadata validation, icon conversion, deduplication, current availability | Persistence, adapter choice, file writes |
| Target store | Selected application snapshots, tests, discoveries, operation errors, folder setting | Bundle scanning, command generation, filesystem mutation |
| Integration registry | Bundle-ID-to-integration mapping, support label, adapter key | User configuration or machine readiness |
| Delivery adapters | Versioned delivery fragment, dependencies, test execution using that same fragment | Target storage, Raycast indexing, success confirmation |
| Command generator | Deterministic complete script and digest | Installation, adapter selection, user confirmation |
| Command artifact store | Folder validation, observation, atomic install/regenerate, safe uninstall, orphan scan/removal | Application launching, Raycast private state |
| Readiness service | Joins current app, dependency, folder, command, discovery, and test observations | Collapsing those facts into an unsupported success claim |
| HTTP routes | Validation, orchestration, safe responses, confirmation transitions | Direct SQL or ad hoc filesystem access |
| Settings UI | Search, selection, status explanation, explicit actions and confirmations | Editable identity, scripts, adapters, or inferred success |

Keep the existing separation between Outgoing publication and delivery.
Generated commands continue to consume only `GET /api/outgoing-state`, including
its Evidence Collection gate, and Target lifecycle operations never change
Outgoing.

## Durable model and migration

Add Alembic revision `0004_raycast_target_catalog` with
`0003_unified_preparation_default` as its parent, and update
`SCHEMA_REVISION`. The controlled `scripts/dev.py restart` workflow remains the
only normal development update path: verify, back up the selected development
state, migrate, seed, and restart that state. Application startup must not
migrate, reset, seed, or repair data.

### Intentional reset

The upgrade is intentionally destructive only to the old target tables:

1. delete all rows from `target_operation_errors`;
2. delete all rows from the old `targets`, including custom or edited rows;
3. replace the old table shape with the schema below; and
4. create no Target rows.

Remove `INITIAL_TARGETS` and `TargetStore.seed_defaults()`. The admin `seed`
result no longer reports or creates target seeds. Prompt and all unrelated
state remain unchanged. The migration must not inspect or mutate the Raycast
folder, so old generated files survive and become visible as Orphaned commands
after the migrated application reads the configured folder.

Downgrade may restore the old empty table shapes but cannot reconstruct reset
definitions. The controlled backup is the rollback path. The migration test
must say this explicitly and prove unrelated prompt/settings rows survive.

### `targets`

| Column | Contract |
| --- | --- |
| `id` | Random UUID string primary key; also determines the command filename. |
| `display_name` | Metadata snapshot, 1–200 Unicode code points. |
| `application_name` | Metadata snapshot, 1–200 Unicode code points. |
| `application_bundle_id` | Validated bundle ID, compared case-insensitively. |
| `application_location` | Canonical absolute `.app` path selected from the catalog, at most 2,048 code points. |
| `application_version` | `CFBundleShortVersionString`, falling back to `CFBundleVersion`; nullable when neither exists. |
| `icon_png` | Nullable bounded PNG snapshot, at most 256 KiB, so a missing application remains identifiable. |
| `created_at`, `updated_at` | Required UTC timestamps. |

`(application_bundle_id, application_location)` is unique using
case-insensitive bundle-ID comparison. Multiple installed copies with the same
bundle ID may be selected independently only when their canonical locations
differ. Adapter and support fields are not persisted; the current registry
resolves them from the immutable bundle identity so registry fixes take effect
without rewriting user data.

Users cannot edit these columns. A **Use this installed copy** remediation may
replace all metadata-owned fields from a freshly rediscovered catalog entry
with the same bundle ID. That update invalidates verification and discovery by
fingerprint without pretending that a missing application moved by itself.

### `target_tests`

| Column | Contract |
| --- | --- |
| `id` | Random UUID primary key. |
| `target_id` | Required foreign key with delete cascade. |
| `marker` | Unique synthetic marker, at most 100 characters; never user text. |
| `outcome` | `awaiting_confirmation`, `confirmed`, `rejected`, or `execution_failed`. |
| `fingerprint_sha256` | Digest of the tested inputs described below. |
| `application_version`, `application_location` | Exact observed values at execution. |
| `adapter_key`, `adapter_version` | Exact adapter contract tested. |
| `command_sha256` | Expected generated-command digest. |
| `raycast_folder` | Canonical configured folder at execution. |
| `attempted_at`, `resolved_at` | UTC timestamps; `resolved_at` is null while awaiting confirmation. |
| `failure_code` | Nullable allowlisted safe execution category; no raw tool output. |

Only a `confirmed` row whose fingerprint equals the current fingerprint yields
**Verified on this Mac**. Retain prior rows to show the latest successful test
time and why a later change made it stale. A rejected or failed later attempt
does not erase the last successful timestamp, but local readiness is not
currently verified unless the latest applicable test is confirmed.

### `target_raycast_discoveries`

| Column | Contract |
| --- | --- |
| `target_id` | Primary key and cascading foreign key. |
| `raycast_folder` | Canonical folder confirmed by the user. |
| `command_sha256` | Exact current command the user found. |
| `confirmed_at` | Required UTC timestamp. |

This records **I found it** only. It is current only while the folder, expected
command digest, and current installed file still match. It does not claim a
hotkey, successful execution, or successful insertion.

### `target_operation_errors`

Retain the existing target-scoped, operation-keyed safe error model and delete
cascade. Expand the operation vocabulary only as required for `install`,
`regenerate`, `uninstall`, `remove`, `test`, and `relink`. Errors contain an
allowlisted code, user-safe message, retry action, and timestamp; never include
Outgoing text, marker content, process output, private Raycast data, or an
unselected machine path.

### Persisted folder setting

Use the existing `app_settings` table with the single key
`raycast_script_commands_folder`. Store a JSON string containing the canonical
absolute path. Before Alembic upgrade, the explicit admin `migrate` command
captures `Settings.resolved_raycast_directory`; after upgrade, it inserts that
canonical path only when the new key is absent. This preserves an existing
`LOCAL_TEXT_RAYCAST_DIRECTORY` override or otherwise persists the current
`~/.config/raycast/scripts` default, without creating the directory. Direct
application startup performs neither step. A test-only injected artifact store
may bypass this lookup.

Changing the setting is one atomic store operation after validation succeeds.
It does not move commands between folders or delete anything in the previous
folder. Targets then observe the new folder as not installed, and prior
verification and Raycast-discovery confirmations become stale by fingerprint.
The old folder may be restored to make matching observations current again;
history is not destructively rewritten.

## Application discovery

Implement discovery as a test-injectable macOS boundary, separate from command
artifacts. Scan these roots in order:

1. `/Applications`;
2. `~/Applications`; and
3. `/System/Applications`.

Traverse directories recursively without following symlinks and never descend
inside an `.app` package after treating it as a candidate. This includes
locations such as `/System/Applications/Utilities` without scanning arbitrary
user data or mounted volumes. The catalog documents that applications outside
these standard roots must be moved or installed into one of them before they
can be selected.

A candidate is launchable only when all of these checks pass:

- the `.app` and `Contents/Info.plist` are non-symlink directories/files;
- the plist is at most 1 MiB and parses to a dictionary;
- `CFBundlePackageType` is `APPL`;
- `CFBundleIdentifier` is a valid single-line bundle identifier;
- `CFBundleExecutable` names an executable regular file under
  `Contents/MacOS` after containment validation;
- `LSBackgroundOnly` and `LSUIElement` are not true; and
- names, version values, location, and icon metadata pass their bounds.

Use `CFBundleDisplayName`, then `CFBundleName`, then the bundle filename for the
display name. Use `CFBundleName`, then the display name for the application
name. Use `CFBundleShortVersionString`, then `CFBundleVersion` for the version.
Resolve `CFBundleIconFile` within `Contents/Resources`; invoke the absolute
macOS `/usr/bin/sips` executable without a shell to produce a bounded PNG in a
private temporary directory. Missing, unsupported, oversized, or failed icons
use the Sayloom fallback icon and do not exclude an otherwise valid app.

Represent each row with an opaque catalog ID derived from the bundle ID and
canonical location. Before Add Target or relink writes anything, rediscover the
catalog ID and validate its metadata again; never trust client-returned names,
IDs, paths, versions, or icons. Catalog reads perform no durable writes.

Do not collapse separate installations with the same bundle ID. Deduplicate
only an identical canonical location. Sort case-insensitively by display name,
then bundle ID, then location. Search matches display name, application name,
bundle ID, and the user-visible location. The API may cache one scan briefly,
but **Refresh applications** must force a new scan and writes must revalidate.

A selected Target remains visible when its exact location disappears or no
longer matches the recorded bundle ID. Its status becomes **Application
missing** with reinstall, **Use this installed copy** when the same bundle ID
exists elsewhere, and Remove Target remediation. Never silently relink it.

## Adapter contract and registry

Define a small internal `DeliveryAdapter` contract:

```python
class DeliveryAdapter(Protocol):
    key: str
    version: str
    dependencies: tuple[Dependency, ...]

    def render_delivery(self, application: ApplicationIdentity, payload_file: str) -> str: ...
```

`render_delivery` returns only the deterministic shell fragment that launches
the exact selected application and inserts the contents of `payload_file`.
Both the installed command generator and the temporary Test Target generator
must compose this same fragment. Do not implement a second test-only delivery
path.

Adapter `version` is an explicit constant changed whenever insertion behavior,
timing, dependency resolution, or generated delivery bytes change. The command
digest catches any complete-script change; the adapter version separately
explains why local verification became stale.

The registry returns an immutable descriptor containing integration key,
display label, `sayloom_tested` support, and adapter. No match returns the
Generic descriptor and focused-paste adapter. Registry matching uses a
case-insensitive exact bundle ID; names and locations never select an adapter.

### Initial adapters

**Focused paste** keeps the current safety behavior:

- require an executable `cliclick`, resolving an explicit test override,
  `PATH`, then `/opt/homebrew/bin/cliclick`;
- launch the exact selected `.app` location rather than whichever duplicate
  LaunchServices chooses for a bundle ID;
- require the user to have focused the intended input;
- release modifiers, perform Cmd-V, and never issue Return;
- preserve and restore the text clipboard on success, failure, and signals;
- preserve UTF-8 and multiline content; and
- report bounded, safe dependency, launch, clipboard, and insertion failures.

**iTerm direct write** keeps the current AppleScript behavior, addressed to the
selected iTerm application identity, and executes
`write text outgoingText newline NO` in the current session of the current
window. It never uses Return and does not require `cliclick`.

### Initial known mappings

| Integration | Bundle ID evidence | Adapter |
| --- | --- | --- |
| Messages | **Unverified:** capture `CFBundleIdentifier` from the installed system app before coding the registry fixture | Focused paste |
| Amp for macOS | **Unverified:** capture `CFBundleIdentifier` from the installed signed native app before coding the registry fixture | Focused paste |
| Amp Web App (Chrome) | `com.google.Chrome.app.bpgpkfmeagdpdcenbogglipmfkalmple` in the current repository; verify on the acceptance Mac because Chrome app IDs can be installation/profile-specific | Focused paste |
| iTerm | `com.googlecode.iterm2` | iTerm direct write |
| Supacode | `app.supabit.supacode` | Focused paste |
| Visual Studio Code | `com.microsoft.VSCode` | Focused paste |

The Messages and native Amp identifiers were not established by the repository
or confirmed design. Do not guess them from an application name or an Internet
claim. Before merging the registry, use the catalog's validated metadata in the
isolated acceptance state to capture the exact IDs, add them as constants and
fixtures, and prove those discovered rows resolve to Sayloom-tested focused
paste. If an expected app is unavailable, that mapping and its acceptance case
remain incomplete rather than being replaced with a speculative ID.

Messages inserts into the currently selected conversation's focused compose
field; it stores no recipient. Amp native and web insert into the user's
prepared thread and focused input.

## Generated commands and artifact ownership

Retain `sayloom-target-{target_id}.sh` and the two legacy ownership headers so
pre-redesign commands can be recognized as orphans:

```sh
# sayloom-owned-target: {target_id}
# sayloom-generated-file: sayloom-target-{target_id}.sh
```

New commands also include a command-schema version, adapter key/version, and
expected bundle ID as non-authoritative comments. Ownership still requires a
non-symlink regular file, an exact safe filename, and both matching legacy
headers within the bounded header read. Metadata-like text in another file or
a mismatched filename never grants ownership.

Generation remains deterministic for the Target snapshot, current registry,
adapter version, and command schema. The command:

1. fetches only current `outgoing_text` from `/api/outgoing-state`;
2. rejects unavailable, malformed, empty, or whitespace-only state;
3. delegates insertion to the resolved adapter fragment; and
4. reports insertion without claiming submission.

Install writes a missing expected file atomically with mode `0700`. Regenerate
atomically replaces only a recognized Sayloom-owned file. Uninstall removes
only a recognized file. A symlink, directory, unreadable entry, malformed
owned marker, or unrelated regular file at the destination is a collision and
is never followed, replaced, chmodded, or removed.

An orphan scan considers only direct entries matching
`sayloom-target-*.sh` in the validated configured folder. A recognized file is
orphaned when its ownership target ID has no database row. An opaque orphan ID
is returned to the browser; deletion re-scans and revalidates ownership and the
exact filename immediately before unlinking. Orphan cleanup is always an
explicit, individually confirmed user action. Unrecognized files are omitted
from the orphan list and never altered.

## Raycast Script Commands folder

The Settings control shows the persisted canonical path and these setup steps:

1. create or choose a dedicated Script Commands folder;
2. in Raycast Settings, open **Extensions → Script Commands**;
3. add that exact folder; and
4. after installing a command, search Raycast and select **I found it** only
   when the command appears.

Saving a folder requires an absolute existing non-symlink directory. Reject a
path with symlinked components, a file, a missing directory, or a directory
outside the user's readable/writable access. Validate actual write and unlink
capability with a create-exclusive owner-only probe file whose fixed prefix is
Sayloom-specific; clean it up in `finally`. A cleanup failure is itself a
validation failure and is surfaced for manual remediation. Never create the
chosen directory implicitly.

Folder validity is observed passively on every Target overview refresh. Do not
read Raycast preferences, databases, indexes, caches, logs, or other private
data to discover its configured folders or indexed commands.

## Readiness and state model

Readiness is a projection, not one persisted status. The API returns each
dimension separately and the UI explains the next action.

### Passive observations

- **Application:** `available`, `missing`, or `changed_identity`. Available
  requires the exact selected location to remain launchable with the same
  bundle ID; current version is reported independently.
- **Dependencies:** `ready` or `missing`. Focused paste checks `cliclick` using
  the same resolution rules as execution. iTerm has no `cliclick` requirement.
- **Raycast folder:** `valid`, `missing`, `not_directory`, `symlink`, or
  `not_writable`.
- **Command file:** `not_installed`, `installed`, `stale`, or `collision`.
- **Raycast discovery:** `unconfirmed`, `confirmed`, or `stale_confirmation`.
- **Local verification:** `never_tested`, `awaiting_confirmation`,
  `verified`, `stale`, `rejected`, or `execution_failed`.

Passive checks never launch an application, invoke `cliclick`, request macOS
permission, execute a command, or inspect Raycast private state. In particular,
they cannot claim that Accessibility permission is granted.

### Fingerprint and invalidation

Compute the verification fingerprint from a versioned canonical encoding of:

- target ID and bundle ID;
- exact current application location and version;
- adapter key and version;
- complete expected generated-command SHA-256; and
- canonical Raycast Script Commands folder.

Any change to application version or location, adapter version, generated
command, or folder makes prior local verification stale. There is no time-based
expiry. Show the most recent successful confirmation time even when stale.

Raycast discovery uses the narrower current folder plus command-digest
fingerprint. A current installed file is **Command file installed**. Only a
matching explicit confirmation is **Raycast discovery confirmed**. Neither
fact implies the other or implies local verification.

### Test Target

`Test Target` is available only when the application, dependencies, and folder
are currently ready; command installation and Raycast discovery are not
prerequisites because the test isolates adapter delivery from Raycast indexing.

The action:

1. asks the user to prepare and focus the intended destination input;
2. creates a cryptographically random marker such as
   `Sayloom target test · 7K4P-2M9Q` containing no user text;
3. stores an `awaiting_confirmation` test with the current fingerprint;
4. writes the marker to an owner-only temporary payload file;
5. executes a temporary command composed from the same adapter fragment used
   by installed commands, with a bounded timeout and no shell interpolation of
   app metadata;
6. always removes temporary data and restores the clipboard; and
7. on execution success, asks **Did this exact marker appear in the intended
   input without being submitted?**

Process success alone never verifies the Target. **Yes** changes that exact
pending test to `confirmed`; **No** changes it to `rejected` and shows focus and
permission remediation. A recognized dependency, launch, timeout, or macOS
permission failure changes it to `execution_failed` with a safe code. A stale,
already-resolved, mismatched-target, or changed-fingerprint confirmation is
rejected with `409` and cannot verify a newer configuration.

The UI label **Verified on this Mac** means only that a user confirmed the
current fingerprint's marker. It does not promote a Generic integration, prove
Raycast discovery, guarantee every future destination focus, or claim that
text was submitted.

## HTTP API

Keep route handlers thin and return structured `409` operation failures with
`code`, `message`, and `retry_action`. Return enum values as strings and UTC
timestamps as ISO 8601. Do not return generated script bodies in ordinary
Target list responses; the old editable preview has no place in the new UI.

### Catalog and settings

- `GET /api/target-applications?refresh=false` returns validated catalog rows:
  opaque `catalog_id`, names, bundle ID, version, display location, icon URL,
  support label, and whether the exact app is already selected.
- `GET /api/target-applications/{catalog_id}/icon` returns only the bounded
  cached PNG or fallback icon after catalog-ID validation.
- `GET /api/target-settings` returns the folder value, validation state,
  remediation, and Raycast setup instructions.
- `PUT /api/target-settings` accepts only
  `{ "raycast_script_commands_folder": "..." }`, validates it completely,
  persists it, and returns the new observation.

### Targets

- `GET /api/targets` returns selected Targets and all separate readiness
  dimensions, support descriptor, available actions, last successful test
  time, safe errors, and orphan summaries.
- `POST /api/targets` accepts only `{ "catalog_id": "..." }`, revalidates the
  catalog row, stores metadata, and returns `201`. It never installs.
- `POST /api/targets/{id}/relink` accepts only a current `catalog_id` with the
  same bundle ID and replaces metadata from discovery.
- `POST /api/targets/{id}/install` requires `not_installed` and writes the
  expected command.
- `POST /api/targets/{id}/regenerate` requires `stale` and replaces only the
  recognized owned command.
- `POST /api/targets/{id}/uninstall` removes only the recognized owned command.
- `POST /api/targets/{id}/raycast-discovery` accepts
  `{ "confirmed": true }` only while the command is current and records
  **I found it**.
- `POST /api/targets/{id}/tests` starts Test Target and returns the test ID,
  marker, execution result, and confirmation prompt.
- `POST /api/targets/{id}/tests/{test_id}/confirmation` accepts
  `{ "appeared_without_submitting": true|false }` once.
- `DELETE /api/targets/{id}` removes a recognized command when possible, then
  deletes the Target, tests, discovery, and errors. It preserves an
  unrecognized collision and returns a warning rather than mutating it. A
  failure to remove a recognized owned command aborts database deletion so the
  operation can be retried without creating an accidental orphan.
- `DELETE /api/target-orphans/{orphan_id}` revalidates and removes exactly one
  recognized orphan after UI confirmation.

Install and Regenerate are separate commands even if they share an internal
atomic-write method. Calling an action in the wrong observed state returns
`409`; it does not silently reinterpret the request.

## Settings UI

Replace the authored-definition modal with three parts in the existing
Settings destination.

### Setup and overview

Place **Raycast Script Commands folder** before Targets. Show current validation
and concise Raycast setup instructions. A folder change requires confirmation
that commands are not moved and current discovery/verification will become
stale.

The Target grid starts with an empty state and **Add Target**. Each selected
Target card shows application icon/name, location, **Sayloom-tested** or
**Generic**, application availability, command file state, Raycast discovery,
local verification, and last successful test time. Do not collapse these into
one green/red badge.

Below the grid, show **Orphaned commands** only when recognized orphans exist.
Each row explains that no Target owns the file and offers a separately
confirmed **Remove orphaned command** action.

### Add Target

Open an accessible searchable dialog populated from the catalog. Search is
case-insensitive and updates a result count/status region. Rows show icon,
name, location, support label, and version. Already-selected exact
installations are disabled or labeled **Added**. Empty, loading, refresh, and
discovery-failure states remain usable and never reveal an editable manual
fallback.

Selecting a row opens a confirmation summary. **Add Target** persists the
selection but does not install a command. No identity or adapter field is an
input control.

### Target detail and actions

The detail view presents read-only application identity and separate sections
for **Integration support**, **Local readiness**, **Command file**, and
**Raycast discovery**. It offers only state-appropriate actions:

- Install when no command exists;
- Regenerate when the owned command is stale;
- Uninstall when an owned current or stale command exists;
- I found it when a current installed command awaits Raycast confirmation;
- Test Target when passive prerequisites are ready; and
- confirmed Remove Target at all times.

For a collision, disable write/removal actions and explain that the unrelated
entry must be moved manually. For a missing application, keep the Target and
command visible; offer reinstall guidance, **Use this installed copy** when
available, Uninstall, and Remove Target. Remove confirmation states that tests
and readiness history are deleted, that a recognized command is removed, and
that an unrecognized collision is preserved. Outgoing is always unchanged.

The Test Target confirmation dialog displays the exact marker and offers
**Yes, it appeared without submitting** and **No**. Closing or navigating away
leaves the attempt awaiting confirmation, not verified. Preserve existing
dirty-dialog, keyboard, narrow-layout, live-region, and focus-return
accessibility expectations where applicable.

## Safety and privacy invariants

1. Normal startup never migrates, seeds, resets, creates a folder, scans
   Raycast private state, or repairs files.
2. The migration resets only target-domain database rows and never touches
   external command files.
3. Catalog data comes from revalidated application bundles, never editable
   client fields.
4. Bundle ID alone selects an adapter; unknown IDs always use Generic focused
   paste.
5. Generated and test delivery share one adapter fragment and never submit.
6. Save/Add, Install, Regenerate, Uninstall, Test, discovery confirmation, and
   Remove are distinct explicit actions.
7. Filesystem writes use canonical validated directories, safe fixed
   filenames, no-follow checks, owner-only temporary files, fsync, and atomic
   replacement.
8. Sayloom never follows, overwrites, chmods, or removes an unrecognized file
   or symlink.
9. Orphans are recognized only by exact filename/ownership agreement and are
   removed only after explicit confirmation.
10. Command presence, Raycast discovery, integration support, dependency
    readiness, and local verification remain separate facts.
11. Only a user's confirmation of the current test fingerprint records
    **Verified on this Mac**; time alone never invalidates it.
12. Test markers are synthetic. Outgoing, clipboard contents, application text,
    Raycast private data, command output, and user destinations are never
    persisted in target tables or logs.
13. Removing or losing an application never silently deletes its Target or
    command.
14. Target operations never modify Outgoing or the fixed development commands.

## Failure behavior

Use stable safe categories with specific remediation:

- `application_missing` / `application_identity_changed`;
- `dependency_missing` for `cliclick`;
- `raycast_folder_missing`, `raycast_folder_invalid`, or
  `raycast_folder_not_writable`;
- `command_not_installed`, `command_stale`, or `command_collision`;
- `install_failed`, `regenerate_failed`, `uninstall_failed`, or
  `orphan_remove_failed`;
- `test_launch_failed`, `test_permission_denied`, `test_insertion_failed`, or
  `test_timeout`; and
- `test_confirmation_stale` or `test_already_resolved`.

Do not infer `test_permission_denied` from generic process failure; use it only
when the macOS tool reports a stable recognized denial. Otherwise report the
bounded generic insertion failure and recommend checking focus and macOS
Accessibility permission. Every failed mutation leaves the previous database
and unrelated filesystem state intact where atomicity permits.

## Staged tracer-bullet implementation

Each stage is independently reviewable and keeps portable tests synthetic.
Do not begin real-device acceptance until all portable stages pass.

### Stage 1: Verified registry fixtures

- In an isolated development state on the acceptance Mac, use read-only catalog
  metadata to capture Messages, native Amp, and Chrome Amp bundle IDs.
- Add registry constants and table-driven resolution tests for all six known
  integrations plus one unknown Generic ID.
- Stop if Messages or native Amp is absent; do not guess or borrow an ID.

**Exit:** Exact fixture IDs resolve to the intended support label and adapter;
an unknown ID resolves to Generic focused paste.

### Stage 2: Reset schema and persisted folder

- Add migration, models, stores, folder validation, schema revision, and admin
  seed removal.
- Prove upgrade resets old seeded/custom Targets while preserving unrelated
  data and leaving synthetic old command files untouched.

**Exit:** A migrated database has zero Targets, a persisted folder value, and
old recognized files are observable as orphans through an injected directory.

### Stage 3: Catalog-to-Target slice

- Implement bounded discovery, icon handling, catalog API, Add Target, missing
  app observation, and relink from metadata.
- Replace authored target request models; remove manual/preset UI paths.

**Exit:** A synthetic `.app` can be discovered, searched, selected, restarted,
and later shown missing without editable identity or adapter inputs.

### Stage 4: Versioned generation and lifecycle

- Extract registry-selected adapter fragments shared by normal and test
  generation.
- Implement command observation, Install, Regenerate, Uninstall, Remove, and
  collision-safe orphan scan/removal.
- Keep the fixed development installer and scripts unchanged.

**Exit:** Exact generated bytes install atomically; stale files regenerate;
owned files uninstall; collisions and symlinks remain byte-for-byte untouched;
Remove cascades history and follows its partial-failure contract.

### Stage 5: Readiness and Test Target

- Implement passive observations, fingerprints, pending confirmation, stale
  rejection, latest-success projection, and Raycast discovery confirmation.
- Exercise the same adapter fragment with a synthetic marker and bounded
  subprocess boundary.

**Exit:** Process success alone is not verified; current explicit confirmation
is verified; every fingerprint component independently makes it stale.

### Stage 6: Complete Settings interaction

- Finish folder setup, target cards/detail, searchable catalog, all lifecycle
  confirmations, missing/collision remediation, orphan rows, and responsive
  accessible states.
- Remove command preview, presets, manual definition fields, adapter selector,
  and Disable/Enable controls.

**Exit:** Browser tests and rendered desktop/narrow inspection cover empty,
Generic, tested, missing, stale, collision, invalid-folder, and orphan states
with no console or accessibility regressions.

### Stage 7: Controlled real-device acceptance

- Create or select a named isolated development state and use the controlled
  verify-then-restart workflow.
- Configure a dedicated disposable Raycast Script Commands folder for that
  state.
- Run the matrix below, record app and adapter versions, and clean up only the
  isolated recognized artifacts after explicit confirmation.

**Exit:** Every required row has evidence from the isolated development state.

## Verifiable acceptance criteria

### Portable domain and storage

- Migration from `0003` deletes four seeded plus synthetic custom target rows,
  creates no replacements, preserves prompt/settings fixtures, and does not
  touch a synthetic external command directory.
- The explicit admin migration persists the pre-upgrade effective Raycast
  folder, including a synthetic environment override; startup and Alembic
  schema inspection do not initialize or change it.
- A second seed creates no Targets. Startup against old schema reports setup
  required without migrating.
- Target, test, discovery, error, and removal cascades match this schema.
- Folder changes are durable across app restart and invalidate by fingerprint
  without moving or deleting commands.
- Every individual version, location, adapter version, generated digest, and
  folder change makes a confirmed test stale; elapsed time does not.

### Discovery and registry

- Fixtures cover valid direct and nested bundles, malformed/oversized plists,
  symlinked roots/bundles/plists/executables, path escape, background/helper
  apps, non-executable bundles, duplicate paths, duplicate bundle IDs at
  distinct locations, names/version fallbacks, icon failure, deterministic
  sorting, refresh, and write-time revalidation.
- Client-supplied metadata cannot alter a Target.
- All six verified known IDs resolve as Sayloom-tested with their required
  adapters; one unknown valid ID resolves as Generic focused paste.
- Moving or deleting a selected fixture leaves its Target visible and does not
  remove its command.

### Command and filesystem safety

- Generated commands are deterministic, shell-parseable, outgoing-only,
  multiline/UTF-8 safe, and contain no Return/Enter submission action.
- Focused paste releases modifiers and restores the exact text clipboard on
  success and every tested failure; iTerm uses `newline NO`.
- Folder probe cleanup, install, regenerate, uninstall, Remove, and orphan
  removal are tested for success and I/O failure.
- Regular-file collisions, symlinks, directories, malformed ownership,
  mismatched IDs, and mismatched filenames remain unmodified.
- Old recognized generated scripts become removable orphans; unrecognized
  files never appear as removable orphans.
- `tests/test_raycast.py` continues to prove exactly five fixed development
  commands and their separate installer behavior.

### API and UI

- Add Target persists but does not install. Install, Regenerate, Uninstall,
  discovery confirmation, Test, and Remove reject invalid state transitions.
- Test execution success returns an awaiting confirmation, **No** does not
  verify, **Yes** verifies only the unchanged fingerprint, duplicate/stale
  confirmations fail, and the last successful time remains visible.
- A Generic Target can be Verified on this Mac while still labeled Generic.
- Command file installed never renders as Raycast discovery confirmed without
  **I found it**.
- Remove deletes the Target and readiness history, removes a recognized owned
  command, preserves an unrecognized collision with a warning, and never
  changes Outgoing.
- Rendered desktop and narrow states are inspected for the empty catalog,
  search/results, target detail, pending marker confirmation, invalid folder,
  missing app, stale command, collision, and orphan cleanup. Keyboard focus,
  dialog cancellation, live status, labels, and touch-size behavior remain
  usable.

### Real-device matrix

For each application below, prepare and focus a non-sensitive disposable input,
run Test Target, verify the unique marker appears without submission, confirm
it in Sayloom, install the command, find it in Raycast, invoke it with synthetic
Outgoing, and verify insertion without submission:

| Application | Expected support | Adapter |
| --- | --- | --- |
| Messages | Sayloom-tested | Focused paste |
| Amp for macOS | Sayloom-tested | Focused paste |
| Amp Web App (Chrome) | Sayloom-tested | Focused paste |
| iTerm | Sayloom-tested | iTerm direct write |
| Supacode | Sayloom-tested | Focused paste |
| Visual Studio Code | Sayloom-tested | Focused paste |
| One unknown launchable app | Generic before and after verification | Focused paste |

Also collect explicit evidence that:

- missing `cliclick` blocks focused-paste readiness with installation guidance
  but does not block iTerm;
- denied Accessibility permission cannot become verified and gives actionable
  remediation without a false denial category;
- changing one expected command byte yields stale and Regenerate restores
  current state;
- an unrelated file and a symlink collision remain untouched;
- missing/non-directory/non-writable folder values are rejected without
  replacing the saved valid setting;
- removing or moving an app yields Application missing while retaining its
  Target and command;
- an old recognized no-definition command appears as Orphaned and is removed
  only after explicit confirmation; and
- command installation and **I found it** remain visibly distinct throughout.

Use only synthetic marker and Outgoing text. Record command results, UI/DOM
facts, inspected screenshots for representative states, and filesystem hashes
for non-mutation cases. The acceptance report must identify the isolated state
and dedicated folder in sanitized terms and state explicitly that the stable
application was not inspected or touched.

## Completion gate

The redesign is complete only when all portable checks pass, every rendered UI
state has been inspected, the exact Messages and native Amp bundle IDs are
captured from validated installed metadata, and every real-device matrix row
passes in the isolated development state. Missing hardware, application,
permission, or Raycast evidence leaves the corresponding criterion unverified;
it must not be replaced by a unit test or a success claim based on process exit.
