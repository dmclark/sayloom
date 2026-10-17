# Frozen provider-screening reference bundle

**Historical, non-operational evidence.** These files preserve the synthetic
fixtures and exact source configuration used in the October 2026 screens. They
are not fresh approvals, current prices/privacy attestations or a live launcher.
Follow the [current procedure](../../provider-response-screening-protocol.md)
before preparing any new run.

## Contents and provenance

- `nebius-response-screen/manifest.json`: authoritative five synthetic cases,
  exact prompt/wrappers, expected outputs and thirty ordered jobs.
- `openrouter-response-screen/manifest.json`: the same cases/messages, with the
  exact prior Azure-only routing, privacy constraints and metadata header.
- `direct-openai-response-screen/manifest.json`: the same cases/messages and
  pinned direct-OpenAI snapshot request settings.
- `thirty-second-screen/runner.py.txt`: byte-preserved executed Python source,
  deliberately saved as non-executable reference text. Preparation copied the
  source manifests and changed the diagnostic deadline to thirty seconds.
- `SHA256SUMS`: hashes of these four source files for byte-level comparison.

The manifests still contain their original five-second deadlines, historical
authorization and reservation fields. They describe their source batches, not a
new run or the cumulative ledger. The runner requires Python 3.11+, `httpx`, Unix
file locking/fsync facilities, three source manifests in this directory layout,
and separate live ledger/state. It imports no application code. The repository's
Python and dependency lock files provide the project environment.

Do not execute the archived source in place. Its owner thread, expected incoming
balances, batch IDs and schedule are historical constants. No live ledger or
state is included; do not manufacture them to bypass the guards. A future approved
run needs a reviewed execution copy, its own ignored evidence/state and offline
safety checks. The original scratch test/report scripts were not retained; do not
claim this bundle supplies them.

Sources: [original Nebius/OpenRouter owner](https://ampcode.com/threads/T-01a1466e-448e-71ef-a68f-d6f64d2e5bf2),
[direct-OpenAI source](https://ampcode.com/threads/T-01a14706-fdfd-7491-9062-bb693db3f681),
and [ten-/thirty-second comparison owner](https://ampcode.com/threads/T-01a14713-03f3-7275-8fc2-376b3467ab62).
Raw responses, operating data, costs ledger, secrets and logs are intentionally
excluded. The comparison thread remains the ledger authority; a Git checkout does
not carry current spending state or permission.

## Verify without inference

From the repository root:

```bash
(cd docs/archive/provider-response-screening && sha256sum --check SHA256SUMS)
```

Expected: four `OK` lines. Reading or checking these files sends no provider calls.
Changing even whitespace in a manifest changes its hash; preserve the final
newline in the near-limit expected text when parsing and exporting fixtures.
