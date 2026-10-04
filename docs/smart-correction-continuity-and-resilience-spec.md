# Smart correction continuity and resilience specification

- **Status:** Confirmed target contract; implementation pending
- **Scope:** Live-dictation continuity, cleanup reliability evidence, provider configuration visibility, and explicit route testing
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Architecture context:** [ADR-0001](adr/0001-correction-modes-and-fallback-routing.md)
- **Domain vocabulary:** [`CONTEXT.md`](../CONTEXT.md)
- **Confirmed:** 2026-10-04

## Purpose

This specification prevents a failed Smart correction rerun from making all
previously Prepared text appear to vanish during continuing dictation. It also
defines the bounded local evidence and route checks needed to distinguish an
invalid configuration, primary-route degradation, successful fallback, and
final cleanup failure without retaining operating text.

Implement this contract in two ordered slices:

1. preserve continuity from the last successful Prepared result while a
   full-current cleanup is pending or has failed; then
2. add sanitized reliability history, warnings, reporting, and explicit
   synthetic route tests.

This document does not authorize implementation, migration, provider calls,
spending, access to private operating data, operation of the stable application,
deployment, commits, pushes, or merges. Those actions retain their existing
workflow and authorization gates.

## Problem and verified baseline

Sayloom currently reruns cleanup against the complete current **Original** after
Original changes. While a replacement request is waiting or running, the prior
Prepared value is no longer considered current and Outgoing switches to
Original. A timeout, provider error, malformed response, local output rejection,
or request failure then places the complete current Original in the Prepared
field and keeps Outgoing on Original.

This behavior is safe in the narrow sense that Sayloom never publishes an
invalid provider result. It is disorienting during continuing dictation: a
failure affecting newly added text also removes the visible effect of every
earlier successful cleanup.

The runtime already supports bounded sequential routing and an explicitly
configured Gemini-to-OpenAI route. Cross-provider routing applies to both Smart
and Conservative requests. It remains opt-in and requires complete exact
configuration plus paid-data acknowledgement. The existing development command
`scripts/dev.py logs --provider-traffic` can temporarily record exact provider
requests and responses while an actively locked viewer is present. Normal and
release logging remains sanitized.

**Unverified (D36):** The stable installation may currently be Gemini-only,
partially configured for cross-provider routing, or exhausting both configured
routes. Repository code proves that fallback exists, but the stable
configuration and logs are outside this work's access boundary. Existing logs
and state contain no approved durable history from which to reconstruct the
reported incidents.

## Outcome and non-goals

During one live draft, Sayloom keeps a page-session checkpoint containing the
last successfully processed Original and its corresponding Prepared result. If
the checkpoint Original remains an exact prefix of the current Original,
Sayloom uses the checkpoint Prepared plus the exact unprocessed suffix while
full-text cleanup is pending or has failed. The user therefore retains earlier
successful preparation and sees newly dictated text immediately.

Every cleanup request still reevaluates the complete current Original. A valid
success replaces the provisional continuity value and establishes a new
checkpoint. The continuity value is not represented as a successful Prepared
result, and its suffix is never represented as cleaned.

This work does not:

- change Smart's correction authority, prompt, model-selection quality, or
  Personal Corrections behavior;
- process only the new suffix or freeze earlier text against later context;
- reconcile a checkpoint across arbitrary edits to its Original prefix;
- introduce transcript history or durable storage of Original, Prepared,
  prompts, provider payloads, or response bodies;
- automatically test providers, spend money, or send synthetic or private text
  without an explicit action;
- enable cross-provider routing from credential presence alone; or
- claim that availability improvements establish correction quality.

## Terms

**Checkpoint Original** is the exact Original accepted by the latest current,
successful cleanup result.

**Checkpoint Prepared** is the Prepared text returned for the Checkpoint
Original by that same successful result.

**Current suffix** is the exact remainder after removing Checkpoint Original as
an exact prefix of current Original.

**Provisional continuity** is Checkpoint Prepared followed by Current suffix.
It is a display and Outgoing fallback, not a provider result.

**Final failure** is a current cleanup request that ends without a valid result
after every eligible configured route is exhausted or a request-level terminal
failure occurs.

**Fallback recovery** is a valid Prepared result from a later configured route
after an earlier route failed.

**Route test** is an explicit diagnostic action that sends fixed synthetic text
once to each configured route independently of live cleanup routing.

## Continuity state model

### Checkpoint creation

A current cleanup result with status `prepared` or `unchanged` creates or
replaces one in-memory checkpoint for the active page draft. The checkpoint
binds:

- exact Original;
- exact Prepared;
- selected correction mode;
- prompt version;
- Smart task context; and
- enabled request evidence, including the effective Personal Corrections input.

A stale, superseded, aborted, malformed, rejected, timed-out, unavailable, or
failed result never creates or updates a checkpoint.

### Eligibility

Provisional continuity is eligible only when:

1. a checkpoint exists for the active page draft;
2. current Original starts with Checkpoint Original exactly;
3. correction mode, prompt version, Smart task context, and effective request
   evidence still match the checkpoint binding; and
4. the user has not selected Off or cleared or replaced the draft.

When eligible, compute the value without normalization:

```text
current_suffix = current_original[len(checkpoint_original):]
provisional_continuity = checkpoint_prepared + current_suffix
```

Sayloom must not insert, remove, normalize, or infer characters at the join.
Whitespace and punctuation in Current suffix remain character-for-character
equivalent to the browser's current Original value.

### Full-text reevaluation

Provisional continuity never changes the provider request boundary. Every
automatic rerun and explicit retry sends the complete current Original through
the selected full correction path. A successful full-current result may revise
earlier Prepared wording because later text supplies additional context.

On success, the full returned Prepared replaces provisional continuity and the
complete current Original and Prepared become the new checkpoint.

### Invalidation

Invalidate the checkpoint when:

- any character inside Checkpoint Original changes or is removed;
- Original is replaced or cleared;
- correction mode changes among Smart, Conservative, and Off;
- prompt version changes;
- Smart task context changes;
- enabled Personal Corrections or other effective request evidence changes; or
- the page reloads or the draft otherwise ends.

After invalidation, waiting or failed cleanup uses the complete current Original
until a new valid success establishes another checkpoint. Checkpoints are never
persisted across page reloads or application restarts.

### State transitions

| Event | Prepared surface | Default Outgoing | Checkpoint |
| --- | --- | --- | --- |
| No successful result yet | Current Original during waiting or failure | Original | Absent |
| Current full-text success | Full returned Prepared | Prepared | Replace with current pair |
| Eligible suffix change, waiting or running | Provisional continuity | Provisional continuity | Retain |
| Eligible suffix change, final failure | Provisional continuity | Provisional continuity | Retain |
| Eligible suffix change, later success | Full returned Prepared | Prepared | Replace with current pair |
| Prefix or request-contract change | Current Original during waiting or failure | Original | Invalidate |
| Off, Clear, replacement, or reload | Existing Off/Clear/replacement behavior | Original or empty | Invalidate |

An explicit per-draft Original selection always wins. Pending cleanup,
provisional continuity, retries, fallback recovery, and later success must not
switch Outgoing away from Original until the existing Clear or reload boundary
ends that override.

## Presentation and review behavior

Use written state, not color alone. While provisional continuity is active, the
Workspace identifies both its source and processing state:

- **Using previous Prepared + new Original — Cleanup in progress**
- **Using previous Prepared + new Original — Cleanup failed**

The Prepared surface remains visibly provisional until a valid full-current
success. It must not use an unqualified `Prepared` status for the mixed value.
Failure details retain the existing retry and safe-attribution behavior.

Provisional continuity:

- may be copied or delivered as the exact visible Outgoing value;
- is not a successful Prepared checkpoint;
- does not claim that Current suffix was corrected;
- does not create Smart lexical-repair review evidence for Current suffix; and
- remains retryable against the complete current Original.

Existing stale-response protections remain mandatory. No response for an older
Original, draft revision, correction mode, prompt, task context, or request
evidence may replace current Prepared, provisional continuity, Outgoing, or the
checkpoint.

## Failure coverage

Eligible provisional continuity applies while a request is waiting or running
and after:

- timeout;
- provider, network, transport, or HTTP error;
- malformed provider response;
- locally rejected output;
- temporary route unavailability or circuit-breaker exclusion; or
- exhaustion of every eligible route.

Request-level terminal failures remain terminal for provider routing. This
specification changes the local continuity fallback only; it does not make
safety-policy failures, invalid local requests, cancellations, or unknown
failures eligible for additional provider calls.

## Provider configuration contract

Cross-provider routing remains explicit. Credential presence alone does not
authorize sending text to another provider.

- A complete Gemini-only configuration remains valid and is labeled
  **Reduced resilience — no independent provider fallback**.
- A complete, acknowledged Gemini-to-OpenAI configuration exposes its exact
  sanitized provider/model order and fallback-enabled state.
- Any partial, invalid, or unacknowledged cross-provider configuration disables
  both Smart and Conservative provider processing. Original and eligible
  provisional continuity remain usable.
- Invalid configuration produces a persistent Workspace warning with the exact
  sanitized defect and repair guidance. Sayloom never silently degrades a
  partial cross-provider configuration to a different provider contract.

Each live cleanup route receives at most one request. Eligible route failure may
advance once to the next configured route within the existing fixed total
deadline and partitioned route budgets. No same-route retry may consume time
reserved for an independent fallback.

## Sanitized reliability history

Every local development state and the release profile keep separate reliability
history in their own external application database. Histories are never shared
across states or profiles and never enter Git, browser storage, or a hosted
telemetry service.

Records contain only the fields needed to distinguish configuration,
availability, and recovery:

- completion timestamp;
- correction mode;
- final status and failure class;
- total duration;
- ordered attempt route index, provider, model, outcome, failure class, and
  duration;
- whether fallback recovered the request; and
- whether the record came from live cleanup or an explicit route test.

Records contain no Original, Prepared, provisional continuity, Outgoing, prompt,
task context, Personal Correction content, provider payload, response body,
credential, request header, provider account identifier, private path, or
outgoing destination.

Retain no more than the latest 1,000 live cleanup requests and no record older
than 30 days. Apply both limits; satisfying one does not waive the other.
Provide an explicit **Clear history** action. Never transmit history
automatically.

Normal application startup continues to compare schema state without migrating.
Any reliability-history schema change uses the existing explicit migration and
controlled verify-then-restart workflow.

## Reliability status and warnings

The Workspace shows concise current status and persistent invalid or degraded
routing warnings. Cleanup settings owns detailed history, aggregate rates,
recent sanitized attempts, route testing, history clearing, and a copyable
sanitized report.

Warn:

- immediately when provider configuration is invalid;
- after three consecutive final runtime failures; and
- when three fallback recoveries occur among the latest ten completed live
  cleanup requests.

A fallback recovery counts as a successful Prepared result for overall
availability, a failure for the earlier route, and a recovery for the later
route. It does not count toward consecutive final failures.

**Assumption:** Reliability denominators and warning windows include only
current live cleanup requests that reach a final accepted result or final
failure. Empty, disabled, browser-cancelled, superseded, and stale requests do
not represent a user-visible completion and should not inflate those windows.
Implementation must preserve this distinction even if provider-attempt records
are written before the browser accepts a result.

The copyable report includes configuration status, ordered provider/model
routes, retention window, aggregate success/final-failure/fallback-recovery
counts, warning state, and sanitized recent attempts. It carries an explicit
statement that it contains no operating text. Copying is user-initiated; the
application does not upload or send the report.

## Explicit route testing

Cleanup settings provides **Test routes** as an explicit user action. Before
starting, disclose that the action sends synthetic text to external providers
and may incur paid calls.

One test run:

1. uses fixed, visibly synthetic text and a fixed bounded instruction;
2. calls each configured route exactly once, independently, even when an
   earlier route succeeds;
3. reports local configuration validity, authentication/access result, response
   validity, safe failure attribution, and latency for each route;
4. never displays provider response bodies, credentials, headers, or
   credential-bearing URLs; and
5. records results separately from live cleanup history.

Route tests must not open, close, reset, or otherwise mutate live route or quota
circuit breakers. They do not affect live reliability rates, consecutive
failure warnings, or fallback-recovery warnings. Sayloom may validate local
configuration automatically, but it never makes an automatic route-test call.

The existing temporary development-only provider-traffic session remains the
only ordinary mechanism in this scope that may place exact requests and
responses in logs. Improve its discoverability from development diagnostics,
but do not make it persistent or available in the release profile.

## Delivery slices

### Slice 1: continuity

Implement the page-session checkpoint and provisional continuity state in the
Workspace without adding durable text storage. Preserve the current full-text
request, stale-response, explicit Original selection, retry, repair-review, and
publication boundaries.

This slice is complete when pending and failed reruns no longer erase earlier
successful preparation for an eligible suffix change, and every invalidation
case safely returns to full Original.

### Slice 2: resilience evidence

Add the external-database migration, sanitized recording, retention, warnings,
Cleanup diagnostics view, copyable report, and explicit independent route
tests. Keep route-test records and breaker state separate from live cleanup.

This slice is complete when an operator can determine, without operating text,
whether cleanup is unconfigured, invalid, Gemini-only, recovering through
OpenAI, repeatedly failing on the primary, or exhausting every route.

## Acceptance criteria

### Continuity

- A first cleanup failure with no checkpoint uses full Original.
- After a successful asymmetric Original → Prepared transformation, appending a
  distinctive suffix shows exact `checkpoint_prepared + suffix` while waiting.
- Timeout, provider error, malformed response, rejected output, and exhausted
  routing preserve that same provisional value and select it as Outgoing.
- Copy and target delivery consume the exact visible provisional value without
  normalization or omission.
- The provider request still contains the complete current Original, not only
  the suffix.
- A later full-current success atomically replaces the provisional value and
  establishes the new complete checkpoint.
- Multiple suffix edits after a failure continue from the same checkpoint while
  its Original remains an exact prefix.
- An edit within the checkpoint prefix, replacement, Clear, Off selection,
  reload, or request-contract change invalidates the checkpoint and uses full
  Original until another success.
- Explicit Original selection survives pending work, failure, retry, fallback
  recovery, and later success.
- Stale and aborted responses cannot change the checkpoint, provisional value,
  Prepared surface, repair review, or Outgoing.
- Provisional state has written accessible status and never claims its suffix is
  Prepared.

### Configuration and routing

- Gemini-only configuration is valid and visibly reduced-resilience.
- Complete acknowledged Gemini-to-OpenAI configuration exposes both sanitized
  routes and permits bounded fallback for Smart and Conservative.
- Every partial or invalid cross-provider combination creates no provider
  clients, preserves Original or eligible provisional continuity, and shows the
  exact safe configuration defect.
- Live routing makes no more than one request per route and never extends the
  configured total deadline.
- Three consecutive final failures and three recoveries among the latest ten
  completed requests produce their distinct warnings.

### Privacy-safe evidence

- History is isolated by external development state or release profile,
  contains only the allowed metadata, and excludes every prohibited content
  field.
- Retention enforces both 1,000-record and 30-day limits, including asymmetric
  cases on either side of each boundary.
- Clear history removes the selected profile/state history without touching
  Personal Corrections, prompts, targets, or another state.
- The copied report is useful for provider attribution and contains no text,
  payload, credential, account identifier, destination, or private path.
- Normal startup never migrates the database.
- The raw provider-traffic mechanism remains temporary, actively locked,
  development-only, and behavior-neutral.

### Route testing

- The action requires a direct user gesture and a paid-call disclosure.
- Fixed synthetic content reaches every configured route exactly once,
  including a backup route after primary success.
- Success, authentication failure, quota failure, malformed response, timeout,
  and transport failure produce safe route-specific results.
- Test execution and failure do not mutate live circuit breakers, cleanup
  history, availability rates, or warning windows.
- No route test runs automatically during startup, configuration display,
  migration, restart, or ordinary cleanup.

## Remaining evidence boundary

Implementation and synthetic verification can prove the state machine,
retention, warning, privacy, and route-test contracts. They cannot establish why
the already observed stable failures occurred. After implementation, diagnosing
new incidents requires the retained sanitized history or a separately
authorized, isolated development reproduction using the existing temporary
provider-traffic session. Neither path authorizes inspection of historical or
stable private text.
