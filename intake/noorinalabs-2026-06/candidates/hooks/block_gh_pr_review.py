#!/usr/bin/env python3
"""PreToolUse hook: Block `gh pr review` and require comment-based reviews.

All agents share a single GitHub user, so `gh pr review --approve` always
fails with "cannot approve your own pull request". This hook catches the
mistake early and redirects to the comment-based review format.

Exit codes:
  0 — allow (not a gh pr review command)
  2 — block (gh pr review detected)
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shell_parse import (
    find_gh_subcommand,
    iter_command_segments,
    strip_heredocs,
    tokenize,
)
from annunaki_log import log_pretooluse_block


def _segments_start_gh_pr_review(command: str) -> bool:
    """True iff a pipeline segment is a command-position `gh pr review` invocation.

    Routes shell tokenization through the shared `_shell_parse` primitives
    (main#663 gh-command parser invariant: do not reimplement segment-splitting
    privately — the shared path carries the line-continuation #287, heredoc, and
    env-prefix-strip fixes a private `re.split` loses):

      1. `strip_heredocs` removes heredoc bodies first, so a `gh pr review`
         appearing inside a `cat <<EOF ... EOF` body is never matched
         regardless of whether the body contains shell separators (closes the
         pre-#663 over-block where `step 1; gh pr review` inside a heredoc
         tripped the private `re.split` segmenter).
      2. `iter_command_segments` splits the tokenized command on pipeline ops.
      3. `find_gh_subcommand` keys on the COMMAND-position first token, so
         `gh pr review` mentioned mid-arg or in a `--body` value is not matched
         (that segment's first token is `cat`/`grep`/`gh pr comment`/etc.).

    Falls back to the historical `re.split` segmenter (still over the
    heredoc-stripped text) when `tokenize` returns None (malformed quotes) so
    behavior is preserved on un-tokenizable input.
    """
    body = strip_heredocs(command)
    tokens = tokenize(body)
    if tokens is None:
        return any(
            re.match(r"gh\s+pr\s+review\b", seg.lstrip())
            for seg in re.split(r"\s*(?:&&|\|\||\||;)\s*", body)
        )
    for seg in iter_command_segments(tokens):
        found = find_gh_subcommand(seg)
        if found is not None and found[1][:2] == ["pr", "review"]:
            return True
    return False


def check(input_data: dict) -> dict | None:
    """Check for gh pr review. Returns result dict if blocking, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    if _segments_start_gh_pr_review(command):
        result = {
            "decision": "block",
            "reason": (
                "BLOCKED: `gh pr review` is not supported — all agents share one "
                "GitHub user, so API-based approvals always fail.\n"
                "Charter § Pull Requests / § Comment-Based Reviews requires "
                "comment-based reviews instead.\n\n"
                "Use `gh pr comment <PR#> --body '...'` with this format:\n"
                "  Requestor: <reviewer name>      # team member POSTING the comment\n"
                "  Requestee: <PR author name>     # team member ADDRESSED by it\n"
                "  RequestOrReplied: Approved | ChangesRequested\n"
                "  TechDebt: none | #issue, ...\n\n"
                "Direction reminder (charter § Comment-Based Reviews Direction table):\n"
                "  Approved / ChangesRequested verdicts → Requestor=reviewer, "
                "Requestee=PR author.\n"
                "  Swapping these reproduces the W9 PR#349 cascade — "
                "`validate_pr_review` counts distinct Requestor values across "
                "Approved comments, so two reviewers both writing the PR author's "
                "name as Requestor collapse to 1/2.\n"
            ),
        }
        log_pretooluse_block("block_gh_pr_review", command, result["reason"])
        return result

    return None


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
