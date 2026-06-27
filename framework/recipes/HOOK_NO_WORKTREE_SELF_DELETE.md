# Recipe: `no_worktree_self_delete` hook

**Purpose**
Refuse `git worktree remove <path>` when the shell's cwd is inside `<path>` —
self-deleting the cwd dangles the session and usually forces a restart.

**What it enforces / matches**
- Per segment (split on `&&`, `||`, `;`, `|`): strips leading `ENV=val`
  assignments and `git` globals (`-C dir`, `-c k=v`, other flags), requires
  `worktree remove`, extracts the first non-flag arg as `<path>`.
- Blocks when realpath(cwd) == realpath(path) or is a descendant (uses
  `Path.relative_to`, so `/foo/bar` does NOT match `/foo/bar-sibling`).
- cwd is recovered via `resolve_invocation_cwd` (last-cd-wins): `cd /safe &&
  git worktree remove <wt>` ALLOWS; `cd <wt> && git worktree remove <wt>` BLOCKS;
  `cd <nonexistent>` falls back to stdin cwd.
- Does NOT match `worktree list`/`add`/`prune`, non-git commands, or paths that
  don't resolve to an existing dir. Fail-open on any exception.

**Config keys used**
- None.

**Adaptation notes**
- Remediation runs `git rev-parse` to suggest a safe cwd; harmless if absent.
- Logging path comes from `paths.events_log` via `_framework_log`.
