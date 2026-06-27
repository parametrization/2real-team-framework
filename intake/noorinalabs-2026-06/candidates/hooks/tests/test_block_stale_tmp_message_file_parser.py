#!/usr/bin/env python3
"""Fixture-driven parser tests for block_stale_tmp_message_file hook.

Each JSON file in fixtures/block_stale_tmp_message_file/ is one test case:

    {
        "description": "<human label>",
        "command": "<raw bash command string>",
        "expect": "allow" | "block:<reason-keyword>"
    }

The `expect` field:
  - "allow"      → check() must return None
  - "block:<kw>" → check() must return a block decision; <kw> is a
                   substring of the reason (case-insensitive) for
                   self-documenting test output, not strict matching.

Fixtures cover PARSER-DISCRIMINATION cases only (does the tokenizer
correctly identify the body-file flag value vs incidental /tmp/* mentions?).
The mtime-staleness gate is exercised separately by the unit tests in
test_block_stale_tmp_message_file.py which use tempfile + os.utime to
control file freshness. Encoding mtime state in static JSON fixtures is not
attempted — that is not what fixtures are for.

Run:  python3 -m pytest .claude/hooks/tests/test_block_stale_tmp_message_file_parser.py -v
      (or the full suite: python3 -m pytest .claude/hooks/tests/ -v)

Covers:
  Bug shape  — heredoc-body /tmp/* mention (W7 retro 2026-05-08)
  Bug shape  — code-fence /tmp/* mention inside heredoc
  Bug shape  — positional /tmp redirect target (`> /tmp/out`)
  Happy path — --body-file /tmp/<fresh>
  Happy path — --body-file=<path> equals form
  Happy path — gh api --input /tmp/<path>
  Adjacent   — full charter git -c identity flags + -F /tmp/<path>
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
_FIXTURES_DIR = _HOOKS_DIR / "fixtures" / "block_stale_tmp_message_file"

sys.path.insert(0, str(_HOOKS_DIR))

import block_stale_tmp_message_file as hook  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
