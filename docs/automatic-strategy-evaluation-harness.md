# Automatic strategy evaluation harness

- **Pipeline version:** `automatic-strategy-evaluation-v1`
- **Status:** frozen public-safe harness, validated with synthetic cases and an executor adapter
- **Authority:** the acceptance contract and comparison protocol linked from the automatic
  correction prototype map

This harness registers, executes, adjudicates, and reports correction-method and complete
Automatic correction strategy candidates without calling a provider itself. It does not authorize
provider traffic, spending, private-data access, stable-state inspection, migration, or deployment.
The evidence-production task supplies a separately reviewed executor adapter after the owner has
approved the frozen manifest.

## Frozen registration

`register_run(...)` accepts absolute paths outside both Git and application operating data. It
validates and exclusively writes mode-0600 copies of the configuration, cases, schedule, and
manifest beneath a new mode-0700 run directory. The manifest exposes the full candidate slate,
provider/model/settings, prompts, software version, routing policy, retry policy, timeout,
per-candidate and total call/token/cost ceilings, privacy posture, approvals, stop conditions, and
canonical SHA-256 hashes. It is therefore the artifact the owner reviews before an evidence run.

Development registration schedules three independently seeded attempts per candidate and case;
validation and held-out registration schedule one. Candidate order is deterministically randomized
inside interleaved case blocks. Held-out registration permits no more than three complete strategies
plus preregistered ablations, requires at least 200 eligible non-synthetic cases, and excludes direct
component execution. Synthetic validation is explicitly marked and can never become acceptance
evidence.

## Execution and review

`execute_run(...)` resolves each candidate's frozen executor identifier through the supplied
evaluation-adapter registry. Unknown or syntactically invalid identifiers fail open for that attempt
without aborting the run. Each adapter receives a frozen `AdapterRequest` containing only Original,
request context, explicitly enabled profile evidence, candidate configuration, deterministic seed,
and execution budget. Each attempt receives an isolated copy of mutable candidate configuration;
case identity and Intended variants remain outside the adapter boundary.

Adapters return the common `ExecutionResult` contract. The result records the selected registered
method, reviewable repair trace, internal retries, latency, calls, tokens, and cost. Empty or
otherwise unreviewable successful output, including repairs unrelated to Original and Prepared, is
normalized to a content-free `malformed_output` failure. A 30-second wall-clock timeout interrupts
the synchronous adapter and fails open. An adapter exception, unregistered route, excess retry,
reported timeout, or exceeded ceiling also
becomes a recorded per-attempt failure; execution continues, except that a ceiling stops only the
affected candidate branch. Outputs and separate blind review/map artifacts are write-once and
hash-frozen.

The evaluation-only adapter module statically registers only provider-free executors. Its constrained
general-model factory requires an injected synchronous transport and has no network-capable default.
That adapter builds canonical untrusted evidence JSON, validates the complete frozen provider/model,
prompt, settings, retry, timeout, and ceiling contract, derives uncertain repair spans locally, and
returns exact transport usage across its bounded attempts. The application runtime does not import
the harness or its adapters.

Blind review creates one item for each disputed repair and contains Original, user-confirmed
Intended variants, one candidate result, and that repair, but no case, method, or candidate identity.
The private blind map records the job and repair index. `import_adjudications(...)` requires one
`correct`, `wrong`, or `equivalent` verdict for every blind item and freezes those repair-level
verdicts before unblinding.

## Deterministic reporting

`build_report(...)` uses a frozen Unicode word-token and Levenshtein contract. Original and Prepared
are aligned independently to the closest acceptable Intended variant. It reports weighted
case-level editing reduction, correct-repair rate, already-correct-word preservation, reliability,
sub-10-second completion, retries, calls, tokens, cost, per-stratum results, and each strategy's
actually routed method subsets. Abstentions and failures remain in the denominator with zero editing
improvement, and their recorded latency determines sub-10-second completion. Routed methods need 30
routed cases, 30 proposed repairs, and adjusted confidence bounds passing every component gate for
decision-grade evidence.

Confidence bounds average repeated executions only within their case cluster, then use deterministic
whole-case, stratum-weighted bootstrap resampling with a one-sided 95% Bonferroni familywise
adjustment across opened candidate and routed-method gates. The generated
`aggregate-report.json` contains no text, case IDs, review IDs, or blind mapping. Every artifact is
outside Git and application state and cannot replace an existing artifact.
