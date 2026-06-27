"""Tests for auto_sync_main — the PostToolUse(Bash) hook that fast-forwards local
main after a successful push/merge to origin/main (main#713).

The fast-forward mechanics live in (and are tested by) ``sync_main``; here we
test the hook's *trigger discrimination* and *gating*: which commands fire it,
that a failed push is ignored, and that only a real move surfaces a message.
``sync_main`` is replaced with a fake so these stay hermetic (no git, no repo).
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

# Hook lives at .claude/hooks/auto_sync_main.py; test at .claude/hooks/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auto_sync_main  # noqa: E402


def _evt(command: str, *, tool="Bash", exit_code=0) -> dict:
    return {
        "tool_name": tool,
        "tool_input": {"command": command},
        "tool_response": {"exit_code": exit_code},
    }


class TargetsMainTest(unittest.TestCase):
    def test_matches_push_to_main_and_pr_merge(self) -> None:
        for cmd in (
            "git push origin main",
            "git push -u origin main",
            "git push origin HEAD:main",
            "gh pr merge 714 --squash",
            "cd /repo && gh pr merge 714 --merge",
        ):
            self.assertTrue(auto_sync_main._targets_main(cmd), cmd)

    def test_ignores_non_main_pushes_and_reads(self) -> None:
        for cmd in (
            "git push origin feature/x",
            "git push origin deployments/phase-5/wave-5",
            "gh pr view 714",
            "git status",
            "ls -la",
        ):
            self.assertFalse(auto_sync_main._targets_main(cmd), cmd)


class CheckTest(unittest.TestCase):
    def setUp(self) -> None:
        # Replace the lazily-imported sync_main module with a fake.
        self._calls: list[object] = []
        self._fake = types.ModuleType("sync_main")
        self._real = sys.modules.get("sync_main")
        sys.modules["sync_main"] = self._fake

        def _restore() -> None:
            if self._real is not None:
                sys.modules["sync_main"] = self._real
            else:
                sys.modules.pop("sync_main", None)

        self.addCleanup(_restore)

    def _set_result(self, status: str, detail: str = "main aaa->bbb (+1)") -> None:
        def fake_sync(root: object) -> object:
            self._calls.append(root)
            return SimpleNamespace(status=status, detail=detail)

        self._fake.sync_main = fake_sync  # type: ignore[attr-defined]

    def test_non_bash_is_ignored(self) -> None:
        self._set_result("fast-forwarded")
        self.assertIsNone(auto_sync_main.check(_evt("git push origin main", tool="Edit")))
        self.assertEqual(self._calls, [])

    def test_non_matching_command_is_ignored(self) -> None:
        self._set_result("fast-forwarded")
        self.assertIsNone(auto_sync_main.check(_evt("git status")))
        self.assertEqual(self._calls, [])

    def test_failed_push_is_ignored(self) -> None:
        self._set_result("fast-forwarded")
        self.assertIsNone(auto_sync_main.check(_evt("git push origin main", exit_code=1)))
        self.assertEqual(self._calls, [], "must not sync when the push itself failed")

    def test_fast_forward_emits_message(self) -> None:
        self._set_result("fast-forwarded", "main aaa->bbb (+2)")
        out = auto_sync_main.check(_evt("gh pr merge 714 --squash"))
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("auto-sync", out["systemMessage"])
        self.assertIn("aaa->bbb", out["systemMessage"])
        self.assertEqual(len(self._calls), 1)

    def test_up_to_date_is_silent(self) -> None:
        self._set_result("up-to-date")
        self.assertIsNone(auto_sync_main.check(_evt("git push origin main")))
        self.assertEqual(len(self._calls), 1, "still consults sync_main, just no message")

    def test_error_surfaces_warning(self) -> None:
        self._set_result("error", "git fetch failed: boom")
        out = auto_sync_main.check(_evt("git push origin main"))
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("could not fast-forward", out["systemMessage"])


if __name__ == "__main__":
    unittest.main()
