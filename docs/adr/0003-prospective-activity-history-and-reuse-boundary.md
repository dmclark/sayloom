# ADR-0003: Prospective activity history without implicit reuse

- **Status:** Owner-confirmed direction; document delivery and implementation pending
- **Decision date:** 2026-11-02
- **Product authority:** [`PRODUCT.md`](../../PRODUCT.md)
- **Delivery sequence:** [Product implementation plan](../product-implementation-plan.md)
- **Reconciliation review:** [Owner-approved draft session](https://ampcode.com/threads/T-01a1a24e-86d4-7791-bfef-dc7020127607), using the owner-confirmed disposition plan

The owner selected ongoing single-user suggestions with automatic private
activity history, rather than an expiring randomized trial or history that
exists only after a separate save. Retaining what happened supports later
review and recovery, but possession of that history is not permission to
personalize later requests or treat model proposals as spoken-word evidence.

## Decision

Start prospectively. Retain Sayloom input passages, generated results,
suggestions, applied/reversed corrections, final wording and relevant
settings/timing as distinguishable records until explicit deletion. Preserve
uncertain/revised labels rather than using those labels to delete content.
Keep model proposals, user actions and speech-verification claims distinct.

Store history privately outside Git, with no automatic cloud sync. Exclude
credentials and unrelated machine/application data. Provide visible
pause/private-passage controls that exclude a passage from retained history;
these controls do not promise offline processing or provider-side erasure.

Include private managed backup and tested restore. Explicit deletion must
cover managed backup copies and cannot be undone by a later restore. User-made
exports and provider-side retention are outside that guarantee. The exact
locations, recording-failure behavior, pause semantics and restore-safe deletion
mechanism remain implementation-contract decisions before activation; do not
claim complete deletion or reliable recording before they are implemented and
verified.

Do not import, merge or reclassify existing trial and conversational-review
records automatically. Preserve their provenance and separate access. Keep the
conversational review tool standalone initially; unified UI redesign is not a
prerequisite for reviewing new application history.

History authorizes no automatic contextual reuse, Personal Correction saving,
model training or evaluation. Existing Personal Corrections still require
separate reviewed saving and preserve ADR-0002's authorization boundaries.
Development-conversation capture remains a separate opt-in aid.

## Consequences and rejected alternatives

- Reject trial expiry and removal of uncertain/revised records for the new
  ongoing history; labels describe evidence, not automatic deletion requests.
- Reject silent history reuse. More retained text is not a larger inference
  permission; any later reuse needs its own decision and authorization.
- Reject automatic historical import. A later import needs provenance,
  preview/deduplication and applicable private-data permission.
- Accept the added privacy and recovery obligations of retained history.
  Managed backup/restore and deletion must be designed together rather than
  allowing an old backup to resurrect deleted content.
- Do not silently extend this policy to SQLite backups containing Personal
  Corrections. Their existing unresolved backup-deletion policy remains a
  distinct decision, including when a future storage design would mix surfaces.

This records product policy, not permission to inspect private records,
activate capture, spend money, run migrations or change runtime. It establishes
no fidelity result, provider qualification or owner usefulness acceptance.
