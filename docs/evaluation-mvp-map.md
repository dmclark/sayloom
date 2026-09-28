# Cleanup and Smart evaluation map

- **Status:** Canonical evaluation map
- **Product authority:** [`PRODUCT.md`](../PRODUCT.md)
- **Prototype specification:**
  [`automatic-correction-prototype-spec.md`](automatic-correction-prototype-spec.md)
- **Evidence contract:**
  [`intended-meaning-evidence-collection-contract.md`](intended-meaning-evidence-collection-contract.md)
- **Issue tracker:** [`dmclark/sayloom`](https://github.com/dmclark/sayloom/issues)
- **Last reconciled:** 2026-09-26

This map separates the proven Cleanup baseline from the evolving Smart frontier,
then orders their evidence work. Implementation evidence does not prove that a
private run happened, and an approved protocol does not authorize private-data
access, provider calls, spending, stable-state operation, deployment, or
production hosting.

## Product boundary

| Stage | Contract | Evidence purpose |
| --- | --- | --- |
| **Cleanup** | Account-independent, versioned rules for presentation fixes, spelling, and contextually obvious, effectively unambiguous misrecognitions. The current Conservative implementation is presentation-only and incomplete. | Qualify and protect one frozen baseline. Cleanup evaluation is regression and release evidence, not method discovery. |
| **Smart** | Versioned, less-determinate, contextual, or user-dependent repair followed by the same Cleanup baseline. Smart is the moving frontier between frozen versions. | Discover frontier methods, measure their incremental value over Cleanup, and qualify the complete Smart-to-Cleanup result. |

Implementation technique does not set the boundary. Cleanup may use a model if
its permitted behavior is determinate and account-independent. Deterministic
code does not become Cleanup merely because it is deterministic. Private
correction profiles and Correction memory initially inform Smart only.

A Smart behavior graduates into a new Cleanup version only after a separately
frozen rule, bounded eligibility test, evidence slice, safety thresholds, and
Cleanup regression coverage establish that it is determinate and
account-independent. Reported results retain the versions they evaluated.

## One evidence source, two evaluation views

Prospective Evidence Collection records Original, producer-confirmed Intended
text, and only the context and profile evidence legitimately available before a
candidate is exposed. Controlled private review then derives and, where needed,
confirms the frozen Cleanup target. One observation may enter both evaluation
views:

| View | Target and eligibility | Required result |
| --- | --- | --- |
| **Cleanup view** | The target permitted by the frozen Cleanup contract. User-specific ambiguity requires preservation or abstention. | The account-independent baseline passes its qualification and preservation gates. |
| **Smart view** | Producer-confirmed Intended text, including no-change, Cleanup-solvable, frontier, profile-dependent, and abstention cases. | Reports frontier value over Cleanup and complete Prepared quality. Profile-independent and profile-dependent strata remain separate. |

Related cases receive one global development, validation, or held-out assignment
across both views. Cleanup freezes before Smart comparison begins. A promoted
rule creates new versioned targets and must be evaluated on evidence not used to
choose it; old results are never relabelled in place.

The first approved package and claim cover one primary user. Contracts are
participant-aware without requiring hosted accounts: each future participant
has an isolated package, and only an explicitly authorized manifest may combine
frozen snapshots. A later multi-participant protocol must report both within-
user performance and unseen-user generalization with participant-aware
partitions and confidence analysis. A pooled case score alone is insufficient.

## Ordered delivery

| Order | Milestone | Completion evidence |
| ---: | --- | --- |
| 0 | **Current implementation recorded** | Conservative source-preserving preparation remains the incomplete Cleanup implementation. The current single-method Smart path is not the evidence-selected automatic strategy. |
| 1 | **Initial Cleanup contract frozen** | Revised [#112](https://github.com/dmclark/sayloom/issues/112) defines spelling and contextually obvious misrecognition eligibility, mandatory abstention boundaries, and separate implementation and evaluation work. |
| 2 | **Obsolete benchmark toolchain removed** | The unoperated source-preserving Cleanup benchmark and canary entry points, dedicated tests, and operating documentation have left the current tree without changing ordinary Cleanup processing or migrating private data. Capture, storage, API, UI, and migration removal remains separate work, and any external private-data disposition requires separate verification and authorization. |
| 3 | **Fresh participant package ready** | Prospective collection writes no migrated legacy observations. Private review can derive Cleanup targets, classify both views, group related cases, and freeze global partitions. |
| 4 | **Cleanup baseline qualified** | The expanded account-independent Cleanup implementation passes its frozen evaluation. Failure leaves Conservative as the actual baseline and blocks Smart comparison. |
| 5 | **Smart evidence ready** | The initial single-participant package satisfies the frozen Smart strata, observed-use weights, and held-out minimum without weakening profile-dependent or abstention coverage. |
| 6 | **Smart finalists frozen** | [#46](https://github.com/dmclark/sayloom/issues/46) compares frontier methods and complete strategies on development and validation evidence against the frozen Cleanup baseline. |
| 7 | **Smart winner selected** | One preregistered held-out run selects a passing strategy or records that none qualifies, preserving the approved quality, preservation, usability, latency, privacy, and cost gates. |
| 8 | **Automatic Smart prototype verified** | Only the selected winner enters Smart. Automatic routing, repair review, uncertainty, stale-state, fail-open, privacy, CART, and Outgoing contracts receive an explicit pass/stop result. |
| 9 | **Limited pilot complete** | A separately authorized bounded pilot completes without becoming production hosting or supporting a broad or multi-user efficacy claim. |

## Issue placement

- [#112](https://github.com/dmclark/sayloom/issues/112) is not ready to
  implement from its current Smart-only brief. It must define Cleanup's first
  lexical expansion using account-independent evidence, compare the smallest
  viable approaches, and produce focused implementation and Cleanup-evaluation
  tickets. Its focused checks do not establish general Cleanup efficacy.
- [#109](https://github.com/dmclark/sayloom/issues/109) is adjacent,
  mode-neutral product feedback and review infrastructure. An explicit
  current-draft “This is what I meant” repair may identify a Cleanup or Smart
  miss, but remains ephemeral and creates no evaluation observation, profile
  update, or Correction memory. Its current Smart-only brief must be revised
  before implementation.
- [#46](https://github.com/dmclark/sayloom/issues/46) owns the Smart frontier
  only after Cleanup freezes. Its existing automatic-strategy harness and
  acceptance gates remain useful, but obvious baseline corrections are no
  longer inherently Smart.
- [#12](https://github.com/dmclark/sayloom/issues/12) and
  [#13](https://github.com/dmclark/sayloom/issues/13) remain separate Smart
  personalization work. They do not block anonymous Cleanup or the initial
  single-participant evaluation.

GitHub workflow labels do not override this map. Issues #109 and #112 must not
be implemented from their current `ready-for-agent` briefs.

## Superseded evaluation path

The source-preserving Cleanup benchmark and canary toolchain was removed without
migration, and no private evaluation run is documented. Its archived contracts
cannot be widened or its evidence reinterpreted for the new Cleanup and Smart
model. Git history and the documentation archive keep its provenance. Separate
capture, storage, API, UI, and migration surfaces remain outside that completed
removal. The historical fixed-arm Smart scaffold likewise remains
non-authoritative for prototype acceptance.

The correction-mode ADR and product implementation plan remain useful for
verified implementation and capability history, but their permanent
Conservative mode and separate Cleanup/Smart evidence assumptions are
superseded. They must be reconciled before they can authorize related work.

Implementation removal and GitHub issue reconciliation are separate authorized
work. This documentation does not itself authorize either action.
