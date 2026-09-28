# Source-preserving cleanup benchmark and canary protocol

- **Protocol:** `cleanup-evaluation-benchmark-v2`
- **Status:** Historical and non-operational; retained for provenance only
- **Approved:** 2026-09-09
- **Machine-readable authority:**
  [`cleanup-evaluation-benchmark-v2.json`](cleanup-evaluation-benchmark-v2.json)
- **Supersedes:**
  [`cleanup-evaluation-benchmark-v1.json`](cleanup-evaluation-benchmark-v1.json), preserved unchanged
  as history
- **Scope:** Current source-preserving cleanup only; no rewrite, Smart correction, transcript
  fidelity, stable routing, or provider promotion

> **Historical document:** The benchmark and canary implementation described
> here has been removed. This protocol is not current evaluation authority and
> does not describe an available workflow or authorize private-data access,
> provider calls, spending, or operation. See the
> [current evaluation map](../evaluation-mvp-map.md) for current authority.

The superseded protocol defined the prerequisites for one offline 60-case paired benchmark and, only after
that benchmark passes, eligibility to request separate authorization for one 10-user-initiated-
cleanup non-shadow canary. Approval of this document authorizes neither implementation nor
operation. A runner, private-corpus access, credentials, provider calls, spending, canary, routing
change, or stable-product change requires its own applicable approval.

## Decision and version-one audit

The chosen disposition is to evaluate current source-preserving cleanup. This answers the bounded
product question: whether paid OpenAI `gpt-5.6-luna`, manually chosen in a pilot, produces less
cleanup correction effort than the paid Gemini `gemini-3.7-flash` baseline without unacceptable
quality, safety, reliability, latency, privacy, or cost regression.

The alternatives do not win. A rewrite arm would test a product mode that does not exist and would
cross into wording changes rejected by the shipped validator. Stopping without a study would discard
a bounded comparison that can answer the manual-candidate question without changing stable behavior.
Neither cleanup output nor its user-confirmed expected value establishes transcript truth.

Version 1 is superseded because:

- its grammar, general-disfluency, recognition-like-correction, and broad mixed categories conflict
  with the shipped lexical source-preserving boundary;
- its routed arm and 12-second/8-second/20-second budgets do not answer the chosen single-candidate
  question, while shipped cleanup retains a shared 30-second request deadline;
- “current Gemini baseline” does not freeze prompt bytes, request settings, schema, validator, or
  provider-reported model version;
- its possible expansion from 60 toward 300 permits post-result sample growth;
- its 10/25/100 canary progression exceeds the approved finite 10-cleanup canary; and
- its 2026-08-26 provider snapshot is entry evidence to refresh, not a fact to assume later.

Current shipped code has the chosen model names and settings. That fact does not replace the
required provider-evidence refresh. `src/local_text/correction_benchmark.py` evaluates the separate
Smart-correction pipeline and must not be imported, reused, or described as the cleanup runner.
Cleanup Gates 1–6 are implemented; no cleanup benchmark runner or canary currently exists.

## Evidence boundary

The population is user-confirmed, dictation-derived **Original** text paired with a
user-confirmed expected polished cleanup. Expected cleanup is evidence for source-preserving
polishing only. It is never a faithful-transcript label, correction episode, personalization record,
analytics event, or training consent. Audio, inferred private identity, and transcript-truth claims
are outside this protocol.

## Eligibility, annotation, and selection

Before selection, the corpus owner reviews without benchmark outputs and freezes each eligible
case's source category, revision, consent, retention state, prompt provenance, record checksum,
one primary stratum, and every applicable overlapping challenge tag. Source category must be
`dictation`; Original and expected cleanup must be present, current, and user-confirmed.

Every difference from Original to expected cleanup must be one or more of:

- capitalization;
- punctuation;
- apostrophes;
- whitespace or paragraph structure.

Every lexical word, including a filler such as “erm,” “hmm,” “uh,” or “um,” must remain in its
original order. Any addition, removal, substitution, duplication, or reordering of a word makes the
case ineligible. Ambiguity or dependence on transcript truth also makes it ineligible.

The exact mutually exclusive primary composition is:

| Primary stratum | Cases |
| --- | ---: |
| Unchanged | 10 |
| Capitalization only | 8 |
| Punctuation only | 8 |
| Apostrophe only | 8 |
| Whitespace/paragraph only | 8 |
| Filler presentation only | 8 |
| Mixed permitted transformations | 10 |

The same set must meet all overlapping minima:

| Challenge tag | Minimum |
| --- | ---: |
| Names/technical terms | 12 |
| Numbers/dates | 12 |
| Negation/modality | 12 |
| Links/code/identifiers | 8 |
| Quotations | 8 |
| Line/paragraph structures | 8 |

For duplicate detection only, normalize Original to Unicode NFC and LF line endings. Preserve the
actual stored text bytes for execution. Cases with identical canonical Original form a duplicate
group. If group members disagree on expected cleanup or primary stratum, exclude the entire group;
otherwise the lowest opaque case ID represents it.

After freezing the eligible pool, generate and record an integer selection seed. Derive each
representative's key as SHA-256 over a domain separator, seed, frozen-pool SHA-256, and case ID.
Among all 60-case subsets satisfying every exact count and minimum, select the subset whose sorted
key vector is lexicographically smallest; break a remaining tie by its sorted case-ID vector. Report
the algorithm version, inputs, duplicate decisions, and selected ordering. An infeasible quota blocks
registration. Never relax a quota, hand-pick around the seed, or expand beyond 60.

Before registration, removing a deleted, expired, withdrawn, or newly ineligible case causes a new
pool freeze and deterministic selection. After registration but before the first provider call, it
invalidates the manifest and requires new registration and confirmation. After any provider call,
it stops and invalidates the run. There is no replacement, selective exclusion, or selective rerun.

## Arms and request contract

Run exactly two single-model arms once per case:

| Arm | Provider/model | Required settings |
| --- | --- | --- |
| Baseline | Paid Gemini `gemini-3.7-flash` | thinking level `low`; no explicit temperature |
| Candidate | Paid OpenAI `gpt-5.6-luna` | reasoning effort `none`; `store:false` |

Both arms use the same frozen effective system-prompt bytes, source framing, strict response schema,
shipped semantic validator, and shipped input-dependent output-cap algorithm. Both have equal
30-second deadlines. There is one request per case per arm and no retry, fallback, route arm, rewrite
arm, or post-result expansion.

Freeze requested model IDs, provider-reported versions when available, endpoint/API mode, settings,
prompt and framing bytes and hashes, schema bytes and hash, adapter and validator versions/hashes,
output-cap algorithm, scoring commit, and dependency lock. Within 24 hours before registration,
reverify official model availability, pricing, retention/data-use terms, account controls, and
`store:false` behavior. Record official URLs and retrieval times. Any material change blocks
registration and requires review.

## Roles, isolation, and entry

The protocol owner approves this protocol and each later authorization. The corpus owner alone
determines eligibility/annotations and conducts every human review. A named run operator administers
the isolated run. One person may hold multiple or all roles, but every assignment is explicit in the
manifest.

Entry requires a purpose-built cleanup runner at a reviewed, immutable, clean commit. Its tests must
prove deterministic selection, case and arm ordering, bootstrap resampling, fail-open scoring,
pre-send budget stops, privacy-safe logging, lifecycle deletion, and interruption recovery. It must
not reuse the Smart-correction benchmark.

Use dedicated paid test credentials and provider-project identities. The runner, imported snapshot,
results, logs, caches, temporary files, pilot service/state, configuration, storage, and delivery
identity are separate from stable operation and the live corpus. Stable resources must be
inaccessible. Logs contain safe identifiers and metadata only—never case, prompt, output, payload,
credential, provider/account identifier, or private path.

Preflight verifies the immutable code and configuration, provider evidence, account controls,
quotas, both cost ceilings, conservative request bounds, local permissions, deletion path, clock,
free space, and 120-private-call capacity without sending private text.

## Budgets and synthetic smoke

The combined ceiling for all synthetic smoke attempts and the benchmark is **$10 USD**. Reserve the
full conservative 120-call benchmark bound before allocating the remainder to smoke. The later
canary has a separate **$2 USD** ceiling. There is no overage, top-up, borrowing, or transfer.

Use integer USD micros for bounds, returned usage, and accumulated cost. Before sending any request,
stop if its conservative bound could exceed the applicable remaining ceiling. An actual breach is a
protocol failure even if the pre-send bound passed.

Before private execution, freeze eight wholly synthetic cases: one for every primary stratum and one
combined preservation challenge containing invented names, numbers, negation, quotation,
identifier/link, and paragraph structure. Run all eight once per arm, for 16 calls. Every call must
use the registered prompt, schema, adapter, validator, settings, output cap, and 30-second deadline;
report the expected attribution and parseable usage; remain within the smoke allocation; and produce
validator-accepted source-preserving output with no severe harm or disclosure/storage violation.

Any smoke failure blocks private execution. After diagnosis and correction, smoke may restart only
as a complete newly registered 16-call suite within the unchanged $10 ceiling and after reserving
the private-run bound. Selective smoke reruns are prohibited.

## Registration manifest and consent

The canonical JSON defines the complete manifest schema. Registration freezes and hashes at least:

1. protocol ID/version/hash/status and the superseded-v1 reference;
2. timestamp, role identities, environment identity, runner/scoring commit, dependency-lock hash,
   and clean-tree verification;
3. eligible-pool hash, selection inputs and algorithm, selected case IDs/revisions/record hashes,
   strata/tags, duplicate decisions, annotation hash, and corpus-snapshot hash;
4. configured and effective prompt IDs/text bytes/hashes, framing bytes/hash, schema bytes/hash and
   version, validator version/hash, and output-cap algorithm/version;
5. arm IDs, providers/models/reported versions, endpoints/API modes, request settings, deadlines,
   no-retry/fallback declaration, and case/arm ordering seeds and algorithms;
6. official-source URLs/times, availability, pricing in USD micros, retention/data-use disclosures,
   account controls, and material-change determination;
7. smoke fixtures, hashes, classifications, seed, and results;
8. normalization/scoring definitions, 10,000-resample bootstrap seed/algorithm, review-rubric hash,
   blinding seeds, harmful taxonomy, and every gate;
9. the $10 budget, conservative bounds, reservation calculation, and stop rules;
10. exact run confirmation, hold, local locations, artifact inventory, lifecycle events, and an
    append-only execution/review/unblinding/report ledger.

Missing or changed frozen data invalidates registration. A provider-reported version first observed
during execution is appended as an observation; disagreement with registered evidence stops the run
rather than mutating frozen fields.

Run confirmation is separate from corpus-save consent. Immediately before execution, it must name
the exact 60 case IDs and revisions, providers/models, effective prompt, maximum 120 private calls,
current provider disclosures, conservative estimate and $10 cap, one named benchmark hold, fixed
release, and every local snapshot/run/report/export location. The hold releases no later than 30
days after confirmation.

Imported snapshot and run artifacts never write back to the corpus. They are deleted at completion,
cancellation, withdrawal, or fixed release, whichever occurs first, after an optional explicit
private local export. Withdrawal stops new calls and deletes managed artifacts but cannot retract
requests already processed by a provider. No consent here covers transcript truth, personalization,
analytics, training, or external sharing.

## Execution, interruption, and hard stops

Execute cases in frozen seeded order. Complete each case's frozen seeded arm order before advancing.
Persist a transactional request reservation before send and one terminal result immediately after.

An interrupted run may resume only if the ledger proves each prior request was never sent or has one
durable terminal result that will not be repeated. Resume also requires an unchanged manifest, valid
consent and hold, intact isolation, provider evidence still within 24 hours, and enough budget. A
possibly sent request without a durable terminal result invalidates the run.

Stop new calls and mark the benchmark non-passing upon:

- withdrawal, cancellation, consent/hold invalidity, or selected-case mutation/deletion;
- manifest, hash, code, configuration, or provider-reported model mismatch;
- isolation, disclosure, text-logging, storage, write-back, or stable-resource violation;
- inability to reserve the next request, an actual budget breach, or missing/malformed usage;
- permanent credential, configuration, or quota failure;
- three consecutive operational failures in either arm: timeout, transport/5xx, temporary quota,
  or unknown system failure;
- evidence that an impermissible output bypassed the validator; or
- an ambiguous in-flight request after interruption.

Validator rejections and safety refusals are scored outcomes, not operational-stop events. No
completed request may be rerun. A stopped run requires a new protocol version where the protocol
itself changes, and always requires a new manifest, hold, current disclosures, budget, and explicit
confirmation before a wholly new run.

## Scoring and blinded review

The primary endpoint is paired normalized Unicode code-point Levenshtein effort from each arm's
user-visible result to expected cleanup. For scoring only, normalize both strings to Unicode NFC and
LF line endings; preserve every other code point, including spaces and paragraph breaks. Per-case
effort is distance divided by `max(expected code-point length, 1)`. The arm statistic is the
arithmetic mean over the same 60 cases.

Failure, timeout, refusal, malformed or rejected output, and deadline breach score as fail-open
Original. Valid-output success means a response arrived within 30 seconds, matched the frozen
schema, and passed the shipped validator. An accepted unchanged result is successful.

The corpus owner reviews all 120 user-visible outputs individually in seeded random order with arm
and provider hidden. For each, freeze:

- acceptability: `acceptable` or `unacceptable`;
- accepted source-contract violation: `yes` or `no`;
- harmful category: `none`, `meaning`, `invented_content`, `qualification_or_negation`,
  `number_or_date`, `name_or_technical_term`, `link_code_or_identifier`, `quotation`, or `layout`;
- severity: `none`, `non-severe`, or `severe`; and
- a concise local rationale.

A severe change materially alters meaning, obligation, permission, negation, factual value,
identity/term, executable identifier/code/link, quotation attribution, or usable document structure.
Lesser real damage is non-severe. Then review seeded, anonymized, side-randomized A/B pairs against
Original with choices `a`, `b`, `tie`, or `neither`. Pair preference is descriptive. Freeze all
individual and pair reviews before a one-time unblinding. Any unresolved review blocks passage.

## Benchmark gates, report, and disposition

All gates are required:

1. Candidate mean effort is at least 10% below baseline mean effort.
2. The one-sided 95th-percentile upper bound from 10,000 paired bootstrap resamples is no greater
   than 5% relative candidate degradation.
3. Candidate valid-output success rate is no more than 5 percentage points below baseline.
4. The candidate has zero accepted source-contract violations.
5. The candidate has zero severe harmful changes.
6. Candidate p95 latency increase is no greater than the larger of 20% of baseline p95 and 1 second.

Freeze the bootstrap seed. For each paired resample, compute
`(candidate_mean - baseline_mean) / baseline_mean`. A resample with zero baseline mean is zero only
when candidate mean is also zero; otherwise it is positive infinity. If observed baseline mean is
zero, stop with no canary. Compute p95 by nearest rank over 60 end-to-end durations, recording a
30-second duration for a timeout.

After review freeze, unblind once and report complete flow accounting, per-arm and paired metrics,
the confidence bound, valid-output rates, contract violations, harms, nearest-rank latency, usage,
cost, failures, descriptive strata and preference, protocol deviations, and every gate with its
numerator, denominator, value, and disposition. Keep the report private and local. Secondary results
cannot compensate for a failed gate.

Do not selectively rerun or omit cases, replace outcomes, alter thresholds, or expand the sample.
Only an all-gates pass creates a signed local eligibility packet containing manifest/report hashes,
gate results, deviations, deletion status, and exact candidate configuration. Fail, invalid, stopped,
or unresolved means no canary.

## Separate canary authorization

Benchmark passage does not start or configure a canary. Before managed benchmark deletion, the user
must explicitly export the private eligibility packet/report if it will support a canary request.
Then obtain a new explicit confirmation naming:

- the passed manifest/report hashes;
- paid OpenAI `gpt-5.6-luna`, exact reported version, effective prompt/schema/validator/settings,
  and 30-second deadline;
- candidate-only manual requests, maximum 10 calls, and no baseline, duplication, retry, fallback,
  routing, or shadow processing;
- provider availability and retention/data-use disclosures refreshed within 24 hours;
- the $2 estimate/cap and pre-send enforcement;
- the 14-day administration dates, temporary evidence, fixed deletion time, and every local storage
  location; and
- withdrawal behavior, including inability to retract already processed provider requests.

Corpus-save and benchmark confirmations do not satisfy canary confirmation.

## Ten-cleanup canary

Run one isolated pilot until the earlier of 10 counted attempts or 14 calendar days after
confirmation. Each counted cleanup must be newly user-initiated in the pilot, explicitly confirmed
as dictation-derived, locally valid, unique within the canary under NFC-plus-LF Original hashing,
and manually directed to the named candidate. Send exactly one candidate request. It counts whether
it succeeds, fails, times out, is refused, or is rejected. Never call Gemini or a second model, retry,
fallback, route, shadow, or resend that Original. Invalid or duplicate input is rejected locally and
does not count. Fewer than 10 attempts by the deadline is incomplete and cannot pass.

After each counted attempt and before permitting another, the corpus owner reviews the user-visible
result against Original and freezes the same acceptability, harmful-category, severity, and local-
rationale fields. An unresolved review blocks new calls.

Temporary canary storage contains only Original, user-visible result, attempt status, validator
disposition, provider/model/version, prompt/schema/validator hashes, timestamps, latency, token use,
cost in USD micros, duplicate hash, and frozen review. It does not retain raw requests/responses,
rejected provider text, post-cleanup edits, outgoing destination, audio, clipboard history,
neighboring text, credentials, or provider/account identifiers.

The canary stops non-passing upon:

- withdrawal, cancellation, consent invalidity, or expiry of the 14-day window;
- manifest, code, configuration, hash, or provider-reported model mismatch;
- any isolation, disclosure, text-logging, storage, write-back, retry, fallback, duplicate-send, or
  stable-resource violation;
- inability to reserve the next request within $2, an actual breach, or missing/malformed usage;
- permanent credential, configuration, or quota failure;
- an ambiguous in-flight request after interruption;
- one accepted source-contract violation, one severe harmful change, or unresolved review; or
- a second unsuccessful attempt anywhere in the 10.

Canary success requires exactly 10 eligible attempts within 14 days; at least 9 valid-output
successes; at least 9 acceptable user-visible results; zero accepted source-contract violations;
zero severe and at most one non-severe harmful change; all reviews resolved; no privacy, isolation,
model, deadline, or protocol violation; and total cost no greater than $2 with pre-send enforcement.
Every attempt must complete within 30 seconds or be the one permitted unsuccessful timeout.

Latency, token/cost distribution, failure class, and rationales are descriptive; there is no
baseline comparison or inferential claim from 10 cleanups. Success, failure, stop, expiry, and
withdrawal are all terminal. After an optional explicit private export, delete all managed canary
text, results, hashes, reviews, logs, caches, and temporary artifacts at completion, cancellation,
withdrawal, or the fixed 14-day release, whichever occurs first. A deletion receipt may retain only
protocol/run ID, disposition, deletion timestamp, and counts—no text-derived hash or case ID.

Canary success authorizes no 25- or 100-cleanup continuation, repeat canary, automatic routing or
fallback, stable default change, provider promotion, or effectiveness claim. Every later experiment
or product change requires a separately reviewed protocol and explicit authorization.

## Completion boundary

This protocol is decision-complete when its narrative and machine-readable forms agree, version 1
remains unchanged and linked as superseded history, and active documentation no longer presents
version-one benchmark or 10/25/100 canary rules as current. Documentation completion still does not
authorize the runner, corpus use, provider traffic, spending, benchmark, canary, stable changes,
commit, push, merge, deployment, or external sharing.
