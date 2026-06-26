# Generic Lib Prompt: Safe Fast-Forward of the Local Default Branch

## Purpose

After any push/merge to the remote default branch, the local checkout of that
branch should pick up the change **immediately** rather than silently lag. A
stale local default branch is a real hazard: tools, hooks, and skills that live
in the repo run off the on-disk (old) version, producing false orientation and
risking work built on a superseded base.

This module fast-forwards the local branch to its remote tracking branch — but
**only when provably safe**. Anything it cannot do safely it reports and refuses,
never guesses.

## Reusable Pattern

**Side-effect-guarded core with strict safety preconditions.** Fast-forward only
when ALL hold:

- the checkout is currently **on the target branch** (never move a feature branch);
- local is **strictly behind** the remote (`behind > 0` AND `ahead == 0`) — never
  rewrite a divergence, never touch an already-current tree;
- the working tree carries **no real local modifications** — tracked changes
  outside a generated-file allowlist abort the sync.

It NEVER force-updates, NEVER creates a merge commit (`--ff-only` only), and
NEVER discards real local work.

**Stash-around for perpetually-dirty generated files.** Machine-generated tracked
files (error logs, checksum/cache files rewritten by hooks every edit) are
*always* dirty in an active session and would otherwise block every sync. Keep a
small **allowlist** of such paths; stash them around the fast-forward and restore
after. If the restore conflicts (origin also changed the file), the
fast-forward still lands and the stash is left for manual recovery — graceful,
not lossy.

**Refusal is a safe outcome, not an error.** Distinguish a *hard* failure (git
plumbing error → `ok=False`, non-zero exit) from a *refusal* (diverged / ahead /
genuinely dirty tree → `ok=True`, exit 0 with a diagnostic). A caller wiring this
into a hook or session-start must not break on a normal "can't fast-forward right
now" state.

**Make a refused-while-behind state LOUD.** A refusal to fast-forward *while the
branch is behind* is a stale-base hazard — the operator might start
default-branch-targeting work off an old tree. Render that case as a multi-line
banner with the behind-count and the blocking paths, not one quiet line that
scrolls past.

## Algorithm

1. `rev-parse --abbrev-ref HEAD`; if not on the target branch → `skipped-not-on-branch`.
2. Optionally `fetch <remote> <branch>`.
3. Count `behind = branch..remote/branch` and `ahead = remote/branch..branch`.
4. If `ahead > 0` → `refused-diverged` (if also behind) or `refused-ahead`.
5. If `behind == 0` → `up-to-date`.
6. Else (behind, not ahead): inspect the dirty tree.
   - tracked changes outside the allowlist → `refused-dirty` (loud banner).
   - only allowlisted generated files dirty → stash them, `merge --ff-only`,
     pop the stash (leave it if the pop conflicts) → `fast-forwarded`.
7. Exit non-zero only on `status == "error"`.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Fast-forward the local default branch to its remote when provably safe.

Never force-updates, never makes a merge commit, never discards local work.
A refusal (diverged/ahead/dirty) is a safe outcome and exits 0.
"""
from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Tracked, machine-generated files safe to stash around a fast-forward — they
# are perpetually dirty in an active session. Repo-root-relative POSIX paths.
GENERATED_ALLOWLIST: frozenset[str] = frozenset({
    # e.g. ".cache/error-log.jsonl", "index/checksums.json"
})


@dataclass
class SyncResult:
    ok: bool          # False only for a HARD failure (git plumbing error)
    status: str       # fast-forwarded | up-to-date | skipped-not-on-branch
    #                 | refused-ahead | refused-diverged | refused-dirty | error
    detail: str
    behind: int = 0
    ahead: int = 0
    from_sha: str = ""
    to_sha: str = ""
    dirty: list[str] = field(default_factory=list)


def _git(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True, check=False)


GitRunner = Callable[[Sequence[str], Path], "subprocess.CompletedProcess[str]"]


def _count(runner: GitRunner, cwd: Path, rev_range: str) -> int:
    res = runner(["rev-list", "--count", rev_range], cwd)
    if res.returncode != 0:
        return -1
    try:
        return int(res.stdout.strip())
    except ValueError:
        return -1


def _parse_dirty(porcelain: str) -> list[str]:
    out = []
    for line in porcelain.splitlines():
        if len(line) < 4 or line[:2] in ("??", "!!"):
            continue
        path = line[3:]
        if " -> " in path:           # rename: report new path
            path = path.split(" -> ", 1)[1]
        out.append(path.strip().strip('"'))
    return out


def sync_main(repo_root, *, branch="main", remote="origin",
              fetch=True, runner: GitRunner = _git) -> SyncResult:
    root = Path(repo_root)
    cur = runner(["rev-parse", "--abbrev-ref", "HEAD"], root)
    if cur.returncode != 0:
        return SyncResult(False, "error", f"git rev-parse failed: {cur.stderr.strip()}")
    if cur.stdout.strip() != branch:
        return SyncResult(True, "skipped-not-on-branch",
                          f"on '{cur.stdout.strip()}', not '{branch}' — no sync")
    if fetch:
        fr = runner(["fetch", remote, branch], root)
        if fr.returncode != 0:
            return SyncResult(False, "error", f"git fetch failed: {fr.stderr.strip()}")

    behind = _count(runner, root, f"{branch}..{remote}/{branch}")
    ahead = _count(runner, root, f"{remote}/{branch}..{branch}")
    if behind < 0 or ahead < 0:
        return SyncResult(False, "error", f"could not compare {branch} with {remote}/{branch}")
    from_sha = runner(["rev-parse", "--short", "HEAD"], root).stdout.strip()
    to_sha = runner(["rev-parse", "--short", f"{remote}/{branch}"], root).stdout.strip()

    if ahead > 0:
        status = "refused-diverged" if behind > 0 else "refused-ahead"
        return SyncResult(True, status,
                          f"{branch} ahead {ahead}/behind {behind} — refusing",
                          behind, ahead, from_sha, to_sha)
    if behind == 0:
        return SyncResult(True, "up-to-date",
                          f"{branch} already at {remote}/{branch} ({to_sha})",
                          behind, ahead, from_sha, to_sha)

    dirty = _parse_dirty(runner(["status", "--porcelain"], root).stdout)
    blocking = [p for p in dirty if p not in GENERATED_ALLOWLIST]
    if blocking:
        return SyncResult(True, "refused-dirty",
                          f"STALE BASE: '{branch}' is {behind} commit(s) behind "
                          f"{remote}/{branch} and cannot fast-forward — local "
                          f"tracked changes block it: {', '.join(blocking)}.",
                          behind, ahead, from_sha, to_sha, dirty=dirty)

    stashed = bool(dirty)  # only allowlisted generated paths remain
    if stashed:
        st = runner(["stash", "push", "--", *dirty], root)
        if st.returncode != 0:
            return SyncResult(False, "error", f"stash failed: {st.stderr.strip()}")
    ff = runner(["merge", "--ff-only", f"{remote}/{branch}"], root)
    if ff.returncode != 0:
        if stashed:
            runner(["stash", "pop"], root)  # best-effort restore before bailing
        return SyncResult(False, "error", f"merge --ff-only failed: {ff.stderr.strip()}")
    new_sha = runner(["rev-parse", "--short", "HEAD"], root).stdout.strip()
    if stashed:
        pop = runner(["stash", "pop"], root)
        if pop.returncode != 0:
            return SyncResult(True, "fast-forwarded",
                              f"{branch} {from_sha} -> {new_sha} (generated file left in stash)",
                              behind, ahead, from_sha, new_sha, dirty=dirty)
    return SyncResult(True, "fast-forwarded",
                      f"{branch} {from_sha} -> {new_sha} (+{behind})",
                      behind, ahead, from_sha, new_sha)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    result = sync_main(args[0] if args else ".")
    if result.status == "refused-dirty" and result.behind > 0:
        bar = "!" * 72
        print(bar); print(f"WARNING  sync_main: {result.detail}"); print(bar)
    else:
        print(f"sync_main: {result.status} — {result.detail}")
    return 1 if result.status == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Adaptation Notes

- **Populate `GENERATED_ALLOWLIST`** with your repo's perpetually-dirty,
  machine-generated tracked files (caches, append-only logs, generated indexes).
  Anything NOT on it that is dirty correctly aborts the sync — that is the
  no-clobber guarantee.
- **The result taxonomy is the value** — keep `ok=False` reserved for hard git
  errors and let every refusal stay `ok=True` exit-0. Callers (session-start
  hooks, pre-work checks) depend on a refusal not breaking them.
- **Inject `runner`** so unit tests can drive the state machine (behind / ahead /
  diverged / dirty / clean-ff) with a fake git, no temp repo required.
- Generalize beyond `main`: the `branch`/`remote` params let it fast-forward any
  tracked branch. Keep the on-branch guard so it never moves a branch you are not
  standing on.
- The loud refused-while-behind banner exists because a one-line stale-base
  warning was once missed and superseded work was nearly pushed. Keep it loud.
