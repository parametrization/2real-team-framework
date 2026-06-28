#!/usr/bin/env python3
"""SessionStart hook: keep the GENERATED structural ontology fresh.

Regenerates ``<paths.ontology>/structural/`` when the index is stale (a source file is newer
than the committed ``code-graph.json``), so the structural layer the librarian reads is current
at the start of every session. Pairs with :mod:`ontology_tracker` (semantic overlay) and
:mod:`ontology_gen` (the generator).

Config-driven + fail-open + INERT-by-default:
  - Repo root + ``paths.ontology`` come from :mod:`_framework_config` (for a meta+children
    project the parent root is resolved from the config-file location).
  - Acts ONLY when an ontology dir already exists, mirroring ontology_tracker — so it is safe
    to wire everywhere; a project with no ontology gets nothing. It NEVER blocks session start.

``ontology_gen`` is imported from the sibling ``lib/`` dir, which resolves correctly in BOTH
layouts: deployed (``.claude/hooks/`` -> ``.claude/lib/``) and source
(``framework/assets/hooks/`` -> ``framework/assets/lib/``).

Exit codes: 0 — always (advisory hook).
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


def _resolve_root(input_data: dict) -> Path:
    """Repo root = config-file parent's parent; else tool cwd; else CLAUDE_PROJECT_DIR."""
    cfg = config(input_data)
    if cfg.path is not None:
        return cfg.path.parent.parent
    cwd = input_data.get("cwd") if isinstance(input_data, dict) else None
    if isinstance(cwd, str) and cwd:
        return Path(cwd)
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path(os.getcwd())


def check(input_data: dict) -> dict | None:
    """SessionStart entry. None = nothing to say; dict = advisory (regenerated)."""
    cfg = config(input_data)
    root = _resolve_root(input_data)
    onto_rel = cfg.get("paths.ontology", "ontology")
    onto_dir = root / onto_rel

    # INERT-by-default: only refresh when an ontology layer already exists.
    if not onto_dir.is_dir():
        return None

    try:
        from ontology_gen.refresh import refresh
    except ImportError:
        return None

    model = cfg.get("project.model", "single-repo")
    name = cfg.get("project.name") or root.name
    try:
        result = refresh(root, ontology_path=onto_rel, repo_name=name, model=model)
    except Exception:
        return None  # fail-open: never break session start over the ontology.

    if not result.get("regenerated"):
        return None

    msg = (
        "[ontology] structural index refreshed (was stale): "
        f"{result.get('files', '?')} files / {result.get('nodes', '?')} nodes / "
        f"{result.get('edges', '?')} edges."
    )
    agg = result.get("aggregate")
    if agg:
        msg += f" cross-repo: {agg.get('nodes', '?')} nodes across {agg.get('repos', '?')} repo(s)."
    return {"systemMessage": msg, "additionalContext": msg}


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        input_data = {}
    result = check(input_data) if isinstance(input_data, dict) else None
    if result and result.get("additionalContext"):
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": result["additionalContext"],
                    }
                }
            )
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
