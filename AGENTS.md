# Repository Guidance

This repository is private and local-first. Commit project context deliberately;
keep runtime and secret material outside Git.

- Keep operating data, API keys, dictated or cleaned text, databases, and logs outside Git.
- Never add credentials, private machine paths, or copied legacy implementation.
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
- Checkpoint after each work phase and before exceeding 20 tool invocations since the last
  checkpoint. Count each tool call issued by the current agent, including calls inside a parallel
  batch, but not a delegated agent's internal calls. Report confirmed findings, changes, verification
  state, blockers, and remaining work; reset the count after reporting. Do not rely on unavailable
  model-request or total-token counters.
- After final verification, stop scope expansion. If new evidence requires an in-scope correction,
  make the targeted change and rerun affected checks. Complete any explicitly authorized delivery
  steps and report what remains uncommitted, unpushed, unmerged, or undeployed.
- Keep investigation, implementation, fixes, and verification for one deliverable in the same
  correctly bound thread and checkout. A phase change alone does not require a new thread.
  Use a separate focused thread for an independently owned deliverable, a required different
  execution environment, or an explicit user request. Defer unrelated review findings and follow-up
  changes rather than expanding the current deliverable.
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
  start acceptance verification while implementation or baseline repair remains unresolved. For UI
  verification, use synthetic data in an isolated runtime and prefer DOM inspection, browser logs,
  targeted tests, and accessibility snapshots. Reserve screenshots for genuinely visual concerns
  such as layout, styling, clipping, responsive behavior, and modals; capture only the relevant
  components and viewports, including representative important states and breakpoints. When
  applicable, verify desktop and 390px widths. Inspect every retained screenshot, reuse unchanged
  captures, and do not propose unsolicited visual alternatives. Ask before inspecting more than
  three screenshots in one task. Report how many were inspected and what each verified, assert
  behavior separately, and clean up temporary captures and other run-created resources.
- Stop and report before broadening a fix when it breaks unrelated fixtures, leaves its owning
  module, or its affected suite still fails after two targeted correction attempts.
- Resolve ambiguous completion from the current owner and `git status`/`git diff`, not a duplicate
  cleanup thread. Validate test or browser commands before rerunning them, and do not repeat an
  unchanged failing command or poll unchanged status without new evidence or a meaningful wait.

## Local worktree workflow

- Worktrees are per independently changing topic, not per thread. Code changes require an
  appropriate topic branch. Keep the primary `main` worktree clean for integration and its
  configured runtime; local-state diagnosis there is read-only. Integrate only after review and
  explicit authorization.
- Local development uses a Supacode-managed worktree served by the canonical shared Amp runner
  `runner-1`. Preserve manager-owned locks; never force-unlock or manually remove managed worktrees.
- An explicitly requested orb may implement code in its own isolated checkout without a local
  Supacode worktree or runner. Read-only research, planning, review, and documentation-only changes
  may run in an orb when all required inputs are available there and no local or uncommitted state
  is needed.
- Create or select a named development state only when the task needs isolated application runtime or database data.
- Before local code-changing work:
  1. Create or select the topic's dedicated Supacode worktree and canonicalize its path.
  2. Confirm that exact path is registered with Supacode and Git, retains its manager-owned lock,
     and is served by `runner-1`.
  3. Verify repository, branch, HEAD, tracking, recent commits, and status.
  4. Use an implementation thread created directly on `runner-1` with `working_directory` exactly
     equal to that verified canonical path. Reuse the current thread only if it is already bound
     correctly; otherwise create a correctly bound continuation.
  5. Keep all task reads, edits, commands, and verification in that worktree.
  Fail closed if any registration or binding check cannot be verified.
- Creating or focusing a worktree, or setting a shell command's `workdir`, does not reattach a
  thread, executor, or Changes panel. Existing threads cannot be rebound retroactively. Never use
  the old Supacode-tab, `amp threads continue`, or `/new` choreography as a substitute for binding.

## Agent skills

### Issue tracker

Issues are tracked in GitHub for `dmclark/sayloom`. See
`docs/agents/issue-tracker.md`.

### Triage labels

Triage uses the default canonical label vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

Domain documentation uses a single-context layout. See `docs/agents/domain.md`.

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

Project-specific workflow preferences are in
`docs/agents/workflow-preferences.md`.
<!-- personal-workflow-project:end -->
