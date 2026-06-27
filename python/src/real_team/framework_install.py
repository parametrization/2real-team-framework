"""Bridge: install the config-driven framework runtime (hooks/lib/skills/config).

The mustache layer (`bootstrap.py`) scaffolds the *team* (charter, roster cards,
trust matrix). This module installs the *runtime* — the genericised hooks, libs,
the lifecycle state machine, the `wave-lifecycle` skill, `framework.config.json`,
and the dispatcher wiring in `settings.json` — by invoking the framework's own
deterministic installer (`framework/install/bootstrap.py`) against the same
target. That keeps a single source of truth for the install logic (no duplicated
copy/merge code) and lets `2real-team init` lay down a complete, runnable
`.claude/` instead of templates alone.

The framework assets are bundled into the wheel under `_bundled/framework/`
(see `hatch_build.py`); in a source checkout they resolve to the repo-root
`framework/`. If neither is found the bridge degrades gracefully (returns None)
so `init` still completes its team scaffolding.

`--no-team` is always passed: the CLI already wrote its own roster cards, so the
framework installer lays down only hooks/lib/skills/config (commit-identity
enforcement stays opt-in — enable it later via the framework installer's roster
generation, which writes the `roster.json` the gate reads).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent


def resolve_framework_root() -> Path | None:
    """Locate the framework root (the dir holding ``install/`` + ``assets/``).

    Prefers the wheel-bundled copy; falls back to the repo-checkout layout
    (``src/real_team`` → up 3 → repo root → ``framework``). Returns None when
    neither has a runnable ``install/bootstrap.py``.
    """
    candidates = [
        _PKG_DIR / "_bundled" / "framework",
        _PKG_DIR.parents[2] / "framework",
    ]
    for root in candidates:
        if (root / "install" / "bootstrap.py").is_file():
            return root
    return None


def install_framework(
    target: Path,
    *,
    owner: str | None = None,
    shell: str = "bash",
    reviewers: int | None = None,
    merge_model: str | None = None,
    dry_run: bool = False,
) -> subprocess.CompletedProcess | None:
    """Install the framework runtime into ``target`` via its own bootstrapper.

    Returns the CompletedProcess (inspect ``.returncode`` / ``.stdout``), or
    None when the framework assets could not be located (caller should report a
    soft notice, not fail).
    """
    root = resolve_framework_root()
    if root is None:
        return None

    cmd: list[str] = [
        sys.executable,
        str(root / "install" / "bootstrap.py"),
        str(target),
        "--no-team",
        "--shell",
        shell,
    ]
    if owner:
        cmd += ["--owner", owner]
    if reviewers is not None:
        cmd += ["--reviewers", str(reviewers)]
    if merge_model:
        cmd += ["--merge-model", merge_model]
    if dry_run:
        cmd += ["--dry-run"]

    return subprocess.run(cmd, capture_output=True, text=True)
