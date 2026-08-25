# Repository Guidance

This repository is local-first and public-safe from its first commit.

- Keep operating data, API keys, dictated or cleaned text, databases, and logs outside Git.
- Never add real user content, credentials, private machine paths, or copied legacy implementation.
- Never inspect, modify, start, stop, or otherwise interact with the existing stable application or any of its checkouts, services, ports, configuration, databases, logs, or integrations.
- Use neutral technical identifiers such as `local_text`; keep them decoupled from the display brand.
- Normal application startup must not run database migrations.
- For validated coding changes, use the controlled verify-then-restart workflow rather than hot reload.
- Keep features and abstractions limited to the current requirement.

## Local worktree workflow

- Keep the primary `main` worktree clean for integration and its configured runtime, not feature editing. Local-state diagnosis there is read-only.
- Before code-changing work: (1) create or select the dedicated Supacode worktree and named development state; (2) start an Amp runner whose actual process cwd is that exact worktree (or start interactive `amp` there); (3) create or continue the implementation thread on that exact runner; (4) verify its repository, branch, recent commits, and expected status; (5) only then edit files.
- Creating a worktree does not move or reattach the current Amp thread, executor, or Changes panel. Never edit a new worktree from a thread or runner attached to the parent, `main`, or another directory, even when shell commands can pass that worktree as their working directory.
- Read-only coordination may remain on the primary runner, but hand code-changing implementation off to the runner attached to the exact worktree.
- Preserve manager-owned locks; never force-unlock or manually remove managed worktrees.
- Integrate to `main` only after review and explicit authorization.
- Use controlled verify-then-restart; normal startup must never run migrations.
