# Cleanup resilience and local evaluation design

> **Superseded implementation-status record (2026-09-10).** This design predates the cleanup-only
> benchmark/canary machinery implemented by issues #25–#32. That implementation does not establish
> that a live run occurred and grants no operational authorization. Cleanup evaluation remains
> independent from Smart evaluation; use the canonical
> [evaluation and Smart MVP map](../evaluation-mvp-map.md) for current cross-track status.

- **Status:** Historical design; version-one benchmark/canary design superseded
- **Code baseline:** `8599efa3c3ac65e50ff44a4ad43f31d68af5ae00`
- **Provider evidence checked:** 2026-08-26
- **Scope:** Cleanup routing and an explicitly confirmed, private evaluation corpus; no runtime,
  persistence, migration, provider, or stable-application change is authorized by this document

The benchmark, scoring, sample, and canary sections originally recorded here are version-one
history. The approved documentation-only successor is the
[source-preserving cleanup benchmark and canary protocol](../cleanup-evaluation-successor-protocol.md),
with its [machine-readable version 2](../cleanup-evaluation-benchmark-v2.json). Version 2 authorizes no
runner implementation, corpus access, provider call, spending, benchmark, canary, routing change,
or stable-product change. The original
[machine-readable version 1](cleanup-evaluation-benchmark-v1.json) remains unchanged as superseded
history.

## Decision summary

### Confirmed constraints

- Cleanup fails open to the current Original text. Original, Prepared, and outgoing text remain
  ephemeral in the current product; only prompt versions and settings are durable.
- Ordinary typing, paste, dictation, editing, cleanup, or outgoing selection is not consent to save
  text. Collection requires a separate action and a second confirmation.
- Evaluation material, consent records, databases, exports, and logs remain local, outside Git, and
  separate from model training or personalization.
- A stable session may explicitly save a case, but must not call an alternate model. Candidate
  execution occurs later in an isolated pilot, never as shadow traffic from stable use.
- A source, faithful transcript, and polished cleanup are different artifacts. This corpus evaluates
  **polished cleanup**. It must not be described or reused as transcript truth, a correction episode,
  or personalized evidence.

### Historical version-one recommendations

The routing and benchmark recommendations below explain Gates 1–6 and version-one history. They do
not override version 2's two single-model arms, 30-second deadlines, fixed 60-case sample, or finite
10-cleanup canary.

1. Put a small sequential router behind `CleanupProvider`. Start with
   `gemini-3.7-flash`, then `gpt-5.6-luna`, only when both paid credentials and the disclosure are
   explicitly configured. Keep Gemini primary initially because Sayloom already has a Gemini
   adapter, not because price establishes quality. Switch primary only after the pre-registered
   benchmark.
2. Give each provider one attempt. Bound the whole operation to 20 seconds: at most 12 seconds for
   the primary and the smaller of 8 seconds or the remaining total budget for fallback. Treat these
   values as benchmark inputs before changing the current 30-second product deadline.
3. Collect only through **Save evaluation case** → review/edit expected cleanup → explicit
   confirmation. Never infer consent from ordinary use.
4. Treat 300 as a candidate ceiling/target, not a proven sample requirement. Start with a fixed
   60-case feasibility set; expand toward 300 only to fill pre-registered strata and narrow uncertain
   confidence intervals, without changing scoring or thresholds after results are visible.

### Historical version-one assumptions

- A sequential cross-provider fallback improves availability enough to justify sending a failed
  request to a second processor.
- A 12-second primary budget and 20-second total budget preserve daily-flow responsiveness.
- User-confirmed expected cleanup without retained audio is sufficient ground truth for polishing.
- Sixty cases expose obvious regressions; up to 300 may be useful for stratum coverage. Neither size
  currently has a power analysis.

### Confirmed user decisions

1. **Corpus authority:** The user owns the corpus. Sayloom may manage it only as local cleanup
   evaluation data. It is not application configuration, transcript-fidelity evidence,
   personalization, or training data; other uses require new explicit consent.
2. **Local boundary:** Use a dedicated SQLite database in a separate external Sayloom evaluation-data
   directory. It must not share the application configuration database or stable/pilot runtime state.
3. **Retention:** Expire cases 90 days after capture, with review before expiry, optional retention
   through one named benchmark, and immediate user-initiated deletion.
4. **Export:** Provide a user-initiated plain JSONL export with an explicit sensitive-data warning,
   field/count preview, and no automatic export or sharing.
5. **Provider disclosure:** After the disclosure is explicitly configured, cleanup may send text to
   paid Gemini and, only after a qualifying failure, to paid OpenAI.
6. **Historical benchmark thresholds:** Version 1 froze the non-inferiority margins and harmful-
   change gate below. Version 2 replaces them for any future cleanup benchmark.

## Reconciliation with transcript fidelity

`docs/transcript-fidelity-spec.md` does not exist at baseline `8599efa`. It was added one local commit
later at `7fe37bc` on branch `docs/transcript-fidelity-spec`, whose parent is exactly `8599efa`. This
investigation read that later local document without merging or changing branches.

The later specification confirms explicit acceptance, local-only private data, no passive history,
separation from training consent, original preservation, and stable/pilot isolation. It separately
blocks transcript-fidelity correction episodes until their governance is resolved. The decisions
above now govern only the cleanup-evaluation corpus; they do not authorize correction episodes or
relabel either kind of sensitive material as configuration.

The two evidence domains remain separate:

| Domain | Expected value | Permitted use |
| --- | --- | --- |
| Cleanup evaluation | User-confirmed polished output | Compare cleanup prompts/models/routing |
| Transcript fidelity | User-confirmed faithful wording | Evaluate recovery; never inferred from cleanup |
| Personalization/training | Separately consented evidence | Out of scope; no corpus item grants consent |

## Current contract and gaps

At the baseline, `CleanupProvider` exposes `provider_id`, one `model`, and `clean()`. The Gemini
adapter owns same-provider model fallback and creates a new `httpx.AsyncClient` per attempt. The
service imposes one total timeout, validates non-empty/control-character/expansion limits, and returns
safe errors. The browser debounces for 700 ms, aborts its prior fetch, ignores stale responses, and
immediately publishes Original while cleanup is waiting or running.

The minimum gaps for cross-provider routing are:

- `CleanupResult.provider` is hard-coded to `gemini`; `ProviderOutput` carries only a model.
- Failure types do not carry provider, retryability, quota scope, retry-after, or attempt duration.
- HTTP 429 does not distinguish temporary rate limiting from permanent credit/spend/quota exhaustion.
- Cooldown is per Gemini model even when multiple models share one project quota.
- Browser abort prevents stale UI updates, but server-side disconnect cancellation and transport
  propagation are not explicitly tested; a future router must not continue to fallback afterward.
- A new HTTP client per attempt prevents connection reuse and makes lifecycle cleanup implicit.
- Output is free-form text rather than provider-enforced structured output followed by one shared
  schema validator.
- Current Gemini 3.x requests set `thinkingLevel: "minimal"`; Google documents that
  `gemini-3.7-flash` supports only low, medium, and high, and that minimal returns an error [G1].

## Smallest routing architecture

```text
CleanupService (fail-open, total deadline, shared output validation)
    └── SequentialCleanupProvider (route order, budgets, breakers, attribution)
          ├── GeminiAdapter  ── one long-lived AsyncClient
          └── OpenAIAdapter  ── one long-lived AsyncClient
```

Keep prompt lookup, API response shaping, fail-open behavior, and semantic output validation in
`CleanupService`. Provider adapters should only frame one provider request, enforce its structured
response contract, normalize one result/error, and honor cancellation. The sequential provider owns
route selection; adapters must not call other models or providers.

Use one internal result for both success and failure attribution:

- success: Prepared text, provider ID, model ID, elapsed milliseconds, input/output token counts when
  supplied, and route index;
- failure: provider ID, model ID, failure class, safe provider code, HTTP status, retry-after when
  safely parseable, elapsed milliseconds, and quota-group ID;
- public result: winning provider/model and a safe ordered attempt summary containing no text,
  prompt, payload, credential, headers, response body, or private path.

### Budgets, cancellation, and storms

- Start one monotonic 20-second total deadline. The primary gets `min(12s, remaining)`; fallback gets
  `min(8s, remaining)`. Do not start an attempt with less than 500 ms remaining.
- One route means one network request. Do not retry within an adapter; otherwise an apparent
  two-provider pool can make four or more paid calls.
- Browser abort, client disconnect, task cancellation, or application shutdown cancels the active
  HTTP request and prevents later routes. Never convert `CancelledError` into provider failure.
- Preserve the current browser debounce and latest-response sequence guard. Add a process-local
  capacity limit of two active routed cleanups; reject a third operation immediately to Original
  rather than queueing stale text.
- Breakers and the total deadline apply to every routed cleanup. After cooldown, one eligible caller
  may own the half-open probe; concurrent callers skip that in-progress probe.

### Failure and breaker policy

| Class | Examples | Try next route? | Breaker effect |
| --- | --- | --- | --- |
| Transient route | connection reset, timeout, 408, 500, 502, 503, 504 | Yes, if budget remains | First failure opens the model route for about 15 s; failed half-open probes use jittered exponential backoff capped at 5 min; a successful owned probe closes |
| Temporary quota | 429 rate/capacity with a valid retry-after or retryable provider code | Yes | Open the configured quota group for at least a valid retry-after; otherwise use jittered exponential backoff from about 60 s, capped at 15 min |
| Permanent quota | exhausted credits, project/org spend or usage limit | Yes, if an independently funded group exists | Disable the quota group until settings reconstruction or configuration reset |
| Permanent configuration | 400 schema/model error, 401/403 credential/access, 404 model | Yes only when an independent configured route may help | Disable 401/403/missing-key credential quota groups; disable other permanent model/config failures only on the affected route, until settings reconstruction or configuration reset |
| Safety/policy | safety block, refusal, recitation, prohibited content, SPII | **No** | No breaker; fail open to Original |
| Invalid output | missing schema field, empty/control text, excessive expansion, truncation | Yes, if budget remains | No breaker for content-dependent invalid output; never publish rejected output |
| Invalid local request | input/prompt validation | No | No breaker |
| Unknown | unclassified or programming exception | No | No breaker; fail open to Original |

`quota_group` is explicit configuration, not inferred from credentials. Gemini models using the same
Cloud project normally share one group; OpenAI models using the same project use another. Never hash
or persist a credential to derive the group. Store breaker state in memory only; restart clears it.

### Structured output and validation

Use the same minimal schema at both providers: an object with exactly one required string,
`prepared_text`, and no additional properties. Gemini 3.7 Flash and GPT-5.6 Luna both document
structured outputs [G1, G2, O1, O2]. Schema validity does not establish semantic correctness: Google
requires application validation, and OpenAI notes refusals, truncation/content filtering, and
schema-valid mistakes [G2, O2]. Therefore keep the current shared checks and add UTF-8/string type,
100,000-character API limit, and exact schema validation. Safety/refusal and incomplete output are
normalized before semantic validation.

### HTTP and credential lifecycle

- Construct one `httpx.AsyncClient` per configured provider during FastAPI lifespan and close it at
  shutdown. Set connect/read/write/pool timeouts explicitly; the route budget remains authoritative.
- Configure only explicit `LOCAL_TEXT_GEMINI_API_KEY` and `LOCAL_TEXT_OPENAI_API_KEY` entries in the
  existing user-only external environment files. Do not discover generic ambient
  `GEMINI_API_KEY`, `GOOGLE_API_KEY`, or `OPENAI_API_KEY` values for production routing.
- Configure provider order, exact models, quota groups, and paid-data-use acknowledgement explicitly.
  A credential alone does not opt in to cross-provider fallback.
- Never expose credentials to the browser. `/api/config` may expose the ordered provider/model names,
  whether fallback is enabled, and the disclosure version only.

The disclosure must say that cleanup sends the current text and cleanup instruction to the named
external primary; a qualifying failure may send the same material to the named fallback; local
storage does not make provider processing local; and corpus saving is separate and optional. Require
paid Gemini: Google's free tier uses prompts and responses to improve products and may involve human
review, while paid Gemini does not use them for product improvement but logs them for a limited
abuse-monitoring period [G3, G4]. OpenAI says API data is not used for training by default, but abuse
logs may retain prompts/responses for up to 30 days; `/v1/responses` should set `store=false`, and
approved Zero Data Retention is a separate account control [O3].

## Explicit corpus workflow

### Capture

1. Stable use remains unchanged until the user activates **Save evaluation case** for the current,
   non-stale cleanup result. No prompt, timer, sampling, edit count, or failure opens this flow.
2. A review dialog shows Source, provider output, and an editable **Expected cleanup**. It identifies
   the corpus purpose, local location, retention rule, provider/model/prompt context, and states:
   “Saving this case does not consent to model training or personalization.”
3. The user must review the expected cleanup, choose the source category
   (`dictation`, `typed`, `pasted`, or `unknown`), and activate **Confirm and save**. Merely closing,
   navigating, sending, or continuing to edit saves nothing.
4. After saving, show the case ID, expiry, **Review**, **Delete now**, and **Export selected** actions.
   Failed or cancelled persistence leaves no partial case.

Capture only:

- source text, exact provider output, and user-confirmed expected cleanup;
- source category explicitly selected by the user;
- winning provider/model and safe per-attempt attribution;
- immutable prompt version ID, content hash, and exact prompt text needed to reproduce the run;
- cleanup contract/schema version, capture time, confirmation time, and optional token/latency/cost
  metadata returned by providers;
- an opaque local case ID and lifecycle timestamps.

Do not capture audio, clipboard history, neighboring drafts, keystrokes, selection history, outgoing
destination, rejected dialog drafts, provider payloads, error bodies, account/project identifiers,
credentials, machine identity, or inferred health/demographic attributes.

### Storage and lifecycle

- Use a dedicated SQLite database under the external Sayloom evaluation-data directory. It is not
  the application configuration database, not a development-state database, and not Git content.
- Purpose is limited to cleanup evaluation. Queries for personalization, prompt auto-tuning, model
  training, analytics, or passive product telemetry are prohibited without new consent.
- Expire a case 90 days after capture. Review lists exact expiry; the user can shorten it or retain
  selected cases through one named benchmark. Deletion removes source, outputs, expected text,
  consent record, and derived labels transactionally.
- Plain JSONL export is user-initiated, warns that it contains sensitive text, previews the case count
  and fields, and writes only to a selected local destination. Include schema version, prompt
  context, consent scope, and checksums. Import or sharing is a separate future decision.
- Stable may capture approved cases but never benchmark them. The pilot imports a user-selected
  snapshot into its distinct private state; stable and pilot never share a live database.

This persistence gate requires a migration, but only in the new evaluation database. It must not add
transcript tables to the current application-configuration migration chain unless the governing
storage decision explicitly chooses that ownership.

## Historical version-one benchmark and canary

Version 1 proposed broader transformation strata, a routed arm, 12-second/8-second/20-second route
budgets, possible expansion toward 300 cases, several compensating metrics, and a 10/25/100 canary
progression. Those rules are superseded and must not be used for implementation or operation.

The [successor protocol](../cleanup-evaluation-successor-protocol.md) records the full audit and the
approved replacement: exactly 60 challenge-balanced dictation cases within the shipped lexical
boundary; two one-attempt arms under the same prompt, validator, and 30-second deadline; paired
normalized code-point Levenshtein effort and non-compensating hard gates; and, only after passage and
new explicit confirmation, one terminal 10-cleanup manual-candidate canary. It has no route arm,
sample expansion, automatic fallback, 25/100 continuation, or stable promotion.

## Later implementation gates

1. **Provider-neutral result and failures (no migration):** remove hard-coded attribution, normalize
   typed failures, preserve fail-open behavior. Verify unit tests for every class, safe logs, and API
   compatibility.
2. **Adapters and client lifecycle (no migration):** add OpenAI and update Gemini structured output,
   exact model settings, reusable clients, and cancellation. Verify with mock transports only,
   including Gemini 3.7's supported thinking level; no credentials or provider calls.
3. **Sequential router (no migration):** budgets, route/quota breakers, cancellation, concurrency,
   and attempt attribution. Verify deterministic fake-clock interleavings, retry-after, storm, and
   total-deadline tests.
4. **Disclosure and explicit configuration (implemented, no migration):** the fixed paid Gemini
   `gemini-3.7-flash` → paid OpenAI `gpt-5.6-luna` route requires exact provider credentials,
   distinct quota groups, route order, and `paid-external-cleanup-v1` acknowledgement. Invalid or
   incomplete cross-provider configuration creates no clients. `/health`, `/api/config`, and the
   expandable Workspace disclosure report sanitized routing status and state that fallback sends
   the same current text/instruction only after qualifying Gemini failure and saves no evaluation
   corpus. Legacy Gemini-only routing remains compatible; generic `OPENAI_API_KEY` is ignored.
5. **Corpus contract and schema design (implemented):** the frozen
   [corpus contract](../cleanup-evaluation-corpus-contract.md) encodes the six confirmed decisions in
   API, separate storage, consent, expiry, transactional deletion, and JSONL export contracts.
   [Version 1](cleanup-evaluation-benchmark-v1.json) is preserved unchanged as historical evidence;
   [version 2](../cleanup-evaluation-benchmark-v2.json) is the canonical protocol. Its approval itself
   authorized no implementation or operation.
6. **Corpus persistence and lifecycle (implemented):** the separate opt-in evaluation database,
   proof-bound capture/confirm/review/delete/export, expiry command, and transactional deletion use
   an explicit migration chain. Affected tests cover fresh and predecessor migration, no-migration
   startup, consent paths, stale confirmation, and synthetic-only export/deletion evidence.
7. **Offline benchmark runner (later implemented by issues #25–#32; operation unauthorized):** the
   cleanup-only machinery implements version 2 without a stable migration. Operation still requires
   its exact private manifest, run confirmation, dedicated identities, synthetic smoke, and
   provider-call approval.
8. **Non-shadow canary machinery (later implemented by issues #25–#32; operation unauthorized):**
   eligibility requires every benchmark gate to pass. Operation then requires separate explicit
   confirmation and distinct pilot identities for the single terminal 10-cleanup manual-candidate
   canary.

## Historical provider-evidence snapshot

All provider facts below were checked on 2026-08-26. They are provenance for the earlier design, not
current entry evidence. Version 2 requires official availability, exact IDs/reported versions,
pricing, and retention/data-use terms to be refreshed within 24 hours before registration. Prices
describe cost, not Sayloom cleanup quality.

- **[G1]** Google, [Gemini 3.7 Flash model](https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash),
  updated 2026-08-13: stable model ID, structured-output support, and supported thinking levels;
  `minimal` is explicitly unsupported.
- **[G2]** Google, [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output),
  updated 2026-08-17: JSON Schema support and requirement to validate semantic values in the app.
- **[G3]** Google, [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing),
  updated 2026-08-26: Gemini 3.7 Flash paid standard introductory rates of $0.75/M input and
  $3.75/M output through 2026-12-31; free content is used to improve products, paid content is not.
- **[G4]** Google, [Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms_preview),
  effective 2024-12-13, updated 2026-04-28: unpaid data improvement/human review warning and paid
  processing/limited abuse-monitoring logging.
- **[G5]** Google, [API errors](https://ai.google.dev/gemini-api/docs/api-errors), updated
  2026-08-05, and [Troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting), accessed
  2026-08-26: blocked-generation classes and exponential backoff for 429/503/transient failures.
- **[O1]** OpenAI, [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna.md),
  accessed 2026-08-26: model ID, Responses support, structured outputs, rate limits, and $0.20/M
  input / $1.20/M output standard short-context pricing.
- **[O2]** OpenAI, [Structured model outputs](https://developers.openai.com/api/docs/guides/structured-outputs.md),
  accessed 2026-08-26: strict schemas plus refusal, truncation, content-filter, semantic-error, and
  first-schema latency exceptions.
- **[O3]** OpenAI, [Data controls](https://developers.openai.com/api/docs/guides/your-data.md),
  accessed 2026-08-26: no API training by default, up-to-30-day abuse logs, Responses storage rules,
  `store=false`, and separately approved Zero Data Retention.
- **[O4]** OpenAI, [Error codes](https://developers.openai.com/api/docs/guides/error-codes.md),
  accessed 2026-08-26: retryable connection/timeout/5xx/rate errors, `Retry-After`, and non-retryable
  credit/spend/usage-limit 429 codes.
