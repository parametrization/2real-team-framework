#!/usr/bin/env python3
"""Stop dispatcher: run configured Stop-event hooks in-process.

Mirrors :mod:`post_dispatcher` but for the Stop event (fires when Claude finishes
responding). Runs each module named in ``hooks.stop`` (config-driven), aggregates
any advisories, and always exits 0. ADVISORY BY CONTRACT: a Stop hook must never
block harmfully — a hook that raises or fails to import is swallowed (fail-open),
and even a hook that returns a ``block`` decision is downgraded to a surfaced
warning (its ``reason`` joins the advisories) rather than an exit-2 stop loop.

Each hook exposes ``check(input_data) -> dict | None``; a non-None result may
carry ``systemMessage`` (surfaced) or ``reason`` (surfaced when systemMessage is
absent). Stop hooks should be cheap/no-op when there is nothing meaningful to do
(e.g. :mod:`session_handoff` throttles itself and honors manual handoff notes).
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
        input_data = {}
    if not isinstance(input_data, dict):
        sys.exit(0)

    modules = config(input_data).get("hooks.stop", [])
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
            continue  # never let a hook crash the Stop event
        if not result:
            continue
        msg = result.get("systemMessage") or result.get("reason")
        if msg:
            messages.append(msg)

    if messages:
        print(json.dumps({"systemMessage": "\n\n".join(messages)}))
    sys.exit(0)  # advisory — never block


if __name__ == "__main__":
    main()
