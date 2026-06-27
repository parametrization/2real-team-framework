#!/usr/bin/env python3
"""Behavioral tests for the warn_ghcr_image hook (main#663).

warn_ghcr_image parses a `gh workflow run` command and resolves the target
repo from its `-R`/`--repo` VALUE. main#663 migrated it off the ad-hoc
`re.search(r"-R\\s+...")` extractor onto the shared parsers so it obeys the
gh-command parser invariant (charter `hooks.md` § 7):

  * command-position shape detection via `_shell_parse.is_gh_subcommand`
    (a `gh workflow run` phrase inside a quoted arg is not an invocation), and
  * flag-VALUE-scoped repo extraction via `_repo_flag_parse.extract_repo`
    (an `-R`-shaped token inside a quoted `--field` value does NOT leak), and
  * ambient git-context resolution via `_shell_parse.resolve_repo_short_name`
    for the flag-omitted case — never silently dropping the command.

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_warn_ghcr_image.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import warn_ghcr_image as hook  # noqa: E402


def _input(command: str, cwd: str | None = None) -> dict:
    data: dict = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        data["cwd"] = cwd
    return data


class ShapeDetectionTests(unittest.TestCase):
    def test_non_bash_tool_passes(self):
        self.assertIsNone(
            hook.check(
                {"tool_name": "Edit", "tool_input": {"command": "gh workflow run deploy.yml"}}
            )
        )

    def test_non_workflow_run_passes(self):
        self.assertIsNone(hook.check(_input("gh pr view 42")))

    def test_workflow_run_but_not_deploy_passes(self):
        # Not a deploy/release-shaped workflow → no warning.
        self.assertIsNone(hook.check(_input("gh workflow run tests.yml")))

    def test_phrase_in_quoted_arg_is_not_an_invocation(self):
        # `gh workflow run` inside a single quoted token is data, not a command.
        cmd = 'echo "gh workflow run deploy.yml"'
        self.assertIsNone(hook.check(_input(cmd)))

    def test_malformed_quotes_fail_open(self):
        # tokenize() returns None on unbalanced quotes → warning-only hook allows.
        self.assertIsNone(hook.check(_input('gh workflow run deploy.yml -R "noorinalabs/x')))


class RepoResolutionTests(unittest.TestCase):
    """resolve_target_repo: flag-VALUE first, then ambient, never leaking."""

    def test_short_name_normalizes_owner_slash_name(self):
        self.assertEqual(
            hook._short_name("noorinalabs/noorinalabs-isnad-graph"), "noorinalabs-isnad-graph"
        )
        self.assertEqual(hook._short_name("noorinalabs-isnad-graph"), "noorinalabs-isnad-graph")
        self.assertIsNone(hook._short_name(None))

    def test_dash_r_space_form(self):
        cmd = "gh workflow run deploy.yml -R noorinalabs/noorinalabs-isnad-graph"
        self.assertEqual(hook.resolve_target_repo(_input(cmd), cmd), "noorinalabs-isnad-graph")

    def test_dash_r_equals_form(self):
        cmd = "gh workflow run deploy.yml -R=noorinalabs/noorinalabs-landing-page"
        self.assertEqual(hook.resolve_target_repo(_input(cmd), cmd), "noorinalabs-landing-page")

    def test_long_repo_flag_form(self):
        cmd = "gh workflow run deploy.yml --repo noorinalabs/noorinalabs-design-system"
        self.assertEqual(hook.resolve_target_repo(_input(cmd), cmd), "noorinalabs-design-system")

    def test_dash_r_inside_quoted_value_does_not_leak(self):
        # The #650/#659/#661 bug class: a `-R`-shaped token inside a quoted
        # --field value must NOT be extracted as the repo. The flag walker sees
        # no real `-R`, so resolution falls through to ambient (mocked None
        # here — the real resolver shells out to git, which is unstable under a
        # `git push` env where GIT_DIR leaks the parent repo). A non-None result
        # would mean the quoted `foo/bar` leaked.
        cmd = 'gh workflow run deploy.yml --field "note: pass -R foo/bar"'
        with patch.object(hook, "resolve_repo_short_name", return_value=None):
            self.assertIsNone(hook.resolve_target_repo(_input(cmd), cmd))

    def test_flag_omitted_uses_ambient_resolution(self):
        # No `-R`/`--repo` flag → resolve from the ambient git context (mirroring
        # gh), never silently drop. Mock the shared resolver to assert the
        # ambient path is taken and normalized to the short name.
        cmd = "gh workflow run deploy.yml"
        with patch.object(hook, "resolve_repo_short_name", return_value="noorinalabs-isnad-graph"):
            self.assertEqual(hook.resolve_target_repo(_input(cmd), cmd), "noorinalabs-isnad-graph")

    def test_flag_omitted_ambient_unresolvable_returns_none(self):
        cmd = "gh workflow run deploy.yml"
        with patch.object(hook, "resolve_repo_short_name", return_value=None):
            self.assertIsNone(hook.resolve_target_repo(_input(cmd), cmd))


class WarningBehaviorTests(unittest.TestCase):
    def setUp(self):
        self._orig = hook.check_ghcr_image

    def tearDown(self):
        hook.check_ghcr_image = self._orig

    def test_flag_omitted_unresolvable_emits_generic_warning(self):
        # Never silently drop: an unresolvable deploy run still warns generically.
        with patch.object(hook, "resolve_repo_short_name", return_value=None):
            result = hook.check(_input("gh workflow run deploy.yml"))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "allow")
        self.assertIn("Verify the GHCR image", result["systemMessage"])

    def test_known_repo_existing_image_no_warning(self):
        hook.check_ghcr_image = lambda image, tag="latest": True
        cmd = "gh workflow run deploy.yml -R noorinalabs/noorinalabs-isnad-graph"
        self.assertIsNone(hook.check(_input(cmd)))

    def test_known_repo_missing_image_warns_with_image(self):
        hook.check_ghcr_image = lambda image, tag="latest": False
        cmd = "gh workflow run deploy.yml -R noorinalabs/noorinalabs-isnad-graph"
        result = hook.check(_input(cmd))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("ghcr.io/noorinalabs/noorinalabs-isnad-graph", result["systemMessage"])

    def test_unmapped_repo_no_warning(self):
        # A resolved repo not in REPO_IMAGE_MAP → no warning (pre-#663 behavior).
        cmd = "gh workflow run deploy.yml -R noorinalabs/noorinalabs-main"
        self.assertIsNone(hook.check(_input(cmd)))


if __name__ == "__main__":
    unittest.main()
