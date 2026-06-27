"""Tests for validate_wave_label_evidence PreToolUse hook.

Covers main#337: three-occurrence W8 pattern (deploy#276, isnad-graph#866-870,
PR#871 stale-worktree) — issue bodies cite file paths that don't exist at
origin head_sha. Hook blocks wave-label application unless paths verify or
override is explicit.
"""

from __future__ import annotations

import os
import shlex
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import validate_wave_label_evidence as hook  # noqa: E402


def _bash_input(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _build_create_cmd(body: str, label: str = "p3-wave-9") -> str:
    """Build a `gh issue create` command preserving multi-line body content
    via shlex.join. Repr-style {body!r} escapes newlines as `\\n` literals
    which breaks the override-line ^ anchor at hook time."""
    return shlex.join(
        [
            "gh",
            "issue",
            "create",
            "--repo",
            "noorinalabs/noorinalabs-main",
            "--title",
            "T",
            "--body",
            body,
            "--label",
            label,
        ]
    )


def _fake_subprocess_factory(
    main_exists: set[str] | None = None,
    wave_exists: set[str] | None = None,
    issue_body: str | None = None,
):
    """Build a subprocess.run side_effect that returns 200/404 for path
    existence checks and supplies issue body for `gh issue view`."""
    main_exists = main_exists or set()
    wave_exists = wave_exists or set()

    class _Result:
        def __init__(self, returncode: int, stdout: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def fake_run(args, capture_output, text, timeout):
        if "issue" in args and "view" in args:
            return _Result(0, issue_body or "")
        if "api" in args:
            # gh api repos/<repo>/contents/<path> -f ref=<ref> ...
            try:
                contents_idx = next(i for i, a in enumerate(args) if "contents/" in a)
            except StopIteration:
                return _Result(1)
            path = args[contents_idx].split("contents/", 1)[1]
            ref_idx = args.index("-f") + 1 if "-f" in args else None
            ref = args[ref_idx].split("=", 1)[1] if ref_idx else ""
            if ref == "main" and path in main_exists:
                return _Result(0)
            if ref.startswith("deployments/") and path in wave_exists:
                return _Result(0)
            return _Result(1)
        return _Result(1)

    return fake_run


class NotAWaveLabelCommandTests(unittest.TestCase):
    """Non-wave-label invocations are passed through silently."""

    def test_gh_issue_view_not_matched(self):
        self.assertIsNone(hook.check(_bash_input("gh issue view 100")))

    def test_gh_issue_create_no_wave_label(self):
        self.assertIsNone(
            hook.check(
                _bash_input(
                    'gh issue create --repo noorinalabs/r --title T --body "B" --label "tech-debt"'
                )
            )
        )

    def test_gh_issue_edit_no_add_label(self):
        self.assertIsNone(hook.check(_bash_input("gh issue edit 100 --add-assignee user")))

    def test_non_bash_tool_passthrough(self):
        self.assertIsNone(hook.check({"tool_name": "Edit", "tool_input": {"command": "x"}}))


class CitedPathExistsAtMainTests(unittest.TestCase):
    """Acceptance (a): cited path exists at origin/main → allow."""

    def test_path_exists_at_main_allows(self):
        body = (
            "## Summary\n"
            "The hook file at noorinalabs-main/.claude/hooks/validate_pr_review.py "
            "needs an update for the W9 cascade.\n"
        )
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main --title T "
            f"--body {body!r} --label 'tech-debt,p3-wave-9'"
        )
        fake = _fake_subprocess_factory(main_exists={".claude/hooks/validate_pr_review.py"})
        with mock.patch.object(hook.subprocess, "run", side_effect=fake):
            self.assertIsNone(hook.check(_bash_input(cmd)))


class CitedPathNotFoundTests(unittest.TestCase):
    """Acceptance (c): cited path 404s at both refs → block."""

    def test_404_on_both_blocks(self):
        body = (
            "## Summary\n"
            "The hook file at noorinalabs-isnad-graph/.claude/hooks/auto_set_env_test.py "
            "should be removed per canonical-paths spec.\n"
        )
        # body must be passed as a literal string token via shlex
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main --title T "
            f"--body {body!r} --label 'tech-debt,p3-wave-9'"
        )
        fake = _fake_subprocess_factory(main_exists=set(), wave_exists=set())
        with mock.patch.object(hook.subprocess, "run", side_effect=fake):
            result = hook.check(_bash_input(cmd))
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn(
            "noorinalabs-isnad-graph/.claude/hooks/auto_set_env_test.py", result["reason"]
        )
        self.assertIn("Origin-Verification:", result["reason"])
        self.assertIn("p3-wave-9", result["reason"])

    def test_partial_404_still_allows(self):
        """If ANY cited path verifies (even one of many), allow.
        Per hook contract: `unverified == cited_paths` only when ALL fail.
        """
        body = (
            "Refs: noorinalabs-main/.claude/hooks/exists.py and "
            "noorinalabs-main/.claude/hooks/does_not_exist.py"
        )
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main --title T "
            f"--body {body!r} --label 'p3-wave-9'"
        )
        fake = _fake_subprocess_factory(main_exists={".claude/hooks/exists.py"})
        with mock.patch.object(hook.subprocess, "run", side_effect=fake):
            self.assertIsNone(hook.check(_bash_input(cmd)))


class PhaseAgnosticLabelFormTests(unittest.TestCase):
    """#810: the evidence gate triggers on the new `wave-{X}` and `wave-x`
    label forms — a new-form label must not bypass the cited-path check."""

    def test_global_form_404_blocks(self):
        """New `wave-16` form with an all-404 cited path → block (gate fires).

        Phase is recovered from status to build the wave branch ref; the cited
        path 404s at both `main` and the derived branch → block.
        """
        body = (
            "## Summary\n"
            "Remove noorinalabs-isnad-graph/.claude/hooks/auto_set_env_test.py per spec.\n"
        )
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main --title T "
            f"--body {body!r} --label 'tech-debt,wave-16'"
        )
        fake = _fake_subprocess_factory(main_exists=set(), wave_exists=set())
        with (
            mock.patch.object(hook, "_read_status_phase", return_value=6),
            mock.patch.object(hook.subprocess, "run", side_effect=fake),
        ):
            result = hook.check(_bash_input(cmd))
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("wave-16", result["reason"])
        # Wave branch ref was built from the status-recovered phase.
        self.assertIn("deployments/phase-6/wave-16", result["reason"])

    def test_placeholder_form_404_blocks(self):
        """`wave-x` placeholder with an all-404 cited path → block (main-only check)."""
        body = "Remove noorinalabs-main/.claude/hooks/gone.py per spec.\n"
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main --title T "
            f"--body {body!r} --label 'wave-x'"
        )
        fake = _fake_subprocess_factory(main_exists=set(), wave_exists=set())
        with mock.patch.object(hook.subprocess, "run", side_effect=fake):
            result = hook.check(_bash_input(cmd))
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("wave-x", result["reason"])

    def test_global_form_path_exists_allows(self):
        """New-form label but cited path verifies at main → allow."""
        body = "Refs noorinalabs-main/.claude/hooks/exists.py\n"
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main --title T "
            f"--body {body!r} --label 'wave-16'"
        )
        fake = _fake_subprocess_factory(main_exists={".claude/hooks/exists.py"})
        with (
            mock.patch.object(hook, "_read_status_phase", return_value=6),
            mock.patch.object(hook.subprocess, "run", side_effect=fake),
        ):
            self.assertIsNone(hook.check(_bash_input(cmd)))


class OriginVerificationOverrideTests(unittest.TestCase):
    """Acceptance (d): `Origin-Verification: <reason>` override bypasses check."""

    def test_override_with_path_at_ref(self):
        body = (
            "## Summary\nfoo at noorinalabs-main/.claude/hooks/missing.py\n"
            "\nOrigin-Verification: missing.py exists at deployments/phase-3/wave-7\n"
        )
        cmd = _build_create_cmd(body)
        # Even with main_exists empty, override should allow
        fake = _fake_subprocess_factory(main_exists=set())
        with mock.patch.object(hook.subprocess, "run", side_effect=fake):
            self.assertIsNone(hook.check(_bash_input(cmd)))

    def test_override_not_applicable(self):
        """Acceptance (e): `Origin-Verification: not-applicable` for pure-policy."""
        body = (
            "## Summary\nPolicy issue. References noorinalabs-main/.claude/hooks/x.py "
            "as proposed shape.\n\nOrigin-Verification: not-applicable — proposed new hook\n"
        )
        cmd = _build_create_cmd(body)
        fake = _fake_subprocess_factory(main_exists=set())
        with mock.patch.object(hook.subprocess, "run", side_effect=fake):
            self.assertIsNone(hook.check(_bash_input(cmd)))


class NoCitedPathsTests(unittest.TestCase):
    """Acceptance (f): no cited paths in body → allow without verification."""

    def test_pure_policy_no_paths(self):
        body = (
            "## Summary\nOrg-wide convention change. Should ADR numbering be 3-digit "
            "or 4-digit? No code paths cited."
        )
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main --title T "
            f"--body {body!r} --label 'p3-wave-9'"
        )
        fake = _fake_subprocess_factory(main_exists=set())
        with mock.patch.object(hook.subprocess, "run", side_effect=fake):
            self.assertIsNone(hook.check(_bash_input(cmd)))


class BodyFileTests(unittest.TestCase):
    """--body-file is read from disk."""

    def test_body_file_with_404_path_blocks(self):
        body = "## Summary\nFile at noorinalabs-main/.claude/hooks/missing.py needs work.\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(body)
            body_file = f.name
        try:
            cmd = (
                f"gh issue create --repo noorinalabs/noorinalabs-main --title T "
                f"--body-file {body_file} --label 'p3-wave-9'"
            )
            fake = _fake_subprocess_factory(main_exists=set())
            with mock.patch.object(hook.subprocess, "run", side_effect=fake):
                result = hook.check(_bash_input(cmd))
            assert result is not None
            self.assertEqual(result["decision"], "block")
        finally:
            os.unlink(body_file)


class IssueEditMatcherTests(unittest.TestCase):
    """Acceptance (h): gh issue edit --add-label triggers the verification.
    Body is fetched via gh issue view (mocked)."""

    def test_edit_with_404_path_blocks(self):
        body = "## Summary\nFile at noorinalabs-main/.claude/hooks/old.py is gone.\n"
        cmd = "gh issue edit 100 --repo noorinalabs/noorinalabs-main --add-label 'p3-wave-9'"
        fake = _fake_subprocess_factory(main_exists=set(), issue_body=body)
        with mock.patch.object(hook.subprocess, "run", side_effect=fake):
            result = hook.check(_bash_input(cmd))
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("noorinalabs-main/.claude/hooks/old.py", result["reason"])

    def test_edit_with_existing_path_allows(self):
        body = "Refers to noorinalabs-main/.claude/hooks/exists.py"
        cmd = "gh issue edit 100 --repo noorinalabs/noorinalabs-main --add-label 'p3-wave-9'"
        fake = _fake_subprocess_factory(main_exists={".claude/hooks/exists.py"}, issue_body=body)
        with mock.patch.object(hook.subprocess, "run", side_effect=fake):
            self.assertIsNone(hook.check(_bash_input(cmd)))


class WaveBranchFallbackTests(unittest.TestCase):
    """Acceptance (b): path missing at main but exists at wave branch → allow."""

    def test_path_only_at_wave_branch(self):
        body = "File at noorinalabs-isnad-graph/.claude/hooks/wave_only.py is the focus."
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main --title T "
            f"--body {body!r} --label 'p3-wave-9'"
        )
        fake = _fake_subprocess_factory(
            main_exists=set(),
            wave_exists={".claude/hooks/wave_only.py"},
        )
        with mock.patch.object(hook.subprocess, "run", side_effect=fake):
            self.assertIsNone(hook.check(_bash_input(cmd)))


class AmbientRepoResolutionTests(unittest.TestCase):
    """main#663 MUST #2: `--repo`/`-R` omitted (in-repo create/edit) resolves
    the ambient repo from the cwd origin (mirroring gh) instead of the old
    empty-default `noorinalabs/` slug. Without resolution the hook would skip
    (allow); these cases prove it reaches verification and blocks on a 404."""

    def test_ambient_create_resolves_repo_and_blocks_on_404(self):
        # No `--repo`: resolution must succeed for the hook to reach body
        # verification at all (else it skips+allows). Cited path 404s → block.
        body = "File at noorinalabs-main/.claude/hooks/missing.py is gone."
        cmd = f"gh issue create --title T --body {body!r} --label 'p3-wave-9'"
        fake = _fake_subprocess_factory(main_exists=set())
        with (
            mock.patch.object(hook, "resolve_repo_short_name", return_value="noorinalabs-main"),
            mock.patch.object(hook.subprocess, "run", side_effect=fake),
        ):
            result = hook.check(_bash_input(cmd))
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("noorinalabs-main/.claude/hooks/missing.py", result["reason"])

    def test_ambient_edit_resolves_repo_and_blocks_on_404(self):
        # `gh issue edit` WITHOUT --repo: body fetched via `gh issue view`, the
        # cited path 404s → block. Resolution feeds the ambient case.
        body = "File at noorinalabs-main/.claude/hooks/old.py is gone."
        cmd = "gh issue edit 100 --add-label 'p3-wave-9'"
        fake = _fake_subprocess_factory(main_exists=set(), issue_body=body)
        with (
            mock.patch.object(hook, "resolve_repo_short_name", return_value="noorinalabs-main"),
            mock.patch.object(hook.subprocess, "run", side_effect=fake),
        ):
            result = hook.check(_bash_input(cmd))
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("noorinalabs-main/.claude/hooks/old.py", result["reason"])

    def test_ambient_unresolvable_logs_skip_and_allows(self):
        # No `--repo` AND cwd origin unresolvable → skip diagnostic + fail-open
        # (allow), never a silent drop and never a bogus-slug false-block.
        body = "See .claude/hooks/gone.py."
        cmd = f"gh issue create --title T --body {body!r} --label 'p3-wave-9'"
        with (
            mock.patch.object(hook, "resolve_repo_short_name", return_value=None),
            mock.patch.object(hook, "log_pretooluse_diagnostic") as diag,
            mock.patch.object(hook.subprocess, "run") as run,
        ):
            self.assertIsNone(hook.check(_bash_input(cmd)))
            run.assert_not_called()
            diag.assert_called_once()


class BodyOverMatchScopingTests(unittest.TestCase):
    """main#663: label-shaped tokens in `--body` must NOT be parsed as labels;
    extraction is scoped to the actual `--label`/`--add-label` flag values."""

    def test_wave_label_shape_in_body_not_treated_as_label(self):
        # Real label is non-wave (`tech-debt`); the body documents a
        # `--add-label 'p3-wave-9'` pattern. The hook must NOT fire — no real
        # wave label is applied, so it never reaches body verification.
        body = "Documents the --add-label 'p3-wave-9' wave-label sync flow."
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main --title T "
            f"--body {body!r} --label 'tech-debt'"
        )
        with mock.patch.object(hook.subprocess, "run") as run:
            self.assertIsNone(hook.check(_bash_input(cmd)))
            run.assert_not_called()


class LineContinuationTests(unittest.TestCase):
    """main#663: shared tokenizer normalizes backslash-newline continuations
    (#287) — the old private `shlex.split` reimplementation did not."""

    def test_backslash_newline_create_still_detected(self):
        body = "noorinalabs-main/.claude/hooks/missing.py"
        cmd = (
            "gh issue create --repo noorinalabs/noorinalabs-main \\\n"
            f"  --title T --body {body!r} --label 'p3-wave-9'"
        )
        fake = _fake_subprocess_factory(main_exists=set())
        with mock.patch.object(hook.subprocess, "run", side_effect=fake):
            result = hook.check(_bash_input(cmd))
        assert result is not None
        self.assertEqual(result["decision"], "block")


if __name__ == "__main__":
    unittest.main()
