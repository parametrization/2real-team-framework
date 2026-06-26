# Block Self-Approval / Redirect-to-Comment-Review (PreToolUse hook)

**Purpose:** When all agents in a simulated team share a single VCS user identity, the platform's native PR-approval command (`<cli> pr review --approve`) always fails — you cannot approve your own pull request. This hook catches the mistake at command time and redirects the agent to a **comment-based review** format that works under a shared identity. More broadly, it is the template for "this command shape is structurally unsupported in our setup — block it early with a precise redirect."

This is a PreToolUse `Bash` hook with `check(input_data) -> dict | None`. Exit 2 to block; 0 to allow.

---

## The rule it enforces

Block any command whose **command-position** verb is `<cli> pr review` (in any pipeline segment), and return a `reason` that (a) explains why it's unsupported, and (b) gives the exact comment-based format to use instead. Do NOT match the phrase when it appears in data position — inside a heredoc body, a `--body` value, or a comment — which is why this routes through the shared shell parser rather than a raw regex.

## Code template (stdlib only, plus the shared shell parser)

```python
#!/usr/bin/env python3
"""PreToolUse Bash hook: block `<cli> pr review`, redirect to comment reviews.

All agents share one VCS user, so API-based self-approval always fails.
Redirect to the comment-based review format.

Exit codes: 0 allow | 2 block.
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shell_parse import find_tool_subcommand, iter_command_segments, strip_heredocs, tokenize
from annunaki_log import log_pretooluse_block

_CLI = "gh"  # your VCS CLI


def _is_pr_review(command: str) -> bool:
    body = strip_heredocs(command)
    tokens = tokenize(body)
    if tokens is None:  # malformed quotes — conservative regex fallback
        return any(re.match(rf"{_CLI}\s+pr\s+review\b", seg.lstrip())
                   for seg in re.split(r"\s*(?:&&|\|\||\||;)\s*", body))
    for seg in iter_command_segments(tokens):
        found = find_tool_subcommand(seg, _CLI, value_globals=set(), bool_globals=set())
        if found is not None and found[1][:2] == ["pr", "review"]:
            return True
    return False


def check(input_data: dict) -> dict | None:
    if input_data.get("tool_name") != "Bash":
        return None
    command = (input_data.get("tool_input") or {}).get("command", "")
    if not _is_pr_review(command):
        return None
    result = {
        "decision": "block",
        "reason": (
            f"BLOCKED: `{_CLI} pr review` is not supported — all agents share one "
            "VCS user, so API-based approvals always fail.\n"
            "Use a comment-based review instead:\n"
            f"  {_CLI} pr comment <PR#> --body '...'\n\n"
            "Required fields in the comment body:\n"
            "  Reviewer: <reviewer name>      # who is POSTING the review\n"
            "  Author:   <PR author name>     # who is ADDRESSED by it\n"
            "  Verdict:  Approved | ChangesRequested\n"
            "Direction: for a verdict, Reviewer = the reviewer, Author = the PR author. "
            "Swapping them makes the reviewer-count validator collapse two distinct "
            "reviewers into one."
        ),
    }
    log_pretooluse_block("block_pr_review", command, result["reason"])
    return result


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)
    result = check(input_data)
    if result and result.get("decision") == "block":
        print(json.dumps(result)); sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
```

## How to adapt

- **The redirect message is the product.** A block without a precise "do this instead" just frustrates. State the unsupported reason and the exact replacement command + format.
- **Command-position matching is mandatory.** Use the shared parser so a review-format example inside a `--body` heredoc isn't itself blocked. Keep the regex fallback only for un-tokenizable input.
- **Keep the format consistent with your reviewer-count validator.** If a separate hook counts reviewers from comment bodies, the field names and direction you instruct here must be exactly what that validator parses.
- **Generalizes** to any "structurally-impossible command in our environment" — swap the verb and the redirect.
