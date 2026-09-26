# Intended-meaning evidence collection contract

- **Status:** Confirmed interaction and participant-package contract; issue
  reconciliation required before further implementation
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Prototype authority:**
  [`automatic-correction-prototype-spec.md`](automatic-correction-prototype-spec.md)
- **Collection task:**
  [Collect intended-meaning evidence during ordinary use](https://github.com/dmclark/sayloom/issues/61)
- **Downstream review task:**
  [Freeze and audit intended-meaning evidence partitions](https://github.com/dmclark/sayloom/issues/62)

This contract defines the bounded browser interaction and participant-package
boundary for prospectively collecting evidence used by separate Cleanup and
Smart evaluation views. Existing issue completion does not authorize the new
shared evaluation work. This document does not authorize access to private
evidence, provider calls, spending, held-out execution, deployment, or pilot
operation.

## Scope

Evidence Collection is optional, temporary research instrumentation for one
participant who is initially also the producer, operator, owner, and package
owner. It is a visibly armed browser-session state independent of Cleanup and
Smart correction, not a third correction mode. It creates prospective private
observations only; it does not train either stage, create correction memory, or
establish multi-user efficacy.

The interaction collects actual Voiceitt-generated English text from the
primary user and the producer's Intended-text judgment before any candidate
Prepared text is exposed. Intended means the message the producer meant
Voiceitt to produce: it corrects meaning-bearing recognition and grammatical
errors, does not stylistically polish the text, and does not claim an exact
transcription of the spoken words. Typed, pasted, synthetic, practice,
provider-generated, or retrospectively reconstructed text cannot become
acceptance evidence.

The initial implementation and claim remain single-participant and need no
hosted account. The contract nevertheless binds every package and observation
to opaque participant and package identities. Each future participant requires
an isolated package, consent, retention, and withdrawal boundary. Recruitment,
hosted account linkage, multi-participant operation, candidate testing during
collection, and multi-user efficacy claims are outside this contract.

## Package administration and readiness

The browser cannot create, migrate, repair, or approve an evidence package.
External administration owns those actions. Arming is available only when the
configured package passes content-free checks for:

- approved package and contract versions;
- opaque participant identity, package identity, and package ownership;
- restrictive directory and artifact permissions;
- append-only observation and audit writes; and
- artifact hashing and reread verification support.

Package paths and private package contents must not enter browser-visible
configuration, application operating state, routine logs, Git, GitHub, Mandrel,
or an orb.

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
- canonical Intended text for an eligible observation;
- confirmation timestamp; and
- binding artifact hashes.

The frozen Original is never overwritten. Every eligible observation receives
a new immutable record, even when it exactly repeats prior evidence.

## Candidate isolation and release

Correction may run only after the new observation or exclusion record has been
written append-only, reread, and hash-verified. After a verified capture or
exclusion, current-product behavior resumes for the interaction; experimental
correction candidates run later, offline, against the collected package. If the
capture session ends before confirmation plus write, reread, and hash
verification, no case was collected. Cleanup candidate input consists only of
frozen Original and the frozen Cleanup contract; core Cleanup is
account-independent. Smart candidate input consists of frozen Original plus
only the context and profile evidence legitimately available at the trigger.
Intended text, disposition details, derived Cleanup targets, and later evidence
must never enter either candidate input.

Prepared text, repair details, and provider execution metadata are runtime
results, not collection artifacts. After verified capture and correction, the
user may inspect Prepared. Copy and target send each require a second explicit
invocation; no blocked action is queued, delayed, or replayed.

## Exclusion, withdrawal, and exact repeats

An exclusion discards Original, Intended, context, and profile content and
retains only strict content-free audit metadata. A later withdrawal removes the
observation's private content, appends an immutable tombstone, and retains no
content-derived hash, length, or grouping information.

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
eligible-observation or exclusion receipt. A request without that receipt is
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
package snapshots. It must use participant-aware grouping and confidence
analysis and report both within-user performance and unseen-user
generalization. A pooled case-level result alone cannot support a multi-user
claim.

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
