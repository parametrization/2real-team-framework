#!/usr/bin/env python3
"""Restore a repo's pre-install originals — undo the files an install displaced/overwrote (#265/#273).

Sibling to ``uninstall.py``, but a DIFFERENT contract. Where ``uninstall`` tears out the whole
framework install set (hooks/lib/skills/config + charter + team artifacts + the managed
``.gitignore``/``settings.json`` wiring) and, as a side effect, restores any archived originals,
``restore`` does exactly one thing: **recover the operator's own pre-existing files that an
install touched**, driven by the reversible manifest (#108) and the install's ``.bak`` backups. It
does NOT remove the framework's net-new files — use ``uninstall`` for a full teardown.

Two directions, both driven by what the installer recorded
==========================================================
An install touches a pre-existing file in one of two reversible ways, and ``restore`` reverses
each from the exact artifact the installer left behind:

* **moved / backed-up** — in the consented *archive* disposition (#108) the whole pre-existing
  ``.claude/`` + ``CLAUDE.md`` are MOVED into ``.claude-backups/<UTC>/`` alongside a restore
  manifest (``archive-manifest.json``). ``restore`` moves them back byte-identical via
  :func:`repo_space.restore_assets` (``overwrite=True``, since a fresh install now sits at the
  target). This is the reversible-manifest path.
* **modified** — where the installer rewrote a file in place it first renamed the operator's
  original to a non-clobbering ``.bak`` sibling (the root ``CLAUDE.md`` → ``CLAUDE.md.bak`` in the
  team-CLI path, and the git ``pre-push`` → ``pre-push.bak`` in the framework bootstrapper).
  ``restore`` moves each ``.bak`` back over the current file, reverting the modification.

Contract boundary — what ``restore`` deliberately is NOT
========================================================
* NOT a git-level pristine reset. It reverses only the install's tracked changes to files it
  actually displaced/overwrote — it never touches untracked edits, other working-tree state, or
  git history. Recovering a globally pristine tree is git's job (``git checkout``/``stash``), not
  this command's.
* NOT the framework teardown. In-place *merges* with no ``.bak`` original (the ``.gitignore``
  managed block, the ``settings.json`` hook wiring) are un-merged structurally by ``uninstall``,
  not here — ``restore`` is scoped to the backup/manifest-recoverable originals only.

Preview + consent (fail-safe)
=============================
Every run first PRINTS the exact plan (what will be restored + what will be reverted) before any
mutation. ``--dry-run`` stops there and writes nothing. A live run then asks an explicit ``[y/N]``
confirmation; ``--non-interactive`` is the automation contract (proceed, no prompt); a non-TTY
without ``--non-interactive`` REFUSES rather than mutating unattended. A repo with nothing to
recover is a clean no-op (exit 0).

Stdlib only (no deps). Reuses ``repo_space`` (archive format + restore) and ``bootstrap`` (the
git-hooks-dir resolver) so the restore set cannot drift from what the install wrote.

Usage
=====
  python3 restore.py /path/to/repo                 # preview, confirm [y/N], then restore
  python3 restore.py /path/to/repo --non-interactive
  python3 restore.py /path/to/repo --dry-run       # preview only; write nothing

Exit codes: 0 ok / dry-run / nothing-to-do, 1 on a refused run or an unresolved conflict.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap  # noqa: E402  (sibling; the git-hooks-dir resolver, so we can't drift)
import repo_space  # noqa: E402  (sibling; archive format + consented restore, #108)

#: Root file the team-CLI install rewrites, preserving the original as ``CLAUDE.md.bak``.
_CLAUDE_MD = "CLAUDE.md"
#: git hook the framework bootstrapper rewrites, preserving the original as ``pre-push.bak``.
_PRE_PUSH = "pre-push"
#: The single, non-suffixed backup names that hold the true PRE-INSTALL original. Later suffixed
#: backups (``.bak.1`` …) captured a subsequent install's own output, not the operator's original,
#: so they are intentionally NOT restored.
_BACKUP_SUFFIX = ".bak"


# --------------------------------------------------------------------------------- plan model


@dataclass
class BakRevert:
    """A modified file to revert: move ``backup`` (the pre-install original) back over ``target``."""

    target_rel: str  #: repo-root-relative POSIX path of the file to put back
    backup: Path  #: absolute path of the ``.bak`` sibling holding the original
    target: Path  #: absolute path of the current file to overwrite


@dataclass
class RestorePlan:
    """What a restore would do, resolved BEFORE any mutation (drives the preview + the apply)."""

    archive_dir: Path | None = None
    archived: list[str] = field(default_factory=list)  #: manifest members present in the archive
    reverts: list[BakRevert] = field(default_factory=list)  #: ``.bak`` originals to move back

    @property
    def is_empty(self) -> bool:
        return not self.archived and not self.reverts


@dataclass
class RestoreReport:
    """Outcome of :func:`apply_restore`."""

    restored: list[str] = field(default_factory=list)  #: archived members moved back
    reverted: list[str] = field(default_factory=list)  #: modified files reverted from ``.bak``
    conflicts: list[str] = field(default_factory=list)  #: archived members left in place
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------------------- discovery


def _discover_bak_reverts(target: Path) -> list[BakRevert]:
    """Find the install's ``.bak`` originals for the files it rewrites in place.

    Deliberately scoped to the two files an install is known to displace — the root ``CLAUDE.md``
    and the git ``pre-push`` hook — matched by the exact, non-suffixed ``.bak`` name the installer
    writes for the FIRST (pre-install) original. It does not sweep for arbitrary ``*.bak`` (which
    could be the operator's own unrelated backups). A ``.bak`` with no current target still counts:
    the original is moved back into place regardless.
    """
    reverts: list[BakRevert] = []

    claude_bak = target / f"{_CLAUDE_MD}{_BACKUP_SUFFIX}"
    if claude_bak.is_file():
        reverts.append(
            BakRevert(target_rel=_CLAUDE_MD, backup=claude_bak, target=target / _CLAUDE_MD)
        )

    hooks_dir, _note = bootstrap._git_hooks_dir(target)
    if hooks_dir is not None:
        pp_bak = hooks_dir / f"{_PRE_PUSH}{_BACKUP_SUFFIX}"
        if pp_bak.is_file():
            rel = pp_bak.with_name(_PRE_PUSH)
            try:
                target_rel = rel.relative_to(target).as_posix()
            except ValueError:
                target_rel = str(rel)  # hooks dir outside the repo (core.hooksPath) — show abs
            reverts.append(BakRevert(target_rel=target_rel, backup=pp_bak, target=rel))

    return reverts


def _archived_members(archive_dir: Path) -> list[str]:
    """Manifest members that are actually present in ``archive_dir`` (restorable now)."""
    try:
        manifest = json.loads((archive_dir / repo_space.MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [
        entry["name"]
        for entry in manifest.get("entries", [])
        if isinstance(entry, dict) and "name" in entry and (archive_dir / entry["name"]).exists()
    ]


def plan_restore(target: Path | str) -> RestorePlan:
    """Resolve the full restore plan for ``target`` without mutating anything."""
    target = Path(target).resolve()
    archive_dir = repo_space.find_latest_archive(target)
    archived = _archived_members(archive_dir) if archive_dir is not None else []
    return RestorePlan(
        archive_dir=archive_dir,
        archived=archived,
        reverts=_discover_bak_reverts(target),
    )


# ----------------------------------------------------------------------------------- apply


def apply_restore(target: Path | str, plan: RestorePlan, *, dry_run: bool = False) -> RestoreReport:
    """Execute ``plan``. Restores archived originals first, then reverts ``.bak`` modifications.

    Archived members are moved back with ``overwrite=True`` (a fresh install sits at the target);
    on a clean restore the spent manifest is consumed and the emptied archive dir pruned so no
    stale backup lingers. A member already present and NOT overwritable is reported as a conflict.
    Each ``.bak`` original is then moved back over its current file. ``dry_run`` computes nothing
    destructive — it just echoes the plan as the report.
    """
    target = Path(target).resolve()
    report = RestoreReport()

    if plan.archive_dir is not None and plan.archived:
        if dry_run:
            report.restored.extend(plan.archived)
        else:
            res = repo_space.restore_assets(target, plan.archive_dir, overwrite=True)
            report.restored.extend(res.restored)
            report.conflicts.extend(res.conflicts)
            if not res.conflicts:
                # Clean restore — consume the now-spent manifest and prune the emptied archive dir
                # (repo_space deliberately leaves the container; #149 finding 4).
                (plan.archive_dir / repo_space.MANIFEST_NAME).unlink(missing_ok=True)
                _prune_dir(plan.archive_dir)
                _prune_dir(plan.archive_dir.parent)  # .claude-backups/ if now empty

    for rev in plan.reverts:
        if dry_run:
            report.reverted.append(rev.target_rel)
            continue
        if rev.target.exists() or rev.target.is_symlink():
            if rev.target.is_dir() and not rev.target.is_symlink():
                shutil.rmtree(rev.target)
            else:
                rev.target.unlink()
        rev.backup.replace(rev.target)  # move the original back (the .bak IS the original)
        report.reverted.append(rev.target_rel)

    return report


def _prune_dir(d: Path) -> None:
    """Best-effort ``rmdir`` of a now-empty dir (never errors if non-empty / missing)."""
    try:
        d.rmdir()
    except OSError:
        pass


# ------------------------------------------------------------------------------------- CLI


def _confirm(target: Path, *, non_interactive: bool, dry_run: bool) -> bool:
    """Consent gate for the destructive run — mirrors ``uninstall``'s automation contract.

    ``--dry-run`` writes nothing so it always proceeds; ``--non-interactive`` is the automation
    contract (proceed, no prompt); an interactive TTY is asked ``[y/N]``; a non-TTY without
    ``--non-interactive`` REFUSES rather than restoring over files unattended.
    """
    if dry_run or non_interactive:
        return True
    if not sys.stdin.isatty():
        print(
            "refusing to restore over files without a TTY — pass --non-interactive to proceed.",
            file=sys.stderr,
        )
        return False
    ans = input(f"Restore this repo's pre-install originals into {target}? [y/N]: ").strip().lower()
    return ans in ("y", "yes")


def _print_plan(plan: RestorePlan, *, dry_run: bool) -> None:
    """Print EXACTLY what will be restored/reverted, before any mutation."""
    verb = "would restore" if dry_run else "will restore"
    print("\n-- plan --" if dry_run else "\n-- to restore --")
    if plan.archived:
        loc = plan.archive_dir.name if plan.archive_dir is not None else "(archive)"
        for name in plan.archived:
            print(f"{verb} (moved back):   {name}   <- {repo_space.BACKUPS_DIRNAME}/{loc}/")
    for rev in plan.reverts:
        print(f"{verb} (reverted):    {rev.target_rel}   <- {rev.backup.name}")
    if plan.is_empty:
        print("(nothing to restore — no archive and no .bak originals from an install)")


def _print_report(report: RestoreReport) -> None:
    print("\n-- result --")
    if report.restored:
        print(f"restored (moved back): {', '.join(report.restored)}")
    if report.reverted:
        print(f"reverted (from .bak):  {', '.join(report.reverted)}")
    if report.conflicts:
        print(
            f"conflict (left in archive; not overwritten): {', '.join(report.conflicts)}",
            file=sys.stderr,
        )
    for note in report.notes:
        print(f"note:                  {note}")
    print("\nDone. Restart Claude Code if a restored file changed the framework wiring.")


def cli_restore(target: Path | str, *, dry_run: bool, non_interactive: bool) -> int:
    """The product entry (shared by ``restore.py`` and the ``2real-team restore`` bridge)."""
    target = Path(target).resolve()
    print(f"== 2real framework restore ({'DRY-RUN' if dry_run else 'RESTORE'}) ==")
    print(f"target repo:   {target}")

    plan = plan_restore(target)
    _print_plan(plan, dry_run=dry_run)

    if plan.is_empty:
        return 0
    if dry_run:
        print("\n(dry-run — nothing was changed)")
        return 0
    if not _confirm(target, non_interactive=non_interactive, dry_run=dry_run):
        print("aborted — nothing changed.", file=sys.stderr)
        return 1

    report = apply_restore(target, plan, dry_run=False)
    _print_report(report)
    return 1 if report.conflicts else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Restore a repo's pre-install originals — undo the install's tracked "
        "changes to files it displaced/overwrote (#265). NOT a git pristine reset; NOT a full "
        "framework teardown (use uninstall.py for that).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("target", nargs="?", default=".", help="Target repo root (default: cwd)")
    ap.add_argument("--dry-run", action="store_true", help="Print the plan; write nothing")
    ap.add_argument(
        "--non-interactive", action="store_true",
        help="Never prompt (the automation contract); proceed without the [y/N] confirmation",
    )
    args = ap.parse_args(argv)
    return cli_restore(
        Path(args.target), dry_run=args.dry_run, non_interactive=args.non_interactive
    )


if __name__ == "__main__":
    raise SystemExit(main())
