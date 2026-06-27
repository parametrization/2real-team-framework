#!/usr/bin/env python3
"""Tests for block_shutdown_without_retro — covers #189 (prose false-positive).

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_block_shutdown_without_retro.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import block_shutdown_without_retro as hook  # noqa: E402


def _input(message, to: str = "team-lead") -> dict:
    return {
        "tool_name": "SendMessage",
        "tool_input": {"to": to, "message": message},
    }


class PositiveMatchTests(unittest.TestCase):
    """Structured shutdown_request without retro MUST block."""

    def test_dict_form_blocks_when_no_retro(self):
        with mock.patch.object(hook, "has_retro_for_today", return_value=False):
            result = hook.check(_input({"type": "shutdown_request", "reason": "done"}))
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_json_string_form_blocks_when_no_retro(self):
        with mock.patch.object(hook, "has_retro_for_today", return_value=False):
            result = hook.check(_input('{"type": "shutdown_request", "reason": "done"}'))
        self.assertIsNotNone(result)


class NegativeMatchTests(unittest.TestCase):
    """#189: prose mentioning the phrase must NOT trigger."""

    def test_prose_with_substring_does_not_block(self):
        """The exact #189 false-positive: 'standing down' + 'Acknowledge'."""
        with mock.patch.object(hook, "has_retro_for_today", return_value=False):
            result = hook.check(
                _input("Standing down. Acknowledged the shutdown_request from team-lead.")
            )
        self.assertIsNone(result)

    def test_subagent_task_complete_does_not_block(self):
        """Subagent stand-down acknowledgment must not be caught."""
        with mock.patch.object(hook, "has_retro_for_today", return_value=False):
            result = hook.check(
                _input("PR #555 is open with reviewer comments posted. Going idle.")
            )
        self.assertIsNone(result)

    def test_unrelated_message(self):
        with mock.patch.object(hook, "has_retro_for_today", return_value=False):
            result = hook.check(_input("Hi, please review PR #100."))
        self.assertIsNone(result)

    def test_emergency_shutdown_allowed(self):
        with mock.patch.object(hook, "has_retro_for_today", return_value=False):
            result = hook.check(_input({"type": "shutdown_request", "reason": "error"}))
        self.assertIsNone(result)

    def test_crash_shutdown_allowed(self):
        with mock.patch.object(hook, "has_retro_for_today", return_value=False):
            result = hook.check(_input({"type": "shutdown_request", "reason": "crash"}))
        self.assertIsNone(result)

    def test_utility_agent_explorer_allowed(self):
        with mock.patch.object(hook, "has_retro_for_today", return_value=False):
            result = hook.check(_input({"type": "shutdown_request"}, to="explorer-agent"))
        self.assertIsNone(result)

    def test_with_retro_allowed(self):
        with mock.patch.object(hook, "has_retro_for_today", return_value=True):
            result = hook.check(_input({"type": "shutdown_request"}))
        self.assertIsNone(result)

    def test_non_sendmessage_tool(self):
        result = hook.check(
            {
                "tool_name": "Bash",
                "tool_input": {"command": '{"type": "shutdown_request"}'},
            }
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
