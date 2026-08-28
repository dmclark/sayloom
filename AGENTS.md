# Repository Guidance

This repository is local-first and public-safe from its first commit.

- Keep operating data, API keys, dictated or cleaned text, databases, and logs outside Git.
- Never add real user content, credentials, private machine paths, or copied legacy implementation.
- Never inspect, modify, start, stop, or otherwise interact with the existing stable application or any of its checkouts, services, ports, configuration, databases, logs, or integrations, except for the target-command boundary below.
- For explicit target-command work, agents may read target status through the stable application's Targets surface or API, inspect the configured Raycast Script Commands directory, and use the Targets install, regenerate, or remove operations. This permits only the target-definition reads and target-local operation-error updates performed by those endpoints. Create only an absent expected target path; overwrite or remove only an artifact recognized as Sayloom-owned by its target ID and generated filename. Never execute target commands, alter collisions or unrelated entries, or access other stable application state. Obtain explicit approval immediately before each live mutation. `scripts/dev.py activate` repoints only the fixed development aliases; use Targets regeneration, not activation, to restore a managed target command.
- Use neutral technical identifiers such as `local_text`; keep them decoupled from the display brand.
- Normal application startup must not run database migrations.
- For validated coding changes, use the controlled verify-then-restart workflow rather than hot reload.
- Keep features and abstractions limited to the current requirement.

## Local worktree workflow

- Worktrees are per independently changing topic, not per Amp thread or Orb. Code changes must occur on an appropriate topic branch rather than the protected primary `main` checkout.
- Local development uses a Supacode-managed worktree with the runner attached to that exact worktree. An explicitly requested Orb may work in its own isolated checkout and does not require a corresponding local Supacode worktree or runner.
- Read-only research, planning, and review may run in an orb when all required inputs are available there; documentation-only changes may also run in an orb when they do not depend on local or uncommitted state.
- Create or select a named development state only when the task needs isolated application runtime or database data.
- Keep the primary `main` worktree clean for integration and its configured runtime, not feature editing; local-state diagnosis there is read-only. Preserve manager-owned locks; never force-unlock or manually remove managed worktrees. Integrate to `main` only after review and explicit authorization.
- Before local code-changing work: (1) create or select the dedicated Supacode worktree; (2) start an Amp runner whose actual process cwd is that exact worktree (or start interactive `amp` there); (3) create or continue the implementation thread on that exact runner; (4) verify its repository, branch, recent commits, and expected status; (5) only then edit files. Create or select a named development state as part of this only when the task needs isolated application runtime or database data.
- Creating a worktree does not move or reattach the current Amp thread, executor, or Changes panel. Never edit a new worktree from a thread or runner attached to the parent, `main`, or another directory, even when shell commands can pass that worktree as their working directory.
