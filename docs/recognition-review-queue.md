# Conversational recognition-repair review queue

This standalone development aid supports issue 182. It is not part of Sayloom,
Personal Corrections, live conversational capture, or an evaluation pipeline.
It proposes exchanges for human review; it never confirms intended wording.
Product Purpose and Success in [PRODUCT.md](../PRODUCT.md) govern the goal:
recover intended words and phrases, including correctly spelled wrong words,
not merely spelling or punctuation cleanup.

## Access and authorization

The installed Amp CLI supports `amp threads export <thread>` and describes it
as exporting the full thread payload as JSON. The implementation uses those
exports, not agent tools, private APIs, or an inference service. Schema inspection
of this implementation thread found `id`, `messages`, `createdAt`, numeric
`messageId`, `protocolMessageID`, and typed content blocks. Other export schemas
are not assumed compatible. Missing identities or ordering metadata fail closed.

Before historical extraction, obtain approval for:

- The exact thread allowlist and New York calendar-date window.
- The exact private export directory and queue path.
- Full-thread export access: Amp's export command is not date-bounded. It
  downloads the entire transcript even though this tool selects text by date.
  Do not run it under an authorization limited to fetching only in-window text.
  An owner-supplied approved export is an alternative.

The owner approved the defaults below and full exports of those five threads in
[the implementation thread](https://ampcode.com/threads/T-01a14ad3-c0d8-73c5-b92f-92258aa5e6eb).
That approval does not cover other threads, windows, or destinations. The live
capture file's permission does not authorize this queue. Do not inspect existing
private repair records to populate it. Keep exports, queue, and reviews outside
Git and Sayloom databases. Orb files do not sync to other machines.

## Usage

With the approved exports already present, run from the repository root:

```sh
uv run python scripts/recognition_review.py
```

From `scripts/`, `python3 recognition_review.py` works too. No arguments are
required. Defaults are fixed, not a rolling “yesterday” window:

| Option | Default |
| --- | --- |
| `--exports` | `<checkout>/.amp/in/artifacts/recognition-review/exports/` |
| `--output` | `<checkout>/.amp/in/artifacts/recognition-review/queue.jsonl` |
| `--start` | `2026-10-16` (inclusive, New York) |
| `--end` | `2026-10-17` (exclusive, New York) |
| `--thread` | The five IDs below |

Default paths are anchored to the script's checkout, regardless of the working
directory; neither is `~/.amp` or `/.amp`. Explicit relative paths resolve against
the working directory. `--help` displays defaults. The approved whitelist is:

- `T-2f893922-15a9-4f75-a7f0-83d8e400f5ff` — Research roadmap reconciliation.
- `T-01a13bea-ddb2-752f-a80d-f0cb7961635a` — Reusable synthetic text preparation fixtures.
- `T-01a14713-03f3-7275-8fc2-376b3467ab62` — Compare three provider configurations.
- `T-fa662f0d-a7da-4aa3-9193-cd1f60899d2e` — Architecture review report.
- `T-01a14139-62fa-708c-bd1b-54fdb2a7531d` — Run approved OpenRouter comparison.

These were selected by total message count among threads updated in the preceding
24 hours. A recent thread update does not establish recent messages, and this
selection is not automatically recomputed on later runs. A zero-candidate result
does not establish that recognition errors did not occur.

Each option can be overridden after obtaining applicable approval. Substitute
approved paths and IDs below; placeholders are not destination approval. Use
restrictive permissions before exporting, since exports can contain tools,
environment context, and more private material than the selected conversation text.

```sh
umask 077
mkdir -p <approved-export-directory>
amp threads export <approved-thread-id> > <approved-export-directory>/<approved-thread-id>.json

uv run python scripts/recognition_review.py \
  --exports <approved-export-directory> \
  --thread <approved-thread-id> \
  --start 2026-10-16 --end 2026-10-17 \
  --output <approved-private-queue.jsonl>
```

Repeat `--thread` for every allowed thread; supplying it replaces the default
whitelist rather than adding to it. There is no directory scan: only
`<thread-id>.json` for allowlisted threads is opened. The payload thread ID must
match its allowlisted filename. No export or network request is performed by the
assembler. Missing exports produce an error, not an automatic download. Its only
subprocesses are local Git checks ensuring
checkout-local queue destinations are ignored and untracked. Queue creation uses
mode 0600, and existing queues with group/other access are rejected. Parent
directories must also remain owner-controlled. The tool does not change existing
directory permissions.

## Dates and candidate chains

`--start` is inclusive and `--end` exclusive, at midnight in America/New_York.
Membership uses message `createdAt`, not thread update time or ingestion time.
Offsets are converted to UTC; each local midnight has its applicable DST offset.
For example, March 8, 2026 is a 23-hour local day; November 1 is a 25-hour day.
Naive timestamps and reversed or empty windows are rejected.

Only user/assistant text blocks enter the queue. Tool results, thinking,
attachments, and out-of-window text are excluded. Metadata outside the window
is used to identify gaps; JSON parsing still loads the full approved export.

Candidate detection is intentionally limited to explicit cues such as “did you
mean,” “I meant,” “I said,” “misheard,” or “transcription error.” A cue links up to
six preceding contiguous in-scope text messages, starting with a user message.
Before detection, an ordinary new user request resets that context; explicit
rejections such as “No, that's wrong” preserve it. This bounded preceding context
is held only in memory until a cue is found, not persisted as a hidden queue.

After detection, further assistant interpretations and user replies remain in
the candidate until a user reply contains neither a cue nor an explicit rejection.
That final reply is included but never treated as confirmed wording. This retains
unsuccessful proposals and later clarification without interpreting agreement.
The heuristic can miss implicit repairs or long late-detected chains, and can
queue ordinary discussion of recognition errors. An unusual phrase alone does
not create a candidate. Full relevant messages are retained, not just regex hits;
human review should further minimize context before any separately approved reuse.

A new window can extend an existing candidate using already retained evidence,
but only across consecutive textual message identities. Missing or unauthorized
intervening context breaks the chain. An observed message from a previous day
that was never retained cannot be recovered by silently widening the window;
explicitly authorize a wider window and supply the approved export instead.

## Incremental state and human review

The JSONL queue is also processing state; there is no separate checkpoint or
database. Every `evidence` record carries a stable candidate ID (thread ID plus
anchor protocol message ID), source thread link, exact message ID, timestamp,
ordering metadata, role, text, and relation. Records are appended, never updated.
The relation distinguishes observed text, agent interpretations, and possible
clarifications. All machine-added evidence is `unconfirmed`.

Repeated and overlapping runs deduplicate by thread and protocol message ID.
Changed content under a retained identity aborts rather than replacing it.
Newly authorized later replies append to the original candidate. Concurrent
writers use an exclusive file lock. A truncated final JSONL line blocks retries;
inspect and explicitly repair it before rerunning. A filesystem write failure
can leave a partial final line; no successful run is claimed in that case.

Human review may append a separate JSON object with `type: "review"`, its
`candidate_id`, classification, exact reviewed wording, confirmation source
message IDs, reviewer identity, and retention authorization. The assembler treats
review records as opaque: it never overwrites or silently upgrades them when new
evidence arrives. Reviewers must distinguish owner-confirmed recognition repairs,
unconfirmed interpretations, agent misunderstandings, and changes of mind.
Ordinary “yes” replies do not automatically establish wording or retention consent.

Voiceitt authorship does not establish that an unusual phrase is erroneous.
Final text cannot establish first-pass content or which pass introduced an error.
Retention does not authorize Personal Correction saving, model training,
evaluation reuse, or sending private text to any inference service.

The CLI streams status lines immediately, including when stdout is piped:

- The inclusive/exclusive New York date window.
- `Reading [i/N] <thread>.json` and the selected in-window text-message count.
- Queue-lock status and the number of existing queue records loaded.
- `Processing [i/N] <thread>.json`, matched candidate exchanges, and new evidence
  records pending save. A candidate can contain several evidence records.
- The save step, `Appended N unconfirmed evidence records; existing records
  unchanged.`, and the resolved queue path.

Per-file counts are provisional until the final append succeeds. On a repeat,
candidate counts may remain nonzero while new evidence records and the final
append count are zero; this means the matching evidence was already retained.
Progress contains metadata and counts, not private message text. Review the
private queue locally; do not paste it into issue comments, test fixtures, or
tracked documentation.

## Synthetic verification

`uv run pytest tests/test_recognition_review.py` exercises the CLI with network
access and non-Git child processes prohibited. Fixtures cover contextual phrase
recovery (including unsuccessful interpretations), preservation of accurate
unusual wording, date boundaries and DST, later replies, overlapping reruns,
review preservation, stable provenance, and rejection of unsupported metadata.
An additional streaming check pauses an export read and verifies that progress
is visible before supplying its input, without forcing unbuffered Python mode.
These are synthetic contract checks, not owner-confirmed examples or evidence of
real-world recovery accuracy. No private corpus enters the fixtures.
