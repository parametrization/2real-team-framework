#!/usr/bin/env python3
"""PreToolUse hook: Block --no-verify on git commit.

Detects `--no-verify` or `-n` (short form) on git commit / push commands and
blocks them — the charter mandates pre-commit hooks must run.

Input Language
==============

Fires on:      PreToolUse Bash
Matches:       git [globals] commit [args... including --no-verify or -n]
               git [globals] push   [args... including --no-verify]
               (any segment of a compound command)
Does NOT match:
    - Heredoc / --body / --body-file argument bodies that mention
      "--no-verify" in prose (#223). Tokenized via shlex so data-position
      `--no-verify` cannot be confused with a command-position flag.
    - `gh issue create --body "..."`, `cat > /tmp/x <<EOF ... --no-verify ... EOF`
    - `echo "we forbid --no-verify"`
    - `git commit -F /tmp/msg.txt` where msg.txt happens to contain --no-verify
      text (the file content is never on the command line at all).

Flag pass-through:
    --no-verify (long form)  → triggers block
    -n          (short form) → triggers block ONLY for git commit (`-n` on
                               git push has different semantics; we keep
                               coverage commit-only to avoid false-positives).

Exit codes:
  0 — allow (no --no-verify on a git commit/push, or not a git command)
  2 — block (--no-verify detected on git commit/push)
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shell_parse import (  # noqa: E402
    find_git_subcommand,
    iter_command_segments,
    strip_heredocs,
    tokenize,
)
from annunaki_log import log_pretooluse_block  # noqa: E402


def _segment_has_no_verify(segment: list[str]) -> bool:
    """True if a tokenized git commit/push segment carries --no-verify or -n.

    `-n` is matched only on `git commit` (charter intent: bypassing pre-commit
    hooks). `git push -n` means dry-run, not bypass; we don't block that.
    """
    decoded = find_git_subcommand(segment)
    if decoded is None:
        return False
    _globals, rest = decoded
    if not rest:
        return False
    subcmd = rest[0]
    if subcmd not in ("commit", "push"):
        return False
    args = rest[1:]
    if "--no-verify" in args:
        return True
    if subcmd == "commit" and "-n" in args:
        return True
    return False


def check(input_data: dict) -> dict | None:
    """Check for --no-verify in command-position. None to allow, dict to block."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    cleaned = strip_heredocs(command)
    tokens = tokenize(cleaned)
    if tokens is None:
        return None  # parse failure → fail open

    triggered = False
    for segment in iter_command_segments(tokens):
        if _segment_has_no_verify(segment):
            triggered = True
            break

    if not triggered:
        return None

    result = {
        "decision": "block",
        "reason": (
            "BLOCKED: `--no-verify` detected on git commit/push. "
            "This bypasses pre-commit hooks which are required by the charter. "
            "Engineers must not use --no-verify routinely. "
            "If you have a legitimate emergency reason, remove --no-verify and "
            "fix the underlying hook failure instead."
        ),
    }
    log_pretooluse_block("block_no_verify", command, result["reason"])
    return result


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    result = check(input_data)
    if result and result.get("decision") == "block":
        print(json.dumps(result))
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
