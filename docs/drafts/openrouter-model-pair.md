# OpenRouter model-pair integration and roadmap reconciliation

**Status:** Review draft, 2026-10-15. No normal-use qualification or paid execution authorized.

## Agreed direction

The owner selected `openai/gpt-4.1` and `openai/gpt-4.1-mini` as the initial
candidate pair through OpenRouter, targeting automatic primary/secondary fallback
if useful results fit the shared five-second application deadline. Model order
remains unselected. Round robin is not part of this delivery.

Source: [owner discussion and bounded implementation authorization](https://ampcode.com/threads/T-2f893922-15a9-4f75-a7f0-83d8e400f5ff).

## Evidence and roadmap impact

The [Nebius benchmark](https://ampcode.com/threads/T-331d5c0d-4485-4ac3-9019-bc99a1ea1574)
and [SiliconFlow benchmark](https://ampcode.com/threads/T-21bc69ea-eeed-4891-93f0-aa549ec762ba)
tested the same Qwen model, not two candidate models. Smart recovered 1/15 and
2/15 contextual repair cases respectively. Both showed substantial deletion of
repeated padding on longer inputs; rejection often preserved Original without
repairing it. These small, single-attempt synthetic runs do not establish real
user effort, a provider ranking, or normal-use qualification.

The [model-alternatives research](https://ampcode.com/threads/T-01a13bbf-8de2-729a-bb01-468f129c62ab)
recommends testing GPT-4.1 and Mini first from catalog and task-adjacent evidence.
Neither was empirically screened there. Its 30-second diagnostic proposal cannot
establish five-second application readiness; its proposed $25 allowance was not
approved and is not carried forward.

The installed Default prompt requests repetition removal while immutable runtime
contracts require preservation. This is a verified instruction conflict, but its
contribution to observed failures is unverified. Do not modify the immutable seed
bytes: installed databases verify its digest. Freeze and review effective prompt
composition before paid comparison; any prompt variant needs explicit scope and
invalidates affected prior evidence.

## Proposed roadmap reconciliation

For review before publication to the implementation plan and issues #159/#172:

> OpenRouter remains the integration direction. The owner has selected GPT-4.1
> and GPT-4.1 Mini as candidate models for a bounded comparison and experimental
> automatic primary/secondary path. This revises the initial single-model target,
> not serving-provider fallback: each model uses one explicitly selected endpoint
> with OpenRouter provider fallback disabled. Production order and feasible time
> allocations remain evidence decisions. No model, endpoint, local backup, or
> combined configuration is qualified. Preserve the shared five-second visible
> outcome deadline, measured local/validation/rendering reserve, existing privacy
> and permission requirements, and owner acceptance. Personal Corrections remains
> next after dependable preparation. Existing gates are not waived or completed.

Publish an amendment rather than rewrite the historical #172 resolution. Index
the new resolution from #159 only after review and authorized publication. This
draft does not mutate either issue or the Sayloom Project. Cross-provider recovery
requirements in #160/#162 remain independently outstanding; two models behind
one gateway do not establish them.

## Experimental implementation

The opt-in route reuses existing sequential orchestration and Original fail-open.
No same-model retries, round robin, endpoint substitution, or new learning/history
are added. Both models share an OpenRouter-account quota group: account throttling
or exhausted credit must not be bypassed by switching models. Eligible transport,
timeout, and invalid-output failures may advance; safety refusals, invalid requests,
cancellation, unknown errors, and unverifiable serving attribution stop.

Configuration is development-only and disabled unless explicitly selected:

| Variable | Required value or constraint |
| --- | --- |
| `LOCAL_TEXT_CLEANUP_ROUTE_ORDER` | `openrouter` |
| `LOCAL_TEXT_OPENROUTER_API_KEY` | Protected credential supplied outside Git; not configured here |
| `LOCAL_TEXT_OPENROUTER_MODELS` | Both exact candidate IDs, comma-separated in proposed attempt order |
| `LOCAL_TEXT_OPENROUTER_ENDPOINTS` | One explicit endpoint per model: `azure` or `azure/swedencentral` |
| `LOCAL_TEXT_CLEANUP_PAID_DATA_ACKNOWLEDGEMENT` | `paid-external-cleanup-v1` |
| `LOCAL_TEXT_CLEANUP_TIMEOUT_SECONDS` | Explicit positive cloud budget strictly below five seconds |
| `LOCAL_TEXT_CLEANUP_ROUTE_ATTEMPT_SECONDS` | Two positive allocations whose sum does not exceed the cloud budget |

There are deliberately no default models, endpoints, or deadline allocations.
Supported supplied text is at most 12,000 Python Unicode code points in total
across Original, task context, and supplied knowledge. No input is truncated.
Strict structured output, local parsing, lexical validation, source framing, and
existing Smart evidence boundaries remain in effect. Runtime contracts do not
guarantee semantic correctness or exact protected-quotation preservation.

Azure options come from dated research, not a new privacy approval or route
qualification. Requests enforce ZDR, parameter support, no data collection, and
one provider endpoint. Returned provider attribution must identify Azure or the
attempt stops. That name alone does not prove a specific regional endpoint;
actual endpoint attribution remains a qualification prerequisite. No raw
OpenRouter payload logging is enabled, including in development diagnostics.
No caching feature is added; these controls do not prove absence of provider-side
in-memory caching. Recheck dated policies and account eligibility before calls.

**Limitation:** A sub-five-second cloud budget leaves nominal room but is not a
measured end-to-end reserve. Local basic Cleanup is absent. This implementation
is not the complete deadline/local-backup contract and must not be activated for
normal use. No credentials, live configuration, or running application were changed.

## Next gates before use

1. Review this draft and the offline implementation. Separately authorize any
   commit, publication, or integration; do not treat this file as authorization.
2. Recover the exact approved fixtures from their source workspace. Freeze the
   comparison manifest and independently specified expectations. Include
   contextual wrong-word/multiword repair, legitimate-use and ambiguity controls,
   protected quotations/instructions, Unicode, and representative length bounds.
   Historical spelling/padding cases provide limited coverage only. Confirming
   intended wording does not automatically authorize evaluation reuse.
3. Recheck endpoint privacy, schema/cap compatibility, route attribution, and
   prompt versions. Present exact attempt count, conservative per-request cost
   reservations, stop rules and spending ceiling for approval before paid calls.
   The existing $2 qualification ceiling is conditional, not execution permission.
4. Compare each model independently; record correct useful results, harmful edits,
   missed repairs, abstention, fallback, full latency, and costs separately. Freeze
   role order only from results. A cheap or fast wrong answer cannot win.
5. Implement and measure local basic Cleanup on the target Mac. Freeze local,
   both-validation, rendering and margin bounds before allocating cloud attempts.
   If both cloud attempts cannot fit usefully, return for an explicit scope decision;
   do not extend the deadline or quietly remove the backup.
6. Verify the integrated path, including primary success, primary failure/rejection
   to secondary success, both failures, quota, cancellation and stale/late outcomes.
   Preserve the existing qualification repetition requirements and independent
   acceptance gates; no synthetic screen alone establishes normal-use acceptance.

Repository tests use synthetic HTTP transports and isolated databases. Passing
them proves implementation contracts only, not cloud capability, privacy policy,
five-second visible completion, local readiness, or owner usefulness acceptance.
