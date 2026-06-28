#!/usr/bin/env python3
"""SessionStart dispatcher: run configured session-start hooks in-process.

Mirrors :mod:`post_dispatcher` but for the SessionStart event. Runs each module named in
``hooks.session_start`` (config-driven), aggregates any ``additionalContext`` /
``systemMessage``, and emits a single SessionStart ``hookSpecificOutput`` so the context is
injected at the top of the session. ADVISORY: never blocks session start; a hook that raises
or fails to import is swallowed (fail-open).

Each hook exposes ``check(input_data) -> dict | None``; a non-None result may carry
``additionalContext`` (preferred — injected into the session) and/or ``systemMessage``.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))
_LIB_DIR = _HOOKS_DIR.parent / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from _framework_config import config  # noqa: E402


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        input_data = {}
    if not isinstance(input_data, dict):
        sys.exit(0)

    modules = config(input_data).get("hooks.session_start", [])
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
        if not result:
            continue
        note = result.get("additionalContext") or result.get("systemMessage")
        if note:
            messages.append(note)

    if messages:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": "\n\n".join(messages),
                    }
                }
            )
        )
    sys.exit(0)  # advisory — never block


if __name__ == "__main__":
    main()
