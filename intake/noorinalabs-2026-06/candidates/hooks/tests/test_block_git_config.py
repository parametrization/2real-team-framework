#!/usr/bin/env python3
"""Tests for block_git_config — covers #216 (heredoc-body false-positive).

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_block_git_config.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import block_git_config as hook  # noqa: E402


def _input(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class PositiveMatchTests(unittest.TestCase):
    """Real `git config` writes MUST be blocked."""

    def test_simple_write(self):
        result = hook.check(_input("git config --global user.name foo"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_repo_level_write(self):
        result = hook.check(_input("git config user.name foo"))
        self.assertIsNotNone(result)

    def test_with_dash_C_global(self):
        result = hook.check(_input("git -C /repo config user.name foo"))
        self.assertIsNotNone(result)

    def test_unset_identity_blocked(self):
        self.assertIsNotNone(hook.check(_input("git config --unset user.email")))

    def test_user_namespace_blocked(self):
        # The whole user.* identity namespace is protected, not just name/email.
        self.assertIsNotNone(hook.check(_input("git config user.signingkey ABC123")))


class OperationalKeyTests(unittest.TestCase):
    """#717: non-identity (operational) config writes MUST be allowed."""

    def test_core_hookspath_write_allowed(self):
        self.assertIsNone(hook.check(_input("git config core.hooksPath .git/hooks")))

    def test_core_hookspath_unset_allowed(self):
        # The exact command #717 was filed for.
        self.assertIsNone(hook.check(_input("git -C /repo config --unset core.hooksPath")))

    def test_commit_gpgsign_allowed(self):
        self.assertIsNone(hook.check(_input("git config commit.gpgsign false")))


class NegativeMatchTests(unittest.TestCase):
    """#216: prose / --body / --body-file content must NOT trigger.

    Also covers read-only forms (charter requirement)."""

    def test_per_commit_dash_c_user_name(self):
        """Per-commit -c flag — the very pattern this hook directs callers to."""
        cmd = 'git -c user.name="A" -c user.email="a@b.c" commit -m "x"'
        self.assertIsNone(hook.check(_input(cmd)))

    def test_heredoc_body_mentions_phrase(self):
        """The exact #216 repro: gh issue body mentioning 'git config'."""
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main "
            "--body-file /tmp/issue_audit_body.md"
        )
        # body-file content is not on the command line at all — trivially safe
        # even before the fix. But:
        self.assertIsNone(hook.check(_input(cmd)))

    def test_inline_body_mentions_phrase(self):
        cmd = 'gh issue create --body "the git config write block trips here"'
        self.assertIsNone(hook.check(_input(cmd)))

    def test_heredoc_inline_mentions_phrase(self):
        cmd = "cat > /tmp/x.md <<'EOF'\nWe block git config because of the charter rule.\nEOF"
        self.assertIsNone(hook.check(_input(cmd)))

    def test_grep_for_phrase(self):
        self.assertIsNone(hook.check(_input('grep "git config" /tmp/foo')))

    def test_echo_phrase(self):
        self.assertIsNone(hook.check(_input('echo "see git config docs"')))

    def test_read_only_get(self):
        self.assertIsNone(hook.check(_input("git config --get user.name")))

    def test_read_only_list(self):
        self.assertIsNone(hook.check(_input("git config --list")))

    def test_read_only_l_short(self):
        self.assertIsNone(hook.check(_input("git config -l")))

    def test_read_only_get_regexp(self):
        self.assertIsNone(hook.check(_input("git config --get-regexp ^user")))

    def test_non_bash_tool(self):
        self.assertIsNone(
            hook.check(
                {
                    "tool_name": "Edit",
                    "tool_input": {"command": "git config user.name foo"},
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
