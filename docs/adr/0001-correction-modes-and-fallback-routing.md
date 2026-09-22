# ADR-0001: Separate correction authority from fallback routing

- **Status:** Accepted
- **Date:** 2026-09-22
- **Scope:** Correction-mode semantics, automatic preparation, provider routing,
  and pre-pilot Smart disclosure
- **Product authority:** [`PRODUCT.md`](../../PRODUCT.md)

## Context

Sayloom currently exposes cleanup enablement and correction mode as separate
durable settings. Conservative is the default. It preserves lexical wording and
may use configured fallback routes. Smart permits bounded lexical repair but is
restricted to the primary route.

Current Conservative validation has one lexical exception: it permits removing
bounded leading fillers such as “um” and “uh.” That exception conflicts with the
confirmed hard lexical boundary below and must be reconciled before the target
contract is implemented.

The Smart restriction implemented the “one deadline, no automatic paid retry”
acceptance criterion from [issue #10](https://github.com/dmclark/sayloom/issues/10).
That criterion coupled two independent concerns:

- **correction authority** — what Sayloom may change in the text; and
- **execution policy** — which configured models or providers may be attempted.

This coupling makes Smart less resilient than Conservative and obscures the
meaning of both mode names. The interface compounds the problem: disabling
automatic cleanup makes the remembered correction mode inert, while enabling
it does not explain whether Conservative or Smart will run.

The current routing behavior originated in the following implementation work:

- [bounded same-provider model fallback](https://github.com/dmclark/sayloom/commit/a92a1bd);
- [resilient sequential routing](https://github.com/dmclark/sayloom/commit/7de0efd);
  and
- [optional Gemini-to-OpenAI routing](https://github.com/dmclark/sayloom/commit/5dd652e).

## Decision

### Expose one automatic-preparation choice

The user-facing choice is:

- **Off — Keep Original**
- **Conservative — Preserve my words**
- **Smart — Repair likely wrong words**

The Workspace shows the choice for the current draft. Settings stores the
default for future drafts. A new draft starts with the saved default, but a
draft-specific change does not alter that default.

Changing the current draft choice acts immediately. Selecting Conservative or
Smart regenerates Prepared from the current Original. Selecting Off invalidates
pending preparation and leaves Original usable. A stale response must not
overwrite the newer choice.

Conservative remains the saved default until Smart passes its evidence gate.
Any later default change requires a separate product decision.

### Define modes only by correction authority

Conservative is a hard source-preserving boundary. It may change presentation,
including capitalization, punctuation, apostrophes, and whitespace, but it
must not add, remove, replace, duplicate, or reorder lexical wording. This
prohibits deleting filler tokens; presentation-only treatment of fillers may
remain source-preserving.

Smart may make least-change lexical repairs for likely input or Voiceitt
recognition errors, followed by Conservative preparation. It does not authorize
general rewriting, style improvement, tone changes, or broader polishing. The
Smart pilot may determine the correction method and abstention logic within
this boundary; it may not redefine the boundary.

### Route independently of correction mode

Conservative and Smart use the same fallback eligibility rules. Every
explicitly configured route is eligible in order. Processing stops at the first
valid success, the shared end-to-end deadline, or a request-level terminal
failure.

A successful primary route prevents unnecessary backup calls. A route-specific
failure may advance to the next configured route. Cancellation, an invalid
local request, and other failures that apply to the request as a whole remain
terminal. Routing must not perform unbounded or blind same-route retries.

Cross-provider fallback remains disabled unless it is explicitly configured
and its paid external processing and data disclosure are acknowledged. That
configuration authorizes the bounded route chain for either correction mode;
it does not authorize sending every request to every provider.

All route attempts share one fixed end-to-end latency budget. The budget is
partitioned so the primary cannot consume time reserved for eligible backups.
Adding a route must not extend the user-facing deadline.

**Deferred:** Evidence must determine the total budget and per-route slices.

### Preserve explicit mode choice on failure

If Smart exhausts its eligible routes, Sayloom fails open to Original and
offers an explicit **Try Conservative** action. It must not silently downgrade
the requested mode.

When a backup route succeeds, Prepared shows a quiet status such as “Prepared
with backup model.” Expandable details identify provider, model, and bounded
attempt outcomes without exposing operating text, prompts, credentials, or
provider payloads. No additional per-request confirmation is required after
the route chain has been explicitly configured and acknowledged.

### Disclose Smart's evidence status and pilot boundary

Before Smart passes its evidence gate, it remains intentionally selectable but
is labeled **Experimental — not yet evidence-backed**. The plain-language
promise “Repair likely wrong words” remains visible with the mode name.

An adjacent **Learn about the pilot** action opens an in-product explanation of
the pilot's purpose, likely participation burden, and privacy boundary. Until a
real enrollment and consent path exists, the explanation ends with “Enrollment
is not currently open.” It must not claim that the user can sign up.

Ordinary Smart use never constitutes enrollment or pilot evidence collection.
Selecting Smart, viewing the explanation, copying Prepared, or reviewing a
repair does not retain pilot data. Participation requires a separate approved
consent and enrollment flow and visibly armed Evidence Collection.

## Consequences

- Mode names have stable meanings independent of model, provider, cost, retry,
  or latency policy.
- The interface presents the three outcomes users can actually select instead
  of exposing an inert Off-plus-mode combination.
- Smart gains the same configured resilience as Conservative without weakening
  its correction boundary.
- Backup routes can add cost and consume more of the fixed latency budget.
  Explicit cross-provider configuration, acknowledgement, bounded routing, and
  visible recovery details remain required.
- Smart remains available for deliberate learning without being represented as
  validated or becoming the default prematurely.
- Model fallback remains automatic within the acknowledged route chain. Mode
  fallback remains explicit.

## Superseded behavior

This decision supersedes:

- the user-facing model of separate automatic-cleanup and correction-mode
  controls;
- Smart's current primary-route-only selection; and
- issue #10's “no automatic paid retry” clause where it prohibits advancing to
  an explicitly configured and acknowledged fallback route.

It retains issue #10's single end-to-end deadline, fail-open behavior, and
foreground, stateless Smart request boundary.

## Alternatives considered

### Bundle correction and execution policy by mode

Rejected because “Conservative” would partly mean “fallback-capable,” while
“Smart” would partly mean “single attempt.” Neither property describes what the
mode may do to the user's words.

### Call every configured provider on every request

Rejected because it would multiply cost, latency, and data disclosure and
would require a new policy for choosing among multiple successful results.

### Silently downgrade failed Smart requests to Conservative

Rejected because it would conceal a change to the user's explicit correction
choice. Original remains the fail-open result; Conservative is an explicit
recovery action.

### Hide Smart until the pilot passes

Rejected because deliberate pre-pilot use supports learning. The experimental
label and Conservative default communicate the evidence state without hiding
the capability.

## Deferred decisions

- Exact total latency budget and per-route allocation.
- Pilot-selected Smart method and abstention logic.
- Whether Smart becomes the default after its evidence gate passes.
- Pilot eligibility, enrollment, consent, and contact mechanism.
- Exact interface composition and implementation migration.
- Detailed classification of provider failures as route-specific or
  request-terminal.
- Alignment of `PRODUCT.md` and current leading-filler validation with the hard
  lexical boundary accepted here.

## Implementation status

This ADR defines the accepted target contract. It does not claim that the
target interface or routing behavior is implemented, authorize application
changes, open pilot enrollment, authorize evidence collection, or authorize a
provider run. Current behavior remains as described in the Context section
until separately implemented and verified.
