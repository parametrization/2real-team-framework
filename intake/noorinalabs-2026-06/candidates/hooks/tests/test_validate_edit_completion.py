#!/usr/bin/env python3
"""Tests for validate_edit_completion hook (closes #198).

Run: ENVIRONMENT=test python3 -m pytest .claude/hooks/tests/test_validate_edit_completion.py -v

Test classes:
- IsErrorResponseTests   — _is_error_response covers all observed shapes
- PostToolUseTests       — error → sentinel append; no error → no sentinel
- PreToolUseSamePathTests — Edit/Write/NotebookEdit on errored path blocks
- PreToolUseSendMessageTests — SendMessage blocks while sentinel non-empty
- PreToolUseBashTests    — git commit / gh pr comment / gh issue comment block
- AckTranscriptTests     — Read / Bash-verb / explicit-marker prune sentinel
- TtlAndStaleTests       — entries past TTL are dropped on read
- BashAcksPathTests      — _bash_acks_path positive/negative coverage
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_edit_completion as hook  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stale_iso(seconds_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


class _SentinelHarness(unittest.TestCase):
    """Shared setup: redirect SENTINEL_DIR to a tmpdir per test."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self._patcher = mock.patch.object(
            hook, "SENTINEL_DIR", self.tmp_path / ".claude" / ".edit-error-sentinel"
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def _input(self, **kwargs) -> dict:
        d = {"session_id": "test-session"}
        d.update(kwargs)
        return d

    def _sentinel_file(self, session_id: str = "test-session") -> Path:
        return hook.SENTINEL_DIR / f"{session_id}.jsonl"


class IsErrorResponseTests(unittest.TestCase):
    """Coverage for the three observed tool_response shapes."""

    def test_top_level_is_error_true(self):
        self.assertTrue(hook._is_error_response({"is_error": True}))

    def test_top_level_is_error_false(self):
        self.assertFalse(hook._is_error_response({"is_error": False}))

    def test_content_list_with_is_error(self):
        self.assertTrue(
            hook._is_error_response(
                {
                    "content": [
                        {"type": "text", "text": "ok"},
                        {"is_error": True, "content": "Error: ..."},
                    ]
                }
            )
        )

    def test_content_list_without_is_error(self):
        self.assertFalse(hook._is_error_response({"content": [{"type": "text", "text": "ok"}]}))

    def test_bash_exit_code_nonzero(self):
        self.assertTrue(hook._is_error_response({"exit_code": 2}))

    def test_bash_exit_code_zero(self):
        self.assertFalse(hook._is_error_response({"exit_code": 0}))

    def test_unrecognized_shape_returns_false(self):
        self.assertFalse(hook._is_error_response("just a string"))
        self.assertFalse(hook._is_error_response(None))
        self.assertFalse(hook._is_error_response([]))


class PostToolUseTests(_SentinelHarness):
    """Edit/Write/NotebookEdit error → sentinel append; no error → no sentinel."""

    def test_edit_error_creates_sentinel_entry(self):
        inp = self._input(
            hook_event_name="PostToolUse",
            tool_name="Edit",
            tool_input={"file_path": "/tmp/X.py"},
            tool_response={
                "is_error": True,
                "content": [{"is_error": True, "content": "Error: File has not been read yet"}],
            },
        )
        hook._post_tool_use(inp)
        sf = self._sentinel_file()
        self.assertTrue(sf.is_file())
        lines = sf.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["path"], str(Path("/tmp/X.py").resolve()))
        self.assertEqual(entry["tool"], "Edit")
        self.assertIn("File has not been read", entry["error"])

    def test_edit_success_does_not_create_sentinel(self):
        inp = self._input(
            hook_event_name="PostToolUse",
            tool_name="Edit",
            tool_input={"file_path": "/tmp/X.py"},
            tool_response={"is_error": False},
        )
        hook._post_tool_use(inp)
        self.assertFalse(self._sentinel_file().exists())

    def test_non_edit_tool_skipped(self):
        inp = self._input(
            hook_event_name="PostToolUse",
            tool_name="Read",
            tool_input={"file_path": "/tmp/X.py"},
            tool_response={"is_error": True},
        )
        hook._post_tool_use(inp)
        self.assertFalse(self._sentinel_file().exists())

    def test_write_error_creates_sentinel(self):
        inp = self._input(
            hook_event_name="PostToolUse",
            tool_name="Write",
            tool_input={"file_path": "/tmp/Y.py"},
            tool_response={"is_error": True},
        )
        hook._post_tool_use(inp)
        self.assertTrue(self._sentinel_file().is_file())

    def test_notebook_edit_uses_notebook_path(self):
        inp = self._input(
            hook_event_name="PostToolUse",
            tool_name="NotebookEdit",
            tool_input={"notebook_path": "/tmp/Z.ipynb"},
            tool_response={"is_error": True},
        )
        hook._post_tool_use(inp)
        sf = self._sentinel_file()
        self.assertTrue(sf.is_file())
        entry = json.loads(sf.read_text().strip())
        self.assertEqual(entry["path"], str(Path("/tmp/Z.ipynb").resolve()))


class PreToolUseSamePathTests(_SentinelHarness):
    """Edit on the errored path BLOCKS until acknowledged."""

    def _seed_sentinel(self, path: str = "/tmp/X.py") -> str:
        abs_path = str(Path(path).resolve())
        sf = self._sentinel_file()
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(
            json.dumps(
                {
                    "path": abs_path,
                    "tool": "Edit",
                    "error": "...",
                    "ts": _now_iso(),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return abs_path

    def test_edit_same_path_blocks(self):
        abs_path = self._seed_sentinel()
        inp = self._input(
            hook_event_name="PreToolUse",
            tool_name="Edit",
            tool_input={"file_path": abs_path},
        )
        result = hook._pre_tool_use_blocks(inp)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn(abs_path, result["reason"])

    def test_edit_different_path_allows(self):
        self._seed_sentinel("/tmp/X.py")
        inp = self._input(
            hook_event_name="PreToolUse",
            tool_name="Edit",
            tool_input={"file_path": "/tmp/UNRELATED.py"},
        )
        self.assertIsNone(hook._pre_tool_use_blocks(inp))

    def test_empty_sentinel_allows_anything(self):
        # No sentinel file at all
        inp = self._input(
            hook_event_name="PreToolUse",
            tool_name="Edit",
            tool_input={"file_path": "/tmp/X.py"},
        )
        self.assertIsNone(hook._pre_tool_use_blocks(inp))


class PreToolUseSendMessageTests(_SentinelHarness):
    def test_sendmessage_with_unhandled_error_blocks(self):
        sf = self._sentinel_file()
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(
            json.dumps(
                {
                    "path": "/tmp/X.py",
                    "tool": "Edit",
                    "error": "...",
                    "ts": _now_iso(),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        inp = self._input(
            hook_event_name="PreToolUse",
            tool_name="SendMessage",
            tool_input={"to": "team-lead", "message": "PR #100 is at v3"},
        )
        result = hook._pre_tool_use_blocks(inp)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_sendmessage_with_empty_sentinel_allows(self):
        inp = self._input(
            hook_event_name="PreToolUse",
            tool_name="SendMessage",
            tool_input={"to": "team-lead", "message": "ok"},
        )
        self.assertIsNone(hook._pre_tool_use_blocks(inp))


class PreToolUseBashTests(_SentinelHarness):
    def _seed(self) -> None:
        sf = self._sentinel_file()
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(
            json.dumps(
                {
                    "path": "/tmp/X.py",
                    "tool": "Edit",
                    "error": "...",
                    "ts": _now_iso(),
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def _bash(self, command: str) -> dict:
        return self._input(
            hook_event_name="PreToolUse",
            tool_name="Bash",
            tool_input={"command": command},
        )

    def test_git_commit_blocks(self):
        self._seed()
        result = hook._pre_tool_use_blocks(self._bash('git -c user.name="A" commit -m x'))
        self.assertIsNotNone(result)

    def test_git_commit_chained_blocks(self):
        self._seed()
        result = hook._pre_tool_use_blocks(self._bash("cd /tmp && git commit -m x"))
        self.assertIsNotNone(result)

    def test_gh_pr_comment_blocks(self):
        self._seed()
        result = hook._pre_tool_use_blocks(self._bash("gh pr comment 100 --body-file /tmp/body.md"))
        self.assertIsNotNone(result)

    def test_gh_issue_comment_blocks(self):
        self._seed()
        result = hook._pre_tool_use_blocks(self._bash("gh issue comment 100 --body 'note'"))
        self.assertIsNotNone(result)

    def test_unrelated_bash_allows(self):
        """Bash that's NOT a state-sensitive action allows even with sentinel."""
        self._seed()
        self.assertIsNone(hook._pre_tool_use_blocks(self._bash("ls -la /tmp")))
        self.assertIsNone(hook._pre_tool_use_blocks(self._bash("python3 script.py")))

    def test_negative_match_git_log(self):
        """`git log` is not a state-sensitive write — allows."""
        self._seed()
        self.assertIsNone(hook._pre_tool_use_blocks(self._bash("git log --oneline")))

    def test_negative_match_gh_pr_view(self):
        """`gh pr view` is read-only — allows."""
        self._seed()
        self.assertIsNone(hook._pre_tool_use_blocks(self._bash("gh pr view 100")))


class AckTranscriptTests(_SentinelHarness):
    """Acknowledgment via Read / Bash-verb / explicit-marker prunes sentinel."""

    def _seed(self, path: str = "/tmp/X.py") -> str:
        abs_path = str(Path(path).resolve())
        sf = self._sentinel_file()
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(
            json.dumps(
                {
                    "path": abs_path,
                    "tool": "Edit",
                    "error": "...",
                    "ts": _now_iso(),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return abs_path

    def _write_transcript(self, blocks: list[dict]) -> str:
        """Write a JSONL transcript with the given content blocks. Returns path."""
        tpath = self.tmp_path / "transcript.jsonl"
        with tpath.open("w", encoding="utf-8") as f:
            for block in blocks:
                f.write(
                    json.dumps(
                        {
                            "type": "assistant",
                            "message": {"role": "assistant", "content": [block]},
                        }
                    )
                    + "\n"
                )
        return str(tpath)

    def test_read_acks(self):
        abs_path = self._seed()
        tpath = self._write_transcript(
            [{"type": "tool_use", "name": "Read", "input": {"file_path": abs_path}}]
        )
        inp = self._input(
            hook_event_name="PreToolUse",
            tool_name="Edit",
            tool_input={"file_path": abs_path},
            transcript_path=tpath,
        )
        self.assertIsNone(hook._pre_tool_use_blocks(inp))
        # Sentinel pruned to empty.
        self.assertFalse(
            self._sentinel_file().exists() and self._sentinel_file().read_text().strip()
        )

    def test_bash_cat_acks(self):
        abs_path = self._seed()
        tpath = self._write_transcript(
            [{"type": "tool_use", "name": "Bash", "input": {"command": f"cat {abs_path}"}}]
        )
        inp = self._input(
            hook_event_name="PreToolUse",
            tool_name="Edit",
            tool_input={"file_path": abs_path},
            transcript_path=tpath,
        )
        self.assertIsNone(hook._pre_tool_use_blocks(inp))

    def test_bash_grep_acks(self):
        abs_path = self._seed()
        tpath = self._write_transcript(
            [{"type": "tool_use", "name": "Bash", "input": {"command": f"grep foo {abs_path}"}}]
        )
        inp = self._input(
            hook_event_name="PreToolUse",
            tool_name="Edit",
            tool_input={"file_path": abs_path},
            transcript_path=tpath,
        )
        self.assertIsNone(hook._pre_tool_use_blocks(inp))

    def test_bash_unrelated_does_not_ack(self):
        """A Bash without an ack-verb on the path should NOT count as ack."""
        abs_path = self._seed()
        tpath = self._write_transcript(
            [{"type": "tool_use", "name": "Bash", "input": {"command": f"echo {abs_path}"}}]
        )
        inp = self._input(
            hook_event_name="PreToolUse",
            tool_name="Edit",
            tool_input={"file_path": abs_path},
            transcript_path=tpath,
        )
        # echo is not in _ACK_BASH_VERBS — should still block.
        self.assertIsNotNone(hook._pre_tool_use_blocks(inp))

    def test_explicit_marker_in_text_acks(self):
        abs_path = self._seed()
        tpath = self._write_transcript(
            [
                {
                    "type": "text",
                    "text": (
                        f"Re-checked. edit-error acknowledged for {abs_path}; reverting v4 -> v3."
                    ),
                }
            ]
        )
        inp = self._input(
            hook_event_name="PreToolUse",
            tool_name="Edit",
            tool_input={"file_path": abs_path},
            transcript_path=tpath,
        )
        self.assertIsNone(hook._pre_tool_use_blocks(inp))

    def test_marker_without_path_does_not_ack(self):
        abs_path = self._seed()
        tpath = self._write_transcript(
            [{"type": "text", "text": "edit-error acknowledged in some other context"}]
        )
        inp = self._input(
            hook_event_name="PreToolUse",
            tool_name="Edit",
            tool_input={"file_path": abs_path},
            transcript_path=tpath,
        )
        # Marker present but path absent → not an ack for this entry.
        self.assertIsNotNone(hook._pre_tool_use_blocks(inp))

    def test_path_without_marker_does_not_ack(self):
        abs_path = self._seed()
        tpath = self._write_transcript(
            [{"type": "text", "text": f"Just a passing reference to {abs_path}."}]
        )
        inp = self._input(
            hook_event_name="PreToolUse",
            tool_name="Edit",
            tool_input={"file_path": abs_path},
            transcript_path=tpath,
        )
        self.assertIsNotNone(hook._pre_tool_use_blocks(inp))


class TtlAndStaleTests(_SentinelHarness):
    def test_stale_entry_dropped_on_read(self):
        sf = self._sentinel_file()
        sf.parent.mkdir(parents=True, exist_ok=True)
        # Mix: one fresh, one stale beyond TTL.
        fresh = {"path": "/tmp/A.py", "tool": "Edit", "error": "x", "ts": _now_iso()}
        stale = {
            "path": "/tmp/B.py",
            "tool": "Edit",
            "error": "x",
            "ts": _stale_iso(hook.SENTINEL_TTL_SECONDS + 10),
        }
        sf.write_text(
            json.dumps(fresh) + "\n" + json.dumps(stale) + "\n",
            encoding="utf-8",
        )
        entries = hook._read_sentinel(sf)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["path"], "/tmp/A.py")

    def test_malformed_line_skipped(self):
        sf = self._sentinel_file()
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(
            "not valid json\n"
            + json.dumps({"path": "/tmp/A.py", "tool": "Edit", "error": "x", "ts": _now_iso()})
            + "\n",
            encoding="utf-8",
        )
        entries = hook._read_sentinel(sf)
        self.assertEqual(len(entries), 1)


class BashAcksPathTests(unittest.TestCase):
    """_bash_acks_path positive + negative."""

    def test_cat_acks(self):
        self.assertTrue(hook._bash_acks_path("cat /tmp/x.py", "/tmp/x.py"))

    def test_head_acks(self):
        self.assertTrue(hook._bash_acks_path("head -10 /tmp/x.py", "/tmp/x.py"))

    def test_grep_acks(self):
        self.assertTrue(hook._bash_acks_path("grep foo /tmp/x.py", "/tmp/x.py"))

    def test_ls_la_acks(self):
        self.assertTrue(hook._bash_acks_path("ls -la /tmp/x.py", "/tmp/x.py"))

    def test_path_alone_does_not_ack(self):
        """Path present but no ack-verb → not an ack."""
        self.assertFalse(hook._bash_acks_path("rm /tmp/x.py", "/tmp/x.py"))

    def test_verb_alone_does_not_ack(self):
        """Verb present but path missing → not an ack."""
        self.assertFalse(hook._bash_acks_path("cat /etc/hosts", "/tmp/x.py"))


if __name__ == "__main__":
    unittest.main()
