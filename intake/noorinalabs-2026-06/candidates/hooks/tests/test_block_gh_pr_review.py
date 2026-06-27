#!/usr/bin/env python3
"""Behavioral test fixtures for block_gh_pr_review hook.

The hook is parser-class — it parses `tool_input.command` via `re.split` on
shell separators (`&&`, `||`, `|`, `;`) and `re.match` for `gh pr review`
detection on each segment. This file closes the empirical fixture gap
surfaced by user-service#98: the hook had zero test coverage at all
(verified at origin: `.claude/hooks/tests/test_block_gh_pr_review.py`
returned HTTP 404 against `noorinalabs-main` `main` pre-PR).

Fixtures pin documented behavior — `gh pr review` blocked, `gh pr comment`
passes, `gh pr edit` passes — and the segment-splitter's interaction with
each shell separator class.

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_block_gh_pr_review.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import block_gh_pr_review as hook  # noqa: E402


def _input(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class PositiveMatchTests(unittest.TestCase):
    """Real `gh pr review` invocations MUST be blocked."""

    def test_bare_form(self):
        result = hook.check(_input("gh pr review 42"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_with_approve_flag(self):
        result = hook.check(_input("gh pr review 42 --approve"))
        self.assertIsNotNone(result)

    def test_with_body_flag(self):
        result = hook.check(_input('gh pr review 42 --body "lgtm"'))
        self.assertIsNotNone(result)

    def test_chained_after_and_and(self):
        """Segment-split on `&&` must still flag a later `gh pr review`."""
        result = hook.check(_input("gh pr view 42 && gh pr review 42 --approve"))
        self.assertIsNotNone(result)

    def test_chained_after_semicolon(self):
        result = hook.check(_input("echo ready ; gh pr review 42"))
        self.assertIsNotNone(result)

    def test_chained_after_pipe(self):
        result = hook.check(_input("true | gh pr review 42"))
        self.assertIsNotNone(result)

    def test_chained_after_double_pipe(self):
        result = hook.check(_input("false || gh pr review 42"))
        self.assertIsNotNone(result)

    def test_block_reason_cites_charter(self):
        """Block message must redirect to `gh pr comment` (charter § Pull Requests)."""
        result = hook.check(_input("gh pr review 42"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("gh pr comment", result["reason"])


class BlockedMessageDirectionTests(unittest.TestCase):
    """Regression for #372: BLOCKED message example must NOT invert Requestor/Requestee.

    Pre-fix the example said `Requestor: <branch author name>` and
    `Requestee: <reviewer name>` — the opposite of the charter § Comment-Based
    Reviews Direction table for Approved/ChangesRequested verdicts. An operator
    copying the example literally reproduced the W9 PR#349 cascade
    (validate_pr_review counts distinct Requestor values; two reviewers both
    posting the PR author's name as Requestor → 1/2 distinct).
    """

    def _reason(self) -> str:
        result = hook.check(_input("gh pr review 42 --approve"))
        self.assertIsNotNone(result)
        assert result is not None
        return result["reason"]

    def test_requestor_example_is_reviewer_not_branch_author(self):
        reason = self._reason()
        self.assertIn("Requestor: <reviewer name>", reason)
        self.assertNotIn("Requestor: <branch author name>", reason)
        self.assertNotIn("Requestor: <branch author>", reason)
        self.assertNotIn("Requestor: <PR author", reason)

    def test_requestee_example_is_pr_author_not_reviewer(self):
        reason = self._reason()
        self.assertIn("Requestee: <PR author name>", reason)
        self.assertNotIn("Requestee: <reviewer name>", reason)
        self.assertNotIn("Requestee: <reviewer>", reason)

    def test_requestor_precedes_requestee_in_example(self):
        reason = self._reason()
        idx_r1 = reason.find("Requestor: <reviewer name>")
        idx_r2 = reason.find("Requestee: <PR author name>")
        self.assertGreaterEqual(idx_r1, 0)
        self.assertGreaterEqual(idx_r2, 0)
        self.assertLess(idx_r1, idx_r2)

    def test_block_message_cites_direction_table(self):
        """Message must reference the charter Direction table (per #372 acceptance #4)."""
        reason = self._reason()
        self.assertIn("Comment-Based Reviews", reason)
        self.assertIn("Direction", reason)

    def test_block_message_explains_swap_failure_mode(self):
        """Message must include a callout naming the W9 PR#349 cascade failure mode."""
        reason = self._reason()
        self.assertIn("W9 PR#349", reason)
        self.assertIn("distinct Requestor", reason)

    def test_block_message_uses_canonical_verdict_strings(self):
        """Verdict tokens prefer the canonical `ChangesRequested` (no space).

        validate_pr_review.py accepts both forms (`ChangesRequested` per
        charter line 14 and the spaced `Changes Requested` per the parser's
        tolerance shim), but the operator-facing example should use the
        canonical form to avoid teaching the spaced variant.
        """
        reason = self._reason()
        self.assertIn("Approved | ChangesRequested", reason)


class NegativeMatchTests(unittest.TestCase):
    """Other `gh pr <subcommand>` shapes MUST NOT be blocked."""

    def test_gh_pr_comment(self):
        """Charter-required review path — explicit allow."""
        cmd = 'gh pr comment 42 --body "Requestor: A\nRequestee: B\nRequestOrReplied: Approved"'
        self.assertIsNone(hook.check(_input(cmd)))

    def test_gh_pr_edit(self):
        self.assertIsNone(hook.check(_input("gh pr edit 42 --body-file .claude/scratch/x.md")))

    def test_gh_pr_list(self):
        self.assertIsNone(hook.check(_input("gh pr list --state open")))

    def test_gh_pr_view(self):
        self.assertIsNone(hook.check(_input("gh pr view 42 --json state,mergedAt")))

    def test_gh_pr_create(self):
        self.assertIsNone(hook.check(_input("gh pr create --body-file .claude/scratch/x.md")))

    def test_gh_pr_ready(self):
        self.assertIsNone(hook.check(_input("gh pr ready 42")))

    def test_gh_issue_with_review_substring_in_body(self):
        """A `--body` literal mentioning the words is not a real invocation."""
        cmd = 'gh issue create --title x --body "see policy on gh pr review"'
        self.assertIsNone(hook.check(_input(cmd)))

    def test_non_bash_tool_passes(self):
        self.assertIsNone(
            hook.check(
                {
                    "tool_name": "Edit",
                    "tool_input": {"command": "gh pr review 42"},
                }
            )
        )

    def test_empty_command(self):
        self.assertIsNone(hook.check(_input("")))

    def test_unrelated_command(self):
        self.assertIsNone(hook.check(_input("ls -la")))

    def test_grep_for_phrase_does_not_match(self):
        """`grep 'gh pr review' file` is not an invocation — first token is grep."""
        self.assertIsNone(hook.check(_input("grep 'gh pr review' /tmp/log")))


class HeredocBoundaryTests(unittest.TestCase):
    """Heredoc bodies are NOT treated as command position (main#663).

    Post-#663 the hook strips heredoc bodies via `_shell_parse.strip_heredocs`
    before tokenizing, so a `gh pr review` mentioned inside a `cat <<EOF ... EOF`
    body is never matched — regardless of whether the body contains shell
    separators. This corrects the pre-#663 over-block where the private
    `re.split` segmenter split a heredoc body on `;` and blocked a documented
    code/prose fragment.
    """

    def test_heredoc_body_starting_with_phrase_no_separator(self):
        """No shell-separator inside the body → heredoc body is stripped."""
        cmd = (
            "cat > /tmp/x.md <<'EOF'\n"
            "gh pr review is blocked by hook policy\n"
            "use gh pr comment instead\n"
            "EOF"
        )
        self.assertIsNone(hook.check(_input(cmd)))

    def test_heredoc_body_with_semicolon_no_longer_false_blocks(self):
        """Regression for the pre-#663 over-block.

        A `gh pr review` phrase inside a heredoc body, even preceded by a `;`,
        is documentation/prose — NOT a real invocation. After routing through
        `strip_heredocs` the body is removed before tokenization, so the hook
        correctly allows the command.
        """
        cmd = "cat <<'EOF'\nstep 1; gh pr review is bad; step 2\nEOF"
        self.assertIsNone(hook.check(_input(cmd)))


if __name__ == "__main__":
    unittest.main()
