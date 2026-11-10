---
name: grill-me-with-docs
description: >-
  Orchestrates a confirmed design interview followed by authorized technical
  documentation. Use only when the user explicitly invokes grill-me-with-docs
  and wants a README, decision record, spec, runbook, migration guide, handoff,
  or Mandrel reference after decisions are settled.
---

# Grill Me With Docs

Run a two-gate workflow: first settle decisions with `grill-me`, then create
documentation from the confirmed result. Never collapse the gates.

## Gate 1: interview

Immediately load `grill-me` with the skill tool and follow it. Do not imitate a
partial interview from memory, ask documentation questions prematurely, or
begin implementation.

Continue the bounded interview across turns until `grill-me` presents its final
decision ledger, current contract, deferred questions, risks, and readiness
recommendation. Preserve the ledger's stable IDs and contradiction history.

Then stop and ask for explicit confirmation in this form:

> Confirm this decision ledger and current contract as the source for
> documentation? Please answer **confirm**, or list corrections by decision ID.

Do not load a writing skill or draft documentation until the user confirms. If
the user changes a decision, return to `grill-me`, update or supersede the
affected entries, recompute readiness, and ask for confirmation again.

## Gate 2: documentation

After confirmation, load `technical-writing` with the skill tool and follow it.
Use the confirmed current contract and ledger as the authoritative source.

If either item is unclear, ask the user to select:

1. **Document type** — README, design / architecture decision, spec, runbook,
   migration guide, handoff, or Mandrel reference.
2. **Exact destination** — chat draft, absolute file path, repository plus path,
   or exact Mandrel project and intended reference operation.

Selecting a prospective destination is not write authorization. Before any
durable write, restate the document type and exact target and ask:

> Write the confirmed documentation to `<exact target>` now?

Proceed only after an explicit yes to that exact target. A general request to
“document this” authorizes neither repository nor Mandrel mutation.

## Documentation rules

- Write normative statements only from confirmed accepted decisions and settled
  facts.
- Mark unresolved content inline as **Proposed**, **Deferred**, **Assumption**,
  or **Unverified**, including the relevant ledger ID.
- Preserve superseded decisions only where history matters, clearly identifying
  the replacement. Do not present rejected options as current behavior.
- Summarize the ledger and rationale; never paste the whole transcript.
- Preserve privacy and omit secrets, unnecessary personal data, and irrelevant
  internal discussion.
- Use concise Markdown, Diátaxis-appropriate structure, exact technical values,
  useful lists or tables, and copyable commands with prerequisites and expected
  results.

For a Mandrel destination, load `writing-mandrel-memory` before the authorized
write and follow the applicable Mandrel project-selection workflow. Never create
a disposable record for validation.

## Hard stop

This orchestration never begins implementation and never commits, pushes,
merges, deploys, or writes to a repository or Mandrel destination without a
separate explicit request and exact authorized target. Documentation approval
does not authorize any of those adjacent actions.
