# Prompt selection and cleanup preference

The page loads immutable prompt history, allows a request-scoped prompt selection, and stores the
cleanup-enabled default durably without turning page selection into durable prompt activation.

## Sub-features

- `PROMPTS.HISTORY`: the selector renders versions newest first with version and title.
- `PROMPTS.SESSION`: selecting a prompt changes cleanup requests for the current page only.
- `PROMPTS.RELOAD`: reload restores the durable active prompt and clears both editors/outgoing state.
- `PROMPTS.PREFERENCE`: **Clean automatically** persists as the default across an application
  instance while text and outgoing state remain process-local.
- `PROMPTS.IMMUTABLE`: prompt versions cannot be edited in place and exact prior versions can be
  durably reactivated through the API/admin surface.

## How to get to it (user POV)

- Open the **Cleanup prompt version for this page session** selector in the Cleaned header.
- Toggle **Clean automatically**, then reload or start a second disposable application instance.
- Use the documented prompt API for creating a synthetic version and activating an exact version;
  there is intentionally no expanded prompt-management UI in the workspace.

## Driving and proof

Preconditions: disposable migrated/seeded database. Create only synthetic prompt versions through
the real API.

- GET prompt history, create one inactive synthetic version, and inspect the selector. Prove order,
  labels, selected durable ID, and accessibility name.
- Select the synthetic version and trigger cleanup. Prove the request includes its exact ID while a
  second GET still reports the original durable active ID. Reload and prove the selector resets.
- Toggle cleanup off. Prove the outgoing PUT succeeds, a new application instance reads false from
  `/api/config`, and the database setting changed. Restore the original preference during cleanup.
- Activate the prior exact prompt ID through the API and read it back. Prove immutability with the
  targeted database/store test rather than editing SQLite directly.

## Gotchas

- Selector choice and durable activation are intentionally different operations.
- Reload clears editor and process-local outgoing text; it must not be described as durable text.
- Database proof may query only the disposable run database and must not include prompt text in a
  committed artifact.
