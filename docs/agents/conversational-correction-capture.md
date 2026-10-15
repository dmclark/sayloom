# Development-time conversational correction capture

## Status and scope

Agreed design for a guidance-only, manually reviewed trial in Sayloom development
conversations. The aid is independent of Sayloom's application and databases.
Collection is not enabled by this document. Enablement and destination approval
belong to the current conversation. Downstream uses of retained examples remain
undecided.

The design was agreed in [the design interview](https://ampcode.com/threads/T-3c5ca383-35c3-4afe-8662-222783ba4873).
For intended-text recovery and user authority, consult Product Purpose and
Success in `PRODUCT.md` and the recognition-repair terms in `GLOSSARY.md`.
Correctly spelled wrong words and multiword phrases are in scope, not just
spelling fixes.

## Enable one session

Before collection, obtain explicit owner authorization for one development
session and approval of one owner-controlled file outside Git and Sayloom's
databases. A checkout-local ignored file is acceptable for an orb trial; the
suggested destination is `.amp/in/artifacts/conversational-capture/examples.md`.
Verify the exact destination is ignored and untracked before writing. Keep
private machine-specific paths out of tracked docs. Confirm the session boundary
with the owner; enablement does not carry into another thread or session
automatically. An orb file is not automatically shared with other threads or
synced to the owner's computer.

Establish the transcription source once per session. When the owner identifies
Voiceitt inaccuracies as the source of the wording errors, use that session-level
confirmation rather than asking for a cause label on every example. Exclude
known agent misunderstandings of accurate text and changes of mind. If a case's
eligibility is unclear, clarify it before offering retention.

If that file is inaccessible in the current environment, report the limitation
and stop capture. Use no fallback copies, persistent pending queues, or silent
transfers. Do not inspect private operating data, historical repair records, or
earlier conversations to discover or backfill examples. Use only exchanges in
the enabled session. No custom capture function or paid calls are needed.

## One-reply review alongside the main conversation

1. Notice possible recognition misunderstandings, including those that remain
   understandable. Unusual wording alone does not establish an error. Ask about
   ambiguity when it affects the work; otherwise offer a brief wording check at
   a natural pause rather than interrupting every unusual phrase.
2. Continue the main conversation where possible and attach a compact complete
   proposed record with **Did you mean ...?** Show the observed and proposed
   intended wording, minimal context, source link, and confirmation by the
   owner's reply. Explain that Regression defaults to Unknown; a final
   **regression** marker means the owner observed Voiceitt's second pass change
   correct first-pass wording into incorrect wording and adds At. Do not ask a
   separate regression question. Screenshots are optional and require separate
   approval to retain; never infer unseen first-pass wording from final text.
3. Accept one reply that confirms or corrects the wording and explicitly
   authorizes retention with **save**, optionally ending with **regression**.
   For example, **yes, save, regression** confirms the proposal, authorizes
   saving, and flags regression. **No, I said [intended wording], save** approves
   the owner-supplied revision with Regression: Unknown, without another preview.
   A bare Yes confirms wording only; it does not authorize saving. Guesses,
   silence, or agreement with the broader development plan confirm neither.
4. Treat a final regression marker case-insensitively, allowing trailing
   punctuation. Without that marker, use Regression: Unknown; this does not
   mean a regression did not occur. Save must be an explicit instruction for
   this record, not merely a word in dictated text. If either marker could be
   part of intended wording or its scope is unclear, clarify before writing.
5. For Regression: Yes, read the system clock when processing the reply and include **At**
   as an ISO 8601 timestamp with the owner's timezone offset. This approximates
   when the regression was reported, not when Voiceitt changed the text. Use
   the same value through saving; do not replace it with save time or invent a
   timestamp for an earlier reply. For Unknown, omit At. When a reply flags a
   regression without authorizing retention, keep the timestamp only in the
   conversation until the owner approves saving; create no pending file.
6. Only after explicit approval, append the displayed record with the owner's
   explicitly supplied edits, confirmation path, regression flag, and conditional
   timestamp. No second approval is needed for those owner-specified changes.
   Agent-added changes to wording or context require another review.
   Verify the append succeeded before reporting it saved. A failed or ambiguous
   write requires inspecting the target state before retrying, to avoid duplicates.
7. Briefly acknowledge whether the example was saved and resume the main
   conversation explicitly. Restate an unanswered development question without
   repeating the whole previous message. If the owner also answered it, continue
   the work; if no answer is needed, proceed to the next step. Do not require the
   owner to remember where the conversation paused.

### Complete proposed record

- **Observed:** Exact wording the agent received or misunderstood.
- **Intended:** Exact owner-confirmed wording.
- **Context:** Only the short surrounding passage needed to understand the pair,
  reviewed by the owner; omit unnecessary sensitive text and full transcripts.
- **Confirmation:** Owner-supplied correction or explicitly confirmed agent proposal.
- **Source:** Link to the source thread, without copying its full conversation.
- **Regression:** Yes for an explicit final regression marker; otherwise Unknown.
- **At:** Report timestamp with timezone offset, included only for Regression: Yes.

Use these labeled fields in the private file; no application schema is required
for the initial trial. Retention approval covers the displayed record, explicit
owner revisions, and the disclosed flag/timestamp behavior, not unrelated text.

## Declines, pauses, and revisions

A declined or unanswered request creates no record and no rejection log. Do not
repeat the request for the same occurrence. **Pause capture** stops capture-related
checks and offers for the rest of the session; ordinary clarification needed for
development work continues.

Keep distinct occurrences separate when context adds value. Do not silently
merge meanings or repeat an already reviewed identical occurrence in the session.
Show proposed revisions to retained records and obtain approval before changing
them. Exclude disputed wording from downstream proposals until resolved. Obtain
explicit authorization before deleting retained examples.

## Trial review and reuse boundary

At the end of an authorized one-session trial, review usefulness, interruption
burden, accuracy of wording, sufficient context, and unnecessary
private retention. Report limitations; guidance alone is not a guarantee that
every agent will notice every misunderstanding.

Determine uses after examples have been collected. Private retention does not
authorize live vocabulary or Personal Correction saving, investigation reuse,
tracked synthetic adaptations, evaluation, model training, or cross-user reuse.
Those decisions require separate authorization. This aid changes no Sayloom
product behavior and does not revive retired Evidence Collection. A regression
flag enables later filtering; it does not authorize sending records to Voiceitt.
