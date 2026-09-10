# Sayloom context

Sayloom prepares imperfect text while preserving the user's authority over intended meaning. This
glossary names the product artifacts, correction boundaries, evidence tracks, and delivery
milestones.

## Language

**Original**:
The editable source text supplied to Sayloom.
_Avoid_: Raw text, input copy

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
