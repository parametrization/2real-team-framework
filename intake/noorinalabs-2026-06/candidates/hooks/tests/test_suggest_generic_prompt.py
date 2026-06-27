"""Tests for suggest_generic_prompt — the PostToolUse(Edit/Write) hook demoted
from a per-edit `[Generic Prompt Suggestion]` systemMessage to a SILENT
state-tracking feeder for the wave-wrapup genericize checkpoint (main#716).

The behavioural contract these tests pin:
  AC2 — the hook NEVER emits a systemMessage (check() returns None always;
        main() prints nothing). The old advisory string must be gone.
  feeder — on a tracked .claude/ Edit/Write the hook delegates to
        generic_prompt_tracker.record_candidate(file_path); on non-applicable
        events it does not.
  robustness — a tracker failure is swallowed (advisory feeder must never
        crash PostToolUse dispatch).
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

# Hook lives at .claude/hooks/suggest_generic_prompt.py; test at .claude/hooks/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# The hook imports generic_prompt_tracker from ../lib; make it importable here too.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "lib"))

import suggest_generic_prompt as hook  # noqa: E402


def _evt(file_path: str, *, tool: str = "Edit") -> dict:
    return {"tool_name": tool, "tool_input": {"file_path": file_path}}


class ReturnsNoneAlwaysTest(unittest.TestCase):
    def test_tracked_edit_returns_none(self) -> None:
        with mock.patch("generic_prompt_tracker.record_candidate") as rc:
            self.assertIsNone(hook.check(_evt("/r/.claude/hooks/foo.py")))
            rc.assert_called_once_with("/r/.claude/hooks/foo.py")

    def test_write_also_feeds_tracker(self) -> None:
        with mock.patch("generic_prompt_tracker.record_candidate") as rc:
            self.assertIsNone(hook.check(_evt("/r/.claude/skills/x/SKILL.md", tool="Write")))
            rc.assert_called_once()

    def test_no_systemmessage_key_ever(self) -> None:
        # The whole point of main#716: no dict with a systemMessage is returned.
        with mock.patch("generic_prompt_tracker.record_candidate"):
            result = hook.check(_evt("/r/.claude/team/charter/agents.md"))
        self.assertIsNone(result)


class NonApplicableTest(unittest.TestCase):
    def test_non_edit_tool_skipped(self) -> None:
        with mock.patch("generic_prompt_tracker.record_candidate") as rc:
            self.assertIsNone(hook.check(_evt("/r/.claude/hooks/foo.py", tool="Bash")))
            rc.assert_not_called()

    def test_missing_file_path_skipped(self) -> None:
        with mock.patch("generic_prompt_tracker.record_candidate") as rc:
            self.assertIsNone(hook.check({"tool_name": "Edit", "tool_input": {}}))
            rc.assert_not_called()


class RobustnessTest(unittest.TestCase):
    def test_tracker_exception_is_swallowed(self) -> None:
        with mock.patch(
            "generic_prompt_tracker.record_candidate", side_effect=RuntimeError("boom")
        ):
            # Must not raise; advisory feeder never breaks dispatch.
            self.assertIsNone(hook.check(_evt("/r/.claude/hooks/foo.py")))


class MainEmitsNothingTest(unittest.TestCase):
    def test_main_prints_no_systemmessage(self) -> None:
        payload = '{"tool_name": "Edit", "tool_input": {"file_path": "/r/.claude/hooks/foo.py"}}'
        buf = io.StringIO()
        with (
            mock.patch("generic_prompt_tracker.record_candidate"),
            mock.patch.object(sys, "stdin", io.StringIO(payload)),
            redirect_stdout(buf),
            self.assertRaises(SystemExit) as cm,
        ):
            hook.main()
        self.assertEqual(cm.exception.code, 0)
        self.assertEqual(buf.getvalue().strip(), "")


if __name__ == "__main__":
    unittest.main()
