# Repository Guidance

This repository is private and local-first. Commit project context deliberately;
keep runtime and secret material outside Git.

- Keep operating data, API keys, dictated or cleaned text, databases, and logs outside Git.
- Never add credentials, private machine paths, or copied legacy implementation.
- Use neutral technical identifiers such as `local_text`; keep them decoupled from the display brand.
- Normal application startup must not run database migrations.
- Keep features and abstractions limited to the current requirement. Repository-wide documentation
  cleanup requires explicit approval.

## Task-specific guidance

- Before local code changes, read `docs/agents/local-worktree-workflow.md` for
  Supacode registration and exact `runner-1` thread binding. These gates do not apply to orbs.
- Before UI verification, read `docs/agents/ui-verification.md` for isolated data,
  viewport coverage, and screenshot limits.
- For issue tracking, read `docs/agents/issue-tracker.md` (GitHub `dmclark/sayloom`).
- For triage, read `docs/agents/triage-labels.md` for the canonical label vocabulary.
- For domain documentation, read `docs/agents/domain.md` for the single-context layout.

## Correction examples and benchmarks

Before proposing correction examples or benchmarks, read Product Purpose and
Success in `PRODUCT.md` and explain how the cases exercise intended-text
recovery. Distinguish owner-confirmed misunderstandings, synthetic cases, and
preservation controls. Treat spelling-only cases as limited coverage and current
implementation limits as implementation facts, not the product goal. Discussion
evidence does not authorize evaluation reuse.

## Development-time conversational capture aid

When asked to configure, enable, pause, or use conversational correction capture,
read `docs/agents/conversational-correction-capture.md`. This is an opt-in
development aid independent of Sayloom's application. This guidance does not
enable collection or authorize access to historical private repair records.

## Temporary recognition-repair record

When discussing recognition repairs, read
`.amp/in/artifacts/confirmed-recognition-repairs.md`. Keep owner-confirmed repairs
separate from inferred interpretations; ask the owner to confirm uncertain
wording before recording it, and obtain applicable write authorization. Treat
examples as discussion evidence, not automatic replacement rules, Personal
Corrections, or evaluation authorization. Keep the record outside Git.

The ignored record does not travel with branches, worktrees, or orbs. If it is
missing, request an explicit transfer from the source checkout or thread before
relying on it; do not reconstruct confirmed repairs from guesses. This pointer
does not authorize inspecting private operating data.

<!-- personal-workflow-project:start -->
## Personal workflow overrides

Before choosing an execution environment, editing, verifying, or delivering changes,
read `docs/agents/workflow-preferences.md` for project-specific defaults.
<!-- personal-workflow-project:end -->
