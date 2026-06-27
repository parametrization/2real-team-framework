#!/usr/bin/env python3
"""Tests for enforce_librarian_consulted hook.

As of #857 the hook is ADVISORY, not blocking: it never denies an edit. When
the librarian has not been consulted it returns a dict with a `systemMessage`
advisory; otherwise it returns None (allow silently). `main()` always exits 0.

Covers the W8 hook-authorship-spec requirement: NEGATIVE MATCH coverage.
Each test documents which negative-space case it guards against.

Run: python3 -m pytest .claude/hooks/tests/test_enforce_librarian_consulted.py -v
Or:  python3 .claude/hooks/tests/test_enforce_librarian_consulted.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Put the hooks dir on sys.path so we can import the hook module.
_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import enforce_librarian_consulted as hook  # noqa: E402


def _assert_advisory(testcase: unittest.TestCase, result: dict | None) -> None:
    """Assert `result` is the advisory form (non-blocking systemMessage)."""
    assert result is not None  # mypy narrowing
    testcase.assertIn("systemMessage", result, "advisory must carry a systemMessage")
    testcase.assertIn(
        "/ontology-librarian",
        result["systemMessage"],
        "advisory message must reference the librarian skill",
    )
    # An advisory must NOT carry a blocking decision (regression guard for the
    # #857 softening — a stray `decision: block` would re-introduce the gate).
    testcase.assertNotEqual(result.get("decision"), "block", "advisory must not block")


def _write_transcript(lines: list[dict]) -> str:
    """Write transcript lines to a temp file, return its path."""
    fd, path = tempfile.mkstemp(suffix=".jsonl", prefix="librarian_test_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")
    return path


def _librarian_user_line(text: str = "/ontology-librarian narrator API") -> dict:
    """User message with a slash-command invocation (string content form)."""
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": (
                "<command-message>ontology-librarian</command-message>\n"
                f"<command-name>{text}</command-name>"
            ),
        },
    }


def _librarian_skill_call() -> dict:
    """Assistant tool_use invoking the Skill tool with ontology-librarian."""
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Skill",
                    "input": {"skill": "ontology-librarian", "args": "hooks"},
                }
            ],
        },
    }


def _unrelated_user_text() -> dict:
    return {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": "please fix the bug"}]},
    }


def _unrelated_skill_call() -> dict:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Skill",
                    "input": {"skill": "ontology-rebuild"},
                }
            ],
        },
    }


class AllowListTests(unittest.TestCase):
    """Paths that should NEVER trigger an advisory (negative-match cases)."""

    def _transcript_no_librarian(self) -> str:
        return _write_transcript([_unrelated_user_text(), _unrelated_skill_call()])

    def test_tmp_path_allowed_without_librarian(self) -> None:
        """NEG: /tmp/foo.md edits must not warn — out-of-repo scratch."""
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/tmp/foo.md"},
                "transcript_path": self._transcript_no_librarian(),
            }
        )
        self.assertIsNone(result, "edits under /tmp must be silent without librarian")

    def test_memory_md_allowed_without_librarian(self) -> None:
        """NEG: MEMORY.md (any location) is the auto-memory index, not code."""
        result = hook.check(
            {
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "/home/parameterization/.claude/projects/proj/memory/MEMORY.md"
                },
                "transcript_path": self._transcript_no_librarian(),
            }
        )
        self.assertIsNone(result, "MEMORY.md must be silent without librarian")

    def test_memory_subdir_allowed_without_librarian(self) -> None:
        """NEG: files under .../memory/ are project memory, not code."""
        result = hook.check(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/anywhere/memory/handoff.md"},
                "transcript_path": self._transcript_no_librarian(),
            }
        )
        self.assertIsNone(result, "memory/ files must be silent")

    def test_user_claude_config_allowed_without_librarian(self) -> None:
        """NEG: ~/.claude/** is user config, not source code."""
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": os.path.expanduser("~/.claude/preferences.json")},
                "transcript_path": self._transcript_no_librarian(),
            }
        )
        self.assertIsNone(result, "~/.claude/** must be silent")

    def test_annunaki_error_log_allowed_without_librarian(self) -> None:
        """NEG: .claude/annunaki/errors.jsonl is hook-managed, not hand-edited."""
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/.claude/annunaki/errors.jsonl",
                },
                "transcript_path": self._transcript_no_librarian(),
            }
        )
        self.assertIsNone(result, ".claude/annunaki/ must be silent")


class NonMatchedToolTests(unittest.TestCase):
    """Tools OTHER than Edit/Write/NotebookEdit must never warn."""

    def test_bash_does_not_warn(self) -> None:
        """NEG: Bash is not in the matcher set — must return None."""
        result = hook.check(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
                "transcript_path": _write_transcript([]),
            }
        )
        self.assertIsNone(result)

    def test_read_does_not_warn(self) -> None:
        """NEG: Read is not a code-change tool; must not match."""
        result = hook.check(
            {
                "tool_name": "Read",
                "tool_input": {"file_path": "/anywhere/code.py"},
                "transcript_path": _write_transcript([]),
            }
        )
        self.assertIsNone(result)

    def test_grep_does_not_warn(self) -> None:
        """NEG: Grep is read-only discovery, not a code-change tool."""
        result = hook.check(
            {
                "tool_name": "Grep",
                "tool_input": {"pattern": "foo"},
                "transcript_path": _write_transcript([]),
            }
        )
        self.assertIsNone(result)


class AdvisoryTests(unittest.TestCase):
    """In-scope code edits without librarian must ADVISE (not block)."""

    def test_compose_edit_without_librarian_advises(self) -> None:
        """POS: the canonical case from #150 — compose edit without librarian.

        Pre-#857 this BLOCKED; now it must advise and allow.
        """
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/noorinalabs-deploy/compose/docker-compose.prod.yml"
                },
                "transcript_path": _write_transcript(
                    [_unrelated_user_text(), _unrelated_skill_call()]
                ),
            }
        )
        _assert_advisory(self, result)

    def test_notebook_edit_without_librarian_advises(self) -> None:
        """POS: NotebookEdit is in the matcher set."""
        result = hook.check(
            {
                "tool_name": "NotebookEdit",
                "tool_input": {"notebook_path": "/repo/analysis.ipynb"},
                "transcript_path": _write_transcript([]),
            }
        )
        _assert_advisory(self, result)

    def test_write_on_charter_advises_without_librarian(self) -> None:
        """POS: .claude/team/ files are project state — advise librarian.

        (Stance documented in the hook docstring: meta-files advise librarian.)
        """
        result = hook.check(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": "/repo/.claude/team/feedback_log.md"},
                "transcript_path": _write_transcript([]),
            }
        )
        _assert_advisory(self, result)

    def test_empty_transcript_advises_real_code_edit(self) -> None:
        """POS: no transcript evidence -> advise."""
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/repo/src/foo.py"},
                "transcript_path": _write_transcript([]),
            }
        )
        _assert_advisory(self, result)


class AllowWithLibrarianTests(unittest.TestCase):
    """Transcripts WITH a librarian call must stay silent on in-scope edits."""

    def test_compose_edit_with_slash_command_silent(self) -> None:
        """POS: same compose path, but transcript has /ontology-librarian user line."""
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/noorinalabs-deploy/compose/docker-compose.prod.yml"
                },
                "transcript_path": _write_transcript(
                    [_librarian_user_line(), _unrelated_user_text()]
                ),
            }
        )
        self.assertIsNone(result, "librarian consulted -> no advisory")

    def test_compose_edit_with_skill_call_silent(self) -> None:
        """POS: librarian invoked via Skill tool -> silent."""
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "/repo/noorinalabs-deploy/compose/docker-compose.prod.yml"
                },
                "transcript_path": _write_transcript([_librarian_skill_call()]),
            }
        )
        self.assertIsNone(result)

    def test_librarian_anywhere_in_transcript_counts(self) -> None:
        """POS: librarian invocation need only exist somewhere in the session."""
        lines = [
            _unrelated_user_text(),
            _unrelated_skill_call(),
            _librarian_skill_call(),
            _unrelated_user_text(),
        ]
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/repo/src/code.py"},
                "transcript_path": _write_transcript(lines),
            }
        )
        self.assertIsNone(result)


class FailOpenTests(unittest.TestCase):
    """Transcript-readability edge cases.

    Since the hook is advisory (#857), the worst case is a spurious advisory,
    never a blocked edit. An UNREADABLE transcript (OSError) fails open and
    stays silent; an ABSENT/empty transcript path yields the advisory (no
    evidence the librarian ran).
    """

    def test_missing_transcript_file_advises(self) -> None:
        """A nonexistent transcript path -> no librarian evidence -> advise."""
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/repo/src/code.py"},
                "transcript_path": "/nonexistent/transcript.jsonl",
            }
        )
        _assert_advisory(self, result)

    def test_no_transcript_path_advises(self) -> None:
        """Empty transcript_path -> no evidence -> advise."""
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/repo/src/code.py"},
                "transcript_path": "",
            }
        )
        _assert_advisory(self, result)


class SignalDetectionTests(unittest.TestCase):
    """Unit-level tests for _content_has_librarian_signal."""

    def test_string_content_with_slash_command(self) -> None:
        self.assertTrue(hook._content_has_librarian_signal("please run /ontology-librarian hooks"))

    def test_string_content_without_slash_command(self) -> None:
        self.assertFalse(hook._content_has_librarian_signal("please run /ontology-rebuild"))

    def test_text_block_with_slash_command(self) -> None:
        self.assertTrue(
            hook._content_has_librarian_signal(
                [{"type": "text", "text": "/ontology-librarian foo"}]
            )
        )

    def test_skill_call_with_librarian(self) -> None:
        self.assertTrue(
            hook._content_has_librarian_signal(
                [
                    {
                        "type": "tool_use",
                        "name": "Skill",
                        "input": {"skill": "ontology-librarian"},
                    }
                ]
            )
        )

    def test_skill_call_with_different_skill_rejected(self) -> None:
        """NEG: Skill tool with a DIFFERENT skill name must not trigger."""
        self.assertFalse(
            hook._content_has_librarian_signal(
                [
                    {
                        "type": "tool_use",
                        "name": "Skill",
                        "input": {"skill": "ontology-rebuild"},
                    }
                ]
            )
        )

    def test_other_tool_use_ignored(self) -> None:
        """NEG: tool_use blocks for non-Skill tools are irrelevant."""
        self.assertFalse(
            hook._content_has_librarian_signal(
                [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "/ontology-librarian"},
                    }
                ]
            )
        )


class SentinelFallbackTests(unittest.TestCase):
    """Sentinel fallback for #169 — transcript-flush race in worktree subagents.

    Each test uses an isolated tmp cwd so sentinel state cannot leak across
    tests or across the host's real .claude/.consulted/ dir.
    Tmp roots are placed outside /tmp so the hook's /tmp allow-list does not
    short-circuit the sentinel/transcript checks we are exercising.
    """

    def setUp(self) -> None:
        # Tmp root outside /tmp — /tmp is on the hook's allow-list, which
        # would short-circuit before the sentinel check we are testing.
        self._tmp_root = tempfile.mkdtemp(prefix="librarian_sentinel_", dir=os.path.expanduser("~"))

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmp_root, ignore_errors=True)

    def _make_cwd(self, name: str) -> str:
        cwd = os.path.join(self._tmp_root, name)
        os.makedirs(cwd, exist_ok=True)
        return cwd

    def _write_sentinel(self, cwd: str, *, mtime_offset: float = 0.0) -> Path:
        """Write a sentinel for the given cwd; optionally shift mtime backwards."""
        sentinel_dir = Path(cwd) / hook.SENTINEL_DIR_NAME
        sentinel_dir.mkdir(parents=True, exist_ok=True)
        sentinel = sentinel_dir / f"{hook._cwd_sentinel_hash(cwd)}.marker"
        sentinel.write_text(f"2026-04-21T00:00:00Z {cwd}\n", encoding="utf-8")
        if mtime_offset:
            new_time = time.time() + mtime_offset
            os.utime(sentinel, (new_time, new_time))
        return sentinel

    def test_fresh_sentinel_silent(self) -> None:
        """POS: sentinel written just now -> silent even with empty transcript.

        This is the #169 worktree-subagent path: transcript flush lagged, but
        the librarian skill wrote a sentinel synchronously.
        """
        cwd = self._make_cwd("fresh")
        self._write_sentinel(cwd)
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": os.path.join(cwd, "src/foo.py")},
                "transcript_path": _write_transcript([]),  # no librarian in transcript
                "cwd": cwd,
            }
        )
        self.assertIsNone(result, "fresh sentinel must suppress the advisory")

    def test_stale_sentinel_advises(self) -> None:
        """NEG: sentinel older than TTL -> must not attest, edit advises."""
        cwd = self._make_cwd("stale")
        # Older than TTL.
        self._write_sentinel(cwd, mtime_offset=-(hook.SENTINEL_TTL_SECONDS + 60))
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": os.path.join(cwd, "src/foo.py")},
                "transcript_path": _write_transcript([]),
                "cwd": cwd,
            }
        )
        _assert_advisory(self, result)

    def test_sentinel_in_different_cwd_advises(self) -> None:
        """NEG: a sentinel keyed to a DIFFERENT cwd must not attest.

        Guards the cwd-keyed isolation property: an orchestrator sentinel
        in the main-repo cwd must not suppress the advisory for a subagent
        in a worktree cwd.
        """
        other_cwd = self._make_cwd("other")
        my_cwd = self._make_cwd("mine")
        # Sentinel exists for other_cwd only.
        self._write_sentinel(other_cwd)
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": os.path.join(my_cwd, "src/foo.py")},
                "transcript_path": _write_transcript([]),
                "cwd": my_cwd,  # different cwd — no matching sentinel here
            }
        )
        _assert_advisory(self, result)

    def test_no_sentinel_but_librarian_in_transcript_silent(self) -> None:
        """POS regression guard: sentinel absent, transcript has librarian -> silent.

        Ensures the sentinel addition did not break the pre-existing
        transcript-scan acceptance signal.
        """
        cwd = self._make_cwd("no_sentinel")
        # No sentinel written.
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": os.path.join(cwd, "src/foo.py")},
                "transcript_path": _write_transcript([_librarian_skill_call()]),
                "cwd": cwd,
            }
        )
        self.assertIsNone(result, "transcript signal must still suppress when sentinel absent")

    def test_no_sentinel_and_no_librarian_advises(self) -> None:
        """NEG: neither signal present -> advise (baseline nudge holds)."""
        cwd = self._make_cwd("neither")
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": os.path.join(cwd, "src/foo.py")},
                "transcript_path": _write_transcript([]),
                "cwd": cwd,
            }
        )
        _assert_advisory(self, result)

    def test_cwd_hash_matches_shell_pwd_sha1sum(self) -> None:
        """Parity guard: Python hash must match `pwd | sha1sum | cut -c1-16`.

        The librarian skill writes the sentinel via shell; if the hook's
        Python hash diverges, no sentinel would ever match.
        """
        import hashlib

        sample = "/home/parameterization/code/noorinalabs-main"
        # Shell `pwd` output ends with newline before `sha1sum` consumes it.
        expected = hashlib.sha1((sample + "\n").encode("utf-8")).hexdigest()[:16]
        self.assertEqual(hook._cwd_sentinel_hash(sample), expected)


class ShellPythonHashParityTests(unittest.TestCase):
    """Issue #175 — subprocess-based shell/Python hash parity.

    The existing `test_cwd_hash_matches_shell_pwd_sha1sum` spot-check above
    re-implements the same algorithm in test code and asserts it equals the
    hook's Python function. That's a Python-vs-Python parity check; it does
    NOT catch divergence between the librarian skill's actual shell pipeline
    (`pwd | sha1sum | cut -c1-16`) and the Python implementation.

    These tests close that gap by:
      1. Running the exact shell pipeline from SKILL.md in an isolated cwd
         and asserting the resulting filename matches the Python hash.
      2. Parsing the shell snippet directly out of SKILL.md so the test
         fails if the skill drifts (e.g., switches to `realpath`, uses a
         different cut width, etc.).
    """

    # Resolve SKILL.md once at class-load — fail fast at collection time if
    # the layout has shifted, before any test runs.
    _SKILL_MD = (
        Path(__file__).resolve().parent.parent.parent / "skills" / "ontology-librarian" / "SKILL.md"
    )

    def _read_skill_md(self) -> str:
        self.assertTrue(
            self._SKILL_MD.is_file(),
            f"Expected SKILL.md at {self._SKILL_MD} — test cannot validate parity "
            "without the canonical shell pipeline source",
        )
        return self._SKILL_MD.read_text(encoding="utf-8")

    def test_shell_pipeline_matches_python_hash_in_isolated_cwd(self) -> None:
        """Run `pwd | sha1sum | cut -c1-16` in an isolated cwd. Assert the
        resulting 16-hex prefix matches `_cwd_sentinel_hash(cwd)`.

        Uses `subprocess.run(..., cwd=tmp_dir)` so the shell `pwd` resolves
        to the test's tmp cwd, not the test runner's cwd. The pipeline is
        passed verbatim from SKILL.md step 0 (the literal bash snippet that
        the librarian skill writes the sentinel filename from).
        """
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory(prefix="hash_parity_") as tmp:
            # Realpath to defeat any /tmp -> /private/tmp on macOS or symlink
            # surprises; Python's `os.path.abspath` does the same resolution
            # the hook applies before hashing.
            tmp_abs = os.path.abspath(tmp)
            result = subprocess.run(
                ["bash", "-c", "pwd | sha1sum | cut -c1-16"],
                cwd=tmp_abs,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            shell_hash = result.stdout.strip()
            python_hash = hook._cwd_sentinel_hash(tmp_abs)
            self.assertEqual(
                shell_hash,
                python_hash,
                f"Shell pipeline produced {shell_hash!r} but Python produced "
                f"{python_hash!r} for cwd {tmp_abs!r}. If the skill writes a "
                f"sentinel under {shell_hash}.marker the hook will look up "
                f"{python_hash}.marker and never find it.",
            )

    def test_shell_pipeline_matches_python_hash_for_long_path(self) -> None:
        """A long path with multiple segments — guard against any
        length-dependent truncation difference between shell and Python."""
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory(prefix="hash_parity_long_") as tmp:
            nested = os.path.join(tmp, "deep", "nested", "worktree", "subagent", "cwd")
            os.makedirs(nested, exist_ok=True)
            nested_abs = os.path.abspath(nested)
            result = subprocess.run(
                ["bash", "-c", "pwd | sha1sum | cut -c1-16"],
                cwd=nested_abs,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            shell_hash = result.stdout.strip()
            python_hash = hook._cwd_sentinel_hash(nested_abs)
            self.assertEqual(shell_hash, python_hash)

    def test_skill_md_uses_expected_shell_pipeline(self) -> None:
        """Drift guard: the bash snippet in SKILL.md step 0 must contain
        the exact `pwd | sha1sum | cut -c1-16` pipeline.

        If a future edit to the skill changes the algorithm (e.g., switches
        to `realpath | sha256sum | cut -c1-16`, or drops the cut width
        to 8 chars), this test goes red so the change is noticed and the
        Python side updated in lock-step.
        """
        skill_md = self._read_skill_md()
        self.assertIn(
            "pwd | sha1sum | cut -c1-16",
            skill_md,
            "SKILL.md step 0 must use the canonical `pwd | sha1sum | cut -c1-16` "
            "pipeline. If the algorithm has changed, update _cwd_sentinel_hash "
            "in _consultation_sentinel.py to match.",
        )

    def test_skill_md_uses_consulted_directory_structure(self) -> None:
        """Drift guard: SKILL.md must write sentinels under the namespaced
        `.claude/.consulted/ontology-librarian/` directory that the hook
        reads from (per #176)."""
        skill_md = self._read_skill_md()
        self.assertIn(
            ".claude/.consulted/ontology-librarian",
            skill_md,
            "SKILL.md must write sentinels under `.claude/.consulted/ontology-librarian/`. "
            "If the directory has moved, update SENTINEL_PARENT_DIR + _SKILL_KEY in the "
            "hook so the read path matches the write path.",
        )


class TolerantSentinelReadTests(unittest.TestCase):
    """#429 regression — Hook 15 accepts non-canonical-hash markers whose
    body cwd matches. Mirrors `FindAttestingSentinelTests` at the hook
    integration layer to lock in the end-to-end silence path."""

    def setUp(self) -> None:
        self._tmp_root = tempfile.mkdtemp(prefix="librarian_tolerant_", dir=os.path.expanduser("~"))

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmp_root, ignore_errors=True)

    def _make_cwd(self, name: str) -> str:
        cwd = os.path.join(self._tmp_root, name)
        os.makedirs(cwd, exist_ok=True)
        return cwd

    def test_noncanonical_hash_marker_with_matching_body_silent(self) -> None:
        """POS: marker filename uses sha1(cwd) without trailing \\n; body
        records the correct cwd. Hook must accept it — this is the
        live-evidence case from #429 (cedric-0066-dark-mode-tokens)."""
        import hashlib

        cwd = self._make_cwd("noncanonical")
        wrong_hash = hashlib.sha1(cwd.encode()).hexdigest()[:16]
        # Sanity: must differ from canonical to actually exercise the
        # tolerant-read path rather than the canonical-path success path.
        canonical_hash = hook._cwd_sentinel_hash(cwd)
        self.assertNotEqual(wrong_hash, canonical_hash)

        skill_dir = Path(cwd) / hook.SENTINEL_DIR_NAME
        skill_dir.mkdir(parents=True, exist_ok=True)
        marker = skill_dir / f"{wrong_hash}.marker"
        marker.write_text(f"2026-05-14T00:00:00Z {cwd}\n", encoding="utf-8")

        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": os.path.join(cwd, "src/foo.py")},
                "transcript_path": _write_transcript([]),
                "cwd": cwd,
            }
        )
        self.assertIsNone(result, "non-canonical-hash marker with matching body must be silent")

    def test_noncanonical_hash_marker_with_wrong_body_still_advises(self) -> None:
        """NEG: a marker with non-canonical hash AND a body pointing at a
        different cwd must still advise — preserves isolation."""
        cwd = self._make_cwd("strict")
        other_cwd = self._make_cwd("elsewhere")
        skill_dir = Path(cwd) / hook.SENTINEL_DIR_NAME
        skill_dir.mkdir(parents=True, exist_ok=True)
        marker = skill_dir / "deadbeefcafe1234.marker"
        marker.write_text(f"2026-05-14T00:00:00Z {other_cwd}\n", encoding="utf-8")

        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": os.path.join(cwd, "src/foo.py")},
                "transcript_path": _write_transcript([]),
                "cwd": cwd,
            }
        )
        _assert_advisory(self, result)


class MainExitCodeTests(unittest.TestCase):
    """#857: `main()` must ALWAYS exit 0 — the hook never blocks an edit."""

    def _run_hook_main_with(self, input_data: dict) -> tuple[int, str]:
        """Invoke `hook.main()` with `input_data` on stdin.

        Returns (exit_code, stdout_text).
        """
        import io

        original_stdin = sys.stdin
        original_stdout = sys.stdout
        sys.stdin = io.StringIO(json.dumps(input_data))
        captured = io.StringIO()
        sys.stdout = captured
        try:
            try:
                hook.main()
                code = 0
            except SystemExit as e:
                code = int(e.code) if e.code is not None else 0
            return code, captured.getvalue()
        finally:
            sys.stdin = original_stdin
            sys.stdout = original_stdout

    def test_advisory_path_exits_zero_with_system_message(self) -> None:
        """POS: librarian absent -> exit 0 AND a systemMessage is printed."""
        cwd = tempfile.mkdtemp(prefix="adv_cwd_", dir=os.path.expanduser("~"))
        try:
            exit_code, out = self._run_hook_main_with(
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": os.path.join(cwd, "src/foo.py")},
                    "transcript_path": _write_transcript([]),
                    "cwd": cwd,
                }
            )
            self.assertEqual(exit_code, 0, "advisory hook must never block (exit 0)")
            payload = json.loads(out)
            self.assertIn("systemMessage", payload)
            self.assertIn("/ontology-librarian", payload["systemMessage"])
        finally:
            import shutil

            shutil.rmtree(cwd, ignore_errors=True)

    def test_silent_path_exits_zero_no_output(self) -> None:
        """NEG: librarian consulted -> exit 0 and NO stdout payload."""
        cwd = tempfile.mkdtemp(prefix="adv_silent_", dir=os.path.expanduser("~"))
        try:
            exit_code, out = self._run_hook_main_with(
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": os.path.join(cwd, "src/foo.py")},
                    "transcript_path": _write_transcript([_librarian_skill_call()]),
                    "cwd": cwd,
                }
            )
            self.assertEqual(exit_code, 0)
            self.assertEqual(out.strip(), "", "silent path must not print a systemMessage")
        finally:
            import shutil

            shutil.rmtree(cwd, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
