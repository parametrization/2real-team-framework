#!/usr/bin/env python3
"""PostToolUse dispatcher: single in-process entry point for advisory hooks.

Runs every configured PostToolUse check (``hooks.post_bash``) in-process. Unlike
the PreToolUse dispatcher, PostToolUse hooks are ADVISORY: the tool has already
run, so this dispatcher NEVER blocks — it aggregates ``systemMessage`` advisories
and always exits 0. A hook that raises is swallowed (fail-open).

Each hook exposes ``check(input_data) -> dict | None``; a non-None result may
carry ``systemMessage`` (surfaced) and arbitrary extra keys (ignored here).
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

    modules = config(input_data).get("hooks.post_bash", [])
    messages: list[str] = []

    for module_name in modules:
        try:
            mod = importlib.import_module(module_name)
        except ImportError:
            continue
        check_fn = getattr(mod, "check", None)
        if check_fn is None:
            continue
        try:
            result = check_fn(input_data)
        except Exception:
            continue
        if result and result.get("systemMessage"):
            messages.append(result["systemMessage"])

    if messages:
        print(json.dumps({"systemMessage": "\n\n".join(messages)}))
    sys.exit(0)  # advisory — never block


if __name__ == "__main__":
    main()
