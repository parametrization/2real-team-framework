#!/usr/bin/env python3
"""Fast-forward the local default branch to its remote when provably safe.

Owner request (main#713): after any push/merge to ``origin/main``, the local
``main`` checkout should pick up the change *immediately* rather than silently
lag. A stale local ``main`` runs pre-fix hooks/skills off disk — this session
opened 22 commits behind origin and ran the pre-#709 session-start reader,
producing false orientation (phase/wave "unknown", a 2-of-8-repo scan).

This module is the deterministic, side-effect-guarded core. It fast-forwards
local ``branch`` to ``remote/branch`` ONLY when:

  * the checkout is currently on ``branch`` (never moves a feature branch),
  * local is strictly behind the remote (``behind > 0`` and ``ahead == 0`` —
    it never rewrites a divergence and never touches an already-current tree),
  * the working tree carries no real local modifications — tracked changes
    outside :data:`GENERATED_ALLOWLIST` abort the sync.

It NEVER force-updates, NEVER creates a merge commit (``--ff-only``), and NEVER
discards real local work. Machine-generated files (the annunaki error log, the
ontology checksums) are stashed around the fast-forward and restored, so a
perpetually-dirty generated file does not block the sync. Anything it cannot do
safely it reports and refuses (``ok=False``) rather than guessing.

CLI: ``python3 .claude/lib/sync_main.py [REPO_ROOT]`` — prints a one-line status
and exits non-zero on a hard failure (``status == "error"``). A refusal
(diverged/ahead/dirty) is a *safe* outcome and exits 0 with a diagnostic, so a
caller wiring this into a hook or session-start never breaks on a normal
"can't fast-forward right now" state.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Tracked, machine-generated files that are safe to stash around a fast-forward.
# They are perpetually dirty in an active session and would otherwise block
# every sync. Repo-root-relative POSIX paths.
#
#  * ``.claude/annunaki/errors.jsonl`` — append-only error log.
#  * ``ontology/checksums.json`` — rewritten by the ontology change-tracker
#    PostToolUse hook on every Edit/Write, so it is dirty in any session that
#    has touched a file (i.e. all of them). Unlike the append-only log it can
#    carry genuine pending resolutions, but the stash/pop restores its content;
#    if an incoming origin rewrite conflicts the pop, the ff still lands and the
#    stash is left for manual recovery (see the pop path below) — graceful, not
#    lossy.
GENERATED_ALLOWLIST: frozenset[str] = frozenset(
    {".claude/annunaki/errors.jsonl", "ontology/checksums.json"}
)


@dataclass
class SyncResult:
    """Outcome of a :func:`sync_main` call.

    ``ok`` is False only for a *hard* failure (git plumbing error). A refusal to
    fast-forward (diverged / ahead / real dirty tree) is a safe, expected state:
    ``ok`` stays True and ``status`` carries the machine-readable reason.
    """

    ok: bool
    status: str  # fast-forwarded | up-to-date | skipped-not-on-branch
    #            | refused-ahead | refused-diverged | refused-dirty | error
    detail: str
    behind: int = 0
    ahead: int = 0
    from_sha: str = ""
    to_sha: str = ""
    dirty: list[str] = field(default_factory=list)


def _git(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _count(runner: "GitRunner", cwd: Path, rev_range: str) -> int:
    res = runner(["rev-list", "--count", rev_range], cwd)
    if res.returncode != 0:
        return -1
    try:
        return int(res.stdout.strip())
    except ValueError:
        return -1


def _parse_dirty(porcelain: str) -> list[str]:
    """Return paths of *tracked* modifications in ``git status --porcelain``.

    Untracked (``??``) and ignored (``!!``) entries are excluded — they never
    block a fast-forward merge. Rename entries (``R  old -> new``) report the
    new path.
    """
    out: list[str] = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        if line[:2] in ("??", "!!"):
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        out.append(path.strip().strip('"'))
    return out


# Typing alias for the injected git runner (real git by default; a fake in tests
# only for the rare unit that does not want a real temp repo).
GitRunner = Callable[[Sequence[str], Path], "subprocess.CompletedProcess[str]"]


def sync_main(
    repo_root: str | Path,
    *,
    branch: str = "main",
    remote: str = "origin",
    fetch: bool = True,
    runner: GitRunner = _git,
) -> SyncResult:
    """Fast-forward ``branch`` to ``remote/branch`` when safe. See module docs."""
    root = Path(repo_root)

    cur = runner(["rev-parse", "--abbrev-ref", "HEAD"], root)
    if cur.returncode != 0:
        return SyncResult(False, "error", f"git rev-parse failed: {cur.stderr.strip()}")
    current_branch = cur.stdout.strip()
    if current_branch != branch:
        return SyncResult(
            True,
            "skipped-not-on-branch",
            f"on '{current_branch}', not '{branch}' — no sync",
        )

    if fetch:
        fres = runner(["fetch", remote, branch], root)
        if fres.returncode != 0:
            return SyncResult(
                False, "error", f"git fetch {remote} {branch} failed: {fres.stderr.strip()}"
            )

    behind = _count(runner, root, f"{branch}..{remote}/{branch}")
    ahead = _count(runner, root, f"{remote}/{branch}..{branch}")
    if behind < 0 or ahead < 0:
        return SyncResult(False, "error", f"could not compare {branch} with {remote}/{branch}")

    from_sha = runner(["rev-parse", "--short", "HEAD"], root).stdout.strip()
    to_sha = runner(["rev-parse", "--short", f"{remote}/{branch}"], root).stdout.strip()

    if ahead > 0:
        status = "refused-diverged" if behind > 0 else "refused-ahead"
        return SyncResult(
            True,
            status,
            f"{branch} ahead {ahead}/behind {behind} — refusing (no force/merge commit)",
            behind,
            ahead,
            from_sha,
            to_sha,
        )
    if behind == 0:
        return SyncResult(
            True,
            "up-to-date",
            f"{branch} already at {remote}/{branch} ({to_sha})",
            behind,
            ahead,
            from_sha,
            to_sha,
        )

    # behind > 0, ahead == 0 — a clean fast-forward is possible if the tree allows.
    dirty = _parse_dirty(runner(["status", "--porcelain"], root).stdout)
    blocking = [p for p in dirty if p not in GENERATED_ALLOWLIST]
    if blocking:
        # behind > 0 is guaranteed here (we are past the behind == 0 return), so
        # every refused-dirty is a STALE BASE: local main cannot pick up origin's
        # commits. Make the detail loud — behind-count + the blocking paths — so
        # the operator does not silently start main-targeting work off a stale
        # tree (main#822: a quiet single line was missed and a superseded
        # ontology rebuild was nearly pushed).
        return SyncResult(
            True,
            "refused-dirty",
            f"STALE BASE: '{branch}' is {behind} commit(s) behind {remote}/{branch} "
            f"and cannot fast-forward — local tracked changes block it: "
            f"{', '.join(blocking)}. Reconcile (commit/stash) before doing "
            f"{branch}-targeting work.",
            behind,
            ahead,
            from_sha,
            to_sha,
            dirty=dirty,
        )

    stashed = bool(dirty)  # only generated-allowlist paths remain
    if stashed:
        st = runner(["stash", "push", "--", *dirty], root)
        if st.returncode != 0:
            return SyncResult(
                False, "error", f"git stash of generated files failed: {st.stderr.strip()}"
            )

    ff = runner(["merge", "--ff-only", f"{remote}/{branch}"], root)
    if ff.returncode != 0:
        if stashed:
            runner(["stash", "pop"], root)  # best-effort restore before bailing
        return SyncResult(False, "error", f"git merge --ff-only failed: {ff.stderr.strip()}")

    new_sha = runner(["rev-parse", "--short", "HEAD"], root).stdout.strip()

    if stashed:
        pop = runner(["stash", "pop"], root)
        if pop.returncode != 0:
            # Fast-forward landed but the generated file could not be restored
            # cleanly (e.g. origin also changed it). Leave the stash for manual
            # recovery; the ff itself succeeded, which is the load-bearing part.
            return SyncResult(
                True,
                "fast-forwarded",
                f"{branch} {from_sha} -> {new_sha} (generated file left in stash)",
                behind,
                ahead,
                from_sha,
                new_sha,
                dirty=dirty,
            )

    return SyncResult(
        True,
        "fast-forwarded",
        f"{branch} {from_sha} -> {new_sha} (+{behind})",
        behind,
        ahead,
        from_sha,
        new_sha,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    repo_root = args[0] if args else "."
    result = sync_main(repo_root)
    if result.status == "refused-dirty" and result.behind > 0:
        # A refused ff while behind is a stale-base hazard — render it as a
        # multi-line banner so it stands out in session-start Step 0 output
        # rather than scrolling past as one quiet line (main#822).
        bar = "!" * 72
        print(bar)
        print(f"⚠  sync_main: {result.detail}")
        print(bar)
    else:
        print(f"sync_main: {result.status} — {result.detail}")
    return 1 if result.status == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
