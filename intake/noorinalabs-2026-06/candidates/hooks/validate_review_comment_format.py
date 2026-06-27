#!/usr/bin/env python3
"""PreToolUse hook: Validate Requestor/Requestee format in PR review comments.

Blocks `gh pr comment` if the Requestor matches the branch author, which
indicates the Requestor and Requestee fields are swapped on a verdict
comment (charter post-#244: on `Approved` / `Changes Requested`,
Requestor must be the reviewer, Requestee the PR author).

Scope (closes #378)
===================

This hook enforces Requestor/Requestee non-swap detection ONLY for
`Approved` and `ChangesRequested` verdict comments — i.e., the rows of
the charter `pull-requests.md` § Comment-Based Reviews Direction table
where the canonical binding is `Requestor = reviewer, Requestee = PR-author`.
For `Request` and `Reply` comments — where the Direction-table role
bindings invert (`Requestor = PR-author, Requestee = reviewer`) — the
swap heuristic does not apply and the hook returns None. Author/reviewer
discipline for Request/Reply traffic is operator-trusted and not
hook-gated.

Unrecognized `RequestOrReplied` values (typos, future verdict types
the hook doesn't know about) fail OPEN — the hook returns None and
lets the comment through. Validating the verdict word itself is
covered by a sibling hook (`validate_pr_review`); duplicating that
logic here would couple two hooks that should remain independent.

Semantic realignment (closes #386)
==================================

Pre-#386 the swap heuristic checked `Requestee.lastname == branch-author.lastname`,
which encoded the pre-#244 reading of the Direction table (Requestor=PR-author,
Requestee=reviewer). Post-#244, the charter inverts the role bindings on
verdict comments: Requestor IS the reviewer (because the reviewer is the
comment author) and Requestee IS the PR author. The post-#244 swap-detection
condition is therefore `Requestor.lastname == branch-author.lastname` — a
verdict whose Requestor matches the branch author indicates the PR author
is being named as the reviewer (the actual swap).

The path-2 narrowing from #378 (verdict-only scope) is preserved unchanged;
this hook only swaps which field is compared inside that scope.

Exit codes:
  0 — allow (not a comment command, not a review comment, fields correct,
       or RequestOrReplied is not Approved/ChangesRequested)
  2 — block (Requestor matches branch author on an Approved /
       ChangesRequested verdict — fields are swapped)
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo_flag_parse import extract_repo
from annunaki_log import log_pretooluse_block


def is_comment_command(command: str) -> bool:
    """Check if the command contains a gh pr comment invocation."""
    for segment in re.split(r"\s*(?:&&|\|\||\||;)\s*", command):
        stripped = segment.lstrip()
        while re.match(r"[A-Za-z_][A-Za-z0-9_]*=\S*\s+", stripped):
            stripped = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+", "", stripped)
        if re.match(r"gh\s+pr\s+comment\b", stripped):
            return True
    return False


def extract_pr_number(command: str) -> str | None:
    """Extract PR number from gh pr comment command."""
    match = re.search(r"\bgh\s+pr\s+comment\s+(\d+)", command)
    if match:
        return match.group(1)
    match = re.search(r"/pull/(\d+)", command)
    if match:
        return match.group(1)
    return None


def extract_comment_body(command: str) -> str | None:
    """Extract the comment body from the gh pr comment command.

    Handles heredoc format: --body "$(cat <<'EOF' ... EOF)"
    and simple quoted strings: --body '...' or --body "..."
    """
    # Heredoc: capture everything between <<'EOF' (or <<EOF) and the closing EOF
    heredoc_match = re.search(
        r"<<'?EOF'?\s*\n(.*?)\nEOF",
        command,
        re.DOTALL,
    )
    if heredoc_match:
        return heredoc_match.group(1)

    # --body with single-quoted string
    sq_match = re.search(r"--body\s+'((?:[^'\\]|\\.)*)'", command, re.DOTALL)
    if sq_match:
        return sq_match.group(1)

    # --body with double-quoted string
    dq_match = re.search(r'--body\s+"((?:[^"\\]|\\.)*)"', command, re.DOTALL)
    if dq_match:
        return dq_match.group(1)

    return None


def get_branch_name(pr_number: str, repo: str | None = None) -> str | None:
    """Fetch the head branch name for a PR.

    When `repo` (a `<owner>/<name>` string parsed from the user's `gh pr comment
    --repo` flag) is supplied, it is forwarded as `--repo <repo>` so the gh
    invocation targets the SAME repo the user is commenting against. Without
    that pass-through, gh's default repo resolution is cwd-based and a
    cross-repo invocation (reviewer in repo A's cwd posting on repo B's PR)
    silently returns the wrong PR's branch — the #503 cross-repo false-block.
    """
    cmd = ["gh", "pr", "view", pr_number, "--json", "headRefName"]
    if repo:
        cmd.extend(["--repo", repo])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return data.get("headRefName", "")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def extract_branch_author_lastname(head_ref: str) -> str | None:
    """Extract the last name from branch format '{FirstInitial}.{LastName}/...'."""
    match = re.match(r"[A-Za-z]\.([A-Za-z]+)/", head_ref)
    if match:
        return match.group(1)
    return None


# Verdict direction values from charter `pull-requests.md` § Comment-Based
# Reviews Direction table. These are the rows where the swap heuristic is
# sound (Requestee = PR-author).
#
# Tolerated form variants: validate_pr_review counts the literal
# "Changes Requested" (with space) per `feedback_validate_pr_review_approved_not_reply`,
# while some templates and older fixtures use the camelCase "ChangesRequested".
# Both are accepted here. Comparison is case-insensitive on the canonical token
# match. The bare "Changes" prefix is NOT a verdict on its own — we require
# the full token (with or without internal space) to avoid false-narrowing.
_VERDICT_DIRECTIONS = frozenset(
    {
        "approved",
        "changesrequested",
        "changes requested",
    }
)


def _direction_is_verdict(body: str) -> bool:
    """True if the comment body's `RequestOrReplied:` value is a verdict direction.

    Matches the value on the same line as the `RequestOrReplied:` label. The
    value is stripped of trailing markdown bolding / whitespace and lowercased
    before comparison against `_VERDICT_DIRECTIONS`. If no value is captured
    (label present but value empty), returns False (fail-out-of-scope —
    consistent with the path-2 stance of narrowing rather than blocking on
    ambiguous shapes).
    """
    match = re.search(r"RequestOrReplied:\s*(.+)", body)
    if not match:
        return False
    raw = match.group(1).strip()
    raw = raw.strip("*").strip()
    if not raw:
        return False
    # Take the leading verdict word(s). The value may be followed by additional
    # text on the same line in some custom shapes; we only look at what comes
    # before a newline (already handled by `.+` group consuming up to EOL).
    # Lowercase for case-insensitive match against the canonical set.
    canonical = raw.lower()
    # Direct match against the canonical set covers both "approved",
    # "changesrequested", and "changes requested" forms.
    if canonical in _VERDICT_DIRECTIONS:
        return True
    # Tolerate trailing-token noise: e.g. "Approved (post-merge)" should still
    # be treated as Approved. Split on whitespace and join the first 1-2 tokens
    # to attempt the camelCase / two-word verdict match.
    parts = canonical.split()
    if not parts:
        return False
    if parts[0] in _VERDICT_DIRECTIONS:
        return True
    if len(parts) >= 2 and " ".join(parts[:2]) in _VERDICT_DIRECTIONS:
        return True
    return False


def check(input_data: dict) -> dict | None:
    """Check review comment format. Returns result dict if blocking/warning, None if allowed."""
    tool_name = input_data.get("tool_name", "")
    if tool_name != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    if not is_comment_command(command):
        return None

    body = extract_comment_body(command)
    if not body:
        return None

    has_requestor = re.search(r"\*{0,2}Requestor:\*{0,2}\s*(.+)", body)
    has_requestee = re.search(r"\*{0,2}Requestee:\*{0,2}\s*(.+)", body)
    has_request_or_replied = re.search(r"RequestOrReplied:", body)

    if not (has_requestor and has_requestee and has_request_or_replied):
        # A charter-format review comment carries all three headers. Missing
        # any one of them means this is not the comment shape the hook
        # validates — return None (allow) and let downstream/operator
        # discipline cover non-conforming bodies.
        return None

    if not _direction_is_verdict(body):
        # Scope-narrowing per #378 / path 2: the Requestee == branch-author
        # swap heuristic is only sound for verdict directions (Approved /
        # ChangesRequested), where the charter Direction table binds
        # Requestee = PR-author. For Request / Reply (or unrecognized
        # directions) the role bindings invert or are unknown — we cannot
        # safely block on the swap signal. Allow through and let
        # operator/orchestrator discipline cover those surfaces.
        return None

    pr_number = extract_pr_number(command)
    if not pr_number:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not extract PR number from comment command. "
                "Unable to validate Requestor/Requestee format."
            ),
        }

    # Forward the user's --repo flag to the internal gh pr view so the branch
    # we fetch is from the SAME repo the user is commenting against. Closes
    # the #503 cross-repo skew: reviewer in repo-A cwd posting on repo-B PR.
    repo = extract_repo(command)
    if not repo:
        # Same-repo path — gh's cwd-based default resolution is used. Emit a
        # stderr breadcrumb so a future cross-repo invocation that omits
        # --repo is discoverable in transcripts, and the brittle cwd-dependence
        # of the same-repo path is not silent.
        print(
            "validate_review_comment_format: --repo flag absent on gh pr comment; "
            "falling back to cwd-default repo resolution for internal gh pr view. "
            "Cross-repo invocations MUST pass --repo to avoid the #503 swap-block.",
            file=sys.stderr,
        )
    branch_name = get_branch_name(pr_number, repo=repo)
    if not branch_name:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not fetch branch name for PR. "
                "Unable to validate Requestor/Requestee format."
            ),
        }

    branch_author = extract_branch_author_lastname(branch_name)
    if not branch_author:
        return {
            "decision": "allow",
            "systemMessage": (
                "WARNING: Could not extract author from branch name. "
                "Unable to validate Requestor/Requestee format."
            ),
        }

    requestor_lastname = _extract_lastname(has_requestor.group(1))

    if requestor_lastname.lower() == branch_author.lower():
        result = {
            "decision": "block",
            "reason": (
                f"BLOCKED: Requestor/Requestee appears swapped. "
                f"Requestor should be the reviewer (who is doing the review). "
                f"Requestee should be the PR author (who is receiving the review). "
                f"The branch author is {branch_author} — they should be the "
                f"Requestee, not the Requestor."
            ),
        }
        log_pretooluse_block("validate_review_comment_format", command, result["reason"])
        return result

    return None


def _extract_lastname(field_value: str) -> str:
    """Extract a lastname from a Requestor/Requestee field value.

    Strips trailing markdown bolding, surrounding whitespace, and a trailing
    parenthetical role annotation (e.g. `Nadia Khoury (Program Director)`).
    Splits on whitespace or dot and returns the final token. Falls back to
    the cleaned full name if there is no separator.
    """
    raw = field_value.strip().strip("*").strip()
    cleaned = re.sub(r"\s*\(.*?\)\s*$", "", raw).strip()
    parts = re.split(r"[\s.]+", cleaned)
    if len(parts) >= 2:
        return parts[-1]
    return cleaned


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
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
