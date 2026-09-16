# Sayloom handoff prompt template

> **Historical workflow template.** This file predates the completed
> GitHub/repository cutover and incorrectly assigns reusable project context to
> Mandrel. Do not use it for current handoffs; follow current repository guidance
> and the [documentation map](../README.md).

Use this template when one bounded Sayloom deliverable moves to another Amp
thread or executor. [`PRODUCT.md`](../../PRODUCT.md) is the product authority; a
handoff references it but does not reproduce it.

## Generate a concise handoff

Replace the placeholders, then give this prompt to Amp:

```markdown
Create a concise Amp handoff for: <ONE NEXT DELIVERABLE>.

Authoritative product source: `PRODUCT.md`.
Read it, but include only the product clauses directly relevant to this
deliverable. Distinguish verified current implementation from target product
behavior.

Use the repository's current Git and executor state rather than guessing it.
Include:

- repository, branch, worktree, and executor;
- base/head commits and expected working-tree status;
- completed work that must not be repeated;
- one next deliverable with observable exit criteria;
- relevant `PRODUCT.md` headings or confirmed decision IDs;
- relevant Mandrel anchors, when they exist;
- deferred work;
- checks already run and checks required next; and
- prohibitions on unrelated changes, pushing, merging, deploying, or changing
  shared state without authorization.

Keep the handoff under 400 words. Do not reproduce `PRODUCT.md`, an interview
transcript, superseded product narratives, or unrelated decisions. If the next
executor cannot access unpushed or dirty state, say which workspace, runner,
patch, bundle, or authorized sync it needs instead of implying that branch name
alone transfers the work.
```

## Handoff structure

```markdown
# Handoff: <next deliverable>

Continue Sayloom in `<repository or absolute path>`.

## Existing state
- Branch: `<branch>` — continue it; do not create another branch.
- Worktree/executor: `<path and local runner or orb>`
- Base/head: `<full hashes>`
- Prior commits: `<hash — subject>`
- Status: `<clean or exact expected changes>`
- Product authority: `PRODUCT.md`, especially `<relevant headings or IDs>`
- Mandrel anchors: `<ref:slug or record IDs, or none>`

## Completed
- <Only completed work that affects the next task; do not repeat it.>

## Next scope
- <One principal deliverable.>
- Exit criteria: <observable result and required check.>

## Product constraints
- <Two to five relevant constraints from PRODUCT.md.>
- Current behavior: <verified implementation fact.>
- Target behavior: <confirmed product requirement.>

## Deferred
- <Explicitly excluded work.>

## Verification
- Already run: `<commands and decisive results>`
- Run next: `<commands or checks>`

## Prohibitions
- Do not repeat completed work or broaden the deliverable.
- Do not push, merge, deploy, rewrite history, or change shared state without
  explicit authorization.
- First verify repository, branch, commits, and clean or expected status.
- If required state is unavailable, stop and request the correct workspace,
  runner, patch, bundle, or authorized sync.

Load applicable repository guidance and recall the listed Mandrel anchors before
editing. Complete and verify only the next scope, then report the result.
```

## Selection rule

Include only product clauses that could change the implementation or acceptance
of the next deliverable. For example, correction-mode work may need the core
text model, correction modes, review behavior, and user-control constraints. It
does not need the hosted credential strategy or target-integration deferral.

The handoff carries immediate execution state. Durable product direction stays
in `PRODUCT.md`, reusable project context stays in Mandrel, and implemented
state stays in focused commits.
