# Provider response-screening protocol

**Status:** Current procedure for preparing a separately authorized synthetic
screen. This document grants no execution, spending, private-text submission or
application-activation permission.

Use this protocol to compare whether exact provider configurations return valid,
normally completed text within a fixed deadline. Measure wording quality
separately. Neither response validity nor a passing screen establishes intended-text
recovery, provider-wide reliability or normal-use qualification.

## Before each run

Create a run-specific GitHub issue linking this protocol and obtain explicit owner
approval of the frozen plan. Record:

- Purpose, exact provider URL, model snapshot, route restrictions, request
  parameters and configuration identity. Disable retries, substitutions, tools
  and automatic fallback.
- Exact synthetic fixture version, prompt, wrappers and expected outputs. Use
  the [frozen reference bundle](archive/provider-response-screening/README.md)
  when repeating this comparison; do not reconstruct fixtures from prose.
- Deadline, threshold, attempt count, window schedule, runtime and stop rules.
  Changing the deadline creates a new sample, not a rescore of cancelled calls.
- Dated price/token limits, conservative per-attempt reservations, new batch
  allowance and effective cumulative caps. Prior remaining budgets are not new
  spending permission.
- Effective privacy controls and any explicitly accepted synthetic-only
  exceptions, including retention, training, caching, auxiliary processing and
  route evidence. Check router and serving provider separately.
- One execution owner, current cumulative ledger location, evidence destination,
  restart prevention and required delivery artifacts.

Verify credentials are available without printing them. Refresh the environment
if needed. A key's existence and `store:false` do not establish Zero Data Retention
(ZDR). If effective ZDR is unconfirmed, explain applicable retention/caching terms
and obtain explicit synthetic-only permission before inference. No private text
is authorized by this protocol or by historical fixture permissions.

## Fixture contract and coverage limits

The frozen five-case set contains two synthetic context-supported repair cases
(`short`, `medium`), a near-limit preservation case (`near_limit`), an ambiguity
control (`ambiguity`) and an already-correct matched control
(`short_preservation`). The repair cases require intended wording changes, not
spelling-only cleanup; the controls expose unwanted rewriting and protected-quote
changes. This exercises limited aspects of PRODUCT.md's intended-text-recovery
goal, not owner-confirmed misunderstandings or comprehensive correction accuracy.

Preserve source, expected text, whitespace, quotation contents, prompt, wrappers
and ordering exactly. The near-limit fixture has 11,961 characters and a final
newline; missing that newline is a formatting difference, not a content omission.
Keep exact and trimmed comparisons separate. These synthetic examples are not
private recognition-repair records or Personal Corrections.

## Frozen execution method

Unless an explicitly approved new plan changes it, use this method:

1. For each configuration, schedule at most **30 attempts**: three ordered passes
   through the five fixtures in each of two windows.
2. Target the second window at the configuration's actual first dispatch plus
   **1,800 seconds**. Use one sequential dispatcher with at least **two seconds
   between a call's completion/cancellation and the next dispatch**. When comparing
   providers, allocate nonoverlapping slots that fit each worst-case window.
   Stop if the approved schedule cannot be met rather than silently changing it.
3. Start a monotonic absolute deadline immediately before dispatch. Include
   connection, sending, full receipt, parsing and response validation—not just
   first token. Cancel at the deadline; never accept a late result. Record actual
   elapsed time and cancellation cleanup overhead.
4. Count a success only for HTTP 200, the expected documented envelope/model and
   route identity where applicable, parseable nonempty text, normal completion
   and completion within the approved deadline. Direct OpenAI does not need an
   OpenRouter `provider` field. A serving-provider display name does not attest
   geography. Normal completion does not prove semantic completeness.
5. Require **28/30 successes** (strictly over 90%). Stop a configuration after
   three response failures make that impossible. Stop immediately for unexplained
   HTTP rejection, unexpected configuration/route, privacy mismatch, missing
   usage evidence on a received response, or exhausted budget. Never replace a
   failed or uncertain dispatched attempt. Timeouts retain unknown charges;
   they do not permit a billing-evidence bypass or replacement call.
6. Report each attempt in the denominator, including transport failures and
   timeouts. An early-stopped sample is not 30 attempts and has no second-window
   evidence if it stopped in window one. Keep earlier diagnostics and different
   deadline samples separate.

Report within-five-, within-ten- and within-thirty-second counts when the approved
deadline permits observation. A five-second cancelled request cannot be classified
later as a ten- or thirty-second completion. Prefer observed completion fractions
for comparison, with timing as a separate observation; report ties and sampling
limits rather than inventing a stable reliability ranking.

## Spending and restart safety

Maintain one cumulative ignored ledger. Retrieve its current version from its
sole owner before preparing a new batch; a source thread's older copy is not
current accounting. Record ownership transfer explicitly and prevent concurrent
writers with an exclusive process lock.

Create distinct batch IDs and additive approved caps. Durably reserve the full
per-attempt bound **before dispatch**. Retain every dispatched reservation,
including successful calls and unresolved timeouts; never release or transfer
historical reservations to fund another screen. Token-derived estimates and
response-reported costs are not final invoices. Cancellation does not prove that
upstream processing or billing stopped.

Use durable prepared/running/finished state. A restarted process must refuse to
dispatch a started or finished batch; uncertain dispatches stay reserved until
reviewed. Never reset state or weaken historical ledger assertions to replay a
completed run. Test reservation ordering, cost arithmetic, historical preservation,
deadline boundaries, early stopping, locks and restart refusal offline before any
paid dispatch.

The historical thirty-second runner is preserved as non-executable reference text,
not a reusable live launcher. It has run-specific ownership, balance, batch and
scheduling constants. Adapt a copy only under an approved new plan, retain its
safety invariants, and test it offline. Keep live state and execution copies
outside Git. In an orb, use supervised services and stop them after the run.

## Required report and verification

Keep credentials, operating text, ledgers, raw provider responses and logs outside
Git and the issue tracker. A run-specific issue should link privacy-safe summaries
and protected evidence, not paste raw payloads. Report:

- Every dispatch, fixture, repetition/window, result/failure and elapsed time;
  per-fixture timings and observed response fractions at each measured threshold.
- Expected model/route evidence, actual window spacing and stop reasons.
- Separate exact/trimmed wording matches and substantive changes, omissions,
  ambiguity or quotation violations. Do not count wording differences as
  connectivity failures or treat exact matches as general correction accuracy.
- New and cumulative reservations, known cost basis, unresolved charges, unused
  allowance, evidence gaps and limits on any recommendation.
- Frozen manifest/runner identity, offline checks, dispatch/result reconciliation,
  accounting verification and confirmation that services stopped.

Verify dispatch counts equal recorded results or explicitly unresolved dispatches;
check exact request bodies, identities, deadlines, gaps, windows and all ledger
sums. Expected outcome: a complete, auditable bounded screen with no duplicate
dispatches or hidden failures. Unused allowance never authorizes another run.

## Historical results and application boundary

These samples are historical evidence, not current execution permission:

| Deadline | Nebius Gemma 27B | OpenRouter / default Azure Mini | Direct OpenAI Mini |
| --- | --- | --- | --- |
| Five seconds | 4/7 | 3/6 | 5/8 |
| Ten seconds | 10/13 | 10/13 | 10/13 |
| Thirty seconds | 10/13 | 29/30 | 30/30 |

The thirty-second comparison supports direct OpenAI as the observed diagnostic
leader, not a proven provider-wide advantage. Two earlier short diagnostics
(one each for Nebius/OpenRouter) are excluded from these denominators.
Full reports and the current ledger remain in the
[comparison thread](https://ampcode.com/threads/T-01a14713-03f3-7275-8fc2-376b3467ab62).
The [preservation issue](https://github.com/dmclark/sayloom/issues/180) tracks this
protocol's publication, not another screen.

The owner subsequently selected **direct OpenAI and a maximum timeout of 30
seconds, not 32**. The
[Wayfinder continuation](https://ampcode.com/threads/T-01a14a57-6539-704e-b377-b4f3cb0c3dac)
owns clarification of provider timeout versus whole visible-outcome scope. This
procedure does not reopen that selection or silently resolve the scope, implement
the timeout, or activate a provider. Direct OpenAI's effective ZDR remains
unconfirmed; prior synthetic exceptions do not authorize private text.

Preserve PRODUCT.md and live issues
[#171](https://github.com/dmclark/sayloom/issues/171),
[#172](https://github.com/dmclark/sayloom/issues/172),
[#179](https://github.com/dmclark/sayloom/issues/179) and
[#162](https://github.com/dmclark/sayloom/issues/162).
Local-backup readiness, measured timing/validation/render reserves, independent
recovery and owner acceptance remain separate gates. Voiceitt stays fixed, final
text only; no first-pass access, private-history reuse or capture expansion follows.
