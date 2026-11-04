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

- The New York calendar-date window and scanning the export directory, or an
  explicit thread restriction via `--thread`.
- The exact private export directory and queue path.
- Full-thread export access: Amp's export command is not date-bounded. It
  downloads the entire transcript even though this tool selects text by date.
  Do not run it under an authorization limited to fetching only in-window text.
  An owner-supplied approved export is an alternative.

The original five-thread selection was a starting sample, not a permanent
allowlist. The owner clarified that selection should be determined by the date
range and approved automatic full-thread downloads, with exports and the queue
shared in the main worktree. Full exports may include text outside the selected
dates; only in-window user/assistant text enters candidate processing. The live
capture file's permission does not authorize this queue. Do not inspect existing
private repair records to populate it. Keep exports, queue, and reviews outside
Git and Sayloom databases. Orb files do not sync to other machines.

## Usage

With the Amp CLI installed and signed in, run from the repository root:

```sh
uv run python scripts/recognition_review.py
```

From `scripts/`, `python3 recognition_review.py` works too. No arguments are
required. Defaults are fixed, not a rolling “yesterday” window:

| Option | Default |
| --- | --- |
| `--exports` | `<primary-worktree>/.amp/in/artifacts/recognition-review/exports/` |
| `--output` | `<primary-worktree>/.amp/in/artifacts/recognition-review/queue.jsonl` |
| `--start` | `2026-10-16` (inclusive, New York) |
| `--end` | `2026-10-17` (exclusive, New York) |
| `--thread` | No restriction; select local exports by message dates |
| `--local-only` | Off; discover threads and download missing or newer exports |

Both default paths are shared across worktrees in Git's primary worktree (the
main checkout), regardless of the script's worktree or working directory. This
is a dedicated export cache, not Amp's own local thread storage. No private data
is moved from earlier destinations automatically. Explicit relative paths resolve
against the working directory.
`--help` displays defaults. For example, to select October 12 through October 16:

```sh
uv run python scripts/recognition_review.py --start 2026-10-12 --end 2026-10-17
```

The command searches your own Amp threads using a conservative update-time lower
bound, expanding the result limit until the returned set is smaller than the
requested limit. There is no update-time upper bound: a thread updated after
`--end` can still contain messages inside the requested window. Candidates whose
reported update precedes the window are excluded. Missing exports are downloaded;
cached exports are refreshed when their `updatedAt` is older than the remote
metadata (or absent). Unchanged exports are reused. Search/export failures abort
rather than silently falling back to incomplete local coverage.

Exact message selection uses `createdAt`, not file modification times or thread
update times. A zero-candidate result does not establish that recognition errors
did not occur. Remote discovery depends on Amp's search index.

Each option can be overridden after obtaining applicable approval. Substitute
approved paths and IDs below; placeholders are not destination approval. Use
restrictive permissions before exporting, since exports can contain tools,
environment context, and more private material than the selected conversation text.

```sh
umask 077
mkdir -p <approved-export-directory>
amp threads export <approved-thread-id> > <approved-export-directory>/<approved-thread-id>.json

uv run python scripts/recognition_review.py \
  --local-only \
  --exports <approved-export-directory> \
  --thread <approved-thread-id> \
  --start 2026-10-16 --end 2026-10-17 \
  --output <approved-private-queue.jsonl>
```

After acquisition, the assembler scans immediate files named `<thread-id>.json`
in the export directory, ignoring unrelated names and subdirectories. Repeat
`--thread` to bypass broad discovery and restrict downloads and reads to named
threads; online runs refresh those explicit exports on every run to include later
replies. Add `--local-only` to disable all Amp calls and read only existing files.
In that mode, missing directories or explicitly named exports produce an error;
an empty directory succeeds with no matches. Local-only coverage is limited to
the available exports and their freshness.

The payload thread ID must match its filename. Exports with missing message
`createdAt` timestamps are skipped in full, with a warning naming each file and
an incomplete-coverage count. No dates are inferred and no partial evidence from
those exports is appended; existing queue records remain unchanged. Other
malformed matching exports still fail the batch before any queue append. Export
downloads use mode-0600 temporary files and atomic replacement, preserving the
prior cache file on command failure, invalid JSON, or mismatched identity. Git
checks reject tracked or nonignored checkout destinations for both exports and
the queue, including destinations in another worktree. Queue creation uses mode
0600, and existing queues with group/other access are rejected. Parent directories
must remain owner-controlled; the tool does not change existing directory
permissions.

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

- Remote discovery, candidate count, export-cache path, and download/reuse status.
- The inclusive/exclusive New York date window.
- `Reading [i/N] <thread>.json` and the selected in-window text-message count.
- The number of threads selected by message dates out of all examined exports.
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
access prohibited; child processes are limited to Git and a fixture-local fake
Amp executable. Fixtures cover discovery beyond the initial result limit,
missing/stale export downloads, cache reuse, failed-download preservation, shared
primary-worktree paths, whole-export timestamp skips with warnings, and contextual phrase
recovery (including unsuccessful interpretations), preservation of accurate
unusual wording, date boundaries and DST, later replies, overlapping reruns,
review preservation, stable provenance, and rejection of unsupported metadata.
An additional streaming check pauses an export read and verifies that progress
is visible before supplying its input, without forcing unbuffered Python mode.
These are synthetic contract checks, not owner-confirmed examples or evidence of
real-world recovery accuracy. No private corpus enters the fixtures.
