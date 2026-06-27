#!/usr/bin/env python3
"""Tests for block_stale_tmp_message_file hook.

Run: python3 -m pytest .claude/hooks/tests/test_block_stale_tmp_message_file.py -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import block_stale_tmp_message_file as hook  # noqa: E402


def _bash(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _touch(path: str, age_seconds: float) -> None:
    """Create the file and stamp it with mtime = now - age_seconds."""
    Path(path).write_text("body", encoding="utf-8")
    target = time.time() - age_seconds
    os.utime(path, (target, target))


class FreshnessGateTests(unittest.TestCase):
    """Core acceptance: fresh allowed, stale blocked."""

    def test_fresh_tmp_file_allowed(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            msg = f"{td}/msg.txt"
            _touch(msg, age_seconds=1)  # well within threshold
            result = hook.check(_bash(f"git commit -F {msg}"))
            self.assertIsNone(result)

    def test_stale_tmp_file_blocked_for_git_commit_F(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            msg = f"{td}/msg.txt"
            _touch(msg, age_seconds=120)  # > 30s threshold
            result = hook.check(_bash(f"git commit -F {msg}"))
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")
            self.assertIn(msg, result["reason"])

    def test_stale_tmp_file_blocked_for_git_commit_long_file(self):
        """`git commit --file <path>` is the long form of -F and must also block."""
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            msg = f"{td}/msg.txt"
            _touch(msg, age_seconds=120)
            result = hook.check(_bash(f"git commit --file {msg}"))
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_stale_tmp_file_blocked_for_gh_pr_create(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            body = f"{td}/body.md"
            _touch(body, age_seconds=120)
            cmd = f"gh pr create --title x --body-file {body}"
            result = hook.check(_bash(cmd))
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_stale_tmp_file_blocked_for_gh_issue_create(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            body = f"{td}/body.md"
            _touch(body, age_seconds=120)
            cmd = f"gh issue create --title x --body-file {body}"
            result = hook.check(_bash(cmd))
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_stale_tmp_file_blocked_for_gh_pr_comment(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            body = f"{td}/body.md"
            _touch(body, age_seconds=120)
            cmd = f"gh pr comment 42 --body-file {body}"
            result = hook.check(_bash(cmd))
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_stale_tmp_file_blocked_for_gh_issue_comment(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            body = f"{td}/body.md"
            _touch(body, age_seconds=120)
            cmd = f"gh issue comment 42 --body-file {body}"
            result = hook.check(_bash(cmd))
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")


class FreshnessGateHeredocRegressionTests(unittest.TestCase):
    """W7-retro 2026-05-08 false-positive regression (#316).

    Reproduces the actual bug shape that motivated this fix:
      - Fresh /tmp/body.md (mtime < threshold) — the genuine --body-file arg
      - Stale /tmp/old.md (mtime > threshold) — mentioned only inside the
        heredoc body as documentation
      - Command: `gh issue create --body-file /tmp/body.md <<EOF ... EOF`
      - Expected: allow (the stale path is NOT a body-file value)

    The pre-fix regex-against-raw-command-string parser found `/tmp/old.md`
    inside the heredoc body and blocked. The post-fix parser strips heredocs
    BEFORE tokenization, so the stale path never reaches the matcher.
    """

    def test_fresh_bodyfile_with_stale_path_in_heredoc_body_allowed(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            fresh = f"{td}/body.md"
            stale = f"{td}/old-stale.md"
            _touch(fresh, age_seconds=1)
            _touch(stale, age_seconds=120)
            cmd = (
                f"gh issue create --title bug --body-file {fresh} <<EOF\n"
                "## Reproducer\n"
                "\n"
                f"A prior {stale} was written and is referenced here as documentation\n"
                "of the bug shape. The hook MUST NOT treat it as a body-file value.\n"
                "EOF"
            )
            result = hook.check(_bash(cmd))
            self.assertIsNone(
                result,
                f"W7-retro regression: stale path inside heredoc body was treated "
                f"as body-file argument and blocked. Reason: {result}",
            )

    def test_fresh_bodyfile_with_code_fence_tmp_in_heredoc_body_allowed(self):
        """Code-fence inside heredoc body referencing /tmp must not trip the matcher.

        Heredoc-strip drops the entire body, so the fenced /tmp/* reference
        falls out before the path-extractor runs.
        """
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            fresh = f"{td}/body.md"
            _touch(fresh, age_seconds=1)
            cmd = (
                f"gh issue create --title doc --body-file {fresh} <<EOF\n"
                "Example:\n"
                "```\n"
                f"cat > /tmp/some-old-example.txt <<INNER\n"
                "content\n"
                "INNER\n"
                "```\n"
                "EOF"
            )
            result = hook.check(_bash(cmd))
            self.assertIsNone(result)


class EqualsFormTests(unittest.TestCase):
    """Coverage for --body-file=<path> / --file=<path> / --input=<path> equals form.

    Pre-fix regex required a SPACE between flag and value, silently missing the
    equals form. Post-fix tokenizer handles both shapes.
    """

    def test_stale_body_file_equals_form_blocked(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            body = f"{td}/body.md"
            _touch(body, age_seconds=120)
            cmd = f"gh issue create --title x --body-file={body}"
            result = hook.check(_bash(cmd))
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")
            self.assertIn(body, result["reason"])

    def test_fresh_body_file_equals_form_allowed(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            body = f"{td}/body.md"
            _touch(body, age_seconds=1)
            cmd = f"gh issue create --title x --body-file={body}"
            result = hook.check(_bash(cmd))
            self.assertIsNone(result)

    def test_stale_git_commit_file_equals_form_blocked(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            msg = f"{td}/msg.txt"
            _touch(msg, age_seconds=120)
            cmd = f"git commit --file={msg}"
            result = hook.check(_bash(cmd))
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")


class GhApiInputTests(unittest.TestCase):
    """Coverage for `gh api ... --input <path>` (issue #316 acceptance flag list)."""

    def test_stale_gh_api_input_blocked(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            payload = f"{td}/payload.json"
            _touch(payload, age_seconds=120)
            cmd = f"gh api repos/foo/bar/issues -X POST --input {payload}"
            result = hook.check(_bash(cmd))
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")
            self.assertIn(payload, result["reason"])

    def test_fresh_gh_api_input_allowed(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            payload = f"{td}/payload.json"
            _touch(payload, age_seconds=1)
            cmd = f"gh api repos/foo/bar/issues -X POST --input {payload}"
            result = hook.check(_bash(cmd))
            self.assertIsNone(result)

    def test_stale_gh_api_input_equals_form_blocked(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            payload = f"{td}/payload.json"
            _touch(payload, age_seconds=120)
            cmd = f"gh api repos/foo/bar/issues -X POST --input={payload}"
            result = hook.check(_bash(cmd))
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")


class NonMatchingTests(unittest.TestCase):
    """Cases where the hook must stay out of the way."""

    def test_non_tmp_path_not_matched(self):
        """Stale file outside /tmp must not trigger — non-/tmp paths are safe.

        Needs a directory NOT under /tmp (the system tempfile default on Linux
        is /tmp, which would defeat the purpose of this test). `os.getcwd()` is
        the natural choice, but a /tmp worktree checkout (the wave isolation
        convention) puts cwd itself under /tmp — so fall back to $HOME, and
        skip only if no non-/tmp location is available (main#802).
        """
        base = os.getcwd()
        if base == "/tmp" or base.startswith("/tmp/"):
            base = os.path.expanduser("~")
        if base == "/tmp" or base.startswith("/tmp/"):
            self.skipTest("no non-/tmp directory available for the negative-path case")
        with tempfile.TemporaryDirectory(dir=base) as td:
            msg = f"{td}/msg.txt"
            _touch(msg, age_seconds=120)
            self.assertFalse(msg.startswith("/tmp/"))
            result = hook.check(_bash(f"git commit -F {msg}"))
            self.assertIsNone(result)

    def test_inline_message_flag_not_matched(self):
        """`git commit -m '...'` does not pass a file → not the hook's concern."""
        result = hook.check(_bash("git commit -m 'fix stuff'"))
        self.assertIsNone(result)

    def test_inline_body_flag_not_matched(self):
        """`gh pr create --body '...'` does not pass a file → not matched."""
        result = hook.check(_bash("gh pr create --title x --body 'inline body'"))
        self.assertIsNone(result)

    def test_non_bash_tool_not_matched(self):
        result = hook.check({"tool_name": "Edit", "tool_input": {"command": "anything"}})
        self.assertIsNone(result)

    def test_empty_command_not_matched(self):
        result = hook.check(_bash(""))
        self.assertIsNone(result)

    def test_missing_tmp_file_does_not_block(self):
        """A non-existent file must not block — let downstream surface its own error."""
        result = hook.check(_bash("git commit -F /tmp/does-not-exist-xyz.txt"))
        self.assertIsNone(result)

    def test_unrelated_git_subcommand_not_matched(self):
        """`git log --grep /tmp/foo` must not be misread as a body-file."""
        result = hook.check(_bash("git log --grep /tmp/foo"))
        self.assertIsNone(result)

    def test_gh_pr_view_not_matched(self):
        """`gh pr view` has no --body-file; stray /tmp mention must not block."""
        result = hook.check(_bash("gh pr view 42 > /tmp/out.txt"))
        self.assertIsNone(result)

    def test_git_commit_with_identity_flags_and_fresh_file_allowed(self):
        """Realistic charter-format commit with -c identity flags + fresh -F file."""
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            msg = f"{td}/msg.txt"
            _touch(msg, age_seconds=1)
            cmd = (
                'git -c user.name="Aino Virtanen" '
                '-c user.email="parametrization+Aino.Virtanen@gmail.com" '
                f"commit -F {msg}"
            )
            result = hook.check(_bash(cmd))
            self.assertIsNone(result)

    def test_git_commit_with_quoted_identity_flags_and_stale_file_blocked(self):
        """Regression: quoted -c values containing spaces must not defeat detection.

        The first cut of this hook used `(?:\\s+-c\\s+\\S+)*` to skip leading -c
        flags, which silently failed once a value like
        `user.name="Aino Virtanen"` introduced a space inside the arg. The
        end-to-end dispatcher invocation surfaced that the hook never matched.
        """
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            msg = f"{td}/msg.txt"
            _touch(msg, age_seconds=120)
            cmd = (
                'git -c user.name="Aino Virtanen" '
                '-c user.email="parametrization+Aino.Virtanen@gmail.com" '
                f"commit -F {msg}"
            )
            result = hook.check(_bash(cmd))
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["decision"], "block")
            self.assertIn(msg, result["reason"])


class ExtractionTests(unittest.TestCase):
    """Direct coverage of _extract_tmp_paths tokenizer behavior."""

    def test_extracts_git_F_path(self):
        self.assertEqual(
            hook._extract_tmp_paths("git commit -F /tmp/msg.txt"),
            ["/tmp/msg.txt"],
        )

    def test_extracts_gh_body_file_path(self):
        self.assertEqual(
            hook._extract_tmp_paths("gh pr create --body-file /tmp/body.md --title x"),
            ["/tmp/body.md"],
        )

    def test_skips_non_tmp_paths(self):
        self.assertEqual(
            hook._extract_tmp_paths("git commit -F .claude/scratch/msg.txt"),
            [],
        )

    def test_extracts_multiple_paths_in_compound_command(self):
        cmd = "git commit -F /tmp/a.txt && gh pr create --title x --body-file /tmp/b.md"
        self.assertEqual(
            sorted(hook._extract_tmp_paths(cmd)),
            ["/tmp/a.txt", "/tmp/b.md"],
        )

    def test_extracts_equals_form_body_file(self):
        """--body-file=<path> equals form must yield the path."""
        self.assertEqual(
            hook._extract_tmp_paths("gh issue create --body-file=/tmp/eq.md"),
            ["/tmp/eq.md"],
        )

    def test_extracts_gh_api_input_path(self):
        """`gh api ... --input <path>` yields the path."""
        self.assertEqual(
            hook._extract_tmp_paths("gh api repos/x/y/issues -X POST --input /tmp/payload.json"),
            ["/tmp/payload.json"],
        )

    def test_extracts_gh_api_input_equals_form(self):
        """`gh api ... --input=<path>` equals form yields the path."""
        self.assertEqual(
            hook._extract_tmp_paths("gh api repos/x/y/issues -X POST --input=/tmp/payload.json"),
            ["/tmp/payload.json"],
        )

    def test_heredoc_body_paths_ignored(self):
        """Paths mentioned inside heredoc bodies are stripped before tokenization."""
        cmd = (
            "gh issue create --body-file /tmp/fresh.md <<EOF\n"
            "see /tmp/old-doc-reference.md for prior context\n"
            "EOF"
        )
        self.assertEqual(
            hook._extract_tmp_paths(cmd),
            ["/tmp/fresh.md"],
        )

    def test_positional_tmp_in_redirect_ignored(self):
        """`gh pr view 42 > /tmp/out.txt` must yield NO paths (no body-file flag)."""
        self.assertEqual(
            hook._extract_tmp_paths("gh pr view 42 > /tmp/out.txt"),
            [],
        )

    def test_git_log_tmp_in_grep_arg_ignored(self):
        """`git log --grep /tmp/foo` must yield NO paths (git log is not covered)."""
        self.assertEqual(
            hook._extract_tmp_paths("git log --grep /tmp/foo"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
