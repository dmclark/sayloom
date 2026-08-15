# Repository Guidance

This repository is local-first and public-safe from its first commit.

- Keep operating data, API keys, dictated or cleaned text, databases, and logs outside Git.
- Never add real user content, credentials, private machine paths, or copied legacy implementation.
- Never inspect, modify, start, stop, or otherwise interact with the existing stable application or any of its checkouts, services, ports, configuration, databases, logs, or integrations.
- Use neutral technical identifiers such as `local_text`; keep them decoupled from the display brand.
- Normal application startup must not run database migrations.
- For validated coding changes, use the controlled verify-then-restart workflow rather than hot reload.
- Keep features and abstractions limited to the current requirement.
