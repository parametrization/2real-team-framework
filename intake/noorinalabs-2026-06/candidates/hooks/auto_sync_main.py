#!/usr/bin/env python3
"""PostToolUse(Bash): fast-forward the local default branch immediately after a
successful push/merge to ``origin/main`` (main#713).

Owner request 2026-06-19: after any push/merge to ``origin/main``, the local
``main`` checkout should pick up the change *now*, not lag — a stale local main
silently runs pre-fix hooks/skills off disk (this session opened 22 commits
behind and ran the pre-#709 session-start reader). This hook covers the
*self-push* case: when the session itself merges/pushes to main, sync the
working copy right after. (Others' pushes are picked up at session boundaries
by session-start Step 0, which calls the same helper.)

Detection is intentionally narrow-but-safe: a ``git push`` whose refspec names
``main`` against ``origin``, or any ``gh pr merge`` (the org's wave-branch→main
merges go through it). The actual fast-forward is delegated to
:func:`sync_main.sync_main`, which is itself fully guarded — it only moves a
clean, strictly-behind ``main`` and refuses (no-op) on a diverged/ahead/dirty
tree — so an over-broad match here can never corrupt state; the worst case is a
wasted ``git fetch``. A failed push/merge (non-zero exit) is ignored: main did
not move, so there is nothing to sync.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
_PROJECT = _HOOKS_DIR.parent.parent  # .claude/hooks -> .claude -> repo root
_LIB = _PROJECT / ".claude" / "lib"

# A push whose refspec targets main against origin, or any PR merge.
_TRIGGERS = (
    re.compile(r"\bgit\s+push\b[^|&;]*\borigin\b[^|&;]*\bmain\b"),
    re.compile(r"\bgit\s+push\b[^|&;]*:main\b"),
    re.compile(r"\bgh\s+pr\s+merge\b"),
)


def _targets_main(command: str) -> bool:
    return any(p.search(command) for p in _TRIGGERS)


def check(input_data: dict) -> dict | None:
    if input_data.get("tool_name", "") != "Bash":
        return None
    command = (input_data.get("tool_input") or {}).get("command", "")
    if not _targets_main(command):
        return None

    # Only sync if the push/merge itself succeeded — otherwise main did not move.
    tool_output = input_data.get("tool_response") or input_data.get("tool_output") or {}
    if isinstance(tool_output, dict) and tool_output.get("exit_code", 0) != 0:
        return None

    if str(_LIB) not in sys.path:
        sys.path.insert(0, str(_LIB))
    try:
        from sync_main import sync_main
    except ImportError:
        return None

    result = sync_main(_PROJECT)
    if result.status == "fast-forwarded":
        return {"systemMessage": f"🔄 auto-sync: local {result.detail}"}
    if result.status == "error":
        return {
            "systemMessage": f"⚠ auto-sync (main#713) could not fast-forward main: {result.detail}"
        }
    # up-to-date / skipped-not-on-branch / refused-* — safe, silent no-op.
    return None


def main() -> None:
    import json

    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    result = check(input_data)
    if result and result.get("systemMessage"):
        print(json.dumps({"systemMessage": result["systemMessage"]}))
    sys.exit(0)


if __name__ == "__main__":
    main()
