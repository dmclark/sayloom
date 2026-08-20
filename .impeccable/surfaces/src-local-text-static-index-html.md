---
version: 1
slug: "src-local-text-static-index-html"
primary_target: "src/local_text/static/index.html"
related_targets: ["src/local_text/static/app.css","src/local_text/static/app.js"]
---

# Sayloom workspace surface brief

## Scope and mode

- **Primary target:** `src/local_text/static/index.html`
- **Related targets:** `src/local_text/static/app.css`,
  `src/local_text/static/app.js`
- **Mode:** Operate
- **Build path:** comp-first
- **Scope:** Establish the visual world for the Workspace and the adjacent
  Cleanup and Targets setup areas. This work documents direction only; it does
  not implement UI.

## Audience and job

The surface serves a person with a non-standard voice who repeatedly turns
imperfect dictation into trustworthy outgoing text while another application
is waiting. The page must make the source, transformation context, current
result, outgoing choice, publication readiness, and any safe recovery detail
scannable without breaking concentration.

## Direction

Preserve and extend the incumbent code-defined identity: warm parchment,
bright paper sheets, a cool Cleaned surface, Night utility chrome, restrained
Thread Blue, fine rules, shallow ambient depth, line-art thread mark, serif
working text, and sans-serif operational controls. New surfaces must look like
rooms in the same tool, not a second product.

The selected concept is
`.impeccable/mocks/sayloom-workspace-concept.png`. It is the compositional north
star for the persistent Workspace / Cleanup / Targets rail, stacked
Original/Cleaned workspace, compact transformation context, and explicit
Cleaned/Original outgoing selector. Its refreshed failure-state composition
also sets the pattern for persistent inline summaries, safe detail disclosure,
and independently continuing raw fail-open.

## Composition and memorable moment

Workspace keeps Original above Cleaned with the existing resizable divider and
Hide input behavior. Prompt and active vocabulary appear together in the
Cleaned heading. The outgoing strip is the memorable operational moment: a
two-option source selector is followed immediately by a written current/fallback
reason, cleanup state, and publication state.

API failures stay with the region that owns them. The concept shows a cleanup
failure expanded inside Cleaned and a separate publication failure collapsed
inside Outgoing. **View details** opens a compact ruled ledger of operation,
local time, HTTP status, stable code, sanitized message, and recovery action;
**Copy details** copies only those visible safe fields. Multiple simultaneous
failures remain separately labeled and do not overwrite one another. Error
inspection never blocks Original or obscures that Outgoing is using raw
fail-open text.

Cleanup uses internal Prompts and Vocabulary tabs with list/detail structure.
The shell can accommodate prompt history without implying that expanded prompt
authoring is in the current implementation scope. Targets uses a master list
plus selected-target detail and separates authored definition, command preview,
and observed installation or permission state.

## Constraints

- No recording-review destination or speculative disabled navigation.
- No target chooser or send button in Workspace; external hotkeys express the
  destination.
- No third editable “final” text field.
- Never show real dictated text, credentials, paths, or private operating data
  in comps or documentation.
- Keep Original and Cleaned vertical at every width. Below the rail breakpoint,
  navigation becomes horizontal; master-detail setup becomes list-to-detail.
- State is never color-only. Keyboard focus, text selection, collapse, and
  separator behavior remain visible and operable.
- Error summaries persist at their owning workflow until success, relevant
  state change, explicit dismissal, or replacement for the same operation.
- Details and copied details never include credentials, headers, Original or
  Cleaned text, provider payloads, stack traces, database contents, or private
  paths.
- Cleanup/provider, publication, configuration, vocabulary, and target errors
  retain separate identities; no transient toast or generic global banner may
  be the only failure record.
- Raw fail-open remains an independent available path while cleanup errors and
  their details are visible.

## Open implementation decisions

- The vocabulary data contract determines final list density, filtering
  threshold, and validation copy.
- Targets may display only installation and permission states the local runtime
  can actually observe.
- Expanded prompt authoring remains separately scoped even though the Cleanup
  shell visibly accommodates Prompts and Vocabulary.
- Stable error codes and the sanitized fields available from each version-one
  API operation remain an implementation contract to define.
