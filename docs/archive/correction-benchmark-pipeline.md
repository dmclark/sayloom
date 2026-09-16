# Correction benchmark pipeline

> **Historical fixed-arm scaffold.** This file documents the implemented eight-arm
> Smart benchmark scaffold, but it is not the current prototype acceptance path.
> Use the [documentation map](../README.md) and the current
> [evaluation and automatic-correction prototype map](../evaluation-mvp-map.md).

- **Pipeline version:** `correction-benchmark-pipeline-v1`
- **Status:** Historical implementation reference; product binding and private run were not completed
- **Scope:** private text-only Smart-correction experiment
- **Conditions:** prompt × task context × curated knowledge, each off/on
- **Milestone map:** [`evaluation-mvp-map.md`](../evaluation-mvp-map.md)

This bounded harness freezes and validates the benchmark pipeline before any
private corpus or paid provider run. It does not call a provider and is not
loaded by normal application startup.

The scaffold is Smart-only and is independent from the cleanup benchmark/canary machinery. Issue
[#14](https://github.com/dmclark/sayloom/issues/14) must bind it to the real Smart Prepared contract
and explicitly enabled Private correction profile after issues
[#10](https://github.com/dmclark/sayloom/issues/10) and
[#12](https://github.com/dmclark/sayloom/issues/12). Synthetic tests establish scaffold behavior;
they do not establish product acceptance, authorize a private run, or provide Smart quality
evidence. Issue [#15](https://github.com/dmclark/sayloom/issues/15) separately requires approval, a
private run, and a pass.

## Private data boundary

Configuration, cases, run directories, imported outputs, blind-review packets,
scores, and reports must use absolute paths outside both the Git repository and
the configured application-state directory. The CLI rejects either overlap.
No private benchmark artifact belongs in Git, logs, Mandrel, or an orb.

The registration configuration freezes:

- run and corpus versions;
- exact provider, model, and settings;
- minimal and full frozen-contract prompt text;
- the arm-order seed;
- the scoring rubric and acceptance gates; and
- the number of practice-only contract revisions, limited to two.

Each case declares `practice` or `unseen`, freezes its eligibility, and freezes
its source, authoritative user-confirmed intended wording, authorized request
context, and curated knowledge. Registration copies those private inputs into a
new mode-0700 run directory, writes mode-0600 artifacts, and records canonical
SHA-256 hashes.

The Workspace can add an explicitly corrected pair to a configured candidate
cases file before registration. Set `LOCAL_TEXT_CORRECTION_BENCHMARK_CASES_PATH`
to that absolute external path. **Correct and add example** writes nothing until
the user submits the dialog, then appends one schema-valid `practice` case with
`eligible: false`, empty authorized context, and no curated knowledge. Private
curation must assign all benchmark metadata and eligibility before registration.

## Workflow

Run each command with absolute, private local paths:

```bash
uv run python -m local_text.correction_benchmark register \
  --configuration /private/input/configuration.json \
  --cases /private/input/cases.json \
  --runs-directory /private/runs

uv run python -m local_text.correction_benchmark import-outputs \
  --run-directory /private/runs/RUN_ID \
  --outputs /private/import/outputs.json

uv run python -m local_text.correction_benchmark import-scores \
  --run-directory /private/runs/RUN_ID \
  --scores /private/import/scores.json

uv run python -m local_text.correction_benchmark report \
  --run-directory /private/runs/RUN_ID
```

Registration derives a deterministic per-eligible-case order containing the
eight established conditions `P0E0K0` through `P1E1K1`. The output import must
follow that exact order and contain exactly one record for every eligible
case-condition pair. `attempt` and `provider_calls` are both fixed to 1, so
retries, omissions, duplicates, and replacement imports are rejected.

A successful import creates `blind-review.json`, which contains opaque review
IDs, source text, authoritative intended text, and candidate text but no case
or condition identity. `blind-map.json` remains separate. The score import must
cover every blinded successful output exactly once. Every pipeline phase is
write-once and verifies prior artifact hashes before proceeding.

`aggregate-report.json` contains condition and overall counts only: fidelity
judgments, wins/losses/ties, lexical repair spans, automatic latency, failures,
provider calls, tokens, and provider cost. It contains no source, intended, or
generated text and no case or review IDs. Practice and unseen aggregates remain
separate, and only the unseen aggregate drives the gate. One unseen
meaning-fidelity failure always fails the gate, even when every other threshold
passes.

The production harness is case-count driven. Automated coverage uses exactly
10 neutral synthetic cases, producing 80 condition executions, solely to prove
the complete pipeline contract.
