#!/usr/bin/env python3
"""PostToolUse hook: ontology change tracker (semantic-overlay only).

Fires on Edit / Write / MultiEdit. Computes SHA256 of the modified file and records it in
``<paths.ontology>/checksums.json`` under ``last_tracked``. When ``last_tracked !=
last_resolved`` the file is "dirty" and needs reconciliation by ``/ontology-rebuild``.

Config-driven + fail-open + INERT-by-default:
  - Repo root + ontology dir come from ``_framework_config`` (``paths.ontology``); for a
    meta+children project a child file is tracked under the parent's checksums (the hook
    resolves the parent root via the config file location).
  - The hook only tracks when an ontology layer actually exists (the ontology dir OR an
    existing ``checksums.json``). In a project with no ontology, it does nothing — so it is
    safe to wire by default. It NEVER blocks (advisory; PostToolUse).

Scope = the hand-curated SEMANTIC OVERLAY only. The GENERATED structural layer at
``<ontology>/structural/`` is regenerated wholesale by the ``ontology_gen`` generator, so
checksum-tracking it would be meaningless churn — it is skipped here exactly like
``checksums.json`` skips itself.

Exit codes: 0 — always (advisory hook, never blocks).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from _framework_config import config  # noqa: E402

# Substring patterns: skip if any appears anywhere in the file path.
_SKIP_SUBSTRINGS = (
    "/checksums.json",
    "__pycache__/",
    ".pyc",
    "node_modules/",
    ".git/",
    ".DS_Store",
)
# Directory components marking an ephemeral worktree-isolation tree.
_WORKTREE_DIR_NAMES = frozenset({".worktrees", "worktrees"})


def _is_worktree_path(file_path: str) -> bool:
    parts = Path(file_path).parts
    for i, part in enumerate(parts):
        if part == ".worktrees":
            return True
        if part == "worktrees" and i > 0 and parts[i - 1] == ".claude":
            return True
    return False


def _resolve_root(input_data: dict) -> Path:
    """Repo root = config-file parent's parent; else best-effort tool cwd."""
    cfg = config(input_data)
    if cfg.path is not None:
        return cfg.path.parent.parent
    cwd = input_data.get("cwd")
    return Path(cwd) if isinstance(cwd, str) and cwd else Path(os.getcwd())


def _ontology_dir(input_data: dict, root: Path) -> Path:
    return root / config(input_data).get("paths.ontology", "ontology")


def _should_skip(file_path: str, onto_dir: Path, root: Path) -> bool:
    for pattern in _SKIP_SUBSTRINGS:
        if pattern in file_path:
            return True
    if _is_worktree_path(file_path):
        return True
    try:
        resolved = Path(file_path).resolve()
    except (OSError, RuntimeError):
        return True
    # Out-of-tree files cannot be this repo's ontology source.
    try:
        rel_parts = resolved.relative_to(root.resolve()).parts
    except ValueError:
        return True
    # Track ONLY the hand-curated SEMANTIC OVERLAY: a file under a dir named like the ontology
    # dir (covers a child's overlay in the meta+children model too), excluding the generated
    # structural/ layer. Source code and other repo files are NOT the overlay — not tracked.
    if onto_dir.name not in rel_parts or "structural" in rel_parts:
        return True
    return False


def _compute_sha256(file_path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def check(input_data: dict) -> dict | None:
    """PostToolUse Edit/Write/MultiEdit entry. None = not applicable; dict = advisory."""
    if input_data.get("tool_name", "") not in ("Edit", "Write", "MultiEdit"):
        return None
    file_path = input_data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return None

    root = _resolve_root(input_data)
    onto_dir = _ontology_dir(input_data, root)
    checksums_file = onto_dir / "checksums.json"

    # INERT-by-default: only track when an ontology layer exists.
    if not onto_dir.is_dir() and not checksums_file.is_file():
        return None

    if _should_skip(file_path, onto_dir, root):
        return None

    sha = _compute_sha256(Path(file_path))
    if sha is None:
        return None

    try:
        rel_path = str(Path(file_path).resolve().relative_to(root.resolve()))
    except ValueError:
        return None

    now = datetime.now(timezone.utc).isoformat()
    try:
        with open(checksums_file, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {"version": 1, "files": {}}

    files = data.setdefault("files", {})
    existing = files.get(rel_path, {})
    files[rel_path] = {
        "last_tracked": sha,
        "last_resolved": existing.get("last_resolved", ""),
        "tracked_at": now,
        "resolved_at": existing.get("resolved_at", ""),
    }

    try:
        checksums_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = checksums_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        tmp.replace(checksums_file)
    except OSError:
        pass  # never fail the hook

    return {"action": "tracked", "path": rel_path}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    check(input_data)
    sys.exit(0)


if __name__ == "__main__":
    main()
