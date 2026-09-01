# Sayloom product roadmap

- **Status:** Confirmed roadmap; execution remains subject to the entry and authorization gates below
- **Audience:** Sayloom product, delivery, investigation, maintenance, and cross-project reviewers
- **Purpose:** Preserve one outcome-based roadmap, distinguish shipped work from proposals, and limit active work to one delivery milestone, one bounded investigation, and urgent maintenance
- **Shipped baseline:** `834d2616aa245a8f4abcd45224406afcd10f56e9`

## Authority and use

This document is the canonical source for Sayloom's current product outcomes,
implementation sequencing, work lanes, and delivery status. It does not replace
[`voiceitt-orchestration`](https://github.com/dmclark/voiceitt-orchestration),
which continues to govern shared architecture, repository/data/privacy
boundaries, and cross-project contracts. A conflict with those shared boundaries
is a blocker, not permission for Sayloom to override them.

Authority is ordered as follows:

1. Explicitly confirmed user decisions and applicable cross-project contracts.
2. This roadmap for Sayloom product direction and execution sequencing.
3. Shipped Sayloom commits for what currently exists.
4. The specifications and plans linked from the inventory below for their stated
   domains.
5. Historical, superseded, rejected, and uncommitted work as evidence only.

Dates, thread titles, and the latest proposal do not establish authority. A
documented feature is not shipped until it is present in shipped commits, and a
shipped feature is not accepted until its required evidence has passed.

The statuses used here are **Confirmed**, **Provisional**, **Unresolved**,
**Superseded**, and **Rejected**. **Parked** describes confirmed deferral, not a
sixth decision status.

## Canonical product outcome

**Confirmed:** Sayloom's primary long-term outcome is improved fidelity of text
derived from Voiceitt for a user with non-standard speech, while retaining a
source-agnostic text boundary. A faithful transcript and polished output are
different artifacts: transcript recovery precedes optional polishing, and
polished text never proves what was spoken.

**Confirmed:** The current shipped product remains a useful local-first,
source-preserving cleanup and outgoing-text workspace. Automatic cleanup may
normalize capitalization, punctuation, apostrophes, and whitespace and remove
leading fillers. Other lexical changes are rejected and fail open to Original.
Broader rewriting is not a current product mode.

**Confirmed:** Cleanup evaluation and transcript-fidelity research are separate
evidence domains. Cleanup cases cannot become transcript truth, correction
episodes, personalization, or training consent without a separately approved
contract.

## Plan inventory

| Plan or workstream | Authority and outcome | Current status | Evidence |
| --- | --- | --- | --- |
| Sayloom fresh start, Gates 0–2 | Original isolated runtime, daily Workspace/Raycast slice, and durable prompt/configuration core | **Confirmed — shipped; some real-Mac acceptance remains** | `f6b735e`, `60e4ea7`, `5282cf9`, `15f16e0` |
| Former fresh-start Gate 3 | Browser-local scratchpad plus resilience and sustained-use evidence | **Superseded in part** — scratchpad restoration and sustained-use gate are no longer required; bounded resilience checks remain in readiness | Confirmed decisions D018 and D023 |
| [Version-one shape](shape-plan.md) | Workspace, Cleanup/Vocabulary, Targets, inspectable failures, and visual direction | **Confirmed as UX evidence; partially shipped** — Workspace and Targets exist; Vocabulary and the Cleanup destination do not | `84dbf8c`, `4724fbc`, `61a1c39`, `68bd6c6`, `62987a6` |
| [Transcript-fidelity specification](transcript-fidelity-spec.md) | Fidelity-first product direction and bounded research design | **Confirmed direction; parked study** — no efficacy pilot has run | `7fe37bc` and the specification's readiness gate |
| [Cleanup resilience and evaluation](cleanup-resilience-evaluation.md) | Provider resilience, explicit cleanup corpus, benchmark, and canary | **Confirmed through Gates 1–6; Gates 7–8 deferred** | `9045482`, `1cf0525`, `7de0efd`, `5dd652e`, `487584e`, `834d261` |
| Semantic-output safety recovery stage | Deterministic source-preserving envelope and fail-open rejection | **Confirmed — shipped** | `0c1b2e8` |
| Cleanup-evaluation corpus lifecycle recovery stage | Explicit external store, consent, review, expiry, deletion, and export | **Confirmed — shipped** | `834d261` |
| “Stage 4” benchmark proposal | Implement an isolated offline benchmark runner | **Superseded as an implementation assignment** — protocol reconciliation must happen first | Confirmed decisions D017 and D022 |
| Public pilot-interest drafts | Non-processing public information and expression of interest | **Confirmed as the delivery milestone after readiness; prior drafts remain unshipped history** | Public-pilot planning thread; no shipped commit |
| Old prompt-program and parity branches | Expanded prompt lifecycle and predecessor-parity reconstruction | **Superseded or cancelled** — reference only; never resume or merge automatically | Archived work history |

## Shipped product inventory

### Confirmed shipped outcomes

- Isolated local development runtime and explicit administration.
- Editable Original, read-only Cleaned, fail-open publication, explicit outgoing
  selection, and CART-style input collapse/resizing.
- Immutable prompt versions and page-session prompt selection.
- Privacy-safe, inspectable cleanup and outgoing failures.
- Fixed and managed Raycast delivery commands and durable target definitions.
- Provider-neutral cleanup adapters, sequential routing, and explicit paid-route
  disclosure.
- Deterministic rejection of non-source-preserving cleanup output.
- An opt-in, separate cleanup-evaluation corpus lifecycle.

### Confirmed but incompletely accepted

- Real-Mac application availability, permissions, insertion, clipboard, and
  hotkey behavior.
- Normal Voiceitt/Chrome dictation through the shipped Workspace.
- Representative real-provider timeout and unavailable states.
- Controlled macOS restart and failure behavior.
- The remaining manual and unavailable accessibility checks.

### Confirmed absent or deferred

- Vocabulary profiles, aliases, activation, and evidence-tiered suggestions.
- A distinct Cleanup destination in the version-one information architecture.
- Transcript-recovery implementation or measured fidelity improvement.
- Recording review, re-recording, and neutral export.
- Expanded prompt lifecycle, named prompt families, and target-scoped prompts.
- Hosted cleanup, direct Voiceitt synchronization, and audio-assisted recovery.

## Outcome-based roadmap

### Outcome 1 — Dependable current local product

**Status: Confirmed — active delivery milestone.**

Establish credible acceptance of the shipped Workspace, cleanup, outgoing
publication, prompts, Targets, Raycast delivery, and controlled lifecycle.

Completion requires:

1. The portable automated baseline passes from the current shipped revision.
2. Real-Mac Raycast delivery inserts exactly the selected outgoing text into
   Amp, iTerm, Supacode, and VS Code without pressing Return.
3. Voiceitt/Chrome input reaches the normal Workspace path.
4. Representative provider success, rejection, timeout, and unavailable states
   display safe details and preserve Original fail-open.
5. Controlled restart and resilience checks pass without touching stable or
   predecessor resources.
6. Required keyboard, focus, labeling, dialog, resize/collapse, and viewport
   checks pass.
7. No unresolved urgent-maintenance defect remains.

**Confirmed:** A sustained-use period is not part of this completion gate.

### Outcome 2 — Evidence-based public interest surface

**Status: Confirmed — queued after Outcome 1.**

Shape and implement a non-processing public information and expression-of-
interest surface. Before implementation, approve its audience, claims, owner,
contact route, accessibility review, collection fields, access, retention,
deletion, follow-up responsibility, success threshold, and review period.

This outcome does not currently authorize public text processing, participant
enrollment, download distribution, hosted cleanup, or claims of fidelity or
provider effectiveness.

### Outcome 3 — Improve transcript fidelity

**Status: Confirmed product outcome; parked execution.**

Resume only through the intake and promotion policy. The shipped fidelity
specification remains the product/research authority, but implementation still
requires compatible ownership, consent, retention, deletion, withdrawal,
terminology, evaluation, and provider boundaries plus a newly approved finite
protocol. Cleanup benchmark evidence cannot complete this outcome.

## Three-lane work board

| Lane | Current item | Status | Exit condition |
| --- | --- | --- | --- |
| Delivery | Outcome 1 — dependable current local product | **Confirmed — active, with blocked prerequisites** | All readiness checks pass and no urgent blocker remains |
| Investigation | Cleanup benchmark protocol reconciliation | **Confirmed — ready, planning-only** | One evidence-backed disposition and proposed frozen successor protocol are presented for approval |
| Urgent maintenance | None | **Confirmed — empty** | Work enters only under the threshold below |

Urgent maintenance is limited to security, privacy, data-loss, stable-product
outage, or readiness-blocking defects. Other defects and usability improvements
remain parked. A qualifying defect receives one owner and one bounded task; it
does not create a fourth active lane.

## Active investigation contract

### Outcome

Determine whether cleanup benchmarking should evaluate only current
source-preserving cleanup, add an isolated review-required rewrite arm, or stop
because no bounded cleanup benchmark would answer a worthwhile product
question.

### Boundaries

- Stable cleanup remains source-preserving.
- Preserve the existing benchmark protocol as historical version 1.
- Do not implement a runner, use a private corpus, access credentials, call a
  provider, operate a benchmark, run a canary, or change stable routing.
- Assess product relevance, measurable outcomes, safety, privacy, cost,
  statistical validity, and overlap with transcript fidelity.

### Completion gate

The investigation is complete only when it:

1. Audits protocol version 1 against current shipped behavior.
2. Identifies obsolete assumptions, categories, arms, metrics, model references,
   budgets, and terminology.
3. Evaluates all three allowed dispositions against the same criteria.
4. Recommends exactly one disposition and explains why the others do not win.
5. Produces a proposed successor protocol with explicit entry, stopping,
   verification, and completion gates.
6. Preserves the superseded protocol and links its replacement.
7. Stops for explicit approval before implementation or operation.

## Actionable execution table

| Priority | Lane | Outcome | Task | Owner | Dependencies | Entry criteria | Verification | Completion gate | Status | Source |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Delivery | Dependable local delivery | In a local Supacode-managed Mac worktree and exact-worktree runner, verify Raycast delivery to Amp, iTerm, Supacode, and VS Code | Readiness owner | Safe isolated local environment; authorization to exercise integrations | Repository, branch, runner, and isolation verified; stable and predecessor resources excluded | Selected outgoing text reaches every target; no Return; clipboard, focus, application, permission, and command-collision behavior recorded | All target assertions pass, or one reproducible readiness blocker is isolated for maintenance | **Blocked — local environment and authorization required** | D005, D016; fresh-start Gate 1 |
| 2 | Delivery | Dependable dictation and cleanup | In the local Supacode environment, verify Voiceitt/Chrome input and representative provider states | Readiness owner | Priority 1 complete; dedicated credentials and explicit provider-call authorization where needed | Request cap and data boundary approved; isolated state ready | Exercise success, rejection, timeout, unavailable, safe details, and fail-open behavior | Every required state passes without leaking operating text | **Blocked — Priority 1 and authorization required** | D002, D016 |
| 3 | Delivery | Safe lifecycle | In the local Supacode environment, verify controlled restart and bounded resilience behavior | Readiness owner | Priority 2 complete; isolated development state | Backup, migration, restart, and stable-resource exclusion reviewed | Exercise start/restart, schema mismatch, migration failure, provider outage, and interruption paths | Lifecycle checks pass, or one reproducible readiness blocker is isolated | **Blocked — Priority 2 required** | Outcome 1 completion gate |
| 4 | Delivery | Accessible current product | In the local Supacode/browser environment, complete bounded keyboard and accessibility acceptance | Readiness owner | Priority 3 complete; representative states available | Required browser/manual tooling identified | Verify keyboard, focus, labels, dialogs, details, resize/collapse, narrow viewport, and available automation | No unresolved serious accessibility failure | **Blocked — Priority 3 required** | D016; shape and verification contracts |
| 1 | Investigation | Valid cleanup experiment | In an isolated Orb, reconcile the cleanup benchmark protocol without private data or provider traffic | Cleanup investigation owner | Shipped code/docs through `834d261`; D022 | Fixed read-only source set and comparison criteria recorded | Source-to-recommendation traceability, contradiction inventory, and complete successor gates | One recommendation and proposed protocol are presented for approval | **Ready — planning-only** | D017, D022 |
| After readiness | Delivery | Measure public interest | In an isolated Orb for planning, shape the non-processing public-interest surface before any implementation | Product owner | Outcome 1 complete | Claims, audience, data boundary, retention, and success threshold approved | Content, privacy, and accessibility review | One bounded implementation contract approved | **Queued** | D019 |

Every task has one accountable role. Work remains forbidden until its entry
criteria are satisfied. The role may delegate execution, but accountability
does not split between threads.

## Intake and promotion policy

### Capture without commitment

Record each new feature, issue, investigation, or tool with its source, desired
outcome, available evidence, and reason it matters. Capture does not authorize
implementation or create an active task.

### Classify and reconcile

Classify the item as product delivery, bounded investigation, urgent
maintenance, capability/process adoption, parking-lot idea, superseded work, or
rejected work. Check it against the canonical outcome, confirmed decisions,
privacy boundaries, shipped behavior, and existing items before proposing work.

### Define before promotion

Promotion requires:

- one observable outcome and one accountable owner;
- authoritative requirement or decision;
- dependencies, blockers, and explicit entry criteria;
- an independently executable verification method and completion gate;
- a task small enough for one focused execution thread;
- an explicit local Supacode or isolated Orb environment choice; and
- a prohibition on implementation until prerequisites are satisfied.

### Enforce work-in-progress limits

At most one delivery milestone and one bounded investigation may be active.
Urgent maintenance is admitted only under the defined threshold. A new item may
enter an empty lane, explicitly replace an active item, remain parked, or be
rejected. Replaced work is marked paused or superseded rather than silently
discarded.

### Handle discoveries during work

- Include work required for the current outcome only when it remains within the
  owning module and contract.
- Park unrelated improvements.
- Route qualifying defects to urgent maintenance.
- Stop and return to planning when evidence invalidates the current contract.
- Mark completion only after verification and the completion gate pass.

## Capability-adoption register

**Status: Confirmed process; Mandrel register created; inventory unverified.**

Track skills, plugins, and tools separately from the product board. Each entry
records capability and source, intended trigger, accountable owner, installed
version/status, last verified use, missing workflow integration, next bounded
exercise, evidence link, review date, and one disposition: **adopted**,
**exercise**, or **retire**.

Known candidates for the first inventory include Impeccable, frontend-design,
accessibility, webapp-testing, user-research, focused-thread management,
Supacode worktree management, Mandrel tools, and the local usage plugin. Their
current installation state must be verified rather than inferred from an older
thread.

**Confirmed cadence:** review on the first Monday of each month at 9:00 AM in
the user's browser timezone and at relevant delivery and verification gates.
**Unresolved:** no recurring reminder exists until its exact schedule receives
separate write authorization.

The durable register is `ref:sayloom-capability-adoption` in Mandrel project
`voiceitt-bridge` (`c875b2af-9020-41b7-9595-d70221603464`).

## Durable memory references

**Status: Confirmed — written and verified.** These focused records live in the
Mandrel `voiceitt-bridge` project; Sayloom does not use a separate Mandrel
project.

| Stable reference | Record status |
| --- | --- |
| `ref:sayloom-roadmap` | Confirmed; committed on the topic branch and not merged to `main` |
| `ref:sayloom-decision-fidelity-first` | Confirmed; outcome too early |
| `ref:sayloom-decision-cleanup-boundary` | Confirmed and validated |
| `ref:sayloom-decision-delivery-sequence` | Confirmed; in progress |
| `ref:sayloom-decision-work-policy` | Confirmed; in progress |
| `ref:sayloom-superseded-history` | Superseded and rejected history |
| `ref:sayloom-unresolved` | Unresolved blockers and future decisions |
| `ref:sayloom-active-board` | Confirmed current board |
| `ref:sayloom-parking-lot` | Confirmed parked work |
| `ref:sayloom-investigation-gates` | Confirmed planning-only gate |
| `ref:sayloom-capability-adoption` | Confirmed process; inventory unverified |
| `ref:sayloom-next-readiness-task` | Blocked verification task |

## Parking lot

The following items are **Confirmed — parked**, not active commitments:

- transcript-fidelity protocol and study;
- Vocabulary profiles, aliases, activation, and evidence-tiered suggestions;
- Cleanup destination and information architecture;
- benchmark-runner implementation, private benchmark operation, and paid
  provider traffic pending protocol approval;
- non-shadow 10/25/100 canary and stable-provider promotion;
- broader rewrite product mode;
- recording review, re-recording, and neutral export;
- expanded prompt lifecycle and multiple named prompt families;
- direct Voiceitt synchronization and audio-assisted research;
- hosted cleanup and hosted destination management; and
- non-urgent UI density, Cleaned-tray, and usability refinements.

Rejected and superseded work remains in linked history rather than this parking
lot.

## Rejected and superseded history

- **Superseded:** Original-to-Cleaned differences as transcript replacement
  truth; they may be advisory evidence only.
- **Superseded:** Broad automatic grammar, tone, or wording rewriting as current
  behavior; source-preserving cleanup is authoritative.
- **Superseded:** “Stage 4” as an approved runner implementation assignment;
  protocol reconciliation comes first.
- **Superseded:** Browser-local scratchpad restoration and sustained-use proof as
  readiness requirements.
- **Rejected:** Passive history, implicit learning, and ordinary edits as
  consent.
- **Rejected:** An editable third final-text field and a Workspace target
  chooser/send surface.
- **Rejected:** Unsupported audience or accessibility positioning invented by a
  draft rather than confirmed by the user.

## Recommended next task

**Confirmed recommendation:** Verify real-Mac Raycast delivery to Amp, iTerm,
Supacode, and VS Code as a verification-only task owned by the Readiness owner.
Use a local Supacode-managed worktree and exact-worktree runner. Stop if safe
isolation from stable, predecessor, or unrelated user integrations cannot be
established. If a defect is found, reproduce it with privacy-safe evidence,
classify it under the urgent-maintenance threshold, and stop before
implementation.

### Ready-to-paste top-level thread prompt

```text
Verify the Sayloom real-Mac Raycast delivery lane as one bounded,
verification-only task.

Repository: dmclark/sayloom
Authority: docs/roadmap.md, especially confirmed decisions D005, D016, D025,
D026, and D030.
Start from current origin/main at or after
834d2616aa245a8f4abcd45224406afcd10f56e9.

Before doing anything:
1. Select or create the appropriate dedicated Supacode-managed verification
   worktree.
2. Attach an Amp runner whose actual cwd is that exact worktree.
3. Verify repository, remote, branch, HEAD, recent commits, and expected status.
4. Use isolated development state only where required.
5. Do not inspect, modify, start, stop, or reuse the stable or predecessor
   application, services, ports, databases, logs, configuration, or integrations.
6. Stop if safe isolation from existing user integrations cannot be established.

Outcome:
Produce real-Mac evidence that Sayloom's selected outgoing text can be delivered
through the supported Raycast commands to Amp, iTerm, Supacode, and VS Code.

Verify:
- each destination receives exactly the selected outgoing text;
- neither fixed nor managed commands press Return;
- Original versus Cleaned selection is respected;
- unavailable application and permission states are reported conservatively;
- clipboard restoration and focus behavior match the current contract;
- command installation/regeneration does not create collisions or alter
  unrelated Raycast commands; and
- no operating text, credentials, private paths, or provider payloads enter
  Git, logs, screenshots, or the final report.

Do not edit code during this verification task. If a defect is found:
- reproduce it once with privacy-safe evidence;
- classify whether it meets the urgent-maintenance threshold;
- stop and report the smallest bounded implementation task; and
- do not broaden into unrelated fixes.

Completion:
Return one concise evidence table with each destination and assertion marked
passed, failed, skipped, or unavailable; exact blockers; sanitized artifact
references; and a readiness recommendation.

Do not commit, push, merge, deploy, write Mandrel, create another thread, or
change shared state without separate explicit authorization.
```

## Authorization boundaries

This roadmap does not itself authorize implementation, private-data use,
provider traffic, collection, publication, deployment, commits, pushes, merges,
Mandrel writes, recurring schedules, or stable/shared-state changes. Each such
action requires its applicable entry criteria and explicit authorization.
