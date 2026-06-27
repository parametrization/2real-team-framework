"""Tests for pr_review_state — the deterministic review-state query CLI (#707).

The driver REUSES validate_pr_review's functions, so these tests mock those
gate functions (never the network). Coverage:
  1. 0 distinct Approved -> gate would BLOCK (exit 1).
  2. 1 distinct Approved (no exception) -> BLOCK (exit 1).
  3. 2 distinct Approved, all TechDebt present -> PASS (exit 0).
  4. A verdict missing the TechDebt line -> BLOCK even with 2 reviewers (exit 1).
  5. wave-bootstrap single-reviewer exception -> PASS with one reviewer (exit 0).
  6. branch-author self-review exclusion: the lastname parsed from the head ref
     is the one passed into check_comment_reviews (the gate excludes a same-
     lastname Requestor).
  7. non-roster Approved Requestor is filtered out of the reviewer count.
  8. a PR-fetch failure -> ReviewStateError -> CLI exit 2.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

# Helper lives at .claude/lib/pr_review_state.py; test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pr_review_state as prs  # noqa: E402


def _comment_result(
    reviewers=(), missing_tech_debt=(), tech_debt_issues=()
) -> "prs.gate.CommentReviewResult":
    """Build a CommentReviewResult like check_comment_reviews would return.

    `reviewers` are full names (any case); they are stored lowercased, matching
    the gate's dedup key.
    """
    result = prs.gate.CommentReviewResult()
    result.reviewers = {r.lower() for r in reviewers}
    result.reviews_missing_tech_debt = list(missing_tech_debt)
    result.tech_debt_issue_numbers = list(tech_debt_issues)
    return result


def _pr_data(
    *, author="someauthor", head_ref="S.Ferreira/0707-pr-review-state", labels=(), reviews=()
) -> dict:
    return {
        "author": author,
        "number": "707",
        "reviews": list(reviews),
        "headRefName": head_ref,
        "labels": list(labels),
    }


class ComputeReviewStateTests(unittest.TestCase):
    def _run(
        self,
        *,
        pr_data,
        comment_result,
        roster_names,
        single_reviewer_exception=False,
    ) -> prs.ReviewState:
        with (
            mock.patch.object(prs.gate, "get_pr_data", return_value=pr_data),
            mock.patch.object(prs.gate, "check_comment_reviews", return_value=comment_result),
            mock.patch.object(prs.gate, "_load_roster_names", return_value=roster_names),
            mock.patch.object(
                prs.gate, "is_single_reviewer_exception", return_value=single_reviewer_exception
            ),
        ):
            return prs.compute_review_state("707", repo="noorinalabs/noorinalabs-main")

    def test_zero_approved_blocks(self):
        state = self._run(
            pr_data=_pr_data(),
            comment_result=_comment_result(reviewers=()),
            roster_names=set(),
        )
        self.assertEqual(state.distinct_reviewer_count, 0)
        self.assertFalse(state.passes())

    def test_one_approved_blocks_without_exception(self):
        state = self._run(
            pr_data=_pr_data(),
            comment_result=_comment_result(reviewers=("Aino Virtanen",)),
            roster_names={"aino virtanen"},
        )
        self.assertEqual(state.distinct_reviewer_count, 1)
        self.assertFalse(state.passes())

    def test_two_approved_passes(self):
        state = self._run(
            pr_data=_pr_data(),
            comment_result=_comment_result(
                reviewers=("Aino Virtanen", "Nadia Khoury"),
                tech_debt_issues=("808",),
            ),
            roster_names={"aino virtanen", "nadia khoury"},
        )
        self.assertEqual(state.distinct_reviewer_count, 2)
        self.assertEqual(state.tech_debt_issue_numbers, ["808"])
        self.assertTrue(state.passes())

    def test_two_approved_but_missing_tech_debt_blocks(self):
        state = self._run(
            pr_data=_pr_data(),
            comment_result=_comment_result(
                reviewers=("Aino Virtanen", "Nadia Khoury"),
                missing_tech_debt=("Nadia Khoury",),
            ),
            roster_names={"aino virtanen", "nadia khoury"},
        )
        self.assertEqual(state.distinct_reviewer_count, 2)
        self.assertEqual(state.reviews_missing_tech_debt, ["Nadia Khoury"])
        self.assertFalse(state.passes())

    def test_wave_bootstrap_single_reviewer_passes(self):
        state = self._run(
            pr_data=_pr_data(labels=("wave-bootstrap",)),
            comment_result=_comment_result(reviewers=("Aino Virtanen",)),
            roster_names={"aino virtanen"},
            single_reviewer_exception=True,
        )
        self.assertEqual(state.distinct_reviewer_count, 1)
        self.assertTrue(state.wave_bootstrap_exception)
        self.assertTrue(state.passes())

    def test_branch_author_lastname_passed_to_check(self):
        """The lastname parsed from the head ref drives the gate's self-review
        exclusion, so it must be the value handed to check_comment_reviews."""
        captured = {}

        def fake_check(number, lastname, repo=None):
            captured["number"] = number
            captured["lastname"] = lastname
            return _comment_result(reviewers=())

        with (
            mock.patch.object(
                prs.gate,
                "get_pr_data",
                return_value=_pr_data(head_ref="S.Ferreira/0707-pr-review-state"),
            ),
            mock.patch.object(prs.gate, "check_comment_reviews", side_effect=fake_check),
            mock.patch.object(prs.gate, "_load_roster_names", return_value=set()),
            mock.patch.object(prs.gate, "is_single_reviewer_exception", return_value=False),
        ):
            state = prs.compute_review_state("707", repo="noorinalabs/noorinalabs-main")

        self.assertEqual(captured["lastname"], "Ferreira")
        self.assertEqual(state.branch_author_lastname, "Ferreira")

    def test_non_roster_requestor_excluded_from_count(self):
        """An Approved Requestor not in the roster is filtered out (#498) and
        does not count toward the threshold."""
        state = self._run(
            pr_data=_pr_data(),
            comment_result=_comment_result(
                reviewers=("Aino Virtanen", "Imelda Santos"),
            ),
            roster_names={"aino virtanen"},  # Imelda is NOT a roster persona
        )
        self.assertEqual(state.comment_reviewers, ["aino virtanen"])
        self.assertEqual(state.non_roster_requestors, ["imelda santos"])
        self.assertEqual(state.distinct_reviewer_count, 1)
        self.assertFalse(state.passes())

    def test_fetch_failure_raises(self):
        with mock.patch.object(prs.gate, "get_pr_data", return_value=None):
            with self.assertRaises(prs.ReviewStateError):
                prs.compute_review_state("707", repo="noorinalabs/noorinalabs-main")


class CliExitCodeTests(unittest.TestCase):
    def _main(self, state_or_exc):
        if isinstance(state_or_exc, Exception):
            cm = mock.patch.object(prs, "compute_review_state", side_effect=state_or_exc)
        else:
            cm = mock.patch.object(prs, "compute_review_state", return_value=state_or_exc)
        with cm:
            return prs.main(["707", "--repo", "noorinalabs/noorinalabs-main"])

    def _state(self, *, count, missing=(), exception=False):
        return prs.ReviewState(
            pr_number="707",
            repo="noorinalabs/noorinalabs-main",
            head_ref="S.Ferreira/0707-pr-review-state",
            branch_author_lastname="Ferreira",
            formal_reviewers=[],
            comment_reviewers=[],
            non_roster_requestors=[],
            distinct_reviewer_count=count,
            wave_bootstrap_exception=exception,
            reviews_missing_tech_debt=list(missing),
            tech_debt_issue_numbers=[],
        )

    def test_exit_zero_on_pass(self):
        self.assertEqual(self._main(self._state(count=2)), 0)

    def test_exit_one_on_too_few_reviewers(self):
        self.assertEqual(self._main(self._state(count=1)), 1)

    def test_exit_one_on_missing_tech_debt(self):
        self.assertEqual(self._main(self._state(count=2, missing=("Nadia Khoury",))), 1)

    def test_exit_two_on_undeterminable(self):
        self.assertEqual(self._main(prs.ReviewStateError("boom")), 2)


if __name__ == "__main__":
    unittest.main()
