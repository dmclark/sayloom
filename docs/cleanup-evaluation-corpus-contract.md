# Cleanup evaluation corpus contract

- **Contract version:** `cleanup-evaluation-corpus-v1`
- **Consent version:** `cleanup-evaluation-consent-v1`
- **Export version:** `cleanup-evaluation-export-v1`
- **Status:** Contract frozen; Stage 3 lifecycle implementation present
- **Canonical benchmark protocol:**
  [`cleanup-evaluation-benchmark-v2.json`](cleanup-evaluation-benchmark-v2.json) — approved protocol
  only; no implementation or operation authorized
- **Superseded history:**
  [`cleanup-evaluation-benchmark-v1.json`](cleanup-evaluation-benchmark-v1.json) — preserved unchanged

This contract governs a private corpus of user-confirmed polished cleanups. It does not authorize
passive collection. The Stage 3 implementation exposes capture only after a successful current
cleanup supplies a short-lived proof and the user completes the separate confirmation. Ordinary
startup still creates no evaluation database and retains no dialog draft or operating text. The
contract resolves interface details including optimistic revisions, bounded benchmark holds, and
two-step export confirmation.

## Fixed boundaries

The six confirmed decisions in the resilience design resolve to these invariants:

1. **Authority and purpose:** the user owns every case. The only allowed purpose is evaluating
   polished cleanup. A case is not transcript truth, application configuration, product analytics,
   personalization evidence, or model-training consent.
2. **Local separation:** cases live in one dedicated SQLite database in an explicitly configured
   external evaluation-data directory. The application configuration database, stable runtime
   state, pilot runtime state, logs, Git, and provider systems may not store or attach this database.
3. **Retention and deletion:** a case expires 90 days after its successful save unless the user
   shortens that period or explicitly holds it through one named benchmark with a fixed release
   date. Deletion is immediate and transactional.
4. **Export:** export is an explicit two-step preview and confirmation. It produces plain UTF-8
   JSONL only through a browser download whose destination the user chooses. There is no automatic
   export, upload, sharing, destination-path logging, or provider call.
5. **Provider disclosure:** saving is separate from provider processing. The saved case records the
   completed cleanup's safe provider attribution, but saving, reviewing, deleting, and exporting
   never invoke a provider.
6. **Benchmark decision:** the canonical public protocol is frozen in version 2 and its
   [narrative authority](cleanup-evaluation-successor-protocol.md). Before execution, a private run
   manifest must bind it to the exact eligible pool and selection, corpus snapshot, prompts,
   annotations, model identifiers and reported versions, settings, scoring code, consent, budgets,
   storage locations, and lifecycle rules. Version 2's documentation approval is not execution
   consent.

Persisted lifecycle timestamps are server-generated UTC instants serialized as RFC 3339 with `Z`;
the cleanup completion time comes from the server-authenticated cleanup proof described below. Case
IDs are opaque UUIDs. Text fields are Unicode strings with no normalization. Source, provider
output, and expected cleanup are each limited to 100,000 characters and may not contain disallowed
control characters under the cleanup output contract.

## Consent and API contract

Opening or editing the review dialog is client-local and non-durable. The first server mutation is
the final **Confirm and save** request. Ordinary cleanup, selecting outgoing text, closing the
dialog, navigating, or a failed request stores nothing.

Every mutating request uses `application/json`, rejects unknown fields, and returns a privacy-safe
error containing only a code, message, and recovery action. Validation errors and logs must never
echo corpus text, prompt text, destination paths, provider payloads, or credentials.

### Confirm and save

`POST /api/evaluation/cases` is the only capture operation. It is enabled only when the external
evaluation database is explicitly configured and current. The request contract is:

```json
{
  "contract_version": "cleanup-evaluation-corpus-v1",
  "capture_proof": "short-lived authenticated value from the current cleanup",
  "consent": {
    "version": "cleanup-evaluation-consent-v1",
    "scope": "polished-cleanup-evaluation-only",
    "confirmed": true
  },
  "source_category": "dictation | typed | pasted | unknown",
  "source_text": "string",
  "provider_output": "string",
  "expected_cleanup": "string",
  "cleanup": {
    "completed_at": "RFC3339 UTC",
    "provider": "safe identifier",
    "model": "safe identifier",
    "attempts": [],
    "prompt_version_id": "application-local identifier",
    "prompt_content_sha256": "64 lowercase hex characters",
    "prompt_text": "string",
    "cleanup_schema_version": "safe identifier"
  }
}
```

Only a successful, non-stale current cleanup result may supply `capture_proof`. The proof binds
hashes of source text and provider output to cleanup completion time, safe attempts, and immutable
prompt context without storing any of them server-side. It expires after 30 minutes and becomes
invalid on process restart. Confirmation verifies the proof and exact bound values; an expired or
mismatched proof saves nothing and requires a new cleanup. Expected cleanup and source category are
intentionally outside the proof because the user supplies them during review.

`attempts` contains only the existing safe attempt attribution: route index, provider, model,
outcome, failure class/code/status/retry-after, elapsed milliseconds, and optional token counts.
It contains no request or response body. Optional cost is integer USD micros plus an explicit
pricing-snapshot identifier; floating-point currency is invalid.

The server revalidates the complete request, computes hashes, and writes the case, consent, and
attempts in one transaction. `captured_at` and `confirmed_at` are the successful transaction time;
`cleanup.completed_at` records when the ephemeral cleanup finished and does not start retention.
The response is metadata only: case ID, revision, capture time, expiry, and available actions. It
does not echo text. A failed or cancelled transaction leaves no row.

The consent presentation immediately above **Confirm and save** must identify the corpus purpose,
external local storage, exact default expiry, provider/model/prompt context, and state verbatim:

> Saving this case does not consent to model training or personalization.

### Review, retention, and deletion

| Operation | Contract |
| --- | --- |
| `GET /api/evaluation/cases` | Returns metadata only, including expiry/hold status; never returns corpus or prompt text. |
| `GET /api/evaluation/cases/{case_id}` | Returns one complete case for an explicit review action. |
| `PATCH /api/evaluation/cases/{case_id}/retention` | Requires the current revision and either an earlier `expires_at`, or one `benchmark_id` plus a fixed `release_at`. A hold may not be open-ended or name multiple benchmarks. |
| `DELETE /api/evaluation/cases/{case_id}` | Requires the current revision and explicit UI confirmation. Atomically deletes the case and every child row; success returns only the deleted case ID. Repeating it is a privacy-safe no-op. |

The original expiry is `captured_at + 90 days`. A user may only shorten it. A benchmark hold has a
user-confirmed fixed release date and ends at the earlier of benchmark completion/cancellation and
that date. When a hold ends, the original expiry applies; if it has passed, the case is deleted in
the same transaction. Upcoming-expiry review begins 14 days before expiry but never extends a case
without the explicit retention mutation.

Expired cases are transactionally deleted before every evaluation read or write. Gate 6 must also
provide an explicit, independently scheduled expiry command. Normal application startup neither
migrates nor purges either database; startup alone is not the expiry mechanism.

### Export

`POST /api/evaluation/exports/preview` accepts case IDs and revisions. It returns a ten-minute,
single-use preview token bound to that exact selection, plus the case count, field names, total byte
estimate, expiry range, and this warning:

> This JSONL export contains sensitive source text, provider output, expected cleanup, and prompt
> text. Save it only to a private local destination. Export does not share or upload it.

`POST /api/evaluation/exports` accepts only that token and a `confirmed: true` flag. Any changed,
deleted, expired, or newly selected case invalidates the token. The browser must obtain an explicit
user-selected save destination before confirmation; an automatic-download setting is insufficient.
The response is streamed `application/x-ndjson` to that browser-owned destination. The server never
accepts or records a filesystem path and creates no application-side copy.

Each line is one self-contained case object with these fields:

```text
export_version, contract_version, case_id, captured_at, confirmed_at, expires_at,
source_category, source_text, provider_output, expected_cleanup, cleanup, consent,
annotations, record_sha256
```

`cleanup` includes the exact prompt context and safe attempts. `consent` includes only version,
scope, and confirmation time. `annotations` contains only later local benchmark labels; it is empty
at capture. `record_sha256` is lowercase SHA-256 over canonical UTF-8 JSON of the other fields
(`sort_keys=true`, compact separators, no ASCII escaping). Lines use compact JSON and LF endings.
No export event, destination, or copy is retained in either database or logs. Import and sharing
remain future decisions.

## Separate storage schema

Gate 6 must implement this logical schema in a new Alembic chain owned by the evaluation database,
not in `migrations/versions` for application configuration. The two databases must never be joined
with SQLite `ATTACH` or cross-database foreign keys. The evaluation directory and database use
user-only permissions, including SQLite journal files.

`LOCAL_TEXT_EVALUATION_DATA_DIRECTORY` is the sole opt-in. It must be an absolute, user-owned path
outside the repository, application state directory, and every stable or pilot runtime directory;
the database name inside it is `cleanup-evaluation.sqlite3`. Missing or invalid configuration keeps
all evaluation mutations unavailable and creates nothing. Gate 6's explicit evaluation-admin
command owns this database's migrations; normal application administration and startup do not.

SQLite must use `foreign_keys=ON`, `secure_delete=ON`, `temp_store=MEMORY`,
`journal_mode=DELETE`, and `journal_size_limit=0`. The application creates no automatic corpus
backup, tombstone, audit copy, or migration snapshot: each would outlive immediate deletion. An
explicit JSONL export is the only user-owned copy Sayloom produces.

| Table | Required data and constraints |
| --- | --- |
| `evaluation_cases` | Opaque ID; contract version; source category and three text artifacts; prompt ID/hash/text; cleanup schema version; winning provider/model; capture/confirmation/cleanup times; original/current expiry; revision. Purpose is fixed to `polished-cleanup-evaluation-only`. |
| `evaluation_consents` | One-to-one case ID; fixed consent version/scope; confirmation time. No reusable blanket consent. |
| `evaluation_attempts` | Ordered, unique route index per case; safe attempt attribution only; non-negative duration/token/cost values. |
| `evaluation_annotations` | Reviewer-created protocol tag/category, source span, and frozen acceptable value(s) after capture; no inferred private identity and no capture-time rows. |
| `benchmark_holds` | At most one active row per case; named benchmark ID; confirmation/release times; fixed release date. |

Every child uses `ON DELETE CASCADE`. Text-bearing columns are `NOT NULL`; optional numeric metadata
is nullable rather than guessed. Hashes and fixed identifiers have format checks. The database has
no training-consent, personalization, analytics, machine-identity, account, provider-payload,
audio, clipboard, keystroke, outgoing-destination, rejected-draft, or filesystem-path column.

Case creation and deletion are single transactions. Expiry deletes the same row graph as explicit
deletion. Benchmark snapshotting uses a read transaction and records only IDs, revisions, and
hashes in the private run manifest; it does not create a second live corpus. Stable may create and
manage confirmed cases after Gate 6, but only an isolated pilot may consume an explicit snapshot.

## Gate 6 acceptance boundary

Gate 6 is not complete until tests prove: missing/unconfigured storage retains nothing; application
startup does not create or migrate the evaluation database; fresh and predecessor evaluation
migrations; failed confirmation rollback; metadata-only listing; revision conflicts; 90-day expiry,
fixed benchmark release, and immediate cascade deletion; preview invalidation; deterministic
synthetic-only JSONL; no provider calls for corpus operations; and isolated-browser consent,
review, delete, and export flows. None of those implementation tasks is part of Gate 5.
