#!/usr/bin/env python3
"""Tests for validate_labels hook.

Covers the W8 hook-authorship-spec requirement: NEGATIVE MATCH coverage for
the two W9 bugs (issue #113) plus regression coverage for positive cases.

Run: python3 -m pytest .claude/hooks/tests/test_validate_labels.py -v
Or:  python3 .claude/hooks/tests/test_validate_labels.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_labels as hook  # noqa: E402


class ExtractLabelsTests(unittest.TestCase):
    """Positive regression tests — labels appearing on the actual flag."""

    def test_long_flag_quoted(self):
        self.assertEqual(
            hook.extract_labels('gh issue create --label "bug"'),
            ["bug"],
        )

    def test_long_flag_unquoted(self):
        self.assertEqual(
            hook.extract_labels("gh issue create --label bug"),
            ["bug"],
        )

    def test_short_flag(self):
        self.assertEqual(
            hook.extract_labels('gh issue create -l "tech-debt"'),
            ["tech-debt"],
        )

    def test_equals_form(self):
        self.assertEqual(
            hook.extract_labels("gh issue create --label=bug"),
            ["bug"],
        )

    def test_short_equals_form(self):
        """Short-flag equals form `-l=value` — #304 fix (silent-skip pre-fix)."""
        self.assertEqual(
            hook.extract_labels("gh issue create -l=tech-debt"),
            ["tech-debt"],
        )

    def test_long_equals_comma_form(self):
        """`--label=a,b,c` — equals + comma-split combined (#304 coverage)."""
        self.assertEqual(
            hook.extract_labels("gh issue create --label=bug,tech-debt,p3-wave-9"),
            ["bug", "tech-debt", "p3-wave-9"],
        )

    def test_short_equals_comma_form(self):
        """`-l=a,b,c` — short equals + comma-split combined (#304 coverage)."""
        self.assertEqual(
            hook.extract_labels("gh issue create -l=bug,tech-debt"),
            ["bug", "tech-debt"],
        )

    def test_mixed_long_equals_and_short_equals(self):
        """`--label=a -l=b` — both equals-forms in one command (#304 coverage)."""
        self.assertEqual(
            hook.extract_labels("gh issue create --label=bug -l=tech-debt"),
            ["bug", "tech-debt"],
        )

    def test_multiple_flags(self):
        self.assertEqual(
            hook.extract_labels('gh issue create --label "bug" --label "tech-debt"'),
            ["bug", "tech-debt"],
        )

    def test_comma_separated_in_one_flag(self):
        self.assertEqual(
            hook.extract_labels('gh issue create --label "bug,tech-debt,p2-wave-9"'),
            ["bug", "tech-debt", "p2-wave-9"],
        )

    def test_mixed_short_and_long(self):
        self.assertEqual(
            hook.extract_labels('gh issue create -l bug --label "tech-debt"'),
            ["bug", "tech-debt"],
        )


class NegativeMatchLabelsTests(unittest.TestCase):
    """NEGATIVE-MATCH coverage for Bug 2 (#113) — label extraction false positives.

    Each test documents which negative-space case it guards against. The hook
    MUST NOT extract labels from text that appears inside the value of
    another flag (e.g. --body).
    """

    def test_body_containing_example_label_flag_is_ignored(self):
        """Body documents an example gh command — its --label must NOT leak."""
        cmd = (
            'gh issue create --title "real title" '
            '--body "Example: gh issue create --label fake-label-xyz" '
            "--label real-label"
        )
        labels = hook.extract_labels(cmd)
        self.assertIn("real-label", labels)
        self.assertNotIn("fake-label-xyz", labels)

    def test_body_with_code_block_label_flag_is_ignored(self):
        """Body includes a fenced code block with --label; still must not leak."""
        cmd = (
            "gh issue create --body '```bash\\ngh issue create --label ghost\\n```' --label actual"
        )
        labels = hook.extract_labels(cmd)
        self.assertIn("actual", labels)
        self.assertNotIn("ghost", labels)

    def test_body_with_short_flag_variant_is_ignored(self):
        cmd = 'gh issue create --body "see: gh issue create -l phantom" -l real'
        labels = hook.extract_labels(cmd)
        self.assertIn("real", labels)
        self.assertNotIn("phantom", labels)

    def test_title_with_label_flag_text_is_ignored(self):
        """Prose in --title that contains `--label X` must not be extracted."""
        cmd = 'gh issue create --title "use --label flag correctly" --label documentation'
        labels = hook.extract_labels(cmd)
        self.assertEqual(labels, ["documentation"])

    def test_no_label_flag_returns_empty(self):
        self.assertEqual(
            hook.extract_labels('gh issue create --title "x" --body "y"'),
            [],
        )

    def test_unrelated_command_returns_empty(self):
        self.assertEqual(
            hook.extract_labels("echo hello --label world"),
            ["world"],  # extract_labels is pure; the gate in check() filters
        )


class TokenizeFailureFallbackTests(unittest.TestCase):
    """#661 — when shlex tokenization FAILS, label extraction must NOT scoop
    label-shaped tokens out of `--body`/`--title` prose.

    The prior fallback ran a `(?:--label|-l)`-anchored regex over the WHOLE
    command on shlex failure, which over-matched documented label patterns in
    the issue body and false-blocked a legitimate `gh issue create`. The fix
    fails OPEN (returns []) instead of over-matching.
    """

    def test_exact_issue_661_reproducer_does_not_leak_body_label(self):
        """The live P4W7 repro: body documents ``--label `p{N}-wave-{M}` `` and
        contains an apostrophe ("gh's") that breaks shlex. The real flag is
        `--label bug`; the documented pattern MUST NOT be extracted."""
        body = "This hook validates --label `p{N}-wave-{M}` tokens. Note gh's resolution."
        cmd = f"gh issue create --repo noorinalabs/noorinalabs-main --label bug --body '{body}'"
        from _shell_parse import tokenize

        self.assertIsNone(tokenize(cmd), "precondition: this command must break shlex")
        labels = hook.extract_labels(cmd)
        self.assertNotIn("`p{N}-wave-{M}`", labels)
        self.assertNotIn("p{N}-wave-{M}", labels)

    def test_tokenize_failure_returns_empty_not_body_tokens(self):
        """A `-l`/`--label` substring inside a quote-broken body must not leak."""
        body = "see -l phantom and --label ghost; can't parse this"
        cmd = f"gh issue create --label real --body '{body}'"
        from _shell_parse import tokenize

        self.assertIsNone(tokenize(cmd))
        self.assertEqual(hook.extract_labels(cmd), [])

    def test_check_does_not_block_on_malformed_quote_body(self):
        """End-to-end: the #661 reproducer must ALLOW (no spurious block)."""
        body = "Documents --label `p{N}-wave-{M}`. Mentions gh's ambient repo."
        cmd = f"gh issue create --repo noorinalabs/noorinalabs-main --label bug --body '{body}'"
        with mock.patch.object(hook, "get_existing_labels", return_value={"bug"}):
            result = hook.check({"tool_name": "Bash", "tool_input": {"command": cmd}})
        self.assertIsNone(result, f"unexpected block on malformed-quote body: {result}")


class ExtractRepoTests(unittest.TestCase):
    """Coverage for Bug 1 (#113) — --repo flag pass-through."""

    def test_long_flag(self):
        self.assertEqual(
            hook.extract_repo(
                "gh issue create --repo noorinalabs/noorinalabs-isnad-graph --label bug"
            ),
            "noorinalabs/noorinalabs-isnad-graph",
        )

    def test_short_flag(self):
        self.assertEqual(
            hook.extract_repo("gh issue create -R owner/repo --label bug"),
            "owner/repo",
        )

    def test_equals_form(self):
        self.assertEqual(
            hook.extract_repo("gh issue create --repo=owner/repo --label bug"),
            "owner/repo",
        )

    def test_no_repo_flag(self):
        self.assertIsNone(
            hook.extract_repo("gh issue create --label bug"),
        )

    def test_repo_token_in_body_is_ignored(self):
        """`--repo ghost/ghost` inside --body must not leak as the target repo."""
        cmd = (
            "gh issue create "
            '--body "sample: gh issue create --repo ghost/ghost" '
            "--repo real/real --label bug"
        )
        self.assertEqual(hook.extract_repo(cmd), "real/real")


class GateMatchingTests(unittest.TestCase):
    """The `check()` gate fires ONLY on gh issue create, not siblings."""

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_gh_issue_list_is_ignored(self):
        self.assertIsNone(hook.check(self._input("gh issue list --label bug")))

    def test_gh_issue_view_is_ignored(self):
        self.assertIsNone(hook.check(self._input("gh issue view 1 --label bug")))

    def test_gh_pr_create_is_ignored(self):
        self.assertIsNone(hook.check(self._input("gh pr create --label bug")))

    def test_non_bash_tool_is_ignored(self):
        self.assertIsNone(
            hook.check(
                {
                    "tool_name": "Edit",
                    "tool_input": {"command": "gh issue create --label bug"},
                }
            )
        )

    def test_command_without_label_flag_is_allowed(self):
        self.assertIsNone(hook.check(self._input('gh issue create --title "x" --body "y"')))


class CheckEndToEndTests(unittest.TestCase):
    """End-to-end `check()` with get_existing_labels mocked.

    These verify that Bug 1 is fixed: when the user passes --repo OWNER/REPO,
    we forward it to get_existing_labels() so label validation hits the
    correct repo.
    """

    @staticmethod
    def _input(command: str) -> dict:
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_repo_is_forwarded_to_get_existing_labels(self):
        """Bug 1: --repo must be passed through to the label fetch."""
        with mock.patch.object(
            hook, "get_existing_labels", return_value={"frontend", "bug"}
        ) as mocked:
            result = hook.check(
                self._input(
                    "gh issue create --repo noorinalabs/noorinalabs-isnad-graph "
                    '--title "t" --body "b" --label frontend'
                )
            )
        self.assertIsNone(result)
        mocked.assert_called_once_with(repo="noorinalabs/noorinalabs-isnad-graph")

    def test_missing_label_blocks(self):
        with mock.patch.object(hook, "get_existing_labels", return_value={"bug"}):
            result = hook.check(self._input("gh issue create --label does-not-exist"))
        self.assertIsNotNone(result)
        self.assertEqual(result["decision"], "block")
        self.assertIn("does-not-exist", result["reason"])

    def test_body_containing_fake_label_does_not_block(self):
        """Bug 2: a body-quoted --label must NOT cause a spurious block."""
        with mock.patch.object(hook, "get_existing_labels", return_value={"bug"}):
            result = hook.check(
                self._input(
                    'gh issue create --body "example: gh issue create --label fake" --label bug'
                )
            )
        self.assertIsNone(result, f"unexpected block: {result}")

    def test_body_plus_wrong_repo_would_block_without_bug1_fix(self):
        """Combined scenario from issue #113: body-leak + cross-repo label.

        The user creates an issue in repo A with a real label that exists in
        repo A. Body documents an example command referencing repo B and a
        non-existent label. Neither the body's --repo nor --label may leak.
        """

        def fake_get_existing_labels(repo=None):
            if repo == "noorinalabs/noorinalabs-isnad-graph":
                return {"frontend"}
            return {"other-label"}  # would be returned if cwd-resolved

        with mock.patch.object(hook, "get_existing_labels", side_effect=fake_get_existing_labels):
            result = hook.check(
                self._input(
                    "gh issue create --repo noorinalabs/noorinalabs-isnad-graph "
                    '--body "example: gh issue create --repo ghost/ghost --label nope" '
                    "--label frontend"
                )
            )
        self.assertIsNone(result, f"unexpected block: {result}")

    def test_no_labels_to_validate_is_allowed(self):
        with mock.patch.object(hook, "get_existing_labels", return_value={"bug"}) as mocked:
            result = hook.check(self._input('gh issue create --title "t" --body "b"'))
        self.assertIsNone(result)
        mocked.assert_not_called()

    def test_label_fetch_failure_warns_not_blocks(self):
        with mock.patch.object(hook, "get_existing_labels", return_value=set()):
            result = hook.check(self._input("gh issue create --label any"))
        self.assertIsNotNone(result)
        self.assertEqual(result["decision"], "allow")


if __name__ == "__main__":
    unittest.main()
