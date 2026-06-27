#!/usr/bin/env python3
"""PreToolUse hook: Block stale /tmp/* message/body files on commit/PR/issue commands.

Refuses commands of the form ``git commit -F /tmp/...`` and ``gh {pr,issue}
{create,comment,edit} --body-file /tmp/...`` (plus ``gh api ... --input
/tmp/...``) when the target file's mtime is older than ~30s. Such files are
almost always leftovers from a prior task or session that the current command
is about to consume by mistake — see ``feedback_tmp_msg_file_stale.md`` for
the three documented surfaces and the 2026-05-03 ontology-rebuild recurrence
that motivated this hook.

Override paths the user can take when blocked:
  - rename the file to a non-/tmp path (e.g. .claude/scratch/msg.txt)
  - pass ``--message`` / ``--body`` inline instead of from a file
  - use a /tmp path that is genuinely fresh (Write the file again, then re-run
    the command — the freshness window resets to the new mtime)

The 30-second threshold is configurable via the ``STALE_TMP_THRESHOLD_SECONDS``
constant. Chosen as a balance between: long enough that a Write+Bash batched
in parallel always passes (Bash sees the file at <1s mtime), short enough that
a leftover file from a prior task in the same session is reliably caught.

Parser pattern (#316)
=====================

The matcher tokenizes the command via `_shell_parse` (strip_heredocs +
tokenize + iter_command_segments + find_git/gh_subcommand) instead of
regex-scanning the raw command string. This eliminates the heredoc-body /
code-fence / positional-arg false-positives where a /tmp/* path mentioned
inside a body file's content was being read as a body-file flag value
(W7-retro 2026-05-08 regression captured by Annunaki).

This is a warn-only matcher (no security implications when bypassed), so a
shlex parse failure (`tokenize` returns None) fails OPEN — the command is
allowed through and the downstream tool surfaces any real error itself.

Exit codes:
  0 — allow (no /tmp/* body-file argument, or file is fresh, or file missing,
       or shlex parse failed)
  2 — block (target file mtime older than threshold)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shell_parse import (  # noqa: E402
    find_gh_subcommand,
    find_git_subcommand,
    iter_command_segments,
    strip_heredocs,
    tokenize,
)
from annunaki_log import log_pretooluse_block  # noqa: E402

STALE_TMP_THRESHOLD_SECONDS = 30

# Flags whose immediately-following token is a path to a body/message file.
# Used as a two-token form (`-F <path>`) AND an equals form (`--body-file=<path>`).
_BODY_FILE_FLAGS = frozenset({"-F", "--file", "--body-file", "--input"})


def _extract_path_after_flag(tokens: list[str], idx: int) -> str | None:
    """Given a token list and an index pointing at a flag token, return the
    associated path value (or None if no value is attached).

    Handles:
      - Two-token form: tokens[idx] == "-F", tokens[idx+1] is the path.
      - Equals form: tokens[idx] == "--body-file=/tmp/x" — the path is after `=`.
    """
    tok = tokens[idx]
    if "=" in tok:
        # Equals form: split once; the prefix is the flag, the suffix is the path.
        flag, _, value = tok.partition("=")
        if flag in _BODY_FILE_FLAGS and value:
            return value
        return None
    if tok in _BODY_FILE_FLAGS and idx + 1 < len(tokens):
        return tokens[idx + 1]
    return None


def _token_is_body_file_flag(tok: str) -> bool:
    """True if `tok` is a body-file flag in either two-token or equals form."""
    if tok in _BODY_FILE_FLAGS:
        return True
    if "=" in tok:
        flag = tok.split("=", 1)[0]
        return flag in _BODY_FILE_FLAGS
    return False


def _segment_covers_body_file(segment: list[str]) -> bool:
    """True if this command segment is one whose body-file flags we check.

    Covers:
      - git commit              (via -F / --file)
      - gh {pr,issue} {create,comment,edit}  (via --body-file)
      - gh api                  (via --input)
    """
    git_decoded = find_git_subcommand(segment)
    if git_decoded is not None:
        _globals, rest = git_decoded
        if rest and rest[0] == "commit":
            return True

    gh_decoded = find_gh_subcommand(segment)
    if gh_decoded is not None:
        _globals, rest = gh_decoded
        if not rest:
            return False
        topic = rest[0]
        if topic == "api":
            return True
        if topic in ("pr", "issue") and len(rest) >= 2 and rest[1] in ("create", "comment", "edit"):
            return True
    return False


def _extract_tmp_paths(command: str) -> list[str]:
    """Return /tmp/* paths supplied to a body-file flag in a covered command.

    Strips heredocs first so a /tmp path mentioned inside a heredoc body is
    not treated as a flag value. Falls back to "no paths" if shlex parsing
    fails (this is a warn-only matcher — fail open).
    """
    cleaned = strip_heredocs(command)
    tokens = tokenize(cleaned)
    if tokens is None:
        # shlex parse failure — fail open. The command will run; if it
        # genuinely consumes a stale file, the downstream tool will surface
        # that error. We do not block on speculation.
        return []

    paths: list[str] = []
    for segment in iter_command_segments(tokens):
        if not _segment_covers_body_file(segment):
            continue
        for i, tok in enumerate(segment):
            if not _token_is_body_file_flag(tok):
                continue
            value = _extract_path_after_flag(segment, i)
            if value and value.startswith("/tmp/"):
                paths.append(value)
    return paths


def _is_stale(path: str, now: float | None = None) -> bool:
    """True if the file exists and its mtime is older than the threshold."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        # File doesn't exist (or stat fails). The downstream command will
        # surface its own error; not our job to pre-empt that.
        return False
    cutoff = (now if now is not None else time.time()) - STALE_TMP_THRESHOLD_SECONDS
    return mtime < cutoff


def _format_age(path: str, now: float | None = None) -> str:
    """Human-friendly age string like '4m 12s ago' for the error message."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return "unknown age"
    age = (now if now is not None else time.time()) - mtime
    if age < 60:
        return f"{int(age)}s ago"
    if age < 3600:
        return f"{int(age // 60)}m {int(age % 60)}s ago"
    return f"{int(age // 3600)}h {int((age % 3600) // 60)}m ago"


def check(input_data: dict) -> dict | None:
    """Check for stale /tmp body-file args. Returns block dict or None."""
    if input_data.get("tool_name", "") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return None

    tmp_paths = _extract_tmp_paths(command)
    if not tmp_paths:
        return None

    now = time.time()
    stale = [p for p in tmp_paths if _is_stale(p, now=now)]
    if not stale:
        return None

    offending = "\n".join(f"  - {p} (mtime {_format_age(p, now=now)})" for p in stale)
    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: stale /tmp/* file passed to git/gh body-file flag.\n"
            f"The following file(s) have an mtime older than "
            f"{STALE_TMP_THRESHOLD_SECONDS}s — likely leftovers from a prior "
            f"task or session:\n"
            f"{offending}\n\n"
            "This is the /tmp/* race captured in `feedback_tmp_msg_file_stale.md`: "
            "a Write+Bash pair batched in parallel can let Bash consume a stale "
            "file written days ago. To proceed, take one of:\n"
            "  1. Re-write the message/body to the same path (Write tool) and re-run "
            "this command — the freshness window resets.\n"
            "  2. Use a non-/tmp path (e.g. .claude/scratch/msg.txt) so the hook "
            "no longer matches.\n"
            "  3. Pass the content inline with `--message`/`-m` (git) or "
            "`--body`/`-b` (gh) instead of from a file."
        ),
    }
    log_pretooluse_block("block_stale_tmp_message_file", command, result["reason"])
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
