"""Tests for check_child_checkouts — the refresh + staleness guard for the
parent's embedded child-repo clones (main#832).

Each test drives REAL git against throwaway temp repos. A fake ``REPO_ROOT``
holds one or more child clones, each backed by its own bare "remote", so the
behind/ahead/dirty classification and the safe fast-forward are exercised
end-to-end. Coverage mirrors the sync_main suite plus the child-specific cases:

  * absent child                       -> absent (skipped, not flagged)
  * on main, clean, current            -> current
  * on main, clean, behind, no refresh -> stale-on-main (flagged, untouched)
  * on main, clean, behind, --refresh  -> fast-forwarded (work pulled forward)
  * parked on a feature branch, behind -> stale-feature-branch (never touched)
  * dirty tree while behind            -> dirty (never discards local work)
  * local commits + behind             -> diverged (never force)
  * local commits only                 -> ahead (never force)
  * render()                            -> FLAGGED block lists the attention set
  * check_all + CLI exit code
"""

from __future__ import annotations

import io
import subprocess
import sys
import unittest
from collections.abc import Sequence
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

# Helper lives at .claude/lib/check_child_checkouts.py; this test is at .claude/lib/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_child_checkouts import (  # noqa: E402
    ChildStatus,
    check_all,
    check_child,
    render,
)
from check_child_checkouts import (  # noqa: E402
    main as cli_main,
)

_IDENT = [
    "-c",
    "user.name=Test",
    "-c",
    "user.email=test@example.com",
    "-c",
    "commit.gpgsign=false",
]


def _git(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *_IDENT, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


def _commit(repo: Path, name: str, content: str, msg: str) -> None:
    (repo / name).write_text(content)
    _git(["add", name], repo)
    _git(["commit", "-m", msg], repo)


class CheckChildCheckoutsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)  # acts as REPO_ROOT
        self._remotes = self.root / "_remotes"
        self._remotes.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_child(self, name: str) -> Path:
        """Create a child clone under REPO_ROOT, on main, in sync with its remote.

        Returns the child working-clone path. A second helper clone ("_<name>")
        is used to advance the remote independently (mirrors sync_main's tests).
        """
        remote = self._remotes / f"{name}.git"
        _git(["init", "--bare", "-b", "main", str(remote)], self._remotes)
        child = self.root / name
        _git(["clone", str(remote), str(child)], self.root)
        _git(["checkout", "-b", "main"], child)
        _commit(child, "README.md", "v1\n", "init")
        _git(["push", "-u", "origin", "main"], child)
        return child

    def _advance_remote(self, name: str) -> None:
        """Push a new commit to a child's remote via a throwaway sibling clone."""
        sib = self.root / f"_adv_{name}"
        _git(["clone", str(self._remotes / f"{name}.git"), str(sib)], self.root)
        _git(["checkout", "main"], sib)
        _commit(sib, "README.md", "v2\n", "remote advance")
        _git(["push", "origin", "main"], sib)

    # ----- absent --------------------------------------------------------

    def test_absent_child_not_flagged(self) -> None:
        res = check_child(self.root, "noorinalabs-does-not-exist")
        self.assertEqual(res.status, "absent")
        self.assertFalse(res.needs_attention)

    # ----- current -------------------------------------------------------

    def test_current_when_on_main_clean_uptodate(self) -> None:
        self._make_child("noorinalabs-deploy")
        res = check_child(self.root, "noorinalabs-deploy")
        self.assertEqual(res.status, "current")
        self.assertEqual(res.behind, 0)
        self.assertEqual(res.ahead, 0)
        self.assertFalse(res.needs_attention)

    # ----- stale-on-main (check) vs fast-forwarded (refresh) -------------

    def test_stale_on_main_flagged_without_refresh(self) -> None:
        child = self._make_child("noorinalabs-isnad-graph")
        self._advance_remote("noorinalabs-isnad-graph")
        res = check_child(self.root, "noorinalabs-isnad-graph", refresh=False)
        self.assertEqual(res.status, "stale-on-main")
        self.assertEqual(res.behind, 1)
        self.assertTrue(res.needs_attention)
        # Untouched: still on v1.
        self.assertEqual((child / "README.md").read_text(), "v1\n")

    def test_refresh_fast_forwards_clean_behind_main(self) -> None:
        child = self._make_child("noorinalabs-isnad-graph")
        self._advance_remote("noorinalabs-isnad-graph")
        res = check_child(self.root, "noorinalabs-isnad-graph", refresh=True)
        self.assertEqual(res.status, "fast-forwarded")
        self.assertFalse(res.needs_attention)
        # The remote commit was pulled forward.
        self.assertEqual((child / "README.md").read_text(), "v2\n")

    # ----- feature branch: flagged, never touched ------------------------

    def test_stale_feature_branch_flagged_and_untouched(self) -> None:
        child = self._make_child("noorinalabs-user-service")
        # Park on an old feature branch, then let main advance on the remote.
        _git(["checkout", "-b", "old/phase-3"], child)
        self._advance_remote("noorinalabs-user-service")
        res = check_child(self.root, "noorinalabs-user-service", refresh=True)
        self.assertEqual(res.status, "stale-feature-branch")
        self.assertEqual(res.branch, "old/phase-3")
        self.assertGreaterEqual(res.behind, 1)
        self.assertTrue(res.needs_attention)
        # Refresh must NOT move a feature branch.
        self.assertEqual((child / "README.md").read_text(), "v1\n")

    # ----- dirty: flagged, never discards work ---------------------------

    def test_dirty_while_behind_flagged_and_preserved(self) -> None:
        child = self._make_child("noorinalabs-design-system")
        self._advance_remote("noorinalabs-design-system")
        (child / "README.md").write_text("uncommitted local edit\n")
        res = check_child(self.root, "noorinalabs-design-system", refresh=True)
        self.assertEqual(res.status, "dirty")
        self.assertIn("README.md", res.dirty)
        self.assertTrue(res.needs_attention)
        # Local edit preserved — refresh refused, nothing discarded.
        self.assertEqual((child / "README.md").read_text(), "uncommitted local edit\n")

    # ----- diverged / ahead ----------------------------------------------

    def test_diverged_when_local_commit_and_behind(self) -> None:
        child = self._make_child("noorinalabs-landing-page")
        self._advance_remote("noorinalabs-landing-page")
        _commit(child, "local.txt", "local\n", "local-only commit")
        res = check_child(self.root, "noorinalabs-landing-page", refresh=True)
        self.assertEqual(res.status, "diverged")
        self.assertGreaterEqual(res.ahead, 1)
        self.assertGreaterEqual(res.behind, 1)
        self.assertTrue(res.needs_attention)

    def test_ahead_when_local_commit_only(self) -> None:
        child = self._make_child("noorinalabs-data-acquisition")
        _commit(child, "local.txt", "local\n", "local-only commit")
        res = check_child(self.root, "noorinalabs-data-acquisition", refresh=True)
        self.assertEqual(res.status, "ahead")
        self.assertGreaterEqual(res.ahead, 1)
        self.assertEqual(res.behind, 0)
        self.assertTrue(res.needs_attention)

    # ----- render + check_all + CLI --------------------------------------

    def test_render_lists_flagged_block(self) -> None:
        results = [
            ChildStatus("noorinalabs-deploy", "current", "main", detail="ok"),
            ChildStatus(
                "noorinalabs-isnad-graph", "stale-on-main", "main", behind=207, detail="stale"
            ),
            ChildStatus("noorinalabs-absent", "absent", detail="no clone"),
        ]
        out = render(results)
        self.assertIn("child-repo checkouts", out)
        self.assertIn("FLAGGED", out)
        self.assertIn("noorinalabs-isnad-graph", out)
        # Absent children are not printed at all.
        self.assertNotIn("noorinalabs-absent", out)
        # A flagged-free render has no FLAGGED block.
        clean = render([ChildStatus("noorinalabs-deploy", "current", "main", detail="ok")])
        self.assertNotIn("FLAGGED", clean)

    def test_render_empty_when_no_children(self) -> None:
        self.assertIn("no child clones", render([ChildStatus("x", "absent")]))

    def test_check_all_inspects_present_children(self) -> None:
        self._make_child("noorinalabs-deploy")
        results = check_all(self.root, children=("noorinalabs-deploy", "noorinalabs-missing"))
        by_repo = {r.repo: r.status for r in results}
        self.assertEqual(by_repo["noorinalabs-deploy"], "current")
        self.assertEqual(by_repo["noorinalabs-missing"], "absent")

    def test_cli_exit_zero_on_flagged_only(self) -> None:
        # A stale-on-main child is a SAFE flagged outcome — CLI must exit 0 so a
        # session-start caller never breaks on a "can't refresh right now" state.
        self._make_child("noorinalabs-deploy")
        self._advance_remote("noorinalabs-deploy")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main([str(self.root)])
        self.assertEqual(rc, 0)
        self.assertIn("stale-on-main", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
