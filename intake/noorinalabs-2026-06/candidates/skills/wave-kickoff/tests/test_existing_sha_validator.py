#!/usr/bin/env python3
"""Tests for the EXISTING_SHA shape validator in wave-kickoff Step 1.

The validator guards against gh api returning the raw 404 JSON error body when
a branch doesn't exist, which was captured live during P3W7 kickoff (e906e135).

Run:
    ENVIRONMENT=test python3 -m pytest \
        .claude/skills/wave-kickoff/tests/test_existing_sha_validator.py -v
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _apply_validator(raw: str) -> str:
    """Mirror the bash validator: return raw if valid 40-hex, else empty string."""
    if SHA_PATTERN.match(raw):
        return raw
    return ""


def _jq_object_sha(fixture_path: Path) -> str:
    """Run jq '.object.sha' against fixture, returning raw stdout (mirrors gh api --jq)."""
    result = subprocess.run(
        ["jq", "-r", ".object.sha"],
        input=fixture_path.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class TestExistingShaValidator(unittest.TestCase):
    def test_404_body_yields_empty(self):
        """Live-trigger fixture: 404 JSON error body must produce EXISTING_SHA=""."""
        fixture = _FIXTURES / "existing_sha_404.json"
        data = json.loads(fixture.read_text())
        self.assertEqual(data["status"], "404")

        raw_jq = _jq_object_sha(fixture)
        result = _apply_validator(raw_jq)
        self.assertEqual(result, "", f"Expected empty, got [{result!r}] from 404 body")

    def test_happy_path_preserves_sha(self):
        """Valid 40-hex commit SHA must be preserved unchanged."""
        fixture = _FIXTURES / "existing_sha_happy.json"
        data = json.loads(fixture.read_text())
        expected_sha = data["object"]["sha"]
        self.assertRegex(expected_sha, r"^[0-9a-f]{40}$")

        raw_jq = _jq_object_sha(fixture)
        result = _apply_validator(raw_jq)
        self.assertEqual(result, expected_sha)

    def test_null_sha_yields_empty(self):
        """When jq returns 'null' string (object.sha is JSON null), validator must clear it."""
        fixture = _FIXTURES / "existing_sha_null_jq.json"
        raw_jq = _jq_object_sha(fixture)
        self.assertEqual(raw_jq, "null")

        result = _apply_validator(raw_jq)
        self.assertEqual(result, "", f"Expected empty for null sha, got [{result!r}]")

    def test_tag_ref_sha_preserved(self):
        """Tag ref SHA (still 40-hex) must pass through validator unchanged."""
        fixture = _FIXTURES / "existing_sha_tag_ref.json"
        data = json.loads(fixture.read_text())
        expected_sha = data["object"]["sha"]
        self.assertRegex(expected_sha, r"^[0-9a-f]{40}$")

        raw_jq = _jq_object_sha(fixture)
        result = _apply_validator(raw_jq)
        self.assertEqual(result, expected_sha)

    def test_raw_404_string_capture_yields_empty(self):
        """When EXISTING_SHA holds the raw 404 JSON body string (no jq), validator clears it."""
        raw = '{"message":"Not Found","documentation_url":"https://docs.github.com/rest/git/refs#get-all-references-in-a-namespace","status":"404"}'
        result = _apply_validator(raw)
        self.assertEqual(result, "", f"Expected empty, got [{result!r}]")

    def test_empty_string_yields_empty(self):
        """Empty string (e.g. api call failed entirely) must stay empty."""
        self.assertEqual(_apply_validator(""), "")

    def test_short_hex_rejected(self):
        """A SHA shorter than 40 hex chars must not pass (truncated/corrupt output)."""
        self.assertEqual(_apply_validator("abc123"), "")

    def test_uppercase_hex_rejected(self):
        """GitHub SHAs are lowercase; uppercase must be rejected as non-canonical."""
        self.assertEqual(_apply_validator("E906E135D811CDE" + "a" * 25), "")


if __name__ == "__main__":
    unittest.main()
