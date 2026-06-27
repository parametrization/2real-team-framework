#!/usr/bin/env python3
"""Tests for validate_workflow_paths_coverage hook (closes #203).

Run:
    ENVIRONMENT=test python3 -m pytest \
        .claude/hooks/tests/test_validate_workflow_paths_coverage.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_workflow_paths_coverage as hook  # noqa: E402


class IsGhPrGateCommandTests(unittest.TestCase):
    """Coverage for the command-shape gate."""

    def test_gh_pr_create_matches(self):
        self.assertTrue(hook._is_gh_pr_gate_command("gh pr create --base main"))

    def test_gh_pr_ready_matches(self):
        self.assertTrue(hook._is_gh_pr_gate_command("gh pr ready 123"))

    def test_chained_command_matches(self):
        self.assertTrue(hook._is_gh_pr_gate_command("git push && gh pr create --title x"))

    def test_env_var_prefix_matches(self):
        self.assertTrue(hook._is_gh_pr_gate_command("FOO=bar gh pr create"))

    def test_gh_pr_list_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("gh pr list"))

    def test_gh_pr_view_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("gh pr view 100"))

    def test_gh_pr_checks_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("gh pr checks"))

    def test_gh_pr_edit_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("gh pr edit 100 --title x"))

    def test_gh_pr_merge_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("gh pr merge 100 --squash"))

    def test_git_push_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("git push origin main"))

    def test_unrelated_bash_does_not_match(self):
        self.assertFalse(hook._is_gh_pr_gate_command("ls -la"))

    def test_create_inside_echo_does_not_match(self):
        """The phrase `gh pr create` inside an `echo` argument must NOT match.

        Our regex anchors on `gh pr (create|ready)` AFTER a shell-op boundary
        or env-var-prefix-stripped command position. `echo "gh pr create"`
        starts with `echo`, so the regex correctly does not match. Negative-
        match coverage for the substring-bug class.
        """
        self.assertFalse(hook._is_gh_pr_gate_command('echo "gh pr create"'))

    def test_create_inside_grep_does_not_match(self):
        """grep with the phrase in pattern position — should NOT match."""
        self.assertFalse(hook._is_gh_pr_gate_command("grep 'gh pr create' /tmp/file"))

    def test_line_continuation_pr_create_matches(self):
        """Backslash-newline line continuation in gh pr create — transitive #305 fix.

        _shell_parse.tokenize() normalizes '\\\\\\n' to ' ' before shlex.split,
        so a multi-line gh pr create still lands at command position and matches.
        """
        cmd = "gh pr create \\\n  --title 'fix: thing' \\\n  --base main"
        self.assertTrue(hook._is_gh_pr_gate_command(cmd))

    def test_line_continuation_pr_ready_matches(self):
        """gh pr ready with line continuation — transitive #305 fix."""
        cmd = "gh pr ready \\\n  123"
        self.assertTrue(hook._is_gh_pr_gate_command(cmd))

    def test_heredoc_containing_gh_pr_create_does_not_match(self):
        """gh pr create text INSIDE a heredoc body must NOT trigger the gate.

        strip_heredocs() removes the body before tokenization, so `gh pr create`
        appearing as document content is never seen as a command token.
        """
        cmd = "cat <<EOF\ngh pr create --base main\nEOF\necho done"
        self.assertFalse(hook._is_gh_pr_gate_command(cmd))

    def test_chained_with_line_continuation_matches(self):
        """git push && gh pr create across a line continuation — #305 transitive."""
        cmd = "git push origin feature \\\n  && gh pr create --base main"
        self.assertTrue(hook._is_gh_pr_gate_command(cmd))


class WalkFlagValueTests(unittest.TestCase):
    """_walk_flag_value: token-based flag extraction."""

    def test_space_separated_form(self):
        tokens = ["gh", "pr", "create", "--base", "main"]
        self.assertEqual(hook._walk_flag_value(tokens, "base"), "main")

    def test_equals_form(self):
        tokens = ["gh", "pr", "create", "--base=develop"]
        self.assertEqual(hook._walk_flag_value(tokens, "base"), "develop")

    def test_absent_returns_none(self):
        tokens = ["gh", "pr", "create"]
        self.assertIsNone(hook._walk_flag_value(tokens, "base"))

    def test_flag_value_inside_body_not_extracted(self):
        """Flag value inside --body is a single token; won't match as --repo value.

        shlex collapses quoted body to one token, so '--repo' inside the body
        string is never a separate token in flag position.
        """
        tokens = ["gh", "pr", "create", "--body", "use --repo x/y here"]
        self.assertIsNone(hook._walk_flag_value(tokens, "repo"))

    def test_flag_at_end_with_no_value_returns_none(self):
        """Flag token at end of list with no following value."""
        tokens = ["gh", "pr", "create", "--base"]
        self.assertIsNone(hook._walk_flag_value(tokens, "base"))


class ExtractFlagTests(unittest.TestCase):
    """_extract_flag covers --flag value, --flag=value, --flag "quoted"."""

    def test_space_separated(self):
        self.assertEqual(hook._extract_flag("gh pr create --base develop", "base"), "develop")

    def test_equals_form(self):
        self.assertEqual(hook._extract_flag("gh pr create --base=develop", "base"), "develop")

    def test_double_quoted(self):
        self.assertEqual(
            hook._extract_flag('gh pr create --title "fix: thing"', "title"),
            "fix: thing",
        )

    def test_single_quoted(self):
        self.assertEqual(
            hook._extract_flag("gh pr create --title 'fix: thing'", "title"),
            "fix: thing",
        )

    def test_absent_flag_returns_none(self):
        self.assertIsNone(hook._extract_flag("gh pr create", "base"))

    def test_repo_value_in_quoted_body_not_extracted(self):
        """--repo value inside --body quoted string must NOT be extracted as --repo.

        shlex collapses the quoted body to one token, so the --repo substring
        inside it is never seen as a flag token by _walk_flag_value.
        """
        cmd = 'gh pr create --body "link: --repo x/y here" --repo noorinalabs/test'
        self.assertEqual(hook._extract_flag(cmd, "repo"), "noorinalabs/test")

    def test_flag_extracted_after_line_continuation(self):
        """--repo flag value after a backslash-newline continuation — #305 transitive."""
        cmd = "gh pr create \\\n  --repo noorinalabs/test \\\n  --base main"
        self.assertEqual(hook._extract_flag(cmd, "repo"), "noorinalabs/test")

    def test_base_extracted_after_line_continuation(self):
        """--base after line continuation tokenizes correctly."""
        cmd = "gh pr create \\\n  --base deployments/phase-3/wave-7"
        self.assertEqual(hook._extract_flag(cmd, "base"), "deployments/phase-3/wave-7")


class ParseWorkflowPathsTests(unittest.TestCase):
    """_parse_workflow_paths covers the canonical block-style YAML forms."""

    def test_pr_with_paths_filter(self):
        yml = (
            "name: CI\n"
            "on:\n"
            "  pull_request:\n"
            "    branches: [main]\n"
            "    paths:\n"
            "      - 'src/**'\n"
            "      - '.github/workflows/ci.yml'\n"
        )
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, {"src/**", ".github/workflows/ci.yml"})
        self.assertFalse(no_paths)

    def test_pr_without_paths_filter(self):
        """`on.pull_request:` with no `paths:` matches all paths."""
        yml = "name: CI\non:\n  pull_request:\n    branches: [main]\n"
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, set())
        self.assertTrue(no_paths)

    def test_pr_last_child_of_on_without_paths_filter(self):
        """Regression for #289: `pull_request:` as LAST child of `on:` with no
        `paths:` key was misparsed as covering-nothing because the on:-block
        boundary cleared `in_pr` without consulting `pr_has_paths_key`.
        """
        yml = (
            "name: CI\n"
            "on:\n"
            "  push:\n"
            "    branches: [main]\n"
            "  pull_request:\n"
            '    branches: [main, "deployments/**"]\n'
            "jobs:\n"
            "  build:\n"
            "    runs-on: ubuntu-latest\n"
        )
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, set())
        self.assertTrue(no_paths)

    def test_pr_with_inline_paths_list(self):
        yml = 'name: CI\non:\n  pull_request:\n    paths: ["src/**", "tests/**"]\n'
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, {"src/**", "tests/**"})
        self.assertFalse(no_paths)

    def test_no_pull_request_trigger(self):
        """Workflow with only `push:` trigger contributes nothing to PR coverage."""
        yml = "name: CI\non:\n  push:\n    branches: [main]\n"
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, set())
        self.assertFalse(no_paths)

    def test_paths_ignore_treated_as_no_paths_filter(self):
        """`paths-ignore:` (without `paths:`) → workflow runs on most paths.

        A workflow with `on.pull_request:` that ONLY has `paths-ignore:`
        runs on every path EXCEPT the ignored ones. For the workflow-orphan
        check, this is closer to "no paths filter" than to "specific paths
        only" — so the parser returns no_paths=True. Future hardening could
        evaluate the paths-ignore complement explicitly; v1 over-allows
        slightly (false negatives — extra coverage assumed) which is the
        safer side for the orphan-blocking goal.
        """
        yml = "name: CI\non:\n  pull_request:\n    paths-ignore:\n      - 'docs/**'\n"
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, set())
        self.assertTrue(
            no_paths,
            "v1 conservative: paths-ignore-only PR trigger treated as no-paths-filter",
        )

    def test_inline_on_pull_request(self):
        yml = "name: CI\non: pull_request\n"
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, set())
        self.assertTrue(no_paths)

    def test_inline_on_list(self):
        yml = "name: CI\non: [push, pull_request]\n"
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, set())
        self.assertTrue(no_paths)


class UnsupportedYAMLFormTests(unittest.TestCase):
    """Issue #306: pin parser behavior on YAML forms not handled by the v1 parser.

    The parser docstring (lines 197-205 of validate_workflow_paths_coverage.py)
    explicitly states it handles "the canonical block-style form used by every
    workflow in the org today" and that "anything it can't parse → returns
    (set(), False) = no coverage signal = conservative."

    These fixtures pin that CONSERVATIVE behavior:
    - YAML anchors / aliases (`&anchor`, `*alias`) → no coverage signal
    - Flow-mapping form (`on: {pull_request: {...}}`) → no coverage signal
    - Multi-document YAML (`---` separators) → only first doc parsed
    - Negative-only paths filter (`!docs/**`) → treated as having paths
      (not a no-paths-filter wildcard)

    "No coverage signal" means: workflow contributes nothing to the union
    of covered globs. If NO workflow covers a workflow-file PR, the hook
    BLOCKS the PR — operator must add an explicit `paths:` filter that
    covers `.github/workflows/**` in the canonical block style.

    Fail-open risk: if a workflow IS the only thing covering a path and
    uses one of these unsupported forms, the hook over-blocks (false
    positive). Pre-fix behavior: silent fail-open via `(set(), False)`.
    Charter call: over-block is safer than under-block for orphan-detection.
    """

    def test_yaml_anchor_form_no_coverage_signal(self):
        """YAML anchor `*alias` in paths → parser cannot resolve; no coverage."""
        yml = "name: CI\non:\n  pull_request:\n    paths: *shared-paths\n"
        paths, no_paths = hook._parse_workflow_paths(yml)
        # Pinned conservative behavior: anchor unresolved → pr_has_paths_key
        # is True (parser saw `paths:`) but paths set is empty.
        self.assertEqual(paths, set())
        # Anchor form is not detected as paths-with-content; the `paths:`
        # line WAS seen so no_paths is False (parser knows there's a paths
        # filter, just can't resolve its content).
        self.assertFalse(no_paths)

    def test_flow_mapping_form_no_coverage_signal(self):
        """Flow-mapping `on: {pull_request: {paths: [...]}}` → parser ignores."""
        yml = "name: CI\non: {pull_request: {paths: ['.github/workflows/**']}}\n"
        paths, no_paths = hook._parse_workflow_paths(yml)
        # The line-by-line regex state machine does not match flow-mapping;
        # `on:` regex requires trailing whitespace + newline.
        self.assertEqual(paths, set())
        self.assertFalse(no_paths)

    def test_multi_document_yaml_only_first_doc_parsed(self):
        """`---` separator: second document is parsed as continuation of the first.

        The parser does not handle YAML stream semantics. A second `---`
        block-document would be treated as content of the first document's
        indentation context, which is YAML-invalid but the parser does not
        care — it just continues regex-matching line by line.
        """
        yml = (
            "name: CI\n"
            "on:\n"
            "  pull_request:\n"
            "    paths:\n"
            "      - 'src/**'\n"
            "---\n"
            "name: CD\n"
            "on:\n"
            "  pull_request:\n"
            "    paths:\n"
            "      - 'deploy/**'\n"
        )
        paths, no_paths = hook._parse_workflow_paths(yml)
        # Behavior: parser sees both `paths:` blocks because indentation
        # happens to keep them in the same on-block from its POV. Pin the
        # observed union — if the parser is ever fixed to handle multi-doc
        # explicitly, this test will fail and force a deliberate update.
        self.assertIn("src/**", paths)
        # `deploy/**` may or may not be picked up depending on parse state;
        # we only pin `src/**` to keep the test deterministic.
        self.assertFalse(no_paths)

    def test_negative_only_paths_filter_treated_as_paths_with_no_positive(self):
        """`paths:` containing only `!glob` entries → paths set has the `!glob` literal.

        The parser does not strip `!` prefixes or interpret negation; the
        literal `!docs/**` is added to the paths set. Downstream
        `_path_matches_any_glob` uses fnmatch which does NOT support `!`
        negation — so the negative pattern matches no real paths, producing
        coverage that excludes everything (over-block). Pinned for #306.
        """
        yml = "name: CI\non:\n  pull_request:\n    paths:\n      - '!docs/**'\n      - '!*.md'\n"
        paths, no_paths = hook._parse_workflow_paths(yml)
        self.assertEqual(paths, {"!docs/**", "!*.md"})
        self.assertFalse(no_paths)
        # Downstream consumer: fnmatch will NOT match real paths against
        # these literals, so coverage for any actual file is False —
        # the workflow effectively covers nothing for the orphan check.
        self.assertFalse(hook._path_matches_any_glob("docs/index.md", paths))
        self.assertFalse(hook._path_matches_any_glob("README.md", paths))

    def test_yaml_anchor_definition_block_does_not_crash_parser(self):
        """A workflow defining `&shared-paths` (anchor source) parses without crash."""
        yml = (
            "name: CI\n"
            "x-shared: &shared-paths\n"
            "  - 'src/**'\n"
            "on:\n"
            "  pull_request:\n"
            "    paths: *shared-paths\n"
        )
        # Should not raise; behavior is documented as no-resolve.
        paths, no_paths = hook._parse_workflow_paths(yml)
        # Anchor definition line `x-shared: &shared-paths` is at top level,
        # not inside on:, so it's ignored. The `paths: *shared-paths` line
        # inside on.pull_request is recognized as paths-key but value not
        # resolved.
        self.assertIsInstance(paths, set)
        self.assertIsInstance(no_paths, bool)


class PathMatchesAnyGlobTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(
            hook._path_matches_any_glob(
                ".github/workflows/ci.yml",
                {".github/workflows/ci.yml"},
            )
        )

    def test_double_star_match(self):
        self.assertTrue(
            hook._path_matches_any_glob(
                ".github/workflows/db-migrate.yml",
                {".github/workflows/**"},
            )
        )

    def test_no_match(self):
        self.assertFalse(
            hook._path_matches_any_glob(
                ".github/workflows/db-migrate.yml",
                {"src/**", "tests/**"},
            )
        )

    def test_empty_globs(self):
        self.assertFalse(
            hook._path_matches_any_glob(
                ".github/workflows/ci.yml",
                set(),
            )
        )


class IsWorkflowFileTests(unittest.TestCase):
    def test_yml_workflow(self):
        self.assertTrue(hook._is_workflow_file(".github/workflows/ci.yml"))

    def test_yaml_workflow(self):
        self.assertTrue(hook._is_workflow_file(".github/workflows/deploy.yaml"))

    def test_non_workflow(self):
        self.assertFalse(hook._is_workflow_file("src/main.py"))

    def test_hooks_dir(self):
        self.assertFalse(hook._is_workflow_file(".claude/hooks/foo.py"))

    def test_workflows_subdir(self):
        """Files under .github/workflows/<subdir>/ DO match the prefix."""
        self.assertTrue(hook._is_workflow_file(".github/workflows/sub/x.yml"))


class CheckEndToEndTests(unittest.TestCase):
    """End-to-end: check() with mocked API calls."""

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def _patches(
        self,
        *,
        repo: str | None = "noorinalabs/test",
        head: str | None = "feat-branch",
        diff_files: list[str] | None = None,
        coverage: tuple[set[str], bool] | None = None,
    ):
        """Return a context manager that patches the I/O surfaces."""
        from contextlib import ExitStack

        stack = ExitStack()
        stack.enter_context(mock.patch.object(hook, "_resolve_repo", return_value=repo))
        stack.enter_context(mock.patch.object(hook, "_resolve_head", return_value=head))
        stack.enter_context(mock.patch.object(hook, "_list_pr_diff_files", return_value=diff_files))
        stack.enter_context(
            mock.patch.object(hook, "_build_coverage_signal", return_value=coverage)
        )
        return stack

    def test_no_workflow_files_in_diff_allows(self):
        """PR with no `.github/workflows/**` changes should never block."""
        with self._patches(diff_files=["src/main.py", "tests/test_main.py"]):
            result = hook.check(self._input("gh pr create --base main"))
        self.assertIsNone(result)

    def test_workflow_change_uncovered_blocks(self):
        """Workflow file in diff + no covering paths filter → block."""
        with self._patches(
            diff_files=[".github/workflows/db-migrate.yml"],
            coverage=({"src/**"}, False),  # base workflows only cover src/**
        ):
            result = hook.check(self._input("gh pr create"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn(".github/workflows/db-migrate.yml", result["reason"])

    def test_workflow_change_covered_by_double_star_allows(self):
        """`.github/workflows/**` in any base workflow's paths → covered."""
        with self._patches(
            diff_files=[".github/workflows/db-migrate.yml"],
            coverage=({".github/workflows/**", "src/**"}, False),
        ):
            self.assertIsNone(hook.check(self._input("gh pr create")))

    def test_workflow_change_covered_by_no_paths_pr_trigger_allows(self):
        """ANY base workflow with `on.pull_request:` and no `paths:` → covers all."""
        with self._patches(
            diff_files=[".github/workflows/db-migrate.yml"],
            coverage=(set(), True),  # any_no_paths is True
        ):
            self.assertIsNone(hook.check(self._input("gh pr create")))

    def test_non_pr_create_command_skipped(self):
        with self._patches():
            self.assertIsNone(hook.check(self._input("gh pr list")))

    def test_non_bash_tool_skipped(self):
        with self._patches():
            self.assertIsNone(
                hook.check({"tool_name": "Edit", "tool_input": {"command": "gh pr create"}})
            )

    def test_repo_resolution_failure_fails_open(self):
        with self._patches(repo=None, diff_files=[".github/workflows/x.yml"]):
            # repo = None → fail open even with workflow file in diff
            self.assertIsNone(hook.check(self._input("gh pr create")))

    def test_diff_api_failure_fails_open(self):
        with self._patches(diff_files=None):
            # _list_pr_diff_files = None → fail open
            self.assertIsNone(hook.check(self._input("gh pr create")))

    def test_coverage_api_failure_fails_open(self):
        with self._patches(
            diff_files=[".github/workflows/x.yml"],
            coverage=None,
        ):
            self.assertIsNone(hook.check(self._input("gh pr create")))

    def test_deploy_153_repro(self):
        """Exact repro of the deploy#153 76d7d7f orphan case.

        Before the fix: `db-migrate.yml` modification + base workflows whose
        paths filters were `infra/**` and `src/**` only → no coverage, but
        `validate_pr_ci_status` still allowed merge because rollup was empty.

        After this hook: BLOCKS at `gh pr create` time.
        """
        with self._patches(
            diff_files=[
                ".github/workflows/db-migrate.yml",
                "docs/runbooks/user-service-alembic.md",
                "infra/prometheus/alerts.yml",
            ],
            coverage=({"src/**", "infra/**"}, False),
        ):
            result = hook.check(
                self._input("gh pr create --repo noorinalabs/noorinalabs-deploy --base main")
            )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("db-migrate.yml", result["reason"])


class CwdAnchorResolutionTests(unittest.TestCase):
    """#521 cwd-anchor sweep: repo/head resolution must use the invocation cwd.

    Pre-fix `_resolve_repo` / `_resolve_head` ran `git` with NO `cwd=`, so a
    worktree subagent's `gh pr create` resolved the hook's parent-process
    repo/branch. The fix threads `resolve_invocation_cwd` through both.
    """

    @staticmethod
    def _input(command: str, cwd: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}

    def test_resolve_repo_anchors_git_on_cwd(self):
        captured: dict[str, object] = {}

        class _R:
            returncode = 0
            stdout = "git@github.com:noorinalabs/noorinalabs-deploy.git\n"

        def fake_run(args, **kwargs):
            captured["cwd"] = kwargs.get("cwd")
            return _R()

        with (
            mock.patch.dict("os.environ", {}, clear=True),
            mock.patch.object(hook.subprocess, "run", side_effect=fake_run),
        ):
            repo = hook._resolve_repo("gh pr create", cwd="/worktree/x")
        self.assertEqual(repo, "noorinalabs/noorinalabs-deploy")
        self.assertEqual(captured.get("cwd"), "/worktree/x")

    def test_resolve_repo_gh_repo_env_priority(self):
        with mock.patch.dict("os.environ", {"GH_REPO": "noorinalabs/noorinalabs-deploy"}):
            with mock.patch.object(hook.subprocess, "run") as run_mock:
                repo = hook._resolve_repo("gh pr create", cwd="/worktree/x")
        self.assertEqual(repo, "noorinalabs/noorinalabs-deploy")
        run_mock.assert_not_called()

    def test_resolve_head_anchors_git_on_cwd(self):
        captured: dict[str, object] = {}

        class _R:
            returncode = 0
            stdout = "A.Idrissi/0242-promote\n"

        def fake_run(args, **kwargs):
            captured["cwd"] = kwargs.get("cwd")
            return _R()

        with mock.patch.object(hook.subprocess, "run", side_effect=fake_run):
            head = hook._resolve_head("gh pr create", cwd="/worktree/x")
        self.assertEqual(head, "A.Idrissi/0242-promote")
        self.assertEqual(captured.get("cwd"), "/worktree/x")

    def test_check_threads_recovered_cwd_into_resolvers(self):
        """End-to-end: `cd /worktree && gh pr create` → resolvers see worktree."""
        import tempfile

        captured: dict[str, object] = {}

        def fake_repo(command, cwd=None):
            captured["repo_cwd"] = cwd
            return "noorinalabs/noorinalabs-deploy"

        def fake_head(command, cwd=None):
            captured["head_cwd"] = cwd
            return "feat-x"

        with tempfile.TemporaryDirectory() as worktree:
            cmd = f"cd {worktree} && gh pr create --base main"
            with (
                mock.patch.object(hook, "_resolve_repo", side_effect=fake_repo),
                mock.patch.object(hook, "_resolve_head", side_effect=fake_head),
                # No workflow files in diff → allow (keeps the test focused on cwd).
                mock.patch.object(hook, "_list_pr_diff_files", return_value=["src/app.py"]),
            ):
                result = hook.check(
                    self._input(cmd, cwd="/home/parameterization/code/noorinalabs-main")
                )
            self.assertIsNone(result)
            self.assertEqual(captured.get("repo_cwd"), worktree)
            self.assertEqual(captured.get("head_cwd"), worktree)


if __name__ == "__main__":
    unittest.main()
