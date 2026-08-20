---
name: Sayloom
description: A quiet, precise working surface for preparing trustworthy outgoing text.
colors:
  thread-blue: "#1769aa"
  thread-blue-dark: "#0b3f6b"
  thread-blue-pale: "#dbeaf6"
  ink: "#111820"
  night: "#0b121b"
  muted: "#5e6874"
  paper: "#eceae4"
  paper-bright: "#fffdf7"
  line: "#b9bec6"
typography:
  display:
    fontFamily: '"Iowan Old Style", Palatino, serif'
    fontSize: "clamp(2rem, 3vw, 3rem)"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "-0.035em"
  headline:
    fontFamily: '"Iowan Old Style", Palatino, serif'
    fontSize: "1.45rem"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  body:
    fontFamily: '"Avenir Next", Avenir, sans-serif'
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0.005em"
  editor:
    fontFamily: 'Charter, "Iowan Old Style", Georgia, serif'
    fontSize: "clamp(1.03rem, 1.25vw, 1.28rem)"
    fontWeight: 400
    lineHeight: 1.7
  label:
    fontFamily: '"Avenir Next", Avenir, sans-serif'
    fontSize: "0.68rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.15em"
rounded:
  control-tight: "2px"
  control: "3px"
  sheet: "4px"
  full: "999px"
spacing:
  micro: "4px"
  control-gap: "8px"
  compact: "12px"
  panel: "20px"
  content: "28px"
  section: "32px"
  frame: "64px"
components:
  button-primary:
    backgroundColor: "{colors.thread-blue}"
    textColor: "{colors.paper-bright}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "7px 14px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.thread-blue-dark}"
    textColor: "{colors.paper-bright}"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "7px 14px"
    height: "36px"
  field:
    backgroundColor: "{colors.paper-bright}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control-tight}"
    padding: "6px 9px"
    height: "36px"
  panel:
    backgroundColor: "{colors.paper-bright}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control-tight}"
  navigation-active:
    backgroundColor: "{colors.thread-blue-dark}"
    textColor: "{colors.paper-bright}"
    typography: "{typography.label}"
  error-record:
    backgroundColor: "{colors.paper-bright}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control-tight}"
    padding: "12px 16px"
---

# Design System: Sayloom

## Overview

**Creative North Star: “The Threaded Work Sheet”**

Sayloom feels like a carefully prepared working sheet: warm paper, exact rules,
ink-led typography, and a blue thread that connects source, transformation, and
outgoing state. It is a quiet macOS utility rather than a generic dashboard.
The interface should disappear during repeated use while remaining legible
enough to trust at a glance.

This is an extension of the incumbent code-defined world, not a replacement.
New setup surfaces inherit the same paper, rule, rail, heading, field, and
control language. Expression stays in small details—the thread mark, numbered
sections, serif working text, and restrained grain—while standard controls keep
their familiar behavior.

**Key Characteristics:**

- Warm paper and cool output surfaces bounded by fine, functional rules.
- Near-black utility chrome with one restrained thread-blue accent.
- Editorial serif for identity and working text; workhorse sans for controls.
- Vertically ordered, spacious task canvases with compact operational metadata.
- State is always written in words; color supports meaning but never carries it.
- Failures remain inspectable as quiet, ruled records beside the workflow that
  owns them, without interrupting raw fail-open.

## Colors

The strategy is restrained: neutrals own the surface and thread blue marks
selection, primary action, focus, and current operational state.

### Primary

- **Thread Blue:** primary actions, active markers, focus support, and current
  state indicators. It is functional, not decorative.
- **Deep Thread Blue:** selected navigation and primary-action hover states.
- **Pale Thread Blue:** the cool family used to distinguish generated output
  without making it look detached from the paper workspace.

### Neutral

- **Ink:** primary text and decisive rules.
- **Night:** utility rail, severe failure indicators, and modal backdrops.
- **Muted Graphite:** helper text, metadata, and inactive labels.
- **Work Paper:** the ambient page field.
- **Bright Paper:** editable sheets, fields, and raised controls.
- **Rule Gray:** borders, separators, and keyboard-key outlines.

**The Blue Thread Rule.** Blue appears only where the interface needs to show
selection, action, focus, or live state. Large inactive regions remain neutral.

**The Written State Rule.** Waiting, stale, failed, disabled, installed, and
selected states must have adjacent text. Never ask hue alone to explain state.

## Typography

The serif/sans pairing separates the text being worked on from the machinery
around it. Iowan Old Style gives the brand and section headings a calm editorial
voice; Charter gives long source and result passages a readable texture;
Avenir Next keeps labels and controls crisp and familiar.

### Hierarchy

- **Display:** product name only; never use display scale inside setup surfaces.
- **Headline:** panel and setup-area titles, kept concise.
- **Body:** interface explanation, field content, and ordinary metadata prose.
- **Editor:** Original and Cleaned text, with generous leading for comparison.
- **Label:** uppercase, tracked micro-labels, section numbers, and compact status
  captions. Sentence-case text remains the default for buttons and navigation.

**The Two Voices Rule.** Serif identifies the brand, titles the working sheet,
and carries authored or generated prose. Sans-serif operates the product.

**The Compact Label Rule.** Uppercase tracking is reserved for short labels;
never apply it to paragraphs, long actions, or wrapped navigation text.

## Layout

The desktop frame is centered at a maximum width of 1480px with 32px side
gutters. At widths below 920px the gutter contracts to 18px; below 760px it
contracts to 12px. Major surfaces align to the same left and right frame.

The persistent utility rail is 108px wide with a 14px gap to the active
surface. Its order is Workspace, Cleanup, Targets. Workspace keeps Original
above Cleaned at every width. The default split is 65/35, adjustable between
45/55 and 80/20, with an 18px separator. Collapsing Original gives Cleaned the
available height without changing text or context.

The Cleaned heading keeps prompt and vocabulary controls together because both
describe the result. The outgoing strip follows the panels and spans their
combined visual width. Its source selector, fallback reason, cleanup state, and
publication state form one scan line but remain separate facts.

API failures expand in place at the workflow that owns them. Cleanup details
belong inside the Cleaned sheet; publication details belong with Outgoing;
vocabulary and target failures stay with their selected profile, suggestion, or
target. One open disclosure may increase its owning sheet's height, but it must
not cover Original, obscure the outgoing source, or push raw fail-open out of
the visible task flow. Multiple failures remain separate ruled records rather
than merging into one global banner. On narrow screens, detail labels and values
stack into one column and actions wrap below them.

Cleanup uses persistent Prompts and Vocabulary tabs inside the setup area. Each
tab uses a master list with a selected detail sheet; do not nest independent
cards inside that sheet. Targets uses the same master-detail proportion and
control rhythm. On narrow screens, the rail becomes horizontal and each
master-detail view becomes list-to-detail navigation rather than squeezed
columns.

Spacing follows a 4px base with recurring 8px control gaps, 12–20px compact
groups, 24–32px sheet padding, and 64px frame-scale separation. More space
belongs inside the text canvases than around setup controls.

**The Linear Proof Rule.** Original → transformation context → Cleaned →
Outgoing must read in that order without crossing the page or opening a manager.

## Elevation & Depth

Depth is ambient and shallow. Paper sheets use fine borders plus a diffuse
shadow (`0 14px 42px rgba(11, 18, 27, 0.15)`). The utility rail may use the
same geometry at slightly greater opacity. Dialogs alone earn strong elevation
(`0 28px 90px rgba(11, 18, 27, 0.38)`) and a dark, softly blurred backdrop.
Fields and ordinary setup rows stay flat.

Subtle radial blue and ink tints may soften the page field, and the incumbent
grain may run across the viewport at low opacity. Neither treatment may reduce
text contrast or become visible decoration.

**The Sheet, Not Card Rule.** Borders organize working surfaces; shadows only
separate a complete sheet from the page. Do not turn every group into a card.

## Shapes

Sayloom is predominantly square and ruled. Form controls use 2–3px corners;
large sheets and dialogs stop at 4px. Full rounding is reserved for switches,
status pills, and circular icon actions whose geometry communicates their
behavior. Fine 1px borders do most of the structural work.

The thread mark and status lights are the only recurring circles. The thread
mark is line art, never a filled badge. Active navigation is a rectangular
field with a thin blue edge marker, not a floating rounded tile.

**The Earned Curve Rule.** A curve must identify a switch, a compact state, or
a circular action. Content containers remain sheet-like.

## Components

### Masthead

Use the line-drawn thread mark, uppercase workspace eyebrow, serif product
name, and optional compact environment badge. A single ink rule closes the
masthead; do not add global actions without a demonstrated workflow need.

### Navigation

The rail is Night with stacked numbered destinations. Default labels use muted
light ink; hover raises contrast with a slight light wash; active uses Deep
Thread Blue, bright text, and a 4px Thread Blue marker. At narrow widths the
same items become a horizontal strip in the same order.

### Text panels

Original is Bright Paper; Cleaned uses the pale blue output family. Each has a
ruled heading, an unboxed text canvas, and a compact footer. Original remains
the sole authoring surface. Cleaned is selectable and read-only. The horizontal
resizer uses rules around a short double-blue grip and exposes separator
semantics for keyboard use.

### Buttons and controls

Primary buttons are blue with bright text and a 3px corner. Hover shifts to
Deep Thread Blue and may lift 1px; active returns to baseline. Quiet buttons
have no border at rest. Selects and inputs are Bright Paper with one Rule Gray
border and 2px corners. Every control receives the incumbent 3px translucent
blue focus outline with a 3px offset.

Disabled controls reduce opacity but keep their label readable. Saving and
loading labels update in place; layout must not jump. Control transitions stay
between 120ms and 180ms. The incumbent page-entry settle may remain, but new
surfaces must not add staged entrance choreography. Reduced-motion preferences
collapse motion to effectively instant state changes.

### Tabs and master-detail setup

Cleanup tabs are text-led and ruled, not pill tabs. The selected tab uses blue
type or a blue underline plus explicit selected semantics. Lists use full-width
rows separated by rules; selection uses a pale blue field and a blue edge. The
detail side is one continuous sheet with section headings, fields, and a fixed
save/status row. Prompts and Vocabulary share this shell without merging their
different data models.

Targets uses the same list/detail shell. Each row pairs a target identity with
one written installation or permission state. Definition, generated command
preview, and observed installation state are separate ruled sections. Save,
install/regenerate, disable, and remove must remain visually and behaviorally
distinct.

### Outgoing selector and state

The outgoing strip is the signature operational component. It begins with
“Outgoing,” then a two-option Cleaned/Original segmented control. The selected
half is Thread Blue with bright text; the unselected half remains Bright Paper.
Adjacent copy names the current source or fallback reason. Cleanup status and
publication readiness follow as separate compact indicators.

Never add a third editable value, target chooser, or send button to this strip.
When Cleaned is unavailable, Original is selected in behavior and the reason is
written next to the control.

### Status

Compact status pills use a fine border, translucent paper, a small light, and a
written label. Longer publication or permission states may use an unboxed light
plus label. Processing may breathe gently; errors use Night and explicit error
copy. Do not introduce a green/red semantic palette unless the whole system is
deliberately extended and contrast-tested.

### Inspectable errors

An API failure is a persistent ruled record inside the surface that owns the
operation—not a toast, modal, or floating alert. A narrow Night edge, Ink text,
and ordinary Bright Paper distinguish it without adding an alarm palette. The
summary contains an operation/time micro-label, one specific sentence naming
what failed, a short consequence or recovery cue, and **View details**.

Expanded details use a compact ledger of safe fields: operation, local time,
HTTP status when available, stable error code, sanitized server message, and a
concrete retry or setup action. **Copy details** copies exactly those visible
sanitized fields and nothing more. If no additional safe detail exists, say so
plainly. Never reveal or copy credentials, headers, Original or Cleaned text,
provider payloads, stack traces, database contents, or private paths.

Each failed operation keeps its own identity and disclosure. Cleanup/provider,
outgoing publication, configuration, vocabulary, and target failures never
overwrite one generic status. Network unavailable, timeout, malformed response,
and server rejection receive distinct summaries even when their recovery action
matches. Records persist until success, a relevant state change, explicit
dismissal, or replacement by a newer failure for the same operation.

The error record reports failure; it does not control fail-open. When cleanup is
unavailable, the Outgoing selector visibly moves to Original, writes the fallback
reason beside the selector, and remains usable while error details are open.

**The Inspectable Failure Rule.** Every API failure leaves a durable, safe,
copyable explanation at its owning workflow while the user's available path
continues independently.

## Do's and Don'ts

### Do

- **Do** inherit the incumbent paper, rail, rule, type, and control language on
  Workspace, Cleanup, and Targets.
- **Do** preserve generous text canvases and compact setup controls.
- **Do** keep prompt and vocabulary context visible with Cleaned.
- **Do** keep Original, Cleaned, and Outgoing source unambiguous in every state.
- **Do** use one continuous sheet or ruled list before adding another container.
- **Do** preserve keyboard focus, resizing, text selection, and readable wrapping.
- **Do** keep each simultaneous API failure separately named, persistent, and
  expandable at the workflow that owns it.
- **Do** make visible safe details and copied details the same bounded dataset.

### Don't

- **Don't** introduce rounded dashboard cards, bento grids, glass, or a second
  accent identity.
- **Don't** use serif type for buttons, form labels, navigation, or status text.
- **Don't** decorate inactive regions with blue or rely on color-only state.
- **Don't** place Original and Cleaned side by side or hide the resizable divider.
- **Don't** add recording-review UI, a target picker, or delivery claims to the
  workspace visual world.
- **Don't** persist or depict real dictated content in documentation or comps.
- **Don't** use a toast as the only failure record or collapse unrelated errors
  into one global banner.
- **Don't** let an expanded error disclosure block editing, choosing Original,
  or understanding the current outgoing value.
