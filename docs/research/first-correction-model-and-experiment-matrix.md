# First correction model and experiment matrix

- **Status:** Research recommendation; no implementation or paid run authorized
- **Product authority:** [`PRODUCT.md`](../../PRODUCT.md)
- **Sources checked:** 2026-09-04

## Decision

Use OpenAI **GPT-5.6 Sol** (`gpt-5.6-sol`) as the single anchor for Sayloom's
first local Smart-correction proof. Freeze the exact model identifier exposed by
the API manifest at registration time rather than silently following a moving
alias. Use the Responses API in foreground mode, no tools, no files, no remote
context, and `store=false`; request the smallest structured result needed for
review and scoring.

This is an experiment anchor, not a production-provider decision. GPT-5.6 Sol is
currently listed for standard API use and OpenAI describes it as its flagship
for complex professional work. It accepts text, produces text, supports
reasoning controls and Structured Outputs, and is available through both the
Responses and Batch APIs [O1]. Those facts make it a capable, controllable first
test of whether the correction contract works at all. They do **not** establish
quality on Sayloom's corpus; only the blinded benchmark can do that.

The smallest useful alternative check is Google's **Gemini 3.8 Flash**. It is GA,
supports adjustable reasoning, and is materially cheaper at current
introductory rates [G1]. Do not compare it yet: changing model/provider while
also changing prompt, task context, and user knowledge would confound the first
proof. Google's Pro-tier Gemini 3.1 model remains preview, so it is not a cleaner
production-grade frontier anchor [G2]. After the configuration experiment is
frozen and scored, a separate provider ticket can compare the winning
configuration against Gemini 3.8 Flash (or the then-current qualified model).

Do not use GPT-6 Astra for this proof. OpenAI currently says it is rolling out
through a Trusted Access Program rather than presenting it as ordinary,
settled API access [O2]. Maximum novelty is less useful than reproducible access.

## What the proof tests

Smart correction receives imperfect **text**, never audio. Every arm must:

1. preserve Original unchanged and separately return a candidate;
2. make only intended-word repairs supported by the supplied text/context;
3. apply Conservative preparation (capitalization, punctuation, apostrophes,
   whitespace, and bounded filler handling) after lexical repair;
4. expose word additions, removals, and replacements for review; and
5. fail open to Original on refusal, timeout, malformed output, or failed local
   validation.

The benchmark asks whether an arm better matches the user-confirmed intended
text, not whether it produces smoother prose. Meaning fidelity and harmful
changes dominate latency, token cost, and lexical-repair diagnostics.

## Frozen 2 × 2 × 2 matrix

Run one full factorial on one frozen, paired corpus. Each case is sent once to
each of eight arms; randomize arm order per case and blind outputs during human
review. Keep model, reasoning effort, output schema, token limit, and all other
request settings identical. The factorial shape estimates each factor's effect
without attributing a context or knowledge gain to a simultaneous prompt
change, and exposes interactions rather than assuming additivity.

| Factor | `0` | `1` |
| --- | --- | --- |
| **P — correction contract** | Minimal task instruction and output schema; no least-change rules beyond “correct likely recognition errors, then prepare” | Frozen Sayloom contract: text-not-audio boundary, least change, no unsupported invention, Conservative preparation, explicit lexical-change list, uncertainty signal, and fail-open-compatible schema |
| **E — explicit ephemeral task context** | No task context | A frozen, case-authorized context field describing the immediate topic/audience/application; sent inline for this call only, never retrieved or persisted by the experiment |
| **K — curated user knowledge** | No user knowledge | A frozen, locally curated allow-list relevant to the case (for example preferred names, terms, spelling, and capitalization), clearly delimited as hints rather than instructions |

The eight arms are `P0E0K0`, `P1E0K0`, `P0E1K0`, `P1E1K0`, `P0E0K1`,
`P1E0K1`, `P0E1K1`, and `P1E1K1`. An absent field is truly omitted, not replaced
with explanatory prose. E and K content must be frozen before any output is
seen and must not reveal the expected answer. Use only knowledge legitimately
available before the utterance. This prevents answer leakage.

### Frozen corpus and measures

Corpus size is not decided here. Let **N** be the number of eligible paired
cases. Freeze case IDs, expected intended text, eligibility, strata, E/K fields,
arm prompts, model manifest, scoring code, reviewer rubric, and gates before
examining model outputs. Balance and report must-preserve strata (names/terms,
numbers/dates, negation/modality, identifiers/links, quotations/formatting, and
already-correct text) and recognition-like repair difficulty. Do not infer
sensitive identity labels.

Primary measures, in order:

1. blinded preference / correction effort against user-confirmed intended text;
2. harmful meaning change rate and must-preserve accuracy, with negation,
   numbers, names/terms, and identifiers broken out;
3. exact match and normalized word/character edit distance;
4. lexical repair precision/recall from the declared change list; then
5. success/refusal/invalid-output rates, input/output tokens, and p50/p95 latency.

Analyze paired case-level contrasts for P, E, and K and their interactions, with
95% paired bootstrap confidence intervals. Report all eight arms, including
negative results; do not select only favorable strata.

### Stopping and advancement gates

Pre-register numeric margins before opening results. Existing cleanup research
already establishes the discipline: no post-results threshold tuning and no
provider-order inference from model-quality arms
([cleanup evaluation](../cleanup-resilience-evaluation.md)). For this proof:

- **Stop immediately** for privacy-gate failure, an unplanned prompt/model
  change, expected-answer leakage, corpus drift, or any unblinding before labels
  are locked. Correct the protocol and start a newly versioned run; do not patch
  the current results.
- **Stop an arm** if it exceeds the pre-registered harmful-change ceiling or a
  run-level spend/token cap. Failed calls remain failures; no paid retries.
- **Validity gate:** advance analysis only if every arm reaches the same
  pre-registered completion floor and missingness is reported. Never drop a
  difficult case selectively.
- **Quality gate:** no configuration advances unless its harmful-change upper
  confidence bound and must-preserve lower confidence bound meet the frozen
  safety margins, and its primary quality result is non-inferior to the frozen
  comparator. Among passing configurations, prefer the least contextualized
  arm unless E or K shows a pre-registered, paired quality benefit without a
  safety regression.
- **Provider-comparison gate:** compare providers only after selecting and
  freezing one passing P/E/K configuration. If no arm passes, revise the
  contract or corpus in a separately versioned experiment—not the thresholds.

## Calls, tokens, and cost cap

ChatGPT subscriptions and API usage have separate billing systems. A ChatGPT
Plus subscription therefore does not provide API credit or authorize this paid
experiment; the API organization still needs its own billing setup and explicit
cost approval [O4].

For the full matrix:

- calls = **8N**;
- input tokens = `sum(input tokens across all 8N calls)`;
- output tokens = `sum(output tokens, including billed reasoning tokens, across all 8N calls)`;
- standard short-context cost at today's GPT-5.6 Sol rates =
  `(input_tokens × $4 + output_tokens × $20) / 1,000,000` [O1, O2].

Before a paid run, count every arm with the provider tokenizer, set per-call
input and output maxima, and reject the manifest if the computed worst case
exceeds the approved cap. Do not assume cached-input discounts. The cited prices
are promotional through at least 2026-11-21 and long-context requests over
272,000 input tokens have higher rates; re-check pricing on run day [O1].

**Planning example, not corpus authority:** if `N = 60`, with hard maxima of
2,000 input tokens and 500 total output tokens per call, then the run permits
480 calls, at most 960,000 input tokens and 240,000 output tokens. The capped
standard cost is **$8.64** (`$3.84 + $4.80`). No retries and no tools are included.
Actual spend should be lower; this ceiling—not an average estimate—is the
authorization boundary. A larger corpus scales linearly: at the same limits,
cost cap = **$0.144 × N**.

## Privacy gate before private corpus text

“Not used for training” and “not retained” are separate claims.

- OpenAI says API data is not used to train or improve models unless the
  customer explicitly opts in [O3]. Separately, default abuse-monitoring logs
  may contain prompts and responses and are retained up to 30 days. The
  Responses API also retains application state for at least 30 days by default;
  `store=false` avoids that application-state retention but does **not** remove
  default abuse-monitoring retention [O3].
- Zero Data Retention (ZDR) or Modified Abuse Monitoring requires OpenAI approval
  and additional requirements, and is selectable at organization/project level
  after approval. Under ZDR, `store` is forced false, subject to documented
  endpoint/model exceptions [O3].
- Google separately says paid Gemini services do not use prompts/responses to
  improve products, while paid-service prompts and responses are normally
  logged for a limited abuse-monitoring period. Project approval is required
  for Gemini Developer API ZDR; the Interactions API stores state by default
  unless `store=false` [G3]. This is relevant to a later comparison, not a reason
  to mix providers into this matrix.

Before sending any private corpus item, a human must verify and record: the paid
OpenAI organization and exact project; training/data-sharing opt-ins are off;
the project's effective retention control (default, MAM, or ZDR); GPT-5.6 Sol
and the chosen foreground endpoint are eligible under that control; the request
sets `store=false`; tools, files, background mode, conversations, and hosted
storage are absent; and the corpus owner's consent permits this named external
processor and retention posture. If the approved posture requires ZDR and the
project does not demonstrably have it, the experiment is **blocked**. Local
ephemerality does not erase provider-side processing or retention.

## Limitations and follow-up facts

- Model claims and prices are a 2026-09-04 snapshot and must be refreshed when
  registering the run. Repository provider names are historical claims, not
  current authority.
- No public benchmark establishes intended-word correction quality for this
  user's workload. The recommendation is deliberately provisional.
- N, per-arm token distributions, safe output limit, reasoning effort, latency
  budget, completion floor, quality/non-inferiority margins, harmful-change
  ceiling, and statistical power remain workload-dependent and must be fixed by
  corpus/tokenizer preflight before paid execution.
- Curated knowledge and ephemeral context need a case-level availability audit;
  cases without legitimate pre-utterance E or K values cannot identify those
  factors and should be declared before randomization.
- A later, separately costed provider comparison must use the frozen winning
  configuration and then-current official model snapshots, prices, and privacy
  controls. Hosted architecture is out of scope.

## First-party sources

All accessed 2026-09-04.

- **[O1]** OpenAI, [GPT-5.6 Sol model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol) — model ID, modalities, reasoning, Structured Outputs, endpoints, snapshots, and pricing qualifiers.
- **[O2]** OpenAI, [API pricing](https://developers.openai.com/api/docs/pricing) — current standard rates, long-context rates, promotion, and GPT-6 Astra rollout status.
- **[O3]** OpenAI, [Data controls in the OpenAI platform](https://developers.openai.com/api/docs/guides/your-data) — training policy, abuse-monitoring retention, Responses application state, `store=false`, and MAM/ZDR controls.
- **[O4]** OpenAI, [Managing billing for ChatGPT and the API platform](https://help.openai.com/en/articles/8156019) — separate ChatGPT-subscription and API billing systems.
- **[G1]** Google, [What's new in Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/latest-model) — GA status, capabilities, reasoning levels, and introductory/standard pricing.
- **[G2]** Google, [Gemini 3 Developer Guide](https://ai.google.dev/gemini-api/docs/gemini-3) — Gemini 3.1 Pro preview status and pricing.
- **[G3]** Google, [Zero data retention in the Gemini Developer API](https://ai.google.dev/gemini-api/docs/zdr) — paid-service training restriction, logging, Interactions storage, and project ZDR requirements.
