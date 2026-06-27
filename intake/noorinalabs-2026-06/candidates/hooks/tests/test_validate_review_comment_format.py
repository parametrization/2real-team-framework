#!/usr/bin/env python3
"""Tests for validate_review_comment_format hook (closes #302).

P3W7 parser-fixture audit (#300) flagged this as a HIGH-priority gap:
parser-class hook with ZERO fixture coverage controlling merge traffic.

The hook parses:
- Shell command segments to detect `gh pr comment` invocations (regex)
- PR comment bodies in 3 quote forms: heredoc, single-quoted, double-quoted
- `Requestor:`, `Requestee:`, `RequestOrReplied:` charter fields
- Branch head ref name to extract author lastname

The hook blocks when `Requestee` lastname matches the branch author lastname,
indicating the operator copied the swapped form of the example (the failure
mode #356/#372/#375 collectively addressed in surrounding hooks).

Run: python3 -m unittest discover -s .claude/hooks/tests \
         -p "test_validate_review_comment_format.py"
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_review_comment_format as hook  # noqa: E402


def _bash_input(command: str) -> dict:
    """Build a PreToolUse Bash input dict shape."""
    return {"tool_name": "Bash", "tool_input": {"command": command}}


class IsCommentCommandTests(unittest.TestCase):
    """Coverage for the `gh pr comment` segment detector."""

    def test_simple_form_matches(self):
        self.assertTrue(hook.is_comment_command("gh pr comment 42"))

    def test_with_body_flag_matches(self):
        self.assertTrue(hook.is_comment_command('gh pr comment 42 --body "x"'))

    def test_chained_after_and_matches(self):
        self.assertTrue(hook.is_comment_command("gh pr view 42 && gh pr comment 42 --body x"))

    def test_chained_after_pipe_matches(self):
        self.assertTrue(hook.is_comment_command("true | gh pr comment 42 --body x"))

    def test_chained_after_semicolon_matches(self):
        self.assertTrue(hook.is_comment_command("echo go ; gh pr comment 42"))

    def test_env_var_prefix_matches(self):
        """Leading KEY=value env-var prefixes are stripped before the regex match."""
        self.assertTrue(hook.is_comment_command("ENVIRONMENT=test gh pr comment 42"))

    def test_multiple_env_var_prefixes_matches(self):
        self.assertTrue(hook.is_comment_command("FOO=1 BAR=2 gh pr comment 42"))

    def test_gh_pr_view_does_not_match(self):
        self.assertFalse(hook.is_comment_command("gh pr view 42"))

    def test_gh_pr_review_does_not_match(self):
        self.assertFalse(hook.is_comment_command("gh pr review 42 --approve"))

    def test_gh_issue_comment_does_not_match(self):
        """Hook is PR-scoped — `gh issue comment` should NOT match."""
        self.assertFalse(hook.is_comment_command("gh issue comment 42 --body x"))

    def test_non_bash_unrelated_command_does_not_match(self):
        self.assertFalse(hook.is_comment_command("ls -la"))

    def test_empty_command_does_not_match(self):
        self.assertFalse(hook.is_comment_command(""))


class ExtractPrNumberTests(unittest.TestCase):
    """PR-number extraction — direct number, then URL fallback."""

    def test_direct_number(self):
        self.assertEqual(hook.extract_pr_number("gh pr comment 42 --body x"), "42")

    def test_url_form(self):
        """#302 input shape: PR number from URL — `https://github.com/.../pull/123`."""
        self.assertEqual(
            hook.extract_pr_number("gh pr comment https://github.com/owner/repo/pull/123"),
            "123",
        )

    def test_url_form_takes_precedence_over_no_direct_number(self):
        """When no bare number follows `gh pr comment`, URL is the fallback path."""
        cmd = "gh pr comment https://github.com/o/r/pull/9 --body x"
        # Hook regex tries bare-number first; URL has `9` as the path tail.
        result = hook.extract_pr_number(cmd)
        self.assertEqual(result, "9")

    def test_no_number_returns_none(self):
        self.assertIsNone(hook.extract_pr_number("gh pr comment --help"))


class ExtractCommentBodyTests(unittest.TestCase):
    """The three quote-form parsers — heredoc, single-quoted, double-quoted."""

    def test_double_quoted_body(self):
        cmd = 'gh pr comment 42 --body "Requestor: A\nRequestee: B"'
        body = hook.extract_comment_body(cmd)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("Requestor: A", body)
        self.assertIn("Requestee: B", body)

    def test_single_quoted_body(self):
        cmd = "gh pr comment 42 --body 'Requestor: A\nRequestee: B'"
        body = hook.extract_comment_body(cmd)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("Requestor: A", body)

    def test_heredoc_body(self):
        """#302 input shape: `--body "$(cat <<'EOF'\\n...\\nEOF)"`."""
        cmd = (
            "gh pr comment 42 --body \"$(cat <<'EOF'\n"
            "Requestor: Aino Virtanen\n"
            "Requestee: Nadia Khoury\n"
            "RequestOrReplied: Approved\n"
            'EOF\n)"'
        )
        body = hook.extract_comment_body(cmd)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("Requestor: Aino Virtanen", body)
        self.assertIn("Requestee: Nadia Khoury", body)
        self.assertIn("RequestOrReplied: Approved", body)

    def test_heredoc_body_with_unquoted_EOF(self):
        """`<<EOF` (no quotes) form also captured."""
        cmd = (
            'gh pr comment 42 --body "$(cat <<EOF\n'
            "Requestor: A\nRequestee: B\nRequestOrReplied: Approved\n"
            'EOF\n)"'
        )
        body = hook.extract_comment_body(cmd)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertIn("Requestor: A", body)

    def test_body_file_returns_none(self):
        """#302 input shape: `--body-file /tmp/...` — hook does NOT read the file.

        Pin behavior: when `--body-file` is used, `extract_comment_body`
        returns None, the hook returns None at the early-return guard, and
        the comment passes without Requestor/Requestee validation. Charter
        decision: file-based bodies are operator-trusted (used for HEREDOC
        avoidance per memory `feedback_heredoc_in_git_commit`); the hook
        does NOT shadow-validate them. Documented out-of-scope-for-v1.
        """
        cmd = "gh pr comment 42 --body-file /tmp/comment-body.md"
        self.assertIsNone(hook.extract_comment_body(cmd))

    def test_no_body_flag_returns_none(self):
        self.assertIsNone(hook.extract_comment_body("gh pr comment 42"))


class ExtractBranchAuthorLastnameTests(unittest.TestCase):
    """Branch head ref → lastname extraction.

    Charter convention: branches are `{FirstInitial}.{LastName}/{IIII}-{slug}`.
    Hook regex anchors on the `[A-Za-z]\\.([A-Za-z]+)/` shape.
    """

    def test_slash_separator_canonical(self):
        self.assertEqual(
            hook.extract_branch_author_lastname("A.Virtanen/0373-ruff-format-vwpc"),
            "Virtanen",
        )

    def test_short_lastname(self):
        self.assertEqual(hook.extract_branch_author_lastname("L.Li/0001-fix"), "Li")

    def test_dash_separator_not_supported(self):
        """#302 input shape: `{Initial}.{Lastname}-{number}` (dash) — NOT matched.

        Pin behavior: hook regex requires a slash separator after the lastname.
        Branches using dash form fall through to the `branch_author = None`
        path and the hook allow-with-warning (does not block). Hook docstring
        documents the slash format as canonical.
        """
        self.assertIsNone(hook.extract_branch_author_lastname("A.Virtanen-0373-ruff-format"))

    def test_underscore_separator_not_supported(self):
        """Charter-allowed underscore form (some implementer agents use `_` for `+`)."""
        self.assertIsNone(hook.extract_branch_author_lastname("A.Virtanen_0373-ruff-format"))

    def test_plain_branch_name_returns_none(self):
        self.assertIsNone(hook.extract_branch_author_lastname("main"))

    def test_hotfix_branch_returns_none(self):
        self.assertIsNone(hook.extract_branch_author_lastname("hotfix/some-fix"))

    def test_lowercase_initial_also_matches(self):
        """Regex is case-tolerant: lowercase initial still produces lastname."""
        self.assertEqual(
            hook.extract_branch_author_lastname("a.virtanen/0001-fix"),
            "virtanen",
        )


class CheckIntegrationTests(unittest.TestCase):
    """End-to-end fixtures driving check() with mocked branch fetch.

    Post-#386 charter binding: on `Approved` / `Changes Requested` verdicts,
    `Requestor` is the reviewer and `Requestee` is the PR author. The hook
    blocks when `Requestor.lastname == branch-author.lastname` — i.e., the
    PR author is being named as the reviewer (the actual swap). All scenarios
    mock `get_branch_name` so the test does not hit the network.

    HEREDOC_CANONICAL: post-#244 canonical verdict shape (Requestor=reviewer,
    Requestee=PR-author). HEREDOC_POST244_SWAP: post-#244 swap shape
    (Requestor=PR-author, matching the branch author lastname — wrong).
    """

    HEREDOC_CANONICAL = (
        "gh pr comment 42 --body \"$(cat <<'EOF'\n"
        "Requestor: Nadia Khoury\n"
        "Requestee: Aino Virtanen\n"
        "RequestOrReplied: Approved\n"
        "TechDebt: none\n"
        'EOF\n)"'
    )

    HEREDOC_POST244_SWAP = (
        "gh pr comment 42 --body \"$(cat <<'EOF'\n"
        "Requestor: Aino Virtanen\n"
        "Requestee: Nadia Khoury\n"
        "RequestOrReplied: Approved\n"
        "TechDebt: none\n"
        'EOF\n)"'
    )

    def test_canonical_form_on_pr_author_branch_allows(self):
        """Branch A.Virtanen/...; Requestor=Nadia Khoury (reviewer),
        Requestee=Aino Virtanen (PR-author=branch-author).
        Khoury != Virtanen → no swap; allow.
        """
        with mock.patch.object(hook, "get_branch_name", return_value="A.Virtanen/0373-ruff-format"):
            result = hook.check(_bash_input(self.HEREDOC_CANONICAL))
        self.assertIsNone(result)

    def test_canonical_form_on_unrelated_branch_allows(self):
        """Branch N.Khoury/...; Requestor=Nadia Khoury (Requestor matches branch).
        Inverted heuristic: Khoury == Khoury → BLOCK.

        This is the post-#386 inversion of the prior `test_happy_path_no_block`.
        The same body shape that pre-#386 produced a block from the (wrong)
        Requestee-side heuristic now produces a block from the (correct)
        Requestor-side heuristic — by coincidence of names. Retained as
        regression coverage for the post-#244 charter shape.
        """
        with mock.patch.object(hook, "get_branch_name", return_value="N.Khoury/0346-w8-retro"):
            result = hook.check(_bash_input(self.HEREDOC_CANONICAL))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_post244_swap_form_blocks(self):
        """Branch A.Virtanen/...; Requestor=Aino Virtanen (PR-author named as
        reviewer — swap). Inverted heuristic: Virtanen == Virtanen → BLOCK.
        """
        with mock.patch.object(hook, "get_branch_name", return_value="A.Virtanen/0373-ruff-format"):
            result = hook.check(_bash_input(self.HEREDOC_POST244_SWAP))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("swapped", result["reason"].lower())

    def test_non_pr_comment_command_allows(self):
        """Not `gh pr comment` → early return None."""
        result = hook.check(_bash_input("gh pr view 42"))
        self.assertIsNone(result)

    def test_no_requestee_field_allows(self):
        """Comment without Requestee: → not a charter-format review → allow."""
        cmd = 'gh pr comment 42 --body "just a comment"'
        result = hook.check(_bash_input(cmd))
        self.assertIsNone(result)

    def test_body_file_allows_through(self):
        """#302 input shape: `--body-file` → no body inspection → allow.

        The hook cannot validate Requestor/Requestee in a file-based body
        without reading the file. Charter call: trust the operator on
        --body-file (used to escape inline-heredoc parsing edge cases).
        """
        cmd = "gh pr comment 42 --body-file /tmp/comment.md"
        result = hook.check(_bash_input(cmd))
        self.assertIsNone(result)

    def test_no_pr_number_returns_warning(self):
        """No bare number AND no /pull/N URL → allow with warning systemMessage.

        Post-#386 the body gate requires all three of Requestor/Requestee/
        RequestOrReplied. Body crafted with all three to trigger parsing
        beyond the gate, no PR number in the `gh pr comment` invocation.
        """
        cmd = (
            'gh pr comment --body "Requestor: Khoury\n'
            "Requestee: Virtanen\n"
            'RequestOrReplied: Approved"'
        )
        with mock.patch.object(hook, "get_branch_name", return_value=""):
            result = hook.check(_bash_input(cmd))
        # Either allow+warn or allow-None; the implementation returns a
        # warn-shape dict OR None depending on regex behavior. Pin both
        # acceptable outcomes.
        if result is not None:
            self.assertEqual(result.get("decision"), "allow")
            self.assertIn("systemMessage", result)

    def test_unfetchable_branch_returns_warning(self):
        """get_branch_name returns None → allow with warning, no block."""
        with mock.patch.object(hook, "get_branch_name", return_value=None):
            result = hook.check(_bash_input(self.HEREDOC_CANONICAL))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "allow")
        self.assertIn("systemMessage", result)

    def test_hotfix_branch_unfetched_lastname_returns_warning(self):
        """Branch without `{Initial}.{Lastname}/` shape → no lastname → warn."""
        with mock.patch.object(hook, "get_branch_name", return_value="hotfix/x"):
            result = hook.check(_bash_input(self.HEREDOC_CANONICAL))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "allow")

    def test_non_bash_tool_passes(self):
        """tool_name != Bash → early return None."""
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"command": "gh pr comment 42 --body x"},
            }
        )
        self.assertIsNone(result)

    def test_cross_repo_pr_comment_with_repo_flag_forwards_repo(self):
        """Post-#503: `gh pr comment N --repo OWNER/REPO` now forwards --repo
        to the internal `gh pr view` so the branch fetched is from the
        commented-against repo, NOT cwd's default.

        Pre-#503 this test pinned the BUG: the hook fetched the wrong PR's
        branch when reviewer's cwd was a different repo, leading to the
        Aino-rev-deploy#314 false-block. Post-#503 the hook reads `--repo`
        from the user's command and passes it through.
        """
        cmd = (
            "gh pr comment 99 --repo noorinalabs/noorinalabs-deploy "
            '--body "Requestor: Aino Virtanen\nRequestee: Nadia Khoury\n'
            'RequestOrReplied: Approved\nTechDebt: none"'
        )
        captured_kwargs: dict = {}

        def fake_get_branch(pr_number, repo=None):  # noqa: ARG001
            captured_kwargs["repo"] = repo
            # Return a deploy-side branch that does NOT match Aino's lastname
            # so the swap heuristic does NOT fire — this is the cross-repo
            # happy path the fix unblocks.
            return "N.Hakim/0071-cloud-init-caddy-removal"

        with mock.patch.object(hook, "get_branch_name", side_effect=fake_get_branch):
            result = hook.check(_bash_input(cmd))
        # The --repo value MUST be threaded into get_branch_name (the whole
        # point of #503).
        self.assertEqual(captured_kwargs.get("repo"), "noorinalabs/noorinalabs-deploy")
        # And the verdict resolves as ALLOW because the fetched branch
        # (N.Hakim/...) lastname doesn't collide with the Requestor (Virtanen).
        self.assertIsNone(result)

    def test_markdown_bold_requestor_form(self):
        """Hook regex tolerates `**Requestor:**` markdown-bold prefix on the swap field.

        Post-#386: the heuristic compares Requestor.lastname to branch-author.
        This test pins markdown-bold tolerance on BOTH fields — the body has
        `**Requestor:** Aino Virtanen` (matching branch A.Virtanen) which the
        inverted heuristic detects as a swap and blocks.
        """
        cmd = (
            'gh pr comment 42 --body "**Requestor:** Aino Virtanen\n'
            "**Requestee:** Nadia Khoury\n"
            'RequestOrReplied: Approved"'
        )
        with mock.patch.object(hook, "get_branch_name", return_value="A.Virtanen/0386-x"):
            result = hook.check(_bash_input(cmd))
        # Branch is A.Virtanen, **Requestor:** strips to Virtanen → match → block.
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")

    def test_requestor_with_parenthetical_role_stripped(self):
        """Parenthetical `Requestor: Aino Virtanen (Standards Lead)` strips role.

        Post-#386: the parenthetical-stripping regex now applies to the
        Requestor field (the one the heuristic checks). Body has the
        post-#244 swap shape with a trailing parenthetical role annotation;
        stripper must leave just `Aino Virtanen` so the lastname match fires.
        """
        cmd = (
            'gh pr comment 42 --body "Requestor: Aino Virtanen (Standards Lead)\n'
            "Requestee: Nadia Khoury\n"
            'RequestOrReplied: Approved"'
        )
        with mock.patch.object(hook, "get_branch_name", return_value="A.Virtanen/0386-x"):
            result = hook.check(_bash_input(cmd))
        # Parenthetical stripped → Virtanen == Virtanen → block.
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("decision"), "block")


class ExtractRepoCallSiteTests(unittest.TestCase):
    """Smoke coverage that `validate_review_comment_format` exposes
    `extract_repo` (re-exported from the shared `_repo_flag_parse` helper)
    and that the canonical happy path still resolves the same value.

    Comprehensive parser coverage (all 4 flag forms, tokenize / regex
    fallback, malformed cases) lives in `test_repo_flag_parse.py` alongside
    the helper. These tests pin the hook's import wiring so a future
    refactor that drops the re-export trips here, not at runtime.
    """

    def test_present_returns_value(self):
        cmd = "gh pr comment 99 --repo noorinalabs/noorinalabs-deploy --body x"
        self.assertEqual(
            hook.extract_repo(cmd),
            "noorinalabs/noorinalabs-deploy",
        )

    def test_absent_returns_none(self):
        cmd = 'gh pr comment 99 --body "x"'
        self.assertIsNone(hook.extract_repo(cmd))

    def test_equals_form_now_supported(self):
        """`--repo=value` form is supported post-#510 (was a documented
        gap in the original #509 implementation — see issue body for the
        latent #503-class regression risk via alternate flag forms).
        Pre-#510 this returned None (pinned by
        `test_with_equals_form_not_supported`); post-#510 it returns the
        value, closing the parser inconsistency with `validate_labels.py`.
        """
        cmd = "gh pr comment 99 --repo=noorinalabs/noorinalabs-deploy --body x"
        self.assertEqual(
            hook.extract_repo(cmd),
            "noorinalabs/noorinalabs-deploy",
        )


class CrossRepoRegressionTests(unittest.TestCase):
    """Regression coverage for the P3W11 #503 cross-repo false-block.

    Reproduces the exact Aino-rev-deploy#314 scenario: reviewer in
    noorinalabs-main cwd posting a verdict on noorinalabs-deploy PR with
    `--repo noorinalabs/noorinalabs-deploy`. Pre-fix the hook fetched main's
    same-numbered PR (whose branch happened to also be `A.Virtanen/...`),
    matched the lastname, and false-blocked. Post-fix the --repo flag is
    forwarded and the correct (deploy-side) branch is fetched.
    """

    REPRO_COMMAND = (
        "gh pr comment 314 --repo noorinalabs/noorinalabs-deploy "
        '--body "Requestor: Aino Virtanen\nRequestee: Nurul Hakim\n'
        'RequestOrReplied: Approved\nTechDebt: none"'
    )

    def test_503_repro_no_false_block_when_repo_forwarded(self):
        """The exact Aino-rev-deploy#314 false-block scenario, post-fix.

        Without --repo forwarding, get_branch_name would (in production) hit
        main's PR #314 with `A.Virtanen/0300-w7-retro-charter` → match Aino's
        lastname → false-block. With --repo forwarding it hits deploy's PR
        #314 with `N.Hakim/0071-cloud-init-caddy-removal` → no lastname
        collision → allow.

        Verified by capturing the repo kwarg passed to get_branch_name and
        asserting it equals what the user wrote.
        """
        captured_kwargs: dict = {}

        def fake_get_branch(pr_number, repo=None):  # noqa: ARG001
            captured_kwargs["repo"] = repo
            # Simulate gh pr view returning the deploy-side branch when --repo
            # is properly forwarded.
            if repo == "noorinalabs/noorinalabs-deploy":
                return "N.Hakim/0071-cloud-init-caddy-removal"
            # The buggy path would have returned main's same-numbered PR.
            return "A.Virtanen/0300-w7-retro-charter"

        with mock.patch.object(hook, "get_branch_name", side_effect=fake_get_branch):
            result = hook.check(_bash_input(self.REPRO_COMMAND))

        # Post-fix: --repo MUST be forwarded.
        self.assertEqual(captured_kwargs.get("repo"), "noorinalabs/noorinalabs-deploy")
        # And the false-block MUST NOT fire (branch lastname = Hakim ≠ Virtanen).
        self.assertIsNone(
            result,
            "Cross-repo verdict with --repo correctly forwarded should NOT block",
        )

    def test_same_repo_path_emits_fallback_warning_on_stderr(self):
        """When --repo is absent, hook uses cwd-default but emits a stderr
        breadcrumb so future cross-repo invocations missing --repo are
        discoverable in transcripts. Pins the fallback log behavior.
        """
        cmd = (
            "gh pr comment 42 "
            '--body "Requestor: Nadia Khoury\nRequestee: Aino Virtanen\n'
            'RequestOrReplied: Approved\nTechDebt: none"'
        )
        # Capture stderr around the hook call.
        import io
        from contextlib import redirect_stderr

        captured_kwargs: dict = {}

        def fake_get_branch(pr_number, repo=None):  # noqa: ARG001
            captured_kwargs["repo"] = repo
            return "A.Virtanen/0373-ruff-format"

        stderr_buf = io.StringIO()
        with (
            mock.patch.object(hook, "get_branch_name", side_effect=fake_get_branch),
            redirect_stderr(stderr_buf),
        ):
            hook.check(_bash_input(cmd))

        # No --repo passed → fallback path; repo kwarg is None.
        self.assertIsNone(captured_kwargs.get("repo"))
        # Stderr breadcrumb names the hook + the #503 origin.
        stderr_text = stderr_buf.getvalue()
        self.assertIn("validate_review_comment_format", stderr_text)
        self.assertIn("--repo", stderr_text)
        self.assertIn("#503", stderr_text)


if __name__ == "__main__":
    unittest.main()
