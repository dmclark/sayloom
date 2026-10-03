# Unified tracked-change Personal Correction field

**Date:** 2026-10-03

**Scope:** Feasibility research for issues [#149](https://github.com/dmclark/sayloom/issues/149), [#150](https://github.com/dmclark/sayloom/issues/150), and [#151](https://github.com/dmclark/sayloom/issues/151)

**Status:** Recommendation for the next design prototype; no production decision or implementation

## Conclusion

Variant A can show the optional **Observed sentence → Intended sentence** evidence
as one track-changes-style visual field, but it must not become one stored value or
replace the ordered mapping controls.

Use one visual container with two modes:

1. a default **Review changes** mode that renders a read-only derived diff with
   deletions and insertions; and
2. an explicit **Edit intended sentence** mode containing a native `<textarea>`
   whose value is only Intended.

Observed remains the frozen pre-edit sentence. It may be omitted from approval,
but it is never edited. Intended alone is editable and may independently be
omitted. Each selected mapping retains its own operation, observed/intended text,
ordinal, reuse eligibility, and any context-conflict decision. This is “one visual
field,” not “one value.”

This preserves the product rule that only an explicitly reviewed Original →
Intended mapping becomes durable authorization, while ordinary editing saves
nothing ([product contract](../../PRODUCT.md#personal-corrections-and-research-boundary)).
It also preserves the implementation specification's distinct nullable sentence
fields and structured mapping rows
([implementation specification](../../docs/personal-corrections-implementation-spec.md#personal_correction_episodes)).

## Meaning and state

The field is a review projection over these authoritative values:

| Value | Authority and behavior |
| --- | --- |
| `observed_sentence` | Frozen pre-edit sentence from the bound review. Read-only. An explicit **Do not save observed sentence** action sets it to `null`; it does not turn it into editable text. |
| `intended_sentence` | Editable post-edit sentence. Editing changes only this value. An explicit **Do not save intended sentence** action sets it to `null`. |
| ordered mappings | Independently selected and editable structured records. Their operation and observed/intended terms—not sentence-diff spans—authorize reusable replacements and episode-only additions/removals. |
| rendered diff | Ephemeral derivation of the two retained sentences. It is never submitted, persisted, or treated as mapping identity. |

The domain distinguishes Intended text as wording confirmed or rewritten by the
user, while a Repair is a reviewable lexical addition, removal, or replacement
([domain glossary](../../CONTEXT.md#language)). The storage contract likewise
requires operation-specific shapes: addition = null observed/non-empty intended,
removal = non-empty observed/null intended, and replacement = both non-empty
([implementation specification](../../docs/personal-corrections-implementation-spec.md#personal_correction_episode_mappings)).
A single serialized rich-text value would erase these distinctions and is rejected.

Editing Intended should re-diff the sentence display after input settles, but
should **not** regenerate, select, split, merge, or rewrite mappings. The current
contract makes sentence evidence and mapping text separately editable; coupling
them would silently change what the user authorizes. A short note should say that
the sentence provides private context and the selected mappings below are what
become the correction episode.

Independent sentence removal remains visible through two named controls outside
the text surface. If Observed is omitted, Review mode shows retained Intended
without deletion markup. If Intended is omitted, it shows retained Observed as
reference, not as a pending deletion. If both are omitted, the container shows
“No sentence context will be saved.” Either value can be restored from the
in-memory bound review until Save or dismissal.

## Mapping selection and context conflicts

Inline changes are not safe selection units. Repeated words, reorderings, adjacent
edits, and later Intended edits can produce different diff segmentation while the
same user-approved mapping remains valid. The complete sheet should therefore keep
the ordered candidate list from Variant A:

- every candidate starts unselected;
- selection and operation-specific editing happen in mapping rows;
- optional visual correspondence between a row and diff highlight is explanatory
  only;
- sentence removal never removes a mapping, and mapping removal never removes a
  sentence;
- additions/removals remain episode-only, while non-empty replacements alone may
  create or reuse profile entries.

An applicability-context conflict belongs to the selected reused replacement,
not to a sentence span. Render **Keep existing context** / **Replace with this
review** beside that mapping (or in a clearly keyed conflict panel), and gate Save
until every selected conflict has a choice. Issue #151's optimistic revision and
409 behavior is unchanged.

## Browser implementation assessment

### Recommended: read-only diff plus native edit mode

Render Review mode from text nodes plus semantic `<del>` and `<ins>` elements;
HTML defines those elements as document edits
([WHATWG HTML, Edits](https://html.spec.whatwg.org/multipage/edits.html)). Provide
an adjacent plain-language summary such as “1 replacement and 1 removal,” because
visual styling or edit markup alone is not a sufficient screen-reader interaction
contract. WAI-ARIA defines `suggestion`, `deletion`, and `insertion` semantics, but
`suggestion` has a strict child model and ARIA 1.3 remains a draft; do not make it
the only way changes are conveyed
([WAI-ARIA 1.3, `suggestion`](https://www.w3.org/TR/wai-aria-1.3/#suggestion)).

Edit mode uses the repository's established native `<textarea>` pattern. A
textarea is a multiline plain-text editing control whose user-agent behavior
includes insertion, deletion, line breaks, wrapping, `maxlength`, and `input`
events ([WHATWG HTML, `textarea`](https://html.spec.whatwg.org/multipage/form-elements.html#the-textarea-element)).
That delegates caret, selection, keyboard navigation, platform undo/redo, paste,
mobile virtual keyboard, autocorrection, and IME composition to the browser.

Implementation rules:

- switch modes only through a labeled button; focus the textarea on entry and
  return focus to that button on exit;
- do not rerender or assign `.value` during an active composition; Input Events
  specifies non-cancelable `insertCompositionText` events between
  `compositionstart` and `compositionend`
  ([Input Events Level 2, composition](https://www.w3.org/TR/input-events-2/#events-composition));
- accept plain text only, let the textarea own selection and paste, and recompute
  the diff after `input`/`compositionend`, not on each keydown;
- use native Undo/Redo while edit mode remains open; do not promise that undo
  crosses a mode switch;
- expose a persistent label, retained/omitted state, character count, validation
  error, and the mapping summary in DOM text; color and strike-through are
  supplementary;
- support the complete flow by keyboard. WCAG requires all functionality to be
  operable through a keyboard interface
  ([WCAG 2.2 SC 2.1.1](https://www.w3.org/TR/WCAG22/#keyboard)).

On narrow screens, stack the summary, field, sentence-retention controls, and
mapping list; allow natural wrapping and vertical scrolling. Do not require hover,
dragging, horizontal scrolling, or precise placement inside marked text. The
prototype already established 390×844 as the representative narrow viewport
([Variant A prototype thread](https://ampcode.com/threads/T-b56bddd6-e907-4592-87ff-c85d3c804691)).

### Rejected: textarea overlay as the primary editor

An overlay can place highlighted HTML behind or above a transparent textarea, but
the textarea can contain only the editable Intended string. Frozen deleted text
changes line wrapping and geometry without existing in the textarea's caret model,
so selection, hit testing, scrolling, IME candidate placement, and mobile zoom can
diverge from what the user sees. Putting Observed deletions into the textarea would
instead make them selectable and editable. This approach is feasible for passive
syntax highlighting, not for trustworthy mixed frozen/editable tracked changes.

### Rejected for this phase: `contenteditable` editor model

`contenteditable` can visually interleave editable insertion text with frozen
deletions, and Input Events provides `beforeinput`, `inputType`, paste data, and
target ranges for editing hosts
([Input Events Level 2](https://www.w3.org/TR/input-events-2/)). However, the app
would then own a document model and transaction layer for DOM normalization,
selection mapping around non-editable spans, composition, paste sanitization,
mobile caret behavior, and coherent undo/redo. Input Events also notes that IME
composition edits are not cancelable, while target ranges differ between
contenteditable and textarea. The discontinued W3C ContentEditable draft itself
records caret-placement issues around non-editable regions and says the `true`
state is not well-defined
([W3C ContentEditable draft](https://www.w3.org/TR/content-editable/)). That cost
is disproportionate for two bounded plain-text values in the project's dependency-
free HTML/CSS/JavaScript stack.

## Privacy, persistence, and stale state

No database migration or API shape change is needed. Approval must continue to
send the same separate nullable sentence fields, selected structured mappings,
context decisions, `approval_id`, and bound mode/version metadata. The database
continues to enforce sentence and mapping bounds and operation shapes. The server
must never parse visual markup to recover meaning.

Keep Observed, Intended drafts, diffs, and undo state in memory only. Do not put
them in local storage, URLs, analytics, routine logs, clipboard helpers, or HTML
strings. Build diff DOM with text nodes, not `innerHTML`. Preserve `Cache-Control:
no-store`, privacy-safe errors, atomic/idempotent approval, and the rule that
surrounding Original, Prepared, Outgoing, provider payload, and model output are
not persisted
([implementation specification](../../docs/personal-corrections-implementation-spec.md#api-boundary)).

The existing stale boundary is unchanged: once review opens, another Original
edit, changed transformation input/result, reload, or restart invalidates review;
the client rejects stale Save and a server revision conflict returns 409 without
mutation
([implementation specification](../../docs/personal-corrections-implementation-spec.md#invalidation)).
Switching Review/Edit modes or editing Intended inside the sheet changes only the
review draft and must not stale the bound source revision.

## Effect on Variant A and issue acceptance

Variant A remains a temporary complete sheet over the unchanged Original/Prepared
workspace. Replace its two sentence textareas with the single two-mode sentence
container, but retain mapping rows, private applicability context, per-replacement
conflicts, status/error area, explicit dismissal, and explicit Save. A final
ordered mapping summary before Save remains valuable because the track-change
sentence is not the authorization payload.

Suggested acceptance-criteria amendments:

- **#149:** review presents one accessible sentence-change container; Observed is
  frozen and independently omittable, Intended alone is editable and independently
  omittable; Review mode accurately re-diffs after edits; one replacement is still
  selected and edited in its structured mapping row. Add keyboard, IME,
  paste-as-plain-text, native undo/redo-within-edit-mode, focus-return, and
  screen-reader summary checks on desktop and narrow browser.
- **#150:** mixed mapping selection remains a separate ordered 1–20 list. Add
  asymmetric cases proving sentence diff segmentation cannot change mapping
  ordinals, operation shapes, selection, or replacement-only reuse. Verify narrow
  wrapping without horizontal overflow.
- **#151:** no persistence or concurrency change. Require every conflict control to
  identify its mapping by ordinal and terms in accessible text, remain reachable by
  keyboard, and keep Save disabled until resolved.

## Interaction sketch

```text
Personal Correction

Sentence context                         [Edit intended sentence]
┌──────────────────────────────────────────────────────────────┐
│ I need a [del: absurd] [ins: observed] result tomorrow.     │
│ 1 replacement                                                │
└──────────────────────────────────────────────────────────────┘
[✓ Save observed sentence]  [✓ Save intended sentence]

Mappings saved in this episode
[✓] 1  Replacement   absurd  →  observed
       Context conflict: ( ) Keep existing  (•) Replace existing
[ ] 2  Removal       tomorrow → —

                                      [Dismiss] [Save Personal Correction]
```

In Edit mode, the box becomes a labeled textarea containing only “I need an
observed result tomorrow.” Frozen Observed and deletion markup are outside its
caret model. Returning to Review mode recomputes the display without changing
mapping selection.

## Risks and unresolved decisions

1. Confirm that editing Intended sentence is intentionally independent of mapping
   text; automatic remapping is not recommended.
2. Decide whether omitted sentence values can be restored during the same review
   and settle exact control copy. Restoration from in-memory bound values is the
   recommended reversible behavior.
3. Decide whether Edit mode exits explicitly (**Review changes**) or on blur.
   Explicit exit is safer and preserves focus predictability.
4. Validate the prototype with the supported desktop browser plus macOS VoiceOver
   and one mobile screen reader. Standards define semantics, not the quality of
   each browser/assistive-technology announcement.
5. Confirm whether inline correspondence highlighting is worth its complexity.
   It must remain explanatory and must not become selection or persistence state.

## Suggested next design step

Build a throwaway Variant A interaction prototype of this two-mode container with
one replacement, one removal, an edited Intended sentence, independent sentence
omission, and one applicability-context conflict. Test keyboard-only use, IME
composition, paste, undo/redo, 390×844 wrapping, and VoiceOver before changing the
three implementation tickets.
