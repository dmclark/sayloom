# Transcript fidelity product and research specification

- **Status:** Confirmed product direction; research design ready for pilot
  planning; implementation blocked on the reconciliation items below
- **Audience:** Sayloom product, research, architecture, and implementation
  reviewers
- **Purpose:** Define what transcript fidelity means, how Sayloom should pursue
  it, and the finite evidence required before implementation

## Authority and scope

Sayloom's primary motivating outcome is improved fidelity of text derived from
Voiceitt for a user with non-standard speech (F001). The input boundary remains
source-agnostic: fidelity behavior must not require that text arrive through a
particular Voiceitt integration.

**Operating principle: Voiceitt-first, not Voiceitt-dependent.** Research,
evaluation, and initial fidelity behavior optimize for the current user's
Voiceitt-derived transcripts. Ingestion and the core evidence concepts must
also work when the source is unknown, without requiring a Voiceitt account,
API, or integration. When source characteristics are known, explicit
source-aware behavior may be adopted if the bounded study shows measured value;
unknown sources retain a generic transcript-recovery path.

Authority is ordered as follows:

1. [`voiceitt-orchestration`](https://github.com/dmclark/voiceitt-orchestration/tree/e17acb0e)
   governs shared architecture, repository/data/privacy boundaries, and
   cross-project contracts. This specification uses its default tip observed
   at `e17acb0e` on 2026-08-20: the
   [README source of truth](https://github.com/dmclark/voiceitt-orchestration/blob/e17acb0e/README.md),
   [Sayloom fresh-start plan](https://github.com/dmclark/voiceitt-orchestration/blob/e17acb0e/docs/plans/sayloom-fresh-start.md),
   and the explicitly subordinate
   [version-one shape summary](https://github.com/dmclark/voiceitt-orchestration/blob/e17acb0e/docs/ui/sayloom-version-one-shape.md).
2. This Sayloom specification governs the product outcome and fidelity
   behavior. Cross-project conflicts are blockers, not permission to override
   orchestration (F006).
3. [`PRODUCT.md`](../PRODUCT.md) remains the broader product description.
   [`docs/shape-plan.md`](shape-plan.md) remains UX evidence, not fidelity
   authority. Its simple alias-to-canonical vocabulary and Original-to-Cleaned
   suggestion assumptions require reconciliation before fidelity
   implementation; diffs are not replacement truth (F003).

Historical or superseded architecture is not authority for this work.

## Problem statement

The product must distinguish three forms of text:

- **Voiceitt output:** the text supplied by the upstream recognizer. Voiceitt's
  public APIs expose final text and, for streaming, limited segment and timing
  data; they do not document ranked alternative transcripts (often called
  n-best alternatives) or confidence (F005).
- **Faithful transcript:** the best-supported account of what the user said,
  preserving meaning and uncertainty rather than improving prose.
- **Polished output:** an optional transformation toward the user's intended
  message, including useful grammar, punctuation, or style cleanup.

These three forms of text do not have one-to-one word correspondence. A
polished result can be useful without proving what was spoken, and an
Original-to-Cleaned diff cannot prove that one phrase is the correct replacement
for another (F002, F003). Existing intended-message cleanup should be preserved,
but evaluated separately from transcript recovery.

## Goals and non-goals

### Goals

- Improve Voiceitt-derived transcript fidelity while retaining a
  source-agnostic text boundary (F001).
- Recover a meaning-faithful transcript before offering optional polishing
  (D001).
- Improve important terms without increasing harmful changes or the amount of
  user correction required (D004, D015).
- Use explicit, local, user-reviewed personalized evidence and preserve the
  upstream original (D003, D006, D007, D010).
- Select concrete transcript-fidelity functionality for the current Sayloom
  project through one bounded study, then stop research and hand the selected
  simplest meaningful improvement to implementation (D014).
- Optimize for the current user; testing with other users, while keeping each
  user's data isolated, can follow later (D012).

### Non-goals

- Replacing Voiceitt, claiming access to undocumented Voiceitt confidence, or
  treating Sayloom-derived evidence as Voiceitt confidence.
- Inferring transcript truth from polished output or ordinary editing.
- Automatic learning from transcript history, background collection, or
  automatic persistence of correction material.
- Audio-first research, direct Voiceitt synchronization, model training, or a
  hosted multi-user design in this gate.
- Prematurely choosing a database schema, correction model, benchmark size,
  numeric target, expected cost, or API access before the study or governing
  contracts establish what the selected functionality requires.

## Product invariants and privacy

1. Transcript recovery and polishing are separate stages with separately
   identifiable outputs and separate evaluation (D001). **Deferred:** whether
   and how both outputs are shown in the UI.
2. When an upstream/source observation is captured for comparison or included
   in an accepted correction episode, it must be preserved and remain
   accessible. This does not make the editable working Original value immutable
   or decide storage or UI mechanics. Proposed corrections remain traceable to
   the captured observation; ambiguity or failure preserves the source text and
   never blocks outgoing text (D007).
3. Only explicitly accepted correction examples and user-authored terms may be
   saved as personalized evidence. Ordinary edits, model output, rejected
   suggestions, and passive history do not grant consent (D003).
4. Personalized evidence remains local and is not included in Gemini requests
   (D010). **Deferred (D011):** the long-term cloud boundary for current
   transcripts. Interim behavior preserves current Gemini cleanup while local
   personalized memory is excluded from those requests.
5. Real transcripts, references, corrections, databases, logs, recordings, and
   consent records remain outside Git. Generated diagnostics must not contain
   real source, transcript, or polished text.
6. The normal application startup path must not migrate storage.
7. Default operation is fast. A higher-accuracy mode must be explicit; Sayloom
   must not automatically combine multiple expensive or token-heavy model runs
   (D013).

**Blocked conflict (D003, D006, F006):** Orchestration currently permits saved
application configuration, not transcript history, and has not assigned
ownership of saved transcripts or training material. This specification
requires selected, explicitly accepted phrase-level correction episodes as
personalized evidence. Those episodes must not be relabeled as ordinary
configuration. Their implementation is blocked until orchestration defines
compatible rules for storage, consent, retention, deletion, and ownership.
Ordinary editing is not training consent.

## Conceptual product flow

```text
Source-agnostic text input
          │
          ▼
Captured source / Voiceitt output (preserved)
          │                         │
          │      local personalized evidence
          │                         │
          └─────────────┬───────────┘
                        ▼
           Stage 1: transcript recovery
               │ faithful │ ambiguous
               ▼          └─────────────▶ flag + preserve original
       Faithful transcript candidate
                         │
                         ▼ optional
               Stage 2: polishing
                         │
                         ▼
                  Polished output
```

Transcript-first is the current boundary. Cloud/API-assisted audio remains open
for later rather than assumed by this design (D002).

## Personalized evidence model

Use two complementary evidence types without deciding a database schema (D006):

- **Term cards** contain a user-authored important term and optional contextual
  cues or observed renderings. An observed rendering is evidence that may help
  retrieve a candidate; it is never an unconditional replacement rule.
- **Correction episodes** contain only the selected phrase-level evidence the
  user explicitly reviews and accepts: the source phrase as received, the
  user-confirmed faithful wording, and enough local context to establish the
  correction. Automatic history is deferred. Saving these examples is blocked
  by the orchestration conflict above.

The product must support reviewing, withdrawing, and deleting accepted evidence
once the approved retention rules exist. **Assumption:** useful local
personalization is feasible on available hardware. **Unverified:** how much
context a correction episode needs to remain useful without becoming transcript
history.

## Evidence-tiered correction behavior

Correction behavior follows evidence strength, not a single guessed answer
(D007):

- **Strong support:** apply the correction while retaining a visible path to
  the Voiceitt original and the evidence category that supported it.
- **Plausible but ambiguous:** do not silently replace; flag the word or phrase
  and offer a short candidate list or the original for user review.
- **Weak, conflicting, unavailable, or failed processing:** preserve the
  Voiceitt original. Recovery fails open.

Evidence strength may come from exact or rule-based matches, phonetic and
contextual fit, an authored term, or an explicitly confirmed episode. Sayloom
must label this as its own level of support, never as Voiceitt confidence.
Polishing cannot raise the confidence of a transcript claim.

## Evaluation framework

Use a controlled benchmark plus explicitly confirmed examples from the normal
workflow (D005). User-confirmed references provide the faithful target.
**Assumption:** these references can provide adequate transcript ground truth
without retained audio. Keep the benchmark and all normal-workflow examples
private and outside Git.

Evaluate every tested approach on the same examples (D004, D015):

- **Word error rate (WER) and character error rate (CER):** diagnostics for
  broad substitutions, insertions, and deletions. They are useful but treat
  words or characters uniformly and can miss the impact of a changed name or
  meaning.
- **Important-term accuracy:** accuracy on user-important names, specialist
  terms, and phrases. Report it separately so aggregate accuracy cannot hide
  the motivating failures.
- **Meaning fidelity and harmful changes:** human review of whether a method
  changed the user's meaning, altered already-correct text, invented content,
  or replaced evidence with fluent prose.
- **Correction effort:** the user actions and substantive edits needed to reach
  the confirmed reference. Lower WER is not a win if review burden rises.

No single measure is sufficient. Assess reference accuracy, important terms,
meaning, harmful changes, and correction effort together. Report tradeoffs
rather than collapsing them into one score.

### Pilot operating model

The current user's daily workflow should supply realistic baseline evidence and
explicitly confirmed pilot cases (D005, D012). Daily use must not become
automatic transcript collection: the user chooses each case and confirms its
faithful reference. Pilot examples are evaluation material, not personalized
product memory or training consent (D003). Before retaining any case, the pilot
protocol must define an orchestration-compatible private location, allowed use,
retention, and deletion; nothing enters Git.

Test candidate approaches on the approved private evaluation set before placing
them in a live workflow. Only an approach that meets the pilot's criteria in
that offline comparison may proceed to live pilot use.

Live pilot behavior must run separately from the stable product that the user
depends on. A different port is necessary but not sufficient: the pilot also
needs distinct service, storage/database, logs, window, configuration, and
delivery-command identities. It must never inspect or modify the stable
instance or its state. Entering the pilot is an explicit user choice, and pilot
failure must not block the stable workflow.

## Bounded transcript-only study

Run one ordered, layered comparison (D014). The current system remains the
end-to-end, full-workflow baseline. Use the same private evaluation set, record
all required measures, and add only one type of behavior at each layer:

1. **Current end-to-end baseline:** current Voiceitt-to-Sayloom behavior,
   including current cleanup, measured without claiming cleanup as fidelity.
2. **Fidelity-specific prompting:** constrain the existing correction path to
   faithful recovery and original preservation rather than prose cleanup.
3. **Deterministic (rule-based) matching:** test narrowly supported exact and
   normalized matching, such as ignoring case or punctuation, without asking a
   large language model (LLM) to decide.
4. **Phonetic and contextual candidate retrieval:** retrieve a small candidate
   set from local authored terms, then decide or flag based on combined fit.
5. **Local personalized evidence:** add term cards and, in a research-only
   form that is not saved until persistence is unblocked, explicitly confirmed
   examples. Do not send this evidence to Gemini.
6. **Specialized correction-model feasibility:** test only if prior layers leave
   an important, recurring type of error that a specialized model could
   plausibly address.

Each layer must earn its added complexity against all required measures. Stop a
branch early if it does not improve a recurring error that matters, increases
harmful changes or correction effort, violates privacy, or depends on evidence
the approved privacy and consent rules do not allow Sayloom to retain. Do not
broaden prompts, candidate sets, or combinations of models merely to rescue a
weak branch.

**Hard decision gate:** after the ordered comparison, select the simplest tested
approach that meaningfully improves at least one motivating fidelity outcome
without an unacceptable regression in meaning, important-term accuracy,
correction effort, privacy, or default responsiveness. Then stop research. If
no approach clears that gate, retain the baseline and record why none of the
tested approaches qualifies. Do not open an unbounded search.

**Proposed:** exact sample size, numeric thresholds, acceptable regressions,
and stopping cutoffs. Pilot planning must set them before evaluation begins;
they must not be tuned after results are seen.

## Voiceitt feedback path

Voiceitt supports speaker training through recorded phrase cards and
personalized vocabulary (F004). Sayloom should generate user-reviewed material
that helps the user submit useful corrections or create relevant Voiceitt
training entries (D008). For the current phase it generates copyable feedback
text only; it does not create or send email (D009).

Direct synchronization is desired but **Deferred (D008)** unless Voiceitt
documents and authorizes a supported API for that operation. The public
transcription responses reviewed for this specification do not establish such
an API.

## Risks and deferred decisions

- **Overcorrection:** generic LLM correction can alter correct words or fluent
  meaning when textual evidence is insufficient. Original preservation and
  harmful-change review are mandatory.
- **False certainty:** public Voiceitt outputs do not expose the alternatives or
  confidence needed to say that audio evidence verifies a correction (F005).
- **Chrome extension/API conjunction — Deferred and Unverified (D002, F005):**
  the current workflow predominantly receives text through the Voiceitt Chrome
  extension. Determine later whether the authenticated personalized API can be
  used alongside that workflow and whether its text or segment timing provides
  useful additional fidelity evidence. Public documentation and SDK examples do
  not establish n-best alternatives or confidence. API access, audio handling,
  cost, and privacy must be resolved before this enters a study; it remains
  outside the initial transcript-only comparison.
- **Personalized evidence leakage:** sending broad personalized context into a
  correction process can expose private material and create irrelevant
  substitutions. Local candidate selection must remain narrow (D010).
- **Metric distortion:** aggregate WER/CER can improve while important terms or
  meaning worsen (D015).
- **Past examples may not apply:** a previously observed rendering may not
  justify the same correction in a new context.
- **Research sprawl:** the ordered comparison and hard gate are binding; weak
  branches stop rather than expanding.

**Deferred:** audio architecture, supported API access, cost, hardware, and
audio privacy; automatic learning history; direct Voiceitt synchronization;
the D011 long-term cloud boundary; exact benchmark size and thresholds until
pilot planning; isolated per-user generalization beyond the current user.

## Reconciliation prerequisites

Before implementation planning:

1. Update orchestration with a reviewed contract for accepted correction
   episodes: ownership, explicit consent, allowed purpose, local persistence,
   retention, deletion, export, and separation from model-training consent.
2. Reconcile `docs/shape-plan.md` so alias-to-canonical vocabulary and
   Original-to-Cleaned suggestions are advisory evidence, not replacement
   truth; preserve the useful UX evidence that does not conflict.
3. Define product language and states for Voiceitt output, faithful transcript,
   ambiguity, Sayloom evidence tier, polished output, and fail-open behavior.
4. Approve a pilot protocol with a fixed private evaluation set, paired review
   procedure that compares every approach with the same references,
   **Proposed** sample size and thresholds, and stopping rules set before the
   study begins.
5. Confirm that personalized evidence cannot enter Gemini requests and that
   current interim cleanup remains behaviorally separate (D010, D011).

## Readiness and exit criteria

This specification is ready for a later implementation handoff only when:

- all reconciliation prerequisites are resolved or explicitly excluded by the
  governing authority;
- the finite pilot has run in order with all four evaluation measures;
- weak branches have been stopped and the hard decision gate has produced one
  selected simplest improvement or a written finding that no tested approach
  qualified;
- the selected behavior defines original preservation, ambiguity, failure,
  review, withdrawal, and deletion outcomes;
- privacy review confirms local-only personalized evidence and no implicit
  training consent; and
- the handoff names the approved product behavior and evidence, without
  inventing schema, model, cost, or API decisions.

Completion of the bounded study is a decision point, not permission for more
open-ended research.

## Decision index

| ID | Confirmed decision or finding |
| --- | --- |
| F001–F003 | Fidelity is primary; cleanup remains useful but distinct; source, transcript, and polish are not word-aligned. |
| F004–F005 | Voiceitt documents personalized training/vocabulary and limited transcript responses, not n-best alternatives or confidence. |
| F006 | Orchestration governs shared contracts; Sayloom governs product outcomes; conflicts are explicit blockers. |
| D001–D002 | Recover faithful transcript before optional polish; transcript-first now, audio later. |
| D003–D007 | Explicitly accepted evidence only; evaluation across several measures; controlled references; term cards plus accepted correction episodes; corrections based on evidence strength. |
| D008–D011 | User-reviewed Voiceitt feedback, copyable text only, local personalized evidence, and a deferred long-term cloud boundary. |
| D012–D015 | Current-user optimization, a fast default and explicit higher-accuracy mode, a bounded layered study, and extra weight for meaning, important terms, and correction effort. |

## Evidence and references

- Voiceitt API: [HTTP API authentication and personalized speech-to-text](https://voiceitt-si-api.readme.io/reference/getting-started-with-the-voiceitt-rest-api-copy),
  [audio-file transcription response](https://voiceitt-si-api.readme.io/reference/publicapicontroller_transcribe-1),
  and [streaming response fields](https://voiceitt-si-api.readme.io/reference/stream_audio_samples).
  The documented REST result is text; streaming adds stable/unstable text plus
  segment identifiers and timing for final segments. No cited response format
  documents n-best alternatives or confidence.
- Voiceitt [Python SDK at reviewed commit `9f561971`](https://gitlab.com/voiceitt-sdk/voiceitt-sdk-py/-/tree/9f561971cf7e87ee5d8bfe5f19f90ce9eb2c467c):
  examples cover authentication, HTTP audio-file transcription, and WebSocket
  partial and final recognition. This confirms that adding the API to the
  extension workflow can be investigated, but it does not document richer
  transcript alternatives or confidence.
- Voiceitt [FAQ](https://www.voiceitt.com/faq): phrase-card recording,
  personalized vocabulary, and text correction feedback guidance.
- Fang et al., [“Fewer Hallucinations, More Verification”](https://arxiv.org/abs/2505.24347):
  direct generic-LLM ASR correction can modify correct text, supporting
  explicit verification and original preservation. Its benchmark results do
  not establish performance for this user or Voiceitt.
- Trinh et al., [“Improving Speech Recognition of Named Entities in Classroom Speech with LLM Revision and Phonetic-Semantic Context”](https://arxiv.org/abs/2506.10779):
  on its classroom dataset, small phonetic-plus-contextual candidate selection
  outperformed full-context prompting while preserving non-entity accuracy.
  This motivates a bounded local comparison; it does not prove that the result
  will apply to non-standard speech or Sayloom.
