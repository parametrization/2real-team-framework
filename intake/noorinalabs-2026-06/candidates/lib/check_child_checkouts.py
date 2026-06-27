#!/usr/bin/env python3
"""Refresh + staleness guard for the parent's embedded child-repo checkouts.

The parent ``noorinalabs-main`` checkout ``.gitignore``s the child repos, which
live as independent clones under ``$REPO_ROOT/noorinalabs-<name>``. They drift:
during p6-wave-16 ``noorinalabs-user-service`` was parked on a *phase-3* commit
and ``noorinalabs-isnad-graph`` sat ~207 commits behind ``origin/main`` (main#832).
A stale child clone is the root cause of #816 (the parent pre-push test reads the
stale on-disk child configs) and makes any agent that reads a child clone directly
draw wrong conclusions.

This is the sibling to :mod:`sync_main` (the parent ``main`` fast-forward, #713)
for the *children*. It applies the **same safety stance**:

  * It fast-forwards a child to ``origin/main`` ONLY when that child is currently
    on ``main``, is strictly behind (``behind > 0`` and ``ahead == 0``), and has a
    clean working tree (the ff is delegated to :func:`sync_main.sync_main`, which
    stashes the machine-generated allowlist around the merge).
  * It NEVER force-discards local work: a child parked on a feature branch, a
    dirty tree, or a divergence is **FLAGGED for a manual decision** and left
    exactly as it is. There is no force path.

``behind``/``ahead`` are always measured against the child's own ``origin/main``
from ``HEAD`` (not from ``main``), so a child parked on an old feature branch
still reports how far behind the mainline it really is — that is the staleness
signal the guard exists to surface.

CLI: ``python3 .claude/lib/check_child_checkouts.py [REPO_ROOT] [--refresh]``

  * default (guard/check): reports per-child status, mutates nothing.
  * ``--refresh``: additionally fast-forwards the clean-on-main-behind children.

Either way it prints a per-child report plus a FLAGGED block for the children
needing a manual call, and exits 0 (a refusal/flag is a *safe* outcome — wiring
this into session-start must never break on a "can't refresh right now" state).
Exit is non-zero only on an internal plumbing error.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

# Reuse the deterministic git primitives + safe fast-forward from sync_main so
# the two guards share one implementation of "what is dirty" / "how to ff".
from sync_main import (
    GitRunner,
    SyncResult,
    _count,
    _git,
    _parse_dirty,
)
from sync_main import (
    sync_main as _sync_branch,
)

# The 7 canonical child repos (CLAUDE.md Repository Map). Kept in sync with the
# session-start Step 0 worktree iteration list.
CHILD_REPOS: tuple[str, ...] = (
    "noorinalabs-isnad-graph",
    "noorinalabs-user-service",
    "noorinalabs-deploy",
    "noorinalabs-design-system",
    "noorinalabs-data-acquisition",
    "noorinalabs-isnad-ingest-platform",
    "noorinalabs-landing-page",
)

# Statuses that need a human call (the FLAGGED block). Everything else
# (current / fast-forwarded / absent) is a clean outcome.
_ATTENTION = frozenset(
    {"stale-on-main", "stale-feature-branch", "dirty", "diverged", "ahead", "error"}
)


@dataclass
class ChildStatus:
    """Outcome of inspecting (and optionally refreshing) one child checkout.

    ``behind``/``ahead`` are HEAD-relative to the child's ``origin/main``.
    ``status`` is machine-readable:

      * ``absent``               — no clone on disk (not flagged; nothing to do)
      * ``current``              — on main, clean, up-to-date with origin/main
      * ``fast-forwarded``       — was stale-on-main-clean; refreshed this run
      * ``stale-on-main``        — on main, clean, behind; refreshable (run --refresh)
      * ``stale-feature-branch`` — parked off main and behind origin/main
      * ``dirty``                — uncommitted tracked changes while behind
      * ``diverged``             — local commits AND behind origin/main
      * ``ahead``                — local commits ahead of origin/main, not behind
      * ``error``                — git plumbing failed for this child
    """

    repo: str
    status: str
    branch: str = ""
    behind: int = 0
    ahead: int = 0
    dirty: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def needs_attention(self) -> bool:
        return self.status in _ATTENTION


def _branch_of(root: Path, runner: GitRunner) -> str:
    res = runner(["rev-parse", "--abbrev-ref", "HEAD"], root)
    return res.stdout.strip() if res.returncode == 0 else ""


def check_child(
    repo_root: str | Path,
    child: str,
    *,
    refresh: bool = False,
    remote: str = "origin",
    fetch: bool = True,
    runner: GitRunner = _git,
) -> ChildStatus:
    """Inspect (and, with ``refresh=True``, safely fast-forward) one child."""
    child_root = Path(repo_root) / child
    if not (child_root / ".git").exists():
        return ChildStatus(child, "absent", detail="no clone on disk")

    if fetch:
        fres = runner(["fetch", remote, "main"], child_root)
        if fres.returncode != 0:
            return ChildStatus(
                child, "error", detail=f"git fetch {remote} main failed: {fres.stderr.strip()}"
            )

    branch = _branch_of(child_root, runner)
    if not branch:
        return ChildStatus(child, "error", detail="could not resolve current branch")

    ref = f"{remote}/main"
    behind = _count(runner, child_root, f"HEAD..{ref}")
    ahead = _count(runner, child_root, f"{ref}..HEAD")
    if behind < 0 or ahead < 0:
        return ChildStatus(
            child, "error", branch=branch, detail=f"could not compare HEAD with {ref}"
        )

    dirty = _parse_dirty(runner(["status", "--porcelain"], child_root).stdout)
    on_main = branch == "main"

    # ---- divergence / ahead (local commits) — never touched ----------------
    if ahead > 0:
        status = "diverged" if behind > 0 else "ahead"
        detail = (
            f"on '{branch}', {ahead} local commit(s) ahead / {behind} behind {ref} "
            f"— left as-is (no force)"
        )
        return ChildStatus(child, status, branch, behind, ahead, dirty, detail)

    # ---- up to date with mainline -----------------------------------------
    if behind == 0:
        note = f" ({len(dirty)} uncommitted change(s))" if dirty else ""
        return ChildStatus(
            child, "current", branch, 0, 0, dirty, f"on '{branch}', current with {ref}{note}"
        )

    # behind > 0, ahead == 0 from here on.

    # ---- dirty tree blocks a refresh — flag, never discard -----------------
    if dirty:
        return ChildStatus(
            child,
            "dirty",
            branch,
            behind,
            0,
            dirty,
            f"on '{branch}', {behind} behind {ref} but {len(dirty)} uncommitted "
            f"tracked change(s) block refresh: {', '.join(dirty)}. Reconcile manually.",
        )

    # ---- parked on an old feature branch — flag, never touch ---------------
    if not on_main:
        return ChildStatus(
            child,
            "stale-feature-branch",
            branch,
            behind,
            0,
            [],
            f"parked on '{branch}', {behind} behind {ref} — genuine local branch, "
            f"not refreshed (checkout main + pull manually if intended)",
        )

    # ---- clean, on main, strictly behind: refreshable ----------------------
    if not refresh:
        return ChildStatus(
            child,
            "stale-on-main",
            branch,
            behind,
            0,
            [],
            f"on 'main', clean, {behind} behind {ref} — refreshable "
            f"(run with --refresh to fast-forward)",
        )

    # refresh requested: delegate the actual ff to sync_main (handles the
    # generated-file stash + --ff-only safety). fetch already done above.
    res: SyncResult = _sync_branch(
        child_root, branch="main", remote=remote, fetch=False, runner=runner
    )
    if res.status == "fast-forwarded":
        return ChildStatus(child, "fast-forwarded", "main", behind, 0, [], f"main {res.detail}")
    if res.status == "up-to-date":
        # Raced to current between our count and the ff (benign).
        return ChildStatus(child, "current", "main", 0, 0, [], f"main {res.detail}")
    # Any sync_main refusal/error: surface it without forcing.
    return ChildStatus(child, "error", "main", behind, 0, [], f"refresh failed: {res.detail}")


def check_all(
    repo_root: str | Path,
    *,
    refresh: bool = False,
    children: Sequence[str] = CHILD_REPOS,
    runner: GitRunner = _git,
) -> list[ChildStatus]:
    """Inspect every present child checkout under ``repo_root``."""
    return [check_child(repo_root, c, refresh=refresh, runner=runner) for c in children]


def render(results: Sequence[ChildStatus]) -> str:
    """Render a per-child report + a FLAGGED block for the ones needing a call."""
    present = [r for r in results if r.status != "absent"]
    if not present:
        return "child-checkouts: no child clones on disk."
    lines: list[str] = ["--- child-repo checkouts (vs origin/main) ---"]
    for r in present:
        lines.append(f"  {r.status:<20} {r.repo} :: {r.detail}")
    flagged = [r for r in present if r.needs_attention]
    if flagged:
        lines.append("--- FLAGGED child checkouts (manual decision; NOT refreshed) ---")
        for r in flagged:
            lines.append(f"  {r.status}  {r.repo} (behind {r.behind}, ahead {r.ahead})")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    refresh = "--refresh" in args
    positional = [a for a in args if not a.startswith("--")]
    repo_root = positional[0] if positional else "."

    results = check_all(repo_root, refresh=refresh)
    print(render(results))

    # Internal plumbing failure is the only non-zero exit. A flagged child
    # (dirty/diverged/feature-branch/stale) is a SAFE outcome — exit 0 so a
    # session-start caller never breaks on a "can't refresh right now" state.
    return 1 if any(r.status == "error" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
