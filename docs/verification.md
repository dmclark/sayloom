# Verification before publication and Stable approval

Use full Linux CI and change-selected local checks. Apply this policy manually;
there is no pre-push selector or hook. Development restart/activation retains
`scripts/check --quick` and does not depend on publication checks or GitHub.

## Trusted Linux result

The existing workflow runs full `scripts/check` on every pull request and push
to `main`, on standard `ubuntu-latest`, with Python 3.12, Node 24 and uv caching.
Local selection never reduces that hosted coverage. Explicit full local
verification remains available as `scripts/check` or `scripts/check --full`.

The Linux identity enforced by Stable's eligibility lookup (#217) is:

| Field | Required value |
| --- | --- |
| Repository | `dmclark/sayloom` on `github.com` |
| Workflow path | `.github/workflows/ci.yml` (display name `CI`) |
| Event and branch | `push`, `main` (`refs/heads/main`) |
| Commit | Run `head_sha` equals the complete pinned published-main candidate SHA |
| Job | Workflow job key `checks`, explicit job/check name `Linux full checks` |
| Outcome | Completed successful workflow run and required job in the latest applicable run/attempt |

Validate workflow and repository provenance, not just a matching check name.
A successful parent, a PR merge/ref result, a fork or other workflow's same-named
check, or an older successful attempt followed by a pending/failed rerun does
not qualify. Missing, pending, failed, cancelled, skipped, neutral or unverifiable
results do not qualify. Lookup must account for pagination and reruns and fail
closed on API outage/rate limits. No hosted Mac result is required.

Stable previews eligibility and checks it again before stopping the service and
before replacing code. The lookup uses the public GitHub API without credentials
or a `gh` login. It validates workflow/repository provenance, paginates runs and
jobs, selects the highest run number and its latest attempt, and refuses
incomplete or inconsistent responses (including results beyond the API's
1,000-result search limit). The `checks` job's explicit API name is
`Linux full checks`; a same-named job outside that trusted workflow cannot qualify.
Only canonical `github.com/dmclark/sayloom` upstream URLs qualify for updates;
custom-source update support is deliberately narrowed, not silently trusted.
Installed-version start/restart remains offline and independent of this gate.

This gate replaces ordinary updates' candidate-wide full-suite/lint/syntax
reruns, not the installation/configuration/schema, locked preparation, synthetic
command, backup/rehearsal, recovery or health safeguards. Backup and rehearsal
occur **after stopping Stable**. Changing CI metadata is separate from structural
plan equality; upstream movement does not change the reviewed candidate SHA.
See [copied-controller adoption](../README.md#adopt-the-new-copied-controller):
an old installed copy retains its old checks for the first successful update.

Branch protection is unchanged. After separately authorized publication, inspect
the exact published SHA's Actions run and job, including provenance, attempt and
conclusion, before claiming hosted success. A local run is not a GitHub check;
source implementation and synthetic acceptance are not installed acceptance.

## Select local checks by responsibility

Start with these coarse existing pytest groups; do not infer impact line by
line or split test modules solely to classify them.

| Group | Existing test files |
| --- | --- |
| Application | All top-level `tests/test_*.py` except `test_stable.py`, `test_raycast.py`, `test_admin.py`, `test_check.py`; include shared tests below. `test_targets.py` deliberately belongs to both groups. |
| Mac integration | `tests/test_stable.py`, `tests/test_raycast.py`, `tests/test_targets.py`; include shared tests below. |
| Shared tests | `tests/test_admin.py`, `tests/test_check.py` accompany either group. Changes to these files select both groups. |
| Both | Union of the groups without duplicate execution: every current top-level pytest file. New/unmapped tests default to both until classified. |

Use the following path-to-responsibility mapping. Abbreviated module names in
the `src/local_text/` rows share that prefix; script paths are written in full.

| Changed paths | Selection |
| --- | --- |
| `src/local_text/cleanup.py`, `prompts.py`, `personal_corrections.py` | Application; accompanying startup/configuration/schema changes select both. |
| `src/local_text/static/*`, `tests/browser/*` | Application plus affected browser checks. |
| `raycast/*`, `launchd/*`, `scripts/raycast_aliases.py`, `scripts/install-raycast.py`, `scripts/render-launchd-plist.py` | Mac integration, including target-generation and synthetic Raycast server-response coverage. |
| `scripts/dev.py`, `scripts/stable.py`, `scripts/development_state.py`, `scripts/run-development.py`, runtime/lifecycle shell wrappers | Both: service management shares configuration, startup, migration and environment contracts. |
| `src/local_text/app.py`, `config.py`, `database.py`, `models.py`, `state.py`, `admin.py`, `legacy_import.py`, `prompt_store.py`, `target_store.py`, `targets.py`, `target_adapter.py` | Both: startup, schema, seeding, health/outgoing-state APIs and generated-command contracts. An API-only edit in `app.py` is not automatically application-only. |
| `migrations/*`, `alembic.ini`, `pyproject.toml`, `uv.lock`, `src/local_text/__init__.py` | Both: schema, dependencies and independent installation. |
| `scripts/check`, shared test fixtures, `.github/workflows/*`, executable environment setup, future selector/hook implementation | Both: verification must cover its consumers. |
| Classified test file alone | Its group; shared or unclassified tests select both. |
| Known prose-only changes | Relevant content, links and diff checks; no application/native suite merely for prose. Executable configuration is not prose. |
| Mixed changes, cross-group renames, deletions, unlisted executable paths | Union affected groups; unresolved executable impact defaults to both. Include old and new paths for renames/deletions. |

For manual application selection, pass the application and shared files to
`uv run pytest`. For Mac integration, run
`uv run pytest tests/test_stable.py tests/test_raycast.py tests/test_targets.py tests/test_admin.py tests/test_check.py`.
For both, use `scripts/check --full`; pytest collects each file once. Run cheap
relevant dependency, lint, JavaScript syntax, diff and shell checks alongside a
selected group (`scripts/check --quick` provides those checks without pytest).
Record the actual file list and selection reason. Missing required tooling or
evidence means incomplete verification, not success.

### Browser and native Mac checks

Browser verification is separate from native Mac verification. JavaScript
syntax checking does not run `tests/browser/inspection.py`, `findings.py` or
`personal_correction_approval.py`. Select affected scripts/interactions and use
their documented entry points with available Playwright/Chromium tooling;
the project manifest does not supply that tooling. Follow
[UI verification guidance](agents/ui-verification.md) for isolated data and
inspected captures when appearance changes. Record coverage gaps explicitly.

Run selected Mac integration checks locally on macOS. In particular, these
`tests/test_raycast.py` tests must execute with native `/usr/bin/plutil`, not skip:

- `test_raycast_fetch_preserves_multiline_outgoing_text`
- `test_raycast_fetch_preserves_utf8_outgoing_text`
- `test_raycast_fetch_refuses_empty_or_malformed_state`

A Linux synthetic run does not replace those native checks. Portable-only
application changes do not require a Mac merely because this integration exists.
Other Raycast/target tests stub clipboard/application commands or inspect
generated scripts; they do not establish desktop permissions or actual delivery.

## Candidate-bound local evidence

Keep a review record outside Git, without operating text, credentials or private
configuration. Use `.amp/in/artifacts/` after verifying the repository-local
exclude; follow the worktree's temporary-directory policy for disposable tests.
Record:

- Purpose/date, tested commit SHA and tree, and whether the worktree is clean.
  For uncommitted work, record HEAD plus a SHA-256 digest of the complete patch
  (including new files) and its file inventory; do not label it a tested commit.
- Comparison base SHA, candidate SHA/tree or uncommitted patch identity, and
  complete affected paths (`git diff --name-status BASE CANDIDATE` for commits,
  accounting for untracked files when reviewing local edits).
- Selected groups, actual test files, reasons, browser/native/real-service
  applicability, and reasons for exclusions.
- Exact commands, platform/tool versions, outcomes, test counts, skips and their
  reasons, log locations, unavailable tooling and remaining limitations.
- Separately, hosted run URL/ID, exact SHA, workflow/job provenance, attempt and
  conclusion when available; otherwise mark hosted evidence pending publication.

For pre-publication review assess the complete branch change relative to its
integration base, not just the latest commit. For Stable approval assess the
entire installed-version-to-pinned-candidate delta, not just the last feature or
pre-push diff. Evidence must cover the candidate's resulting code. Rebase,
merge, conflict resolution or subsequent edits require renewed impact assessment
and affected checks; earlier evidence is reusable only for unaffected code with
that reasoning recorded. A future outgoing-commit hook cannot prove a later
integration result.

The trusted owner/agent reviews applicable application, Mac, browser and
separately authorized real-service evidence before the existing explicit Stable
update approval. Resolve missing required evidence before approval. A different
candidate requires renewed review. No signed attestation, verification database
or second approval stage is introduced. Automated #217 eligibility covers
Linux CI only: unattended invocation or `--yes` neither proves local testing nor
waives the operator's review responsibility.

## Separate real-service evidence

Ordinary lifecycle tests keep `LOCAL_TEXT_TEST_LAUNCHD` unset and use synthetic
`launchctl`/`plutil` with isolated homes, databases, ports and identities. They
exercise controllers and real application processes, not the real service manager.

Changes to service installation/plists, activation/restart, launch environment,
ownership detection or recovery require separately authorized real-launchd
evidence before claiming those real-service behaviors accepted. For other
changes record why this lane is not affected. Never enable it automatically or
operate owner services as a test. Synthetic success is not real-service acceptance.

Before any authorized execution, verify a disposable macOS GUI launchd session,
synthetic external paths/configuration/data, unused ports, unique service labels
and a cleanup plan for every agent/process/artifact. Inspect the exact selected
tests and fixtures first: the current opt-in branch of `service_environment`
only cleans the Stable manifest's label, and some development/coexistence and
failure-injection tests require the synthetic branch or skip with real launchd.
Do not simply run the entire suite with `LOCAL_TEXT_TEST_LAUNCHD=1` and call its
skips real-service coverage. Define a compatible bounded scenario and verify
cleanup after both success and failure before claiming acceptance. Missing a
suitable disposable environment or authorization leaves this evidence pending.
Actual Raycast application delivery, accessibility/automation permissions and
clipboard behavior need their own authorized desktop checks.

## Scope and provenance

This policy implements the amended [#216](https://github.com/dmclark/sayloom/issues/216)
contract and the [approved selection boundaries](https://ampcode.com/artifacts/test-selection-boundaries-1187d495-3825-4bbb-a32c-ccb9e302f092).
The Stable gate and documented copied-controller adoption implement amended
[#217](https://github.com/dmclark/sayloom/issues/217). The pre-push selector, hosted
Mac CI, workflow dispatch and owner-service actions remain outside scope.
Publication and installation require separate authorization; local success alone
establishes neither hosted CI nor installed acceptance.
