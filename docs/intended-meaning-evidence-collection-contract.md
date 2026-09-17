# Intended-meaning evidence collection contract

- **Status:** Approved interaction and external-package contract
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Prototype authority:**
  [`automatic-correction-prototype-spec.md`](automatic-correction-prototype-spec.md)
- **Collection task:**
  [Collect intended-meaning evidence during ordinary use](https://github.com/dmclark/sayloom/issues/61)
- **Downstream review task:**
  [Freeze and audit intended-meaning evidence partitions](https://github.com/dmclark/sayloom/issues/62)

This contract defines the bounded browser interaction and external-package
boundary for prospectively collecting intended-meaning evidence. It authorizes
implementation and synthetic verification of that infrastructure. It does not
authorize access to private evidence, provider calls, spending, held-out
execution, deployment, or pilot operation.

## Scope

Evidence Collection is optional research instrumentation for one person who is
simultaneously the producer, operator, owner, and external-package owner. It is
a visibly armed browser-session state independent of Conservative and Smart
correction, not a third correction mode.

The interaction collects actual Voiceitt-generated English text from the
primary user and the producer's Intended-text judgment before any candidate
Prepared text is exposed. Typed, pasted, synthetic, practice, provider-generated,
or retrospectively reconstructed text cannot become acceptance evidence.

Accounts, roles, producer selection, multi-user isolation, live persistent
collection state, candidate testing during collection, external-data
inspection, and external-data deletion outside the defined withdrawal workflow
are outside this contract.

## Package administration and readiness

The browser cannot create, migrate, repair, or approve an evidence package.
External administration owns those actions. Arming is available only when the
configured package passes content-free checks for:

- approved package and contract versions;
- package ownership;
- restrictive directory and artifact permissions;
- append-only observation and audit writes; and
- artifact hashing and reread verification support.

Package paths and private package contents must not enter browser-visible
configuration, application operating state, routine logs, Git, GitHub, Mandrel,
or an orb.

## Arming and session lifetime

Arming requires a fresh session attestation that collected cases are actual
primary-user Voiceitt-generated English. The armed state is visually persistent
while active and never becomes a durable default.

A process-local, single-browser-session collection lease binds the armed browser
to the package readiness result. Evidence Collection disarms on explicit stop,
page reload, browser loss or lease expiry, application restart, package
unavailability, write failure, or hash-verification failure.

Cleanup evaluation capture remains available during ordinary use but is
disabled while Evidence Collection is armed.

## Consequential actions and pre-exposure state

Automatic Smart, explicit Smart, Copy, and target send are consequential while
Evidence Collection is armed. Before one of those actions can expose or consume
a candidate for the current Original revision, Sayloom must:

1. conceal current and stale Prepared text, repair details, candidate errors,
   and Prepared selection;
2. make no candidate request;
3. keep Original editable;
4. block Copy and target send; and
5. request the producer's Intended-text judgment.

Changing Original by any character makes an earlier judgment or receipt stale.
Editing Original while confirmation is pending cancels that frozen snapshot and
starts a prospective new case. Empty or whitespace-only Original creates no
observation and opens no judgment interaction.

## Producer judgments

The producer must choose exactly one disposition:

1. **Ready as-is** — Intended equals Original and needs no preparation.
2. **Meaning right; presentation cleanup needed** — Intended equals Original,
   but Conservative presentation cleanup remains useful.
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

Cancel saves nothing and exposes no candidate. Failure recovery always offers
an explicit choice among retry, ordinary uncollected use, and cancel.

## Frozen observation boundary

At the consequential trigger, Sayloom freezes:

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
written append-only, reread, and hash-verified. Candidate input consists of the
frozen Original plus only the context and profile evidence legitimately
available at the trigger. Intended text, disposition details, and later evidence
must never enter candidate input.

Prepared text, repair details, and provider execution metadata are runtime
results, not collection artifacts. After verified capture and correction, the
user may inspect Prepared. Copy and target send require a second explicit
invocation; no blocked action is queued or replayed.

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
eligible-observation or exclusion receipt. A target request without that receipt
fails with:

> Complete intended-meaning confirmation in Sayloom, then retry.

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
- pre-exposure judgments for Smart, Copy, and target send;
- immutable prospective observations, receipts, exclusions, and withdrawal;
- provisional exact-repeat suggestions;
- failure handling;
- removal of the superseded Smart **Correct and add example** path; and
- synthetic browser and storage-boundary tests.

The downstream review task owns:

- private batch review and final eligibility or exclusion;
- additional Intended variants;
- situation, difficulty, error, context, profile, and high-stakes
  classifications;
- exact-repeat confirmation and near-duplicate or related-version grouping;
- observed-use weights;
- group-preserving recorded-seed 60/20/20 partitions;
- the immutable protocol-ready evidence package; and
- the content-free sufficiency audit, including every required stratum and the
  200-case held-out minimum.

The superseded Smart **Correct and add example** browser, API, configuration,
documentation, and test path is removed during collection implementation. The
separate Cleanup evaluation system remains; its **Save evaluation case** action
is only disabled while collection is armed. Historical offline Cleanup
scaffolding is not part of this removal.

## Verification boundary

Automated verification uses synthetic fixtures only and makes no provider calls.
It must exercise package readiness, restrictive permissions, append-only writes,
reread and hash verification, every producer disposition, cancellation and
staleness, failure disarming, withdrawal, exact-repeat normalization, Smart
pre-exposure behavior, Copy and target-send receipts, explicit second
invocation, and absence of Intended leakage or text-bearing routine logs.
