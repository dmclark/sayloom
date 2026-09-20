# Repository Guidance

This repository is private and local-first. Commit project context deliberately;
keep runtime and secret material outside Git.

- Keep operating data, API keys, dictated or cleaned text, databases, and logs outside Git.
- Never add credentials, private machine paths, or copied legacy implementation.
- Never inspect, modify, start, stop, or otherwise interact with the existing stable application or any of its checkouts, services, ports, configuration, databases, logs, or integrations.
- Use neutral technical identifiers such as `local_text`; keep them decoupled from the display brand.
- Normal application startup must not run database migrations.
- For validated coding changes, use the controlled verify-then-restart workflow rather than hot reload.
- Keep features and abstractions limited to the current requirement. Repository-wide documentation
  cleanup requires explicit approval.
- Keep agent work to one bounded deliverable: clarify material ambiguity before editing; inspect exact
  anchors with narrow output; cap every command and tool result, and summarize or slice rather than
  dumping generated, bundled, minified, or other large files. Diagnose failures before retrying;
  avoid delegating small changes or work on a shared dirty worktree; and do not replay unchanged
  context. Separate work into investigate/reproduce, implement plus affected checks, and, for
  substantial work, a distinct full integration-verification phase after implementation is resolved.
- Checkpoint and report before the hard stop of 25 model requests or 1.5M total tokens; never cross
  whichever limit comes first. Once final verification is declared, stop work.
- Hand off to a new focused thread before further implementation when the principal deliverable or
  phase changes. Defer unrelated review findings and follow-up changes to a separate focused thread
  rather than expanding the current deliverable.
  Start each fresh thread with a compact, self-contained prompt containing only confirmed decisions,
  current state, evidence, the exact next deliverable, and necessary references; never import or
  replay a long parent transcript.
- Give each changing worktree one implementation owner at a time. Delegate coding only for an
  independent workstream with disjoint files and explicit ownership; the same owner resolves
  cleanup, revert, and final verification unless a handoff explicitly transfers that responsibility.
  Request one coherent implementation pass followed by one verification pass; if verification fails,
  diagnose the new evidence, make a targeted correction, and then rerun instead of entering an
  open-ended implementation and verification loop.
- Match verification to the change scope; documentation-only changes normally need diff and content
  checks, not application tests. Run each affected test group once after the final relevant edit, and
  rerun it only after a subsequent change could affect it. One integration owner runs any requested
  full baseline once after constituent work is resolved; never overlap broad verification owners or
  start acceptance verification while implementation or baseline repair remains unresolved.
- Stop and report before broadening a fix when it breaks unrelated fixtures, leaves its owning
  module, or its affected suite still fails after two targeted correction attempts.
- Resolve ambiguous completion from the current owner and `git status`/`git diff`, not a duplicate
  cleanup thread. Validate test or browser commands before rerunning them, and do not repeat an
  unchanged failing command or poll unchanged status without new evidence or a meaningful wait.

## Local worktree workflow

- Worktrees are per independently changing topic, not per Amp thread or Orb. Code changes must occur on an appropriate topic branch rather than the protected primary `main` checkout.
- Local development uses a Supacode-managed worktree. A connected runner with `any-directory` capability may operate in any worktree that runner lists; its process cwd need not equal the selected worktree. An explicitly requested Orb may work in its own isolated checkout and does not require a corresponding local Supacode worktree or runner.
- Read-only research, planning, and review may run in an orb when all required inputs are available there; documentation-only changes may also run in an orb when they do not depend on local or uncommitted state.
- Create or select a named development state only when the task needs isolated application runtime or database data.
- Keep the primary `main` worktree clean for integration and its configured runtime, not feature editing; local-state diagnosis there is read-only. Preserve manager-owned locks; never force-unlock or manually remove managed worktrees. Integrate to `main` only after review and explicit authorization.
- Before local code-changing work: (1) create or select the dedicated Supacode worktree; (2) confirm it is registered with Supacode and Git, retains its manager-owned lock, and is listed by the connected runner; (3) verify repository, branch, HEAD, tracking, recent commits, and status; (4) set every filesystem tool's `workdir` to that worktree; (5) keep all reads, edits, commands, and verification there. Create or select a named development state as part of this only when the task needs isolated application runtime or database data.
- Creating a worktree does not move or reattach the current Amp thread, executor, or Changes panel. Treat the selected worktree as the task boundary and do not mix operations across worktrees.

## Agent skills

### Issue tracker

Issues are tracked in GitHub for `dmclark/sayloom`. See
`docs/agents/issue-tracker.md`.

### Triage labels

Triage uses the default canonical label vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

Domain documentation uses a single-context layout. See `docs/agents/domain.md`.

<!-- personal-workflow-project:start -->
## Personal workflow overrides

Project-specific workflow preferences are in
`docs/agents/workflow-preferences.md`.
<!-- personal-workflow-project:end -->
