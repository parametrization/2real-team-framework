#!/usr/bin/env python3
"""SessionStart hook: orient the session — config summary, memory + handoff pointers.

Runs via :mod:`start_dispatcher` (``hooks.session_start``). Emits a compact
orientation block as ``additionalContext``: what project/config governs this
repo, where the version-controlled project memory index lives, and — when a
``<paths.memory>/handoff.md`` exists — a directive to read the latest session
handoff first.

Adapted from the botfarm_inc reference session_start hook, genericised for the
framework: everything is parameterized off ``framework.config.json``
(``project.*``, ``scm.owner``, ``policy.merge_model``, ``paths.memory``) instead
of hardcoded paths, and the heavyweight per-project protocol steps are left to
project skills (e.g. a ``/session-start`` skill) — this hook only points at what
exists.

Config-driven + fail-open + INERT when unconfigured: if no
``framework.config.json`` is found (the repo is not bootstrapped) it says
nothing; unreadable files are skipped, never raised. It NEVER blocks session
start.

Exit semantics (via the dispatcher): advisory only.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from _framework_config import config  # noqa: E402


def _resolve_root(cfg, input_data: dict) -> Path:
    """Repo root = config-file parent's parent; else tool cwd; else CLAUDE_PROJECT_DIR."""
    if cfg.path is not None:
        return cfg.path.parent.parent
    cwd = input_data.get("cwd") if isinstance(input_data, dict) else None
    if isinstance(cwd, str) and cwd:
        return Path(cwd)
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path(os.getcwd())


def _age_str(mtime: float) -> str:
    """Humanised age of a file, coarse on purpose (fresh vs stale is what matters)."""
    age = max(0.0, time.time() - mtime)
    if age < 3600:
        return f"{int(age // 60)}m ago"
    if age < 86400:
        return f"{int(age // 3600)}h ago"
    return f"{int(age // 86400)}d ago"


def check(input_data: dict) -> dict | None:
    """SessionStart entry. None = unconfigured repo (inert); dict = orientation."""
    cfg = config(input_data)
    if cfg.path is None:
        return None  # not a bootstrapped repo — stay silent

    root = _resolve_root(cfg, input_data)
    name = cfg.get("project.name") or root.name
    model = cfg.get("project.model", "single-repo")
    owner = cfg.get("scm.owner")
    merge_model = cfg.get("policy.merge_model", "direct-to-main")
    default_branch = cfg.get("scm.default_branch", "main")

    lines = [
        "[framework session-start]",
        f"Project: {name} ({model})"
        + (f" — github.com/{owner}" if owner else " — scm.owner unset"),
        f"Process: merge_model={merge_model}, default_branch={default_branch}"
        + f", shell={cfg.get('shell', 'bash')}",
    ]

    memory_rel = cfg.get("paths.memory", ".claude/memory")
    memory_dir = root / memory_rel
    index = memory_dir / "MEMORY.md"
    if index.is_file():
        lines.append(f"Project memory index: {memory_rel}/MEMORY.md (topic files read on demand)")

    handoff = memory_dir / "handoff.md"
    if handoff.is_file():
        try:
            age = _age_str(handoff.stat().st_mtime)
        except OSError:
            age = "age unknown"
        lines.append(
            f"Session handoff found ({age}): READ {memory_rel}/handoff.md FIRST — "
            "it is the latest pickup point."
        )

    return {"additionalContext": "\n".join(lines)}


if __name__ == "__main__":  # manual smoke: print the orientation for the cwd repo
    result = check({})
    if result:
        print(result["additionalContext"])
