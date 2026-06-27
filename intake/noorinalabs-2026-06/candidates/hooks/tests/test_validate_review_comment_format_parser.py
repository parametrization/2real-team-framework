#!/usr/bin/env python3
"""Fixture-driven Direction-table tests for validate_review_comment_format hook.

Each JSON file in fixtures/validate_review_comment_format/ is one test case:

    {
        "description": "<human label>",
        "command": "<raw bash command string>",
        "branch_ref": "<head ref name returned by get_branch_name() mock>",
        "expect": "allow" | "block:<reason-keyword>"
    }

The `branch_ref` field is mocked into `validate_review_comment_format.get_branch_name`
so tests do not hit the network. The `expect` field:
  - "allow"      → check() must return None
  - "block:<kw>" → check() must return a block decision; <kw> is a
                   substring of the reason (case-insensitive) for
                   self-documenting test output, not strict matching.

Fixtures cover the four `RequestOrReplied` Direction-table values
(charter pull-requests.md § Comment-Based Reviews):
  - Approved / ChangesRequested — verdict directions, swap heuristic in
    scope. Post-#386 the heuristic compares
    `Requestor.lastname == branch-author.lastname` (block when the PR
    author is being named as the reviewer — the post-#244 swap shape).
  - Request / Reply — role bindings inverted in the charter Direction
    table; hook narrows OOS (allow). Coverage shows that the canonical
    Request/Reply shape (which has Requestor=PR-author=branch-author)
    would block under verdict scope, but path-2 narrowing protects them.
  - Unrecognized value — fail-open (allow); the hook does not validate
    the verdict word itself, that is `validate_pr_review`'s scope.

Run:  python3 -m pytest .claude/hooks/tests/test_validate_review_comment_format_parser.py -v
      (or the full suite: python3 -m pytest .claude/hooks/tests/ -v)
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
_FIXTURES_DIR = _HOOKS_DIR / "fixtures" / "validate_review_comment_format"

sys.path.insert(0, str(_HOOKS_DIR))

import validate_review_comment_format as hook  # noqa: E402


def _load_fixtures() -> list[tuple[str, dict]]:
    """Return (fixture_name, fixture_data) pairs for every JSON in the fixture dir."""
    fixtures = []
    for path in sorted(_FIXTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        fixtures.append((path.stem, data))
    return fixtures


def _make_input(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class FixtureDrivenDirectionTableTests(unittest.TestCase):
    """One test method per fixture file — generated dynamically."""


def _add_fixture_test(name: str, fixture: dict) -> None:
    """Attach a test method to FixtureDrivenDirectionTableTests for `fixture`."""
    description = fixture.get("description", name)
    command = fixture["command"]
    branch_ref = fixture.get("branch_ref", "")
    expect = fixture["expect"]

    def test_method(self: unittest.TestCase) -> None:
        with mock.patch.object(hook, "get_branch_name", return_value=branch_ref):
            result = hook.check(_make_input(command))
        if expect == "allow":
            self.assertIsNone(
                result,
                f"{description!r}: expected allow (None) but got: {result}",
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
    setattr(FixtureDrivenDirectionTableTests, test_method.__name__, test_method)


for _fixture_name, _fixture_data in _load_fixtures():
    _add_fixture_test(_fixture_name, _fixture_data)


class Post244InversionRegressionTests(unittest.TestCase):
    """Explicit regression: the post-#386 heuristic compares Requestor, not Requestee.

    Pre-#386 the heuristic checked `Requestee.lastname == branch-author`, which
    encoded the pre-#244 reading where Requestee was expected to be the
    reviewer. Post-#244 the charter inverts the bindings for verdict comments
    (Requestor=reviewer, Requestee=PR-author=branch-author). The heuristic was
    realigned in #386.

    These tests pin the direction of the inversion. If they break, someone is
    re-introducing the pre-#244 semantics — STOP and read charter
    pull-requests.md § Comment-Based Reviews Direction table before "fixing"
    them.
    """

    BRANCH = "A.Virtanen/0386-direction-table-realign"
    REVIEWER = "Nadia Khoury"
    PR_AUTHOR = "Aino Virtanen"  # matches BRANCH author lastname

    def _cmd(self, requestor: str, requestee: str, direction: str = "Approved") -> str:
        return (
            "gh pr comment 42 --body \"$(cat <<'EOF'\n"
            f"Requestor: {requestor}\n"
            f"Requestee: {requestee}\n"
            f"RequestOrReplied: {direction}\n"
            "TechDebt: none\n"
            'EOF\n)"'
        )

    def test_canonical_post244_verdict_shape_allows(self):
        """Requestor=reviewer (Khoury), Requestee=PR-author=branch-author (Virtanen) → allow.

        Under PRE-#386 semantics this same body would have BLOCKED (Requestee
        matched branch). Under POST-#386 inverted semantics it must ALLOW.
        """
        with mock.patch.object(hook, "get_branch_name", return_value=self.BRANCH):
            result = hook.check(_make_input(self._cmd(self.REVIEWER, self.PR_AUTHOR)))
        self.assertIsNone(
            result,
            "Post-#244 canonical verdict shape (Requestor=reviewer, Requestee=PR-author) "
            "must be ALLOWED by the inverted heuristic. If this fails, the heuristic "
            "may have been reverted to the pre-#244 reading.",
        )

    def test_post244_swap_shape_blocks(self):
        """Requestor=PR-author=branch-author (Virtanen) → BLOCK with post-#386 reason.

        Pre-#386 the same body would have ALLOWED (Requestee was Khoury, not
        the branch author). Post-#386 the inverted heuristic catches it.
        """
        with mock.patch.object(hook, "get_branch_name", return_value=self.BRANCH):
            result = hook.check(_make_input(self._cmd(self.PR_AUTHOR, self.REVIEWER)))
        self.assertIsNotNone(result, "Post-#244 swap shape must BLOCK")
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        # The post-#386 BLOCKED-message describes the inverted semantics —
        # the branch author should be the Requestee, not the Requestor.
        self.assertIn("Requestee, not the Requestor", result["reason"])

    def test_blocked_message_uses_post244_language(self):
        """The BLOCKED message must reference 'reviewer' for Requestor and
        'PR author' for Requestee.
        """
        with mock.patch.object(hook, "get_branch_name", return_value=self.BRANCH):
            result = hook.check(_make_input(self._cmd(self.PR_AUTHOR, self.REVIEWER)))
        assert result is not None
        reason = result["reason"]
        self.assertIn("Requestor should be the reviewer", reason)
        self.assertIn("Requestee should be the PR author", reason)


class DirectionVerdictHelperTests(unittest.TestCase):
    """Direct coverage of `_direction_is_verdict` shape."""

    def _body(self, direction: str) -> str:
        return f"Requestor: A\nRequestee: B\nRequestOrReplied: {direction}"

    def test_approved_verdict(self):
        self.assertTrue(hook._direction_is_verdict(self._body("Approved")))

    def test_changes_requested_camelcase_verdict(self):
        self.assertTrue(hook._direction_is_verdict(self._body("ChangesRequested")))

    def test_changes_requested_two_word_verdict(self):
        """`Changes Requested` (space-separated) — the form validate_pr_review counts.

        Per feedback_validate_pr_review_approved_not_reply.md, the literal
        two-word form is the one the sibling hook counts. Both forms must
        be recognized here.
        """
        self.assertTrue(hook._direction_is_verdict(self._body("Changes Requested")))

    def test_approved_lowercase_verdict(self):
        self.assertTrue(hook._direction_is_verdict(self._body("approved")))

    def test_approved_markdown_bold_verdict(self):
        """`**Approved**` markdown bolding is stripped before comparison."""
        self.assertTrue(hook._direction_is_verdict(self._body("**Approved**")))

    def test_approved_with_trailing_token_verdict(self):
        """Trailing parenthetical / explanatory text after the verdict word allowed."""
        self.assertTrue(hook._direction_is_verdict(self._body("Approved (post-merge)")))

    def test_request_not_verdict(self):
        self.assertFalse(hook._direction_is_verdict(self._body("Request")))

    def test_reply_not_verdict(self):
        self.assertFalse(hook._direction_is_verdict(self._body("Reply")))

    def test_unknown_not_verdict(self):
        self.assertFalse(hook._direction_is_verdict(self._body("Asdf")))

    def test_bare_changes_not_verdict(self):
        """`Changes` alone (without `Requested`) is NOT a verdict — must NOT match.

        Defensive guard: tolerating the bare prefix would over-narrow and
        leave legitimate non-verdict comments mis-classified as verdicts.
        """
        self.assertFalse(hook._direction_is_verdict(self._body("Changes")))

    def test_empty_value_not_verdict(self):
        self.assertFalse(hook._direction_is_verdict("Requestor: A\nRequestOrReplied: "))

    def test_missing_label_not_verdict(self):
        self.assertFalse(hook._direction_is_verdict("Requestor: A\nRequestee: B"))


if __name__ == "__main__":
    unittest.main()
