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

The prototype begins by defining, implementing, and qualifying one frozen,
account-independent **Cleanup** baseline. It then selects, integrates, and
verifies an **Automatic correction strategy** that chooses among multiple
frontier **Correction methods**, passes its result through that Cleanup
baseline, and satisfies the frozen Smart acceptance contract on approved
held-out evidence. A separately authorized limited pilot may then demonstrate
the result without making a broad efficacy claim. The initial claim remains one
primary user across representative unseen cases; multi-user efficacy, automatic
learning, and durable personalization are deferred, separate research and
product decisions.

The prototype implements the product's Cleanup-to-Smart sequence; it does not
add another correction mode. The separately authorized **Evidence Collection**
interaction is optional research instrumentation independent of both stages.
It creates prospective private observations for task-specific Cleanup and Smart
evaluation views; it does not train either stage, create correction memory, or
establish multi-user efficacy.

The following are not prototype outcomes:

- production hosting, migrations, account infrastructure, or deployment;
- durable personalization learning or Correction memory;
- broader rewriting or polishing;
- audio ingestion or claims about what was spoken;
- population-wide or high-stakes safety claims;
- multi-participant operation or efficacy claims; or
- silently moving a correction between Cleanup and Smart without a versioned
  contract and new evidence.

## Verified current baseline

As of 2026-09-26, Conservative preparation is the default, source-preserving,
incomplete Cleanup implementation and rejects lexical changes. The current Smart path
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

The obsolete source-preserving Cleanup benchmark and canary toolchain has been
removed, and its protocol artifacts are historical and non-operational. No
private evaluation run is documented, and no legacy observation was migrated.
The provider-neutral automatic-strategy harness remains the independent Smart
evaluation contract; archived Cleanup protocols and evidence cannot be
reinterpreted for this prototype.

The latest external Smart evidence audit reported zero eligible and zero
held-out cases, no required-strata coverage, and no observed-use weights. This
is an evidence blocker. The approved minimum of 200 held-out cases and full
required strata remains unchanged.

## User-visible correction contract

The prototype preserves the product contract:

- The user chooses Cleanup alone or Smart followed by Cleanup; automatic method
  selection occurs inside Smart and is not exposed as another mode.
- Cleanup is account-independent. Context, Private correction profiles, and
  Correction memory cannot expand core Cleanup's authority.
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
- Context is request-scoped. Profile evidence is user-controlled, Smart-only,
  and supplied only when explicitly enabled and relevant. Ordinary correction,
  review, copying, or inaction stores no learning.

## Candidate method and automatic-selection boundary

A Correction method is a bounded way to propose or abstain from a Smart-frontier
repair. The frozen Cleanup baseline follows frontier repair and is not a
competing method. The initial development slate must represent:

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
user. Intended text is the message the producer meant Voiceitt to produce: it
corrects meaning-bearing recognition or grammatical errors, does not
stylistically polish the wording, and does not claim an exact transcription of
the spoken words. It is wording confirmed or rewritten by that user before any
candidate output is shown; one canonical wording may have additional
user-confirmed acceptable variants.

Prospective collection follows the
[intended-meaning evidence collection contract](intended-meaning-evidence-collection-contract.md).
While collection is deliberately armed, every qualifying Voiceitt interaction is
captured or explicitly excluded. Collection triggers on the first Smart, Copy,
or target send attempt for the current Original, before candidate output or
outgoing use, and freezes Original and only contemporaneously available context
and explicitly enabled profile evidence before the producer judges Intended
text. Correction may begin only after the resulting observation or
content-free exclusion is immutably written, reread, and hash-verified. Intended
text never enters candidate input. Copy and local delivery remain blocked until
the current revision has a verified observation or exclusion receipt.

Collection produces distinct observations and may suggest only exact-repeat
relationships. Private review owns final eligibility and exclusions, additional
Intended variants, derivation and required producer confirmation of Cleanup
targets under the frozen Cleanup contract, classifications, exact-repeat
confirmation, near-duplicate/related-version grouping, observed-use weights,
and partitioning.
Unreviewed observations remain stored but do not count as eligible, cannot be
partitioned, and cannot be used in development or evaluation.

Before acceptance-grade evidence, an explicitly exploratory milestone applies:
at least 50 eligible cases across the package, with meaningful coverage of
important Voiceitt outcomes, including correct text, cleanup-only text, meaning
errors, context- or profile-dependent cases, and ambiguity or abstention where
applicable. The milestone is directional exploration only; it cannot support
efficacy claims and does not replace the acceptance protocol. After that corpus
is privately reviewed, private review groups related cases and freezes the
development, validation, and held-out partitions before any candidate work.
Only development evidence opens for candidate exploration; validation and
held-out evidence stay sealed so those cases remain eligible for later formal
evaluation. Candidate exploration starts only after this milestone. Review,
classification, coverage, grouping, and partition progress belong to a separate
local private-review workflow, not the collector page. Real collection may
start once the collector itself passes complete acceptance even while
private-review tooling is still being built, but evidence cannot open for
development until that review and partition tooling exists.

The participant package must freeze eligibility, exclusions, related-case
groups, near-duplicates, one global 60/20/20
development-validation-held-out assignment across both evaluation views,
time-appropriate context and profile snapshots, all required strata, and
observed-use weights. The Smart held-out partition must contain at least 200
eligible cases and every required stratum. Typed, pasted, synthetic, practice,
or provider-generated cases may support engineering checks but cannot establish
prototype acceptance.

The first approved package belongs to one primary user. Contracts include an
opaque participant and package identity, but do not require hosted accounts.
Future participants use isolated packages. Combining frozen snapshots requires
a separately authorized manifest and a new protocol that reports both
within-user performance and unseen-user generalization with participant-aware
partitions and confidence analysis.

Original, Intended, Prepared, context, profile data, case identifiers, review
mappings, databases, and exports remain in approved user-controlled storage
outside Git, GitHub, Mandrel, orbs, application operating state, and routine
logs. Only content-free audits, hashes, aggregate results, and authorization
records may be shared in issues.

## Evaluation protocol and acceptance gates

Cleanup and Smart are separate task-specific views of the same prospectively
collected evidence. Cleanup is evaluated and frozen first against targets
permitted by its account-independent contract. User-specific ambiguity requires
preservation or abstention. Failure leaves Conservative as the actual baseline
and blocks Smart comparison.

Smart evaluation then measures both incremental frontier value over the frozen
Cleanup baseline and complete Smart-to-Cleanup Prepared quality against
producer-confirmed Intended text. No-change, Cleanup-solvable,
profile-independent, profile-dependent, and abstention cases remain visible as
separate strata. A promoted rule creates new Cleanup and Smart versions and
must be tested on evidence not used to choose it; prior results are never
relabelled.

Development evidence shapes Smart methods and routing. The exploratory milestone is
additive and does not weaken the acceptance protocol: decision-grade evidence
still requires at least 200 eligible held-out cases, every required stratum,
observed-use weights, and the frozen protocol gates. Validation evidence selects
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

Integration must preserve the frozen Cleanup behavior, fail-open Original, exact
Outgoing selection, server-derived repair metadata, request-scoped context,
explicit profile enablement, stale-result invalidation, content-free routine
logging, and normal startup without migrations. Development cases may inform
methods, prompts, retrieval, and routing, but case text must not silently enter
the shipped runtime or correction memory. It requires synthetic and
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
| 1. Freeze initial Cleanup | Revised #112 defines account-independent lexical eligibility and abstention, then focused child work implements the smallest viable baseline. |
| 2. Retire the obsolete benchmark path | Completed: the old source-preserving benchmark and canary toolchain left the current tree without changing ordinary Cleanup or migrating a legacy observation. Separate capture, storage, API, UI, and migration removal remains outside this stage. |
| 3. Accumulate and review fresh evidence | Armed collection writes verified observations to the participant package. Private review derives Cleanup targets, freezes shared related-case grouping and partitions, and prepares both evaluation views. |
| 4. Qualify Cleanup | The expanded Cleanup baseline passes its frozen account-independent qualification; otherwise Conservative remains the baseline and Smart comparison stops. |
| 5. Audit Smart evidence | An exploratory milestone of at least 50 eligible cases precedes candidate work but supports no efficacy claim. A content-free audit later proves all required Smart strata and at least 200 eligible held-out cases. |
| 6. Build experimental adapters | Required frontier method families implement the common harness contract, remain outside runtime, and pass synthetic privacy, determinism, repair-trace, fail-open, timeout, and budget tests without provider traffic. |
| 7. Compare on development evidence | The staged search and one allowed targeted expansion finish against frozen Cleanup; surviving complete strategies, routers, manifests, budgets, and planned ablations freeze before held-out results open. |
| 8. Evaluate held out and select | An approved run produces the write-once private evidence package and content-free report; a winner passes every gate, or the recorded outcome is no qualifying strategy. |
| 9. Integrate the winner | The selected multi-method strategy becomes Smart; losing experimental families remain outside runtime and Cleanup/fail-open contracts still pass. |
| 10. Verify automatic correction | Automated and browser checks cover routing, repairs, uncertainty, stale results, CART display, failures, privacy, and exact Outgoing; verification records an explicit pass/stop outcome. |
| 11. Run a limited pilot | Only after separate operational authorization, the bounded pilot completes, retains no participant text by default, records structured feedback, tears down access, and makes no broader claim. |

## Remaining open decisions

- Which candidate configurations survive development and validation.
- Whether measured headroom justifies parallel generation plus adjudication or a
  specialized correction model.
- Which complete strategy wins held-out selection, or whether none qualifies.
- The selected winner's exact runtime adapter and uncertainty signal, within
  the existing Smart user-visible contract.
- Whether to authorize a limited shareable pilot and, if so, its named
  audience, provider posture, budget, duration, and teardown plan.

These decisions do not reopen the frozen Smart quality gates. Any proposal for
a user-visible mode beyond Cleanup and Smart conflicts with the current product
contract and must stop for an approved `PRODUCT.md` decision rather than
changing that contract implicitly. Evidence Collection is not such a mode;
multi-participant operation or claims require a new protocol and authorization.
