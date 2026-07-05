#!/usr/bin/env python3
"""Reinstall this repo's mirrored Claude assets from the canonical install source.

Self-hosting rule (#116). This repo is BOTH the framework source AND a live consumer of
it (dogfood). Claude-related assets therefore live in two trees:

* **Canonical / install source** — ``framework/assets/**`` (what deploys to target repos).
* **Live runtime** — ``.claude/**`` (what this repo actually loads).

The dual-deploy requirement says the canonical copy is authoritative; this command is its
missing second half: after you edit a canonical asset, run this so the live ``.claude/**``
copy is regenerated from it and the two never drift.

Scope — what is "reinstalled" here
==================================
Only the asset classes Claude Code loads *from* ``.claude/`` and that are byte-copied
verbatim from canonical are managed (today: ``skills/``). The other Claude assets do not
need a copy-and-sync step:

* **hooks/ + lib/** are wired IN PLACE — ``.claude/settings.json`` points the dispatchers at
  ``$CLAUDE_PROJECT_DIR/framework/assets/hooks/*``. The repo runs the canonical files
  directly, so they are canonical-by-reference and cannot drift.
* **team/charter/** is rendered from a template with per-repo ``{{...}}`` substitution and is
  intentionally hand-evolvable (bootstrap installs it skip-if-exists), so it is not a
  byte-mirror.

Live-only assets (a ``.claude/skills/`` entry with no canonical counterpart, e.g. a
repo-local skill) are left untouched — reinstall only pushes canonical → live, it never
deletes.

Usage
=====
  python3 framework/install/reinstall.py           # refresh .claude/ from canonical
  python3 framework/install/reinstall.py --check    # report drift, write nothing (exit 1 if any)

Stdlib only; no deps. Pairs with the ``test_reinstall_parity.py`` CI gate, which fails a PR
that edits a canonical asset (or its live copy) without running this command.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

# framework/install/reinstall.py -> framework/
_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _FRAMEWORK_ROOT.parent
_ASSETS = _FRAMEWORK_ROOT / "assets"

#: (canonical subdir under framework/assets, live subdir under .claude) copied byte-for-byte.
#: Add a tuple here to bring another byte-mirrored asset class under reinstall enforcement.
_MANAGED_TREES = (("skills", "skills"),)


def _iter_tree(base: Path):
    """Yield repo-relative Paths of every file under ``base`` (skipping ``__pycache__``)."""
    if not base.is_dir():
        return
    for p in sorted(base.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            yield p.relative_to(base)


def plan(assets_root: Path = _ASSETS, claude_root: Path = _REPO_ROOT / ".claude") -> list[str]:
    """Live ``.claude/`` paths whose bytes differ from canonical (missing or drifted).

    A non-empty result means the live copy is out of sync with the canonical source in
    either direction (canonical edited without reinstall, or the live copy hand-edited) —
    both are drift the reinstall must reconcile.
    """
    drift: list[str] = []
    for canon_sub, live_sub in _MANAGED_TREES:
        canon = assets_root / canon_sub
        live = claude_root / live_sub
        for rel in _iter_tree(canon):
            src = canon / rel
            dst = live / rel
            if not dst.is_file() or dst.read_bytes() != src.read_bytes():
                drift.append(f".claude/{live_sub}/{rel.as_posix()}")
    return drift


def apply(assets_root: Path = _ASSETS, claude_root: Path = _REPO_ROOT / ".claude") -> list[str]:
    """Copy every managed canonical file over its live counterpart. Returns paths written."""
    written: list[str] = []
    for canon_sub, live_sub in _MANAGED_TREES:
        canon = assets_root / canon_sub
        live = claude_root / live_sub
        for rel in _iter_tree(canon):
            src = canon / rel
            dst = live / rel
            if dst.is_file() and dst.read_bytes() == src.read_bytes():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            written.append(f".claude/{live_sub}/{rel.as_posix()}")
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Reinstall this repo's mirrored Claude assets from framework/assets/.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="Report drift and write nothing; exit 1 if any live copy differs from canonical.",
    )
    args = ap.parse_args(argv)

    if args.check:
        drift = plan()
        if drift:
            print("reinstall: DRIFT — these live copies differ from canonical framework/assets/:")
            for d in drift:
                print(f"  {d}")
            print("Run: python3 framework/install/reinstall.py")
            return 1
        print("reinstall: .claude/ is in sync with canonical framework/assets/.")
        return 0

    written = apply()
    if written:
        print(f"reinstall: refreshed {len(written)} file(s) from canonical:")
        for w in written:
            print(f"  {w}")
    else:
        print("reinstall: already in sync — nothing to do.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
