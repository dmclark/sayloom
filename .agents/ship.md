Commit any uncommitted changes. Fetch origin and rebase onto origin/main. If a
substantive conflict occurs, stop and ask before resolving it. Run
`scripts/check` after the rebase. If any check fails, stop without pushing and
report the failure. Push to origin/main only after all checks pass. If the push
is rejected because main moved, rebase again, rerun `scripts/check`, and push
again. Report the commit and verification result, then archive this thread.
