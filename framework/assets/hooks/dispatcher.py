#!/usr/bin/env python3
"""PreToolUse dispatcher: single in-process entry point for Bash hooks.

Instead of one subprocess per hook, this runs every configured check in-process
by importing the module and calling its ``check(input_data) -> dict | None``.

Each hook module exposes::

    check(input_data: dict) -> dict | None
        None              -> allow
        {"decision": "block", "reason": ...}        -> block (exit 2)
        {"decision": "allow", "systemMessage": ...} -> allow + surface a warning

The active module list + order is read from the framework config
(``hooks.pre_bash``), so enabling/disabling a check is a config edit, not a code
change. Order matters: cheap/local checks first, network-calling (gh) last.

Exit codes:
  0 — allow (all passed, or aggregated warnings)
  2 — block (first blocking hook wins)

Fail-safe posture: a missing module is skipped; a hook that raises is skipped
(never let one hook crash the whole gate).
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from _framework_config import config  # noqa: E402


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    if input_data.get("tool_name", "") != "Bash":
        sys.exit(0)

    modules = config(input_data).get("hooks.pre_bash", [])
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
        except Exception:
            continue  # never let a hook crash the gate
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
