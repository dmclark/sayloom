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

This map is the canonical lifecycle inventory for `docs/`. When a document's
lifecycle changes, move both the file and its entry here. Historical Markdown
documents also keep a prominent warning at the top so direct links remain safe.
More specific status, scope, and authorization limits belong in the document
itself rather than being duplicated here.

## Current authorities

| Document | Authority |
| --- | --- |
| [Automatic correction prototype specification](automatic-correction-prototype-spec.md) | Focused definition of done for the automatic-correction prototype. |
| [Intended-meaning evidence collection contract](intended-meaning-evidence-collection-contract.md) | Confirmed interaction, privacy, participant-package, and evaluation-view boundary for prospective evidence collection; issue reconciliation is required before further implementation. |
| [Evaluation and automatic-correction prototype map](evaluation-mvp-map.md) | Current milestone order and separation of Cleanup and Smart evaluation. |
| [Automatic strategy evaluation harness](automatic-strategy-evaluation-harness.md) | Frozen harness contract for automatic-strategy evaluation; grants no operational authorization. |
| [Agent issue-tracker guidance](agents/issue-tracker.md), [triage labels](agents/triage-labels.md), [domain-doc guidance](agents/domain.md), and [workflow preferences](agents/workflow-preferences.md) | Current repository workflow guidance within each file's scope. |

## Active references

| Document | Use |
| --- | --- |
| [Development screenshot](images/sayloom-development.png) | Supporting image used by the root README, not an authority. |
| [Correction modes and fallback routing decision](adr/0001-correction-modes-and-fallback-routing.md) | Verified implementation and routing history. Its Conservative/Smart product boundary is superseded and must not authorize new work. |
| [Product implementation plan](product-implementation-plan.md) | Broader capability history pending reconciliation. Its separate Cleanup/Smart evidence path and permanent Conservative mode are superseded. |

## Draft collateral

| Document | Status |
| --- | --- |
| [Partner participant invitation](drafts/partner-participant-invitation.md) and [rendered PDF draft](drafts/partner-participant-invitation-draft.pdf) | Working draft with unresolved bracketed details; not participant-ready. |
| [Partner demonstration](drafts/partner-demo.html) | Illustrative demonstration collateral, not efficacy evidence or authorization. |

## Historical and superseded material

| Document | Superseded or completed by |
| --- | --- |
| [Correction benchmark pipeline](archive/correction-benchmark-pipeline.md) | Fixed eight-arm Smart scaffold; superseded for prototype acceptance by the automatic-strategy specification, map, and harness. |
| [Cleanup resilience and local evaluation design](archive/cleanup-resilience-evaluation.md) | Abandoned source-preserving corpus and benchmark path; the current evaluation model is defined by the product contract, prototype specification, evidence contract, and evaluation map. |
| [Cleanup benchmark protocol version 1](archive/cleanup-evaluation-benchmark-v1.json) | Historical machine-readable artifact from the abandoned source-preserving evaluation path. |
| [Cleanup benchmark protocol version 2](archive/cleanup-evaluation-benchmark-v2.json) | Historical machine-readable protocol from the retired benchmark and canary toolchain; non-operational. |
| [Cleanup evaluation corpus contract](archive/cleanup-evaluation-corpus-contract.md) | Historical contract retained for provenance after its benchmark consumers were removed; non-operational. |
| [Cleanup evaluation successor protocol](archive/cleanup-evaluation-successor-protocol.md) | Historical narrative protocol from the retired benchmark and canary toolchain; non-operational. |
| [Product roadmap](archive/roadmap.md) | `PRODUCT.md` and the current evaluation/prototype map. |
| [UX shape plan](archive/shape-plan.md) | `PRODUCT.md`; retained as historical UX evidence. |
| [Transcript fidelity specification](archive/transcript-fidelity-spec.md) | `PRODUCT.md`; retained as historical research evidence. |
| [First correction model and experiment matrix](archive/first-correction-model-and-experiment-matrix.md) | Automatic-strategy specification, map, and harness. |
| [Hosted AI delivery research](archive/hosted-ai-delivery-privacy-unit-economics.md) | Historical provider research based on the superseded single-model proof; revalidate all volatile facts before reuse. |
| [Handoff prompt template](archive/handoff-prompt-template.md) | Predates the GitHub/repository cutover and incorrectly assigns reusable project context to Mandrel. Use current repository guidance instead. |
| [Mandrel-to-GitHub migration plan](archive/mandrel-to-github-migration-plan.md) and [completion report](archive/mandrel-to-github-migration-report.md) | Completed migration record; current workflow authority is repository guidance and the agent documents above. |
