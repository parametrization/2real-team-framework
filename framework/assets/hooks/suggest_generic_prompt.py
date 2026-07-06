#!/usr/bin/env python3
"""PostToolUse hook: silent promotion-candidate state-feeder (#102, P0).

Fires on Edit / Write / MultiEdit / NotebookEdit. Records every touched
project-local artifact under a "promotable" ``.claude/`` subtree
(``memory/``, ``skills/``, ``hooks/``, ``lib/``, ``team/charter/``) into the
generic-prompt ledger (:mod:`generic_prompt_tracker`) as a ``pending``
candidate — a durable trail of "this might be worth promoting into
``framework/assets/**``" for the ``promotion-audit`` skill to later classify.

**Deliberately SILENT — no ``systemMessage``, no mid-task nudge.** The upstream
donor (see ``framework/recipes/NOORINALABS_RECONCILE.md`` §3a) originally
surfaced a per-edit advisory here; that pattern decayed (noorinalabs main#716)
because a nudge on every edit trains the reader to ignore it. This port is
deliberately de-escalated to a pure state-feeder: :func:`check` always returns
``None`` — its only effect is the ledger write, and the ``promotion-audit``
skill is the (deterministic, periodic) surface for the accumulated signal.

Config-driven + fail-open + INERT-by-default, mirroring :mod:`ontology_tracker`:
  - Repo root + the ledger path come from :mod:`_framework_config`
    (``paths.generic_prompt_ledger``); for a meta+children project a child file
    is tracked under the parent's ledger (root resolved from the config-file
    location).
  - Acts ONLY when a framework config is actually found (``cfg.path is not
    None``) — a bare checkout with no ``.claude/framework.config.json`` gets
    nothing, so it is safe to wire by default.
  - A first touch of an artifact records a ``pending`` entry; an artifact that
    already carries ANY ledger entry (pending, genericized, or skip) is left
    untouched — re-editing an already-decided file never resets its decision
    (``generic_prompt_tracker.record_candidate(..., skip_if_present=True)``).
  - NEVER blocks and NEVER raises (exceptions from the ledger write are
    swallowed) — a broken hook must not fail the tool call it observes.

Exit codes: 0 — always (advisory/inert hook, never blocks).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))
_LIB_DIR = _HOOKS_DIR.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from _framework_config import config  # noqa: E402
from generic_prompt_tracker import record_candidate  # noqa: E402

# Top-level dir names (relative to the ``.claude/`` root) that hold
# promotion-candidate artifacts.
_CANDIDATE_ROOTS = frozenset({"memory", "skills", "hooks", "lib"})
# A two-part prefix that is ALSO a candidate root (team/charter/**), checked
# separately since it is not a bare top-level dir name.
_CHARTER_PREFIX = ("team", "charter")

# Substring patterns: never a candidate if any appears anywhere in the path.
_SKIP_SUBSTRINGS = ("__pycache__/", ".pyc", "node_modules/", ".git/", ".DS_Store")


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


def _claude_rel_parts(file_path: str, root: Path) -> tuple[str, ...] | None:
    """The path parts of *file_path* relative to ``<root>/.claude/``, or None if outside it."""
    try:
        resolved = Path(file_path).resolve()
    except (OSError, RuntimeError):
        return None
    try:
        rel = resolved.relative_to((root / ".claude").resolve())
    except ValueError:
        return None
    return rel.parts


def _is_candidate(rel_parts: tuple[str, ...]) -> bool:
    if not rel_parts:
        return False
    if rel_parts[0] in _CANDIDATE_ROOTS:
        return True
    return len(rel_parts) >= 2 and rel_parts[0] == _CHARTER_PREFIX[0] and rel_parts[1] == _CHARTER_PREFIX[1]


def check(input_data: dict) -> dict | None:
    """PostToolUse Edit/Write/MultiEdit/NotebookEdit entry. Always returns None (silent)."""
    if input_data.get("tool_name", "") not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return None
    file_path = input_data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return None
    for pattern in _SKIP_SUBSTRINGS:
        if pattern in file_path:
            return None
    if _is_worktree_path(file_path):
        return None

    cfg = config(input_data)
    if cfg.path is None:
        return None  # INERT-by-default: no framework config found
    root = _resolve_root(input_data)

    rel_parts = _claude_rel_parts(file_path, root)
    if rel_parts is None or not _is_candidate(rel_parts):
        return None

    ledger_rel = cfg.get("paths.generic_prompt_ledger", ".claude/generic_prompt_ledger.json")
    ledger_path = root / ledger_rel
    artifact = ".claude/" + "/".join(rel_parts)
    # The ledger file itself is never its own candidate.
    if str(ledger_path.resolve()) == str(Path(file_path).resolve()):
        return None

    try:
        record_candidate(ledger_path, artifact, skip_if_present=True)
    except Exception:
        pass  # never fail the hook

    return None


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    check(input_data)
    sys.exit(0)


if __name__ == "__main__":
    main()
