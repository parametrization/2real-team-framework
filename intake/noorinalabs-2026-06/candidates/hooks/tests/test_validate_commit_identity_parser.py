#!/usr/bin/env python3
"""Fixture-driven parser tests for validate_commit_identity hook.

Each JSON file in fixtures/validate_commit_identity/ is one test case:

    {
        "description": "<human label>",
        "command": "<raw bash command string>",
        "expect": "allow" | "block:<reason-keyword>"
    }

The `expect` field:
  - "allow"         → check() must return None
  - "block:<kw>"    → check() must return a block decision; <kw> is a
                      substring of the reason (case-insensitive) for
                      self-documenting test output, not strict matching.

Run:  python3 -m pytest .claude/hooks/tests/test_validate_commit_identity_parser.py -v
      (or the full suite: python3 -m pytest .claude/hooks/tests/ -v)

Covers:
  Bug shape  — backslash-line-continuation (#287)
  Happy path — single-line, -F file, multi -c, --amend
  Adjacent   — heredoc -m, gpg -c, worktree add with 'commit' in branch name
  Negative   — missing name, missing email, mismatched email, unrecognized name
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
_FIXTURES_DIR = _HOOKS_DIR / "fixtures" / "validate_commit_identity"

sys.path.insert(0, str(_HOOKS_DIR))

import validate_commit_identity as hook  # noqa: E402


def _load_fixtures() -> list[tuple[str, dict]]:
    """Return (fixture_name, fixture_data) pairs for every JSON in the fixture dir."""
    fixtures = []
    for path in sorted(_FIXTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        fixtures.append((path.stem, data))
    return fixtures


def _make_input(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class FixtureDrivenParserTests(unittest.TestCase):
    """One test method per fixture file — generated dynamically."""


def _add_fixture_test(name: str, fixture: dict) -> None:
    """Attach a test method to FixtureDrivenParserTests for `fixture`."""
    description = fixture.get("description", name)
    command = fixture["command"]
    expect = fixture["expect"]

    def test_method(self: unittest.TestCase) -> None:
        result = hook.check(_make_input(command))
        if expect == "allow":
            self.assertIsNone(
                result,
                f"{description!r}: expected allow (None) but got block: {result}",
            )
        elif expect.startswith("block:"):
            self.assertIsNotNone(
                result,
                f"{description!r}: expected block but got allow (None)",
            )
            assert result is not None  # for mypy
            self.assertEqual(
                result.get("decision"),
                "block",
                f"{description!r}: result decision is not 'block': {result}",
            )
        else:
            raise ValueError(f"Unknown expect value {expect!r} in fixture {name!r}")

    test_method.__name__ = f"test_{name}"
    test_method.__doc__ = description
    setattr(FixtureDrivenParserTests, test_method.__name__, test_method)


for _fixture_name, _fixture_data in _load_fixtures():
    _add_fixture_test(_fixture_name, _fixture_data)


class LineContinuationNormalizationTests(unittest.TestCase):
    """Unit tests for the backslash-newline normalization in _shell_parse.tokenize."""

    def test_backslash_newline_not_in_tokens(self):
        """After normalization, no newline char token appears in the output."""
        import _shell_parse as sp

        cmd = 'git -c user.name="X" \\\n    -c user.email="y@z.com" commit -m "m"'
        tokens = sp.tokenize(cmd)
        self.assertIsNotNone(tokens)
        self.assertNotIn("\n", tokens, "Newline char must not appear as a standalone token")
        self.assertNotIn("n", tokens, "Stray 'n' token must not appear after normalization")

    def test_commit_subcommand_found_after_continuation(self):
        """find_git_subcommand resolves to 'commit' even with backslash-continuation."""
        import _shell_parse as sp

        cmd = 'git -c user.name="X" \\\n    -c user.email="y@z.com" \\\n    commit -m "m"'
        tokens = sp.tokenize(cmd)
        self.assertIsNotNone(tokens)
        for seg in sp.iter_command_segments(tokens):
            decoded = sp.find_git_subcommand(seg)
            if decoded is not None:
                _globals, rest = decoded
                if rest and rest[0] == "commit":
                    return  # found it
        self.fail(
            "commit subcommand not found in tokens after backslash-continuation normalization"
        )

    def test_normalization_does_not_break_quoted_values(self):
        """Quoted values containing literal spaces survive normalization correctly."""
        import _shell_parse as sp

        cmd = 'git -c user.name="Aino Virtanen" \\\n    commit -m "multi word message"'
        tokens = sp.tokenize(cmd)
        self.assertIsNotNone(tokens)
        self.assertIn("user.name=Aino Virtanen", tokens)
        self.assertIn("multi word message", tokens)


if __name__ == "__main__":
    unittest.main()
