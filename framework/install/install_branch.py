#!/usr/bin/env python3
"""Stage a framework install onto a throwaway git branch — trial an install, then merge or delete (#279).

The git-native sibling of ``restore.py``. Both answer "let me try this install and back out cleanly
if I don't like it", but from opposite ends:

* ``restore`` is the **git-independent** path: the install lands on your working tree, and ``restore``
  reverses the tracked file changes afterward via the reversible manifest (#108) + the ``.bak``
  backups the installer left. It needs no git and works in a dirty tree.
* ``install_branch`` (this module) is the **git-native** path: it creates a dedicated install branch
  off the current HEAD, runs the install there, and commits the whole install set as ONE commit on
  that branch. Undo is a git operation — you either ``git merge`` the branch when satisfied or
  ``git branch -D`` it to walk away, with zero manifest bookkeeping to reason about.

When to prefer which
====================
* Prefer **install-branch** when the target is a clean git repo and you want an all-or-nothing trial
  you can review as a single diff (``git diff <orig>..<branch>``) and accept or discard atomically.
* Prefer **restore** when you're in a non-git repo, your tree is dirty, or you've already installed
  onto your working branch and want to selectively undo the install's file changes.

How they COMPOSE (they do not conflict)
=======================================
install-branch does not replace or consume the manifest path — it wraps a git envelope AROUND the
very same install. The install action it runs is the ordinary bootstrapper, which still writes its
manifest + ``.bak`` backups; those artifacts are simply captured inside the branch commit. So on a
staged install branch BOTH undo routes remain available and independent:

* discard the whole trial  -> ``git branch -D <branch>`` (drops the install *and* its manifest), or
* selectively revert files  -> run ``restore`` on the branch (uses the captured manifest/``.bak``).

install-branch never deletes a manifest, and ``restore`` never touches a branch, so running one
cannot corrupt the other's state.

Degradation policy — REFUSE, don't silently fall back (deliberate design call)
==============================================================================
In a **non-git repo** there is no branch to create; in a **dirty working tree** staging onto a branch
cut from a dirty HEAD would fold the operator's own uncommitted work into the "install" commit,
breaking the clean merge/discard guarantee this mode exists to provide. In both cases we REFUSE with
an actionable message that points at the ``restore`` path (``install`` normally, then ``restore`` to
undo) rather than silently switching strategies: the two paths have different, non-substitutable
contracts, and a silent fall-back would surprise the operator and quietly void the "walk away clean"
promise. The choice is the operator's, made with full information.

Preview + consent (fail-safe, mirrors ``restore``)
==================================================
Every run first PRINTS the plan (git status, the branch it will create, whether it will leave you on
that branch). ``--dry-run`` stops there and creates nothing. A live run then asks an explicit
``[y/N]``; ``--non-interactive`` is the automation contract (proceed, no prompt); a non-TTY without
``--non-interactive`` REFUSES rather than mutating unattended. If the install action fails midway, the
branch is rolled back (checkout original, delete the branch) so the tree is left as it was found.

Stdlib only (no deps). The engine takes the install action as a callable so it stays git-only and
testable; the CLI wires that callable to the framework ``bootstrap.py`` (extra args pass through).

Usage
=====
  python3 install_branch.py /path/to/repo --owner my-org         # preview, [y/N], stage on a branch
  python3 install_branch.py /path/to/repo --owner my-org --non-interactive
  python3 install_branch.py /path/to/repo --dry-run              # preview only; create nothing
  python3 install_branch.py /path/to/repo --branch try/real-team # pick the install-branch name
  python3 install_branch.py /path/to/repo --return               # leave tree on the original branch

Exit codes: 0 ok / dry-run / staged, 1 on a refused run, a collision, or a failed install.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

#: The install branch created off the current HEAD unless ``--branch`` overrides it.
DEFAULT_BRANCH = "real-team/install"
#: Commit identity for the staged-install commit. Applied via per-commit ``-c`` flags (NEVER global
#: git config), so staging never mutates the operator's git identity — matches the charter rule.
_COMMIT_NAME = "2real-team installer"
_COMMIT_EMAIL = "noreply@2real-team.local"

#: An install action mutates the working tree in ``target``; it must raise on failure.
InstallAction = Callable[[Path], None]


# --------------------------------------------------------------------------------- git helpers


def _git(target: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run ``git -C <target> <args>`` capturing output; ``check`` raises on non-zero."""
    return subprocess.run(
        ["git", "-C", str(target), *args],
        capture_output=True, text=True, check=check,
    )


def is_git_repo(target: Path) -> bool:
    """True if ``target`` is inside a git work tree."""
    r = _git(target, "rev-parse", "--is-inside-work-tree")
    return r.returncode == 0 and r.stdout.strip() == "true"


def is_dirty(target: Path) -> bool:
    """True if the work tree has staged or unstaged changes (untracked files included)."""
    r = _git(target, "status", "--porcelain")
    return r.returncode == 0 and bool(r.stdout.strip())


def current_ref(target: Path) -> str | None:
    """The current branch name, or a short commit sha when HEAD is detached; None if unresolved."""
    r = _git(target, "symbolic-ref", "--quiet", "--short", "HEAD")
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    r = _git(target, "rev-parse", "--short", "HEAD")
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def branch_exists(target: Path, name: str) -> bool:
    """True if a local branch ``name`` already exists (a collision we refuse to clobber)."""
    return _git(target, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}").returncode == 0


# --------------------------------------------------------------------------------- plan model


@dataclass
class StagePlan:
    """What a stage would do, resolved BEFORE any mutation (drives the preview + the guard)."""

    target: Path
    git_ok: bool
    dirty: bool
    branch: str
    original_ref: str | None
    branch_collision: bool

    @property
    def can_stage(self) -> bool:
        return self.git_ok and not self.dirty and not self.branch_collision

    @property
    def blocker(self) -> str | None:
        """Actionable reason a live stage is refused, or None when it can proceed."""
        if not self.git_ok:
            return (
                f"{self.target} is not a git repository — there is no branch to stage onto.\n"
                "  Use a plain install and `restore` to undo it (the git-independent path)."
            )
        if self.dirty:
            return (
                "the working tree has uncommitted changes — staging onto a branch cut from a "
                "dirty HEAD would fold them into the install commit.\n"
                "  Commit or stash them first, or use a plain install and `restore` to undo it."
            )
        if self.branch_collision:
            return (
                f"branch '{self.branch}' already exists — refusing to reuse or clobber it.\n"
                f"  Delete it (git branch -D {self.branch}) or pass --branch <name>."
            )
        return None


@dataclass
class StageReport:
    """Outcome of :func:`stage_install`."""

    staged: bool = False
    branch: str | None = None
    original_ref: str | None = None
    commit: str | None = None
    on_branch: bool = False  #: True if the tree is left checked out on the install branch
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------- planning


def plan_stage(target: Path | str, *, branch: str | None = None) -> StagePlan:
    """Resolve the stage plan for ``target`` without mutating anything."""
    target = Path(target).resolve()
    git_ok = is_git_repo(target)
    name = branch or DEFAULT_BRANCH
    return StagePlan(
        target=target,
        git_ok=git_ok,
        dirty=is_dirty(target) if git_ok else False,
        branch=name,
        original_ref=current_ref(target) if git_ok else None,
        branch_collision=branch_exists(target, name) if git_ok else False,
    )


# --------------------------------------------------------------------------------- apply


def stage_install(
    target: Path | str,
    install_action: InstallAction,
    *,
    branch: str | None = None,
    dry_run: bool = False,
    non_interactive: bool = False,
    keep_checkout: bool = True,
) -> StageReport:
    """Create an install branch off HEAD, run ``install_action`` there, and commit the result.

    Returns a :class:`StageReport`. On any refusal (non-git, dirty tree, branch collision, declined
    consent) nothing is created and ``staged`` is False. On a live run the branch is created and
    switched to, ``install_action`` mutates the tree, everything is committed as one commit, and —
    unless ``keep_checkout`` is False — the tree is left on the install branch for the operator to
    try. If ``install_action`` raises, the branch is rolled back (checkout original, delete branch)
    so the tree is left as found, and the error propagates. ``dry_run`` creates nothing.
    """
    target = Path(target).resolve()
    plan = plan_stage(target, branch=branch)
    report = StageReport(branch=plan.branch, original_ref=plan.original_ref)

    if not plan.can_stage:
        report.notes.append(plan.blocker or "cannot stage")
        return report
    if dry_run:
        report.notes.append(f"dry-run — would create branch '{plan.branch}' and stage the install")
        return report

    orig = plan.original_ref
    if orig is None:  # unresolved HEAD (broken repo) — nothing to branch from / return to
        report.notes.append("cannot resolve the current HEAD to branch from — commit first.")
        return report
    if _git(target, "checkout", "-b", plan.branch).returncode != 0:
        report.notes.append(f"failed to create branch '{plan.branch}'")
        return report

    try:
        install_action(target)
    except Exception:
        _rollback(target, orig, plan.branch)
        raise

    _git(target, "add", "-A")
    if _git(target, "diff", "--cached", "--quiet").returncode == 0:
        # The install produced no changes — don't leave a dangling empty branch behind.
        _rollback(target, orig, plan.branch)
        report.notes.append("install produced no changes; install branch removed (nothing to try).")
        return report

    msg = f"chore(install): stage 2real-team framework install on {plan.branch}"
    commit = _git(
        target,
        "-c", f"user.name={_COMMIT_NAME}",
        "-c", f"user.email={_COMMIT_EMAIL}",
        "commit", "-m", msg,
    )
    if commit.returncode != 0:
        _rollback(target, orig, plan.branch)
        report.notes.append(f"failed to commit the staged install: {commit.stderr.strip()}")
        return report

    head = _git(target, "rev-parse", "--short", "HEAD")
    report.commit = head.stdout.strip() or None
    report.staged = True

    if keep_checkout:
        report.on_branch = True
    else:
        _git(target, "checkout", orig)
        report.on_branch = False
    return report


def _rollback(target: Path, original_ref: str, branch: str) -> None:
    """Best-effort undo of a partial stage: return to ``original_ref`` and delete ``branch``.

    Safe to ``git clean -fd`` the untracked debris a half-run install left: we only stage from a
    verified-clean tree (a dirty tree is refused upfront), so anything untracked here is install
    output, never the operator's own work.
    """
    _git(target, "checkout", "--force", original_ref)
    _git(target, "clean", "-fd")
    _git(target, "branch", "-D", branch)


# --------------------------------------------------------------------------------- CLI plumbing


def _confirm(plan: StagePlan, *, non_interactive: bool) -> bool:
    """Consent gate for the live stage — mirrors ``restore``'s automation contract.

    ``--non-interactive`` proceeds without prompting (automation); an interactive TTY is asked
    ``[y/N]``; a non-TTY without ``--non-interactive`` REFUSES rather than mutating unattended.
    """
    if non_interactive:
        return True
    if not sys.stdin.isatty():
        print(
            "refusing to create an install branch without a TTY — pass --non-interactive to proceed.",
            file=sys.stderr,
        )
        return False
    ans = input(f"Stage the install onto branch '{plan.branch}'? [y/N]: ").strip().lower()
    return ans in ("y", "yes")


def _print_plan(plan: StagePlan, *, dry_run: bool) -> None:
    print("\n-- plan --")
    if not plan.git_ok:
        print("git repo:      no")
        return
    print(f"git repo:      yes (on {plan.original_ref})")
    print(f"working tree:  {'dirty' if plan.dirty else 'clean'}")
    verb = "would create" if dry_run else "will create"
    print(f"install branch: {verb} '{plan.branch}'"
          + ("  [ALREADY EXISTS]" if plan.branch_collision else ""))


def _print_report(report: StageReport) -> None:
    print("\n-- result --")
    if not report.staged:
        for note in report.notes:
            print(f"note: {note}")
        return
    b, orig = report.branch, report.original_ref
    print(f"staged install on branch '{b}' (commit {report.commit}).")
    if report.on_branch:
        print(f"you are on '{b}' now — try it out, then:")
        print(f"  keep it:    git checkout {orig} && git merge {b}")
        print(f"  discard it: git checkout {orig} && git branch -D {b}")
    else:
        print(f"your tree is back on '{orig}' (clean); the install is parked on '{b}'.")
        print(f"  review it:  git diff {orig}..{b}")
        print(f"  keep it:    git merge {b}")
        print(f"  discard it: git branch -D {b}")
    for note in report.notes:
        print(f"note: {note}")


def cli_stage(
    target: Path | str,
    install_action: InstallAction,
    *,
    branch: str | None,
    dry_run: bool,
    non_interactive: bool,
    keep_checkout: bool,
) -> int:
    """Product entry: preview -> consent -> stage. Shared by the CLI and the ``2real-team`` bridge."""
    target = Path(target).resolve()
    print(f"== 2real framework install-branch ({'DRY-RUN' if dry_run else 'STAGE'}) ==")
    print(f"target repo:   {target}")

    plan = plan_stage(target, branch=branch)
    _print_plan(plan, dry_run=dry_run)

    if not plan.can_stage:
        print(f"\nrefusing to stage: {plan.blocker}", file=sys.stderr)
        return 1
    if dry_run:
        print("\n(dry-run — nothing was created)")
        return 0
    if not _confirm(plan, non_interactive=non_interactive):
        print("aborted — nothing created.", file=sys.stderr)
        return 1

    try:
        report = stage_install(
            target, install_action, branch=branch, dry_run=False,
            non_interactive=non_interactive, keep_checkout=keep_checkout,
        )
    except Exception as exc:
        # The engine already rolled the branch back before re-raising; report cleanly, don't dump
        # a traceback at the operator.
        print(f"\ninstall failed — branch '{plan.branch}' rolled back, tree left as found.\n"
              f"  {exc}", file=sys.stderr)
        return 1
    _print_report(report)
    return 0 if report.staged else 1


def _bootstrap_action(passthrough: Sequence[str]) -> InstallAction:
    """Build the default install action: run the framework ``bootstrap.py`` in ``--non-interactive``.

    Extra CLI args (``--owner``, ``--model``, …) pass straight through to the bootstrapper. Runs
    inside the already-checked-out install branch, so its writes land there. Raises on a non-zero
    bootstrap exit so :func:`stage_install` rolls the branch back.
    """
    def _action(target: Path) -> None:
        cmd = [
            sys.executable, str(Path(__file__).resolve().parent / "bootstrap.py"),
            str(target), "--non-interactive", *passthrough,
        ]
        proc = subprocess.run(cmd, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"framework bootstrap failed (exit {proc.returncode})")

    return _action


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Stage a framework install onto a throwaway git branch so you can merge it when "
        "satisfied or `git branch -D` to walk away clean (#279). The git-native sibling of "
        "restore.py; refuses in a non-git repo or dirty tree (use install + restore there). "
        "Unrecognized args pass through to bootstrap.py.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("target", nargs="?", default=".", help="Target repo root (default: cwd)")
    ap.add_argument("--branch", default=None,
                    help=f"Install branch name to create (default: {DEFAULT_BRANCH})")
    ap.add_argument("--dry-run", action="store_true", help="Print the plan; create nothing")
    ap.add_argument("--non-interactive", action="store_true",
                    help="Never prompt (the automation contract); proceed without [y/N]")
    ap.add_argument("--return", dest="return_to_original", action="store_true",
                    help="After staging, check the original branch back out (tree left clean; "
                         "install parked on the branch) instead of staying on the install branch")
    args, passthrough = ap.parse_known_args(argv)

    return cli_stage(
        Path(args.target),
        _bootstrap_action(passthrough),
        branch=args.branch,
        dry_run=args.dry_run,
        non_interactive=args.non_interactive,
        keep_checkout=not args.return_to_original,
    )


if __name__ == "__main__":
    raise SystemExit(main())
