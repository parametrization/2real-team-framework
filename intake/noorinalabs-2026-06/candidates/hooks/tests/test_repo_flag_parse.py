#!/usr/bin/env python3
"""Tests for `_repo_flag_parse` shared helper.

Consolidates `--repo` / `-R` extraction across `validate_labels.py` and
`validate_review_comment_format.py`. Covers all four flag forms gh CLI
accepts (space-form / equals-form × long / short) plus the regex
fallback used when shlex tokenization fails on malformed input.

Issue #510 origin: filed during #509 review when I noticed
`validate_review_comment_format.extract_repo_from_command` recognized
only `--repo X` while `validate_labels.extract_repo` already recognized
all four forms — a latent #503-class regression risk (cross-repo block
silently misfires through `--repo=` / `-R` flag spellings).

Run: python3 -m pytest .claude/hooks/tests/test_repo_flag_parse.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import _repo_flag_parse as parser  # noqa: E402


class FourFormsTests(unittest.TestCase):
    """All four `gh` flag forms must parse to the same OWNER/REPO value."""

    EXPECTED = "noorinalabs/noorinalabs-deploy"

    def test_long_space_form(self):
        """`--repo OWNER/NAME` — charter convention; the dominant shape."""
        cmd = f"gh pr comment 314 --repo {self.EXPECTED} --body x"
        self.assertEqual(parser.extract_repo(cmd), self.EXPECTED)

    def test_long_equals_form(self):
        """`--repo=OWNER/NAME` — gh accepts this; pre-#510 the
        review-comment hook silently fell back to cwd, recreating the
        #503 cross-repo false-block."""
        cmd = f"gh pr comment 314 --repo={self.EXPECTED} --body x"
        self.assertEqual(parser.extract_repo(cmd), self.EXPECTED)

    def test_short_space_form(self):
        """`-R OWNER/NAME` — gh's documented short flag."""
        cmd = f"gh pr comment 314 -R {self.EXPECTED} --body x"
        self.assertEqual(parser.extract_repo(cmd), self.EXPECTED)

    def test_short_equals_form(self):
        """`-R=OWNER/NAME` — short flag + equals separator."""
        cmd = f"gh pr comment 314 -R={self.EXPECTED} --body x"
        self.assertEqual(parser.extract_repo(cmd), self.EXPECTED)


class MixedWithOtherFlagsTests(unittest.TestCase):
    """`--repo` co-existing with other flags must not false-match."""

    def test_after_body_flag(self):
        cmd = 'gh pr comment 99 --body "ok" --repo owner/repo'
        self.assertEqual(parser.extract_repo(cmd), "owner/repo")

    def test_before_label_flag(self):
        cmd = "gh issue create --repo owner/repo --label bug --title t --body b"
        self.assertEqual(parser.extract_repo(cmd), "owner/repo")

    def test_no_repo_substring_in_other_flag_false_matches(self):
        """A flag like `--no-repo` (or any unrelated long flag containing
        `repo` substring) must NOT match. Anchoring on token boundary
        prevents this — the test pins the protection."""
        cmd = "gh foo --no-repo --bar baz"
        self.assertIsNone(parser.extract_repo(cmd))

    def test_repo_inside_quoted_body_does_not_match(self):
        """A reviewer body containing the literal text `--repo` inside a
        quoted comment must not be parsed as a real flag — tokenizer path
        treats the quoted argument as a single opaque token, so the
        token-walk sees `gh`, `pr`, `comment`, `99`, `--body`, `<one-token>`."""
        cmd = 'gh pr comment 99 --body "discussed --repo owner/repo in #123"'
        self.assertIsNone(parser.extract_repo(cmd))


class AbsentAndMalformedTests(unittest.TestCase):
    """`--repo` absent or malformed → None (callers fail-open)."""

    def test_absent_returns_none(self):
        cmd = "gh pr comment 99 --body x"
        self.assertIsNone(parser.extract_repo(cmd))

    def test_empty_string_returns_none(self):
        self.assertIsNone(parser.extract_repo(""))

    def test_trailing_flag_no_value_returns_none(self):
        """`gh foo --repo` with nothing after → no capturable value.
        gh itself would error; we just return None so the caller falls
        back to cwd-default + breadcrumb log."""
        cmd = "gh pr comment 99 --repo"
        self.assertIsNone(parser.extract_repo(cmd))


class RegexFallbackTests(unittest.TestCase):
    """When `_shell_parse.tokenize` returns None (malformed shell), the
    helper falls back to the conservative regex. Both paths must agree
    on the four supported forms."""

    @staticmethod
    def _malformed(value_form: str) -> str:
        """Build a command with an unbalanced quote so shlex fails, then
        append the flag-under-test. The regex fallback must still find it."""
        return f"echo 'unterminated && gh pr comment 99 {value_form} --body x"

    def test_fallback_long_space(self):
        cmd = self._malformed("--repo owner/repo")
        self.assertEqual(parser.extract_repo(cmd), "owner/repo")

    def test_fallback_long_equals(self):
        cmd = self._malformed("--repo=owner/repo")
        self.assertEqual(parser.extract_repo(cmd), "owner/repo")

    def test_fallback_short_space(self):
        cmd = self._malformed("-R owner/repo")
        self.assertEqual(parser.extract_repo(cmd), "owner/repo")

    def test_fallback_short_equals(self):
        cmd = self._malformed("-R=owner/repo")
        self.assertEqual(parser.extract_repo(cmd), "owner/repo")

    def test_fallback_absent_returns_none(self):
        cmd = self._malformed("--label bug")
        self.assertIsNone(parser.extract_repo(cmd))


class IssueOrigin503ReproTests(unittest.TestCase):
    """Pin the exact #503 / #509 / #510 lineage shape on a real-world
    cross-repo verdict-comment command. If a future regression silently
    drops one of the alternate flag forms back to cwd-default, this
    fixture surfaces it."""

    def test_503_canonical_command_extracts_deploy_repo(self):
        cmd = (
            "gh pr comment 314 --repo noorinalabs/noorinalabs-deploy "
            '--body "Requestor: Aino Virtanen\nRequestee: Nurul Hakim\n'
            'RequestOrReplied: Approved\nTechDebt: none"'
        )
        self.assertEqual(parser.extract_repo(cmd), "noorinalabs/noorinalabs-deploy")

    def test_503_with_equals_form_also_extracts(self):
        """Post-#510: the equals-form variant of the same command also
        resolves to the deploy repo (was returning None pre-#510 →
        cross-repo block would silently misfire)."""
        cmd = (
            "gh pr comment 314 --repo=noorinalabs/noorinalabs-deploy "
            '--body "Requestor: Aino Virtanen\nRequestee: Nurul Hakim\n'
            'RequestOrReplied: Approved\nTechDebt: none"'
        )
        self.assertEqual(parser.extract_repo(cmd), "noorinalabs/noorinalabs-deploy")


if __name__ == "__main__":
    unittest.main()
