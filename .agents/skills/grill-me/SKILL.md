---
name: grill-me
description: >-
  Runs a bounded requirements and design interview with a decision ledger. Use
  only when the user explicitly invokes grill-me for architecture, schema,
  privacy, deployment, major UX, workflow, or ambiguous product decisions.
---

# Grill Me

Run a focused decision interview before implementation. Turn ambiguity into a
reviewable contract without making application, Git, or durable-memory changes.

## Boundaries

- Use this workflow only after explicit invocation. Do not infer that every
  design discussion needs grilling.
- Interview only. Do not implement, edit repositories, create Git state, deploy,
  or write Mandrel data while grilling.
- Do not spawn subagents or child threads automatically. Never select Ultra.
  Use the current mode and tools directly.
- Research only factual questions that materially unblock a decision. Prefer
  direct local sources and authoritative documentation; avoid broad research.
- Do not ask the user for facts that available tools can establish safely.
- Preserve privacy. Ask for constraints and data classes, not secrets,
  credentials, private records, or unnecessary personal data.
- If the user asks for implementation mid-interview, state that grilling is
  still active and ask whether to finish the contract or explicitly end the
  interview. Do not treat the implementation request as implicit permission.

## Establish the frontier

Start by restating the decision outcome and scope in one or two sentences. Build
a small decision tree containing:

1. **Settled facts** — verified constraints or explicit user requirements.
2. **Choices** — decisions the user can make, with meaningful alternatives.
3. **Dependencies** — facts or prior choices that block later choices.
4. **Frontier** — choices whose dependencies are settled and can be asked now.

Do not expose a sprawling tree. Show only a compact frontier summary and the
ledger. Research unverified factual dependencies before opening a question
round. Label unverified but necessary statements as assumptions rather than
facts.

Prioritize decisions with high reversal cost, privacy or security impact,
schema/API consequences, or the ability to eliminate downstream questions.

## Ask bounded rounds

Ask at most five currently unblocked questions in one round; prefer one to three
when they are consequential or coupled. Never ask blocked questions merely to
fill a round.

For every question use this compact shape:

```markdown
### Q<D-ID> — <decision>

Why now: <dependency or consequence in one sentence>

- A. <option and key tradeoff>
- B. <option and key tradeoff>
- C. <option and key tradeoff, when useful>

Recommended: **<option>** — <brief rationale tied to stated constraints>.
```

Allow free-form answers and combinations. Include “defer” only when deferral is
safe, and explain the default or consequence of deferring. Do not disguise a
factual lookup as a preference question.

End each round with a direct request for the user's answers, then stop. Do not
continue the interview, document the final contract, or start work until the
user responds.

## Maintain the decision ledger

Carry one compact Markdown ledger across rounds. Use stable IDs so later answers
can refer to earlier decisions. Include every category, writing `—` when empty:

```markdown
## Decision ledger

| Status | ID | Decision or fact | Rationale / consequence |
|---|---|---|---|
| Accepted | D001 | ... | ... |
| Rejected | D002-B | ... | ... |
| Deferred | D003 | ... | Revisit before ... |
| Superseded | D004 | ... | Replaced by D007 |
| Assumption | A001 | ... | Validate before ... |
| Unresolved | D005 | ... | Blocked by D001 |
```

Keep entries concise and summarize answers rather than copying the transcript.
Record factual findings as facts in the accepted row only when verified; retain
their relevant source or evidence in the rationale. Do not silently convert an
assumption into a fact.

After each response:

1. Map answers to stable IDs and update the ledger.
2. Record declined alternatives as rejected only when the user actually rejects
   them; unchosen is not always rejected.
3. Detect conflicts with prior decisions, constraints, and assumptions.
4. If an answer changes a prior choice, mark the old entry **Superseded**, link
   it to the replacement ID, and briefly explain the consequence.
5. If intent is unclear, ask one focused clarification before treating the old
   answer as superseded.
6. Recompute the frontier and ask only newly unblocked decisions.

## Finish the interview

Finish when the material frontier is resolved or safely deferred, or when the
user explicitly asks to stop. Do not manufacture low-value questions.

Present:

```markdown
## Current contract
- <confirmed behavior, boundary, interface, or constraint>

## Deferred questions
- <ID, trigger or deadline, and safe interim default>

## Risks
- <risk, impact, and mitigation or owner>

## Readiness
**Ready / Ready with conditions / Not ready** — <concise reason>.
```

Include the final compact ledger immediately before this summary. A **Ready**
recommendation means decisions are sufficient for the stated next step; it does
not authorize implementation, repository changes, Git actions, deployment, or
Mandrel writes. State any explicit authorization still needed.

## Precedence

System and developer instructions, explicit user constraints, repository
guidance, and applicable safety or privacy policies outrank this skill. If they
conflict with an answer, surface the conflict as an unresolved decision rather
than weakening the higher-priority instruction.
