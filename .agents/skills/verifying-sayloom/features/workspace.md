# Workspace editing and layout

The browser provides a focused Original editor, read-only Cleaned output, clear and collapse
controls, and a keyboard/pointer-adjustable stacked layout.

## Sub-features

- `WORKSPACE.INPUT`: typing, ordinary paste, and compatible dictation update Original and its count.
- `WORKSPACE.CLEAR`: Clear empties both editors and returns focus to Original.
- `WORKSPACE.COLLAPSE`: Hide input collapses Original without losing text-entry focus; the control's
  expanded state and label stay accurate.
- `WORKSPACE.RESIZE`: the separator starts at 65/35, supports pointer drag, Arrow keys, Home, End,
  and double-click reset, and stays within 45–80% Original.
- `WORKSPACE.RESPONSIVE`: desktop uses the available viewport and the narrow layout remains usable.

## How to get to it (user POV)

- Open the generated isolated Sayloom Development portal and focus **Original source text**.
- Use **Clear** or **Hide input** in the workspace controls.
- Tab to **Resize Original and Cleaned fields** and use keyboard controls; separately exercise a
  pointer drag and double-click.

## Driving and proof

Preconditions: healthy isolated browser lane, cleanup disabled to avoid provider timing, synthetic
input only.

- Enter synthetic multiline text. Prove the Original value, character count, native focus/caret,
  accessibility-tree textbox name, and screenshot state.
- Activate Clear. Prove both textbox values are empty, Original is focused, the outgoing API has an
  empty kind, and accessibility status reports the clear publication result.
- Activate Hide input and its inverse. Prove `aria-expanded`, visible layout, retained Original
  value, and focus behavior.
- On the separator, exercise ArrowUp/ArrowDown/Home/End and pointer input. Prove `aria-valuenow`,
  `aria-valuetext`, bounds, reset to 65, and screenshots at desktop and narrow viewports.

Portable support comes from the focused app/static tests, but browser claims require a live drive.

## Gotchas

- Programmatically assigning a textarea value without dispatching the real interaction does not
  prove typing, paste, or dictation behavior.
- A screenshot cannot prove focus, caret, accessible values, or keyboard operation.
- Cleanup debounce can change the Cleaned panel while layout evidence is being captured; disable
  cleanup for deterministic workspace-only proof.
