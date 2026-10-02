# ADR-0002: Personal Corrections ownership and state portability

- **Status:** Accepted
- **Date:** 2026-10-01
- **Scope:** Local Personal Corrections ownership, authorization, development-state portability, deletion, and sequencing
- **Product authority:** [`PRODUCT.md`](../../PRODUCT.md)
- **Implementation specification:** [Personal Corrections implementation specification](../personal-corrections-implementation-spec.md)

## Context

Sayloom needs live, user-controlled personalization for one local user before
there is a justified account, device-sync, or hosting boundary. The current
application also contains Evidence Collection runtime and participant-package
machinery built for a research direction that is no longer active. Those
surfaces are current implementation facts, not the target product direction.

Local development uses independently activated development states. Parallel
states must remain useful for debugging, so they cannot all point at one live
Personal Corrections database. At the same time, a newly created state should
not unexpectedly lose the user's approved Personal Corrections when an
eligible source state has been explicitly activated.

Development-state data currently lives under macOS Application Support. The
target neutral, cross-platform root is
`${XDG_DATA_HOME:-~/.local/share}/local-text/dev-states/`. Moving existing data
is a controlled administration operation; normal application startup must not
migrate schema or files.

## Decision

### Use Personal Corrections for live personalization

Personal Corrections serve live Smart personalization. Formal evaluation is
deferred. Renewed research or evaluation requires a new, explicitly approved
purpose and contract; ordinary Personal Corrections use does not authorize it.

The application uses the constant durable owner ID `local`. It has no account,
login, owner selector, or owner-management interface. Accounts remain deferred
until multi-user, device-sync, or hosting boundaries create a real need.

Sayloom saves a Personal Correction only after the user explicitly reviews and
approves an **Original → Intended** mapping. Saving authorizes that correction
for live use across later sessions. The authorization remains in force until
the correction is edited, disabled, or deleted. Ordinary editing, processing,
copying, delivery, dismissal, or inaction saves nothing.
Editing ends the prior mapping's authorization. The edited Original → Intended
mapping requires review and explicit save before it becomes authorized.

Product language says **save a Personal Correction**. It does not describe
this action as data collection.

API keys remain in protected shared configuration. They never enter a Personal
Corrections database or export. Keychain storage is deferred.

### Give each development state an independent snapshot

A future development state inherits a verified transactional snapshot of
Personal Corrections from the eligible source that was explicitly activated
for creation. Initialization verifies the inherited snapshot before activating
the new state.

If an eligible source exists and inheritance or verification fails,
initialization fails before activation. It must not silently create an empty
profile. If no eligible source exists, initialization succeeds with an empty
profile and reports that outcome explicitly.

Inheritance happens only at creation. There is no automatic post-creation
sync, and parallel states may diverge. Existing states are not backfilled.

Development-state data moves to
`${XDG_DATA_HOME:-~/.local/share}/local-text/dev-states/` through an explicit
migration command. Normal startup never performs this migration.

Deleting a Personal Correction in the UI affects only the current state. A
separate administration command may purge Personal Corrections across
registered states, but it must preview the affected registered states and
require confirmation before deletion. It does not search or mutate
unregistered state directories.

This decision governs live registered-state databases only. It does not decide
whether managed SQLite backups containing Personal Corrections are omitted,
purged, or retained, and neither deletion flow removes user-created exports.
The backup-deletion policy remains deferred; no implementation may claim
complete durable deletion until that policy is confirmed and verified.

### Retire Evidence Collection before adding Personal Corrections

Evidence Collection is superseded product direction. A later implementation
phase was required to remove it from the Workspace and runtime APIs, including
arming and lease logic, participant-package tooling, and dedicated tests. That
retirement is complete. Historical documents and Git history remain intact and
grant no authority to resume collection or evaluation.

Implementation proceeds in this order:

1. migrate the development-state root explicitly;
2. retire Evidence Collection runtime and tooling;
3. implement Personal Corrections; and
4. add verified new-state inheritance.

## Consequences

- The local product gets useful personalization without premature identity
  infrastructure or a research-evidence dependency.
- Explicit review and approval provide a clear durable authorization boundary.
- Development states remain isolated and can diverge intentionally after
  creation.
- State creation becomes fail-closed when promised inheritance cannot be
  verified.
- Current states receive no automatic correction backfill.
- UI deletion cannot imply deletion from other states; the cross-state purge
  boundary is explicit and administrative.
- Live-database deletion does not establish deletion from managed backups or
  user-created exports; complete durable deletion remains an unresolved claim.
- Evidence Collection code and operational paths are retired; historical
  records remain for provenance only.

## Alternatives considered

### One shared live Personal Corrections database

Rejected because parallel debugging states must remain independently mutable.
A shared database would couple tests and experiments across states and make
state-local deletion or rollback misleading.

### Automatically synchronize states

Rejected because post-creation synchronization would erase the isolation and
intentional divergence needed for debugging.

### Create an empty profile when inheritance fails

Rejected because silent loss of approved Personal Corrections would make a
newly activated state appear valid while changing personalized behavior.

### Add accounts now

Rejected because one local owner is sufficient and no current multi-user,
device-sync, or hosting boundary justifies account and login complexity.

## Implementation status

This ADR defines the accepted target contract and sequence. It does not claim
that the state-root migration, Evidence Collection retirement, Personal
Corrections, cross-state purge, or new-state inheritance is implemented. It
does not authorize migration, deletion, runtime operation, issue mutation, or
external changes.
