#!/usr/bin/env python3
"""Tests for block_no_verify — covers #223 (heredoc-body false-positive).

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_block_no_verify.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import block_no_verify as hook  # noqa: E402


def _input(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class PositiveMatchTests(unittest.TestCase):
    """Real `--no-verify` invocations MUST be blocked."""

    def test_commit_long_form(self):
        result = hook.check(_input('git commit --no-verify -m "x"'))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_commit_short_form(self):
        result = hook.check(_input('git commit -n -m "x"'))
        self.assertIsNotNone(result)

    def test_commit_with_dash_c_globals(self):
        result = hook.check(
            _input('git -c user.name="A" -c user.email="a@b.c" commit --no-verify -m "x"')
        )
        self.assertIsNotNone(result)

    def test_commit_flag_after_message(self):
        result = hook.check(_input('git commit -m "x" --no-verify'))
        self.assertIsNotNone(result)

    def test_push_long_form(self):
        result = hook.check(_input("git push --no-verify origin main"))
        self.assertIsNotNone(result)


class NegativeMatchTests(unittest.TestCase):
    """#223: heredoc / --body / --body-file content must NOT trigger."""

    def test_heredoc_body_mentions_phrase(self):
        cmd = (
            "cat > /tmp/x.md <<'EOF'\n"
            "Requestor: Aino\n"
            "We never use --no-verify in this codebase.\n"
            "EOF"
        )
        self.assertIsNone(hook.check(_input(cmd)))

    def test_gh_issue_body_mentions_phrase(self):
        cmd = 'gh issue create --body "see policy on --no-verify"'
        self.assertIsNone(hook.check(_input(cmd)))

    def test_echo_mentions_phrase(self):
        self.assertIsNone(hook.check(_input('echo "we do not allow --no-verify"')))

    def test_unrelated_command_with_substring(self):
        self.assertIsNone(hook.check(_input("grep '\\-\\-no-verify' /tmp/foo")))

    def test_non_bash_tool(self):
        self.assertIsNone(
            hook.check(
                {
                    "tool_name": "Edit",
                    "tool_input": {"command": "git commit --no-verify"},
                }
            )
        )

    def test_git_push_with_dash_n_is_dry_run_not_blocked(self):
        """`git push -n` is dry-run, not bypass — we don't block it."""
        self.assertIsNone(hook.check(_input("git push -n origin main")))

    def test_no_git_at_all(self):
        self.assertIsNone(hook.check(_input("ls --no-verify-flag")))

    def test_git_stash_no_commit_not_blocked(self):
        # isnad-graph#868: regex-based child copy false-positive on `\bcommit\b`
        # matching "commit" inside "--no-commit". Parent's shlex tokenization
        # via _shell_parse rejects this shape (subcommand is `stash`, not
        # `commit`). Fixture pin so a future non-shlex refactor regresses here.
        self.assertIsNone(hook.check(_input("git stash --no-commit")))


if __name__ == "__main__":
    unittest.main()
