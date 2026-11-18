# Unresolved findings contract

- **Status:** Owner-approved planned behavior; findings supply and chosen-alternative application are not implemented by this document.
- **Scope:** Bounded normal-path findings supply and explicit application under [#197](https://github.com/dmclark/sayloom/issues/197), dependent on [#196](https://github.com/dmclark/sayloom/issues/196).
- **Confirmed:** 2026-11-16 — D001–D010 and P001, P002, P004; amended 2026-11-18 to supersede D010's mandatory efficacy component and P003's completion dependency. Neither is marked passed; optional evaluation details remain deferred.
- **Product authority:** [PRODUCT.md](../PRODUCT.md); [domain vocabulary](../GLOSSARY.md).
- **Decision source:** [Owner-approved contract, revision 4](https://ampcode.com/artifacts/197-findings-contract-and-proposed-amendments-a698b85a-5eac-4ca7-b5e6-5cc6987e8e8b). This document records its confirmed technical requirements, not its interview or delivery history.
- **Retention clarification:** [Owner-confirmed interim delivery boundary](https://ampcode.com/threads/T-01a1e5ce-f1b1-7556-bf85-87f9de86c90c); prospective history remains separate required work, not a #197 implementation prerequisite.
- **Lifecycle clarification:** Subsequent owner-confirmed [occurrence-sensitive lifecycle and failure-only Retry rules](https://ampcode.com/threads/T-01a1e6ea-8273-74f4-be18-726fc2e8de03), [immediate radio application and new-passage reset](https://ampcode.com/threads/T-01a1e5ec-28b1-700b-9d61-b4e78911cab0), and [E1/E2 approval](https://ampcode.com/threads/T-01a1e1e1-670f-7423-baad-0be190432820) establish the interaction requirements below. They do not establish implementation completion or release readiness.

## Purpose and implementation boundary

Provide bounded hypotheses about suspected recognition errors left unresolved
in accepted Prepared text, then let the owner keep, manually edit, or explicitly
apply a chosen alternative to Original. Findings are not general writing/style
review, confirmed intent, or already-applied repairs (D001, D007).

Applied-repair descriptions and retrospective Personal Corrections candidates
are not substitutes for normal-route unresolved findings. The requirements below
describe the approved target. Local implementation or controlled demonstrations
do not by themselves establish deployed behavior, acceptance completion, live
detection quality or release readiness.

This contract grants no implementation, activation, private-data access, provider
calls, spending, or Git delivery authority (D002). #197 owns actionable acceptance;
this document owns the bounded technical contract. It neither completes broader
[#192](https://github.com/dmclark/sayloom/issues/192) reconciliation nor makes
withdrawn #198 a prerequisite. Deployed Stable parity remains unverified and is
not an added prerequisite.

**Local inspection implementation, November 18, 2026:** The unpushed
`feat/196-safe-inspection` branch contains bounded normal-route findings and
chosen-alternative application, occurrence-sensitive lifecycle, failure-only
Retry and memory-only Original Undo/Redo. Its reported 227 offline checks do not
establish native-browser acceptance, usefulness, cost or release readiness.
Browser acceptance is deferred. This is not a statement that these capabilities
are merged or activated. Broader saved-correction and prospective-history
obligations remain outstanding.

**Correction authority and visibility:** Findings concern suspected recognition
errors, not general awkwardness or style. Offer meaningfully distinct,
passage-supported alternatives when useful, or a specific finding without
replacement; never fill a quota. Automatic Prepared changes retain PRODUCT.md's
stricter eligibility/abstention and consequential-change requirements. Existing
Conservative semantics remain unchanged. Normal review must make every lexical
addition, removal and replacement discoverable directly from Prepared, including
previous wording for removals and replacements. A historical before/after
description remains available even if location is unavailable; never guess a
highlight. CART remains clean. This records a requirement, not a claim of rendered
compliance.

## One preparation request, unchanged mode authority

Prepared and findings must come from the existing preparation request in Smart
and Conservative; Off makes no generation request (D003–D005). Conservative
continues to preserve lexical words, and Smart retains its existing least-change
lexical-repair semantics. Findings do not expand automatic rewriting permission.

Preserve automatic preparation, debounce, settings, confirmation protections,
open Prepared-correction protection, and stale/late-response rejection. Viewing
or focusing findings, selecting an Inspection entry, and Keep cause no preparation
or provider request. Explicitly choosing an alternative radio applies that
alternative immediately; this text edit follows exactly the normal manual-edit
preparation schedule and policy. Add no separate findings request, trigger,
request stream or findings-only retry (D004, D006).

Remove routine Regenerate. Show Retry only for a failed preparation in Original’s
right-aligned footer; ordinary edits, successful preparation and findings-only
incompleteness do not create a Retry opportunity. Retry and the existing
⌘Enter/Ctrl+Enter shortcut invoke the same guarded recovery action, with identical
availability and visible explanations. Do not cancel an open manual correction
or clear its confirmation to retry. Preserve the correction and visibly explain
any block.

Retry prepares current Original in the currently selected enabled mode through
the existing normal request path, without a silent Smart-to-Conservative or other
cross-mode fallback. Off or empty Original cannot generate. Retry does not alter
automatic preparation scheduling or provider-level retry policy and adds no
automatic extra request.

Preserve provider selection, routing, timeouts, and retry policy. Introduce no
independent detector service, engine/provider choice, or retrieval mechanism.
Selective adaptation of #187 prompt/validation ideas is permitted, but not its
trial lifecycle, storage, fixed provider, or separate requests (D008). Its
one-to-three-alternative and UTF-16 contracts must not replace this contract's
zero-to-three alternatives and code-point spans.

Sayloom receives final Voiceitt text only. Findings must not claim access to
first-pass text or identify which recognition pass introduced an error. A
Voiceitt API switch is outside scope.

## Logical response and exact binding

The normal response must carry accepted Prepared text, unresolved findings,
and server-derived findings processing status. Typed findings must survive
provider output, parsing, service/result transport, and normal browser ingestion.
Exact wire field spellings and the provider/server schema split remain
implementation details; the semantics here do not.

Each finding has independently validated Original and Prepared spans, a short
reason, and zero to three distinct alternatives (D009). Every alternative is a
replacement for that finding's exact Original occurrence, even when its
displayed Prepared wording differs. Zero alternatives is valid: retain manual
editing and Keep, with no apply action. Never preselect an alternative or apply
one without the owner’s explicit choice. Choosing its radio is the application
action, not a separate preview step.

Span offsets count Unicode code points. Validate each span against its own text,
not by copying Original offsets to Prepared. Browser conversion to UTF-16
textarea selection must preserve the exact occurrence, including non-BMP text.
Bind results to the request's exact Original text/revision and accepted Prepared
text/generation; recheck current bindings at application.

Edits and other binding changes invalidate stale markings and alternatives.
Finding visibility follows the lifecycle below; retaining an entry does not
restore an actionable binding. Restoring identical wording does not revive an
old binding. Never search matching words elsewhere to rebind a stale finding.
Same-occurrence reconciliation requires reliable occurrence identity and never
licenses applying an old alternative at a newly guessed location. Disable stale
alternatives rather than guessing.

## Validation and partial failure

Keep independently valid Prepared when findings alone fail validation. Preserve
individually valid findings and omit invalid entries (D006, P004). Derive status
on the server rather than accepting a model's claim of successful validation:

| Findings result | Status and retained result |
| --- | --- |
| Valid array, including an empty array, with no rejected entries or overflow | `complete`; retain valid findings, including successful zero findings. |
| Array with any rejected entry or overflow | `partial`; retain at most the first five valid findings in returned priority order. If all entries are invalid, retain zero usable findings with partial status. |
| Missing or non-array findings | `unavailable`; retain independently valid Prepared. |

Status describes processing completeness, not confidence, exhaustive detection,
or absence of recognition errors. Visibly distinguish partial/unavailable
findings from successful zero findings within #196's approved layout.

Reject an entry for invalid or empty spans, mismatched source text,
missing/invalid reason, duplicate or invalid alternatives, more than three
alternatives, or exceeded string/span limits. Reject oversized entries
individually; do not truncate wording, deduplicate into a different meaning, or
invent replacements. Overflow must not silently appear complete.

These rules do not make invalid Prepared acceptable or promise recovery from
truncated/unparseable output. Preserve existing preparation failure protections.
A combined transport/generation failure can make both results unavailable;
separate failure isolation is not guaranteed. Do not retry solely for findings.

## Accepted limits and generation budget

| Item | Limit (D009, P002) |
| --- | --- |
| Findings per response | At most 5; zero is valid. This is a review ceiling, not exhaustive detection. |
| Distinct alternatives per finding | 0–3 |
| Each reason | 160 Unicode code points |
| Each alternative | 200 Unicode code points |
| Each Original and Prepared finding span | 200 Unicode code points, independently checked |
| Original and Prepared passages | Preserve existing 100,000-code-point limits and Prepared semantic validation. |
| Added output allowance | Up to 4,096 tokens per existing provider attempt, before clipping to existing provider ceilings; retain applicable reasoning headroom. |

Do not raise provider ceilings: Gemini 65,536 tokens, OpenAI 128,000, OpenRouter
32,768. Retain existing Gemini reasoning headroom of 2,048 tokens, actual
configured deadlines, and route partitions; do not reset a deadline to a source
default. No runtime configuration is selected by these source-level constraints.

The increment is an initial generation ceiling, not a guaranteed reserve, proven
fit, actual usage, monetary cap, or evidence of affordability. Long inputs can
still be clipped by provider ceilings; variable tokenization/JSON escaping,
truncation, and timeouts can still lose usable preparation. Prior synthetic
serialization sizing was not a token measurement, recognition benchmark, or
provider quality/cost result. The allowance authorizes no spending.

## Inspection and chosen-alternative application

Preserve #196's Prepared-focused unresolved markings, non-colour cues, compact
matching-colour Inspection entries to the right of Prepared, selection,
per-finding Keep, alternatives beneath entries, and CART suppression (D001).
Do not add a separate Fix Passage or full-passage editor.

An explicit radio choice immediately replaces only that alternative’s exactly
bound Original occurrence, removes that unresolved finding/marking, and retains
the chosen repair. There is no separate Apply button or preselected option.
Other findings follow the occurrence-sensitive lifecycle below, and repairs
retain their separate location checks. Application does not wholesale clear
Inspection.

The new repair remains listed through the resulting automatic Prepared update
and later updates, inspectable in Original only while its location is reliable.
Invalidating edits or updates require **Location unavailable**, not uncertain
highlighting. Preparation-produced repairs remain inspectable in Prepared.
Removal-only repairs retain the
Original-location exception: highlight removed wording only when still present
at a valid Original location. Otherwise select the entry and show **Location
unavailable**, without uncertain highlighting or text changes. Retention never
implies location validity.

Hide an unresolved finding immediately when its exact Original occurrence is
edited or removed. Keep unaffected old findings disabled Awaiting recheck while
automatic preparation is pending. A current accepted complete findings result
replaces old unresolved findings, including clearing them on successful zero
findings. Complete describes processing, not exhaustive detection or confirmed
intent.

With partial findings, preserve independently valid Prepared. Retain omitted
unaffected old findings disabled Not rechecked, show newly valid findings as
current and actionable, and replace an older entry for the same exact Original
occurrence rather than duplicate it. With unavailable findings, preserve
independently valid Prepared and unaffected old entries disabled Not rechecked;
add no new findings. Clearly indicate the incomplete check, including partial
results with zero usable findings.

With whole-request failure, retain unaffected old findings disabled Not rechecked,
add none from the failure, and show the preparation error with the guarded footer
Retry. Findings whose occurrences were edited or removed still disappear
immediately. Omission from incomplete or failed results does not establish
resolution. These rules do not change invalid-Prepared failure handling or
stale-response rejection.

Applied repairs remain separate from unresolved hypotheses and retain the
existing location protections. Keep dismisses a current finding without changing
text or requesting preparation, including a finding with no alternatives.
Awaiting recheck and Not rechecked findings cannot offer outdated replacements
or uncertain highlights.

Replacing or deleting fully selected Original as a new passage clears Inspection
entries, selection and processing state; selection alone does not. Ordinary
partial edits do not reset all entries.

The new-passage reset also applies when the replacement wording is identical.
This does not make old bindings valid again.

**Original edit history:** Preserve the later owner-approved, memory-only
Original Undo/Redo boundary. Text equality alone cannot revive an obsolete
finding or make an uncertain occurrence actionable. When an input event lacks
reliable edit-range identity, conservative whole-text replacement handling
retires uncertain unresolved findings rather than guessing survivors; retain
applied repairs with location safeguards and preserve the selected mode. This is
not persistent activity history, history reuse or automatic Personal Correction
saving.

Preserve desktop keyboard selection/application/dismissal, manual editing,
plain-text copying, Outgoing/delivery, and CART's no-inline-marking behavior
when Original is hidden. Applying, editing, selecting, and Keep do not themselves
save Personal Corrections or grant future reuse permission. Existing separately
authorized saving remains independent. #197 does not implement or activate
history; the prospective private history required by
[PRODUCT.md](../PRODUCT.md#ongoing-suggestions-and-automatic-private-activity-history)
and [ADR-0003](adr/0003-prospective-activity-history-and-reuse-boundary.md)
is separate work that may later record those actions under its own contract.
No automatic private-record import is included. Omitting rejected findings from
the live response does not require retaining rejected model wording in history;
the [history scope](product-implementation-plan.md#history-purposes-and-content-boundary)
excludes that wording by default.

## Completion gates and deferred evaluation

Keep #197 as one end-to-end acceptance issue (P001). Focused implementation
deliverables may separate supply/validation and application/integration, with
actual code and evidence transferred between workspaces. Any later formal efficacy
evaluation is optional and separately authorized, not a required implementation
phase. Documentation approval starts no operation and creates no issue.

History does not block #197 implementation. Ordinary use may precede history
after #197's existing acceptance gates pass, with an explicit warning that those
sessions are not retained and cannot be recovered later. Prospective private
history remains required follow-up work; the interim route neither activates
recording nor permits later reconstruction of unretained sessions. Implementation
and activation still require separate authorization. This sequencing exception
preserves engineering and operational requirements. The November 18 product
decision supersedes the mandatory efficacy component of D010 and P003's
completion dependency; it does not approve evaluation, data reuse or spending.

Controlled evidence must exercise the normal preparation HTTP path through
validation and browser consumption, plus the complete entry selection, explicit
radio choice with immediate application, repair inspection and automatic
update/edit interaction (D003, D010). Fixture-only DOM-event injection is partial
evidence, not completion. Required coverage includes:

- Smart, Conservative, Off, successful zero findings, and zero/one/multiple
  alternatives.
- Partial/unavailable findings with valid Prepared preserved; invalid Prepared
  retaining existing failure behavior; malformed, oversized, boundary-length,
  and overflow findings, including returned priority order.
- Capped per-attempt allowances and unchanged deadlines, routing, and retries.
- A non-first alternative at only one repeated Original occurrence, differing
  Original/Prepared offsets, and code-point/UTF-16 conversion.
- Stale Original revisions, Prepared generations, late responses, and identical
  wording restored without reviving bindings.
- Choosing a non-first radio alternative applies immediately to only its bound
  occurrence, without preselection or an Apply button; focusing/viewing alone
  does not apply. The applied repair remains inspectable subject to
  reliable-location checks.
- An edit to a flagged occurrence hides it immediately, while editing/deleting
  an unflagged repeated occurrence preserves the untouched flagged occurrence
  disabled pending recheck. Cover Unicode and edits before a retained occurrence
  without guessing a new binding.
- Unaffected findings show Awaiting recheck while pending. Complete, including
  successful zero, replaces older unresolved findings. Partial retains omitted
  old entries as Not rechecked and replaces the same occurrence with newly valid
  findings; unavailable and whole-request failure retain unaffected old entries
  as Not rechecked. Incomplete results with zero usable findings do not imply
  resolution. Applied repairs remain separate throughout.
- New-passage replacement/deletion, including identical-wording replacement,
  resets entries, selection and processing state; selecting all alone and
  ordinary partial edits do not.
- Debounce, Off, open Prepared correction and current confirmation remain
  protected. Viewing/focusing/Keep make no requests; radio application uses only
  the normal edit path. Failure-only Retry is right-aligned in Original’s footer;
  button and shortcut share guards, visible explanations and manual-correction
  protections. Findings-only incompleteness does not offer a separate retry.
  Cover recovery of current Original using the currently selected enabled mode
  without silent Smart-to-Conservative or other cross-mode fallback, and
  inability to generate with Off or empty Original.
- Keyboard use, CART suppression, copying/Outgoing, no implicit saving or reuse,
  and owner review of the resulting interaction.

Controlled checks do not establish real detection usefulness, latency,
affordability or release readiness. Under the owner's November 18 ordinary-use
policy, systematic efficacy evaluation and effectiveness sign-off are not
prerequisites for ordinary-use adoption or #197 completion. This supersedes
D010's mandatory efficacy component; it does not mark it passed or remove
required correctness, safety, privacy, integration, desktop interaction, owner
review or operational checks.

Native-browser acceptance is currently deferred and unpassed. Reported offline
checks are not native-browser verification. #197 remains open while its retained
acceptance requirements are outstanding. Private-data access, provider use,
spending, integration and activation require their applicable separate
authorization. Neither token ceilings nor offline call-count/deadline checks
establish actual cost or live provider behavior. Do not recreate the declined
efficacy study as an operational-check prerequisite.

**Deferred optional evaluation (P003):** If formal evaluation is later requested,
approve its purpose, cases and reuse consent, coverage, criteria and spending
separately. Ordinary use, discussion examples, private repairs and Personal
Corrections grant no evaluation or training permission. No corpus, numerical
pass threshold, provider run or spending is approved here. Preserve the separate
saving/history boundaries and interim non-retention warning. No gate is claimed
passed by this amendment.
