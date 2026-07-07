#!/usr/bin/env python3
"""PreToolUse hook: block malformed / self-review verdict submissions.

Companion to ``validate_review_comment_format`` (#111). Where that hook gates the
*grammar* of a ``gh pr comment`` / ``gh issue comment`` verdict, this hook guards
the two ways a verdict SUBMISSION is wrong regardless of any policy gate — the
cases that are *always* invalid, so blocking them can never brick the team's own
reviewing:

  1. A raw ``gh pr review`` invocation. All framework agents share one GitHub
     user, so ``gh pr review --approve`` always fails with "cannot approve your
     own pull request", and ``gh pr review --request-changes`` is an API-review
     the charter does not use. The charter (§ Comment-Based Reviews) requires
     comment-based verdicts instead, so this is redirected at write time.

  2. A verdict-comment whose header parses as a charter verdict but names the
     SAME person as ``Requestor:`` (the reviewer) and ``Requestee:`` (the PR
     author) — a self-review. A reviewer clearing their own PR is invalid under
     the charter's Direction rules and inflates the reviewer-count merge gate.

  3. (Belt-and-suspenders) a verdict-comment that *attempts* the charter shape
     but is malformed. ``validate_review_comment_format`` already blocks this and
     ordinarily runs first; this hook re-checks it via the SAME
     ``validate_grammar`` so the self-review path never fires on an unparseable
     body, and so the load-bearing test exercises the grammar branch directly.

Design: reuse the existing parsing layer — this module imports
``validate_review_comment_format``'s command detection, body extraction, and
grammar validator rather than reimplementing any of it (the #663 gh-parser and
#111 grammar invariants live in one place). The self-review comparison is the
only new parsing, and it is a normalized identity equality over the two header
fields the existing regexes already extract.

Flag coordination (Wave 5 / #196)
==================================
S2's ``policy.pr_review_gate_enabled`` gates *merge* enforcement (a different
enforcement point). This hook is deliberately NOT behind that flag and needs no
opt-in: it blocks only cases that are wrong under the charter no matter the gate
state (raw ``gh pr review``; self-review; malformed grammar) and fails open on
everything else. A well-formed cross-person verdict passes untouched, so the
hook cannot brick the team's ability to post verdicts during this wave.

Fail-open posture (#175): pure parsing, no config/roster/network. Any ambiguous
edge — not a review/comment command, no extractable body, a body that is not a
charter-verdict attempt, ``Requestee: N/A``, or an unreadable ``--body-file`` —
returns ``None`` (allow). ``FAIL_OPEN = True`` makes an uncaught bug in this hook
allow rather than block.

Exit codes:
  0 — allow (not a review/comment command, no body, free-form comment,
      well-formed cross-person verdict, or any fail-open edge)
  2 — block (raw ``gh pr review``; malformed charter verdict; self-review)
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Reuse the existing verdict-parsing layer verbatim — do NOT reimplement command
# detection, body extraction, or the charter grammar (#111 / #196 reuse mandate).
import validate_review_comment_format as vrcf  # noqa: E402
from _framework_log import log_pretooluse_block  # noqa: E402
from _shell_parse import (  # noqa: E402
    find_gh_subcommand,
    iter_command_segments,
    strip_heredocs,
    tokenize,
)

#: Fail-open (#175): an uncaught exception from ``check()`` allows the command,
#: matching this module's documented fail-open posture. Blocking the team over a
#: parser bug in a verdict-submission guard would be exactly the brick this hook
#: is written to avoid.
FAIL_OPEN = True


_PR_REVIEW_REASON = (
    "BLOCKED: `gh pr review` is not used by this team — all agents share one "
    "GitHub user, so an API `--approve` always fails ('cannot approve your own "
    "pull request') and `--request-changes` bypasses the charter's scored "
    "review record.\n"
    "Charter § Comment-Based Reviews requires a verdict COMMENT instead:\n\n"
    "  gh pr comment <PR#> --body \"$(cat <<'EOF'\n"
    "  Requestor: Firstname.Lastname        # you, the reviewer (comment author)\n"
    "  Requestee: Firstname.Lastname        # the PR author being addressed\n"
    "  RequestOrReplied: Request            # Request (posting) | Replied (reply)\n"
    "\n"
    "  Must-fix: <enumerated items, or None>   # enumerated = changes requested\n"
    "  Tech-debt: <items, or None>             # non-blocking\n"
    "  EOF\n"
    "  )\"\n"
)

_SELF_REVIEW_REASON = (
    "BLOCKED: self-review — the verdict names the same person as `Requestor:` "
    "(the reviewer) and `Requestee:` (the PR author): {who}.\n\n"
    "A reviewer cannot clear their own PR. The charter reserves the verdict "
    "record for an INDEPENDENT reviewer; a self-verdict also inflates the "
    "reviewer-count merge gate (trust_signals counts distinct Requestor values, "
    "so a self-review would be scored as if a second engineer had approved).\n"
    "Post the verdict as the actual reviewer (Requestor = the reviewer, "
    "Requestee = the PR author), or have another team member review."
)


def _is_gh_pr_review(command: str) -> bool:
    """True iff a pipeline segment is a command-position ``gh pr review`` call.

    Routes through the shared ``_shell_parse`` primitives (the #663 gh-parser
    invariant: never reimplement segment-splitting privately — the shared path
    carries the line-continuation, heredoc, and env-prefix-strip fixes):

      1. ``strip_heredocs`` removes heredoc bodies first, so a ``gh pr review``
         appearing inside a ``cat <<EOF ... EOF`` body is never matched.
      2. ``iter_command_segments`` splits the tokenized command on pipeline ops.
      3. ``find_gh_subcommand`` keys on the COMMAND-position first token, so a
         ``gh pr review`` mentioned mid-arg or inside a ``--body`` value is not
         matched (that segment's first token is ``cat`` / ``gh pr comment`` / …).

    Falls back to the historical ``re.split`` segmenter (over the
    heredoc-stripped text) when ``tokenize`` returns None (malformed quotes) so
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


def _normalize_identity(name: str) -> str:
    """Fold a header identity to a comparison key.

    Drops surrounding bold, a role suffix (``Tariq Morales (QA)``), and all
    punctuation/whitespace, lower-casing the rest — so ``Nia.Rossi``,
    ``Nia Rossi``, and ``**Nia.Rossi**`` all compare equal. ``N/A`` folds to
    ``na`` (see :func:`_self_review_reason`, which treats it as "no addressee").
    """
    name = re.sub(r"\([^)]*\)", "", name)  # strip a role suffix
    return re.sub(r"[^a-z0-9]", "", name.lower())


#: Requestee values that mean "no specific addressee" — never a self-review.
_NON_ADDRESSEE = frozenset({"", "na"})


def _self_review_reason(body: str) -> str | None:
    """Return a block reason if *body* is a self-review verdict, else None.

    Precondition: ``vrcf.validate_grammar(body)`` returned None, so both header
    fields are present with non-empty same-line values. A self-review is
    Requestor and Requestee folding to the same identity, with a real addressee
    (``Requestee: N/A`` status turns are never self-reviews).
    """
    req_m = vrcf._LINE_FIELD_RE["Requestor"].search(body)
    ree_m = vrcf._LINE_FIELD_RE["Requestee"].search(body)
    if req_m is None or ree_m is None:  # defensive — grammar validated upstream
        return None
    requestor = _normalize_identity(req_m.group(1))
    requestee = _normalize_identity(ree_m.group(1))
    if requestee in _NON_ADDRESSEE or requestor in _NON_ADDRESSEE:
        return None
    if requestor == requestee:
        return _SELF_REVIEW_REASON.format(who=req_m.group(1).strip().strip("*").strip())
    return None


def check(input_data: dict) -> dict | None:
    """Block a raw ``gh pr review``, a malformed charter verdict, or a
    self-review verdict-comment; else None. Fails open on every ambiguous edge
    (see module docstring)."""
    if input_data.get("tool_name") != "Bash":
        return None

    command = input_data.get("tool_input", {}).get("command", "")

    # (1) Raw `gh pr review` — always invalid for a shared-user team.
    if _is_gh_pr_review(command):
        log_pretooluse_block(
            "block_gh_pr_review", command, _PR_REVIEW_REASON, input_data=input_data
        )
        return {"decision": "block", "reason": _PR_REVIEW_REASON}

    # (2)/(3) Verdict-comment submission. Reuse the existing detection + parsing.
    if not vrcf.is_comment_command(command):
        return None
    body = vrcf.extract_comment_body(command, input_data)
    if not body:
        return None  # nothing inspectable → allow
    if not vrcf.looks_like_charter_comment(body):
        return None  # free-form comment, not a charter verdict attempt

    reason = vrcf.validate_grammar(body)
    if reason is not None:
        # Malformed under the charter grammar. validate_review_comment_format
        # ordinarily blocks this first; re-check via the SAME validator so the
        # self-review comparison below never runs on an unparseable body.
        log_pretooluse_block(
            "block_gh_pr_review", command, reason, input_data=input_data
        )
        return {"decision": "block", "reason": reason}

    self_review = _self_review_reason(body)
    if self_review is not None:
        log_pretooluse_block(
            "block_gh_pr_review", command, self_review, input_data=input_data
        )
        return {"decision": "block", "reason": self_review}

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
