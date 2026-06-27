#!/usr/bin/env python3
"""Tests for validate_pr_review hook.

Covers:
- Issue #147: TechDebt attestation must be required ONLY on actual review
  verdicts (Approved / ChangesRequested), NOT on Request or Reply comments.
- Issue #164: reviewer set must dedup on full reviewer name, NOT on
  lastname — two distinct reviewers sharing a lastname (e.g.,
  Lucas Ferreira and Santiago Ferreira) count as TWO reviewers.
- Issue #244: reviewer for verdict comments is the Requestor (comment
  author), NOT the Requestee. Resolves the prior Requestee-as-reviewer
  mismatch with the canonical charter format (resolves #233).
- Issue #228: Single-Reviewer Exception for wave-bootstrap PRs reviewed
  by a charter-enforcer role.

Charter format used in fixtures (canonical per `pull-requests.md`
§ Comment-Based Reviews — Requestor=comment-author, Requestee=comment-target):
- Request comments     → Requestor=PR author,  Requestee=reviewer
- Reply comments       → Requestor=replier,    Requestee=being-replied-to
- Approved verdicts    → Requestor=reviewer,   Requestee=PR author
- ChangesRequested     → Requestor=reviewer,   Requestee=PR author

Also covers the W8 hook-authorship NEGATIVE-MATCH requirement.

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_validate_pr_review.py -v
Or:  ENVIRONMENT=test python3 .claude/hooks/tests/test_validate_pr_review.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_pr_review as hook  # noqa: E402


class IsVerdictTests(unittest.TestCase):
    """Unit tests for the _is_verdict helper — the core filter for #147."""

    def test_approved_is_verdict(self):
        self.assertTrue(hook._is_verdict("Approved"))

    def test_changes_requested_is_verdict(self):
        self.assertTrue(hook._is_verdict("Changes Requested"))

    def test_changes_alone_is_verdict(self):
        """Some teammates use the shorter `Changes` form — accepted per charter."""
        self.assertTrue(hook._is_verdict("Changes"))

    def test_case_insensitive(self):
        self.assertTrue(hook._is_verdict("approved"))
        self.assertTrue(hook._is_verdict("APPROVED"))
        self.assertTrue(hook._is_verdict("Changes REQUESTED"))

    def test_whitespace_trimmed(self):
        self.assertTrue(hook._is_verdict("  Approved  "))
        self.assertTrue(hook._is_verdict("\tApproved\n"))

    def test_markdown_bold_trailing_stripped(self):
        self.assertTrue(hook._is_verdict("Approved*"))
        self.assertTrue(hook._is_verdict("Approved**"))

    # NEGATIVE MATCHES — the whole point of #147.
    def test_request_is_not_verdict(self):
        """RequestOrReplied: Request is NOT a verdict (review request)."""
        self.assertFalse(hook._is_verdict("Request"))

    def test_replied_is_not_verdict(self):
        """RequestOrReplied: Replied is NOT a verdict (author reply)."""
        self.assertFalse(hook._is_verdict("Replied"))

    def test_empty_is_not_verdict(self):
        self.assertFalse(hook._is_verdict(""))
        self.assertFalse(hook._is_verdict("   "))

    def test_unknown_value_is_not_verdict(self):
        self.assertFalse(hook._is_verdict("Maybe"))
        self.assertFalse(hook._is_verdict("Questioned"))


class _CheckCommentReviewsHarness(unittest.TestCase):
    """Common helpers for driving check_comment_reviews() with fake API data."""

    PR_NUMBER = 99
    BRANCH_AUTHOR = "pham"  # matches branch L.Pham/0001-...
    REPO = "noorinalabs/noorinalabs-isnad-graph"

    @staticmethod
    def _run_with_fake_api(comments_list: list[dict], branch_author: str, repo: str | None = None):
        """Run check_comment_reviews with subprocess.run mocked to return the given comments."""
        # First call is gh repo view (owner/name), skipped if repo is provided.
        # Second call is gh api .../issues/{n}/comments.
        repo_view_stdout = json.dumps({"owner": {"login": "noorinalabs"}, "name": "r"})
        comments_stdout = json.dumps(comments_list)

        call_count = {"n": 0}

        def fake_run(args, capture_output, text, timeout):
            call_count["n"] += 1
            result = mock.MagicMock()
            result.returncode = 0
            if args[0] == "gh" and args[1:3] == ["repo", "view"]:
                result.stdout = repo_view_stdout
            else:
                result.stdout = comments_stdout
            return result

        with mock.patch.object(hook.subprocess, "run", side_effect=fake_run):
            return hook.check_comment_reviews(
                _CheckCommentReviewsHarness.PR_NUMBER,
                branch_author,
                repo=repo,
            )


class TechDebtFilterTests(_CheckCommentReviewsHarness):
    """Issue #147: TechDebt line required only on Approved/Changes Requested.

    Each test builds a fake comment list and verifies the
    reviews_missing_tech_debt list contains exactly the expected names.
    """

    @staticmethod
    def _comment(body: str) -> dict:
        return {"body": body, "user": {"login": "anyone"}}

    def test_request_without_techdebt_does_not_block(self):
        """NEGATIVE MATCH for #147: Request comment lacking TechDebt must NOT be flagged."""
        comments = [
            self._comment(
                "Requestor: Linh Pham\nRequestee: Jelani Mwangi\nRequestOrReplied: Request"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_replied_without_techdebt_does_not_block(self):
        """NEGATIVE MATCH for #147: Replied comment lacking TechDebt must NOT be flagged."""
        comments = [
            self._comment(
                "Requestor: Linh Pham\nRequestee: Anya Kowalczyk\nRequestOrReplied: Replied"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_approved_without_techdebt_does_block(self):
        """Positive: Approved lacking TechDebt MUST still be flagged — #147 does NOT weaken this.

        Canonical format (resolves #244): Requestor=reviewer, Requestee=PR author.
        """
        comments = [
            self._comment(
                "Requestor: Mateo Santos\nRequestee: Linh Pham\nRequestOrReplied: Approved"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, ["Mateo Santos"])

    def test_changes_requested_without_techdebt_does_block(self):
        comments = [
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Changes Requested"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, ["Anya Kowalczyk"])

    def test_approved_with_techdebt_none_passes(self):
        comments = [
            self._comment(
                "Requestor: Mateo Santos\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_approved_with_techdebt_issues_passes_and_collects(self):
        comments = [
            self._comment(
                "Requestor: Mateo Santos\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: #15, #16"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, [])
        self.assertEqual(sorted(result.tech_debt_issue_numbers), ["15", "16"])

    def test_pr_821_scenario(self):
        """Exact scenario from issue #147 repro, in canonical #244 format.

        PR #821 had 3 real reviews (Jelani+Anya approved, Anya changes-requested —
        all with TechDebt) and 4 non-review comments (3 Request, 1 Reply — no
        TechDebt). The hook blocked on the 4 non-review comments. After the fix,
        only actual-verdict comments without TechDebt should be flagged.

        Canonical format (#244): verdict comments swap to Requestor=reviewer.
        """
        comments = [
            # Review requests — Requestor=PR author, Requestee=reviewer (no TechDebt required)
            self._comment(
                "Requestor: Linh Pham\nRequestee: Jelani Mwangi\nRequestOrReplied: Request"
            ),
            self._comment(
                "Requestor: Linh Pham\nRequestee: Anya Kowalczyk\nRequestOrReplied: Request"
            ),
            # Verdicts — Requestor=reviewer, Requestee=PR author
            self._comment(
                "Requestor: Jelani Mwangi\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Changes Requested\nTechDebt: #200"
            ),
            # Author reply — Requestor=replier (Linh), Requestee=being-replied-to (Anya)
            self._comment(
                "Requestor: Linh Pham\nRequestee: Anya Kowalczyk\nRequestOrReplied: Replied"
            ),
            # Re-request for re-review after changes
            self._comment(
                "Requestor: Linh Pham\nRequestee: Anya Kowalczyk\nRequestOrReplied: Request"
            ),
            # Re-review approval — Requestor=reviewer (Anya)
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(
            result.reviews_missing_tech_debt, [], "non-verdict comments must not be flagged"
        )
        self.assertEqual(sorted(result.tech_debt_issue_numbers), ["200"])

    def test_markdown_bold_ror_value_still_filtered(self):
        """`**RequestOrReplied:** Request` with markdown bold — still not a verdict."""
        comments = [
            self._comment(
                "**Requestor:** Linh Pham\n"
                "**Requestee:** Jelani Mwangi\n"
                "**RequestOrReplied:** Request"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_markdown_bold_approved_still_requires_techdebt(self):
        comments = [
            self._comment(
                "**Requestor:** Mateo Santos\n"
                "**Requestee:** Linh Pham\n"
                "**RequestOrReplied:** Approved"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviews_missing_tech_debt, ["Mateo Santos"])


class ReviewerDedupTests(_CheckCommentReviewsHarness):
    """Issue #164: reviewer set must dedup on full name, NOT on lastname.

    Prior behavior keyed the set on lastname, so Lucas Ferreira and Santiago
    Ferreira counted as one reviewer. Guard tests for the full-name fix.

    Post-#244 reviewer identification uses Requestor on verdict comments;
    fixtures updated to canonical format (Requestor=reviewer).
    """

    @staticmethod
    def _comment(body: str) -> dict:
        return {"body": body, "user": {"login": "anyone"}}

    def test_two_reviewers_same_lastname_count_as_two(self):
        """NEGATIVE MATCH for #164: two Ferreiras must count as 2, not 1.

        Canonical format: each reviewer is the Requestor of their own
        Approved verdict comment.
        """
        comments = [
            self._comment(
                "Requestor: Lucas Ferreira\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            self._comment(
                "Requestor: Santiago Ferreira\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(
            len(result.reviewers),
            2,
            f"two distinct reviewers sharing lastname collapsed into: {result.reviewers}",
        )
        self.assertIn("lucas ferreira", result.reviewers)
        self.assertIn("santiago ferreira", result.reviewers)

    def test_same_person_counted_once_across_multiple_comments(self):
        """Positive: same reviewer's verdict counts once even across re-cycles.

        Canonical format: the Approved verdict has Requestor=reviewer.
        Request comments (Requestor=PR author) do NOT contribute to the
        reviewer set after the #244 fix — only Approved verdicts count.
        """
        comments = [
            # Initial review request (Requestor=PR author) — does NOT count toward reviewers
            self._comment(
                "Requestor: Linh Pham\nRequestee: Mateo Santos\nRequestOrReplied: Request"
            ),
            # Verdict (Requestor=reviewer) — counts
            self._comment(
                "Requestor: Mateo Santos\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(len(result.reviewers), 1)
        self.assertIn("mateo santos", result.reviewers)

    def test_branch_author_lastname_still_excluded(self):
        """Author-equality check still works on Requestor (post-#244).

        Branch author has lastname `Pham`. If a Pham-surnamed Requestor
        somehow appears on an Approved verdict (a self-approval attempt),
        it must be excluded. Regression guard for the author-equality
        branch on the now-canonical Requestor field.
        """
        comments = [
            self._comment(
                "Requestor: Linh Pham\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, set(), "branch author must not self-review")


class ExtractBranchAuthorLastnameTests(unittest.TestCase):
    """Regression tests for issue #179.

    The regex must accept BOTH separator styles seen in practice — the
    charter-spec slash and the dash-separator that recent branches actually
    use. When the regex missed dash-separator branches, reviewer-counting
    never ran and merges blocked on 0/2 reviews.
    """

    def test_slash_separator_legacy(self):
        """Legacy slash separator still extracts lastname."""
        self.assertEqual(hook.extract_branch_author_lastname("A.Virtanen/0001-foo"), "Virtanen")

    def test_dash_separator_current(self):
        """Dash separator — the fix for #179."""
        self.assertEqual(hook.extract_branch_author_lastname("A.Virtanen-0001-foo"), "Virtanen")

    # NEGATIVE MATCHES — hook-authorship spec requires neg coverage.
    def test_underscore_separator_rejected(self):
        """Underscore is NOT an accepted separator."""
        self.assertIsNone(hook.extract_branch_author_lastname("A.Virtanen_0001-foo"))

    def test_plain_branch_name_rejected(self):
        """A branch without the `{Initial}.{LastName}` prefix returns None."""
        self.assertIsNone(hook.extract_branch_author_lastname("main"))

    def test_no_separator_rejected(self):
        """Prefix present but no separator before trailing content returns None."""
        self.assertIsNone(hook.extract_branch_author_lastname("A.Virtanen0001"))


class MergeCommandMatchTests(unittest.TestCase):
    """Regression tests for the merge-command gate."""

    def test_gh_pr_merge_matches(self):
        self.assertTrue(hook.is_merge_command("gh pr merge 123"))
        self.assertTrue(hook.is_merge_command("gh pr merge 123 --squash"))
        self.assertTrue(hook.is_merge_command("gh pr merge --repo x/y 123"))

    def test_chained_matches(self):
        self.assertTrue(hook.is_merge_command("foo && gh pr merge 1"))
        self.assertTrue(hook.is_merge_command("ENV=1 gh pr merge 1"))

    def test_non_merge_does_not_match(self):
        self.assertFalse(hook.is_merge_command("gh pr list"))
        self.assertFalse(hook.is_merge_command("gh pr view 1"))
        self.assertFalse(hook.is_merge_command("gh pr create"))
        self.assertFalse(hook.is_merge_command("git merge main"))
        self.assertFalse(hook.is_merge_command("gh pr checks"))


class IsApprovedTests(unittest.TestCase):
    """Issue #244: only Approved comments count toward the 2-reviewer rule.

    ChangesRequested is a verdict (TechDebt required) but does NOT contribute
    to the 2-Approved-distinct-reviewer threshold per charter line 36.
    """

    def test_approved_is_approved(self):
        self.assertTrue(hook._is_approved("Approved"))

    def test_lowercase_approved(self):
        self.assertTrue(hook._is_approved("approved"))

    def test_changes_requested_is_not_approved(self):
        self.assertFalse(hook._is_approved("Changes Requested"))

    def test_changesrequested_camelcase_is_not_approved(self):
        self.assertFalse(hook._is_approved("ChangesRequested"))

    def test_request_is_not_approved(self):
        self.assertFalse(hook._is_approved("Request"))

    def test_replied_is_not_approved(self):
        self.assertFalse(hook._is_approved("Replied"))


class RequestorCountingTests(_CheckCommentReviewsHarness):
    """Issue #244: reviewer for verdict comments is the Requestor (comment author).

    Pre-#244 the hook counted distinct Requestee values. Post-#244 it counts
    distinct Requestor values across Approved comments only.
    """

    @staticmethod
    def _comment(body: str) -> dict:
        return {"body": body, "user": {"login": "anyone"}}

    def test_approved_counts_requestor(self):
        """Two Approved verdicts from distinct Requestors → 2 reviewers."""
        comments = [
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            self._comment(
                "Requestor: Jelani Mwangi\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(len(result.reviewers), 2)
        self.assertIn("anya kowalczyk", result.reviewers)
        self.assertIn("jelani mwangi", result.reviewers)

    def test_request_does_not_count_toward_reviewers(self):
        """A Request comment (Requestor=PR author) is NOT a review verdict."""
        comments = [
            self._comment(
                "Requestor: Linh Pham\nRequestee: Anya Kowalczyk\nRequestOrReplied: Request"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, set())

    def test_changes_requested_does_not_count_toward_approved_threshold(self):
        """ChangesRequested is a verdict but NOT toward the 2-Approved threshold.

        Charter line 36: "two distinct Requestor values" specifically across
        `Approved` comments. CR comments do not satisfy the threshold.
        """
        comments = [
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Changes Requested\nTechDebt: none"
            ),
        ]
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        # ChangesRequested has TechDebt so it's a verdict (no missing-attestation
        # error), but the reviewer set stays empty because only Approved counts.
        self.assertEqual(result.reviewers, set())
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_p3w3_wave_merge_repro(self):
        """Exact repro of the P3W3 wave-merge --admin episode (issue #244).

        Wave-merge PRs had 2 distinct Approveds, but the prior hook counted
        Requestee (= PR author) and saw 1 distinct value → blocked. With
        #244 fix counting Requestor, both reviewers are recognized.
        """
        comments = [
            # Two distinct reviewers Approved — canonical Requestor=reviewer
            self._comment(
                "Requestor: Bereket Tadesse\nRequestee: Aino Virtanen\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            self._comment(
                "Requestor: Lucas Ferreira\nRequestee: Aino Virtanen\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        # Branch author lastname is "Virtanen" (Aino's wave-merge PR).
        result = self._run_with_fake_api(comments, "Virtanen", repo=self.REPO)
        self.assertEqual(
            len(result.reviewers),
            2,
            "P3W3 #244 repro: should count Bereket + Lucas as 2 distinct Requestors",
        )


class LoadCharterEnforcerNamesTests(unittest.TestCase):
    """Issue #228: charter-enforcer names parsed from local roster filenames.

    Tests against the parent repo's actual roster (Aino Virtanen as
    standards_lead, Nadia Khoury as program_director). The hook uses
    `_ROSTER_DIR` resolved relative to the hook file at module import.
    """

    def test_parent_roster_includes_aino(self):
        """Parent's standards_lead_aino.md → Aino Virtanen is an enforcer."""
        enforcers = hook.load_charter_enforcer_names()
        self.assertIn(
            "aino virtanen",
            enforcers,
            f"Standards Lead missing from charter enforcers: {enforcers}",
        )

    def test_parent_roster_includes_nadia(self):
        """Parent's program_director_nadia.md → Nadia Khoury is an enforcer."""
        enforcers = hook.load_charter_enforcer_names()
        self.assertIn("nadia khoury", enforcers)

    def test_engineer_roles_excluded(self):
        """`sre_engineer_*`, `security_engineer_*`, etc. are NOT enforcers."""
        enforcers = hook.load_charter_enforcer_names()
        # Aisha (sre_engineer) and Nino (security_engineer) must NOT be in the set.
        self.assertNotIn("aisha idrissi", enforcers)
        self.assertNotIn("nino kavtaradze", enforcers)


class SingleReviewerExceptionTests(unittest.TestCase):
    """Issue #228: hook honors charter's Single-Reviewer Exception."""

    def test_exception_grants_with_label_and_enforcer(self):
        """Label `wave-bootstrap` + sole reviewer is a charter enforcer → exception applies."""
        # Use Aino's lowercased full name (matches what reviewers set holds).
        self.assertTrue(
            hook.is_single_reviewer_exception(
                pr_labels=["wave-bootstrap", "tech-debt"],
                reviewers={"aino virtanen"},
            )
        )

    def test_exception_denied_without_label(self):
        """No `wave-bootstrap` label → exception does NOT apply."""
        self.assertFalse(
            hook.is_single_reviewer_exception(
                pr_labels=["tech-debt"],
                reviewers={"aino virtanen"},
            )
        )

    def test_exception_denied_with_zero_reviewers(self):
        """Zero reviewers is not "exactly one" — exception does NOT apply."""
        self.assertFalse(
            hook.is_single_reviewer_exception(
                pr_labels=["wave-bootstrap"],
                reviewers=set(),
            )
        )

    def test_exception_denied_with_two_reviewers(self):
        """Two reviewers means the strict rule is already satisfied — exception unnecessary."""
        self.assertFalse(
            hook.is_single_reviewer_exception(
                pr_labels=["wave-bootstrap"],
                reviewers={"aino virtanen", "nadia khoury"},
            )
        )

    def test_exception_denied_with_non_enforcer_reviewer(self):
        """`wave-bootstrap` label + sole reviewer is NOT a charter enforcer → no exception."""
        self.assertFalse(
            hook.is_single_reviewer_exception(
                pr_labels=["wave-bootstrap"],
                reviewers={"some random engineer"},
            )
        )


class CheckEndToEndTests(unittest.TestCase):
    """End-to-end check() integration tests for #244 + #228 paths."""

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def _patch_pr_data(self, **overrides) -> dict:
        """Build a stub PR-data dict with sensible defaults; override per test."""
        base = {
            "author": "parametrization",
            "number": 100,
            "reviews": [],  # no formal GitHub reviews in any of these tests
            "headRefName": "L.Pham/0001-fix",
            "labels": [],
        }
        base.update(overrides)
        return base

    def test_two_distinct_approved_requestors_allows_merge(self):
        """Canonical happy path: 2 distinct Requestors on Approved comments → allow.

        Uses real parent-roster personas (Aino + Nadia) so the #498 roster
        gate admits both. Pre-#498 this test used fictional personas (Anya
        Kowalczyk / Jelani Mwangi) that incidentally passed because Hook 4
        didn't yet cross-check roster membership — exactly the asymmetry
        #498 closes.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._patch_pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNone(result, "2 distinct Requestor Approveds should allow merge")

    def test_one_reviewer_without_wave_bootstrap_blocks(self):
        """Strict rule: 1 reviewer + no wave-bootstrap label → block.

        Uses a real roster persona (Aino) so the failure mode tested is
        purely the count shortfall, not a #498 non-roster rejection.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._patch_pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("1/2", result["reason"])

    def test_block_message_explains_reply_vs_approved(self):
        """BLOCKED message MUST surface the Reply-vs-Approved distinction and
        the diagnostic recipe. Codified by #352 after a P3W8 17-addendum
        cascade across 11 PRs where spawn briefs initially specified
        `RequestOrReplied: Reply` and the prior message didn't explain why
        Reply doesn't count.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"anya kowalczyk"}  # 1/2
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._patch_pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        assert result is not None
        reason = result["reason"]
        # Failure-mode framing: Reply-vs-Approved distinction is named.
        self.assertIn("Reply vs Approved", reason)
        self.assertIn(
            "Reply / Replied / Request / ChangesRequested do NOT",
            reason,
        )
        # Body-prose-not-inspected framing (so operator doesn't think
        # "looks good" or "Approved." in the body fixes it).
        self.assertIn("body prose is not inspected", reason)
        # Diagnostic recipe: gh api jq one-liner is shown.
        self.assertIn("gh api repos/<owner>/<repo>/issues/<PR>/comments", reason)
        self.assertIn('contains("RequestOrReplied: Approved")', reason)
        # Memory pointer: canonical reference for full context.
        self.assertIn("feedback_validate_pr_review_approved_not_reply.md", reason)

    def test_block_message_explains_requestor_requestee_swap(self):
        """BLOCKED message MUST surface the Requestor/Requestee swap failure
        mode (W9 PR#349 cascade), in addition to the Reply-vs-Approved one
        (#352). The two failure modes are field-distinct: Reply-vs-Approved
        is wrong RoR value; swap is wrong Requestor/Requestee assignment.
        Codified by #356 after orchestrator spawn-brief template had the
        Requestor/Requestee fields swapped for 7 reviewer posts on PR#349
        before the hook caught the 1-distinct count.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"anya kowalczyk"}  # 1/2
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._patch_pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        assert result is not None
        reason = result["reason"]
        # Failure-mode framing: swap is named as a distinct mode parallel to
        # Reply-vs-Approved (not merged into it).
        self.assertIn("Requestor / Requestee swap", reason)
        # Field-direction clarification.
        self.assertIn("Requestor is the REVIEWER", reason)
        self.assertIn("Requestee is the PR AUTHOR", reason)
        # Origin-story pointer: name the W9 PR#349 cascade so an operator
        # hitting the same shape can cross-reference.
        self.assertIn("W9 PR#349 cascade", reason)
        # Diagnostic recipe: distinct-Requestor jq one-liner is shown.
        self.assertIn("Requestor:", reason)
        self.assertIn("unique", reason)
        # Charter pointer: § Comment-Based Reviews Direction table.
        self.assertIn(
            "pull-requests.md § Comment-Based Reviews",
            reason,
        )

    def test_one_reviewer_with_wave_bootstrap_and_enforcer_allows(self):
        """Single-Reviewer Exception (#228): wave-bootstrap + charter enforcer → allow.

        Uses the actual parent roster — Aino Virtanen is the Standards Lead.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen"}
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value=self._patch_pr_data(labels=["wave-bootstrap", "tech-debt"]),
            ),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNone(
            result,
            "wave-bootstrap PR with charter-enforcer Approved should merge with 1 reviewer",
        )

    def test_one_reviewer_with_wave_bootstrap_but_non_enforcer_blocks(self):
        """Single-Reviewer Exception requires a charter-enforcer reviewer.

        wave-bootstrap label alone does NOT grant the exception — the sole
        reviewer must also be a charter-enforcer per local roster.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"some engineer"}
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value=self._patch_pr_data(labels=["wave-bootstrap"]),
            ),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_admin_short_circuits(self):
        """--admin allows merge regardless of reviewer count (emergency override)."""
        with mock.patch.object(hook, "get_pr_data") as get_mock:
            result = hook.check(self._input("gh pr merge 100 --admin"))
        self.assertIsNone(result)
        get_mock.assert_not_called()

    def test_wave_merge_head_ref_runs_comment_review(self):
        """Issue #294: wave-merge PRs (head = deployments/phase-{N}/wave-{M}) must
        invoke check_comment_reviews with an empty-string author-lastname sentinel
        rather than silently skipping it.

        Before the fix, extract_branch_author_lastname() returned None for the
        wave-branch shape and the inner `if branch_author_lastname:` short-circuited,
        leaving comment_review_result empty — the 2-reviewer gate blocked legitimate
        wave-merge PRs even when 2 charter-format Approved comments were present.

        With the fix, the new `elif` clause detects deployments/.../wave-... heads
        and calls check_comment_reviews(number, "", repo=repo) so existing
        reviewer-vs-author lastname comparison admits any non-empty reviewer name.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value=self._patch_pr_data(headRefName="deployments/phase-3/wave-6"),
            ),
            mock.patch.object(
                hook, "check_comment_reviews", return_value=review_result
            ) as ccr_mock,
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNone(
            result,
            "wave-merge PR with 2 charter-format Approveds should allow merge",
        )
        ccr_mock.assert_called_once()
        # Empty-string sentinel is what permits any non-empty reviewer name.
        call_args = ccr_mock.call_args
        self.assertEqual(call_args.args[0], 100)
        self.assertEqual(call_args.args[1], "")

    def test_wave_merge_head_ref_blocks_with_one_reviewer(self):
        """Issue #294: wave-merge PRs still subject to the 2-reviewer threshold.

        The fix only routes the comment-review check; it does NOT relax the
        reviewer count requirement. A wave-merge PR with a single Approved
        comment must still block (no wave-bootstrap exception applies here).
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen"}
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value=self._patch_pr_data(headRefName="deployments/phase-3/wave-6"),
            ),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("1/2", result["reason"])


class CommentPaginationTests(_CheckCommentReviewsHarness):
    """Issue #303: PR comments fetched with `gh api --paginate`.

    Pre-fix the hook fetched `?per_page=100` without `--paginate`, silently
    missing reviews on PRs with >100 comments. Post-fix the subprocess
    invocation includes `--paginate`, and gh concatenates each page's JSON
    array into a single merged array for top-level array responses.

    The fixtures here assert (1) the subprocess `args` contain `--paginate`
    and (2) reviewer counting still works correctly when the comments list
    grows past 100 — the scenario that pre-fix would have silently allowed
    merge.
    """

    @staticmethod
    def _comment(body: str) -> dict:
        return {"body": body, "user": {"login": "anyone"}}

    def test_subprocess_invocation_includes_paginate_flag(self):
        """gh api ... must be called with --paginate (#303 fix verification)."""
        captured_args: list[list[str]] = []

        def fake_run(args, capture_output, text, timeout):  # noqa: ARG001
            captured_args.append(list(args))
            result = mock.MagicMock()
            result.returncode = 0
            if args[0] == "gh" and args[1:3] == ["repo", "view"]:
                result.stdout = json.dumps({"owner": {"login": "noorinalabs"}, "name": "r"})
            else:
                result.stdout = json.dumps([])
            return result

        with mock.patch.object(hook.subprocess, "run", side_effect=fake_run):
            hook.check_comment_reviews(self.PR_NUMBER, self.BRANCH_AUTHOR, repo=self.REPO)

        gh_api_calls = [a for a in captured_args if a[0] == "gh" and a[1] == "api"]
        self.assertEqual(len(gh_api_calls), 1, "exactly one gh api call expected")
        self.assertIn(
            "--paginate",
            gh_api_calls[0],
            "gh api invocation must include --paginate (#303)",
        )

    def test_paginated_response_with_101_comments_finds_review_at_position_101(self):
        """Review at comment index 100 (the 101st) MUST still register post-fix.

        Pre-fix: per_page=100 with no pagination → comment 101 invisible →
        validate_pr_review counts 1/2 distinct Approved reviewers and
        SILENTLY allows merge if only one Approved was in the first 100.
        Post-fix: --paginate fetches all pages; reviewer at position 101 is
        included; reviewer count is 2/2 and merge proceeds correctly.
        """
        # Build 100 non-review comments (Request/Reply) + 1 Approved at position 101.
        chatter = [
            self._comment(
                f"Requestor: Linh Pham\nRequestee: Reviewer{i}\nRequestOrReplied: Request"
            )
            for i in range(100)
        ]
        review_at_101 = [
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            self._comment(
                "Requestor: Jelani Mwangi\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        comments = chatter + review_at_101
        self.assertEqual(len(comments), 102, "sanity: harness builds the right shape")
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(
            len(result.reviewers),
            2,
            "post-#303: reviewers past position 100 must be counted",
        )
        self.assertIn("anya kowalczyk", result.reviewers)
        self.assertIn("jelani mwangi", result.reviewers)

    def test_paginated_response_with_250_comments_traverses_full_list(self):
        """3-page-equivalent traversal — the loop iterates the entire merged array."""
        chatter = [
            self._comment(f"Requestor: Author{i}\nRequestee: Linh Pham\nRequestOrReplied: Request")
            for i in range(248)
        ]
        reviews = [
            self._comment(
                "Requestor: Anya Kowalczyk\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
            self._comment(
                "Requestor: Jelani Mwangi\nRequestee: Linh Pham\n"
                "RequestOrReplied: Approved\nTechDebt: none"
            ),
        ]
        comments = chatter + reviews
        self.assertEqual(len(comments), 250)
        result = self._run_with_fake_api(comments, self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(len(result.reviewers), 2)


class LoadRosterNamesTests(unittest.TestCase):
    """Issue #498: `_load_roster_names()` returns ALL persona names from the
    local roster (not role-filtered like `load_charter_enforcer_names`).

    Tests against the parent repo's actual roster — Aino, Nadia, Wanjiku,
    Santiago must all be present; engineer roles too (sre, security, etc.).
    """

    def test_includes_standards_lead(self):
        names = hook._load_roster_names()
        self.assertIn("aino virtanen", names, f"missing standards lead: {names}")

    def test_includes_program_director(self):
        self.assertIn("nadia khoury", hook._load_roster_names())

    def test_includes_tpm(self):
        self.assertIn("wanjiku mwangi", hook._load_roster_names())

    def test_includes_release_coordinator(self):
        self.assertIn("santiago ferreira", hook._load_roster_names())

    def test_includes_engineer_roles(self):
        """Unlike `load_charter_enforcer_names`, engineer roles ARE included."""
        names = hook._load_roster_names()
        # sre_engineer_lucas → Lucas Ferreira; sre_engineer_aisha → Aisha Idrissi.
        self.assertIn("lucas ferreira", names)


class RosterValidationGateTests(unittest.TestCase):
    """Issue #498: 2-reviewer gate must reject non-roster Requestor strings.

    Drives `check()` end-to-end with stubbed pr_data and a stubbed
    `check_comment_reviews` result; the only real-roster read is the parent
    repo's `_load_roster_names()` (via `_iter_roster_entries`).

    Repro target: PR #487 verdict comments posted under "Camila Restrepo" and
    "Imelda Santos" — neither in `.claude/team/roster/`. Pre-fix Hook 4
    counted both and merged. Post-fix both are filtered out.
    """

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    @staticmethod
    def _pr_data(**overrides) -> dict:
        base = {
            "author": "parametrization",
            "number": 487,
            "reviews": [],
            "headRefName": "S.Ferreira/0470-doc-sync",
            "labels": [],
        }
        base.update(overrides)
        return base

    def test_two_non_roster_requestors_blocked(self):
        """Regression: 2 non-roster Requestors must BLOCK (P3W11 #487 repro)."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"camila restrepo", "imelda santos"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 487 --squash"))
        self.assertIsNotNone(result, "non-roster Requestors must not satisfy the 2-reviewer gate")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        reason = result["reason"]
        self.assertIn("camila restrepo", reason.lower())
        self.assertIn("imelda santos", reason.lower())
        self.assertIn("Non-roster:", reason)
        self.assertIn("roster", reason.lower())

    def test_mixed_roster_and_non_roster_blocked(self):
        """1 roster + 1 non-roster → 1/2 (only the roster member counts)."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "imelda santos"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 487 --squash"))
        self.assertIsNotNone(result, "1 roster + 1 non-roster must not pass 2/2")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        reason = result["reason"]
        self.assertIn("imelda santos", reason.lower())
        self.assertNotIn("aino virtanen", reason.lower().split("non-roster:")[1].split("\n")[0])
        # Final count should reflect the filtered roster-only set.
        self.assertIn("1/2", reason)

    def test_two_roster_requestors_pass(self):
        """Regression baseline: 2 real roster members → allow (existing behavior)."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 487 --squash"))
        self.assertIsNone(result, "two distinct roster members must pass the 2-reviewer gate")

    def test_empty_roster_blocks_with_diagnostic(self):
        """Fail-closed: if the roster cannot be read, every Requestor is non-roster.

        Critical safe-direction default per `safety_direction_over_ux_friction`
        memory: an unreadable roster must NOT silently pass review gates that
        depend on it. The BLOCK message must surface the empty-roster
        condition diagnostically so an operator can fix the dir, not bypass.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        with (
            mock.patch.object(hook, "_load_roster_names", return_value=set()),
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 487 --squash"))
        self.assertIsNotNone(result, "empty roster must fail closed")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        reason = result["reason"]
        self.assertIn("empty", reason.lower())
        self.assertIn("could not be read", reason)


class StripCodeRegionsTests(unittest.TestCase):
    """Issue #511: `_strip_code_regions` removes fenced and inline code so the
    field extractor cannot capture reviewer prose-quotes of field syntax.

    Replacement char is space (not empty) so line indices stay stable for
    downstream trailer-block detection.
    """

    def test_strips_inline_backticks(self):
        result = hook._strip_code_regions("see `Requestor: foo` for context")
        self.assertNotIn("Requestor", result)
        self.assertEqual(len(result), len("see `Requestor: foo` for context"))

    def test_strips_fenced_triple_backtick_block(self):
        body = "before\n```\nRequestor: foo\n```\nafter"
        result = hook._strip_code_regions(body)
        self.assertNotIn("Requestor", result)
        self.assertIn("before", result)
        self.assertIn("after", result)

    def test_unterminated_inline_backtick_passes_through(self):
        """A lone backtick without a closing pair is treated as literal."""
        result = hook._strip_code_regions("opening ` and then Requestor: foo")
        self.assertIn("Requestor: foo", result)

    def test_unterminated_fenced_block_strips_rest(self):
        """An open ``` without a close conservatively eats the rest. Reviewer
        error mode (forgot close fence) → fail safe by not matching trailing
        chars as fields.
        """
        body = "intro ```\nRequestor: foo"
        result = hook._strip_code_regions(body)
        self.assertIn("intro", result)
        self.assertNotIn("Requestor", result)

    def test_multiline_inline_span_is_not_matched(self):
        """`...` with a newline in between is NOT an inline-code span per
        CommonMark — opening backtick passes through, line preserved.
        """
        body = "opening `\nRequestor: foo\n` closing"
        result = hook._strip_code_regions(body)
        self.assertIn("Requestor: foo", result)


class TrailerBlockSubstringTests(unittest.TestCase):
    """Issue #511: `_trailer_block_substring` returns text after the LAST
    bare-`---` separator line. No-separator → full body (back-compat).
    """

    def test_no_separator_returns_full_body(self):
        body = "Requestor: foo\nRequestee: bar"
        self.assertEqual(hook._trailer_block_substring(body), body)

    def test_one_separator_returns_post_only(self):
        body = "prose intro\n\n---\nRequestor: foo\nRequestee: bar"
        result = hook._trailer_block_substring(body)
        self.assertIn("Requestor", result)
        self.assertNotIn("prose intro", result)

    def test_multiple_separators_last_wins(self):
        body = (
            "intro\n\n---\nfake trailer with Requestor: WRONG\nmore prose\n"
            "---\nRequestor: CORRECT\nRequestee: target"
        )
        result = hook._trailer_block_substring(body)
        self.assertIn("CORRECT", result)
        self.assertNotIn("WRONG", result)

    def test_separator_must_be_on_own_line(self):
        body = "intro with --- embedded\nRequestor: foo"
        self.assertEqual(hook._trailer_block_substring(body), body)

    def test_separator_with_surrounding_whitespace_is_recognized(self):
        body = "intro\n  ---  \nRequestor: foo"
        result = hook._trailer_block_substring(body)
        self.assertIn("Requestor", result)
        self.assertNotIn("intro", result)


class ProseFalseMatchRegressionTests(_CheckCommentReviewsHarness):
    """Issue #511: prose-mention of charter fields above the trailer block
    MUST NOT be captured as the verdict. Three exact-shape regressions for
    the P3W11 batch-11 instances — pre-#511 each false-blocked at 1/2.
    """

    @staticmethod
    def _comment(body: str) -> dict:
        return {"body": body, "user": {"login": "anyone"}}

    def test_main_509_wanjiku_prose_above_trailer_ignored(self):
        """main#509 (Wanjiku) — prose described the bare-line trailer; pre-fix
        captured rest-of-prose-line as Requestor. Post-fix the trailer block
        (after `---`) is the only match scope.
        """
        body = (
            "PR body trailer convention is the literal bare-line block "
            "(Requestor / Requestee / RequestOrReplied: New / TechDebt: none) "
            "at the end of the body. Aino's #509 follows it correctly.\n"
            "\n"
            "---\n"
            "Requestor: Wanjiku Mwangi\n"
            "Requestee: Aino Virtanen\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none"
        )
        result = self._run_with_fake_api([self._comment(body)], self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, {"wanjiku mwangi"})
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_deploy_337_lucas_prose_observation_ignored(self):
        """deploy#337 (Lucas) — soft observation about missing trailer block.
        Pre-fix the prose mention of `Requestor: / Requestee: / ...` itself
        captured garbage. Post-fix the actual trailer wins.
        """
        body = (
            "Soft observation: Aisha's PR body does not include the trailer "
            "structured-fields block (Requestor: / Requestee: / "
            "RequestOrReplied: New / TechDebt: none bare-line). Non-blocking — "
            "she can amend post-merge. LGTM on the conftest guard.\n"
            "\n"
            "---\n"
            "Requestor: Lucas Ferreira\n"
            "Requestee: Aisha Idrissi\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none"
        )
        result = self._run_with_fake_api([self._comment(body)], self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, {"lucas ferreira"})
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_deploy_339_bereket_backtick_quote_ignored(self):
        """deploy#339 (Bereket) — verdict quoted PR body's `Requestor: (TBD…)`
        inside backticks. Pre-fix backtick contents were extracted as
        Requestor. Post-fix `_strip_code_regions` zeroes the backticks.
        """
        body = (
            "PR body uses `Requestor: (TBD — orchestrator will assign)` "
            "correctly — no reviewer name prediction, deferred per charter "
            "feedback_pr_number_placeholders.\n"
            "\n"
            "---\n"
            "Requestor: Bereket Tadesse\n"
            "Requestee: Lucas Ferreira\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none"
        )
        result = self._run_with_fake_api([self._comment(body)], self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, {"bereket tadesse"})
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_legacy_no_separator_uses_last_match_fallback(self):
        """Back-compat: pre-#511 verdict comments without a `---` separator
        still work — the extractor falls back to the full body and uses
        last-match-wins. Prose above an end-of-body trailer is ignored
        because the last match is the real trailer.
        """
        body = (
            "Noting the body has Requestor: oldformat-prose-mention\n"
            "but the real trailer below uses canonical fields:\n"
            "Requestor: Wanjiku Mwangi\n"
            "Requestee: Aino Virtanen\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none"
        )
        result = self._run_with_fake_api([self._comment(body)], self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, {"wanjiku mwangi"})
        self.assertEqual(result.reviews_missing_tech_debt, [])

    def test_multiple_separators_only_last_trailer_matches(self):
        """If a verdict has multiple `---` (e.g., reviewer included an aside
        block with its own separator), only the LAST trailer is the source
        of truth — earlier blocks are ignored even if they look canonical.
        """
        body = (
            "intro prose\n"
            "\n"
            "---\n"
            "Requestor: WrongName Person\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none\n"
            "\n"
            "(this was an aside block, not the real verdict)\n"
            "\n"
            "---\n"
            "Requestor: Nadia Khoury\n"
            "Requestee: Aino Virtanen\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none"
        )
        result = self._run_with_fake_api([self._comment(body)], self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, {"nadia khoury"})

    def test_existing_canonical_trailer_still_works(self):
        """Regression baseline: a plain canonical verdict (no prose preamble,
        no separator, fields-only body) still parses correctly under the new
        scope discipline. Guards against over-zealous narrowing.
        """
        body = (
            "Requestor: Wanjiku Mwangi\n"
            "Requestee: Aino Virtanen\n"
            "RequestOrReplied: Approved\n"
            "TechDebt: none"
        )
        result = self._run_with_fake_api([self._comment(body)], self.BRANCH_AUTHOR, repo=self.REPO)
        self.assertEqual(result.reviewers, {"wanjiku mwangi"})


class ExtractRepoCallSiteTests(unittest.TestCase):
    """Smoke coverage that `validate_pr_review` exposes `extract_repo`
    (re-exported from the shared `_repo_flag_parse` helper) and that the
    canonical `gh pr merge --repo` happy path still resolves the same
    value.

    Comprehensive parser coverage (all 4 flag forms, tokenize / regex
    fallback, malformed cases) lives in `test_repo_flag_parse.py` alongside
    the helper. These tests pin the hook's import wiring so a future
    refactor that drops the re-export trips here, not at runtime. Mirrors
    `test_validate_review_comment_format.ExtractRepoCallSiteTests` from
    #513.
    """

    def test_present_returns_value(self):
        cmd = "gh pr merge 487 --repo noorinalabs/noorinalabs-deploy --squash"
        self.assertEqual(
            hook.extract_repo(cmd),
            "noorinalabs/noorinalabs-deploy",
        )

    def test_absent_returns_none(self):
        cmd = "gh pr merge 487 --squash"
        self.assertIsNone(hook.extract_repo(cmd))

    def test_equals_form_now_supported(self):
        """`--repo=value` form is supported post-#514 (was the documented
        latent #503-class gap in the original #509 implementation — sister
        consolidation #510 fixed it for two hooks via #513, #514 extends
        the fix to validate_pr_review for the gh-pr-merge code path)."""
        cmd = "gh pr merge 487 --repo=noorinalabs/noorinalabs-deploy --squash"
        self.assertEqual(
            hook.extract_repo(cmd),
            "noorinalabs/noorinalabs-deploy",
        )


class ChildRosterResolutionTests(unittest.TestCase):
    """Issue #552: the roster the 2-reviewer gate validates against must be
    resolved relative to the PR's TARGET repo, not hardcoded to the parent.

    Pre-#552 `_ROSTER_DIR` was fixed to the parent repo's roster, so a child
    repo PR reviewed by legitimate child-repo personas (e.g. Anya Kowalczyk,
    Idris Yusuf) had those reviewers filtered out as "non-roster" — the gate
    blocked the merge or, after the merge was forced, defeated itself via
    `--admin`. In P3W13 this forced `--admin` on 14/37 child-repo PRs.

    The fix unions the parent roster with the named child repo's
    `.claude/team/roster/`. These tests build a hermetic on-disk parent+child
    roster tree under a tmp dir and monkeypatch `_ROSTER_DIR` /
    `_PARENT_REPO_ROOT` so they do not depend on the live sibling checkout.
    """

    PARENT_PERSONAS = {
        "standards_lead_aino": "Aino Virtanen",
        "program_director_nadia": "Nadia Khoury",
    }
    # Child personas — NOT present in the parent roster. `manager_*` is a
    # charter-enforcer prefix; `engineer_*` is a plain reviewer.
    CHILD_PERSONAS = {
        "engineer_anya": "Anya Kowalczyk",
        "engineer_idris": "Idris Yusuf",
        "manager_bereket": "Bereket Tadesse",
    }
    CHILD_REPO_NAME = "noorinalabs-isnad-graph"
    CHILD_REPO = f"noorinalabs/{CHILD_REPO_NAME}"

    def _write_roster(self, roster_dir: Path, personas: dict[str, str]) -> None:
        roster_dir.mkdir(parents=True, exist_ok=True)
        for slug, name in personas.items():
            (roster_dir / f"{slug}.md").write_text(
                f"# Roster Card\n\n## Identity\n- **Name:** {name}\n", encoding="utf-8"
            )

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        # Parent repo root holds .claude/team/roster and the child repo sibling.
        parent_repo = root / "noorinalabs-main"
        self._parent_roster = parent_repo / ".claude" / "team" / "roster"
        self._write_roster(self._parent_roster, self.PARENT_PERSONAS)
        child_roster = parent_repo / self.CHILD_REPO_NAME / ".claude" / "team" / "roster"
        self._write_roster(child_roster, self.CHILD_PERSONAS)

        self._patchers = [
            mock.patch.object(hook, "_ROSTER_DIR", self._parent_roster),
            mock.patch.object(hook, "_PARENT_REPO_ROOT", parent_repo),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self) -> None:
        for p in self._patchers:
            p.stop()
        self._tmp.cleanup()

    # --- _child_roster_dir resolution -------------------------------------

    def test_child_roster_dir_resolves_for_child_repo(self):
        d = hook._child_roster_dir(self.CHILD_REPO)
        assert d is not None
        self.assertTrue(d.is_dir())
        self.assertEqual(d.parent.parent.parent.name, self.CHILD_REPO_NAME)

    def test_child_roster_dir_none_for_parent_repo(self):
        """`--repo noorinalabs/noorinalabs-main` → no distinct child dir."""
        self.assertIsNone(hook._child_roster_dir("noorinalabs/noorinalabs-main"))

    def test_child_roster_dir_none_for_absent_repo(self):
        self.assertIsNone(hook._child_roster_dir(None))
        self.assertIsNone(hook._child_roster_dir("not-a-repo-spec"))

    # --- union roster -----------------------------------------------------

    def test_load_roster_names_unions_parent_and_child(self):
        names = hook._load_roster_names(repo=self.CHILD_REPO)
        # Parent personas present.
        self.assertIn("aino virtanen", names)
        self.assertIn("nadia khoury", names)
        # Child personas unioned in (#552).
        self.assertIn("anya kowalczyk", names)
        self.assertIn("idris yusuf", names)

    def test_load_roster_names_parent_only_when_no_repo(self):
        """No `--repo` → parent-only resolution (back-compat for parent PRs)."""
        names = hook._load_roster_names(repo=None)
        self.assertIn("aino virtanen", names)
        self.assertNotIn("anya kowalczyk", names)

    def test_enforcer_names_union_includes_child_manager(self):
        """Child-repo `manager_*` is a charter enforcer for that repo's PRs."""
        enforcers = hook.load_charter_enforcer_names(repo=self.CHILD_REPO)
        self.assertIn("bereket tadesse", enforcers)
        # engineer_* personas are NOT enforcers.
        self.assertNotIn("anya kowalczyk", enforcers)

    # --- end-to-end check() behavior --------------------------------------

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    @staticmethod
    def _pr_data(**overrides) -> dict:
        base = {
            "author": "parametrization",
            "number": 935,
            "reviews": [],
            "headRefName": "A.Kowalczyk/0900-fix",
            "labels": [],
        }
        base.update(overrides)
        return base

    def test_child_pr_valid_child_reviewers_pass(self):
        """Two distinct child-repo reviewers on a child PR → allow (#552 core)."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"anya kowalczyk", "idris yusuf"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input(f"gh pr merge 935 --repo {self.CHILD_REPO} --squash"))
        self.assertIsNone(result, "valid child-repo reviewers must pass the 2-reviewer gate")

    def test_child_pr_unknown_reviewer_blocks(self):
        """A reviewer in NEITHER parent nor child roster is still non-roster."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"anya kowalczyk", "phantom persona"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input(f"gh pr merge 935 --repo {self.CHILD_REPO} --squash"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("phantom persona", result["reason"].lower())
        self.assertIn("1/2", result["reason"])

    def test_parent_pr_still_passes_with_parent_reviewers(self):
        """Regression: parent-repo PR (no `--repo`) with 2 parent reviewers → allow."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNone(result, "parent-repo PR with 2 parent reviewers must still pass")

    def test_child_reviewer_does_not_count_on_parent_pr(self):
        """A child-only persona must NOT satisfy the gate on a parent PR (no leak)."""
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "anya kowalczyk"}
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --squash"))
        self.assertIsNotNone(result, "child persona must not count on a parent-repo PR")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("1/2", result["reason"])

    def test_missing_child_roster_dir_hard_blocks(self):
        """Safe direction: `--repo` names a child whose roster dir is absent →
        HARD BLOCK with diagnostic, never silent parent-only fallback
        (feedback_safety_direction_over_ux_friction).
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        missing_repo = "noorinalabs/noorinalabs-does-not-exist"
        with (
            mock.patch.object(hook, "get_pr_data", return_value=self._pr_data()),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input(f"gh pr merge 935 --repo {missing_repo} --squash"))
        self.assertIsNotNone(result, "unresolvable child roster must fail closed")
        assert result is not None
        self.assertEqual(result["decision"], "block")
        reason = result["reason"]
        self.assertIn("roster", reason.lower())
        self.assertIn("could not be resolved", reason)

    def test_child_pr_single_reviewer_exception_with_child_enforcer(self):
        """Single-Reviewer Exception honors a child-repo enforcer on a child PR.

        wave-bootstrap + sole reviewer is the child repo's manager (enforcer)
        → exception applies even though that persona is not in the parent roster.
        """
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"bereket tadesse"}
        with (
            mock.patch.object(
                hook,
                "get_pr_data",
                return_value=self._pr_data(labels=["wave-bootstrap", "tech-debt"]),
            ),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input(f"gh pr merge 935 --repo {self.CHILD_REPO} --squash"))
        self.assertIsNone(
            result,
            "child-repo enforcer should satisfy the single-reviewer exception on a child PR",
        )


class ResolveRosterDirsTests(unittest.TestCase):
    """Issue #552: `_resolve_roster_dirs` returns parent + child dirs and raises
    `RosterResolutionError` when a named child roster dir is missing.
    """

    def test_parent_only_when_no_repo(self):
        dirs = hook._resolve_roster_dirs(None)
        self.assertEqual(dirs, [hook._ROSTER_DIR])

    def test_parent_only_when_repo_is_parent(self):
        dirs = hook._resolve_roster_dirs(f"noorinalabs/{hook._PARENT_REPO_ROOT.name}")
        self.assertEqual(dirs, [hook._ROSTER_DIR])

    def test_raises_when_child_roster_missing(self):
        with self.assertRaises(hook.RosterResolutionError):
            hook._resolve_roster_dirs("noorinalabs/noorinalabs-nonexistent-xyz")


class BatchLoopMergeDetectorTests(unittest.TestCase):
    """#567: `is_variable_pr_merge_in_loop` detects a `gh pr merge <var>` inside
    a for/while/until loop — the shape that fail-opens the 2-reviewer gate
    (memory `feedback_batch_loop_merge_evades_pr_review_hook`).

    Six parser classes per charter `hooks.md § 5a` segment-parser coverage:
    newline-separated loop, quoted-var arg, `${}`-form, literal-still-passes,
    while-loop, nested-loop. Plus the body-mention false-positive guard."""

    def test_for_loop_quoted_var_blocked(self):
        # parser-class: quoted-var
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop(
                'for pr in 48 49 50; do gh pr merge "$pr" --repo o/r --merge; done'
            )
        )

    def test_for_loop_bare_var_blocked(self):
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop("for pr in 48 49; do gh pr merge $pr --merge; done")
        )

    def test_brace_form_var_blocked(self):
        # parser-class: ${}-form
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop('for pr in 1 2; do gh pr merge "${pr}" --merge; done')
        )

    def test_while_loop_blocked(self):
        # parser-class: while-loop
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop("while read pr; do gh pr merge ${pr} --merge; done")
        )

    def test_until_loop_blocked(self):
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop('until [ -z "$pr" ]; do gh pr merge $pr; done')
        )

    def test_newline_separated_loop_blocked(self):
        # parser-class: newline
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop(
                'for pr in 48 49\ndo\n  gh pr merge "$pr" --merge\ndone'
            )
        )

    def test_nested_loop_blocked(self):
        # parser-class: nested-loop
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop(
                'for r in a b; do\n  for pr in 1 2; do gh pr merge "$pr" --merge; done\ndone'
            )
        )

    def test_literal_merge_not_blocked(self):
        # parser-class: literal-still-passes — a literal PR number is untouched
        # by the guard (its number parses and the normal gate runs).
        self.assertFalse(hook.is_variable_pr_merge_in_loop("gh pr merge 54 --repo o/r --merge"))

    def test_literal_loop_not_blocked(self):
        # A loop iterating LITERAL merges (no shell variable) is not the
        # fail-open shape — each merge parses a literal number.
        self.assertFalse(
            hook.is_variable_pr_merge_in_loop("for n in 1; do gh pr merge 54 --merge; done")
        )

    def test_var_merge_outside_loop_not_blocked(self):
        # Out of scope for #567: a one-off variable merge with no loop.
        self.assertFalse(hook.is_variable_pr_merge_in_loop('gh pr merge "$PR" --merge'))

    def test_loop_text_in_body_not_blocked(self):
        # False-positive guard: a `--body` payload that merely MENTIONS the
        # loop-merge shape (quoted prose) must NOT be detected. The real
        # command is `gh pr create`, not a merge.
        self.assertFalse(
            hook.is_variable_pr_merge_in_loop(
                'gh pr create --body "for pr in 1; do gh pr merge $pr; done"'
            )
        )

    def test_non_merge_loop_not_blocked(self):
        # A loop that runs some other gh command is irrelevant to the gate.
        self.assertFalse(
            hook.is_variable_pr_merge_in_loop('for pr in 1 2; do gh pr view "$pr"; done')
        )

    def test_886_gh_run_rerun_loop_not_blocked(self):
        # #886 regression — the EXACT non-merge shape that false-blocked at the
        # P7W18 wrapup: a `gh run rerun "$ds_run" --failed` staleness recheck
        # inside a for-loop. No `gh pr merge` anywhere → must not match.
        self.assertFalse(
            hook.is_variable_pr_merge_in_loop(
                "for ds_run in $(gh run list --repo noorinalabs/noorinalabs-deploy "
                '--json databaseId --jq ".[].databaseId"); do '
                'gh run rerun "$ds_run" --repo noorinalabs/noorinalabs-deploy --failed; done'
            )
        )

    def test_886_nonloop_merge_with_unrelated_rerun_loop_not_blocked(self):
        # #886 regression (the actual false-positive mechanism): a multi-line
        # block pairing a NON-loop variable merge with a SEPARATE, unrelated
        # `gh run rerun` staleness loop. The merge is not inside the loop body,
        # so the gate does not fail-open and the guard must NOT fire. Before the
        # #886 narrowing this returned True (merge-var pattern + loop keywords
        # matched independently anywhere in the command).
        cmd = (
            'gh pr merge "$PR" --repo noorinalabs/noorinalabs-deploy --merge\n'
            'echo "wave merged"\n'
            "for ds_run in 11 12 13; do "
            'gh run rerun "$ds_run" --repo noorinalabs/noorinalabs-deploy --failed; done'
        )
        self.assertFalse(hook.is_variable_pr_merge_in_loop(cmd))

    def test_886_batch_loop_merge_still_blocked(self):
        # #886 must NOT weaken the real protection: a `gh pr merge "$pr"` that is
        # genuinely INSIDE the loop body (the fail-open evasion class from
        # `feedback_batch_loop_merge_evades`) is still detected.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop(
                'for pr in 48 49 50; do gh pr merge "$pr" --repo o/r --merge; done'
            )
        )

    # ---- #894 residual fail-open evasions ----

    def test_894_subshell_wrapped_merge_blocked(self):
        # Gap 1: a merge wrapped in a `( … )` subshell leaves the arg as `$pr)`.
        # The pre-#894 terminator lookahead `(?=\s|;|&|\||$)` omitted `)`, so the
        # merge verb never matched and the loop fail-opened. Now BLOCKED.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop("for pr in 1 2; do (gh pr merge $pr); done")
        )

    def test_894_subshell_wrapped_quoted_merge_blocked(self):
        # Gap 1 variant: subshell + quoted var arg.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop('for pr in 1 2; do (gh pr merge "$pr" --merge); done')
        )

    def test_894_subscripted_array_arg_blocked(self):
        # Gap 2: a subscripted `"${prs[$i]}"` arg failed the lone-simple-var
        # unwrap fullmatch and was stripped as opaque prose — the merge arg
        # vanished and the loop fail-opened. Now BLOCKED.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop('for i in 0 1; do gh pr merge "${prs[$i]}"; done')
        )

    def test_894_command_substitution_arg_blocked(self):
        # Gap 2 variant: a command-substitution `"$(cmd)"` arg, likewise stripped
        # pre-#894. Now BLOCKED.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop(
                'for i in 0 1; do gh pr merge "$(get_pr)" --merge; done'
            )
        )

    def test_894_command_substitution_arg_with_inner_space_blocked(self):
        # Gap 2 robustness: whitespace INSIDE the `$(…)` expansion must not make
        # the quoted run look like prose — it is still one shell-word argument.
        self.assertTrue(
            hook.is_variable_pr_merge_in_loop('for i in 0 1; do gh pr merge "$(get_pr $i)"; done')
        )

    def test_894_literal_merge_inside_loop_not_blocked(self):
        # Over-broadening guard: a bare-integer `gh pr merge 54` INSIDE a loop is
        # still NOT blocked — the literal parses and the normal gate runs.
        self.assertFalse(
            hook.is_variable_pr_merge_in_loop("for n in 1; do gh pr merge 54 --merge; done")
        )

    def test_894_nonliteral_merge_outside_loop_not_blocked(self):
        # #886 co-location preserved under the #894 broadening: a one-off
        # subscripted/compound merge OUTSIDE any loop, co-occurring with an
        # unrelated `gh run rerun` loop, does NOT fail-open and MUST NOT block.
        cmd = (
            'gh pr merge "${prs[0]}" --repo noorinalabs/noorinalabs-deploy --merge\n'
            "for r in 11 12 13; do "
            'gh run rerun "$r" --repo noorinalabs/noorinalabs-deploy --failed; done'
        )
        self.assertFalse(hook.is_variable_pr_merge_in_loop(cmd))

    def test_894_body_mention_of_compound_merge_not_blocked(self):
        # The #894 unwrap broadening must not re-open the prose-mention guard:
        # a `--body "…"` payload mentioning the compound-arg loop shape (it
        # carries whitespace OUTSIDE the expansion) is still stripped, not matched.
        self.assertFalse(
            hook.is_variable_pr_merge_in_loop(
                'gh pr create --body "for i in 0 1; do gh pr merge ${prs[$i]}; done"'
            )
        )


class BatchLoopMergeEndToEndTests(unittest.TestCase):
    """#567 end-to-end: check() HARD BLOCKS a batch-loop variable merge, and a
    literal merge still flows to the normal 2-reviewer gate unchanged."""

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_loop_var_merge_hard_blocked(self):
        # The guard returns BEFORE get_pr_data; patch it to a sentinel that
        # would NOT itself block, so a passing test proves the LOOP guard
        # (not the downstream gate) produced the block.
        with mock.patch.object(hook, "get_pr_data", return_value=None):
            result = hook.check(
                self._input('for pr in 48 49 50; do gh pr merge "$pr" --merge; done')
            )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("Batch-loop", result["reason"])
        self.assertIn("one pr per call", result["reason"].lower())

    def test_894_subscripted_loop_merge_hard_blocked(self):
        # #894 end-to-end: a subscripted in-loop merge reaches check() and HARD
        # BLOCKS. Patch get_pr_data so a pass proves the LOOP guard fired, not
        # the downstream gate.
        with mock.patch.object(hook, "get_pr_data", return_value=None):
            result = hook.check(
                self._input('for i in 0 1; do gh pr merge "${prs[$i]}" --merge; done')
            )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("Batch-loop", result["reason"])

    def test_894_subshell_loop_merge_hard_blocked(self):
        # #894 end-to-end: a subshell-wrapped in-loop merge HARD BLOCKS.
        with mock.patch.object(hook, "get_pr_data", return_value=None):
            result = hook.check(self._input("for pr in 1 2; do (gh pr merge $pr); done"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_loop_var_merge_with_admin_still_overrides(self):
        # --admin is the emergency override and bypasses the loop guard too.
        result = hook.check(
            self._input('for pr in 1 2; do gh pr merge "$pr" --admin --merge; done')
        )
        self.assertIsNone(result, "--admin must bypass the batch-loop guard")

    def test_literal_merge_unaffected_by_loop_guard(self):
        # A bare literal merge is NOT loop-shaped; it reaches the normal gate.
        # With 2 distinct approved reviewers it allows (proves the guard did
        # not interfere with the literal path).
        review_result = hook.CommentReviewResult()
        review_result.reviewers = {"aino virtanen", "nadia khoury"}
        pr_data = {
            "author": "parametrization",
            "number": 100,
            "reviews": [],
            "headRefName": "L.Pham/0001-fix",
            "labels": [],
        }
        with (
            mock.patch.object(hook, "get_pr_data", return_value=pr_data),
            mock.patch.object(hook, "check_comment_reviews", return_value=review_result),
        ):
            result = hook.check(self._input("gh pr merge 100 --merge"))
        self.assertIsNone(result, "literal 2-approved merge must still pass the gate")


class StripQuotedRunsKeepVarArgsTests(unittest.TestCase):
    """#567 pure-parser: `_strip_quoted_runs_keep_var_args` drops quoted prose
    but unwraps a lone `"$var"` arg to its bare form."""

    def test_lone_double_quoted_var_unwrapped(self):
        out = hook._strip_quoted_runs_keep_var_args('gh pr merge "$pr" --merge')
        self.assertIn("$pr", out)
        self.assertNotIn('"', out)

    def test_brace_lone_var_unwrapped(self):
        out = hook._strip_quoted_runs_keep_var_args('gh pr merge "${pr}" --merge')
        self.assertIn("${pr}", out)

    def test_prose_double_quoted_run_dropped(self):
        out = hook._strip_quoted_runs_keep_var_args('gh pr create --body "do gh pr merge $pr"')
        # The body content (including its inner merge mention) is removed.
        self.assertNotIn("merge $pr", out)

    def test_single_quoted_run_dropped(self):
        out = hook._strip_quoted_runs_keep_var_args("echo 'for pr in 1; do gh pr merge $pr; done'")
        self.assertNotIn("gh pr merge", out)

    # ---- #894: broadened single-word-expansion unwrap ----

    def test_subscripted_array_arg_unwrapped(self):
        out = hook._strip_quoted_runs_keep_var_args('gh pr merge "${prs[$i]}" --merge')
        self.assertIn("${prs[$i]}", out)
        self.assertNotIn('"', out)

    def test_command_substitution_arg_unwrapped(self):
        out = hook._strip_quoted_runs_keep_var_args('gh pr merge "$(get_pr)" --merge')
        self.assertIn("$(get_pr)", out)

    def test_command_substitution_with_inner_space_unwrapped(self):
        # Whitespace inside the expansion does not make the run prose.
        out = hook._strip_quoted_runs_keep_var_args('gh pr merge "$(get_pr $i)" --merge')
        self.assertIn("$(get_pr $i)", out)

    def test_quoted_literal_word_not_unwrapped(self):
        # A non-expansion single word (e.g. a stray `"done"`) must NOT be
        # unwrapped — that would inject a spurious loop keyword into the view.
        out = hook._strip_quoted_runs_keep_var_args('gh pr comment --body "done"')
        self.assertNotIn("done", out)

    def test_prose_with_expansion_outside_dropped(self):
        # Whitespace OUTSIDE the expansion ⇒ prose ⇒ dropped wholesale.
        out = hook._strip_quoted_runs_keep_var_args('--body "merge ${prs[$i]} now"')
        self.assertNotIn("prs", out)


class StripExpansionsTests(unittest.TestCase):
    """#894 pure-parser: `_strip_expansions` removes balanced ${…}/$(…) groups so
    `_is_single_expansion_word` can tell a one-word arg from prose."""

    def test_brace_group_removed(self):
        self.assertEqual(hook._strip_expansions("${prs[$i]}").strip(), "")

    def test_paren_group_with_inner_space_removed(self):
        self.assertEqual(hook._strip_expansions("$(get_pr $i)").strip(), "")

    def test_nested_paren_group_removed(self):
        self.assertEqual(hook._strip_expansions("$(a $(b) c)").strip(), "")

    def test_bare_var_left_intact(self):
        # A bare `$pr` has no internal whitespace to hide, so it is not a group.
        self.assertEqual(hook._strip_expansions("$pr"), "$pr")

    def test_prose_whitespace_survives(self):
        self.assertTrue(any(c.isspace() for c in hook._strip_expansions("do merge $pr")))


class IsSingleExpansionWordTests(unittest.TestCase):
    """#894: predicate gating the double-quoted-run unwrap."""

    def test_bare_var_is_word(self):
        self.assertTrue(hook._is_single_expansion_word("$pr"))

    def test_subscripted_is_word(self):
        self.assertTrue(hook._is_single_expansion_word("${prs[$i]}"))

    def test_command_sub_with_space_is_word(self):
        self.assertTrue(hook._is_single_expansion_word("$(get_pr $i)"))

    def test_prose_is_not_word(self):
        self.assertFalse(hook._is_single_expansion_word("do gh pr merge $pr"))

    def test_literal_word_is_not_word(self):
        self.assertFalse(hook._is_single_expansion_word("done"))


if __name__ == "__main__":
    unittest.main()
