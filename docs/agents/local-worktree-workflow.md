# Local worktree workflow

Read this before changing code on the local machine. These requirements do not
apply to an orb's isolated checkout.

Use one Supacode-managed worktree per independently changing topic, on an
appropriate topic branch, served by the canonical shared Amp runner `runner-1`.
Keep the primary `main` worktree clean for integration and its configured runtime;
local-state diagnosis there is read-only. Integrate only after review and explicit
authorization. Preserve manager-owned locks; never force-unlock or manually remove
managed worktrees.

## Before editing

1. Create or select the topic's dedicated Supacode worktree and canonicalize its path.
2. Confirm that exact path is registered with Supacode and Git, retains its
   manager-owned lock, and is served by `runner-1`.
3. Verify repository, branch, HEAD, tracking, recent commits, and status.
4. Use an implementation thread created directly on `runner-1` with
   `working_directory` exactly equal to the verified canonical path. Reuse the
   current thread only if it is already bound correctly; otherwise create a
   correctly bound continuation.
5. Keep the task's reads, edits, commands, and verification in that worktree.

Proceed only after every registration and binding check succeeds. Creating or
focusing a worktree, or setting a shell command's `workdir`, does not reattach a
thread, executor, or Changes panel. Existing threads cannot be rebound retroactively.

Create or select a named development state only when the task needs isolated
application runtime or database data.
