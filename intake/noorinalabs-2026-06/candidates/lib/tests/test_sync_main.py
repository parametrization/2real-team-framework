"""Tests for sync_main — the deterministic, side-effect-guarded fast-forward of
the local default branch to its remote (main#713).

Each test drives REAL git against throwaway temp repos (a bare "remote" plus
working clones) so the plumbing is exercised end-to-end. Coverage:

  * behind + clean              -> fast-forwarded
  * already current             -> up-to-date (no-op)
  * not on the target branch    -> skipped-not-on-branch
  * local ahead only            -> refused-ahead (never force-pushes/rewrites)
  * local + remote diverged     -> refused-diverged
  * real tracked local change   -> refused-dirty (never discards work) + the
                                   loud STALE-BASE detail (behind-count + paths)
  * only generated-allowlist     -> stashed around ff and restored (every entry,
                                   incl. ontology/checksums.json per main#822)
  * conflicting generated pop    -> ff still lands, stash left for recovery
  * CLI refused-dirty banner    -> multi-line, not a single quiet line
  * _parse_dirty                -> excludes untracked/ignored, follows renames
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

# Helper lives at .claude/lib/sync_main.py; this test is at .claude/lib/tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sync_main import (  # noqa: E402
    GENERATED_ALLOWLIST,
    _parse_dirty,
    sync_main,
)
from sync_main import (
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


class SyncMainTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        base = Path(self._tmp.name)
        self.remote = base / "remote.git"
        self.local = base / "local"
        self.other = base / "other"
        _git(["init", "--bare", "-b", "main", str(self.remote)], base)

        _git(["clone", str(self.remote), str(self.local)], base)
        _git(["checkout", "-b", "main"], self.local)
        _commit(self.local, "README.md", "v1\n", "init")
        _git(["push", "-u", "origin", "main"], self.local)

        _git(["clone", str(self.remote), str(self.other)], base)
        _git(["checkout", "main"], self.other)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _advance_remote(self) -> None:
        """Push a new commit to the remote via the 'other' clone."""
        _commit(self.other, "README.md", "v2\n", "remote advance")
        _git(["push", "origin", "main"], self.other)

    # ----- happy paths --------------------------------------------------

    def test_fast_forward_when_behind_and_clean(self) -> None:
        self._advance_remote()
        before = _git(["rev-parse", "HEAD"], self.local).stdout.strip()
        res = sync_main(self.local)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "fast-forwarded")
        self.assertEqual(res.behind, 1)
        self.assertEqual(res.ahead, 0)
        after = _git(["rev-parse", "HEAD"], self.local).stdout.strip()
        self.assertNotEqual(before, after)
        self.assertEqual((self.local / "README.md").read_text(), "v2\n")

    def test_up_to_date_noop(self) -> None:
        res = sync_main(self.local)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "up-to-date")
        self.assertEqual(res.behind, 0)

    def test_skipped_when_not_on_branch(self) -> None:
        _git(["checkout", "-b", "feature/x"], self.local)
        self._advance_remote()
        res = sync_main(self.local)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "skipped-not-on-branch")
        # Did NOT move the feature branch.
        self.assertEqual((self.local / "README.md").read_text(), "v1\n")

    # ----- refusals -----------------------------------------------------

    def test_refused_when_ahead(self) -> None:
        _commit(self.local, "local.txt", "local\n", "local-only commit")
        res = sync_main(self.local)
        self.assertTrue(res.ok)  # refusal is a safe outcome
        self.assertEqual(res.status, "refused-ahead")
        self.assertGreaterEqual(res.ahead, 1)

    def test_refused_when_diverged(self) -> None:
        self._advance_remote()
        _commit(self.local, "local.txt", "local\n", "local-only commit")
        res = sync_main(self.local)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "refused-diverged")
        self.assertGreaterEqual(res.ahead, 1)
        self.assertGreaterEqual(res.behind, 1)

    def test_refused_when_real_dirty(self) -> None:
        self._advance_remote()
        (self.local / "README.md").write_text("uncommitted edit\n")
        res = sync_main(self.local)
        self.assertTrue(res.ok)
        self.assertEqual(res.status, "refused-dirty")
        self.assertIn("README.md", res.dirty)
        # Fast-forward did NOT happen — local content preserved.
        self.assertEqual((self.local / "README.md").read_text(), "uncommitted edit\n")

    def test_refused_dirty_detail_is_loud_stale_base_warning(self) -> None:
        # main#822 (b): a refused ff while behind > 0 must surface a prominent
        # stale-base warning carrying the behind-count and the blocking paths,
        # not a single quiet line.
        self._advance_remote()
        (self.local / "README.md").write_text("uncommitted edit\n")
        res = sync_main(self.local)
        self.assertEqual(res.status, "refused-dirty")
        self.assertGreater(res.behind, 0)
        self.assertIn("STALE BASE", res.detail)
        self.assertIn(str(res.behind), res.detail)  # behind-count is surfaced
        self.assertIn("README.md", res.detail)  # blocking path is surfaced

    def _track_generated(self, gen: str) -> Path:
        """Track an allowlisted generated file on both clones, leaving a clean,
        in-sync state ready for a later ``_advance_remote`` clean ff."""
        gpath = self.local / gen
        gpath.parent.mkdir(parents=True, exist_ok=True)
        gpath.write_text("line1\n")
        _git(["add", gen], self.local)
        _git(["commit", "-m", f"track {gen}"], self.local)
        _git(["push", "origin", "main"], self.local)
        # other must catch up so a later remote advance is a clean ff for local.
        _git(["pull", "origin", "main"], self.other)
        return gpath

    def test_generated_allowlist_stashed_and_restored(self) -> None:
        # Every allowlisted generated file, dirtied alone, is stashed around the
        # ff and restored — it must NOT block the fast-forward. Covers main#822's
        # ontology/checksums.json alongside the annunaki log.
        self.tearDown()  # discard the auto-setUp repos; build fresh per entry
        for gen in sorted(GENERATED_ALLOWLIST):
            with self.subTest(generated=gen):
                self.setUp()  # fresh temp repos per allowlist entry
                try:
                    gpath = self._track_generated(gen)
                    self._advance_remote()
                    gpath.write_text("line1\nlocal-append\n")  # dirty it while behind

                    res = sync_main(self.local)
                    self.assertTrue(res.ok)
                    self.assertEqual(res.status, "fast-forwarded")
                    # Remote change landed AND the local generated append survived.
                    self.assertEqual((self.local / "README.md").read_text(), "v2\n")
                    self.assertEqual(gpath.read_text(), "line1\nlocal-append\n")
                finally:
                    self.tearDown()

    def test_checksums_json_is_allowlisted(self) -> None:
        # main#822 (1): the perpetually-dirty ontology checksums file must be in
        # the ff-stash allowlist so it never blocks a session-start fast-forward.
        self.assertIn("ontology/checksums.json", GENERATED_ALLOWLIST)

    def test_conflicting_generated_pop_degrades_gracefully(self) -> None:
        # main#822 caveat: if an incoming origin rewrite of a generated file
        # conflicts the stash pop, the ff still lands and the stash is left for
        # manual recovery — graceful, never a hard error and never lost work.
        gen = "ontology/checksums.json"
        gpath = self._track_generated(gen)

        # Remote rewrites BOTH the generated file and README, so the ff brings a
        # new generated-file blob that the stashed local edit conflicts with.
        (self.other / gen).write_text("line1\nremote-rewrite\n")
        (self.other / "README.md").write_text("v2\n")
        _git(["add", gen, "README.md"], self.other)
        _git(["commit", "-m", "remote rewrites generated file"], self.other)
        _git(["push", "origin", "main"], self.other)

        gpath.write_text("line1\nlocal-append\n")  # diverging local edit

        res = sync_main(self.local)
        self.assertTrue(res.ok)  # NOT a hard error
        self.assertEqual(res.status, "fast-forwarded")
        self.assertIn("stash", res.detail.lower())  # signals manual recovery
        # The fast-forward (the load-bearing part) landed.
        self.assertEqual((self.local / "README.md").read_text(), "v2\n")
        # Local work is preserved in the stash, not discarded.
        stash_list = _git(["stash", "list"], self.local).stdout
        self.assertTrue(stash_list.strip(), "local generated edit must remain stashed")

    def test_cli_refused_dirty_prints_loud_banner(self) -> None:
        # main#822 (b): the CLI surface (session-start Step 0) renders a refused
        # ff while behind as a multi-line banner, not one quiet line.
        self._advance_remote()
        (self.local / "README.md").write_text("uncommitted edit\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main([str(self.local)])
        out = buf.getvalue()
        self.assertEqual(rc, 0)  # refusal is a safe outcome, exit 0
        self.assertGreaterEqual(len(out.strip().splitlines()), 3)  # banner, not 1 line
        self.assertIn("STALE BASE", out)

    # ----- _parse_dirty unit -------------------------------------------

    def test_parse_dirty_excludes_untracked_and_follows_rename(self) -> None:
        porcelain = (
            " M src/a.py\n?? new_untracked.py\n!! ignored.log\n"
            "R  old.py -> renamed.py\nA  added.py\n"
        )
        self.assertEqual(
            _parse_dirty(porcelain),
            ["src/a.py", "renamed.py", "added.py"],
        )


if __name__ == "__main__":
    unittest.main()
