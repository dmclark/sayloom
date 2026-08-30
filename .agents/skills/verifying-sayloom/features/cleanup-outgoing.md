# Cleanup, outgoing selection, and safe errors

Sayloom cleans synthetic Original text when available, otherwise fails open to Original, and
publishes the explicitly selected current value for downstream commands.

Current cleanup is source-preserving copy-editing. It may normalize capitalization, punctuation,
apostrophes, and whitespace or remove leading filler words. Provider output that otherwise adds,
substitutes, removes, or reorders words is rejected locally and fails open to Original; configured
prompt versions cannot widen this boundary.

## Sub-features

- `CLEANUP.AUTO`: enabled edits schedule cleanup and expose waiting/running/final status.
- `CLEANUP.MANUAL`: **Run cleanup** and Ctrl/Command+Enter trigger the same current-text flow.
- `CLEANUP.FALLBACK`: disabled, timeout, stale, provider-error, and unavailable states publish
  Original rather than stale Cleaned text.
- `CLEANUP.SELECT`: Cleaned is selected only when current; explicit Original selection survives
  reruns until Clear or reload.
- `CLEANUP.PUBLISH`: visible outgoing state matches a read-only `/api/outgoing-state` response.
- `CLEANUP.ERRORS`: cleanup and publication errors open persistent, accessible, copyable,
  privacy-safe details.
- `CLEANUP.ROUTING`: the configured provider/model order and external-processing behavior are
  visible, expandable, and credential-free; invalid cross-provider configuration activates no
  provider and preserves Original fail-open.
- `CLEANUP.SEMANTIC_OUTPUT`: accepted provider output preserves the source lexical sequence except
  for leading fillers; rejected output never becomes Cleaned or Outgoing text.

## How to get to it (user POV)

- Type or paste into **Original source text** with **Clean automatically** enabled.
- Activate **Run cleanup** or press Ctrl/Command+Enter.
- Choose **Original** or **Cleaned** in the **Outgoing text source** group.
- When enabled by a failure, open the cleanup/publication status button and use **Copy details**.
- Expand **Cleanup route** below Outgoing to inspect provider order, conditional fallback, paid
  external processing, and the no-evaluation-corpus statement.

## Driving and proof

Preconditions: healthy isolated browser lane. Use the unconfigured isolated lane and mock-provider
Portable tests for deterministic fail-open, timeout, provider-error, and routing proof. Use the
Provider lane only for explicitly approved real-request compatibility within the declared call
budget.

- For every entry point, capture the initiating action and status transitions, then prove editor
  values, pressed outgoing button, outgoing label, publication live status, and a GET of
  `/api/outgoing-state` with matching synthetic text and kind.
- Replace a fully selected Original value while cleanup is pending. Prove stale Cleaned output is
  not published. Add incremental text separately and prove the prior Cleaned value may remain
  visible while Outgoing immediately uses current Original.
- Choose Original after a current success and rerun cleanup. Prove the override survives. Clear or
  reload and prove it resets.
- For errors, prove dialog role/name, focus movement and return, safe ledger fields, copied safe
  text, and absence of operating text, provider payload, credentials, stack traces, database
  contents, and private paths.
- For routing disclosure, separately prove unavailable, legacy Gemini-only, invalid or
  unacknowledged cross-provider, and acknowledged Gemini → OpenAI states. Confirm route order,
  disclosure text, keyboard expansion, and absence of credential values in API and DOM output.
- For semantic output, use independent-validator and mocked-provider tests to prove ordinary
  case/punctuation/apostrophe normalization and leading-filler removal succeed, while
  instruction-following, novel words, substitutions, removals, and reordering deterministically
  reject and publish Original.
- Record an ARIA snapshot, decisive DOM/API facts, console output, and an inspected screenshot for
  each state claimed.

## Gotchas

- A mock-provider API test is Portable proof, not Provider-lane or browser proof.
- Without explicit approval and a dedicated credential, real Gemini/OpenAI cleanup is
  `unavailable`; deterministic mocked and disabled/fail-open paths may still pass in their lanes.
- Debounced cleanup and publication are separate. Wait for both final states before recording.
- Do not induce publication failure by stopping or changing any service not created by this run.
