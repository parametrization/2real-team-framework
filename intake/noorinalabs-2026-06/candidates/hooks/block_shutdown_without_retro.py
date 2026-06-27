#!/usr/bin/env python3
"""PreToolUse hook: Block agent shutdown until wave retrospective is recorded.

Prevents SendMessage calls that carry a structured shutdown_request unless a
retrospective entry exists in feedback_log.md for today's date.

Input Language
==============

Fires on:      PreToolUse SendMessage
Matches:       SendMessage tool_input where `message` is a STRUCTURED
               shutdown_request — either a dict with `type: "shutdown_request"`
               or a JSON-string parseable to such a dict.
Does NOT match (#189):
    - Plain prose containing the substring "shutdown_request" but not in a
      structured JSON object. Subagent stand-down acknowledgments
      ("standing down", "Acknowledge", "task complete") that happen to
      mention the phrase in passing are no longer caught.
    - Utility-agent targets (name contains "explorer", "review", "hook").
    - Emergency shutdowns where the JSON object's `reason` is "error" or
      "crash".

Exit codes:
  0 — allow
  2 — block (no retro found for today)
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shell_parse import is_shutdown_request_message  # noqa: E402
from annunaki_log import log_pretooluse_block  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FEEDBACK_LOG = _REPO_ROOT / ".claude" / "team" / "feedback_log.md"


def has_retro_for_today() -> bool:
    """Check if feedback_log.md contains a retrospective entry dated today."""
    today_str = date.today().strftime("%Y-%m-%d")
    try:
        content = _FEEDBACK_LOG.read_text(encoding="utf-8")
        # Look for a heading line containing today's date
        for line in content.splitlines():
            if line.startswith("#") and today_str in line:
                return True
        return False
    except FileNotFoundError:
        return False


def _parsed_shutdown_obj(message) -> dict | None:
    """Return the parsed shutdown_request dict, or None if not a structured shutdown."""
    if isinstance(message, dict) and message.get("type") == "shutdown_request":
        return message
    if isinstance(message, str):
        s = message.strip()
        if not s.startswith("{"):
            return None
        try:
            obj = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            return None
        if isinstance(obj, dict) and obj.get("type") == "shutdown_request":
            return obj
    return None


def is_emergency(obj: dict) -> bool:
    """Check if a parsed shutdown_request has reason == error / crash."""
    return obj.get("reason") in ("error", "crash")


def is_utility_agent(tool_input: dict) -> bool:
    """Check if the target agent is a utility agent that doesn't need retros."""
    target = tool_input.get("to", "").lower()
    return "explorer" in target or "review" in target or "hook" in target


def check(input_data: dict) -> dict | None:
    """Dispatcher-compatible entry point. None to allow, dict to block.

    Exposed alongside `main()` so tests can drive the hook without going
    through stdin/exit-code plumbing.
    """
    tool_name = input_data.get("tool_name", "")
    if tool_name != "SendMessage":
        return None

    tool_input = input_data.get("tool_input", {})
    message = tool_input.get("message", "")

    # Only care about STRUCTURED shutdown requests (#189 — no more substring
    # false-positives on prose).
    if not is_shutdown_request_message(message):
        return None

    obj = _parsed_shutdown_obj(message)
    # is_shutdown_request_message returned True, so obj must be parseable;
    # guard defensively in case of API drift.
    if obj is None:
        return None

    # Allow emergency shutdowns
    if is_emergency(obj):
        return None

    # Allow utility agent shutdowns
    if is_utility_agent(tool_input):
        return None

    # Check for retro
    if has_retro_for_today():
        return None

    # Block: no retro found
    return {
        "decision": "block",
        "reason": (
            "BLOCKED: Cannot shut down agents before running the wave retrospective. "
            "Run /wave-retro or /retro first, then retry shutdown."
        ),
    }


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result is None:
        sys.exit(0)

    print(json.dumps(result))
    if result.get("decision") == "block":
        message = (input_data.get("tool_input") or {}).get("message", "")
        log_pretooluse_block(
            "block_shutdown_without_retro", message, result["reason"], tool_name="SendMessage"
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
