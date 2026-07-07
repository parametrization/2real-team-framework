"""Filesystem snapshots — the ground truth teardown restores to (#104 §1 Stage 1 / §2).

A snapshot is a ``{relpath: sha256}`` map of a fixture workdir captured *before* a single
install byte lands. Teardown recomputes it and diffs (symmetric difference) to prove zero
residue. We hash working-tree files but skip volatile git plumbing (``.git/objects``,
``.git/logs``, index churn) so a re-run is deterministic — EXCEPT ``.git/hooks`` which is
framework-owned (the installed ``pre-push`` must be captured, torn down, and diffed).
Stdlib only.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

#: Framework-owned namespace (#103 `no_unexpected_files`, mirrors bootstrap `_FRAMEWORK_OWNED`).
#: Any path a clean install adds must match one of these prefixes/patterns.
OWNED_PREFIXES = (".claude/", "ontology/", ".git/hooks/")
OWNED_EXACT = (".claude", "ontology")


def _skip(rel_parts: tuple[str, ...]) -> bool:
    """True for volatile git internals we deliberately do not hash.

    Everything under a ``.git`` dir (at ANY depth — meta installs nest child git repos) is
    skipped EXCEPT ``.git/hooks`` (the installed pre-push is a framework-owned artifact teardown
    must account for).
    """
    if ".git" in rel_parts:
        i = rel_parts.index(".git")
        after = rel_parts[i + 1] if i + 1 < len(rel_parts) else None
        return after != "hooks"
    return "__pycache__" in rel_parts


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    """Map every non-volatile file under ``root`` to its sha256 (posix relpaths)."""
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if _skip(rel.parts):
            continue
        out[rel.as_posix()] = _sha256(p)
    return out


def added_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Relpaths present after install that were absent before."""
    return sorted(set(after) - set(before))


def symmetric_diff(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Paths that differ between two snapshots: added, removed, or content-changed.

    This is the residue metric for teardown — a fully reversible install returns an empty
    list against its pre-install snapshot.
    """
    diff: set[str] = set(before) ^ set(after)
    for rel in set(before) & set(after):
        if before[rel] != after[rel]:
            diff.add(rel)
    return sorted(diff)


def is_owned(relpath: str) -> bool:
    """True iff ``relpath`` falls inside the framework-owned namespace.

    Matches at ANY depth so meta-and-children installs (``api/.claude/**``,
    ``web/CLAUDE.md``, a child ``ontology/**``) are recognised as owned, not stray — the
    installer legitimately writes into each child repo. A genuinely stray write (a random
    file outside any ``.claude``/``ontology``/``CLAUDE.md`` path) is still flagged.
    """
    parts = relpath.split("/")
    if ".claude" in parts or "ontology" in parts:
        return True
    if parts[-1].startswith("CLAUDE.md"):
        return True
    if parts[-1] == ".gitignore":  # #187: installer ensures the ledger-ignore default
        return True
    if ".git" in parts:  # an installed .git/hooks/pre-push at any depth (meta children)
        i = parts.index(".git")
        return i + 1 < len(parts) and parts[i + 1] == "hooks"
    return False


def unexpected_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Added paths that landed OUTSIDE the framework-owned namespace (#103 no_unexpected_files)."""
    return [p for p in added_paths(before, after) if not is_owned(p)]
