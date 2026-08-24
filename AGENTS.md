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
- Runner-backed Amp threads use the runner's existing directory; they do not create a worktree automatically.
- Before implementation, use a dedicated branch/worktree—preferably through the active manager (currently Supacode)—and give it a named development state.
- Preserve manager-owned locks; never force-unlock or manually remove managed worktrees.
- Integrate to `main` only after review and explicit authorization.
- Use controlled verify-then-restart; normal startup must never run migrations.
