# UI verification

Read this before verifying UI changes. Use synthetic data in an isolated runtime.

- For interaction or semantics, prefer DOM inspection, browser logs, targeted
  tests, and accessibility snapshots. Assert behavior separately from appearance.
- For appearance changes (layout, styling, clipping, responsive behavior, or
  modals), capture the affected components and inspect the rendered result.
  Cover representative affected states at desktop widths. Follow
  [workflow preferences](workflow-preferences.md) for the deferred mobile UI stage;
  normal development does not require mobile or 390px captures.
- Inspect every retained screenshot and reuse unchanged captures. Ask before
  inspecting more than three screenshots in one task. Report the number inspected
  and what each verified.
- Keep visual work within the requested design; do not propose unsolicited alternatives.
- Clean up temporary captures and other run-created resources after verification.
