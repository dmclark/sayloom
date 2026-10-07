# Project workflow preferences

This file refines the user's global workflow defaults for this repository. It
cannot weaken system/developer instructions, applicable repository instructions,
or explicit instructions in the current request.

## Overrides

- For local code changes, follow the root guidance's **Local worktree workflow**,
  including its fail-closed Supacode/Git registration gate, exact `runner-1`
  directory and new-thread binding, and single-worktree boundary. A shell
  command workdir or existing thread is not a substitute for that binding;
  use a correctly bound continuation. Keep the primary `main` checkout clean
  for integration.
- Prefer an Amp orb for isolated work. Read-only research, planning, review, and
  documentation-only changes may run in an orb when their inputs are available
  there.
- Track actionable work in GitHub Issues for the private `dmclark/sayloom`
  repository and use the private user-owned **Sayloom** Project for workflow
  state. Repository documents and ADRs own durable current knowledge and
  decisions.
- For implementation changes, affected checks usually include
  `uv run ruff check .` and relevant `uv run pytest` coverage. Follow the root
  guidance for test frequency and scope-appropriate verification.
- For validated runtime changes, use the controlled `scripts/dev.py restart`
  workflow rather than hot reload.
- Keep changes uncommitted unless a commit is explicitly requested or clearly
  required by repository policy. Commit only reviewed, in-scope changes. Require
  separate explicit authorization before integrating changes into `main`.
  Preserve the repository's restrictions on private data, credentials,
  operating state, and shared or external actions.
