# Repository Guidance

This repository is local-first and public-safe from its first commit.

- Keep operating data, API keys, dictated or cleaned text, databases, and logs outside Git.
- Never add real user content, credentials, private machine paths, or copied legacy implementation.
- Never inspect, modify, start, stop, or otherwise interact with the existing stable application or any of its checkouts, services, ports, configuration, databases, logs, or integrations.
- Use neutral technical identifiers such as `local_text`; keep them decoupled from the display brand.
- Normal application startup must not run database migrations.
- For validated coding changes, use the controlled verify-then-restart workflow rather than hot reload.
- Keep features and abstractions limited to the current requirement.
- Keep agent work to one bounded deliverable: clarify material ambiguity before editing; inspect exact
  anchors with narrow, capped output; diagnose failures before retrying; avoid delegating small
  changes or work on a shared dirty worktree; and do not replay unchanged context. Separate work
  into investigate/reproduce, implement plus affected checks, and, for substantial work, a distinct
  full integration-verification phase after implementation is resolved.
- Hand off to a new focused thread before further implementation when the principal deliverable or
  phase changes. Defer unrelated review findings and follow-up changes to a separate focused thread
  rather than expanding the current deliverable.
  Start each fresh thread with a compact, self-contained prompt containing only confirmed decisions,
  current state, evidence, the exact next deliverable, and necessary references; never import or
  replay a long parent transcript. This is a reviewable checkpoint, not automatic token enforcement.
- Give each changing worktree one implementation owner at a time. Delegate coding only for an
  independent workstream with disjoint files and explicit ownership; the same owner resolves
  cleanup, revert, and final verification unless a handoff explicitly transfers that responsibility.
  Request one coherent implementation pass followed by one verification pass; if verification fails,
  diagnose the new evidence, make a targeted correction, and then rerun instead of entering an
  open-ended implementation and verification loop.
- Default implementation verification to affected checks. One integration owner runs any requested
  full baseline once after constituent work is resolved; never overlap broad verification owners or
  start acceptance verification while implementation or baseline repair remains unresolved.
- Stop and report before broadening a fix when it breaks unrelated fixtures, leaves its owning
  module, or its affected suite still fails after two targeted correction attempts.
- Resolve ambiguous completion from the current owner and `git status`/`git diff`, not a duplicate
  cleanup thread. Validate test or browser commands before rerunning them, and do not repeat an
  unchanged failing command or poll unchanged status without new evidence or a meaningful wait.

## Mandrel project

- All durable memory for this repository belongs to the existing Mandrel project
  `voiceitt-bridge` (`c875b2af-9020-41b7-9595-d70221603464`).
- Sayloom is part of the Voiceitt Bridge product memory. It is not a separate Mandrel project.
- Before the first Mandrel read or write in a thread, verify that `voiceitt-bridge` is active and
  switch only if needed. Reuse that confirmed selection unless the connection changes or there is
  evidence that the active project changed; do not repeatedly reload project-selection guidance.
- Never create or suggest a separate Sayloom Mandrel project.

## Local worktree workflow

- Worktrees are per independently changing topic, not per Amp thread or Orb. Code changes must occur on an appropriate topic branch rather than the protected primary `main` checkout.
- Local development uses a Supacode-managed worktree with the runner attached to that exact worktree. An explicitly requested Orb may work in its own isolated checkout and does not require a corresponding local Supacode worktree or runner.
- Read-only research, planning, and review may run in an orb when all required inputs are available there; documentation-only changes may also run in an orb when they do not depend on local or uncommitted state.
- Create or select a named development state only when the task needs isolated application runtime or database data.
- Keep the primary `main` worktree clean for integration and its configured runtime, not feature editing; local-state diagnosis there is read-only. Preserve manager-owned locks; never force-unlock or manually remove managed worktrees. Integrate to `main` only after review and explicit authorization.
- Before local code-changing work: (1) create or select the dedicated Supacode worktree; (2) start an Amp runner whose actual process cwd is that exact worktree (or start interactive `amp` there); (3) create or continue the implementation thread on that exact runner; (4) verify its repository, branch, recent commits, and expected status; (5) only then edit files. Create or select a named development state as part of this only when the task needs isolated application runtime or database data.
- Creating a worktree does not move or reattach the current Amp thread, executor, or Changes panel. Never edit a new worktree from a thread or runner attached to the parent, `main`, or another directory, even when shell commands can pass that worktree as their working directory.
