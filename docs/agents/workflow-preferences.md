# Project workflow preferences

This file refines the user's global workflow defaults for this repository. It
cannot weaken system/developer instructions, applicable repository instructions,
or explicit instructions in the current request.

## Overrides

- For local code changes, use a Supacode-managed topic worktree and attach the
  Amp runner to that exact worktree before editing. Keep the primary `main`
  checkout clean for integration.
- Prefer an Amp orb for isolated work. Read-only research, planning, review, and
  documentation-only changes may run in an orb when their inputs are available
  there.
- Track issues as Mandrel tasks in the existing `voiceitt-bridge` project. Do
  not create a separate project for Sayloom.
- **Prepared tracker cutover — not active:** after the migration pilot and
  final manifest are approved and an authority cutoff is recorded, track
  actionable work in GitHub Issues for `dmclark/sayloom`, use the private
  user-owned **Sayloom** Project for workflow state, and keep Mandrel unchanged
  as read-only provenance. Before that cutoff, GitHub pilot Issues are
  migration-validation artifacts only; do not dual-write active work.
- Default implementation verification to affected checks, including
  `uv run ruff check .` and the relevant `uv run pytest` coverage. Reserve a
  full integration baseline for the designated integration owner when needed.
- For validated runtime changes, use the controlled `scripts/dev.py restart`
  workflow rather than hot reload. Never inspect, modify, start, stop, or
  otherwise interact with the stable application or its state and integrations.
- Keep changes uncommitted until the user has reviewed the working-tree diff
  and explicitly authorized a commit. After authorization, commit only the
  reviewed changes. Require separate explicit authorization before integrating
  changes into `main`. Preserve the repository's restrictions on private data,
  credentials, operating state, and shared or external actions.
