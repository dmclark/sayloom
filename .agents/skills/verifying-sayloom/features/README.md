# Sayloom feature map

This index is the source of truth for verification scope. It maps user-visible and operational
contracts, not implementation modules. The index and sibling feature files must remain one-to-one.

## Baseline preconditions

- Use a new run ID, synthetic text, disposable SQLite database, dynamic port, and fresh browser
  session.
- Require the generated development-state identity and healthy schema before driving.
- Never interact with the stable application or its resources.
- Record every planned lane as `passed`, `skipped`, `unavailable`, or `configured in CI` using the
  definitions in `../SKILL.md`.
- Capture each entry point separately. Preserve evidence while removing run-created state.

## Features

| ID | Feature | Primary lanes |
|---|---|---|
| `WORKSPACE` | [Workspace editing and layout](workspace.md) | Portable, Isolated browser |
| `CLEANUP` | [Cleanup, outgoing selection, and safe errors](cleanup-outgoing.md) | Portable, Isolated browser, Provider |
| `PROMPTS` | [Prompt selection and cleanup preference](prompts-preference.md) | Portable, Isolated browser, Database/migration |
| `ADMIN` | [Schema, migration, seed, and import lifecycle](admin-lifecycle.md) | Portable, Database/migration, macOS integration |
| `RAYCAST` | [Raycast publication destinations](raycast.md) | Portable, macOS integration |

## Feature-file contract

Each feature file contains exactly these sections in order:

1. **Sub-features** with stable IDs and one behavior per item.
2. **How to get to it (user POV)** with every distinct entry point.
3. **Driving and proof** with prerequisites, action, observable result, and side-effect evidence.
4. **Gotchas** that can invalidate a run or a claim.

When only some sub-features are in scope, name them in the evidence ledger rather than claiming the
entire feature passed.
