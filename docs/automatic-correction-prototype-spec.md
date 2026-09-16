# Automatic correction prototype specification

- **Status:** Approved execution specification
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Initiative:** [Build Sayloom's automatic correction prototype](https://github.com/dmclark/sayloom/issues/46)
- **Scope:** Offline method comparison, selected-strategy integration, verification, and a limited shareable pilot

This specification turns the approved decisions under the initiative into the
definition of done for the automatic-correction prototype. GitHub Issues own the
work, and the existing private **Sayloom** Project shows its workflow state.
Neither this document nor issue completion authorizes private-data access,
provider calls, spending, stable-state operation, deployment, or production
hosting.

## Outcome and non-goals

The multi-method strategy is not complete today; the current Smart runtime uses
one correction method. The prototype will be done only after Sayloom has
selected, integrated, and verified an **Automatic correction strategy** that
chooses among multiple **Correction methods** to produce reviewable Prepared
text and passes the frozen acceptance contract on approved held-out evidence. A
separately authorized limited pilot may then demonstrate the result to a small
audience without making a broad efficacy claim.

The prototype is a possible implementation of the product's existing **Smart
correction** mode. It does not add a user-visible mode. Any evidence that a new
mode is required is a product decision that must be approved in `PRODUCT.md`
before implementation.

The following are not prototype outcomes:

- changing Conservative preparation or its lexical boundary;
- production hosting, migrations, account infrastructure, or deployment;
- durable personalization learning or Correction memory;
- broader rewriting or polishing;
- audio ingestion or claims about what was spoken;
- population-wide or high-stakes safety claims; or
- treating Cleanup evaluation as Smart-correction evidence.

## Verified current baseline

As of 2026-09-16, the repository implements two correction modes. Conservative
preparation is the default and rejects lexical changes. The current Smart path
uses one provider-backed least-change prompt, permits a bounded lexical edit
distance, accepts request-scoped context and explicitly enabled curated
knowledge, computes repair spans on the server, and fails open to Original on
provider, timeout, or validation failure. The interface can inspect Smart
repairs, but the production runtime does not automatically select among multiple
correction methods.

The repository also contains a provider-neutral automatic-strategy evaluation
harness with frozen registration, deterministic scheduling, injected execution,
blind repair adjudication, case-clustered confidence gates, and text-free
reporting. It is evaluation-only and is not imported by the application
runtime. The earlier fixed eight-arm Smart benchmark remains historical
scaffolding, not the prototype acceptance protocol.

The latest external evidence audit reported zero eligible and zero held-out
cases, no required-strata coverage, and no observed-use weights. This is an
evidence blocker. The approved minimum of 200 held-out cases and full required
strata remains unchanged.

## User-visible correction contract

The prototype preserves the product contract:

- The user chooses Conservative or Smart; automatic method selection occurs
  inside Smart and is not exposed as another mode.
- Original remains editable and available. A failure, timeout, invalid result,
  or abstention leaves a usable fail-open Original path.
- Prepared contains the selected strategy's result. Outgoing remains the exact
  visible Original or Prepared value selected for copying or delivery.
- Every lexical addition, removal, and replacement is computed by Sayloom and
  remains reviewable when Original is visible. Uncertain repairs receive extra
  emphasis without claiming model confidence or access to audio.
- Hiding Original changes presentation only; it does not change correction
  behavior.
- Editing or regenerating Original invalidates stale Prepared results, repair
  metadata, and review state.
- Context is request-scoped. Profile evidence is user-controlled and supplied
  only when explicitly enabled and relevant. Ordinary correction, review,
  copying, or inaction stores no learning.

## Candidate method and automatic-selection boundary

A Correction method is a bounded way to propose or abstain from lexical
repairs. Conservative preparation follows lexical repair and is not a competing
method. The initial development slate must represent:

1. abstention/fail-open to Original;
2. deterministic lexical matching;
3. bounded phonetic and contextual retrieval and ranking;
4. constrained general-model correction;
5. retrieval plus model adjudication; and
6. a specialized correction model only if earlier families leave a recurring,
   important error class it could plausibly address.

Experimental implementations are adapters to the evaluation harness and remain
outside production runtime. They receive only a case's frozen, legitimately
available evidence packet and return the common Prepared/repair contract.

Development compares the best single method plus fail-open as a control, a
fixed narrow-to-broad cascade, and a confidence- or evidence-based router. The
single-method control cannot qualify as the Automatic correction strategy.
Parallel generation plus adjudication is added only for measured quality
headroom. At most one targeted candidate-expansion round is allowed before
finalists are frozen.

## Private evidence requirements

Acceptance evidence is actual Voiceitt-generated English text from one primary
user. Intended text is wording confirmed or rewritten by that user before any
candidate output is shown; one canonical wording may have additional
user-confirmed acceptable variants.

The private package must freeze eligibility, exclusions, related-case groups,
near-duplicates, 60/20/20 development-validation-held-out partitions,
time-appropriate context and profile snapshots, all required strata, and
observed-use weights. The held-out partition must contain at least 200 eligible
cases and every required stratum. Typed, pasted, synthetic, practice, or
provider-generated cases may support engineering checks but cannot establish
prototype acceptance.

Original, Intended, Prepared, context, profile data, case identifiers, review
mappings, databases, and exports remain in approved user-controlled storage
outside Git, GitHub, Mandrel, orbs, application operating state, and routine
logs. Only content-free audits, hashes, aggregate results, and authorization
records may be shared in issues.

## Evaluation protocol and acceptance gates

Development evidence shapes methods and routing. Validation evidence selects
and freezes no more than three complete strategies and any preregistered
ablations. Held-out evidence is opened once after preregistration; a strategy
changed after opening requires fresh or formally versioned held-out evidence.
Failures, abstentions, selector mistakes, and fail-open outcomes stay in the
denominator.

For a specialist method on its routed cases, adjusted one-sided 95% confidence
bounds must show:

- at least 25% less editing from Prepared than Original;
- at least 95% correct proposed repairs; and
- at least 99% preservation of already-correct words.

Decision-grade specialist evidence also requires at least 30 routed held-out
cases and 30 proposed repairs. Otherwise the result is insufficient evidence.

For the complete Automatic correction strategy, adjusted one-sided 95%
familywise confidence bounds must show:

- at least 50% less editing from Prepared than Original;
- at least 95% correct proposed repairs;
- at least 99% preservation of already-correct words;
- at least 95% usable Prepared results; and
- at least 95% completion within 10 seconds.

Attempts still running at 30 seconds stop and fail open. Every newly introduced
wrong word is an incorrect repair. Frozen provider-call, token, and cost ceilings
stop an affected branch when exceeded. Quality and safety gates cannot be
traded away for latency, reliability, cost, or maintainability.

If more than one strategy passes, select by editing reduction, then incorrect
repairs, reliability, latency, approved cost, and maintainability, applying the
approved practical-equivalence margins. Gate-preserving ablation may simplify a
winner but may not reduce it to one correction method. If none passes, report
that outcome without weakening the protocol.

## Runtime integration boundary

Only the evidence-selected winner may enter the Smart runtime path. Integration
adapts the selected methods and frozen selector behind the existing Smart
request/result boundary; it must not copy the experimental search framework or
losing candidates into production.

Integration must preserve Conservative behavior, fail-open Original, exact
Outgoing selection, server-derived repair metadata, request-scoped context,
explicit profile enablement, stale-result invalidation, content-free routine
logging, and normal startup without migrations. It requires synthetic and
automated checks before any separately authorized private or operational use.

## Limited shareable-pilot boundary

A limited shareable pilot is a separately authorized demonstration of the
verified prototype, not production hosting or normal-use release. It may use a
small named audience, ordinary non-sensitive text, a bounded duration and cost,
and a predeclared stop condition. It must disclose that Sayloom infers from text,
is unaffiliated with Voiceitt, and has evidence only for one primary user.

The pilot retains structured feedback rather than participant text by default,
does not enable unattended or high-stakes use, and makes no broad efficacy
claim. Hosting, provider privacy and retention, participant consent, access,
spend, operation, and teardown each require explicit authorization before the
pilot starts.

## Staged delivery plan

| Stage | Observable exit criteria |
| --- | --- |
| 1. Reconcile planning | This specification and the two coordinating plans agree; the issue graph and existing Project show one executable path. |
| 2. Accumulate and audit evidence | A new content-free audit proves grouped 60/20/20 partitions, observed-use weights, all required strata, and at least 200 eligible held-out cases. Until then the outcome remains insufficient evidence. |
| 3. Build experimental adapters | Required method families implement the common harness contract, remain outside runtime, and pass synthetic privacy, determinism, repair-trace, fail-open, timeout, and budget tests without provider traffic. |
| 4. Compare on development evidence | The staged search and one allowed targeted expansion finish; surviving complete strategies, routers, manifests, budgets, and planned ablations are frozen before held-out results open. |
| 5. Evaluate held out and select | An approved run produces the write-once private evidence package and content-free report; a winner passes every gate, or the recorded outcome is no qualifying strategy. |
| 6. Integrate the winner | The selected multi-method strategy is the automatic implementation inside Smart; losing experimental families remain outside runtime and Conservative/fail-open contracts still pass. |
| 7. Verify automatic correction | Automated and browser checks cover routing, repairs, uncertainty, stale results, CART display, failures, privacy, and exact Outgoing; verification records an explicit pass/stop outcome. |
| 8. Run a limited pilot | Only after separate operational authorization, the bounded pilot completes, retains no participant text by default, records structured feedback, tears down access, and makes no broader claim. |

## Remaining open decisions

- Which candidate configurations survive development and validation.
- Whether measured headroom justifies parallel generation plus adjudication or a
  specialized correction model.
- Which complete strategy wins held-out selection, or whether none qualifies.
- The selected winner's exact runtime adapter and uncertainty signal, within
  the existing Smart user-visible contract.
- Whether to authorize a limited shareable pilot and, if so, its named
  audience, provider posture, budget, duration, and teardown plan.

These decisions do not reopen the frozen evidence boundary, protocol, or gates.
Any proposal for a user-visible mode beyond Conservative and Smart conflicts
with the current product contract and must stop for an approved `PRODUCT.md`
decision rather than changing that contract implicitly.
