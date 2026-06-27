#!/usr/bin/env python3
"""Tests for no_worktree_self_delete hook.

Covers the W8 hook-authorship-spec requirement: NEGATIVE MATCH coverage.
Each test documents which negative-space case it guards against.

Run: python3 -m pytest .claude/hooks/tests/test_no_worktree_self_delete.py -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import no_worktree_self_delete as hook  # noqa: E402


class _WorktreeFixture:
    """Context manager that builds a fake parent repo + sibling worktree tree.

    Layout:
        <root>/
          parent/           (fake parent repo)
          worktrees/
            wt-a/           (target worktree)
              sub/          (descendant of wt-a)
            wt-b/           (sibling worktree)
          unrelated/        (unrelated path)
    """

    def __init__(self) -> None:
        self.tmpdir: tempfile.TemporaryDirectory | None = None
        self.root: Path = Path()
        self.parent: Path = Path()
        self.wt_a: Path = Path()
        self.wt_a_sub: Path = Path()
        self.wt_b: Path = Path()
        self.unrelated: Path = Path()

    def __enter__(self) -> _WorktreeFixture:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.parent = self.root / "parent"
        self.wt_a = self.root / "worktrees" / "wt-a"
        self.wt_a_sub = self.wt_a / "sub"
        self.wt_b = self.root / "worktrees" / "wt-b"
        self.unrelated = self.root / "unrelated"
        for p in (self.parent, self.wt_a_sub, self.wt_b, self.unrelated):
            p.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, *exc: object) -> None:
        if self.tmpdir is not None:
            self.tmpdir.cleanup()


def _bash(command: str, cwd: str) -> dict:
    """Build a hook input dict for a Bash call."""
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": cwd,
    }


class SelfDeleteBlocks(unittest.TestCase):
    """POS cases — cwd is inside the target worktree → block."""

    def test_cwd_equals_target_blocks(self) -> None:
        """POS: `cwd == target` is the canonical self-delete footgun."""
        with _WorktreeFixture() as f:
            result = hook.check(_bash(f"git worktree remove {f.wt_a}", cwd=str(f.wt_a)))
            assert result is not None
            self.assertEqual(result["decision"], "block")
            self.assertIn("inside", result["reason"])
            self.assertIn("worktree", result["reason"])

    def test_cwd_descendant_of_target_blocks(self) -> None:
        """POS: cwd is a subdir inside the target — still a self-delete."""
        with _WorktreeFixture() as f:
            result = hook.check(_bash(f"git worktree remove {f.wt_a}", cwd=str(f.wt_a_sub)))
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_chained_cd_to_nonexistent_then_remove_still_blocks(self) -> None:
        """POS: `cd /safe && remove <wt>` where `/safe` does NOT exist on disk.

        Post-#535 the hook honors a leading `cd`, but ONLY when the target is
        an absolute directory that exists. A `cd <nonexistent>` is ignored and
        cwd recovery falls back to the stdin cwd (the worktree) — so this is
        still the self-delete and must block. This guards the "don't relax the
        guard on a path that isn't there" invariant.
        """
        with _WorktreeFixture() as f:
            cmd = f"cd /nonexistent-{os.getpid()} && git worktree remove {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.wt_a)))
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_env_prefix_still_blocks(self) -> None:
        """POS: leading `FOO=bar` env assignments must not hide the command."""
        with _WorktreeFixture() as f:
            cmd = f"GIT_TRACE=1 FOO=bar git worktree remove {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.wt_a)))
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_force_flag_still_blocks(self) -> None:
        """POS: `--force` between `remove` and <path> must not hide the path."""
        with _WorktreeFixture() as f:
            cmd = f"git worktree remove --force {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.wt_a)))
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_short_f_flag_still_blocks(self) -> None:
        """POS: `-f` short form, between `remove` and <path>."""
        with _WorktreeFixture() as f:
            cmd = f"git worktree remove -f {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.wt_a)))
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_dash_c_global_flag_still_blocks(self) -> None:
        """POS: `git -c foo=bar worktree remove <path>` must still block."""
        with _WorktreeFixture() as f:
            cmd = f"git -c advice.worktreeAddOrdering=false worktree remove {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.wt_a)))
            assert result is not None
            self.assertEqual(result["decision"], "block")


class SafeInvocationsAllow(unittest.TestCase):
    """NEG cases — worktree remove shapes that must NOT block."""

    def test_sibling_worktree_allowed(self) -> None:
        """NEG: removing wt-a while cwd is in wt-b (sibling) → allow."""
        with _WorktreeFixture() as f:
            result = hook.check(_bash(f"git worktree remove {f.wt_a}", cwd=str(f.wt_b)))
            self.assertIsNone(result)

    def test_unrelated_cwd_allowed(self) -> None:
        """NEG: cwd unrelated to target path → allow."""
        with _WorktreeFixture() as f:
            result = hook.check(_bash(f"git worktree remove {f.wt_a}", cwd=str(f.unrelated)))
            self.assertIsNone(result)

    def test_parent_repo_cwd_allowed(self) -> None:
        """NEG: cwd is the parent managing repo, target is a child worktree."""
        with _WorktreeFixture() as f:
            result = hook.check(_bash(f"git worktree remove {f.wt_a}", cwd=str(f.parent)))
            self.assertIsNone(result)

    def test_prefix_confusion_allowed(self) -> None:
        """NEG: `/foo/wt-a-sibling` should not match target `/foo/wt-a`.

        Guards against the substring-prefix bug Phase 2 Wave 8 surfaced
        (e.g., #123). We use Path.relative_to semantics, not startswith.
        """
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "wt-a"
            sibling = Path(root) / "wt-a-sibling"
            target.mkdir()
            sibling.mkdir()
            result = hook.check(_bash(f"git worktree remove {target}", cwd=str(sibling)))
            self.assertIsNone(result)


class CdRecoverySafetyMatrix(unittest.TestCase):
    """#535 safety matrix — last-cd-wins cwd recovery changes the block/allow
    SAFETY verdict (not just repo identity), so it gets its own dedicated
    test surface. Each case pins a (command, stdin-cwd) → (block|allow) cell.

    The motivating bug: a worktree subagent runs `cd <wt> && git worktree
    remove <wt>` but the harness stdin `cwd` is anchored at the PARENT, so the
    pre-#535 stdin-cwd read saw the parent (safe-looking) and FAILED OPEN on a
    real self-delete (#173 / #534 follow-up). Recovery resolves the post-cd
    cwd and catches it.
    """

    # --- improvement cases: recovery now CATCHES self-deletes the old
    #     stdin-cwd read missed (harness cwd anchored at parent) ---

    def test_cd_into_target_then_remove_blocks_even_when_stdin_cwd_is_parent(
        self,
    ) -> None:
        """POS: `cd <wt_a> && remove <wt_a>` with stdin cwd at the PARENT.

        This is the exact worktree-subagent footgun: the old hook read the
        parent cwd and allowed; recovery resolves to <wt_a> and blocks."""
        with _WorktreeFixture() as f:
            cmd = f"cd {f.wt_a} && git worktree remove {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.parent)))
            assert result is not None, "cd-into-target self-delete must block"
            self.assertEqual(result["decision"], "block")

    def test_cd_into_subdir_then_remove_blocks_from_parent(self) -> None:
        """POS: `cd <wt_a/sub> && remove <wt_a>` with stdin cwd at parent —
        cwd recovers to a descendant of the target → block."""
        with _WorktreeFixture() as f:
            cmd = f"cd {f.wt_a_sub} && git worktree remove {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.parent)))
            assert result is not None
            self.assertEqual(result["decision"], "block")

    # --- correctness cases: recovery now ALLOWS safe removes the old
    #     stdin-cwd read false-blocked (shell cd's OUT before removing) ---

    def test_cd_to_safe_then_remove_allows_even_when_stdin_cwd_is_target(
        self,
    ) -> None:
        """NEG: `cd <safe-existing> && remove <wt_a>` with stdin cwd at
        <wt_a>. The shell moves OUT of <wt_a> first, so this is NOT a
        self-delete — recovery resolves to <safe> and allows. Pre-#535 this
        false-blocked on the stdin cwd."""
        with _WorktreeFixture() as f:
            cmd = f"cd {f.parent} && git worktree remove {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.wt_a)))
            self.assertIsNone(result, "cd-out-then-remove is safe; must allow")

    def test_cd_to_sibling_worktree_then_remove_allows(self) -> None:
        """NEG: `cd <wt_b> && remove <wt_a>` — cd to a sibling worktree, then
        remove the other; safe, allow."""
        with _WorktreeFixture() as f:
            cmd = f"cd {f.wt_b} && git worktree remove {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.wt_a)))
            self.assertIsNone(result)

    # --- last-cd-wins ordering ---

    def test_last_cd_wins_safe_then_unsafe_blocks(self) -> None:
        """POS: `cd <safe> && cd <wt_a> && remove <wt_a>` — the LAST cd lands
        inside the target, so it is a self-delete → block."""
        with _WorktreeFixture() as f:
            cmd = f"cd {f.parent} && cd {f.wt_a} && git worktree remove {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.parent)))
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_last_cd_wins_unsafe_then_safe_allows(self) -> None:
        """NEG: `cd <wt_a> && cd <safe> && remove <wt_a>` — the LAST cd moves
        out of the target, so the remove is safe → allow."""
        with _WorktreeFixture() as f:
            cmd = f"cd {f.wt_a} && cd {f.parent} && git worktree remove {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.wt_a)))
            self.assertIsNone(result)

    # --- recovery must not RELAX the guard on a path that isn't there ---

    def test_cd_to_nonexistent_falls_back_to_stdin_cwd_and_blocks(self) -> None:
        """POS: `cd <nonexistent> && remove <wt_a>` with stdin cwd at <wt_a>.
        The nonexistent cd target is ignored; recovery falls back to the stdin
        cwd (inside the target) → block. Recovery never relaxes on an absent
        directory."""
        with _WorktreeFixture() as f:
            cmd = f"cd /nope-{os.getpid()} && git worktree remove {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.wt_a)))
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_no_cd_bare_remove_uses_stdin_cwd_blocks(self) -> None:
        """POS: bare `git worktree remove <wt_a>` with no cd — stdin cwd
        (inside target) is used directly → block. Confirms the no-cd path is
        unchanged by recovery."""
        with _WorktreeFixture() as f:
            result = hook.check(_bash(f"git worktree remove {f.wt_a}", cwd=str(f.wt_a)))
            assert result is not None
            self.assertEqual(result["decision"], "block")


class NonMatchingCommandsAllow(unittest.TestCase):
    """NEG cases — other commands must not trigger the guard."""

    def test_worktree_list_allowed(self) -> None:
        """NEG: `git worktree list` has no path to remove."""
        with _WorktreeFixture() as f:
            result = hook.check(_bash("git worktree list", cwd=str(f.wt_a)))
            self.assertIsNone(result)

    def test_worktree_add_allowed(self) -> None:
        """NEG: `git worktree add <path>` is creating, not removing."""
        with _WorktreeFixture() as f:
            result = hook.check(_bash(f"git worktree add {f.wt_a}", cwd=str(f.wt_a)))
            self.assertIsNone(result)

    def test_worktree_prune_allowed(self) -> None:
        """NEG: `git worktree prune` takes no path argument."""
        with _WorktreeFixture() as f:
            result = hook.check(_bash("git worktree prune", cwd=str(f.wt_a)))
            self.assertIsNone(result)

    def test_git_commit_allowed(self) -> None:
        """NEG: unrelated git subcommand."""
        with _WorktreeFixture() as f:
            result = hook.check(_bash('git commit -m "foo"', cwd=str(f.wt_a)))
            self.assertIsNone(result)

    def test_ls_allowed(self) -> None:
        """NEG: non-git command."""
        with _WorktreeFixture() as f:
            result = hook.check(_bash("ls -la", cwd=str(f.wt_a)))
            self.assertIsNone(result)

    def test_echo_mentioning_worktree_remove_allowed(self) -> None:
        """NEG: substring mention inside echo/message must not block.

        The segment starts with `echo`, not `git`, so the regex can't match.
        """
        with _WorktreeFixture() as f:
            result = hook.check(
                _bash(
                    f'echo "git worktree remove {f.wt_a}"',
                    cwd=str(f.wt_a),
                )
            )
            self.assertIsNone(result)

    def test_non_bash_tool_allowed(self) -> None:
        """NEG: Edit/Write/etc. are not in the matcher."""
        result = hook.check(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": "/x/y"},
                "cwd": "/x",
            }
        )
        self.assertIsNone(result)


class SymlinkHandling(unittest.TestCase):
    """Symlinked cwd or target must still resolve to the same realpath."""

    def test_symlinked_cwd_blocks(self) -> None:
        """POS: cwd reached via a symlink to the target still blocks.

        Creates `/tmp/root/link` → `/tmp/root/worktrees/wt-a`, cwd=link,
        target=real. realpath normalizes both → same → block.
        """
        with _WorktreeFixture() as f:
            link = f.root / "link-to-wt-a"
            try:
                link.symlink_to(f.wt_a)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unsupported on this platform")
            result = hook.check(_bash(f"git worktree remove {f.wt_a}", cwd=str(link)))
            assert result is not None
            self.assertEqual(result["decision"], "block")


class ChainedSegmentSplitting(unittest.TestCase):
    """Multi-segment commands (&&, ||, ;, |) must each be inspected."""

    def test_second_segment_blocks(self) -> None:
        """POS: `echo foo && git worktree remove <cwd>` blocks on segment 2."""
        with _WorktreeFixture() as f:
            cmd = f"echo starting && git worktree remove {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.wt_a)))
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_semicolon_separator_blocks(self) -> None:
        """POS: `echo foo ; git worktree remove <cwd>` blocks on segment 2."""
        with _WorktreeFixture() as f:
            cmd = f"echo foo ; git worktree remove {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.wt_a)))
            assert result is not None
            self.assertEqual(result["decision"], "block")

    def test_pipe_separator_blocks(self) -> None:
        """POS: pipe separates segments; the git call is its own segment."""
        with _WorktreeFixture() as f:
            cmd = f"echo foo | cat && git worktree remove {f.wt_a}"
            result = hook.check(_bash(cmd, cwd=str(f.wt_a)))
            assert result is not None
            self.assertEqual(result["decision"], "block")


class RemediationMessage(unittest.TestCase):
    """Block message must name a concrete safe cwd or give a generic fallback."""

    def test_reason_contains_cd_guidance(self) -> None:
        """POS: reason string instructs the user to cd somewhere first."""
        with _WorktreeFixture() as f:
            result = hook.check(_bash(f"git worktree remove {f.wt_a}", cwd=str(f.wt_a)))
            assert result is not None
            self.assertIn("cd", result["reason"].lower())
            self.assertIn(str(f.wt_a), result["reason"])


if __name__ == "__main__":
    unittest.main()
