# Documentation map

Use this page to determine a file's documentation lifecycle before relying on
it. A document can be current without being product authority: its authority is
limited to the scope stated in that document.

[`PRODUCT.md`](../PRODUCT.md) is the sole authority for product vision,
positioning, roadmap direction, audience, and scope. The root-level
[`CONTEXT.md`](../CONTEXT.md) defines current domain vocabulary,
[`README.md`](../README.md) describes the current implementation and development
workflow, and [`DESIGN.md`](../DESIGN.md) contains the repository's design-system
reference. GitHub Issues own actionable work, and the private **Sayloom** Project
owns workflow state.

## Lifecycle convention

- **Current authority** defines an active contract, plan, protocol, or process
  within its stated scope.
- **Active reference** describes current implementation, workflow, or research
  input but does not set product direction or authorize operations.
- **Draft** is unfinished collateral and must not be used as an approved
  commitment or invitation.
- **Historical** is retained for provenance only. It may describe the state at
  a named revision, but it does not authorize current work.

Current documents remain directly under `docs/` or in a purpose-specific
current directory such as `docs/agents/`. Unfinished collateral lives under
`docs/drafts/`, and superseded or completed material lives under
`docs/archive/`. Do not add lifecycle suffixes such as `-current` or
`-superseded` to filenames; moving a file between these directories is the
lifecycle transition.

One historical exception is the retired Evidence Collection contract: it remains
at its existing path rather than under `docs/archive/` so established links keep
their provenance. Its prominent warning states that no live tooling remains and
that it grants no current authority.

This map is the canonical lifecycle inventory for `docs/`. When a document's
lifecycle changes, move both the file and its entry here. Historical Markdown
documents also keep a prominent warning at the top so direct links remain safe.
More specific status, scope, and authorization limits belong in the document
itself rather than being duplicated here.

## Current authorities

| Document | Authority |
| --- | --- |
| [Personal Corrections ownership and state portability decision](adr/0002-personal-corrections-ownership-and-state-portability.md) | Accepted local ownership, durable authorization, development-state portability, deletion, and implementation-sequence contract. |
| [Personal Corrections execution guide](personal-corrections-execution-guide.md) | Current four-phase execution order: state-root migration, Evidence Collection retirement, Personal Corrections, then new-state inheritance. |
| [Personal Corrections implementation specification](personal-corrections-implementation-spec.md) | Confirmed target storage, review and approval, Smart retrieval, live-database deletion, export, migration, and inheritance boundary; managed-backup deletion remains unresolved and implementation remains pending. |
| [Product implementation plan](product-implementation-plan.md) | Approved broader capability plan reconciled to the four-phase Personal Corrections sequence. |
| [Raycast Target Management redesign implementation specification](raycast-target-management-implementation-spec.md) | Review-ready implementation contract for installed-application discovery, managed target lifecycle, readiness, safety, migration, and isolated real-device acceptance. |
| [Agent issue-tracker guidance](agents/issue-tracker.md), [triage labels](agents/triage-labels.md), [domain-doc guidance](agents/domain.md), and [workflow preferences](agents/workflow-preferences.md) | Current repository workflow guidance within each file's scope. |

## Active references

| Document | Use |
| --- | --- |
| [Development screenshot](images/sayloom-development.png) | Supporting image used by the root README, not an authority. |
| [Correction modes and fallback routing decision](adr/0001-correction-modes-and-fallback-routing.md) | Verified implementation and routing history. Its Conservative/Smart product boundary is superseded and must not authorize new work. |
| [Automatic correction prototype specification](automatic-correction-prototype-spec.md), [evaluation map](evaluation-mvp-map.md), and [automatic strategy evaluation harness](automatic-strategy-evaluation-harness.md) | Deferred research references only. Renewed research requires a new approved evaluation purpose and contract; these files grant no current collection, provider, evaluation, or pilot authority. |

## Draft collateral

| Document | Status |
| --- | --- |
| [Partner participant invitation](drafts/partner-participant-invitation.md) and [rendered PDF draft](drafts/partner-participant-invitation-draft.pdf) | Working draft with unresolved bracketed details; not participant-ready. |
| [Partner demonstration](drafts/partner-demo.html) | Illustrative demonstration collateral, not efficacy evidence or authorization. |

## Historical and superseded material

| Document | Superseded or completed by |
| --- | --- |
| [Intended-meaning evidence collection contract](intended-meaning-evidence-collection-contract.md) | ADR-0002 and the live Personal Corrections direction. Retired historical contract retained at its current path; no live collection or participant-package tooling remains, and it grants no collection or evaluation authority. |
| [Correction benchmark pipeline](archive/correction-benchmark-pipeline.md) | Fixed eight-arm Smart scaffold; superseded for prototype acceptance by the automatic-strategy specification, map, and harness. |
| [Cleanup resilience and local evaluation design](archive/cleanup-resilience-evaluation.md) | Abandoned source-preserving corpus and benchmark path. No current evaluation model is authorized; renewed research requires a new approved purpose and contract. |
| [Cleanup benchmark protocol version 1](archive/cleanup-evaluation-benchmark-v1.json) | Historical machine-readable artifact from the abandoned source-preserving evaluation path. |
| [Cleanup benchmark protocol version 2](archive/cleanup-evaluation-benchmark-v2.json) | Historical machine-readable protocol from the retired benchmark and canary toolchain; non-operational. |
| [Cleanup evaluation corpus contract](archive/cleanup-evaluation-corpus-contract.md) | Historical contract retained for provenance after its benchmark consumers were removed; non-operational. |
| [Cleanup evaluation successor protocol](archive/cleanup-evaluation-successor-protocol.md) | Historical narrative protocol from the retired benchmark and canary toolchain; non-operational. |
| [Product roadmap](archive/roadmap.md) | `PRODUCT.md`, ADR-0002, and the current Personal Corrections execution guide. |
| [UX shape plan](archive/shape-plan.md) | `PRODUCT.md`; retained as historical UX evidence. |
| [Transcript fidelity specification](archive/transcript-fidelity-spec.md) | `PRODUCT.md`; retained as historical research evidence. |
| [First correction model and experiment matrix](archive/first-correction-model-and-experiment-matrix.md) | Automatic-strategy specification, map, and harness. |
| [Hosted AI delivery research](archive/hosted-ai-delivery-privacy-unit-economics.md) | Historical provider research based on the superseded single-model proof; revalidate all volatile facts before reuse. |
| [Handoff prompt template](archive/handoff-prompt-template.md) | Predates the GitHub/repository cutover and incorrectly assigns reusable project context to Mandrel. Use current repository guidance instead. |
| [Mandrel-to-GitHub migration plan](archive/mandrel-to-github-migration-plan.md) and [completion report](archive/mandrel-to-github-migration-report.md) | Completed migration record; current workflow authority is repository guidance and the agent documents above. |
