# Sayloom context

Sayloom prepares imperfect text while preserving the user's authority over intended meaning. This
glossary names the product artifacts, correction boundaries, evidence tracks, and delivery
milestones.

## Language

**Original**:
The editable source text supplied to Sayloom.
_Avoid_: Raw text, input copy

**Intended text**:
Wording that the user who produced Original confirms or rewrites to express what they meant. It is
the authority for correction evaluation: one canonical wording may have additional user-confirmed
acceptable variants, and neither a model nor an evaluator may substitute its judgment.
_Avoid_: Ground-truth transcript, inferred intent

**Conservative preparation**:
Source-preserving preparation that may change presentation but not lexical wording.
_Avoid_: Smart correction, rewrite

**Prepared**:
Sayloom's generated result after the selected correction and preparation path.
_Avoid_: Cleaned text, output

**Smart correction**:
Least-change repair of likely intended words, followed by Conservative preparation. Its
meaning-bearing changes remain reviewable.
_Avoid_: Cleanup, rewrite, transcript recovery

**Correction method**:
A bounded way to propose or abstain from lexical repairs. An Automatic correction strategy selects
among multiple correction methods; Conservative preparation follows lexical repair and is not a
correction method.
_Avoid_: Automatic correction strategy, Conservative preparation

**Automatic correction strategy**:
The complete Smart correction arrangement that automatically selects among multiple correction
methods to produce Prepared.
_Avoid_: Single correction method, manual method selection

**Repair**:
A reviewable lexical addition, removal, or replacement proposed by Smart correction.
_Avoid_: Cleanup edit, accepted correction

**Private correction profile**:
Explicitly enabled, user-owned knowledge that may inform Smart correction.
_Avoid_: Memory, training data

**Correction memory**:
Optional retained knowledge derived through a separately approved learning interaction. It is
outside the Smart MVP.
_Avoid_: Private correction profile, implicit learning

**Cleanup evaluation**:
The evidence track for Current product source-preserving preparation. It does not establish Smart
correction quality.
_Avoid_: Smart benchmark, correction evidence

**Smart evaluation**:
The independent evidence track for Smart correction against user-confirmed intended wording.
_Avoid_: Cleanup benchmark

**Evidence Collection**:
An optional, visibly armed research interaction that prospectively records actual
Voiceitt-generated Original and producer-confirmed Intended text before any candidate Prepared text
is exposed. It is independent of Conservative and Smart correction and is not a correction mode.
_Avoid_: Evidence mode, automatic learning, correction mode

**Evidence observation**:
One prospectively frozen Original with its contemporaneous correction evidence and the producer's
pre-exposure Intended-text judgment or content-free exclusion disposition. Observations remain
distinct even when an exact-repeat relationship is suggested.
_Avoid_: Training example, transcript, grouped case

**Evidence package**:
The approved, user-controlled external collection that retains immutable private observations and
content-free audit records for later Smart evaluation preparation.
_Avoid_: Application state, practice corpus, Cleanup evaluation corpus

**Current product**:
The product stage that turns Original into Prepared through Conservative preparation.

**Smart MVP candidate**:
The product stage with Smart correction, reviewable repairs, and an explicitly enabled Private
correction profile, before the approved private Smart evaluation passes.

**Evidence-backed Smart MVP**:
A Smart MVP candidate that has passed the separately approved private Smart evaluation.

**Locally proven Smart product**:
The later product stage that has passed the local self-pilot, including any optional Correction
memory scope approved for that stage.

**Partner-demo ready**:
A Locally proven Smart product that has completed the partner-demo readiness stage.
