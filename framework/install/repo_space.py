#!/usr/bin/env python3
"""Consent-gated backup / archive / restore for REPO-level ``.claude`` assets (#108).

Mirrors the user-level install UX (#107) for a repo's own Claude assets — the
repo-root ``.claude/`` directory and ``CLAUDE.md``. Before an install replaces or
overwrites a repo's existing Claude assets, the operator chooses — with explicit
consent — between two dispositions:

* **amend in place** (default, non-destructive): keep the existing assets; the
  bootstrapper's idempotent merge / skip-if-exists steps augment them. This is
  today's behaviour and the safe default for ``--non-interactive`` / non-TTY / CI.
* **archive then fresh**: move the existing ``.claude/`` and ``CLAUDE.md`` OUT of
  Claude's load scope into a timestamped ``.claude-backups/<UTC>/`` directory — which
  Claude does NOT load — leaving a clean slate for a fresh install. Fully restorable.

Why ``.claude-backups/`` and not somewhere under ``.claude/``: Claude loads exactly
``.claude/`` and ``CLAUDE.md`` at the repo root. The archive is deliberately relocated
to a sibling directory that is neither of those (and is NOT named ``.claude*``), so an
archived copy is inert — it cannot shadow or be loaded alongside a fresh install.

Reuses the #107 toolkit rather than reimplementing it: ``consent.prompt_consent`` (the
opt-in gate, with a repo-scoped prompt line) and ``atomic_io.atomic_write_text`` (the
atomic manifest write, #145). The timestamped, non-clobbering naming mirrors
``backup.backup_file``'s scheme. Stdlib-only, no deps.

Public API
==========
``has_existing_assets(repo_root) -> bool``
    Whether the repo root carries any managed Claude asset (``.claude/`` or ``CLAUDE.md``).

``choose_disposition(repo_root, *, non_interactive, chooser=None) -> str``
    Resolve the archive-vs-amend decision. Fail-safe: returns ``"amend"`` (the
    non-destructive path) for ``non_interactive`` or a non-TTY; an interactive TTY is
    offered keep-&-amend / archive-&-fresh / cancel. Returns ``"amend" | "archive"
    | "cancel"``. ``chooser`` is a test seam.

``archive_assets(repo_root, *, now=None) -> ArchiveResult``
    MOVE every existing managed asset into a fresh, non-clobbering
    ``.claude-backups/<UTC>/`` directory and write a restore manifest there. Returns
    the archive dir, the moved names, and the manifest path. No-op (empty result) when
    there is nothing to archive.

``restore_assets(repo_root, archive_dir, *, overwrite=False) -> RestoreResult``
    MOVE archived assets back to their original repo-root locations, byte-identical.
    Refuses to clobber a currently-present target (records it as a conflict) unless
    ``overwrite=True``, which removes the current target first. Reads the manifest
    written by :func:`archive_assets`.

``prepare_for_install(repo_root, *, non_interactive, ...) -> PrepareResult``
    The high-level entry the bootstrapper calls: no-op for a fresh repo; otherwise
    resolves the disposition and, for archive, takes an explicit destructive consent
    (via :func:`consent.prompt_consent`) BEFORE moving anything. Returns the action
    taken (``"fresh" | "amend" | "archived" | "cancel"``) and any :class:`ArchiveResult`.

CLI
===
  python3 repo_space.py archive <repo>
  python3 repo_space.py restore <archive_dir> [--into <repo>] [--force]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from atomic_io import atomic_write_text
from consent import prompt_consent

#: Repo-root Claude assets the harness loads (and that an install may replace).
REPO_CLAUDE_ASSETS: tuple[str, ...] = (".claude", "CLAUDE.md")

#: Container for relocated archives — a sibling of ``.claude/``, NOT under it and NOT
#: named ``.claude*``, so Claude never loads an archived copy. One subdir per archive.
BACKUPS_DIRNAME = ".claude-backups"

#: Restore manifest dropped inside each archive dir (records what to move back where).
MANIFEST_NAME = "archive-manifest.json"
MANIFEST_VERSION = 1

#: Destructive-action consent line (repo-scoped; overrides the user-space default).
_CONSENT_PROMPT = (
    "Archive the above repo Claude assets out of Claude's scope and install fresh? [y/N]: "
)


# ------------------------------------------------------------------------------- results


@dataclass
class ArchiveResult:
    """Outcome of :func:`archive_assets`. ``archived`` is False on a no-op."""

    archive_dir: Path | None = None
    moved: list[str] = field(default_factory=list)
    manifest_path: Path | None = None

    @property
    def archived(self) -> bool:
        return bool(self.moved)


@dataclass
class RestoreResult:
    """Outcome of :func:`restore_assets`. ``conflicts`` are targets left untouched."""

    restored: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


@dataclass
class PrepareResult:
    """Outcome of :func:`prepare_for_install`.

    ``action`` is one of ``"fresh"`` (no existing assets), ``"amend"`` (keep in place),
    ``"archived"`` (existing assets relocated; see ``archive``), or ``"cancel"`` (no
    consent — the caller must leave everything untouched and abort).
    """

    action: str
    archive: ArchiveResult | None = None


# --------------------------------------------------------------------------- detection


def has_existing_assets(repo_root: Path | str) -> bool:
    """True if any managed Claude asset (``.claude/`` or ``CLAUDE.md``) is present."""
    root = Path(repo_root)
    return any((root / name).exists() for name in REPO_CLAUDE_ASSETS)


def _present_assets(root: Path) -> list[str]:
    return [name for name in REPO_CLAUDE_ASSETS if (root / name).exists()]


# --------------------------------------------------------------------- archive / restore


def archive_assets(repo_root: Path | str, *, now: datetime | None = None) -> ArchiveResult:
    """Move existing managed assets into ``.claude-backups/<UTC>/`` + write a manifest.

    Deliberately relocates (moves, not copies) each asset OUT of Claude's load scope so
    the archived copy is inert. The archive dir is non-clobbering (a numeric suffix is
    added if the same-second dir exists). ``now`` is injectable for deterministic tests.

    The manifest is written **before** the first ``shutil.move`` — it is the archive's
    recovery index, so it must happen-before the point of no return. If the process crashes
    mid-move, the manifest already names every intended member; :func:`restore_assets` then
    moves back whatever reached the archive and skips members that never left the repo root
    (they are still in place, untouched), so a partial archive is always recoverable rather
    than stranded/unrestorable. (#149 durability finding 3.)
    """
    root = Path(repo_root)
    present = _present_assets(root)
    if not present:
        return ArchiveResult()

    moment = now or datetime.now(timezone.utc)
    stamp = moment.strftime("%Y%m%dT%H%M%SZ")
    base = root / BACKUPS_DIRNAME
    archive_dir = base / stamp
    n = 1
    while archive_dir.exists():
        archive_dir = base / f"{stamp}.{n}"
        n += 1
    archive_dir.mkdir(parents=True)

    # Record types from the still-in-place assets, then persist the manifest BEFORE moving.
    entries = [
        {"name": name, "type": "dir" if (root / name).is_dir() else "file"} for name in present
    ]
    manifest = {
        "version": MANIFEST_VERSION,
        "archived_utc": stamp,
        "repo_root": str(root),
        "entries": entries,
    }
    manifest_path = archive_dir / MANIFEST_NAME
    atomic_write_text(manifest_path, json.dumps(manifest, indent=2) + "\n")

    moved: list[str] = []
    for name in present:
        shutil.move(str(root / name), str(archive_dir / name))
        moved.append(name)

    return ArchiveResult(archive_dir=archive_dir, moved=moved, manifest_path=manifest_path)


def restore_assets(
    repo_root: Path | str, archive_dir: Path | str, *, overwrite: bool = False
) -> RestoreResult:
    """Move archived assets back to their original repo-root locations, byte-identical.

    Reads the manifest written by :func:`archive_assets`. A currently-present target is
    NEVER clobbered unless ``overwrite=True`` (which removes the current target first,
    e.g. a fresh install laid down after the archive); without it the member is left in
    the archive and reported as a conflict. Restoring is idempotent for already-restored
    members (a missing archive member is skipped).

    **Scope is deliberately exact — the managed assets only.** Restore moves back exactly the
    manifest's members (``.claude/`` + ``CLAUDE.md``) and touches nothing else. It does NOT
    return the working tree to a globally pristine state: out-of-scope artifacts a fresh
    install may have left (e.g. ``.git/hooks/pre-push``) and the now-emptied
    ``.claude-backups/<UTC>/`` container are intentionally left in place — pruning them is a
    separate "return to pristine" concern, not this restore's contract (#149 finding 4). The
    ``test_restore_scope_is_exactly_managed_assets`` test asserts this boundary.
    """
    root = Path(repo_root)
    archive_dir = Path(archive_dir)
    manifest_path = archive_dir / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    result = RestoreResult()
    for entry in manifest.get("entries", []):
        name = entry["name"]
        src = archive_dir / name
        dst = root / name
        if not src.exists():
            continue  # already restored / member absent from the archive
        if dst.exists() or dst.is_symlink():
            if not overwrite:
                result.conflicts.append(name)
                continue
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        shutil.move(str(src), str(dst))
        result.restored.append(name)
    return result


# ------------------------------------------------------------------- disposition choice


def _disposition_summary(root: Path) -> str:
    present = ", ".join(_present_assets(root)) or "(none)"
    return (
        f"This repo already carries Claude assets: {present}\n"
        f"  [k] keep & amend  — leave them; the installer augments them idempotently (default)\n"
        f"  [a] archive & fresh — move them to {BACKUPS_DIRNAME}/<UTC>/ "
        "(out of Claude's scope, restorable), then install fresh\n"
        "  [c] cancel        — do nothing"
    )


def choose_disposition(
    repo_root: Path | str,
    *,
    non_interactive: bool,
    chooser: Callable[[], str] | None = None,
    _isatty: bool | None = None,
    _input: Callable[[str], str] = input,
) -> str:
    """Resolve archive-vs-amend. Fail-safe default is ``"amend"`` (non-destructive).

    ``non_interactive`` or a non-TTY always returns ``"amend"`` (today's behaviour,
    safe for CI). An interactive TTY is offered keep / archive / cancel. ``chooser``
    is a test seam returning the decision directly; ``_isatty`` / ``_input`` are test
    seams for the interactive path.
    """
    if non_interactive:
        return "amend"
    if chooser is not None:  # test seam: stands in for the interactive choice
        return chooser()
    isatty = _isatty if _isatty is not None else sys.stdin.isatty()
    if not isatty:
        return "amend"
    print(_disposition_summary(Path(repo_root)))
    try:
        ans = _input("[k]eep & amend / [a]rchive & fresh / [c]ancel [keep]: ").strip().lower()
    except EOFError:
        return "cancel"
    if ans in ("a", "archive"):
        return "archive"
    if ans in ("c", "cancel", "n", "no"):
        return "cancel"
    return "amend"


def _archive_consent_summary(root: Path) -> str:
    present = ", ".join(_present_assets(root)) or "(none)"
    return (
        f"About to ARCHIVE this repo's existing Claude assets ({present}):\n"
        f"  - each is MOVED into {BACKUPS_DIRNAME}/<UTC-stamp>/ (out of Claude's load scope)\n"
        "  - a restore manifest is written alongside them; restore is fully reversible\n"
        f"  - the fresh install then writes a clean {REPO_CLAUDE_ASSETS[0]}/"
    )


def _default_consent(non_interactive: bool) -> Callable[[str], bool]:
    """Bind :func:`consent.prompt_consent` to this run with the repo-scoped prompt."""
    return lambda summary: prompt_consent(
        summary, non_interactive=non_interactive, prompt=_CONSENT_PROMPT
    )


def prepare_for_install(
    repo_root: Path | str,
    *,
    non_interactive: bool,
    chooser: Callable[[], str] | None = None,
    consent_fn: Callable[[str], bool] | None = None,
    now: datetime | None = None,
    _isatty: bool | None = None,
) -> PrepareResult:
    """Resolve + apply the pre-install disposition for a repo's existing Claude assets.

    * no existing assets                         -> ``"fresh"`` (nothing to consent to).
    * disposition ``amend``                      -> ``"amend"`` (proceed, non-destructive).
    * disposition ``cancel``                     -> ``"cancel"`` (caller aborts).
    * disposition ``archive`` + destructive consent granted -> archive, ``"archived"``.
    * disposition ``archive`` + consent declined -> ``"cancel"`` (nothing moved).

    ``chooser`` / ``consent_fn`` / ``_isatty`` are test seams; production callers pass
    only ``repo_root`` and ``non_interactive``.
    """
    root = Path(repo_root)
    if not has_existing_assets(root):
        return PrepareResult(action="fresh")

    disposition = choose_disposition(
        root, non_interactive=non_interactive, chooser=chooser, _isatty=_isatty
    )
    if disposition == "cancel":
        return PrepareResult(action="cancel")
    if disposition == "amend":
        return PrepareResult(action="amend")

    # archive: take an EXPLICIT destructive consent before moving anything.
    granted = (consent_fn or _default_consent(non_interactive))(_archive_consent_summary(root))
    if not granted:
        return PrepareResult(action="cancel")
    return PrepareResult(action="archived", archive=archive_assets(root, now=now))


# --------------------------------------------------------------------------------- CLI


def _cmd_archive(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve()
    if not has_existing_assets(root):
        print(f"nothing to archive: no {' / '.join(REPO_CLAUDE_ASSETS)} under {root}")
        return 0
    result = archive_assets(root)
    print(f"archived {', '.join(result.moved)} -> {result.archive_dir}")
    print(f"restore with: python3 {Path(__file__).name} restore {result.archive_dir}")
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    archive_dir = Path(args.archive_dir).resolve()
    manifest_path = archive_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        print(f"ERROR: no {MANIFEST_NAME} in {archive_dir} — not a repo_space archive.",
              file=sys.stderr)
        return 1
    root = Path(args.into).resolve() if args.into else Path(
        json.loads(manifest_path.read_text(encoding="utf-8")).get("repo_root", ".")
    ).resolve()
    result = restore_assets(root, archive_dir, overwrite=args.force)
    if result.restored:
        print(f"restored {', '.join(result.restored)} -> {root}")
    if result.conflicts:
        print(
            f"skipped (already present at target; use --force to overwrite): "
            f"{', '.join(result.conflicts)}",
            file=sys.stderr,
        )
        return 1
    if not result.restored:
        print("nothing to restore (archive already empty).")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Consent-gated archive / restore of repo-level .claude assets (#108).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("archive", help="Move a repo's existing .claude/ + CLAUDE.md out of scope.")
    a.add_argument("repo", nargs="?", default=".", help="Repo root (default: cwd).")
    a.set_defaults(func=_cmd_archive)

    r = sub.add_parser("restore", help="Restore an archive back to its original repo state.")
    r.add_argument("archive_dir", help="The .claude-backups/<UTC>/ dir to restore from.")
    r.add_argument("--into", metavar="DIR",
                   help="Repo root to restore into (default: the manifest's repo_root).")
    r.add_argument("--force", action="store_true",
                   help="Overwrite a target that currently exists (removes it first).")
    r.set_defaults(func=_cmd_restore)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
