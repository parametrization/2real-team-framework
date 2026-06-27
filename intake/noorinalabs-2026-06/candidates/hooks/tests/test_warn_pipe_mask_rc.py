#!/usr/bin/env python3
"""Tests for `warn_pipe_mask_rc.check()` — PostToolUse rc-masking pipe flag (#838).

Covers the two acceptance axes:
  - FALSE-POSITIVE GUARDS: a no-pipe push, the `; echo rc=$?` fix, `&&`, a
    push as the pipeline's LAST stage, pipefail-guarded pipes, non-push pipes,
    and the phrase in heredoc/quoted/data position must ALL stay silent. The
    no-pipe `git push origin <branch>` case is load-bearing: it is what every
    wave-17 agent runs, and a false positive there would noise the whole wave.
  - DETECTION + TIERING: a push/merge in a non-final pipeline stage is flagged,
    escalating TIER 2 (footgun shape only) → TIER 1 (confirmed masked failure)
    when the captured output carries a failure signal or a non-zero rc.

Both the bashlex AST path and the shlex/regex fallback (bashlex monkeypatched
off) are exercised.

Run from the repo root:
    python3 -m pytest .claude/hooks/tests/test_warn_pipe_mask_rc.py -v
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

import warn_pipe_mask_rc as wpm  # noqa: E402


def _event(command: str, stdout: str = "", stderr: str = "", exit_code: int = 0) -> dict:
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"stdout": stdout, "stderr": stderr, "exit_code": exit_code},
    }


class NoMatchCases(unittest.TestCase):
    """Commands that must NOT be flagged (false-positive guards)."""

    def test_plain_push_no_pipe(self):
        # THE common wave case — must stay silent.
        self.assertIsNone(wpm.check(_event("git push origin N.Kavtaradze/0838-x")))

    def test_push_with_echo_rc_fix(self):
        # The recommended fix uses `;` not a pipe — never flag it.
        self.assertIsNone(wpm.check(_event("git push origin main ; echo rc=$?")))

    def test_push_with_and_chain(self):
        self.assertIsNone(wpm.check(_event("git push origin main && echo done")))

    def test_push_as_last_pipeline_stage(self):
        # git push is the LAST stage; its rc IS the pipeline rc — not masked.
        self.assertIsNone(wpm.check(_event("cat refs.txt | git push origin main")))

    def test_non_push_pipe(self):
        self.assertIsNone(wpm.check(_event("git log --oneline | head -5")))

    def test_gh_pr_view_pipe(self):
        self.assertIsNone(wpm.check(_event("gh pr view 42 | cat")))

    def test_pipefail_guarded(self):
        # pipefail propagates the failing rc — not masked.
        self.assertIsNone(wpm.check(_event("set -o pipefail; git push origin main | tail -3")))

    def test_phrase_in_quoted_string(self):
        self.assertIsNone(wpm.check(_event('echo "git push origin main | tail"')))

    def test_phrase_in_heredoc_body(self):
        cmd = "git commit -F - <<'EOF'\ngit push origin main | tail\nEOF"
        self.assertIsNone(wpm.check(_event(cmd)))

    def test_non_bash_tool(self):
        evt = _event("git push origin main | tail")
        evt["tool_name"] = "Edit"
        self.assertIsNone(wpm.check(evt))

    def test_empty_command(self):
        self.assertIsNone(wpm.check(_event("")))


class DetectionAndTiering(unittest.TestCase):
    """Commands that must be flagged, with the right severity tier."""

    def test_push_tail_footgun_shape(self):
        # Masking shape present, clean output → TIER 2 (footgun nudge).
        res = wpm.check(_event("git push origin main | tail -3", stdout="Everything up-to-date"))
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "footgun_shape")
        self.assertIn("rc-masking pipe", res["systemMessage"])
        self.assertIn("git push", res["labels"])

    def test_push_tail_masked_rejection(self):
        # Masking shape + a real rejection on output, rc=0 → TIER 1 (loud).
        out = "To github.com:org/repo.git\n ! [rejected]   main -> main (non-fast-forward)"
        res = wpm.check(_event("git push origin main 2>&1 | tail -3", stdout=out))
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "masked_failure")
        self.assertIn("MASKED PUSH/MERGE FAILURE", res["systemMessage"])

    def test_push_nonzero_exit_is_tier1(self):
        res = wpm.check(_event("git push origin main | tail", exit_code=1))
        self.assertEqual(res["action"], "masked_failure")

    def test_gh_pr_merge_head_footgun(self):
        res = wpm.check(_event("gh pr merge 123 --merge | head", stdout="merged"))
        self.assertEqual(res["action"], "footgun_shape")
        self.assertIn("gh pr merge", res["labels"])

    def test_gh_pr_merge_not_mergeable_tier1(self):
        res = wpm.check(
            _event("gh pr merge 123 --merge | cat", stderr="Pull request is not mergeable")
        )
        self.assertEqual(res["action"], "masked_failure")

    def test_push_pipe_no_space(self):
        # `git push|tail` (no spaces around the pipe) must still be caught.
        res = wpm.check(_event("git push origin main|tail"))
        self.assertIsNotNone(res)
        self.assertIn("git push", res["labels"])

    def test_push_pipe_tee(self):
        # tee also swallows the rc — the masker name is irrelevant.
        res = wpm.check(_event("git push origin main 2>&1 | tee push.log"))
        self.assertIsNotNone(res)

    def test_push_with_git_global_opts(self):
        res = wpm.check(_event("git -c user.name=x push origin main | tail"))
        self.assertIsNotNone(res)
        self.assertIn("git push", res["labels"])

    def test_failure_marker_in_stderr(self):
        res = wpm.check(
            _event("git push origin main | tail", stderr="error: failed to push some refs")
        )
        self.assertEqual(res["action"], "masked_failure")

    def test_label_dedup(self):
        # Two masked pushes in one command → label appears once.
        res = wpm.check(_event("git push origin a | tail; git push origin b | head"))
        self.assertEqual(res["labels"].count("git push"), 1)


class FallbackPath(unittest.TestCase):
    """Same detection must hold when bashlex is unavailable (degraded mode)."""

    def setUp(self):
        self._saved = wpm._BASHLEX_AVAILABLE
        wpm._BASHLEX_AVAILABLE = False

    def tearDown(self):
        wpm._BASHLEX_AVAILABLE = self._saved

    def test_fallback_detects_masked_push(self):
        res = wpm.check(_event("git push origin main | tail"))
        self.assertIsNotNone(res)
        self.assertIn("git push", res["labels"])

    def test_fallback_detects_no_space(self):
        res = wpm.check(_event("git push origin main|tail"))
        self.assertIsNotNone(res)

    def test_fallback_silent_on_plain_push(self):
        self.assertIsNone(wpm.check(_event("git push origin main")))

    def test_fallback_silent_on_push_last_stage(self):
        self.assertIsNone(wpm.check(_event("cat x | git push origin main")))

    def test_fallback_silent_on_pipefail(self):
        self.assertIsNone(wpm.check(_event("set -o pipefail; git push origin main | tail")))

    def test_fallback_silent_on_and_chain(self):
        self.assertIsNone(wpm.check(_event("git push origin main && echo ok")))

    def test_fallback_detects_gh_pr_merge(self):
        res = wpm.check(_event("gh pr merge 7 --squash | head"))
        self.assertIsNotNone(res)
        self.assertIn("gh pr merge", res["labels"])


class MainEntrypoint(unittest.TestCase):
    """The standalone `main()` must exit 0 (CI smoke test) and emit JSON."""

    def _run(self, payload: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(_HOOKS_DIR / "warn_pipe_mask_rc.py")],
            input=payload,
            capture_output=True,
            text=True,
        )

    def test_empty_stdin_exits_zero(self):
        proc = self._run("")
        self.assertEqual(proc.returncode, 0)

    def test_masked_emits_systemmessage(self):
        payload = json.dumps(_event("git push origin main | tail"))
        proc = self._run(payload)
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertIn("systemMessage", out)

    def test_clean_emits_nothing(self):
        payload = json.dumps(_event("git push origin main"))
        proc = self._run(payload)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
