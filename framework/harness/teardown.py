"""Teardown drivers (#104 §2).

Two mechanisms:

* **drop-the-copy** (§2a, B1-B11): every fixture is a disposable tmp workdir, so teardown is
  ``rm -rf``. Residue is zero by construction; the harness runner does this for every cell.

* **manifest-driven in-place uninstall** (§2b): the reversibility PROOF. On a throwaway copy of
  a happy-path fixture we remove the *enumerated install footprint* (the paths the install
  added, which IS the manifest — fully knowable), restore any ``.bak`` backups, recompute the
  ``{relpath: sha256}`` map and diff it against the pre-install snapshot. ``residue`` = the
  symmetric difference; **pass iff 0**. A non-zero result means the installer wrote a path the
  footprint enumeration missed (drift), which also trips ``no_unexpected_files``.

No product ``uninstall`` exists (deferred #142) — this is entirely harness-side, exactly as the
owner bound for this wave. Stdlib only.
"""

from __future__ import annotations

from pathlib import Path

from .snapshot import added_paths, snapshot, symmetric_diff


def _restore_backups(target: Path) -> None:
    """Restore ``<name>.bak`` → ``<name>`` for the files the installer backs up on conflict.

    Happy-path fresh installs create no backups, so this is usually a no-op; it keeps the
    uninstall correct if the proof is ever run over a conflict fixture.
    """
    for bak in list(target.rglob("*.bak")):
        if ".git" in bak.parts:
            continue
        original = bak.with_suffix("")  # strip the trailing .bak
        if original.name.endswith(".bak"):
            original = bak.parent / bak.name[:-4]
        if original.exists():
            original.unlink()
        bak.replace(original)


def manifest_driven_uninstall(target: Path, pre_install: dict[str, str]) -> list[str]:
    """Remove the install footprint and return the residue vs the pre-install snapshot.

    The removal manifest is the set of files present now but absent in ``pre_install`` — the
    install's own enumerable footprint. After removal + backup restoration we diff again;
    an empty list proves the install was fully reversible.
    """
    post_install = snapshot(target)
    footprint = added_paths(pre_install, post_install)
    for rel in footprint:
        p = target / rel
        if p.is_file():
            p.unlink()
    _restore_backups(target)
    _prune_empty_owned_dirs(target)
    post_teardown = snapshot(target)
    return symmetric_diff(pre_install, post_teardown)


def _prune_empty_owned_dirs(target: Path) -> None:
    """Best-effort removal of now-empty framework-owned dirs (cosmetic; residue is file-based)."""
    for owned in (".claude", "ontology"):
        root = target / owned
        if not root.is_dir():
            continue
        for d in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        if root.is_dir() and not any(root.iterdir()):
            root.rmdir()
