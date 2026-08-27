# Schema, migration, seed, and import lifecycle

Explicit administration prepares disposable durable state while normal startup remains read-only
with respect to schema and seed state.

## Sub-features

- `ADMIN.STATUS`: schema reports missing, uninitialized, mismatch, or current without mutation.
- `ADMIN.STARTUP`: missing/mismatched startup reports setup required and performs no migration/seed.
- `ADMIN.MIGRATE`: explicit migration reaches Alembic head and is safe to repeat.
- `ADMIN.SEED`: deterministic seed is safe to repeat and required configuration is validated.
- `ADMIN.IMPORT`: allowlisted preview/digest/confirm is read-only then transactional and one-time.
- `ADMIN.CONTROLLED`: the macOS restart workflow verifies, backs up, migrates/seeds, restarts, and
  health-checks only the state inferred from the current checkout. Checkout states use persistent
  independently allocated ports; activation moves the Raycast-targeted state to port 7523.
- `ADMIN.STATE-LIFECYCLE`: init creates a branch-named checkout state when missing; list, remove,
  and preview-first prune manage registered and stale external state without shared fallback.

## How to get to it (user POV)

- Run `uv run python -m local_text.admin schema|migrate|seed` with an explicit disposable
  `LOCAL_TEXT_DATABASE_PATH`.
- Run `import-preview` and `import-confirm --digest ...` against a synthetic source directory.
- Run `scripts/dev.py`, `init`, `db`, `list`, and preview-only `prune` against a disposable state
  root. Exercise `remove --yes` and `prune --apply` only on states created by that run.
- On a dedicated verification-only macOS host, use the named-state controlled workflow. Never run
  it on a host with the stable application.

## Driving and proof

Follow the Database proof sequence in `../SKILL.md` and retain sanitized JSON output for each state.

- Prove missing-schema status and setup-required startup leave the path absent.
- Migrate, seed, report current revision, rerun both operations, then use a second application
  instance to prove seeded state is readable and unique.
- For every new migration, build supported predecessor fixtures with synthetic rows, upgrade them,
  and verify data plus constraints. Empty-database success alone is insufficient.
- Prove checkout inference ignores other worktrees, generated names follow the Git branch, ports
  are unique, activation swaps port 7523, and cleanup removes only selected disposable resources.
- Preview a synthetic import, modify an allowlisted source, reject the stale digest, preview again,
  confirm once, reject a second confirmation, and verify ignored files were not read or changed.
- Keep `ADMIN.CONTROLLED` in the macOS lane. Portable tests may pass while the real-device entry
  point is `unavailable`; report both records rather than merging them.

## Gotchas

- `schema` intentionally exits nonzero for a non-current database; that expected result can pass.
- Starting Uvicorn against a missing database can import the app before a probe. Verify absence
  after startup and health, not just before.
- Never create migration proof from a copied real database.
- In the Amp orb, launchd and the controlled fixed-port restart are `unavailable`, not passed by
  proxy through tests.
