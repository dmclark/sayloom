---
name: verifying-sayloom
description: Verifies and maintains Sayloom behavior with feature-mapped evidence across isolated test, browser, database, macOS, provider, and CI lanes. Use when implementing or reviewing changes, proving a fix, checking migrations or accessibility, or updating the verification map.
---

# Verifying Sayloom

Use this contract to make verification claims that another engineer can reproduce. Read
`features/README.md` before choosing checks, then read each affected feature file.

## Safety boundary

- Never inspect, start, stop, migrate, query, or drive the stable application, its checkout,
  fixed ports, state, services, configuration, database, logs, or integrations, except for the
  explicit target-command boundary below.
- For explicitly authorized target-command work, the macOS integration lane may read target status
  through the stable application's Targets surface or API, inspect the configured Raycast Script
  Commands directory, and use the Targets install, regenerate, or remove operations. This permits
  only the target-definition reads and target-local operation-error updates performed by those
  endpoints. Create only an absent expected target path; overwrite or remove only an artifact
  recognized as Sayloom-owned by its target ID and generated filename. Never execute a target
  command, alter a collision or unrelated entry, or access other stable application state. Obtain
  explicit approval immediately before each live mutation. Activation repoints only the fixed
  development aliases; Targets regeneration is the recovery path for a managed command.
- Use synthetic text and a new disposable database and service for every live run. Unset
  `LOCAL_TEXT_*`, `GEMINI_API_KEY`, and `GOOGLE_API_KEY` unless a dedicated provider lane is
  intentionally being tested. Never print credential values.
- Do not use `scripts/dev.py restart` for verification: it owns the current checkout's registered
  development service and assigned port. Cover that workflow with tests or on a dedicated
  verification host that has no stable application.
- Normal application startup must not migrate or seed. Run administration commands explicitly.
- Keep databases, logs, run notes, and evidence out of Git. Evidence shown to the user belongs
  under `.amp/in/artifacts/sayloom-verification/<run-id>/` and must contain synthetic data only.
- Cleanup may remove only resources created by the current run. Preserve evidence until the user
  has reviewed the report.

## Evidence statuses

Use exactly one of these statuses for every planned feature × lane check:

- **`passed`**: Executed in this run, observed the expected result, and recorded decisive output
  or an artifact. A test that passed does not make an unexercised browser or real-device path pass.
- **`skipped`**: The check was available and applicable, but was deliberately not run. Record who
  or what made that decision and why. Time pressure alone must not be hidden as a pass.
- **`unavailable`**: The check could not run because a required capability or prerequisite was
  absent. Record the prerequisite, the read-only probe or attempted route, and the result. Do not
  use this for a failing product behavior.
- **`configured in CI`**: A tracked CI job is configured to run the check, but it was not executed
  in this run. Cite the workflow path and job. This is not `passed`; CI status must be checked
  separately before claiming it passed.

Never collapse these into “covered,” “green,” or a percentage. Product failures remain failures:
report the expected behavior, actual behavior, reproduction, and evidence rather than assigning a
non-passing status that conceals the regression.

Each evidence record has this shape:

```text
Feature / entry point:
Lane:
Status: passed | skipped | unavailable | configured in CI
Action or command:
Expected:
Observed:
Evidence: command output, API/DOM fact, ARIA snapshot, screenshot, or tracked CI job
Notes: cleanup, prerequisite, or blocker
```

## Environment lanes

Plan only applicable lanes, but report every planned lane explicitly.

| Lane | Purpose | Isolation and proof |
|---|---|---|
| Portable | Python, JavaScript, shell, API, and state logic | Run in this checkout with generated temporary paths and no credentials. Record commands and exit status. |
| Isolated browser | Real user interaction, responsive layout, and accessibility tree | New temporary database, dynamic loopback port, health-checked supervised service, fresh browser session, synthetic text. Prove DOM/accessibility state and visible output. |
| Database/migration | Schema lifecycle, persistence, import, and no-migration startup | New temporary SQLite database and synthetic import directory. Check state before and after every mutating command. |
| macOS integration | launchd, Raycast, Chrome, iTerm, clipboard, and destination-app behavior | Dedicated verification host/profile with no stable app present, except for an explicitly authorized target-command check constrained by the safety boundary. If this orb is Linux or the apps are absent, use `unavailable`; tests alone stay in Portable. |
| Provider | Successful Gemini cleanup, timeout, and provider failure | Dedicated test credential plus isolated browser service and synthetic input. Missing credential is `unavailable`, not `skipped` or `passed`. Mock-provider tests stay in Portable. |
| CI | Checks delegated to automation | Use `configured in CI` only after reading the tracked workflow and citing its job. No workflow means the lane is `unavailable` if required. |

## Workflow

1. **Map scope.** Use `features/README.md` to list affected feature IDs and every changed user
   entry point. Inspect routes, controls, commands, tests, migrations, and docs; do not infer the
   map from filenames alone.
2. **Create the ledger first.** List feature × lane checks and expected proof before running them.
   This makes omissions and intentional skips visible.
3. **Run the Portable lane.** Use the smallest targeted check first, then the complete baseline
   when the change can affect shared behavior:

   ```sh
   uv sync --locked
   uv run ruff check .
   uv run pytest
   node --check src/local_text/static/app.js
   find scripts raycast -name '*.sh' -type f -exec sh -n {} \;
   git diff --check
   ```

   Do not report the full baseline as passed if only targeted tests ran; name the target.
4. **Run Database/migration checks** when application state, models, prompts, import, startup,
   health, or migrations could be affected. Follow “Database proof” below.
5. **Run the Isolated browser lane** for user-visible behavior. Follow “Browser and accessibility
   proof” below. Do not substitute HTTP responses or source inspection for a browser interaction.
6. **Probe optional lanes.** Probe platform, provider, and tracked CI configuration read-only.
   Assign their precise status; do not silently omit them.
7. **Clean run-owned resources.** Stop only the service created by this run, close its browser
   session, and remove its temporary state. Keep report artifacts.
8. **Report by claim.** Lead with failures or blockers, then the evidence ledger. State exactly
   which checks did not run.

## Isolated service recipe

Generate a unique run ID, dynamic available port, and state directory. In an Amp orb, start the
server with `amp orb service start <unique-name> --command '<command>' --portal`; never use `&`,
`nohup`, or `tmux` for the server. The command must set explicit values equivalent to:

```sh
env -u LOCAL_TEXT_GEMINI_API_KEY -u LOCAL_TEXT_GEMINI_MODEL \
  -u LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS -u GEMINI_API_KEY -u GOOGLE_API_KEY \
  LOCAL_TEXT_PROFILE=development \
  LOCAL_TEXT_DEVELOPMENT_STATE_NAME=verification-RUN_ID \
  LOCAL_TEXT_STATE_DIRECTORY=/tmp/sayloom-verification-RUN_ID \
  LOCAL_TEXT_DATABASE_PATH=/tmp/sayloom-verification-RUN_ID/local-text.sqlite3 \
  uv run uvicorn local_text.app:app --host 127.0.0.1 --port PORT
```

Before startup, explicitly migrate and seed that same database with
`uv run python -m local_text.admin migrate` and `seed`. Require `/health` to return HTTP 200,
`status: ok`, `profile: development`, the generated state name, and the expected database
revision. A healthy but differently identified process is not the verification instance.

Use the internal loopback URL for tools running inside the orb. Share only the portal URL printed
by Amp, never a raw loopback or sandbox-host URL. Stop the named Amp service during cleanup.

## Browser and accessibility proof

- Run `agent-browser skills get core --full` before using `agent-browser`; follow the installed
  version's commands rather than guessing syntax.
- Start from a fresh browser session and the generated verification identity. Capture console
  errors before and after each flow.
- Drive by accessible role and name first. IDs may diagnose behavior but are not accessibility
  proof. Exercise each mapped entry point separately; one shortcut does not prove another.
- For each UI claim, record: initiating action, resulting DOM or API fact, focused element where
  relevant, an ARIA/accessibility snapshot, and one screenshot with Sayloom Development plus the
  generated verification state visible.
- Run `agent-browser a11y --tags wcag2a,wcag2aa --json`. Record violations and manually resolve or
  report every `incomplete` rule; a zero-violation count with incomplete rules is not a complete
  accessibility pass.
- Inspect each screenshot with `view_media`; merely creating a screenshot is not verification.
- Exercise keyboard behavior for keyboard-operable controls. Check narrow and desktop viewports
  when layout or responsive code changes.
- For mutations, prove the visible result and a read-only second view such as a GET endpoint,
  reload, reopened record, or SQLite query against the disposable database. A transient status
  message alone is insufficient.
- Never use a screenshot as the sole proof of behavior. Never include credentials, real user text,
  private paths, database content, or logs in evidence.

## Database proof

Use a new temporary directory and pass `LOCAL_TEXT_DATABASE_PATH` explicitly on every command.
At minimum, prove the applicable sequence:

1. `admin schema` reports `missing`, exits nonzero, and does not create the database.
2. Starting against the missing path returns setup-required health and still does not create or
   migrate the database.
3. `admin migrate` reaches the repository's Alembic head; `admin seed` creates the deterministic
   seed; `admin schema` reports `current` with matching current/expected revisions.
4. Running `migrate` and `seed` again is safe and does not duplicate seed state.
5. A real schema-backed user/API flow persists across a second read or application instance.
6. If a new migration exists, upgrade from every supported predecessor represented by fixtures,
   not only from an empty database. Verify constraints and preserved synthetic rows.
7. For importer changes, prove preview is read-only, a changed source invalidates its digest,
   confirm is transactional and one-time, and unallowlisted files remain ignored.

Do not copy, open, back up, or mutate an existing database. Do not claim the macOS controlled
backup/restart path passed from unit tests; report it in its own lane.

## Maintaining the contract

When routes, controls, commands, persistence, migrations, or supported platforms change:

1. Reconcile `features/README.md` one-to-one with files under `features/`; no missing, duplicate,
   extra, or dead entries.
2. Compare each mapped feature with source and tests. Add missing user entry points and remove only
   behavior that no longer exists by design.
3. Live-drive every affected feature in each applicable available lane. Source inspection alone
   cannot validate a driving recipe.
4. Classify findings: **contract drift** changes this skill/map; **harness gap** changes only a
   verification-owned helper and must be re-proved; **product regression** is reported and must
   not be hidden by weakening the map.
5. Keep product fixes separate from verification-contract maintenance unless the user explicitly
   requested both.
