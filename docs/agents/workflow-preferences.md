# Project workflow preferences

This file refines the user's global workflow defaults for this repository. It
cannot weaken system/developer instructions, applicable repository instructions,
or explicit instructions in the current request.

## Overrides

- Prefer an Amp orb for isolated work. Agents may edit code in an orb's isolated
  checkout without a separate request for an orb or a local Supacode worktree.
  Use an appropriate topic branch for code changes. Tasks that depend on local
  or uncommitted state require access to that state; an orb does not inherit it.
- In an orb, put agent-created temporary files inside the project checkout's
  `.amp/` directory, rather than `/tmp`, the home directory, or a sibling directory.
  Use `.amp/in/tmp/` for scratch scripts, debug output, and intermediate captures;
  reserve `.amp/in/artifacts/` for files the user should review. Both are ignored
  by Git. Link reviewable files using their actual absolute paths inside the
  checkout, and remove disposable scratch files when finished.
- For local work, use the user's centralized temporary-file folder shared across
  worktrees, rather than creating a temporary-file folder in each worktree. The
  checkout-local `.amp/` rule above applies only to orbs. Obtain the centralized
  path from local configuration or the user before writing local temporary files.
- Before local code changes, follow `local-worktree-workflow.md`. Its Supacode
  and `runner-1` gates apply only to local work, not to orbs.
- Track actionable work in GitHub Issues for the private `dmclark/sayloom`
  repository and use the private user-owned **Sayloom** Project for workflow
  state. Repository documents and ADRs own durable current knowledge and
  decisions.
- For implementation changes, affected checks usually include
  `uv run ruff check .` and relevant `uv run pytest` coverage. Documentation-only
  changes normally need diff and content checks, not application tests.
- Use desktop-only scope for normal UI development, testing, mockups, and design
  reviews. Defer mobile layouts, narrow-viewport checks, and mobile interaction
  testing to the separate later mobile UI stage in
  [the Wayfinder map](https://github.com/dmclark/sayloom/issues/159).
  Start mobile work only when that stage is explicitly selected.
- Run each affected test group after the final relevant edit; rerun only when
  later changes could affect it. Assign any requested full integration baseline
  to one owner after implementation and baseline repairs are resolved.
- Stop and report before broadening a fix when it breaks unrelated fixtures,
  leaves its owning module, or its affected suite still fails after two targeted
  correction attempts.
- For validated runtime changes, use the controlled `scripts/dev.py restart`
  workflow rather than hot reload.
- Keep changes uncommitted unless a commit is explicitly requested or clearly
  required by repository policy. Commit only reviewed, in-scope changes. Require
  separate explicit authorization before integrating changes into `main`.
