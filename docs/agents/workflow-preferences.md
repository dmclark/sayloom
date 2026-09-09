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
- Track actionable work in GitHub Issues for the private `dmclark/sayloom`
  repository and use the private user-owned **Sayloom** Project for workflow
  state. Repository documents and ADRs own durable current knowledge and
  decisions.
- Keep Mandrel project `voiceitt-bridge` unchanged as read-only legacy
  provenance. Do not create a separate Sayloom Mandrel project or dual-write to
  Mandrel.
- For implementation changes, affected checks usually include
  `uv run ruff check .` and relevant `uv run pytest` coverage. Follow the root
  guidance for test frequency and scope-appropriate verification.
- For validated runtime changes, use the controlled `scripts/dev.py restart`
  workflow rather than hot reload. Never inspect, modify, start, stop, or
  otherwise interact with the stable application or its state and integrations.
- Keep changes uncommitted unless a commit is explicitly requested or clearly
  required by repository policy. Commit only reviewed, in-scope changes. Require
  separate explicit authorization before integrating changes into `main`.
  Preserve the repository's restrictions on private data, credentials,
  operating state, and shared or external actions.
