#!/usr/bin/env python3
"""Generic event logger for framework hooks.

PreToolUse hooks call :func:`log_pretooluse_block` when they block a command so
the prevented action is auditable; PostToolUse hooks call
:func:`log_posttooluse_event` for advisory follow-ups. Records are appended as
JSONL to the ``paths.events_log`` location from the framework config
(default ``.claude/framework/events.jsonl``).

This is the product-neutral replacement for the source project's
``annunaki_log`` — same API surface (so ported hooks need only change the import
line), same test-mode suppression, but generic naming and a config-driven path.

Stdlib only. Never raises — a logging failure must never fail the hook.

Test-mode suppression
=====================

When ``ENVIRONMENT=test`` or ``FRAMEWORK_HOOK_TEST_MODE=1`` is set, or the code is
running under pytest (``PYTEST_CURRENT_TEST`` present), writes are skipped — so a
hook test-suite exercising matchers against synthetic fixtures (which may resolve
config to the real repo root when a test omits an isolated ``cwd``) does not
pollute the real events log.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

sys_path_dir = os.path.dirname(os.path.abspath(__file__))
import sys  # noqa: E402

if sys_path_dir not in sys.path:
    sys.path.insert(0, sys_path_dir)

from _framework_config import config  # noqa: E402

_DEFAULT_EVENTS_REL = ".claude/framework/events.jsonl"


def _is_test_mode() -> bool:
    if os.environ.get("ENVIRONMENT", "") == "test":
        return True
    if os.environ.get("FRAMEWORK_HOOK_TEST_MODE", "") == "1":
        return True
    # pytest sets PYTEST_CURRENT_TEST while a test is running. Suppress here too, so a
    # test that fires a hook without an isolated cwd can't write the real events log.
    if "PYTEST_CURRENT_TEST" in os.environ:
        return True
    return False


def _events_path(input_data: dict | None) -> Path:
    """Resolve the events-log path from config, anchored at the config's repo root.

    The configured ``paths.events_log`` is repo-relative; we anchor it at the
    directory containing the discovered ``.claude/`` (config.path's grandparent),
    falling back to cwd-relative when no config file was found.
    """
    cfg = config(input_data)
    rel = cfg.get("paths.events_log", _DEFAULT_EVENTS_REL)
    if cfg.path is not None:
        # cfg.path == <root>/.claude/framework.config.json → root is parent.parent
        root = cfg.path.parent.parent
    else:
        root = Path(os.getcwd())
    return (root / rel).resolve()


def append_jsonl_record(path: Path, record: dict, *, _input_data: dict | None = None) -> None:
    """Append one JSONL record. Skips empty records; never raises."""
    if not isinstance(record, dict) or not record:
        return
    if _is_test_mode():
        return
    line = json.dumps(record, ensure_ascii=False).replace("\n", " ").strip()
    if not line:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # never fail the hook


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_pretooluse_block(
    hook_name: str,
    command: str,
    reason: str,
    tool_name: str = "Bash",
    input_data: dict | None = None,
) -> None:
    """Append a PreToolUse block event (a real prevented command)."""
    record = {
        "timestamp": _now(),
        "type": "pretooluse_block",
        "hook": hook_name,
        "tool_name": tool_name,
        "command": command[:500],
        "reason": reason[:500],
    }
    append_jsonl_record(_events_path(input_data), record)


def log_posttooluse_event(
    hook_name: str,
    command: str,
    reason: str,
    tool_name: str = "Bash",
    input_data: dict | None = None,
) -> None:
    """Append a PostToolUse advisory event (a follow-up condition, not a block)."""
    record = {
        "timestamp": _now(),
        "type": "posttooluse_event",
        "hook": hook_name,
        "tool_name": tool_name,
        "command": command[:500],
        "reason": reason[:500],
    }
    append_jsonl_record(_events_path(input_data), record)
