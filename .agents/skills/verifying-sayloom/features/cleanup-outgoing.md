# Cleanup, outgoing selection, and safe errors

Sayloom cleans synthetic Original text when available, otherwise fails open to Original, and
publishes the explicitly selected current value for downstream commands.

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

## How to get to it (user POV)

- Type or paste into **Original source text** with **Clean automatically** enabled.
- Activate **Run cleanup** or press Ctrl/Command+Enter.
- Choose **Original** or **Cleaned** in the **Outgoing text source** group.
- When enabled by a failure, open the cleanup/publication status button and use **Copy details**.

## Driving and proof

Preconditions: healthy isolated browser lane. Use the unconfigured isolated lane for deterministic
fail-open proof and the Provider lane for successful-clean, timeout, and provider-error proof.

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
- Record an ARIA snapshot, decisive DOM/API facts, console output, and an inspected screenshot for
  each state claimed.

## Gotchas

- A mock-provider API test is Portable proof, not Provider-lane or browser proof.
- Without a dedicated credential, successful Gemini cleanup is `unavailable`; the deterministic
  disabled/fail-open browser flow may still pass.
- Debounced cleanup and publication are separate. Wait for both final states before recording.
- Do not induce publication failure by stopping or changing any service not created by this run.
