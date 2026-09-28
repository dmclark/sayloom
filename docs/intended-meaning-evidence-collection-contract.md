# Intended-meaning evidence collection contract

- **Status:** Confirmed participant-evidence-package and collection specification;
  implementation reconciliation required before further implementation
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Prototype authority:**
  [`automatic-correction-prototype-spec.md`](automatic-correction-prototype-spec.md)
- **Decision source:**
  [Confirmed package-contract interview](https://ampcode.com/threads/T-01a0e53c-8153-714f-93a3-67df8d02e8b6)
- **Collection task:**
  [Collect intended-meaning evidence during ordinary use](https://github.com/dmclark/sayloom/issues/61)
- **Downstream review task:**
  [Freeze and audit intended-meaning evidence partitions](https://github.com/dmclark/sayloom/issues/62)

This specification defines the bounded browser interaction and **participant
evidence package** used to collect evidence for separate Cleanup and Smart
evaluation views. **Evidence package** is the short form. The package is a
private collection archive, not an evaluation-ready dataset, training corpus,
personalization store, or correction memory. Existing issue completion does not
authorize review, snapshot creation, provider access, shared evaluation work,
spending, held-out execution, deployment, or pilot operation.

## Scope

Evidence Collection is optional, temporary research instrumentation for one
participant. The participant, text producer, application operator, package
owner, administrator, and custodian are distinct roles even when one person
initially fills all of them. Evidence Collection is a visibly armed
browser-session state independent of Cleanup and Smart correction, not a third
correction mode. The package is the durable external artifact written by that
interaction. Collection creates prospective private observations awaiting
review; it does not establish eligibility, train either stage, create
correction memory, or establish multi-user efficacy.

The interaction collects actual Voiceitt-generated English text from the
primary user and the producer's Intended-text judgment before any candidate
Prepared text is exposed. Intended means the message the producer meant
Voiceitt to produce: it corrects meaning-bearing recognition and grammatical
errors, does not stylistically polish the text, and does not claim an exact
transcription of the spoken words. Typed, pasted, synthetic, practice,
provider-generated, or retrospectively reconstructed text cannot become
acceptance evidence.

The initial implementation and claim remain single-participant and need no
hosted account. Every package and observation binds to opaque participant and
package identities. One package accumulates one participant's observations
across separately armed sessions for one collection-contract version. Each
future participant requires an isolated package, approval, retention, and
withdrawal boundary. Recruitment, hosted account linkage, multi-participant
operation, candidate testing during collection, and multi-user efficacy claims
are outside this contract.

## Package administration and readiness

The browser cannot create, migrate, repair, or approve an evidence package.
External administration creates the package at the exact absolute external
directory configured by `LOCAL_TEXT_EVIDENCE_PACKAGE_DIRECTORY`; that setting
is independent of `LOCAL_TEXT_EVALUATION_DATA_DIRECTORY`. Creation establishes
opaque participant and package identities, package and collection-contract
versions, creation time, owner-only permissions, and the participant ownership
boundary.

Approval of the exact manifest is the package owner's informed acceptance of
the participant binding and the versioned collection, privacy, permitted-use,
and retention contract. It is not merely a file-integrity confirmation and does
not authorize review, snapshot creation, evaluation execution, provider access,
training, personalization, publication, or sharing. An approved package is
never migrated in place. A material contract change requires a newly approved
package or an explicitly derived immutable artifact with provenance.

Arming is available only when the configured package passes content-free checks
for:

- approved package and contract versions;
- opaque participant identity, package identity, and package ownership;
- restrictive directory and artifact permissions;
- append-only observation and audit writes; and
- artifact hashing and reread verification support.

Package paths and private package contents must not enter browser-visible
configuration, application operating state, routine logs, Git, GitHub, Mandrel,
or an orb.

An exact package copy or move remains portable when its bytes and relative
structure are preserved, owner-only permissions are restored, configuration
names the new package root, and readiness and hash checks pass. The absolute
path is not package identity or part of approval.

## Ownership, permitted use, and retention

The participant owns and controls the package and its private observations. An
administrator or custodian receives no independent right to retain, reuse,
upload, or share them. Package approval defines the only purpose-bound uses for
which later authorization may be granted: collection, verification, private
review, classification, partitioning, and derivation of Cleanup and Smart
evaluation views. It does not activate those later operations. An authorized
development view may inform rules, prompts, routing, and other Smart logic that
does not contain or permit reconstruction of private evidence.

Only these purpose-bound workflows may read package data:

- Evidence Collection, while explicitly armed, for readiness, collection,
  immediate verification, content-free counts, exact-repeat suggestions, and
  withdrawal;
- an explicitly authorized private-review workflow; and
- an explicitly authorized snapshot builder.

Normal startup, ordinary Cleanup and Smart operation, correction providers, and
evaluation runners never read the live package. Package approval, per-session
collection, private review, snapshot creation, and each evaluation run are
separate authorization layers. Sending case data to a third-party provider,
publishing examples or reconstructive aggregates, training or fine-tuning,
personalization, correction memory, unrelated analysis, and claims beyond the
evaluated population or protocol require additional explicit authorization.

Review records, classifications, Intended variants, targets, groups,
partitions, and case-level evaluation views remain private participant data
under the source package's purpose, retention, and withdrawal restrictions.
Only non-reconstructive aggregate findings and generic Smart logic may leave
that boundary under the approved purpose.

Private content remains only while collection, review, or an authorized
evaluation purpose is active. Extending retention to another phase or purpose
requires owner review. **Deferred:** exact retention dates or phase-specific
durations belong to the approved package policy. Owner-managed backups are
private copies under the same restrictions and must account for withdrawal;
Sayloom provides no implicit managed backup.

Closing a package prevents new collection, review, snapshots, and evaluation.
Already authorized activity stops cleanly, after which the owner chooses
complete deletion or private archival storage under an explicit policy.
**Deferred:** the exact closure and revocation mechanism.

## Arming and session lifetime

Arming requires a fresh session attestation that collected cases are actual
primary-user Voiceitt-generated English. The armed state is visually persistent
while active and never becomes a durable default. Observations accumulate in
the same approved package across multiple armed sessions; every armed session
requires fresh attestation and a fresh package readiness result.

A query parameter may request Evidence Collection mode, but it never authorizes
or arms collection by itself. Arming requires a bounded same-browser-session
collection lease bound to the package readiness result. A page refresh may
reconnect to a still-valid lease; without a valid lease, the user must attest
and arm again. Evidence Collection disarms on explicit stop, browser-session
loss or lease expiry, application restart, package unavailability, write
failure, or hash-verification failure. The exact query parameter name, lease
token format, timeout, and reconnection mechanics are deferred implementation
details.

While armed, the page shows clearly labelled content-free counts: verified
observations and exclusions for the current lease-session, and cumulative
active verified observations in the approved package. Cumulative counts persist
across multiple armed sessions and exclude withdrawn observations. Raw counts
are distinct from reviewed eligible cases and must not imply progress toward
eligibility.

The obsolete source-preserving Cleanup evaluation capture must not receive new
observations and is scheduled for removal. Evidence Collection is the sole
prospective source for the new task-specific Cleanup and Smart views.

## Consequential actions and pre-exposure state

Automatic preparation, explicit Cleanup or Smart, Copy, and target send are
consequential while Evidence Collection is armed. Collection triggers on the
first preparation, Copy, or target send attempt for the current Original,
before any candidate output or outgoing use. Before one of those actions can
expose or consume a candidate for the current Original revision, Sayloom must:

1. conceal current and stale Prepared text, repair details, candidate errors,
   and Prepared selection;
2. make no candidate request;
3. keep Original editable;
4. block Copy and hold an invoked target send in the same request; and
5. request the producer's Intended-text judgment.

Changing Original by any character makes an earlier judgment or receipt stale.
Editing Original while confirmation is pending cancels that frozen snapshot and
starts a prospective new case. Empty or whitespace-only Original creates no
observation and opens no judgment interaction.

## Producer judgments

Only the person who produced Original may establish Intended text. An
administrator, reviewer, model, or assisting operator cannot infer or replace
that judgment. **Deferred:** any future proxy-judgment arrangement requires a
separate contract and explicit provenance.

The producer must choose exactly one disposition:

1. **Ready as-is** — Intended equals Original and needs no preparation.
2. **Meaning right; Cleanup needed** — Intended equals Original, but presentation
   Cleanup remains useful.
3. **Edit Intended** — edit an Original-initialized copy until every lexical or
   grammatical meaning difference is corrected.
4. **Not Voiceitt** — exclude because the source attestation does not apply.
5. **Cannot reliably reconstruct** — exclude because Intended text cannot be
   established with confidence.
6. **Exclude** — omit the observation without asserting either preceding
   reason.

The first two dispositions deliberately retain identical Intended text as
distinct producer judgments. Additional acceptable variants and evidence
classifications belong to downstream private review.

Cancel saves nothing and exposes no candidate. Capture failure always offers an
explicit choice among Retry, Continue without collecting, and Cancel.
Continuing without collecting disarms Evidence Collection; the fallback is
never silent. Intended confirmation happens during capture, before any
exposure. Separate private corpus review may happen asynchronously in later
sessions.

## Frozen observation boundary

At the consequential trigger, Sayloom freezes:

- opaque participant and package identities;
- Original;
- contemporaneous request context;
- the explicitly enabled Private correction profile snapshot;
- correction contract and prompt version;
- source-attestation and package-contract versions;
- trigger timestamp; and
- a new observation identifier.

At confirmation, Sayloom additionally freezes:

- disposition;
- canonical Intended text for a collected observation;
- confirmation timestamp; and
- binding artifact hashes.

The frozen Original is never overwritten. Every collected observation receives
a new immutable record, even when it exactly repeats prior evidence. Collection
provenance and storage integrity do not make an observation evaluation-eligible;
only downstream private review can do that.

## Candidate isolation and release

Correction may run only after the new observation or exclusion record has been
written append-only, reread, and hash-verified. After a verified capture or
exclusion, current-product behavior resumes for the interaction. Experimental
candidates run later against authorized frozen views, never against the live
package. If the capture session ends before confirmation plus write, reread,
and hash verification, no observation was collected. Cleanup candidate input
consists only of frozen Original and the frozen Cleanup contract; core Cleanup
is account-independent. Smart candidate input consists of frozen Original plus
only the context and profile evidence legitimately available at the trigger.
Intended text, disposition details, derived Cleanup targets, and later evidence
must never enter either candidate input.

Prepared text, repair details, and provider execution metadata are runtime
results, not collection artifacts. After verified capture and correction, the
user may inspect Prepared. Copy and target send each require a second explicit
invocation; no blocked action is queued, delayed, or replayed.

## Exclusion, withdrawal, and exact repeats

An exclusion discards Original, Intended, context, and profile content and
retains only strict content-free audit metadata. **Not Voiceitt** records source
contamination, **Cannot reliably reconstruct** records unavailable Intended
text and potential missingness bias, and **Exclude** preserves omission without
a reason. All remain ineligible and may be reported only as content-free
aggregate counts.

A later withdrawal removes the observation's private content, appends an
immutable tombstone, and retains no content-derived hash, length, or grouping
information. Immutability means an observation cannot be edited or replaced;
withdrawal is the defined privacy exception to content retention.

Withdrawal removes an observation from future review, snapshots, development,
and evaluation and invalidates or supersedes unexecuted private artifacts that
contain it. Retained private copies, including active owner-managed backups,
remain subject to removal. Already acquired non-reconstructive aggregate
findings or generic logic cannot necessarily be unlearned; approval and review
must disclose that limit.

Collection may suggest an exact-repeat relationship only when both Original and
Intended match after:

- Unicode NFC normalization; and
- CR/LF normalization to LF.

No case, whitespace, punctuation, or other folding is allowed. Observations
remain separate. Downstream private review confirms exact repeats and owns all
near-duplicate and related-version grouping.

## Copy and target-send gate

The collection lease gates server-side Outgoing consumption. Copy and target
send are permitted only when the current Original revision has a verified
collected-observation or exclusion receipt. A request without that receipt is
rejected without private text or retained action. After verified capture and
correction, the user explicitly invokes Copy or target send again. Cancel or
close writes no evidence and leaves Evidence Collection armed for the next item.

The browser must surface the conflict without including private text. Routine
logs remain content-free.

## Failure behavior

Ambiguous readiness, unavailable package state, write failure, reread mismatch,
or hash failure prevents candidate exposure and disarms Evidence Collection.
None of these failures may silently continue as uncollected candidate execution,
write to the preserved practice store, or persist private content in application
state or logs.

Ordinary uncollected use is available only through an explicit recovery choice.
Original remains editable throughout failure recovery.

## Task boundary

The collection task owns:

- package administration interfaces, append-only writes, readiness, and hashes;
- source attestation, session lease, arming, and disarming;
- pre-exposure judgments for preparation, Copy, and target send;
- immutable prospective observations, receipts, exclusions, and withdrawal;
- provisional exact-repeat suggestions;
- failure handling;
- removal of the superseded Smart **Correct and add example** path; and
- synthetic browser and storage-boundary tests.

The downstream review task owns:

- private batch review and final eligibility or exclusion;
- separate provenance-bearing review records that never rewrite collection
  history;
- additional Intended variants;
- derivation of a Cleanup target under one frozen account-independent Cleanup
  contract and producer confirmation wherever judgment is required;
- situation, difficulty, error, context, profile, and high-stakes
  classifications;
- exact-repeat confirmation and near-duplicate or related-version grouping;
- observed-use weights;
- one group-preserving recorded-seed 60/20/20 assignment shared by Cleanup and
  Smart views;
- immutable protocol-ready Cleanup and Smart views of the participant package;
  and
- the content-free sufficiency audit, including every required stratum and the
  200-case held-out minimum.

An explicitly exploratory milestone precedes acceptance-grade evidence: at
least 50 eligible cases across the package with meaningful coverage of
important Voiceitt outcomes. The milestone is directional exploration only and
cannot support efficacy claims. After that corpus is privately reviewed,
review groups related cases and freezes the development, validation, and
held-out partitions before any candidate work; only development evidence opens,
and validation and held-out evidence stay sealed. Unreviewed observations
remain stored but do not count as eligible, cannot be partitioned, and cannot
be used in development or evaluation. Review, classification, coverage,
grouping, and partition progress belong to a separate local private-review
workflow, not the collector page.

The superseded Smart **Correct and add example** path and the obsolete
source-preserving Cleanup evaluation system are separate removal work. No data
from either path migrates into a participant package. Any disposition of
external private data requires separate verification and authorization.

## Evaluation views and participant expansion

One reviewed observation may enter both views without duplicate collection.
The Cleanup view uses only the target permitted by the frozen Cleanup contract;
user-specific ambiguity requires preservation or abstention. The Smart view
uses producer-confirmed Intended text and keeps no-change, Cleanup-solvable,
frontier, profile-dependent, and abstention cases visible. Profile-independent
and profile-dependent Smart strata are reported separately.

Cleanup freezes before Smart comparison. Related observations keep the same
global partition in both views. A rule promoted from Smart creates new versioned
targets and must be evaluated on evidence not used to choose it; existing
results are never relabelled.

A later multi-participant evaluation combines only explicitly authorized frozen
package snapshots through a purpose-bound manifest that identifies the exact
inputs, retention terms, partitioning, and allowed analysis. Source-package
ownership remains unchanged. The evaluation must use participant-aware grouping
and confidence analysis and report both within-user performance and unseen-user
generalization. A pooled case-level result alone cannot support a multi-user
claim.

## Current implementation reconciliation

Issue [#118](https://github.com/dmclark/sayloom/issues/118) is the correct but
incomplete configuration slice of this specification. Its implementation gives
Evidence Collection the dedicated exact-root
`LOCAL_TEXT_EVIDENCE_PACKAGE_DIRECTORY`, keeps evaluation storage independent,
uses external administration, avoids package creation during normal startup,
and keeps readiness content-free. That bounded change should not absorb the
broader package-contract work.

Before the implementation represents this complete specification, follow-up
work must:

- replace the `eligible_observation` storage label with terminology that does
  not claim review eligibility;
- add opaque participant identity and explicit ownership, permitted-use, and
  retention terms to package creation and approval;
- make approval represent informed acceptance rather than integrity alone;
- define package closure and revocation; and
- propagate withdrawal through retained private derived artifacts.

These gaps do not invalidate issue #118's configuration boundary. They prevent
the current package implementation from being treated as the complete confirmed
contract.

## Verification boundary

Automated verification uses synthetic fixtures only and makes no provider calls.
It must exercise package readiness, restrictive permissions, append-only writes,
reread and hash verification, lease arming, reconnection, and expiry,
content-free armed-page counts, every producer disposition, cancellation and
staleness, failure disarming, withdrawal, exact-repeat normalization, Cleanup
and Smart pre-exposure behavior, shared partition identity, task-specific target
isolation, explicit second invocation for Copy and target send, correction
failure and cancellation, and absence of Intended leakage or text-bearing
routine logs.
