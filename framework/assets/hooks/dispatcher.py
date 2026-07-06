#!/usr/bin/env python3
"""PreToolUse dispatcher: single in-process entry point for Bash + Agent hooks.

Instead of one subprocess per hook, this runs every configured check in-process
by importing the module and calling its ``check(input_data) -> dict | None``.

Each hook module exposes::

    check(input_data: dict) -> dict | None
        None              -> allow
        {"decision": "block", "reason": ...}        -> block (exit 2)
        {"decision": "allow", "systemMessage": ...} -> allow + surface a warning

The active module list + order is read from the framework config, keyed by the
tool being gated: ``hooks.pre_bash`` for Bash, ``hooks.agent`` for the Agent
tool (subagent spawns; wired via the settings ``PreToolUse`` matcher ``Agent``
— ``Task`` is accepted as the legacy name of the same tool). Enabling/disabling
a check is a config edit, not a code change. Order matters: cheap/local checks
first, network-calling (gh) last. First block wins for every routed tool.

Exit codes:
  0 — allow (all passed, or aggregated warnings)
  2 — block (first blocking hook wins)

Fail-safe posture, per hook (#175)
====================================

A missing/uninstalled module is always skipped (`ImportError` — nothing to run).

A hook whose `check()` raises an uncaught exception is a different story: most
hooks in this repo are documented fail-open (a matcher that can't parse a
command should not block the user over its own bug), but at least one —
`require_load_bearing_test` (#167) — is *deliberately* fail-CLOSED: its entire
purpose is to stop unverified new behavior from reaching review, so an
unhandled crash inside it must BLOCK, not silently allow the exact thing it
exists to catch.

Each hook module declares its fail-direction via a module-level
``FAIL_OPEN = True`` attribute. A module that sets it is skipped (allow) on a
crash, exactly like before #175. A module that does NOT set it (the default —
covers `require_load_bearing_test` and any future hook that forgets to
declare) is treated as fail-CLOSED: the crash blocks the tool call. This makes
"fail open on my own bug" an explicit, auditable opt-in per hook rather than
the dispatcher's implicit default, and means a newly added hook is fail-closed
until its author consciously decides otherwise.
"""

from __future__ import annotations

import importlib
import json
import sys
import traceback
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from _framework_config import config  # noqa: E402
from _framework_log import log_pretooluse_block  # noqa: E402

#: tool_name -> config key holding the ordered module list for that gate.
#: "Task" is the legacy name of the Agent tool — same gate.
_TOOL_CONFIG_KEYS = {
    "Bash": "hooks.pre_bash",
    "Agent": "hooks.agent",
    "Task": "hooks.agent",
}


def _crash_reason(module_name: str, exc: Exception) -> str:
    return (
        f"BLOCKED (fail-closed): the `{module_name}` hook raised an uncaught "
        f"{type(exc).__name__} instead of returning a decision. This module is "
        "not declared fail-open (no `FAIL_OPEN = True`), so the dispatcher "
        "treats the crash as a block rather than silently allowing the tool "
        "call (#175). If this hook is meant to fail open on infrastructure "
        "errors, fix the bug or add `FAIL_OPEN = True` to its module."
    )


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    cfg_key = _TOOL_CONFIG_KEYS.get(input_data.get("tool_name", ""))
    if cfg_key is None:
        sys.exit(0)

    modules = config(input_data).get(cfg_key, [])
    warnings: list[str] = []

    for module_name in modules:
        try:
            mod = importlib.import_module(module_name)
        except ImportError:
            continue  # configured but not installed → skip gracefully
        check_fn = getattr(mod, "check", None)
        if check_fn is None:
            continue
        try:
            result = check_fn(input_data)
        except Exception as exc:
            if getattr(mod, "FAIL_OPEN", False):
                continue  # declared fail-open: never let this hook crash the gate
            reason = _crash_reason(module_name, exc)
            log_pretooluse_block(
                "dispatcher",
                json.dumps(input_data.get("tool_input", {}))[:200],
                f"{reason}\n{traceback.format_exc()[-2000:]}",
                tool_name=input_data.get("tool_name", "Bash"),
                input_data=input_data,
            )
            print(json.dumps({"decision": "block", "reason": reason}))
            sys.exit(2)
        if result is None:
            continue
        if result.get("decision") == "block":
            print(json.dumps(result))
            sys.exit(2)
        msg = result.get("systemMessage", "")
        if msg:
            warnings.append(msg)

    if warnings:
        print(json.dumps({"decision": "allow", "systemMessage": "\n\n".join(warnings)}))
    sys.exit(0)


if __name__ == "__main__":
    main()
