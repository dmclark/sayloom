# Intended-meaning evidence collection

- **Collection version:** `intended-meaning-collection-v1`
- **Scope:** prospective evidence for one primary Voiceitt user
- **Status:** provider-free local capture; partitioning and sufficiency audit remain deferred

This command records actual Voiceitt-generated English and producer-confirmed Intended variants
before any candidate Prepared output is shown. It never reads candidate output, calls a provider,
or uses application operating data. Original, Intended variants, context, and profile values are
entered without terminal echo and written only beneath a new approved external package.

Do not use the preserved practice store, an existing package directory, a repository path, or an
application-state path. The package path must be a new child of the external location approved for
issue #57. Initialize it once:

```sh
uv run python -m local_text.intended_meaning_collection init \
  --package-directory /absolute/approved/external/path/prospective-collection-v1
```

Then run capture immediately after each eligible Voiceitt observation, before viewing candidate
output:

```sh
uv run python -m local_text.intended_meaning_collection capture \
  --package-directory /absolute/approved/external/path/prospective-collection-v1
```

Capture requires an interactive terminal and refuses redirected input. Private text fields use
hidden input. Public prompts collect the observation time, eligibility, the required situation,
difficulty, error, context, and profile strata, high-stakes status, and provenance confirmations.
If the producer cannot confidently reconstruct Intended text, record the offered exclusion reason
instead of inventing an Intended variant.

Each successful capture returns a random neutral `group_id`. Reuse that 32-character token for
repeated phrases, related versions, and near-duplicates, and select every applicable group
relationship. Private wording cannot be used as an ID.

The package and case directories are mode `0700`. The manifest, each case, and their SHA-256 files
are mode `0600` and created exclusively. A case ID cannot be replaced after any write attempt. The
command verifies the frozen package manifest and permissions before every capture and prints no
Original, Intended, context, or profile text.

Collection does not assign development, validation, or held-out partitions and does not claim
sufficient evidence. A later issue #60 increment must freeze whole groups into 60/20/20 partitions,
derive observed-use weights, and produce a content-free audit proving every one of the 23 required
strata and at least 200 eligible held-out cases. If those conditions are not met, the result remains
insufficient evidence.
