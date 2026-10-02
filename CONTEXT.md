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

**Cleanup**:
The account-independent, proven correction baseline. A Cleanup version freezes determinate
eligibility and abstention rules for presentation fixes, spelling, and contextually obvious,
effectively unambiguous misrecognitions.
_Avoid_: Presentation-only cleanup, Smart frontier, generic rewriting

**Conservative preparation**:
The current incomplete Cleanup implementation stage. It may change capitalization, punctuation,
apostrophes, and whitespace but preserves every lexical word.
_Avoid_: Permanent correction mode, complete Cleanup contract

**Smart correction**:
The versioned moving frontier for less-determinate, contextual, or user-dependent repair, followed
by Cleanup. Its meaning-bearing changes remain reviewable.
_Avoid_: Cleanup, rewrite, transcript recovery

**Prepared**:
Sayloom's generated result after the selected Smart and Cleanup path.
_Avoid_: Cleaned text, output

**Correction method**:
A bounded way for Smart to propose or abstain from frontier repairs. An Automatic correction
strategy selects among multiple correction methods; Cleanup follows frontier repair and is not a
competing correction method.
_Avoid_: Automatic correction strategy, Cleanup

**Automatic correction strategy**:
The complete Smart arrangement that automatically selects among frontier correction methods before
Cleanup produces Prepared.
_Avoid_: Single correction method, manual method selection

**Repair**:
A reviewable lexical addition, removal, or replacement. A repair may be proposed by Smart or
explicitly supplied by the user after either Cleanup or Smart misses intended wording.
_Avoid_: Accepted correction, evaluation evidence

**Private correction profile**:
Explicitly enabled, user-owned knowledge that may inform Smart correction. It does not affect core
Cleanup.
_Avoid_: Cleanup dependency, memory, training data

**Correction memory**:
Optional retained knowledge derived through a separately approved learning interaction. It is
outside the Smart MVP and does not affect core Cleanup.
_Avoid_: Private correction profile, implicit learning

**Cleanup evaluation**:
Qualification and regression evidence for one frozen, account-independent Cleanup version.
_Avoid_: Smart discovery, historical source-preserving benchmark

**Smart evaluation**:
Discovery and acceptance evidence for one frozen Smart frontier version. It measures both the
frontier's incremental value over Cleanup and the complete Smart-to-Cleanup result against Intended
text.
_Avoid_: Cleanup qualification, unversioned experimentation

**Participant package**:
Legacy, user-controlled external research storage retained temporarily for administration and
validation only. The Workspace and normal runtime neither write nor read it. Its presence does not
authorize collection; issue #143 owns its removal.
_Avoid_: Current product state, active collection, application state

**Evaluation view**:
A task-specific frozen projection of approved evidence. Cleanup and Smart views may reference the
same observation with different eligibility, targets, and metrics while sharing one global related-
case partition assignment.
_Avoid_: Duplicate collection, interchangeable benchmark

**Current product**:
The product stage that turns Original into Prepared through Conservative preparation, the current
incomplete Cleanup implementation.

**Smart MVP candidate**:
The product stage with a frozen Cleanup baseline, Smart frontier correction, reviewable repairs, and
an explicitly enabled Private correction profile, before the approved private Smart evaluation
passes.

**Evidence-backed Smart MVP**:
A Smart MVP candidate that has passed the separately approved private Cleanup and Smart evaluations.

**Locally proven Smart product**:
The later product stage that has passed the local self-pilot, including any optional Correction
memory scope approved for that stage.

**Partner-demo ready**:
A Locally proven Smart product that has completed the partner-demo readiness stage.
