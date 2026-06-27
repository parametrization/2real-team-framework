#!/usr/bin/env python3
"""Tests for validate_pr_ci_status hook (closes #219).

Covers:
- `classify_check` core logic — pass/fail/pending across the conclusion +
  status + bucket axes.
- #219 NEUTRAL allowlist semantics — a CheckRun whose name starts with an
  allowlisted prefix (`chromatic`) treats NEUTRAL as pending; all other
  CheckRuns' NEUTRAL preserved as pass. #262 broadened the exact-match set
  to `startswith` prefix matching so multi-step Chromatic shapes match.
- Hook-authorship § 3 negative-match coverage.

Run:
    ENVIRONMENT=test python3 -m pytest \
        .claude/hooks/tests/test_validate_pr_ci_status.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_pr_ci_status as hook  # noqa: E402


def _check(name: str = "ci", *, conclusion: str = "", status: str = "", bucket: str = "") -> dict:
    """Build a CheckRun dict with the fields classify_check inspects."""
    out: dict = {"name": name}
    if conclusion:
        out["conclusion"] = conclusion
    if status:
        out["status"] = status
    if bucket:
        out["bucket"] = bucket
    return out


class ClassifyCheckCoreTests(unittest.TestCase):
    """Existing classify_check semantics (pre-#219, must remain stable)."""

    def test_failure_conclusion_classed_fail(self):
        for c in ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"):
            with self.subTest(conclusion=c):
                self.assertEqual(
                    hook.classify_check(_check(conclusion=c)),
                    "fail",
                    f"conclusion {c} should classify as fail",
                )

    def test_fail_bucket_classed_fail(self):
        # bucket overrides conclusion when bucket is `fail`
        self.assertEqual(hook.classify_check(_check(bucket="fail", conclusion="SUCCESS")), "fail")

    def test_pending_status_classed_pending(self):
        for s in ("QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED"):
            with self.subTest(status=s):
                self.assertEqual(
                    hook.classify_check(_check(status=s)),
                    "pending",
                    f"status {s} should classify as pending",
                )

    def test_completed_no_conclusion_classed_pass(self):
        """status=COMPLETED with empty conclusion is treated as pass."""
        self.assertEqual(hook.classify_check(_check(status="COMPLETED")), "pass")

    def test_success_conclusion_classed_pass(self):
        self.assertEqual(hook.classify_check(_check(conclusion="SUCCESS")), "pass")

    def test_skipped_conclusion_classed_pass(self):
        self.assertEqual(hook.classify_check(_check(conclusion="SKIPPED")), "pass")

    def test_pass_bucket_classed_pass(self):
        # bucket=pass requires a non-empty conclusion or COMPLETED status to
        # bypass the empty-conclusion early-return path.
        self.assertEqual(
            hook.classify_check(_check(bucket="pass", conclusion="SUCCESS")),
            "pass",
        )

    def test_skipping_bucket_classed_pass(self):
        self.assertEqual(
            hook.classify_check(_check(bucket="skipping", conclusion="SKIPPED")),
            "pass",
        )


class NeutralAllowlistTests(unittest.TestCase):
    """Issue #219: chromatic NEUTRAL → pending; all other NEUTRAL → pass.

    Charter `pull-requests.md` § CI Must Be Green is the source of truth;
    this allowlist is the operational mapping for services whose NEUTRAL
    semantics differ from GitHub's "no opinion" default.
    """

    def test_chromatic_neutral_classed_pending(self):
        """REQUIRED test (per #219 acceptance): chromatic + NEUTRAL → block via pending."""
        self.assertEqual(
            hook.classify_check(_check(name="chromatic", conclusion="NEUTRAL")),
            "pending",
        )

    def test_chromatic_success_classed_pass(self):
        """REQUIRED test (per #219 acceptance): chromatic + SUCCESS → allow."""
        self.assertEqual(
            hook.classify_check(_check(name="chromatic", conclusion="SUCCESS")),
            "pass",
        )

    def test_other_check_neutral_still_classed_pass(self):
        """REQUIRED test (per #219 acceptance): non-chromatic + NEUTRAL → allow.

        Negative-match coverage per Hook Authorship Requirement § 3 — the
        allowlist must NOT broaden NEUTRAL → pending for unrelated checks.
        """
        for name in ("ci", "lint", "test", "build", "deploy-stg", "ruff-format"):
            with self.subTest(name=name):
                self.assertEqual(
                    hook.classify_check(_check(name=name, conclusion="NEUTRAL")),
                    "pass",
                    f"check '{name}' NEUTRAL should remain pass (preserves prior behavior)",
                )

    def test_chromatic_case_insensitive(self):
        """Display-name match is case-insensitive — `Chromatic` and `CHROMATIC` also match."""
        for variant in ("Chromatic", "CHROMATIC", "chRoMatic"):
            with self.subTest(name=variant):
                self.assertEqual(
                    hook.classify_check(_check(name=variant, conclusion="NEUTRAL")),
                    "pending",
                )

    def test_chromatic_failure_still_fail(self):
        """Allowlist doesn't soften failures — chromatic FAILURE is still fail."""
        self.assertEqual(
            hook.classify_check(_check(name="chromatic", conclusion="FAILURE")),
            "fail",
        )

    def test_chromatic_pending_status_still_pending(self):
        """If status itself is pending, classification is pending regardless of allowlist."""
        self.assertEqual(
            hook.classify_check(_check(name="chromatic", status="IN_PROGRESS")),
            "pending",
        )

    def test_allowlist_constant_uses_lowercase(self):
        """Sanity check on the constant: entries must be pre-lowercased to match the comparison."""
        for entry in hook._NEUTRAL_PENDING_CHECK_PREFIXES:
            self.assertEqual(entry, entry.lower(), f"prefix entry {entry!r} must be lowercase")

    def test_chromatic_in_allowlist(self):
        """Sanity: the canonical W4-motivated prefix is present."""
        self.assertIn("chromatic", hook._NEUTRAL_PENDING_CHECK_PREFIXES)

    def test_chromatic_multistep_shapes_match_via_prefix(self):
        """#262: multi-step Chromatic check-name shapes that the v1 exact-match
        set would have MISSED now classify pending via prefix `startswith`."""
        for name in ("Chromatic / Visual", "chromatic-visual", "Chromatic / Snapshots"):
            with self.subTest(name=name):
                self.assertEqual(
                    hook.classify_check(_check(name=name, conclusion="NEUTRAL")),
                    "pending",
                    f"'{name}' NEUTRAL should be pending (prefix match, #262)",
                )

    def test_non_prefix_neutral_still_pass(self):
        """#262 trade-off boundary: a name that merely CONTAINS but does not
        START WITH `chromatic` is NOT pend-classified (startswith, not substring)."""
        self.assertEqual(
            hook.classify_check(_check(name="Visual Tests / Chromatic", conclusion="NEUTRAL")),
            "pass",
        )


class CheckNameTests(unittest.TestCase):
    """check_name fallback chain for the allowlist match."""

    def test_name_field(self):
        self.assertEqual(hook.check_name({"name": "chromatic"}), "chromatic")

    def test_context_fallback(self):
        self.assertEqual(hook.check_name({"context": "Chromatic / Visual"}), "Chromatic / Visual")

    def test_workflow_name_fallback(self):
        self.assertEqual(
            hook.check_name({"workflowName": "chromatic-snapshots"}), "chromatic-snapshots"
        )

    def test_no_name_returns_unnamed(self):
        self.assertEqual(hook.check_name({}), "<unnamed>")


class IsMergeCommandTests(unittest.TestCase):
    """Coverage for the merge-command gate (preserves prior behavior; #219 doesn't touch this)."""

    def test_simple_merge(self):
        self.assertTrue(hook.is_merge_command("gh pr merge 123"))

    def test_merge_with_squash(self):
        self.assertTrue(hook.is_merge_command("gh pr merge 123 --squash"))

    def test_chained_merge(self):
        self.assertTrue(hook.is_merge_command("foo && gh pr merge 1"))

    def test_env_prefix(self):
        self.assertTrue(hook.is_merge_command("ENV=1 gh pr merge 1"))

    def test_pr_list_does_not_match(self):
        self.assertFalse(hook.is_merge_command("gh pr list"))

    def test_pr_view_does_not_match(self):
        self.assertFalse(hook.is_merge_command("gh pr view 1"))

    def test_pr_create_does_not_match(self):
        self.assertFalse(hook.is_merge_command("gh pr create"))

    def test_git_merge_does_not_match(self):
        self.assertFalse(hook.is_merge_command("git merge main"))


class ClassifyRollupTests(unittest.TestCase):
    """main#802: classify_rollup is the single empty/fail/pending/ready taxonomy
    shared by check() and the .claude/lib/pr_ci_state.py readiness oracle."""

    def test_empty_rollup_classed_empty(self):
        self.assertEqual(hook.classify_rollup([]), "empty")

    def test_all_pass_classed_ready(self):
        rollup = [_check(conclusion="SUCCESS"), _check(conclusion="SKIPPED")]
        self.assertEqual(hook.classify_rollup(rollup), "ready")

    def test_any_failure_classed_failing(self):
        rollup = [_check(conclusion="SUCCESS"), _check(conclusion="FAILURE")]
        self.assertEqual(hook.classify_rollup(rollup), "failing")

    def test_pending_no_failure_classed_pending(self):
        rollup = [_check(conclusion="SUCCESS"), _check(status="IN_PROGRESS")]
        self.assertEqual(hook.classify_rollup(rollup), "pending")

    def test_failure_outranks_pending(self):
        rollup = [_check(conclusion="FAILURE"), _check(status="QUEUED")]
        self.assertEqual(hook.classify_rollup(rollup), "failing")


class EmptyRollupTests(unittest.TestCase):
    """main#802: statusCheckRollup = [] — empty is a HARD not-ready state,
    discriminated by the repo's CI shape.

    Empty rollup means no CI checks reported. Origin: design-system #129's
    dropped `synchronize` event produced zero runs — NOT the same as green.
    Per main#802 (P6W1 retro, owner-approved 2026-06-21), check() now:

      - BLOCKS when a covering on.pull_request workflow with no `paths:` filter
        exists (`covering_pr_workflow_exists` → True): a check that runs on
        every PR reported nothing → anomalous dropped-trigger.
      - WARN-ALLOWS when the repo is fully path-filtered (→ False) or the signal
        is undeterminable (→ None): the legitimate docs-only zero-check case on
        noorinalabs-main/deploy is preserved (no deadlock; deploy#153 pattern).

    `fetch_pr_base_ref` + `covering_pr_workflow_exists` are mocked so the tests
    never touch the network.
    """

    @staticmethod
    def _bash_input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_empty_rollup_blocks_when_covering_workflow_exists(self):
        """[] rollup + an always-running (no-paths) workflow → BLOCK (#802)."""
        with (
            mock.patch.object(hook, "fetch_checks", return_value=[]),
            mock.patch.object(hook, "fetch_pr_base_ref", return_value="main"),
            mock.patch.object(hook, "covering_pr_workflow_exists", return_value=True),
            mock.patch.object(hook, "log_pretooluse_block"),
        ):
            result = hook.check(self._bash_input("gh pr merge 42"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("EMPTY statusCheckRollup", result["reason"])
        self.assertIn("main#802", result["reason"])

    def test_empty_rollup_warn_allows_when_fully_path_filtered(self):
        """[] rollup on a fully path-filtered repo → allow + WARNING (no deadlock)."""
        with (
            mock.patch.object(hook, "fetch_checks", return_value=[]),
            mock.patch.object(hook, "fetch_pr_base_ref", return_value="main"),
            mock.patch.object(hook, "covering_pr_workflow_exists", return_value=False),
        ):
            result = hook.check(self._bash_input("gh pr merge 42"))
        assert result is not None
        self.assertEqual(result.get("decision"), "allow")
        self.assertIn("empty statusCheckRollup", result["systemMessage"])

    def test_empty_rollup_warn_allows_when_undeterminable(self):
        """[] rollup + undeterminable coverage signal → fail-open to warn-allow."""
        with (
            mock.patch.object(hook, "fetch_checks", return_value=[]),
            mock.patch.object(hook, "fetch_pr_base_ref", return_value=None),
            mock.patch.object(hook, "covering_pr_workflow_exists", return_value=None),
        ):
            result = hook.check(self._bash_input("gh pr merge 42"))
        assert result is not None
        self.assertEqual(result.get("decision"), "allow")

    def test_warn_message_references_workflow_paths_coverage(self):
        """Warn (path-filtered) message points operator at the sibling hook."""
        with (
            mock.patch.object(hook, "fetch_checks", return_value=[]),
            mock.patch.object(hook, "fetch_pr_base_ref", return_value="main"),
            mock.patch.object(hook, "covering_pr_workflow_exists", return_value=False),
        ):
            result = hook.check(self._bash_input("gh pr merge 42"))
        assert result is not None
        self.assertIn("validate_workflow_paths_coverage", result["systemMessage"])

    def test_warn_message_references_deploy_153_incident(self):
        """Warn message cites the canonical root-cause incident for context."""
        with (
            mock.patch.object(hook, "fetch_checks", return_value=[]),
            mock.patch.object(hook, "fetch_pr_base_ref", return_value="main"),
            mock.patch.object(hook, "covering_pr_workflow_exists", return_value=False),
        ):
            result = hook.check(self._bash_input("gh pr merge 42"))
        assert result is not None
        self.assertIn("deploy#153", result["systemMessage"])

    def test_admin_with_valid_exception_skips_empty_rollup_check(self):
        """`--admin` + a valid ADMIN_MERGE_EXCEPTION short-circuits before
        fetch_checks — empty rollup never inspected (main#322)."""
        env = {"ADMIN_MERGE_EXCEPTION": "wave-merge: P3W13 wave->main wrapup"}
        with (
            mock.patch.object(hook, "fetch_checks", return_value=[]) as mock_fetch,
            mock.patch.object(hook, "log_pretooluse_block"),
            mock.patch.dict("os.environ", env, clear=False),
        ):
            result = hook.check(self._bash_input("gh pr merge 42 --admin"))
        self.assertIsNone(result)
        mock_fetch.assert_not_called()

    def test_admin_without_exception_blocks_before_fetch(self):
        """`--admin` with NO ADMIN_MERGE_EXCEPTION now BLOCKS (main#322) and
        never reaches fetch_checks — the silent bypass is closed."""
        with (
            mock.patch.object(hook, "fetch_checks", return_value=[]) as mock_fetch,
            mock.patch.object(hook, "log_pretooluse_block"),
            mock.patch.dict("os.environ", {}, clear=True),
        ):
            result = hook.check(self._bash_input("gh pr merge 42 --admin"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        mock_fetch.assert_not_called()

    def test_non_merge_command_not_checked(self):
        """`gh pr view` should not trigger empty-rollup logic at all."""
        with mock.patch.object(hook, "fetch_checks", return_value=[]) as mock_fetch:
            result = hook.check(self._bash_input("gh pr view 42"))
        self.assertIsNone(result)
        mock_fetch.assert_not_called()


class AdminMergeExceptionTests(unittest.TestCase):
    """main#322: `--admin` merges must declare a charter-listed exception via
    ADMIN_MERGE_EXCEPTION=<class>:<rationale>, else fail safe (block). This is
    the hook-time validation of the formally-listed charter exceptions that
    the org-wide branch-protection rulesets' admin-bypass relies on.

    `validate_admin_exception` reads the env var (stdin `env` block first, then
    os.environ). It returns None when authorized, a block dict otherwise.
    """

    @staticmethod
    def _input(exception: str | None) -> dict:
        env = {} if exception is None else {"ADMIN_MERGE_EXCEPTION": exception}
        return {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 42 --admin"},
            "env": env,
        }

    # --- authorized: each charter class with a rationale allows ---

    def test_each_charter_class_with_rationale_authorizes(self):
        for cls in ("wave-bootstrap", "doc-sweep", "wave-merge", "emergency"):
            with self.subTest(cls=cls):
                with mock.patch.dict("os.environ", {}, clear=True):
                    result = hook.validate_admin_exception(
                        self._input(f"{cls}: legitimate reason for {cls}")
                    )
                self.assertIsNone(result, f"{cls} with rationale must authorize")

    # --- blocked: absent / empty / unknown-class / missing-rationale ---

    def test_absent_exception_blocks(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            result = hook.validate_admin_exception(self._input(None))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_unknown_class_blocks(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            result = hook.validate_admin_exception(self._input("because-i-said-so: please"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_known_class_without_rationale_blocks(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            result = hook.validate_admin_exception(self._input("wave-merge:"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_known_class_no_colon_blocks(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            result = hook.validate_admin_exception(self._input("wave-merge"))
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_block_message_lists_valid_classes(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            result = hook.validate_admin_exception(self._input(None))
        assert result is not None
        for cls in hook._CHARTER_ADMIN_EXCEPTIONS:
            self.assertIn(cls, result["reason"])

    # --- env source precedence: os.environ fallback when no stdin env block ---

    def test_os_environ_fallback_authorizes(self):
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 42 --admin"},
        }
        with mock.patch.dict(
            "os.environ",
            {"ADMIN_MERGE_EXCEPTION": "doc-sweep: byte-identical CLAUDE.md sync"},
            clear=True,
        ):
            result = hook.validate_admin_exception(payload)
        self.assertIsNone(result)

    def test_constant_matches_charter_classes(self):
        self.assertEqual(
            set(hook._CHARTER_ADMIN_EXCEPTIONS),
            {"wave-bootstrap", "doc-sweep", "wave-merge", "emergency"},
        )


class ExtractRepoCallSiteTests(unittest.TestCase):
    """Smoke coverage that `validate_pr_ci_status` exposes `extract_repo`
    (re-exported from the shared `_repo_flag_parse` helper) and that the
    canonical `gh pr merge --repo` happy path still resolves the same
    value.

    Comprehensive parser coverage (all 4 flag forms, tokenize / regex
    fallback, malformed cases) lives in `test_repo_flag_parse.py` alongside
    the helper. These tests pin the hook's import wiring so a future
    refactor that drops the re-export trips here, not at runtime. Mirrors
    `test_validate_pr_review.ExtractRepoCallSiteTests` from #516 and
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
        """`--repo=value` form is supported post-#515 (was the documented
        latent #503-class gap in the original space-only inline parser —
        sister consolidations #513, #516 fixed it for three hooks; #515
        extends the fix to validate_pr_ci_status for the gh-pr-merge CI
        gate code path)."""
        cmd = "gh pr merge 487 --repo=noorinalabs/noorinalabs-deploy --squash"
        self.assertEqual(
            hook.extract_repo(cmd),
            "noorinalabs/noorinalabs-deploy",
        )


if __name__ == "__main__":
    unittest.main()
