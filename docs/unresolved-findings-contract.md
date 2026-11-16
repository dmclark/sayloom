# Unresolved findings contract

- **Status:** Owner-approved planned behavior; findings supply and chosen-alternative application are not implemented by this document.
- **Scope:** Bounded normal-path findings supply and explicit application under [#197](https://github.com/dmclark/sayloom/issues/197), dependent on [#196](https://github.com/dmclark/sayloom/issues/196).
- **Confirmed:** 2026-11-16 — D001–D010 and P001, P002, P004; P003 evaluation details remain deferred.
- **Product authority:** [PRODUCT.md](../PRODUCT.md); [domain vocabulary](../GLOSSARY.md).
- **Decision source:** [Owner-approved contract, revision 4](https://ampcode.com/artifacts/197-findings-contract-and-proposed-amendments-a698b85a-5eac-4ca7-b5e6-5cc6987e8e8b). This document records its confirmed technical requirements, not its interview or delivery history.
- **Retention clarification:** [Owner-confirmed interim delivery boundary](https://ampcode.com/threads/T-01a1e5ce-f1b1-7556-bf85-87f9de86c90c); prospective history remains separate required work, not a #197 implementation prerequisite.

## Purpose and implementation boundary

Provide bounded hypotheses about suspected recognition errors left unresolved
in accepted Prepared text, then let the owner keep, manually edit, or explicitly
apply a chosen alternative to Original. Findings are not general writing/style
review, confirmed intent, or already-applied repairs (D001, D007).

Normal preparation currently has no unresolved-findings producer. Applied-repair
descriptions and retrospective Personal Corrections candidates are not substitutes.
The existing inspection work supplies presentation and safe location handling;
it does not establish normal-route supply or chosen-alternative application.
The requirements below describe the approved target, not verified runtime behavior.

This contract grants no implementation, activation, private-data access, provider
calls, spending, or Git delivery authority (D002). #197 owns actionable acceptance;
this document owns the bounded technical contract. It neither completes broader
[#192](https://github.com/dmclark/sayloom/issues/192) reconciliation nor makes
withdrawn #198 a prerequisite. Deployed Stable parity remains unverified and is
not an added prerequisite.

## One preparation request, unchanged mode authority

Prepared and findings must come from the existing preparation request in Smart
and Conservative; Off makes no generation request (D003–D005). Conservative
continues to preserve lexical words, and Smart retains its existing least-change
lexical-repair semantics. Findings do not expand automatic rewriting permission.

Preserve the preparation trigger, debounce, settings, confirmation protections,
open Prepared-correction protection, and stale/late-response rejection. Viewing,
selecting options, and Keep cause no preparation or provider request. Applying
to Original follows exactly the normal manual-edit preparation schedule and
policy. Add no separate findings request, trigger, request stream, or findings-only
retry (D004, D006).

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
editing and Keep, with no apply action. Never select or apply an alternative
automatically.

Span offsets count Unicode code points. Validate each span against its own text,
not by copying Original offsets to Prepared. Browser conversion to UTF-16
textarea selection must preserve the exact occurrence, including non-BMP text.
Bind results to the request's exact Original text/revision and accepted Prepared
text/generation; recheck current bindings at application.

Edits, regeneration, or other binding changes invalidate markings and
alternatives while retaining inspection entries. Restoring identical wording
does not revive an old binding. Never search matching words elsewhere to rebind
a stale finding. Disable every stale alternative rather than guessing a location.

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

An explicit apply action replaces only the chosen alternative's exactly bound
Original occurrence, removes only that unresolved finding/marking, and retains
the chosen repair. Other findings, options, repairs, and valid markings remain
subject to their own binding checks; do not clear retained entries wholesale.

The new repair remains listed through the resulting automatic Prepared update
and later updates, inspectable in Original only while its location is reliable.
Invalidating edits or updates require **Location unavailable**, not uncertain
highlighting. Preparation-produced repairs remain inspectable in Prepared.
Removal-only repairs retain the
Original-location exception: highlight removed wording only when still present
at a valid Original location. Otherwise select the entry and show **Location
unavailable**, without uncertain highlighting or text changes. Retention never
implies location validity.

Findings remain listed until dismissed or successfully applied. After an
invalidating manual edit, show **Text changed** and disable outdated options
when the original wording is gone. Keep dismisses without changing text,
including findings with no alternatives.

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
deliverables may separate supply/validation, application/integration, and later
evaluation, with handoffs preserving actual code and evidence. Documentation
approval does not start those phases or create additional issues.

History does not block #197 implementation. Ordinary use may precede history
after #197's existing acceptance gates pass, with an explicit warning that those
sessions are not retained and cannot be recovered later. Prospective private
history remains required follow-up work; the interim route neither activates
recording nor permits later reconstruction of unretained sessions. Implementation
and activation still require separate authorization. This sequencing exception
does not waive D010 or approve deferred P003 evaluation or spending.

Controlled evidence must exercise the normal preparation HTTP path through
validation and browser consumption, plus the complete select → choose → apply
→ inspect → automatic update/edit interaction (D003, D010). Fixture-only DOM-event
injection is partial evidence, not completion. Required coverage includes:

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
- Only the applied finding removed; the chosen Original repair and other entries
  retained; reliable and unavailable locations through updates/manual edits.
- Debounce, preparation off, open Prepared correction, current confirmation,
  and no requests from viewing/selecting/Keep or extra requests from application.
- Keyboard use, CART suppression, copying/Outgoing, no implicit saving or reuse,
  and owner review of the resulting interaction.

Controlled checks do not establish real detection usefulness, latency, cost,
or release readiness. Before closing #197 or claiming release readiness, complete
a separately authorized real-provider evaluation of intended-text recovery
usefulness, latency, and cost against owner-approved criteria (D010).

**Deferred (P003):** evaluation cases and consent for their reuse, provider
coverage, usefulness/false-positive/preservation criteria, numerical latency
thresholds, and per-request/ongoing cost and spending ceilings require owner
approval before evaluation. Discussion evidence and private repair records are
not automatically evaluation cases. No corpus, numerical pass thresholds,
provider run, or spending is approved here. Follow PRODUCT.md before selecting
cases; do not substitute spelling-only success for intended-text recovery.

This is a bounded #197 completion gate, not a product-wide effectiveness
programme, ordinary-use measurement duty, or revival of retired evaluation
harnesses. The broader [ordinary-use direction](product-implementation-plan.md#197-specific-completion-gate)
and separately authorized saving/history work remain unchanged. Keep #197 open
if evaluation is not authorized or does not pass, even after controlled checks
are complete. No completion gate is claimed passed by this documentation.
