# Generic Lib Prompt: Embedded Sub-Repo Staleness Guard + Safe Fast-Forward

## Purpose

When a parent repository `.gitignore`s a set of **child repositories** that live
as independent clones beneath it, those clones drift: one ends up parked on an
old branch, another sits hundreds of commits behind its own `origin/main`. A
stale child clone is a silent root cause of wrong conclusions (an agent reading
the on-disk child config reads the past) and of pre-push checks that test stale
state.

This guard inspects every present child clone against its own `origin/main` and,
optionally, **safely fast-forwards** the ones it is safe to. It NEVER force-
discards local work — anything ambiguous is FLAGGED for a human decision and left
exactly as it is. It is the children's analogue of a parent-`main`
fast-forward helper, applying the same safety stance.

## Reusable Pattern

- **Inspect-only by default; `--refresh` opts into mutation.** The check path
  mutates nothing.
- **Fast-forward ONLY when unambiguous and safe:** the child is on `main`,
  strictly behind (`behind > 0 and ahead == 0`), and has a clean working tree.
  Delegate the actual ff to a shared safe-ff primitive (`--ff-only`, with any
  generated-file stashing) so "what is dirty / how to ff" has one implementation.
- **There is no force path.** A feature-branch checkout, a dirty tree, or a
  divergence is flagged, never touched.
- **`behind`/`ahead` measured from `HEAD` vs `origin/main`** (not from local
  `main`), so a child parked on an old branch still reports its true mainline
  staleness — that *is* the signal.
- **A flag is a SAFE outcome → exit 0.** Wiring this into session-start must never
  break on a "can't refresh right now" state. Exit non-zero only on internal
  plumbing failure.
- **Machine-readable status enum** drives both the report and the FLAGGED block.

## Algorithm

Per child:

1. No `.git` on disk → `absent` (nothing to do).
2. `git fetch origin main`; failure → `error`.
3. Resolve branch; count `behind = HEAD..origin/main`, `ahead = origin/main..HEAD`.
4. `ahead > 0` → `diverged` (also behind) or `ahead`; left as-is.
5. `behind == 0` → `current`.
6. From here `behind > 0, ahead == 0`:
   - dirty tree → `dirty` (flag, never discard);
   - not on `main` → `stale-feature-branch` (flag);
   - on `main`, clean, no `--refresh` → `stale-on-main` (refreshable);
   - on `main`, clean, `--refresh` → delegate safe ff → `fast-forwarded`.
7. Render a per-child report plus a FLAGGED block for statuses needing a human.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Refresh + staleness guard for a parent's embedded child-repo checkouts.

Default: report per-child status, mutate nothing. --refresh: additionally
fast-forward the clean-on-main-behind children. Flags (never forces) anything
ambiguous. Exit 0 unless internal plumbing fails.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The set of child repo subdir names lives in ONE place (mirror your repo map).
CHILD_REPOS: tuple[str, ...] = ("child-a", "child-b", "child-c")

_ATTENTION = frozenset({"stale-on-main", "stale-feature-branch", "dirty",
                        "diverged", "ahead", "error"})


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True, check=False)


def _count(cwd: Path, rng: str) -> int:
    r = _git(["rev-list", "--count", rng], cwd)
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else -1


@dataclass
class ChildStatus:
    repo: str
    status: str
    branch: str = ""
    behind: int = 0
    ahead: int = 0
    detail: str = ""

    @property
    def needs_attention(self) -> bool:
        return self.status in _ATTENTION


def check_child(repo_root: Path, child: str, *, refresh: bool = False,
                remote: str = "origin") -> ChildStatus:
    root = repo_root / child
    if not (root / ".git").exists():
        return ChildStatus(child, "absent", detail="no clone on disk")
    if _git(["fetch", remote, "main"], root).returncode != 0:
        return ChildStatus(child, "error", detail="git fetch failed")
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], root).stdout.strip()
    ref = f"{remote}/main"
    behind, ahead = _count(root, f"HEAD..{ref}"), _count(root, f"{ref}..HEAD")
    if behind < 0 or ahead < 0:
        return ChildStatus(child, "error", branch, detail="compare failed")
    dirty = bool(_git(["status", "--porcelain"], root).stdout.strip())
    if ahead > 0:
        return ChildStatus(child, "diverged" if behind else "ahead", branch, behind, ahead,
                          "local commits — left as-is (no force)")
    if behind == 0:
        return ChildStatus(child, "current", branch, 0, 0, f"current with {ref}")
    if dirty:
        return ChildStatus(child, "dirty", branch, behind, 0,
                          "uncommitted changes block refresh — reconcile manually")
    if branch != "main":
        return ChildStatus(child, "stale-feature-branch", branch, behind, 0,
                          "parked off main — not refreshed")
    if not refresh:
        return ChildStatus(child, "stale-on-main", branch, behind, 0,
                          "clean & behind — run --refresh to fast-forward")
    ff = _git(["merge", "--ff-only", ref], root)
    if ff.returncode == 0:
        return ChildStatus(child, "fast-forwarded", "main", behind, 0, "fast-forwarded")
    return ChildStatus(child, "error", "main", behind, 0, "refresh failed")


def render(results: list[ChildStatus]) -> str:
    present = [r for r in results if r.status != "absent"]
    if not present:
        return "child-checkouts: no child clones on disk."
    lines = ["--- child-repo checkouts (vs origin/main) ---"]
    lines += [f"  {r.status:<20} {r.repo} :: {r.detail}" for r in present]
    flagged = [r for r in present if r.needs_attention]
    if flagged:
        lines.append("--- FLAGGED (manual decision; NOT refreshed) ---")
        lines += [f"  {r.status}  {r.repo} (behind {r.behind}, ahead {r.ahead})" for r in flagged]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    refresh = "--refresh" in args
    positional = [a for a in args if not a.startswith("--")]
    repo_root = Path(positional[0] if positional else ".")
    results = [check_child(repo_root, c, refresh=refresh) for c in CHILD_REPOS]
    print(render(results))
    return 1 if any(r.status == "error" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Adaptation Notes

- **List your child subdir names in one constant.** Keep it in sync with whatever
  iterates the same set elsewhere (e.g. a session-start worktree sweep).
- **Reuse a shared safe-ff primitive if you have one.** The template inlines a
  bare `merge --ff-only`; production code should delegate to the same helper your
  parent-`main` sync uses, so stashing of generated files and the dirtiness
  definition are not duplicated.
- **Keep exit 0 for every flagged state.** This is the property that lets you wire
  it into startup without it ever blocking a session. Only a genuine plumbing
  error should be non-zero.
- **Mainline branch name is a parameter.** Substitute `main`/`master`/`trunk` as
  your org uses.
```
