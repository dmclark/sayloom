# Privacy-safe runtime diagnostics

- **Status:** Consolidated draft for implementation review; not implementation authorization.
- **Prepared:** 2026-11-08.
- **Scope:** Content-free diagnostics for Sayloom cleanup requests.
- **Source baseline:** `8d2ccbd38396521a11704274064d0bdcc3983e48`.
- **Evidence:** [Diagnosis thread](https://ampcode.com/threads/T-01a1b88e-40e2-7117-bf13-64d411758ac5).
- **Decisions:** [Specification thread](https://ampcode.com/threads/T-01a1b8e9-e74e-73e4-a9bc-8649d0fcd4c0).
- **Implementation issue:** [#191](https://github.com/dmclark/sayloom/issues/191).

The owner's confirmed scope decisions are recorded below. Interface names,
enumerations, and mechanics are proposed requirements pending review. This
document authorizes no implementation, runtime operation, or credential repair.

## Purpose and evidence

Explain cleanup failures without inspecting dictated or prepared text, prompts,
stored passages, provider payloads, historical repair records, or credentials.
An owner should be able to correlate a UI error with a server operation,
distinguish attempted failures from unavailable routes and local capacity
rejection, and identify the process and source/build evidence involved.

The inspection snapshot showed attempted provider failures followed by
zero-attempt results. Source behavior supports exhausted routing: authentication
rejection disables routes, while transient and quota failures open breakers.
Live breaker state was not inspected. Exact UI requests could not be correlated
with logs, and health did not expose build identity. Last-route attribution did
not establish a sole root cause. These are snapshot findings, not assertions
about the current runtime.

Existing seams are `CleanupService`, `SequentialCleanupProvider`, `CleanupAttempt`,
`SafeError`, and `_log_cleanup` in [`cleanup.py`](../src/local_text/cleanup.py);
`/api/cleanup`, validation handling, and `/health` in
[`app.py`](../src/local_text/app.py); and the error dialog and copy helpers in
[`app.js`](../src/local_text/static/app.js).

## Confirmed scope decisions

1. Include full safe route outcomes, breaker states, observed cooldowns, and
   historical failure causes in the error dialog and copied details.
2. Reuse existing log retention. Document its limits; add no rotation mechanism
   or automatic-expiry guarantee.
3. Exclude input length and token counts from the new diagnostic projection.
   Preserve existing API fields and logging metadata separately.
4. Use clearly labeled startup checkout identity in development. Require
   immutable metadata for packaged-release identity.
5. Correlate every server-admitted cleanup HTTP request, including validation and
   configuration rejection, no-ops, and server-observed cancellation.

## Non-goals and authorization boundaries

- Do not change routing, fallback, deadlines, capacity, breaker behavior, or
  recovery policy; success when every route is unavailable is not guaranteed.
- Do not repair credentials, make paid probes, or integrate separate resilience
  work merely to implement diagnostics.
- Do not add a dashboard, telemetry service, diagnostics database, or diagnostic
  history endpoint.
- Do not claim that whole service logs are safe to share.
- Do not add first-pass Voiceitt access or infer which recognition pass caused
  an error.
- Use synthetic fixtures for verification. Implementation does not authorize
  private operating-data access, database writes against existing app state,
  app restarts, settings changes, deployment, or provider spending.

## Existing surfaces and compatibility

| Surface | Proposed extension |
| --- | --- |
| `POST /api/cleanup` | `X-Request-ID` header and versioned `diagnostics` object. |
| Existing error dialog and Copy details | Validated full diagnostic projection. |
| Existing `cleanup_result` log event | Correlation and allowlisted diagnostic projection. |
| `/health` and startup log | Process and source/build identity. |

Preserve normal result statuses, public cleanup error codes, result attribution
fields, and completed-attempt semantics. Do not use legacy provider/model
attribution as the explanation for request-level rejection.

The projection is not a serialized `CleanupResult`: that response contains text,
and its existing attempts include usage counts excluded from the projection.
Existing log metadata can coexist with a nested `diagnostics` projection; this
does not certify all legacy fields or whole log files under the new allowlist.

## Request correlation and ownership

A cleanup-scoped ASGI request boundary owns correlation and the terminal event
for exact-path `POST /api/cleanup`. It must operate before validation and body
parsing, without buffering or logging the body. It does not instrument other
endpoints or transport failures that never enter the application.

- Generate an opaque random `request_id`; do not trust supplied IDs or derive
  IDs from text, accounts, credentials, database records, or private paths.
- Return the ID in `X-Request-ID` and structured diagnostics. A retry gets a new
  ID. Route observations and the terminal event share the operation's ID.
- Record UTC RFC 3339 start and completion timestamps with millisecond precision.
  Use monotonic time for elapsed durations and cooldowns.
- Move terminal emission to the request boundary rather than emitting a second
  service-level terminal event. Service and router code contribute typed safe
  facts through request-scoped state; never recover them by parsing a response.
- Emit one terminal record for success, no-op, rejection, unexpected failure, or
  observed cancellation. Process death or logging failure can prevent emission;
  the absence of a record proves neither non-arrival nor non-execution.
- Response diagnostics are finalized before serialization. Their `completed_at`
  and `duration_ms` describe outcome finalization, not response transmission.
  A normal terminal log reuses those values. If transmission subsequently fails
  or is cancelled, the terminal log records that later outcome with the same
  request ID; it cannot revise an already serialized response. Correlation does
  not require those late-failure fields to equal the earlier response fields.
- Before response headers, unexpected errors can produce the fixed safe 500
  response below. After headers start, never attempt a second response; record
  the failure safely. Do not broaden unrelated exception handling.
- Preserve stale-response protection. Copy server UTC time; localized browser
  time may supplement it but cannot substitute for it.
- If headers arrive but the body is unreadable, retain the header request ID
  while marking further diagnostics unavailable. With no headers, verified
  server correlation is unavailable; do not assert that no server work occurred.

## Diagnostic projection version 1

### Operation summary

| Field | Contract |
| --- | --- |
| `schema_version` | Integer `1`. |
| `request_id` | Server-generated random operation identifier. |
| `process_instance_id` | Random identifier created once per process. |
| `started_at`, `completed_at` | Server UTC entry and outcome-finalization timestamps. |
| `duration_ms` | Nonnegative entry-to-finalization duration; rounded zero is valid. |
| `response_http_status` | Selected local response status, or `null` when none was selected; not a delivery acknowledgement. |
| `result_status` | Existing cleanup status, or `request_rejected`, `internal_error`, `cancelled`. |
| `termination_reason` | Fixed reason defined below. |
| `routing_configuration_status` | `configured`, `unconfigured`, `invalid`, or `unknown`. |
| `attempts` | Safe projection of completed provider-call records. |
| `route_decisions` | Ordered observations for the available route inventory. |

Proposed termination reasons:

- `completed`: successful prepared or unchanged result.
- `empty_input`: no cleanup needed for empty input.
- `cleanup_disabled`: the request explicitly disabled cleanup.
- `provider_unconfigured`: no active provider configuration.
- `configuration_invalid`: cleanup routing configuration is invalid.
- `local_capacity_full`: local admission failed before route evaluation.
- `all_routes_unavailable`: no adapter call started and every route was blocked.
- `attempts_exhausted`: at least one completed call failed, no route succeeded,
  and routing exhausted the remaining choices, including blocked choices.
- `terminal_failure`: a completed failure stopped routing by policy.
- `deadline_exhausted`: remaining time prevented further work.
- `request_rejected`: HTTP validation, setup, or prompt lookup rejected the request.
- `cancelled`: the server observed cancellation.
- `unknown`: evidence does not support a more specific reason, including an
  unexpected request-boundary failure.

Use the actual stopping decision: deadline and terminal policy stops take
precedence over generic exhaustion. Do not infer reasons from elapsed time or
legacy attribution. Distinguish explicit disablement from absence of a provider,
while retaining the existing `disabled` result status for compatibility.

### Attempts and interrupted execution

The new attempt projection permits only `route_index`, validated `provider` and
`model`, `outcome`, `elapsed_ms`, normalized `failure_class`, allowlisted
`provider_code`, `http_status`, and `retry_after_seconds`. Keep existing success
and failure outcomes; omit input length and token counts.

Empty `attempts` means no completed attempt record is available. It does not by
itself establish that no call started. An interrupted route is represented in
`route_decisions`, not as a fabricated completed attempt. Preserve completed
prior attempts when a later call is interrupted.

Entering adapter execution does not prove bytes reached a remote service.
Cancellation does not prove that the remote service stopped processing.

### Route decisions and gates

Each available configured route has:

- `route_index`, validated `provider`, and validated `model`.
- `disposition`: `attempted` for completed execution, `interrupted` for execution
  cancelled before a completed outcome, `skipped_unavailable`, or `not_evaluated`.
- `not_evaluated_reason`: nullable fixed value: `local_capacity_full`,
  `prior_success`, `terminal_failure`, `deadline_exhausted`, `request_rejected`,
  `cancelled`, or `cleanup_not_requested`.
- `observed_at`: route-decision timestamp, or `null` when not evaluated.
- `gates`: actual route-breaker and quota-breaker observations, in evaluation order.

Each gate observation contains:

| Field | Contract |
| --- | --- |
| `scope` | `route` or `quota_group`; exclude the internal quota-group identifier. |
| `state` | `closed`, `open`, `half_open`, `permanently_disabled`, or `unknown`. |
| `blocking_reason` | `cooldown`, `permanently_disabled`, `half_open_probe_occupied`, or `null`. |
| `remaining_cooldown_ms` | Nonnegative timed-cooldown remainder, otherwise `null`. |
| `cause` | Nullable safe failure metadata establishing this blocking state. |

A cause contains only normalized failure class, provider HTTP status, allowlisted
provider code, observation timestamp, and originating request ID when known.
Preserve the cause establishing the current state, not an unrelated later
failure. Shared quota causes can originate from another route/request; label
them as historical shared-gate evidence, never a current attempt by this route.

Capture observations during actual routing decisions. If the route gate blocks,
do not invent a quota-gate observation. Do not acquire probes, mutate breakers,
or perform network calls for diagnostics. Observations are time-specific, not
an atomic global snapshot. Interrupted execution retains admission observations
without inventing provider outcome or HTTP status.

### Configuration, missing values, and bounds

- `configured` means a validated route inventory is available; `unconfigured`
  means no active provider configuration; `invalid` means validation failed;
  `unknown` means inventory cannot be established.
- Interpret an empty route list using this status. Do not manufacture routes
  from invalid settings. If inventory exists but work is rejected, mark its
  routes not evaluated.
- Use `null` for unavailable/not-applicable optional values, not zero, HTTP 200,
  or an inferred cause. Use fixed safe placeholders for invalid identifiers.
- Preserve current provider/model identifier validators and static model
  allowlists; never emit arbitrary configured strings on validation failure.
- Provider HTTP statuses must be integers in 100–599, excluding booleans.
  Durations must be finite nonnegative integers; retry-after values retain the
  existing 0–86,400-second bound. Counts of route records follow the validated
  configured inventory, not caller-supplied arrays.
- For missing/unsupported diagnostic versions, show Diagnostic detail unavailable.

### Provider-code allowlist

Permit these internal normalized codes:

`unknown`, `transport_error`, `timeout`, `missing_api_key`, `malformed_response`,
`safety_policy`, `rejected_output`, `circuit_open`, `bulkhead_full`,
`total_deadline`, `route_mismatch`.

Permit these known external codes:

`invalid_api_key`, `credit_balance_exhausted`,
`organization_spend_limit_exceeded`, `organization_usage_limit_exceeded`,
`project_spend_limit_exceeded`.

Permit generated `http_<status>` only from a validated numeric provider error
status in 400–599. Unknown external codes become that generated code when
possible, otherwise `unknown`. Identifier-shaped arbitrary codes are not safe
by default. Projection normalization does not change routing classification or
legacy API fields.

## Cleanup HTTP error envelope

Normal cleanup responses retain their contract and gain `diagnostics`.
Cleanup-specific HTTP errors use this shape:

```json
{
  "detail": {
    "code": "invalid_cleanup_request",
    "message": "The request did not match the cleanup contract.",
    "retry_action": "Review the request and retry cleanup."
  },
  "diagnostics": {}
}
```

The empty object above stands for the complete versioned projection, not a
permitted production omission. Messages and recovery actions are fixed strings.

| Condition | HTTP status | Safe code | Diagnostic result status |
| --- | --- | --- | --- |
| Invalid body or request contract | 422 | `invalid_cleanup_request` | `request_rejected` |
| Missing schema or required app setup | 503 | `cleanup_setup_required` | `request_rejected` |
| Missing selected prompt | 404 | `prompt_version_not_found` | `request_rejected` |
| Unexpected request-boundary failure | 500 | `cleanup_internal_error` | `internal_error` |
| Observed cancellation | No response guaranteed | No error response required | `cancelled` |

Never include validation input, raw exceptions, submitted IDs, or schema values
in this envelope. Apply this handling only to cleanup; do not change unrelated
API validation contracts. Invalid routing configuration retains current normal
fail-open behavior rather than inventing a new HTTP rejection.

## UI and copied details

Extend the existing cleanup error dialog and copy action, not a new screen.
Include full safe correlation, route, gate, cooldown, and historical cause
details. Show current attempts separately from historical causes. Do not use
the legacy result model as a failed-provider heading for request-wide rejection.

For zero-call exhausted routing, use wording equivalent to:

> No provider call started. All configured routes were unavailable when checked.

Label cooldowns remaining at observation; they are not recovery promises.
Permanent disablement must not recommend waiting alone. Select recovery wording
from fixed safe templates, distinguishing temporary, permanent, mixed, and
unknown availability. Credential repair remains a separate operational action.

Render validated fields as text, never HTML. Copy only explicit projection
fields, not generic response/error serialization. Exclude usage counts, content,
and arbitrary extra fields. Retain existing Original fallback, recovery controls,
and in-memory error lifecycle. Do not fetch current health and present it as
proof of which process served an earlier error: correlate process IDs.

## Process and build identity

Add an identity object to `/health` and the safe startup log:

- `process_instance_id`: random once per process.
- `started_at`: app-process initialization timestamp, not claimed OS birth time.
- `application_version`: trusted package version, or `null` when unavailable.
- `source_revision`: full commit SHA or `null`.
- `source_state`: `clean`, `modified`, or `unknown`.
- `build_id`: immutable packaged artifact identifier or `null`.
- `identity_basis`: `packaged_build`, `startup_checkout`, or `unknown`.

The development launcher explicitly selects the checkout's `src` with Uvicorn
`--app-dir`, without reload. Capture identity once inside the app process and
verify association between the imported module and checkout before reporting
startup checkout identity. Git inspection may read revision and change flags,
but must not emit paths, filenames, or diffs. Later health requests do not query
current HEAD. Uncertain provenance becomes unknown.

Startup checkout identity is limited evidence, not proof of exact loaded code.
This remains true for a clean checkout because launch/import races are possible.
Packaged identity must use embedded immutable artifact metadata; application
version and the static-asset hash are not substitutes. No metadata producer
exists in the inspected packaging/CI. Until supplied, report no immutable build
assurance. Adding a release pipeline is not part of development diagnostics.
Keep health readiness semantics unchanged.

## Privacy, access, and retention

- Construct records with explicit typed allowlists. Do not fall back to dumping
  raw objects when diagnostics fail.
- Exclude content, content hashes, prompts, passage/repair IDs, payloads, URLs,
  headers, response bodies, raw exceptions, tracebacks, credentials, credential
  fingerprints, private paths, usernames, hostnames, and repository remotes.
- Permit only approved technical identifiers, random IDs, timestamps, enums,
  bounded numeric metadata, and build metadata. Input length and token counts
  remain outside the new projection.
- Do not enable or depend on `--provider-traffic`.
- Label copied details content-free but operationally sensitive.
- Add no database, browser local storage, external telemetry, history endpoint,
  new network exposure, or broader filesystem permissions.
- Set `Cache-Control: no-store` on diagnostic-bearing cleanup and health responses.
- Diagnostic serialization/logging failure must not change cleanup results,
  routing, probe ownership, fallback, or cancellation propagation.

Repository service setup assigns log-directory mode `0700` and log-file mode
`0600`. No repository-defined age limit, size cap, or automatic rotation was
found. Explicit development-state removal deletes its logs with the state.
Logs may otherwise remain indefinitely. Preserve this lifecycle without adding
expiry guarantees, rotation, or deletion machinery. Current machine permissions,
external rotation, backups, clipboard retention, and OS policies are unverified.

Whole logs can contain legacy metadata or content from other logging modes.
Only selected new diagnostic projections satisfy this contract; do not describe
an entire service log as safe to share.

## Acceptance criteria and verification

Use synthetic fixtures and the existing test files; no paid probes or private
operating data. Extend tests through public request/result behavior wherever
possible. Diagnostics verification must not depend on provider-content logging.

1. Concurrent operations and retries have distinct IDs. Header, response body,
   copied details, and terminal log agree on identity and normal finalized
   outcome. Late transmission failure remains correlated but may supersede the
   earlier outcome in the log. Stale responses cannot replace current details;
   unreadable bodies retain an available header ID.
2. After synthetic authentication disablement and another route's cooldown, a
   subsequent zero-call request reports all routes unavailable, both blocking
   explanations, and historical causes without blaming the last route alone.
3. Full local capacity yields no calls and not-evaluated routes, not invented
   cooldowns. Half-open contention identifies occupied probes without acquiring
   another probe or changing ownership.
4. Mixed attempted/skipped routing preserves actual completed attempts and
   separate skip evidence. Shared quota causes retain their originating request
   rather than becoming new attempts. Backup success preserves prior evidence.
5. Deadline and terminal policy stops remain distinct from route unavailability.
   Empty input, explicit disablement, absent provider, invalid routing, and
   pre-cleanup HTTP rejection have distinguishable reasons.
6. Observed cancellation preserves completed prior attempts and marks an active
   route interrupted without fabricating its outcome or implying remote stop.
   Exactly one terminal event is emitted when handling finishes normally or by
   observed failure/cancellation; hard process termination is not guaranteed.
7. Validation/setup/prompt errors use the cleanup-only fixed envelope and IDs.
   Unexpected errors are content-free; failures after headers never send a
   second response. Local and provider HTTP statuses remain separate.
8. Missing cause/status/identity stays unknown/null. Rounded zero duration is
   not used to infer rejection. Invalid routing never fabricates a valid inventory.
9. Process IDs change after restart. Startup identity stays fixed after checkout
   changes. Development identity does not claim immutable loaded-code proof;
   absent packaged metadata cannot produce packaged-build assurance.
10. Synthetic sentinels in content, prompts, errors, payloads, credentials, paths,
    and unrecognized identifier-shaped codes cannot enter new diagnostics or
    copied details. Projection fields exclude usage counts and unknown fields.
11. Existing routing, deadlines, call counts, fallback, public cleanup error codes,
    and normal API fields remain unchanged. Existing tests pass with intentional
    logging/response additions, not suppressed failures.
12. Diagnostic-bearing responses are not cached. UI rendering uses text and
    preserves accessible dialog/copy behavior and recovery controls.

Relevant checks are `uv run ruff check .` and affected tests in
`tests/test_cleanup.py`, `tests/test_cleanup_router.py`, and `tests/test_app.py`.
Before implementation UI verification, follow
[`ui-verification.md`](agents/ui-verification.md): use isolated synthetic state,
desktop scope, and inspect the affected error/copy interaction and rendered
states. Tests that simulate providers must demonstrate no extra calls caused
by diagnostics. No normal startup database migration is permitted.

## Remaining limitations and delivery

There are no remaining owner questions about the five confirmed scope choices.
Exact implementation mechanics remain subject to review and the no-behavior-change
constraint. Operational facts about the current machine and future packaged
release provenance remain explicitly unknown; they are not reasons to inspect
private operating data.

This specification and a linked implementation issue are separate from permission
to implement, restart, deploy, or repair credentials. The owner approved public
publication of this specification and its implementation issue. Implementation
remains subject to separate authorization and review of this contract; publishing
the documentation does not start implementation or change the running app.
