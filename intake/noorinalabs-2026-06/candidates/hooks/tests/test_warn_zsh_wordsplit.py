#!/usr/bin/env python3
"""Tests for `warn_zsh_wordsplit.check()` — PreToolUse zsh bash-ism advisory (#879).

Covers the two acceptance axes:
  - FALSE-POSITIVE GUARDS: quoted forms, glob patterns, command substitutions,
    array expansions, heredoc bodies, and non-Bash tools must ALL stay silent.
  - DETECTION: each of the four patterns (set -- $scalar, for x in $scalar,
    ${!indirect}, mapfile/readarray) must fire on a risky unquoted construct.

Run from the repo root:
    python3 -m pytest .claude/hooks/tests/test_warn_zsh_wordsplit.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import warn_zsh_wordsplit as wzw  # noqa: E402


def _event(command: str) -> dict:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


# ---------------------------------------------------------------------------
# FALSE-POSITIVE GUARDS — must NOT fire
# ---------------------------------------------------------------------------


class NoMatchCases(unittest.TestCase):
    """Commands that must NOT be flagged."""

    # --- non-Bash tool ---

    def test_non_bash_tool_returns_none(self):
        evt = _event("set -- $items")
        evt["tool_name"] = "Edit"
        self.assertIsNone(wzw.check(evt))

    # --- empty / unrelated command ---

    def test_empty_command_returns_none(self):
        self.assertIsNone(wzw.check(_event("")))

    def test_unrelated_command_returns_none(self):
        self.assertIsNone(wzw.check(_event("git push origin main")))

    # --- set -- guards ---

    def test_set_dashdash_quoted_dollar_at(self):
        # set -- "$@" is the canonical safe form
        self.assertIsNone(wzw.check(_event('set -- "$@"')))

    def test_set_dashdash_bare_dollar_at(self):
        # $@ is a special parameter that doesn't word-split in a harmful way
        self.assertIsNone(wzw.check(_event("set -- $@")))

    def test_set_dashdash_bare_dollar_star(self):
        self.assertIsNone(wzw.check(_event("set -- $*")))

    def test_set_dashdash_quoted_scalar(self):
        # Quoted "$scalar" does not word-split — safe
        self.assertIsNone(wzw.check(_event('set -- "$items"')))

    # --- for-in guards ---

    def test_for_glob_pattern(self):
        self.assertIsNone(wzw.check(_event("for f in *.py; do echo $f; done")))

    def test_for_command_sub_parens(self):
        self.assertIsNone(wzw.check(_event("for x in $(ls); do echo $x; done")))

    def test_for_command_sub_backtick(self):
        self.assertIsNone(wzw.check(_event("for x in `ls`; do echo $x; done")))

    def test_for_brace_expansion(self):
        self.assertIsNone(wzw.check(_event("for i in {1..5}; do echo $i; done")))

    def test_for_literal_list(self):
        self.assertIsNone(wzw.check(_event("for x in a b c; do echo $x; done")))

    def test_for_quoted_scalar(self):
        # `for x in "$list"` — the `"` sits between `in ` and `$`, so the
        # `\s+` + `_SCALAR_REF` adjacency never matches. Quoted scalars do not
        # word-split in either shell, so this MUST stay silent.
        self.assertIsNone(wzw.check(_event('for x in "$list"; do echo $x; done')))

    def test_set_dashdash_quoted_scalar_explicit(self):
        # `set -- "$list"` — quoted; must stay silent (companion to the for case).
        self.assertIsNone(wzw.check(_event('set -- "$list"')))

    # --- path / glob / concat prefixes: $NAME is only PART of a word (#879) ---

    def test_for_path_glob_prefix_home(self):
        # for f in $HOME/*.py — $HOME is a path prefix, not a standalone scalar.
        self.assertIsNone(wzw.check(_event("for f in $HOME/*.py; do echo $f; done")))

    def test_for_path_glob_prefix_repo_root(self):
        self.assertIsNone(
            wzw.check(_event("for w in $REPO_ROOT/.claude/worktrees/*/; do echo $w; done"))
        )

    def test_for_path_concat_prefix(self):
        # for f in $dir/known_hosts — concatenation, single scalar path word.
        self.assertIsNone(wzw.check(_event("for f in $dir/known_hosts; do echo $f; done")))

    def test_set_dashdash_path_glob_prefix(self):
        # set -- $dir/*.txt — glob with a scalar prefix; SAFE in zsh.
        self.assertIsNone(wzw.check(_event("set -- $dir/*.txt")))

    def test_for_dollar_at_positional(self):
        # $@ and $* in for-in are safe
        self.assertIsNone(wzw.check(_event('for x in "$@"; do echo $x; done')))

    def test_for_array_expansion(self):
        # ${arr[@]} is explicit array expansion — safe
        self.assertIsNone(wzw.check(_event('for x in "${arr[@]}"; do echo $x; done')))

    # --- heredoc body ---

    def test_heredoc_body_set_dashdash_silent(self):
        # The dangerous construct is INSIDE the heredoc body — must not fire
        cmd = "cat <<'EOF'\nset -- $items\nEOF"
        self.assertIsNone(wzw.check(_event(cmd)))

    def test_heredoc_body_for_unquoted_silent(self):
        cmd = "cat <<'EOF'\nfor x in $list; do echo $x; done\nEOF"
        self.assertIsNone(wzw.check(_event(cmd)))

    def test_heredoc_body_indirect_silent(self):
        cmd = "cat <<'EOF'\necho ${!var}\nEOF"
        self.assertIsNone(wzw.check(_event(cmd)))

    def test_heredoc_body_mapfile_silent(self):
        cmd = "cat <<'EOF'\nmapfile -t arr < file\nEOF"
        self.assertIsNone(wzw.check(_event(cmd)))

    # --- declare / typeset — NOT flagged ---

    def test_declare_array_not_flagged(self):
        self.assertIsNone(wzw.check(_event("declare -A mydict")))

    def test_typeset_not_flagged(self):
        self.assertIsNone(wzw.check(_event("typeset -A mymap")))


# ---------------------------------------------------------------------------
# DETECTION — must fire on each pattern
# ---------------------------------------------------------------------------


class DetectionCases(unittest.TestCase):
    """Commands that MUST produce a systemMessage advisory."""

    def _assert_fires(self, command: str, expected_fragment: str | None = None) -> dict:
        result = wzw.check(_event(command))
        self.assertIsNotNone(result, f"Expected advisory for: {command!r}")
        assert result is not None  # narrowing for mypy
        msg = result.get("systemMessage", "")
        self.assertIn("ZSH-SAFETY ADVISORY", msg)
        if expected_fragment:
            self.assertIn(expected_fragment, msg)
        return result

    # Pattern 1: set -- $scalar

    def test_set_dashdash_bare_scalar(self):
        self._assert_fires("set -- $items", "set --")

    def test_set_dashdash_different_varname(self):
        self._assert_fires("set -- $spec", "bash-ism")

    def test_set_dashdash_braced_scalar_still_fires(self):
        # `set -- ${spec}` — braced standalone scalar must still fire (#879).
        self._assert_fires("set -- ${spec}", "set --")

    # Pattern 2: for VAR in $scalar

    def test_for_unquoted_scalar(self):
        self._assert_fires("for x in $list; do echo $x; done", "for")

    def test_for_unquoted_scalar_different_varname(self):
        self._assert_fires("for item in $items; do process $item; done", "for")

    def test_for_unquoted_scalar_no_semicolon(self):
        # multi-line form
        cmd = "for x in $list\ndo\n  echo $x\ndone"
        self._assert_fires(cmd, "for")

    def test_for_multiple_scalars_still_fires(self):
        # `for x in $a $b $c` — each is a standalone bare scalar; the canonical
        # gotcha must still fire after the #879 word-boundary FP fix.
        self._assert_fires("for x in $a $b $c; do echo $x; done", "for")

    def test_for_two_scalars_still_fires(self):
        # `for x in $a $b` — coordinator acceptance case (bare, space-separated).
        self._assert_fires("for x in $a $b", "for")

    def test_for_braced_scalar_still_fires(self):
        # `${list}` is a standalone scalar (braced, no subscript) — must fire.
        self._assert_fires("for x in ${list}; do echo $x; done", "for")

    # Pattern 3: ${!indirect}

    def test_indirect_expansion_simple(self):
        self._assert_fires("echo ${!varname}", "indirect")

    def test_indirect_expansion_keys(self):
        self._assert_fires("echo ${!arr[@]}", "indirect")

    def test_indirect_expansion_keys_star(self):
        self._assert_fires("echo ${!arr[*]}", "indirect")

    # Pattern 4: mapfile / readarray

    def test_mapfile(self):
        self._assert_fires("mapfile -t arr < file.txt", "mapfile")

    def test_readarray(self):
        self._assert_fires("readarray -t lines < input.txt", "mapfile")

    # Multiple patterns in one command

    def test_multiple_patterns_in_one_command(self):
        cmd = "set -- $items; mapfile -t arr < file"
        result = self._assert_fires(cmd)
        msg = result["systemMessage"]
        # Both patterns should appear
        self.assertIn("set --", msg)
        self.assertIn("mapfile", msg)

    # The systemMessage must mention the zsh-safe fix

    def test_set_dashdash_message_mentions_fix(self):
        result = wzw.check(_event("set -- $args"))
        self.assertIsNotNone(result)
        msg = result["systemMessage"]
        # Should mention an explicit array or IFS-read alternative
        self.assertTrue(
            "array" in msg.lower() or "read" in msg.lower(),
            f"Expected fix hint in: {msg!r}",
        )

    def test_for_message_mentions_fix(self):
        result = wzw.check(_event("for x in $items; do echo $x; done"))
        self.assertIsNotNone(result)
        msg = result["systemMessage"]
        self.assertTrue(
            "read" in msg.lower() or "array" in msg.lower(),
            f"Expected fix hint in: {msg!r}",
        )

    def test_indirect_message_mentions_zsh_equivalent(self):
        result = wzw.check(_event("echo ${!var}"))
        self.assertIsNotNone(result)
        msg = result["systemMessage"]
        # Should mention the zsh equivalent
        self.assertIn("(P)", msg)

    def test_mapfile_message_mentions_zsh_alternative(self):
        result = wzw.check(_event("mapfile -t arr < file"))
        self.assertIsNotNone(result)
        msg = result["systemMessage"]
        self.assertIn("read", msg.lower())


# ---------------------------------------------------------------------------
# MAIN ENTRYPOINT smoke tests
# ---------------------------------------------------------------------------


class MainEntrypoint(unittest.TestCase):
    """The standalone `main()` must exit 0 and emit JSON when a pattern fires."""

    def _run(self, payload: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(_HOOKS_DIR / "warn_zsh_wordsplit.py")],
            input=payload,
            capture_output=True,
            text=True,
        )

    def test_empty_stdin_exits_zero(self):
        proc = self._run("")
        self.assertEqual(proc.returncode, 0)

    def test_no_match_exits_zero_no_output(self):
        payload = json.dumps(_event("git push origin main"))
        proc = self._run(payload)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_match_emits_systemmessage(self):
        payload = json.dumps(_event("set -- $items"))
        proc = self._run(payload)
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertIn("systemMessage", out)
        self.assertIn("ZSH-SAFETY ADVISORY", out["systemMessage"])

    def test_match_always_exits_zero(self):
        # Advisory hook — must never exit non-zero
        payload = json.dumps(_event("mapfile -t arr < file"))
        proc = self._run(payload)
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
