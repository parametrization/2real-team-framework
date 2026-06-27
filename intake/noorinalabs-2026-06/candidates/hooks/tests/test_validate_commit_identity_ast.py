#!/usr/bin/env python3
"""bashlex Bash-AST parse path for validate_commit_identity (#748 D3b).

Splits into three concerns:

1. AST extraction (`_shell_parse.iter_command_segments_ast`) — structural
   segment extraction across quoting, backslash continuation, `$(...)`,
   `&&`/`;`/`|` chains, and env-var prefixes. These assert the AST path
   specifically, so they are skipped when bashlex is not installed.

2. AST-superiority over the shlex fallback — a `git commit` hidden inside a
   `$(...)` command substitution is a REAL invocation the shlex path cannot see
   (the substitution is one quoted token) but the AST surfaces. Skipped without
   bashlex.

3. Degraded-mode safety (ALWAYS runs) — with bashlex forced unavailable (or its
   parse forced to fail), the hook must not crash and must return the SAME
   verdict via the shlex/regex fallback.

Run: ENVIRONMENT=test python3 -m pytest \
        .claude/hooks/tests/test_validate_commit_identity_ast.py -v
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import _shell_parse as sp  # noqa: E402
import validate_commit_identity as hook  # noqa: E402

_AINO = "Aino Virtanen"
_AINO_EMAIL = "parametrization+Aino.Virtanen@gmail.com"
_VALID = f'git -c user.name="{_AINO}" -c user.email="{_AINO_EMAIL}"'


def _input(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _find_git_commit(segments: list[list[str]]) -> list[str] | None:
    """Return the first `git ... commit ...` segment from AST output, else None."""
    for segment in segments:
        decoded = sp.find_git_subcommand(segment)
        if decoded is None:
            continue
        _globals, rest = decoded
        if rest and rest[0] == "commit":
            return segment
    return None


@unittest.skipUnless(sp.bashlex_available(), "bashlex not installed — AST path inactive")
class AstExtractionTests(unittest.TestCase):
    """`iter_command_segments_ast` structural extraction (bashlex present)."""

    def test_quoted_value_kept_whole(self):
        segs = sp.iter_command_segments_ast(f'{_VALID} commit -m "multi word msg"')
        self.assertIsNotNone(segs)
        commit = _find_git_commit(segs)
        self.assertIsNotNone(commit)
        self.assertIn("user.name=Aino Virtanen", commit)
        self.assertIn("multi word msg", commit)

    def test_backslash_line_continuation(self):
        """#287: backslash-newline continuation resolves to one git commit."""
        cmd = (
            f'git -c user.name="{_AINO}" \\\n'
            f'    -c user.email="{_AINO_EMAIL}" \\\n'
            f'    commit -m "continued"'
        )
        segs = sp.iter_command_segments_ast(cmd)
        self.assertIsNotNone(segs)
        self.assertIsNotNone(_find_git_commit(segs))

    def test_env_prefix_stripped(self):
        """A leading KEY=value AssignmentNode is excluded from the segment."""
        segs = sp.iter_command_segments_ast(f"FOO=bar {_VALID} commit -m x")
        self.assertIsNotNone(segs)
        commit = _find_git_commit(segs)
        self.assertIsNotNone(commit)
        self.assertEqual(commit[0], "git")
        self.assertNotIn("FOO=bar", commit)

    def test_chains_and_pipes_split(self):
        for cmd in (
            f"{_VALID} commit -m a ; ls",
            f"{_VALID} commit -m a && ls",
            f"{_VALID} commit -m a | cat",
        ):
            with self.subTest(cmd=cmd):
                segs = sp.iter_command_segments_ast(cmd)
                self.assertIsNotNone(segs)
                self.assertIsNotNone(_find_git_commit(segs))

    def test_heredoc_body_is_not_a_command(self):
        """`cat <<EOF ... git commit ... EOF` — body is data, not a command."""
        cmd = "cat <<EOF\ngit commit -m sneaky\nEOF"
        segs = sp.iter_command_segments_ast(cmd)
        self.assertIsNotNone(segs)
        self.assertIsNone(_find_git_commit(segs))

    def test_commit_in_branch_name_not_a_subcommand(self):
        cmd = "git worktree add /tmp/wt -b feature/commit-identity origin/main"
        segs = sp.iter_command_segments_ast(cmd)
        self.assertIsNotNone(segs)
        self.assertIsNone(_find_git_commit(segs))

    def test_parse_error_returns_none(self):
        """Unbalanced quote → None so the caller falls back."""
        self.assertIsNone(sp.iter_command_segments_ast('git commit -m "unbalanced'))


@unittest.skipUnless(sp.bashlex_available(), "bashlex not installed — AST path inactive")
class AstSupersedesShlexTests(unittest.TestCase):
    """Cases the AST handles that the shlex fallback cannot."""

    def test_command_sub_with_valid_identity_allowed(self):
        result = hook.check(_input(f'{_VALID} commit -m "$(echo done)"'))
        self.assertIsNone(result)

    def test_commit_hidden_in_substitution_is_blocked(self):
        """A real `git commit` inside $(...) is surfaced by the AST and blocked.

        The shlex fallback keeps the whole `$(...)` as one quoted token and so
        cannot see this commit — this is the AST-superiority case, hence the
        skipUnless guard.
        """
        result = hook.check(_input('echo "$(git commit -m sneaky)"'))
        self.assertIsNotNone(result)
        assert result is not None  # for mypy
        self.assertEqual(result.get("decision"), "block")


class DegradedModeTests(unittest.TestCase):
    """bashlex forced unavailable — fallback must give the same verdict, no crash.

    Always runs (independent of whether bashlex is actually installed) by
    monkeypatching `_shell_parse._BASHLEX_AVAILABLE`, since both
    `bashlex_available()` and `iter_command_segments_ast()` read that module
    global at call time.
    """

    def setUp(self):
        # Reset the once-per-process warning latch so the warning test is
        # deterministic regardless of test ordering.
        hook._DEGRADED_WARNED = False

    def test_valid_commit_allowed_in_degraded_mode(self):
        with mock.patch.object(sp, "_BASHLEX_AVAILABLE", False):
            with redirect_stderr(io.StringIO()):
                result = hook.check(_input(f'{_VALID} commit -m "fallback ok"'))
        self.assertIsNone(result)

    def test_missing_identity_blocked_in_degraded_mode(self):
        with mock.patch.object(sp, "_BASHLEX_AVAILABLE", False):
            with redirect_stderr(io.StringIO()):
                result = hook.check(_input('git commit -m "no identity"'))
        self.assertIsNotNone(result)
        assert result is not None  # for mypy
        self.assertEqual(result.get("decision"), "block")

    def test_degraded_mode_emits_single_warning(self):
        with mock.patch.object(sp, "_BASHLEX_AVAILABLE", False):
            buf = io.StringIO()
            with redirect_stderr(buf):
                hook.check(_input(f'{_VALID} commit -m "one"'))
                hook.check(_input(f'{_VALID} commit -m "two"'))
            stderr = buf.getvalue()
        self.assertEqual(stderr.count("degraded regex mode"), 1, stderr)
        self.assertIn("bashlex not installed", stderr)

    def test_no_crash_on_messy_command_in_degraded_mode(self):
        """A heredoc-in-$() shape must not crash the fallback path."""
        cmd = f"{_VALID} commit -m \"$(cat <<'EOF'\nmulti\nline\nEOF\n)\""
        with mock.patch.object(sp, "_BASHLEX_AVAILABLE", False):
            with redirect_stderr(io.StringIO()):
                result = hook.check(_input(cmd))
        self.assertIsNone(result)


class BashlexParseFailureFallthroughTests(unittest.TestCase):
    """bashlex present but its parse returns None → fall through to shlex path."""

    def test_parse_failure_falls_through_to_shlex(self):
        # Patch the name in the HOOK module namespace (it `from _shell_parse
        # import iter_command_segments_ast`s a bound reference), not in sp.
        with mock.patch.object(hook, "iter_command_segments_ast", return_value=None):
            # bashlex_available() stays True, so no degraded warning; the hook
            # must still validate via the shlex tokenizer.
            valid = hook.check(_input(f'{_VALID} commit -m "shlex path"'))
            self.assertIsNone(valid)
            blocked = hook.check(_input('git commit -m "no id"'))
            self.assertIsNotNone(blocked)


if __name__ == "__main__":
    unittest.main()
