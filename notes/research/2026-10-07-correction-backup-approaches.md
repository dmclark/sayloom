# Correction backups when cloud access fails

**Date:** 2026-10-07

**Scope:** Reading research for Sayloom's local macOS workflow; timeout and API-access recovery, not a model-wording comparison.

**Status:** Recommendation only. No implementation, formal evaluation, collection, provider calls, model downloads, runtime operations, or configuration changes authorized or performed.

## Recommendation in plain language

Use layers, not a longer retry loop. Keep a genuinely independent cloud route
for failures isolated to one provider, and add a local path that can actually
improve text when neither cloud route works. Start that local path with a small,
versioned set of spelling and presentation fixes; investigate one small local
language model if contextual recognition repair is essential. Preserve earlier
successful preparation during appended dictation using the already specified
continuity checkpoint. Checkpoints alone do **not** correct the new text.

For a compatible Apple Intelligence Mac, investigate Apple's on-device model
first because an official Python SDK now exists. Otherwise, or if its context
limits or repairs prove unsuitable, investigate a quantized
`Qwen3-4B-Instruct-2507` through Ollama or MLX LM. Choose one runtime, not all
three. Hardware and correction quality remain unverified. [A1–A4, L1–L4]

The requirement should be **useful correction under defined failures**, not
“always change something.” Abstaining on an ambiguous sentence is correct.
Nothing researched is literally failsafe, and no text-only technique can
guarantee that it recovered what the user said. [R1]

## What is established—and what is not

- This orb's clean checkout initially matched both HEAD and `origin/main` at
  [the supplied revision](https://github.com/dmclark/sayloom/commit/849a1e4dd22a05b08dd6ab3ec90b8cb7eaaee477).
  The source thread's uncommitted PRODUCT.md edit did **not** transfer and was
  neither needed nor reproduced.
- Sayloom accepts text, not audio. Cleanup is the account-independent baseline;
  Smart is the contextual/user-dependent frontier, followed by Cleanup. The
  implemented Conservative path is an incomplete Cleanup stage, not authority
  to silently introduce new spelling or meaning-changing behavior. [R1]
- Existing routing has partitioned deadlines, single calls per eligible route,
  route/quota breakers, and output validation. Transient, quota, configuration,
  and invalid-output failures may advance; safety-policy, invalid-local-request,
  and unknown failures are terminal. Final failure preserves Original. Tests
  explicitly cover budget exhaustion, shared quota, auth/configuration failure,
  cancellation, and terminal safety refusal. These are source observations;
  tests were not executed for this documentation-only research. [R4, R5]
- Saved approval/storage exists. Server-owned Smart profile retrieval is not
  implemented at this revision; the target retrieval specification is not proof
  that ordinary processing already uses the saved corrections. The continuity
  checkpoint is also a target, not delivered behavior. [R2–R4, R6]
- No live provider configuration, incident evidence, Mac specification, or
  approved private text was available. A timeout does not establish a provider
  outage; an access failure could be authentication, quota, billing, policy,
  network, or local configuration. This research does not diagnose the user's
  incidents. ADR-0001's old product-mode split is superseded. [R3, R7, C1–C4]

## Availability is different from correctness

There are three separate promises:

1. **Usable output:** If the application and local draft still function, Original
   can remain editable/copyable without a provider. This is a conditional
   application guarantee, not a guarantee against browser/server/device failure.
2. **Bounded improvement:** A frozen rule can guarantee its specified
   transformation for eligible input; a checkpoint can preserve a previously
   accepted prefix. Neither guarantees improvement for arbitrary new text.
3. **Intended-text accuracy:** Dictionaries, rules, approved mappings, and models
   can all misinterpret a new context. Valid output/schema compliance does not
   establish correct meaning. No option guarantees this promise. [R1–R5, A4, S1]

Meaningful offline improvement is feasible on a bounded subset: misspellings,
some spacing or punctuation defects, and carefully eligible recurring repairs.
General recovery of real-word substitutions, missing ideas, names, or ambiguous
phrases requires inference or user confirmation—not just text normalization.

## Comparison of viable alternatives

Capabilities below are candidate behavior, not demonstrated Sayloom efficacy.

| Alternative | What it can improve with cloud models unavailable | Offline, latency, and resources | Costs/privacy/licensing | Remaining failure modes and fit |
| --- | --- | --- | --- | --- |
| **Direct Gemini → direct OpenAI** with independent credentials and billing | Nothing if all cloud access is unavailable; another cloud model may provide full contextual repair when only the first provider fails | Online only; sequential latency includes the failed primary allocation, so reserve a useful fallback allocation | Metered requests, possibly both attempts; text goes to a second processor under its own terms | Best near-term cloud-access resilience because adapters already exist. Shared network, local router, payload, policy, or exhausted total budget can defeat both. Same-provider models are not equivalent independence. [R3–R5, C1–C6] |
| **Apple on-device SystemLanguageModel** | Candidate spelling, grammar, phrase/contextual recognition repair, optionally informed by approved Smart evidence | Offline after system assets are ready; SDK requires macOS 26+, Xcode 26+, Python 3.10+, Apple Intelligence enabled on a compatible Mac. Check availability. No measured latency | No metered cloud inference for on-device use; uses local hardware. Python SDK Apache-2.0; Apple model/SDK platform terms are distinct | Attractive on eligible Macs; unavailable assets/settings/region/language, context overflow, refusal, OS/model changes, and wrong repairs remain. Explicitly select on-device, not Private Cloud Compute. [A1–A4] |
| **Qwen3-4B-Instruct-2507, quantized, via Ollama or MLX LM** | Candidate contextual repairs plus spelling/grammar; model card describes a non-thinking instruction model, not a proven Voiceitt corrector | Offline with all weights/tokenizer cached. MLX targets Apple silicon; Ollama supports macOS 14+ on Apple M CPU/GPU or Intel CPU-only. Cold load, RAM pressure, queueing, heat, and power matter | No per-token local charge; storage, electricity and maintenance. Qwen Apache-2.0; Ollama/MLX LM MIT. Audit converted artifact and tokenizer licenses too | Most controllable local-model route; likely slower on Intel. Neither a runtime nor quantization establishes repair quality. Daemon/crash/OOM, unsupported output, and hallucination remain. [L1–L4] |
| **Local LanguageTool basic server** | Dictionary spelling and rule-based grammar/punctuation findings; selected rules can yield replacements | Offline with packaged dependencies. Java sidecar; current source build requires Java 17/Maven, while the server guide still mentions Java 8+. Verify the chosen release rather than assuming Java 8 suffices | No hosted API charge; local text processing if truly self-hosted; LGPL-2.1 runtime and dependency/resource obligations | Useful candidate generator, not a replacement for Smart. Local server explicitly lacks cloud AI rules and synonyms. Grammar/style rules may exceed current product scope; allowlist only eligible Cleanup repairs. [S1, S2, R1] |
| **Dictionary spelling + small deterministic rule set**; SymSpell or macOS NSSpellChecker as candidate sources | Selected misspellings, carefully defined spacing/presentation defects; no general recovery of valid-but-wrong words | Dictionary/rules need no GPU or cloud. SymSpell needs a dictionary/index; NSSpellChecker needs a macOS API integration and installed language resources | SymSpell MIT, with separately licensed dictionary inputs; NSSpellChecker is an Apple platform service, not an open-source redistributable engine | Smallest offline floor. Candidate rank is not certainty. Protect names, numbers, URLs, code, negation, quotations and intentional repetition. NSSpellChecker docs do not establish blanket offline/privacy guarantees for every installed spelling service. [S3, S4] |
| **Approved Personal Corrections as bounded Smart assistance** | Repeat approved word/phrase repairs when applicable; can inform a local model without cloud access | Local database retrieval; no model download for matching. Matching alone does not resolve context | No external charge; private local state. Keep approval, revision, disable/delete, ownership and export boundaries | Existing target supplies evidence, not automatic replacement authority. Arbitrary context matching or blind replacement is unsafe. A deterministic personalized fallback would need a separately confirmed Smart execution contract. [R1, R2, R6] |
| **Hybrid + continuity** | Preserve corrected prefix; provide bounded local improvement for newly processed full text; optionally obtain broader cloud repair later | Local candidate need not wait for cloud timeout; cloud and local work require a shared deadline and stale-result discipline | Combines the selected layers' costs and privacy boundaries, not automatic consent to every route | Recommended architecture direction. More layers can increase contention and inconsistency; don't concatenate overlapping fixes or treat a provisional result as full success. [R3–R5] |

### Cloud independence, not merely a second model name

Use a direct provider endpoint with its own valid access, billing capacity and
quota group. Gemini quotas apply per project rather than API key; OpenAI limits
can apply at organization/project and shared-model-family scope. Another key in
the same exhausted scope does not supply fresh capacity. Another Gemini model
can help model-specific overload but still shares provider/access dependencies.
An aggregator can route different models yet adds a common gateway/auth/billing
failure point; independence must be checked through the entire route. The
gateway observation is architectural reasoning, not a measured outage claim.
[C1, C2, R4]

Provider-auth/billing failures should advance to an authorized independent route
without burning the user's latency budget on retries that cannot restore access.
A temporary 429/503 may recover later, but any wait must fit the reserved budget.
Do not override request-level safety refusal or invalid input to try another
provider/local model; existing routing makes those terminal. Avoid accidental
SDK retry multiplication if adding an SDK. [R4, R5, C3, C4]

Two cloud routes remain correlated through the user's Internet connection,
DNS/proxy/firewall, application and prompt/validator bugs. Independent providers
can both lack funded access, both reject the material, or both exceed the total
deadline. No independence probability or uptime claim can be computed from the
available evidence.

**Cost illustration, not model selection:** Official standard paid prices read
on this date list Gemini 2.5 Flash-Lite at $0.10 input/$0.40 output and GPT-4.1
mini at $0.40 input/$1.60 output per million tokens. At 1,000 input and 300 output
tokens, that is $0.00022 and $0.00088 respectively; two billable attempts would
be $0.00110 under those assumptions. Actual prompts include instructions and
evidence; output/reasoning, repeated full-draft reruns, and provider billing for
failed/cancelled work can change spend. Prices do not demonstrate model access,
continued availability, adapter compatibility, latency or repair quality.
Recheck exact model and terms before choosing. [C5, C6]

OpenAI API data is not trained on by default, but abuse-monitoring content can
be retained up to 30 days, with stated exceptions. `store=false` is not Zero Data
Retention; ZDR requires approval. Paid Gemini terms exclude product improvement
using prompts/responses but permit limited safety logging; unpaid terms permit
human review and warn against sensitive/personal input, with regional exceptions.
No-training must not be described as no-retention. [C7, C8]

### Local-model practicality

Apple's official Python SDK removes the need to assume a bespoke Swift helper
for this Python backend. It is still a new dependency with platform prerequisites,
not a drop-in Sayloom adapter. Apple documents a 4,096-token system-model context
in its generation guide; budget instructions, input, evidence and output together
and verify the actual OS/model version. The framework also exposes cloud models;
“Foundation Models” alone is not an offline guarantee. Apple controls system
model updates, so record OS/model/prompt versions for reproducibility. [A1–A4]

For a quantized 4B model, 4-bit weights alone are roughly 2 GB by arithmetic,
**not** total RAM or disk usage. Quantization metadata, tokenizer, KV cache,
runtime and other applications add overhead. A 16 GB Apple-silicon Mac is a
reasonable investigation starting point, not a vendor minimum or verified
requirement; an 8 GB machine might run a small context but needs proof under
normal memory pressure. No user hardware is known. Large contexts and parallel
requests make memory/latency worse. [L1–L3]

Ollama defaults to keeping a model loaded for five minutes and exposes
`keep_alive`; warm standby trades memory/battery for shorter cold starts. It now
also supports cloud features, so an offline design must explicitly select local
weights, disable cloud/web features, keep loopback binding, avoid remote tools,
and prove network isolation. These are future design precautions, not actions
performed here. For MLX, pin locally cached artifacts rather than depending on a
Hub fetch during recovery. Do not fine-tune on Personal Corrections: approval for
live reuse is not authorization for model training. [L1–L4, R1]

### Non-model improvements and the limits of approved mappings

Examples are synthetic **desired boundaries**, not observed tool results:

- `Please send teh agenda.` → `Please send the agenda.` is a candidate spelling
  improvement. Even this needs a frozen eligibility rule and abstention on ties;
  a dictionary's single suggestion is not proof of intended meaning.
- A contextual real-word error such as `Meet me at the pear.` cannot reliably
  become `pier` from dictionary validity alone. Context or explicit confirmation
  is necessary; do not mark it “certain.”
- Spacing fixes must preserve `3.14`, URLs, code, formatting, quotations and
  intentional repetition. Do not globally collapse whitespace or delete repeated
  words. New spelling/grammar rules need a versioned Cleanup contract and affected
  regression coverage, not a silent change to Conservative validation. [R1, S1–S4]

Personal Corrections currently authorize approved mappings for later Smart
assistance. Target retrieval uses normalized exact aliases at lexical boundaries,
enabled state, deterministic ordering, at most 50 unique mappings, and approved
applicability context. Additions/removals are episode evidence, not reusable
replacement entries. Ambiguous context may cause abstention. [R2]

A saved `pear → pier` must not change `pear tart`, a substring of `pearl`, or a
different contextual occurrence. Local models can use the same bounded evidence
contract when retrieval is implemented. Deterministic application would require
an explicit policy for context-free versus context-dependent eligibility,
conflicting/overlapping aliases, original-span replacement, case/Unicode offsets,
and no cascading substitutions. Disable/delete/revision changes must take effect
before reuse. Do not let Personal Corrections change independent Cleanup, or
describe saved approval as already delivering offline repairs. [R1, R2, R4, R6]

## Hybrid recovery that addresses the frustration

Proposed direction, not a replacement for the confirmed continuity contract:

1. Keep current Original available immediately and preserve explicit Original
   selection. If eligible, show the specified previous Prepared + exact suffix
   while a full-current request runs. Never normalize that suffix or splice in
   additional local fixes under the continuity label. [R3]
2. Produce a separately identified, validated full-current local candidate using
   a frozen account-independent rule subset; in Smart only, optionally use a
   local model with bounded approved evidence once that boundary exists. This
   can improve a first failed draft without any checkpoint. It needs a new
   execution/result contract; the current failure result is Original. [R1–R4]
3. When authorized and online, use the bounded independent cloud routes for
   contextual repairs. Reserve local recovery time, or prepare the cheap local
   candidate without waiting for cloud failure; don't serialize three long
   timeouts. A later result must match draft/version/evidence bindings and must
   not override user Outgoing selection. [R3–R5]
4. On exhaustion, distinguish **local preparation**, **provisional continuity**,
   and **Original—no eligible corrections**. Show unsupported/uncertain repairs
   for review. Only full validated current success has full-success semantics;
   do not relabel degraded output to inflate recovery statistics. [R1, R3]

The independent route addresses provider-specific access failure; the offline
path addresses shared Internet/cloud failure; continuity addresses loss of prior
work. These are complementary, not interchangeable solutions. Browser/server/
device failure still needs separate handling, and an empty or ineligible input
may correctly produce no changes.

## Smallest synthetic proof before choosing

**Not run here.** This is a proposed feasibility gate, not a formal evaluation
restart, corpus, efficacy study, or private-text collection. Execution, paid calls,
model acquisition and any formal quality evaluation need separate authorization.

1. **Access proof with mocks:** Exercise primary timeout, primary invalid auth,
   transient 429, permanent quota, both routes unavailable, invalid output,
   request safety refusal, and local helper unavailable. Demonstrate independent
   route budgets/quota identities, terminal safety behavior, bounded completion,
   correct degraded labels and Original selection. Mocks prove routing, not that
   a real account is funded or reachable. [R4, R5]
2. **Offline usefulness proof:** Use 12 hand-written cases, two each for
   misspelling, spacing/punctuation, valid-word ambiguity, approved mapping with
   applicable/inapplicable context, protected name/URL/number/code, and
   negation/intentional repetition. Define expected edits or abstention before
   inspecting output. Require a visible warranted improvement on at least the
   clear spelling case and the eligible bounded preparation case when both
   clouds fail—not merely a nonempty response. Require preservation of protected
   meaning in the negative cases. Two positive cases prove feasibility, not
   population-level effectiveness. Profile use needs synthetic approved records,
   never a user's saved data. [R1, R2]
3. **One actual-Mac local-model proof:** Record hardware/RAM/macOS, pinned model,
   quantization, prompt and dependency versions. On the same cases, compare just
   the eligible Apple path or Qwen path against the deterministic floor. With
   network blocked after authorized asset acquisition, confirm no outbound
   requests; measure cold/warm completion, peak memory and a long-context boundary
   under ordinary competing load. A route that misses the chosen recovery budget
   or adds unsupported meaning is not a useful automatic backup. No latency
   threshold is established by this reading research. [A1–A4, L1–L3]
4. **Continuity proof:** One asymmetric corrected prefix plus a distinctive exact
   appended suffix, then primary/all-route failure, an edit inside the prefix,
   changed Personal Corrections evidence, and a stale late response. Verify the
   exact join while eligible and invalidation otherwise; no edits lost and no
   suffix claimed as corrected. Do not count this as new correction quality. [R3]

Choose after these proofs, not before: independent cloud routing is the smallest
existing access-resilience lever; deterministic preparation is the smallest
offline improvement lever; one local model is justified only if it adds useful
contextual repairs within the Mac's budget. If only ambiguous real-word errors
matter, a spelling-only backup is insufficient even when very reliable.

## Sources

Repository sources were inspected at the supplied revision; external first-party
pages were accessed on 2026-10-07. Model cards and vendor docs establish capability
and terms, not Sayloom correction efficacy. Prices, OS availability and model
limits can change; pin and recheck before implementation.

- **R1:** [Product contract](../../PRODUCT.md), especially correction modes, text-only purpose, personalization and research boundary.
- **R2:** [Personal Corrections specification](../../docs/personal-corrections-implementation-spec.md), deterministic retrieval, reusable replacement eligibility and failure behavior; a target contract with partially delivered storage/approval.
- **R3:** [Continuity and resilience specification](../../docs/smart-correction-continuity-and-resilience-spec.md), verified baseline and pending checkpoint contract.
- **R4:** [Cleanup routing, adapters and validation source](../../src/local_text/cleanup.py), `ROUTE_FAILURE_ACTIONS`, `SequentialCleanupProvider`, `CleanupService`.
- **R5:** [Router tests](../../tests/test_cleanup_router.py), budget, quota-group, breaker, safety and cancellation cases.
- **R6:** [Personal Corrections storage/approval source](../../src/local_text/personal_corrections.py).
- **R7:** [Documentation lifecycle map](../../docs/README.md), superseded ADR-0001 product boundary and deferred evaluation references.
- **C1:** [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), per-project quota and non-guaranteed capacity.
- **C2:** [OpenAI rate limits](https://developers.openai.com/api/docs/guides/rate-limits), organization/project/shared-model scopes and retry limits.
- **C3:** [Gemini troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting), access errors and SDK retry behavior.
- **C4:** [OpenAI error codes](https://developers.openai.com/api/docs/guides/error-codes), transient versus billing/auth/usage failures.
- **C5:** [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), standard paid Gemini 2.5 Flash-Lite token prices.
- **C6:** [OpenAI pricing](https://developers.openai.com/api/docs/pricing), standard GPT-4.1 mini token prices.
- **C7:** [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data), training, abuse monitoring, Responses storage and ZDR.
- **C8:** [Gemini API terms](https://ai.google.dev/gemini-api/terms), paid/unpaid data handling and regional exceptions.
- **A1:** [Apple Foundation Models Python SDK](https://github.com/apple/python-apple-fm-sdk), requirements, availability API and Apache-2.0 license.
- **A2:** [Foundation Models framework](https://developer.apple.com/documentation/foundationmodels), on-device versus cloud model selection.
- **A3:** [Generating content with Foundation Models](https://developer.apple.com/documentation/foundationmodels/generating-content-and-performing-tasks-with-foundation-models), model readiness and documented 4,096-token system context; [Apple Intelligence requirements](https://support.apple.com/en-us/121115), compatible Macs, language and system-asset storage (current support page emphasizes the newer OS generation, not the Python SDK's minimum).
- **A4:** [Apple generative-output safety](https://developer.apple.com/documentation/foundationmodels/improving-the-safety-of-generative-model-output), guardrail errors and model refusals.
- **L1:** [MLX LM source/README](https://github.com/ml-explore/mlx-lm), Apple-silicon inference, quantization, caching, memory limitations and MIT license.
- **L2:** [Ollama macOS requirements](https://docs.ollama.com/macos), macOS 14+, Apple M GPU/CPU and x86 CPU.
- **L3:** [Ollama FAQ](https://docs.ollama.com/faq), local privacy, cloud disablement, loopback, keep-alive, queueing and memory; [runtime license](https://github.com/ollama/ollama/blob/main/LICENSE).
- **L4:** [Qwen's Qwen3-4B-Instruct-2507 model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), non-thinking model and local runtime support; [model license](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/main/LICENSE).
- **S1:** [LanguageTool local HTTP server](https://dev.languagetool.org/http-server.html), local API and absence of cloud AI rules/synonyms.
- **S2:** [LanguageTool source/README](https://github.com/languagetool-org/languagetool), Java 17 build prerequisite and LGPL-2.1 license.
- **S3:** [SymSpell source/README](https://github.com/wolfgarbe/SymSpell), edit-distance/frequency suggestions, compound handling, MIT code and separate dictionary-source licenses. Its published speed claims are not adopted as Sayloom measurements.
- **S4:** [Apple NSSpellChecker](https://developer.apple.com/documentation/appkit/nsspellchecker), language resources, spelling/grammar checking and proposed substitutions.
