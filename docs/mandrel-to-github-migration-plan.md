# Mandrel-to-GitHub migration implementation plan

- **Status:** Approved for implementation; not yet executed
- **Repository:** `dmclark/sayloom`
- **Approver:** `dmclark`
- **Audience:** Migration operator and repository maintainer

## Purpose

This plan replaces Mandrel as Sayloom's active tracker and project-memory
system. GitHub Issues will hold actionable work, one private GitHub Project will
provide the workflow view, and versioned repository documents and ADRs will
hold durable current knowledge and decisions.

Mandrel remains intact as a permanent, read-only provenance archive. It must
not remain a second active system after cutover. This plan documents the later
migration procedure; it does not authorize or perform the migration.

## Authority after cutover

| Information | Authoritative location |
| --- | --- |
| Actionable Sayloom work | GitHub Issues in `dmclark/sayloom` |
| Workflow state | Private `dmclark` GitHub Project named **Sayloom** |
| Durable current facts and processes | Existing or new repository documents |
| Qualifying current decisions | `docs/adr/NNNN-slug.md` |
| Legacy, stale, ambiguous, or cross-product provenance | Read-only Mandrel project `voiceitt-bridge` |

The shared Mandrel project identifier is
`c875b2af-9020-41b7-9595-d70221603464`. Genuine cross-product Voiceitt
relationships remain there and may be referenced without being duplicated.
No new Sayloom task, context, decision, or session may be written to Mandrel
after cutover.

## Safety boundaries

- Never modify or delete a Mandrel record.
- Never bulk-export the interleaved `voiceitt-bridge` project into GitHub or
  Git.
- Never migrate a record based on semantic similarity alone.
- Do not copy credentials, dictated or generated operating text, runtime
  databases or logs, private machine paths, copied predecessor implementation,
  unrelated Voiceitt material, or unnecessary private content.
- Execute only rows explicitly approved by `dmclark`.
- Do not commit the detailed working manifest, raw exports, or review notes.
- Obtain separate authorization for GitHub mutations, repository changes,
  artifact removal, commits, pushes, merges, or other shared-state actions when
  the migration is executed.

## Private migration workspace

Before inventory, the operator must set `SAYLOOM_MIGRATION_WORKDIR` to an
absolute, private directory outside every Git checkout. The directory must be
owned by and accessible only to the current user. Store the detailed manifest,
raw source material, and review notes only there.

The operator must verify all of the following before continuing:

- the variable is set and resolves outside the Sayloom checkout;
- the directory is not tracked by any Git repository;
- its permissions prevent access by other users;
- backup, synchronization, and retention behavior are appropriate for the
  private source material.

Repository documents refer to this location only as
`$SAYLOOM_MIGRATION_WORKDIR`; they must not record its machine-specific value.

## Candidate admission

A Mandrel record enters the candidate manifest only when it has positive
Sayloom evidence. Accepted evidence, in descending order of strength, is:

1. an exact `ref:sayloom-*` anchor listed in `docs/roadmap.md`;
2. an explicit Sayloom tag or name, or a link to `dmclark/sayloom`;
3. a graph neighbor of an already confirmed record that has been manually
   reviewed and accepted.

Graph proximity and semantic similarity are discovery aids, not admission
evidence. Ambiguous, unrelated, or private records remain only in Mandrel.

## Working manifest

Inventory produces a private, row-oriented manifest under
`$SAYLOOM_MIGRATION_WORKDIR`. Each row must record:

- stable Mandrel source identifier and record type;
- concise private synopsis, without unnecessary copied source text;
- qualifying evidence and any graph-neighbor review;
- proposed disposition and rationale;
- proposed GitHub or repository destination;
- proposed Issue status, priority, routing label, and outcome when applicable;
- pilot membership;
- approval state and approver;
- created destination identifier or URL;
- execution and validation state;
- error or rollback notes.

The manifest is the execution journal. The operator must write a destination
back to its row immediately after creating an artifact. A resumed run must skip
rows with validated destinations and inspect uncertain rows rather than create
duplicates.

## Disposition rules

Assign exactly one disposition to every approved candidate:

| Record meaning | Disposition |
| --- | --- |
| Open or current action | Create a GitHub Issue and add it to the Sayloom Project |
| Durable current fact or process | Update the existing canonical document, or create a focused document when none exists |
| Current consequential decision | Create or update an ADR only when the repository's ADR threshold is met |
| Completed execution | Link to an existing PR, commit, release, or canonical document |
| Stale or superseded history | Retain in Mandrel with an archive-only manifest disposition |
| Unrelated, private, or ambiguous material | Retain in Mandrel and exclude from migration |

A completed-work record may become a closed Issue only when no adequate Git
artifact exists, the history remains important for current discoverability,
and `dmclark` approves the exception on that manifest row.

Prefer updating a document that already owns a durable fact or process. Use
`docs/adr/NNNN-slug.md` only for a current decision that is hard to reverse,
surprising without context, and the result of a genuine trade-off. Create
`docs/adr/` lazily if the first approved ADR requires it. Do not create a
document for stale or superseded knowledge.

Every migrated artifact must identify Mandrel as its legacy source, include a
stable non-secret source ID, and state the qualifying Sayloom evidence. Summarize
verified content instead of copying a full legacy body when a summary is
sufficient.

## GitHub workflow configuration

Create one private user-owned GitHub Project:

- **Owner:** `dmclark`
- **Name:** `Sayloom`

Configure these fields:

| Field | Values |
| --- | --- |
| Status | Inbox, Ready, In Progress, Blocked, Done |
| Priority | P0, P1, P2, P3 |
| Outcome | Shipped, Won't Fix, Superseded, Duplicate |

Configure these views:

- **Triage:** open Issues in Inbox;
- **Delivery:** Ready, In Progress, and Blocked Issues;
- **Roadmap:** open Issues grouped by Priority;
- **Archive:** Done Issues grouped by Outcome.

Create only these routing labels initially:

- `needs-triage`
- `needs-info`
- `ready-for-agent`
- `ready-for-human`
- `wontfix`

Pull requests are excluded from triage. Project fields represent workflow
state; labels represent routing signals.

Configure automation to add open Issues from `dmclark/sayloom` to the Project,
excluding pull requests; set Status to Done when an Issue closes; and restore
an appropriate open status when it reopens, defaulting to Inbox if its prior
state cannot be recovered. Do not automate priority, routing labels, or
Outcome.

## Issue mapping

Do not mechanically translate Mandrel status or priority. The approved manifest
row must assign each imported open action explicitly:

| Meaning | GitHub mapping |
| --- | --- |
| Unclear or unclassified | Status: Inbox; label: `needs-triage` |
| Awaiting information | Status: Inbox; label: `needs-info` |
| Ready for automation | Status: Ready; label: `ready-for-agent` |
| Ready for manual work | Status: Ready; label: `ready-for-human` |
| Active | Status: In Progress; assignee when known |
| Blocked | Status: Blocked; blocker stated in the Issue |

Assign P0–P3 only when the manifest contains an explicit justification;
otherwise leave Priority blank. Outcome remains a human judgment and is not
inferred automatically.

## Migration procedure

Each phase has an approval gate. Do not advance until its exit criteria are
met.

### Phase 1: Inventory

1. Establish and verify `$SAYLOOM_MIGRATION_WORKDIR`.
2. Record a source snapshot time in ISO 8601 UTC format.
3. Discover candidates using the positive-evidence rules.
4. Manually review proposed graph neighbors.
5. Give every candidate a proposed disposition and destination.
6. Preserve rejected candidates and their rationale in the private manifest.

**Exit:** The candidate set is explainable, every admitted row has positive
evidence, and no bulk export or Mandrel mutation occurred.

### Phase 2: Review and pilot approval

1. Review every candidate classification and proposed mapping.
2. Select 5–10 pilot records, including when available:
   - an open action;
   - a noncanonical durable fact or decision;
   - an archive-only record;
   - a cross-product or graph-neighbor boundary case.
3. Have `dmclark` approve the pilot manifest and provisional full manifest.

**Exit:** Every pilot row and its expected destination are explicitly approved.

### Phase 3: Prepare

1. Verify GitHub permissions and private visibility.
2. Create the labels and private Sayloom Project only with separate mutation
   authorization.
3. Configure fields, views, and limited lifecycle automation.
4. Prepare, but do not yet activate, changes to:
   - `AGENTS.md`;
   - `docs/agents/issue-tracker.md`;
   - `docs/agents/workflow-preferences.md`.
5. Prepare any approved durable document or ADR changes.

**Exit:** The target workflow is privately configured and the authority-policy
changes are reviewable but have not declared cutover.

### Phase 4: Pilot

1. Create artifacts for approved pilot rows only.
2. Record each destination immediately in the working manifest.
3. Verify provenance, content, labels, fields, links, and private visibility.
4. Confirm that archive-only and cross-product cases remained in Mandrel.
5. Incorporate corrections into the selection, disposition, and mapping rules.
6. Have `dmclark` approve every pilot disposition and the revised rules.

**Exit:** The pilot contains no false-positive Sayloom records, every artifact
is correct and traceable, and the approver accepts the revised rules.

### Phase 5: Final approval and cutover

1. Apply the approved pilot corrections to the provisional full manifest.
2. Have `dmclark` approve the final full manifest.
3. Reconcile Mandrel activity since the source snapshot.
4. Record one authority cutoff as an ISO 8601 UTC timestamp in the private
   manifest and the repository policy-change PR description.
5. Stop all new Sayloom writes to Mandrel. Queue new work briefly rather than
   dual-write during cutover.
6. Apply the three prepared repository policy changes so they consistently
   name GitHub Issues, the private Sayloom Project, repository docs/ADRs, and
   read-only Mandrel in their new roles.
7. Process the remaining approved manifest rows, recording every destination.

**Exit:** No post-snapshot activity is missing, no dual-writing occurred, and
all approved rows have been processed or explicitly stopped with an error.

### Phase 6: Validate and close

Validate the complete approved set, not a sample:

- every approved row has exactly one disposition;
- every created artifact maps to one approved source row;
- every destination link resolves and contains the required provenance;
- Issue labels, fields, status, assignee, and visibility match the manifest;
- durable knowledge is canonical in its intended document or ADR;
- no unapproved, ambiguous, unrelated, or private Voiceitt content was copied;
- `AGENTS.md`, `docs/agents/issue-tracker.md`, and
  `docs/agents/workflow-preferences.md` consistently identify the new
  authority;
- Mandrel records remain unchanged;
- no rollback threshold was crossed.

Create the sanitized completion report at
`docs/mandrel-to-github-migration-report.md`. It may contain policy, aggregate
counts, accepted mappings, destination links, exceptions, validation results,
and source IDs only when they reveal no private or cross-product information.
Record the UTC cutoff timestamp in the report. Do not include the detailed
manifest or raw Mandrel content.

**Exit:** `dmclark` explicitly approves the full reconciliation and sanitized
report. GitHub and Git are then permanently authoritative for Sayloom, while
Mandrel remains read-only.

## Stop and rollback

Stop the pilot or cutover immediately for:

- any private or unrelated Voiceitt material entering GitHub or Git;
- any loss of source provenance;
- incorrect Project visibility or access;
- a systematic classification problem affecting more than one record.

A single-record metadata or content mistake may be corrected and re-reviewed.
Do not broaden the migration while diagnosing it.

Until final validation is approved, rollback remains available because Mandrel
is untouched. Halt imports, queue new work, and identify all created artifacts
from the working manifest. Mark them migration-invalid or remove them only
after explicit approval. Revert the authority-policy change and resume Mandrel
writes only if necessary. Revise the dry-run manifest and repeat its approval
gate before retrying.

After final validation approval, do not resume Mandrel writes. Correct later
errors in GitHub or Git while preserving the legacy source as read-only
provenance.

## Implementation-time decisions

The following values remain intentionally deferred until inventory or
execution supplies the necessary evidence:

- exact candidate count and pilot membership;
- manual versus scripted creation, based on approved volume;
- exact destination document and ADR for each durable record;
- source snapshot and authority-cutoff timestamps;
- whether any failed GitHub artifact should be corrected, marked invalid, or
  removed.

These decisions do not weaken the approval, privacy, provenance, or rollback
requirements above.
