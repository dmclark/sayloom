# Hosted AI delivery: privacy and unit economics

- **Status:** Research recommendation; hosting, provider spend, and production use remain gated
- **Product authority:** [`PRODUCT.md`](../../PRODUCT.md)
- **Sources checked:** 2026-09-04

## Recommendation

Keep **OpenAI direct API with GPT-5.6 Sol (`gpt-5.6-sol`)** as the provisional
first hosted path if the local proof passes. It minimizes the first transition
because it preserves the proof's model and API contract. Use foreground
Responses requests, `store=false`, no tools/files/remote context, explicit
project spend limits, and the verified effective retention posture. Default
OpenAI access is acceptable only if the product disclosure and consent permit
up to 30-day abuse-monitoring retention; if zero retention is required, launch
is blocked until OpenAI approves and the project demonstrably enables ZDR [O2].
Without ZDR, OpenAI also applies encrypted, GPU-local prompt caching with a
maximum 24-hour application-state retention period; this must be included in
the effective posture even when `store=false` [O2].

Qualify **Vertex AI Gemini 3.8 Flash (`gemini-3.8-flash`)** as the first
cost/latency alternative after the winning correction configuration is frozen.
It has a much lower token ceiling and useful regional controls, but no Sayloom
quality or latency evidence yet. Keep **Amazon Bedrock Claude Sonnet 5
(`anthropic.claude-sonnet-5`)** as the infrastructure/privacy alternative when
AWS-native IAM, an explicit Bedrock `none` retention mode, or AWS geography
routing is materially valuable **and the selected model's reported
`allowed_modes` includes `none`**. Do not add Azure merely for another route:
none of the known requirements currently needs it, and each provider adds
credential, privacy, billing, failure, and evaluation surface.

This is a shortlist, not provider selection. Initial hosting remains gated on
the local proof, managed credentials are required, and BYOK and automated target
delivery remain deferred. Any experiment, account, commitment, or API usage
that creates cost needs a fresh estimate and approval.

## Workload basis and unknowns

There are **no completed empirical workload measurements**. The approved proof
plans 50 practice plus 100 unseen cases, uses GPT-5.6 Sol as its anchor, allows
at most 2,000 input and 500 total output tokens per call, and separately checks
20 normal dictations. Those are planning bounds, not production averages.

The proof and normal-use check must measure, by exact model/configuration:
input/output (including billed reasoning) tokens, attempted and valid results,
usable results under the frozen human rubric, refusal/validation/failure rate,
p50/p95 end-to-end and time-to-first-token latency, concurrency, retries, and
429/5xx incidence. Hosted demand, geography, monthly active users, corrections
per user, peak burst, required retention posture, and latency SLO remain unknown.

## Decision-relevant comparison

Volatile facts and prices below are the 2026-09-04 snapshot. “No training” is
not “no retention.” Prices are USD per 1M tokens for short, online text requests;
the last column applies the full 2,000-input/500-output bound with no cache,
tools, retries, network/hosting charges, taxes, or contracted discounts.

| Managed route | Access and model | Default/available data posture | Capacity, latency, and hosting | Standard price (input/output) | Cost per attempted result |
| --- | --- | --- | --- | ---: | ---: |
| **OpenAI direct** | Ordinary API project access; proof anchor `gpt-5.6-sol`, Responses API [O1] | API content is not used to train unless opted in. Default abuse logs may contain prompts/responses for up to 30 days. Responses also stores application state by default; `store=false` removes that state, not abuse logs. Without ZDR, supported models use encrypted GPU-local prompt caching with a maximum 24-hour expiry. MAM/ZDR needs approval and extra requirements [O2]. | Limits vary by model and org/project usage tier and use RPM/TPM and other meters. Standard and Fast share limits; Fast is a per-request/project option advertised as up to 2.5× faster, not a Sayloom latency guarantee [O4, O5]. Eligible regional processing has a 10% uplift and model/endpoint/control restrictions [O2, O3]. | **$4 / $20** promotional through at least 2026-11-21 [O3] | **$0.018000** |
| **Google Vertex AI** | Google Cloud project, billing, API/IAM; GA `gemini-3.8-flash` on global and listed regional/multi-region endpoints [G2] | Contractual training restriction: no training/fine-tuning without permission. Request/response logging is off by default, but in-scope Cloud terms can permit abuse prompt logging; request an exception if ZDR is required. Interactions defaults `store=true`; use stateless `generateContent`, or explicitly false. In-memory project-isolated cache has 24-hour TTL and can be disabled [G1]. | PayGo capacity is shared/dynamic; inspect project/location/model quotas. Global improves availability/reduces 429s but gives no processing-location control. US/EU multi-region endpoints constrain ML processing; endpoint choice alone does not guarantee residency. Provisioned Throughput is a later commitment, not justified before demand [G2, G3, G4]. | Global **$0.75 / $3.75** through 2026-12-31; non-global **$0.825 / $4.125** [G3] | Global **$0.003375**; non-global **$0.003713** |
| **AWS Bedrock / Anthropic** | AWS account/payment/IAM/Marketplace permissions; Anthropic first-use form on `bedrock-runtime` (not `bedrock-mantle`). Model `anthropic.claude-sonnet-5`; third-party EULA applies [A2, A3]. | Model providers cannot access Bedrock deployment accounts, logs, prompts, or completions. Where a model's reported `allowed_modes` includes `none`, explicit account/project `data_retention_mode: none` writes no request/response to durable AWS storage or provider, rejects incompatible features/models, forces Responses `store=false`, and disables background mode. `default` inherits model behavior and may retain for abuse detection, so it is not an acceptable assumption. Verify Sonnet 5's effective and allowed modes in the target account before treating it as ZDR-capable [A1, A4]. | Per-model token quotas are separate by endpoint and can vary with region/payment history or approved increases. Sonnet 5 currently exposes Standard only, despite generic descriptions of Priority/Flex/Reserved. Runtime geo IDs constrain routing to US/Canada, EU, or AU; global has no residency constraint; Mantle offers selected in-region endpoints [A3, A5]. No supported numeric latency promise was found. | **$2 / $10** [A3, A6] | **$0.009000** |

## Unit economics

For input ceiling `I = 2,000`, output ceiling `O = 500`, and published rates
`Pi` and `Po` per million tokens:

`attempted_cost = (I × Pi + O × Po) / 1,000,000`.

Thus OpenAI Standard is `(2,000×4 + 500×20)/1M = $0.018`; OpenAI Fast is
twice that, **$0.036** [O3, O5]; Vertex global promotional is **$0.003375**
(**$0.00675** at the published 2027 standard rates), and Vertex non-global is
**$0.0037125** now [G3]; Bedrock Sonnet 5 is **$0.009** [A3, A6]. These are
conservative token ceilings, not expected averages. Google states non-200
responses are not token-charged; provider failure/refusal billing rules differ,
so invoices and usage telemetry must settle actual attempted cost [G3].

Let observed usable-result rate be `u = usable_results / attempted_results`,
using the pre-registered human rubric and counting paid invalid/refused/failed
outputs as attempts. Then:

`cost_per_usable_result = total attributable provider cost / usable_results`

or, when every attempt has the same illustrative ceiling, approximately
`attempted_cost / u`. No value of `u` is known; inventing one would turn the
provider ranking into fiction. Also report retries/fallback separately: a
second paid route can nearly add another attempted cost without producing a
usable result.

## Privacy and retention launch gates

Before any private hosted text is sent, a human owner must record and approve:

1. named processor, exact account/project, model snapshot/ID, endpoint, region,
   subprocessors/terms, disclosure, and corpus/user consent;
2. effective no-training/data-sharing settings and **effective retention mode**,
   not marketing language—OpenAI default (up to 30-day abuse logs) versus
   approved MAM/ZDR; Google abuse-logging applicability/exception and disabled
   request logging/cache choice; or Bedrock project/account `none` plus model
   compatibility;
3. stateless request shape: no tools, grounding, files, conversations,
   background processing, provider retrieval, explicit cache features, or
   provider-side logging; separately document and disable provider-managed
   in-memory caching where possible, because OpenAI applies it without ZDR;
4. app telemetry that excludes Original, Prepared, prompts, responses,
   credentials, and personalization while retaining only safe aggregate
   latency/token/cost/error evidence; and
5. account isolation, deletion/incident terms, DPA and any required regulated-
   data terms. Endpoint controls do not substitute for contract review.

If the approved policy requires zero provider retention and the selected route
cannot demonstrate it, hosted launch is blocked. Product-side ephemerality does
not erase processor retention.

## Rate, latency, and hosting implications

- Start with one foreground attempt, strict total deadline, cancellation, local
  fail-open to Original, and no automatic paid retry. Size `max_output_tokens`
  tightly: OpenAI notes limits can account for configured maximum tokens [O4].
- Do not buy reserved/provisioned capacity initially. First measure normal-use
  bursts. PayGo 429s are expected operating outcomes; honor valid retry-after
  only within policy, expose safe attribution, and shed stale work.
- Stream if it improves perceived latency, but score complete validated output.
  Provider labels such as “Flash,” “Fast,” “Priority,” or “global” do not
  establish Sayloom p95. OpenAI Fast doubles this bound; Vertex global trades
  location control for availability; current Bedrock Sonnet 5 Standard offers
  no premium tier [O5, G2, A3].
- Co-locate the hosted application with the selected provider geography only
  after choosing the user/data geography. Verify the full path: application,
  TLS edge, inference routing, logs, backups, and support—not merely the API
  hostname.

## Recheck at implementation

On the approval date, re-open every source below and capture an implementation
manifest: exact GA model/snapshot and structured-output support; endpoint and
region availability; actual account access; effective retention/data-sharing
configuration; DPA/EULA/subprocessor terms; per-model RPM/TPM/concurrency and
monthly spend limits; service-tier eligibility/SLA; token accounting (especially
reasoning); failed-call billing; and current standard/regional/fast prices.
Recalculate worst-case and measured-average monthly spend from proof telemetry,
include application hosting/egress/observability/tax, and obtain approval before
creating any cost. Run a small, separately approved provider comparison using
the frozen winning correction configuration; do not infer quality from price.

## First-party sources

All accessed 2026-09-04.

- **[O1]** OpenAI, [GPT-5.6 Sol model](https://developers.openai.com/api/docs/models/gpt-5.6-sol) — model ID and endpoint/capability surface.
- **[O2]** OpenAI, [Data controls](https://developers.openai.com/api/docs/guides/your-data) — training, abuse/application-state retention, MAM/ZDR, and residency requirements.
- **[O3]** OpenAI, [API pricing](https://developers.openai.com/api/docs/pricing) — Standard/Fast rates, promotion, and regional uplift.
- **[O4]** OpenAI, [Rate limits](https://developers.openai.com/api/docs/guides/rate-limits) — org/project/model meters, usage tiers, headers, and ramp behavior.
- **[O5]** OpenAI, [Fast mode](https://developers.openai.com/api/docs/guides/fast-mode) — speed claim, shared limits, fallback, pricing, and SLA qualification.
- **[G1]** Google Cloud, [Agent Platform and zero data retention](https://cloud.google.com/vertex-ai/generative-ai/docs/data-governance) — training restriction, abuse/request logging, Interactions storage, and in-memory cache.
- **[G2]** Google Cloud, [Deployments and endpoints](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations) — model ID, endpoints, processing-location limits, and global trade-off.
- **[G3]** Google Cloud, [Generative AI pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing) — Gemini 3.8 Flash promotional/standard and regional pricing and failed-response billing.
- **[G4]** Google Cloud, [Quotas and system limits](https://cloud.google.com/vertex-ai/generative-ai/docs/quotas) — project/region/model quota administration and shared capacity.
- **[A1]** AWS, [Data protection in Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html) — provider isolation from deployment accounts and customer content.
- **[A2]** AWS, [Request access to models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html) — IAM, Marketplace, payment, Anthropic first-use, and EULA requirements.
- **[A3]** AWS, [Claude Sonnet 5 model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html) — model/route IDs, tiers, and geography options.
- **[A4]** AWS, [Bedrock data retention](https://docs.aws.amazon.com/bedrock/latest/userguide/data-retention.html) — scoped modes, `none`, feature enforcement, and default-mode warning.
- **[A5]** AWS, [Bedrock quotas](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas.html) — endpoint/model token quotas and adjustment factors.
- **[A6]** AWS, [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/) — Claude Sonnet 5 on-demand token rates and billing route.
