---
name: verifying-sayloom
description: Verifies Sayloom integration or release readiness with full feature-mapped evidence across isolated test, browser, database, macOS, provider, and CI lanes. Use only for explicitly requested full, integration, or release verification. Do not use for routine localized implementation or review.
---

# Verifying Sayloom

Use this acceptance contract after implementation and affected checks are resolved. It is separate
from implementation verification and makes full verification claims that another engineer can
reproduce. Read `features/README.md` before choosing checks, then read only the affected feature
files unless release scope requires the complete feature map.

## Invocation boundary

- Do not load or apply this skill during routine localized implementation. The implementation owner
  runs only affected targeted tests and static checks, even when the module concerns browser,
  persistence, migrations, providers, accessibility, or macOS behavior.
- Use this workflow only when the user explicitly requests full, integration, release, or acceptance
  verification. For substantial work, make it a separate phase after constituent implementations
  and their affected checks are complete.
- Full or integration scope maps every entry point and applicable lane affected by all constituent
  changes. Release scope maps the complete release feature set. Do not narrow a genuinely selected
  full run to the checks that were convenient during implementation.
- Existing evidence may guide scope, but only checks executed in the current run can be marked
  `passed`. Do not repeat unchanged checks or reload this contract in the same thread.

## Ownership and phase gates

- Assign one integration owner to the broad run. Constituent implementation owners do not repeat the
  full baseline; the integration owner runs it once after their changes and affected checks resolve.
- Permit only one broad verification owner and one broad lane at a time. Finish and classify the
  current lane before another broad owner or lane begins.
- Do not begin acceptance verification while implementation failures, open corrections, or baseline
  repair remain unresolved. The owner who starts baseline repair retains it until it passes or stops
  at the escalation boundary.
- Keep these phase boundaries explicit: investigate/reproduce; implement plus affected checks; then,
  for substantial work, this separate full integration-verification phase.

## Escalation boundary

During implementation follow-up or baseline repair, stop and report before broadening scope if any
one of these occurs:

- the fix breaks unrelated fixtures or would require changing them;
- the fix must expand outside the module that owns the failing behavior; or
- the affected suite still fails after two targeted correction attempts.

Report the failing claim, relevant excerpt, corrections attempted, and the scope or fixture change
that would be required. Do not silently turn acceptance verification into cross-module product work.

## API usage budget

- Local Sayloom HTTP requests do not consume model-provider API quota. Prefer them as read-only
  confirmation of browser-visible state, not as a substitute for browser interaction.
- The default external-provider budget is **zero calls**. Use mocked-provider Portable tests for
  timeout, malformed response, HTTP failure, cooldown, route ordering, and fail-open behavior.
- Make a real Gemini or OpenAI request only when the user explicitly requests or approves provider
  verification and the provider adapter, model contract, credential path, or production routing
  changed. A general request to verify the application does not authorize paid provider calls.
- Before a real-provider run, state the planned providers, maximum request count, synthetic input,
  and stop condition. Default to one successful request per affected provider. Do not deliberately
  trigger paid timeout, quota, or error responses when a mock proves the application behavior.
- Record request count and returned token usage when available, never credential values or operating
  text. Stop after the planned calls even if an optional state remains unproved; report it precisely.

## Safety boundary

- Never inspect, start, stop, migrate, query, or drive the stable application, its checkout,
  fixed ports, state, services, configuration, database, logs, or integrations.
- Use synthetic text and a new disposable database and service for every live run. Unset
  `LOCAL_TEXT_*`, `GEMINI_API_KEY`, and `GOOGLE_API_KEY` unless a dedicated provider lane is
  intentionally being tested. Never print credential values.
- Do not use `scripts/dev.py restart` for verification: it owns the current checkout's registered
  development service and assigned port. Cover that workflow with tests or on a dedicated
  verification host that has no stable application.
- Normal application startup must not migrate or seed. Run administration commands explicitly.
- Keep databases, logs, run notes, and evidence out of Git. Evidence shown to the user belongs
  under `.amp/in/artifacts/sayloom-verification/<run-id>/` and must contain synthetic data only.
- Prefer quiet test modes and short tracebacks. Persist verbose browser, server, and test logs in the
  run artifact directory rather than the conversation; report summaries and only failure-relevant
  excerpts. Do not retain or reread unchanged output.
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
| macOS integration | launchd, Raycast, Chrome, iTerm, clipboard, and destination-app behavior | Dedicated verification host/profile only, with no stable app present. If this orb is Linux or the apps are absent, use `unavailable`; tests alone stay in Portable. |
| Provider | Real Gemini/OpenAI request compatibility when explicitly approved | Dedicated test credential, isolated browser service, synthetic input, and a declared call budget. Missing approval or credential is `unavailable`, not `skipped` or `passed`. Mock-provider tests stay in Portable. |
| CI | Checks delegated to automation | Use `configured in CI` only after reading the tracked workflow and citing its job. No workflow means the lane is `unavailable` if required. |

## Workflow

1. **Map scope.** Use `features/README.md` to list affected feature IDs and every changed user
   entry point. Inspect routes, controls, commands, tests, migrations, and docs; do not infer the
   map from filenames alone.
2. **Create the ledger first.** List feature × lane checks and expected proof before running them.
   This makes omissions and intentional skips visible.
3. **Run the Portable lane.** The integration owner runs the complete baseline after all constituent
   implementation checks are resolved:

   ```sh
   uv sync --locked
   uv run ruff check .
   uv run pytest
   node --check src/local_text/static/app.js
   find scripts raycast -name '*.sh' -type f -exec sh -n {} \;
   git diff --check
   ```

   Capture concise summaries and exit status, writing verbose output to the run artifact directory.
   Do not report the full baseline as passed if only targeted tests ran. If a baseline check fails,
   diagnose it with the smallest affected command and follow the escalation boundary before repair.
4. **Run Database/migration checks** when application state, models, prompts, import, startup,
   health, or migrations could be affected. Follow “Database proof” below.
5. **Run the Isolated browser lane** for user-visible behavior. Follow “Browser and accessibility
   proof” below. Do not substitute HTTP responses or source inspection for a browser interaction.
6. **Classify planned optional lanes.** Probe platform and tracked CI configuration read-only only
   when relevant. Do not inspect credentials or call a provider unless the Provider lane was
   explicitly approved. Assign every planned lane its precise status; do not add unrelated lanes.
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
  -u LOCAL_TEXT_GEMINI_QUOTA_GROUP_ID -u LOCAL_TEXT_OPENAI_API_KEY \
  -u LOCAL_TEXT_OPENAI_MODEL -u LOCAL_TEXT_OPENAI_QUOTA_GROUP_ID \
  -u LOCAL_TEXT_CLEANUP_ROUTE_ORDER -u LOCAL_TEXT_CLEANUP_PAID_DATA_ACKNOWLEDGEMENT \
  -u LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS -u GEMINI_API_KEY -u GOOGLE_API_KEY -u OPENAI_API_KEY \
  LOCAL_TEXT_PROFILE=development \
  LOCAL_TEXT_DEVELOPMENT_STATE_NAME=verification-RUN_ID \
  LOCAL_TEXT_STATE_DIRECTORY=/tmp/sayloom-verification-RUN_ID \
  LOCAL_TEXT_DATABASE_PATH=/tmp/sayloom-verification-RUN_ID/local-text.sqlite3 \
  LOCAL_TEXT_RAYCAST_DIRECTORY=/tmp/sayloom-verification-RUN_ID/raycast \
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
