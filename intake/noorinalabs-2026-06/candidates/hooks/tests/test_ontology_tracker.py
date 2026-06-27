#!/usr/bin/env python3
"""Tests for ontology_tracker hook path filtering.

Covers the W8 hook-authorship-spec requirement: NEGATIVE MATCH coverage for
the three noise patterns in issue #143 (/tmp, .claude/worktrees, out-of-repo)
plus a positive case (real source file inside the repo).

Run: python3 -m pytest .claude/hooks/tests/test_ontology_tracker.py -v
Or:  python3 .claude/hooks/tests/test_ontology_tracker.py
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

import ontology_tracker as hook  # noqa: E402


class ShouldSkipNegativeTests(unittest.TestCase):
    """Negative-match coverage for the three issue-#143 noise patterns."""

    def test_tmp_prefix_is_skipped(self):
        """/tmp/* — ephemeral scratch (issue-body staging files)."""
        self.assertTrue(hook._should_skip("/tmp/issue-body-1234.md"))

    def test_tmp_nested_is_skipped(self):
        """/tmp/<dir>/<file> — also ephemeral."""
        self.assertTrue(hook._should_skip("/tmp/staging/notes.md"))

    def test_worktree_inside_repo_is_skipped(self):
        """.claude/worktrees/** — in-flight copies of tracked files.

        The eventual merge-to-main triggers a separate Edit on the canonical
        repo path; double-tracking the worktree copy pollutes checksums with
        stale paths once the worktree is removed.
        """
        wt_path = str(
            hook.REPO_ROOT
            / ".claude"
            / "worktrees"
            / "A.Virtanen-0143-tracker"
            / "ontology"
            / "services.yaml"
        )
        self.assertTrue(hook._should_skip(wt_path))

    def test_worktree_substring_anywhere_is_skipped(self):
        """The worktrees marker need only appear as a substring in the path."""
        self.assertTrue(hook._should_skip("/some/other/root/.claude/worktrees/foo/bar.md"))

    def test_out_of_repo_absolute_path_is_skipped(self):
        """Files outside REPO_ROOT (e.g. user auto-memory) — out of scope."""
        # Use a real existing path that is guaranteed outside REPO_ROOT
        # so resolve() does not fail. /etc/hostname is universally readable
        # on Linux test runners.
        self.assertTrue(hook._should_skip("/etc/hostname"))

    def test_home_memory_path_is_skipped(self):
        """The exact pattern reported in #143: user auto-memory files.

        Out-of-repo absolute paths (e.g. ``/home/.../.claude/projects/.../
        memory/MEMORY.md``) must be skipped because they are outside
        REPO_ROOT.
        """
        self.assertTrue(
            hook._should_skip("/home/parameterization/.claude/projects/foo/memory/MEMORY.md")
        )


class _FakeRepoRootMixin:
    """Monkeypatch ``hook.REPO_ROOT`` to a fresh non-worktree temp dir.

    Any test that builds a fixture path under ``hook.REPO_ROOT`` must be
    independent of *where pytest is invoked from*. The real ``REPO_ROOT`` is
    derived from ``__file__`` (``…/parent/parent/parent``), so when the suite
    runs from a linked worktree under ``.claude/worktrees/`` it itself
    contains a ``.worktrees`` path component. A fixture like
    ``REPO_ROOT / "docs" / "notes.worktrees.md"`` would then spuriously match
    ``_is_worktree_path`` and the negative-case assertion would FALSE-fail
    (#686) — even though the same test is green on a normal checkout and in
    CI. Anchoring fixtures under a temp dir that is outside both ``/tmp/``
    (skipped by ``SKIP_PREFIXES``) and any ``*/.worktrees/`` tree (skipped by
    the segment check) keeps them invocation-location independent.
    """

    def setUp(self):
        super().setUp()
        # Place the fake root under the user's home cache directory so it is
        # outside /tmp/ and outside any worktree tree (see class docstring).
        base = Path.home() / ".cache" / "noorinalabs-test-ontology-tracker"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(prefix="ont_track_", dir=str(base))
        self._fake_root = Path(self._tmp.name).resolve()
        self._orig_root = hook.REPO_ROOT
        hook.REPO_ROOT = self._fake_root

    def tearDown(self):
        hook.REPO_ROOT = self._orig_root
        self._tmp.cleanup()
        super().tearDown()


class ShouldSkipPositiveTests(_FakeRepoRootMixin, unittest.TestCase):
    """Positive regression — real in-repo source files MUST still track.

    These tests construct paths inside a temporary fake "repo root" (see
    ``_FakeRepoRootMixin``) so they pass identically whether the test runner
    is checked out in the main repo or a worktree.
    """

    def test_in_repo_ontology_yaml_is_tracked(self):
        """ontology/services.yaml under REPO_ROOT — the canonical positive case."""
        path = str(self._fake_root / "ontology" / "services.yaml")
        self.assertFalse(hook._should_skip(path))

    def test_in_repo_relative_path_is_tracked(self):
        """A relative in-repo path resolves under REPO_ROOT and is tracked."""
        cwd = os.getcwd()
        try:
            os.chdir(self._fake_root)
            self.assertFalse(hook._should_skip("ontology/conventions.md"))
        finally:
            os.chdir(cwd)

    def test_in_repo_hook_file_is_tracked(self):
        """A source file inside .claude/hooks/ should be tracked."""
        path = str(self._fake_root / ".claude" / "hooks" / "ontology_tracker.py")
        self.assertFalse(hook._should_skip(path))

    def test_semantic_overlay_repo_yaml_is_tracked(self):
        """#857: the hand-curated overlay (ontology/repos/*.yaml) IS still tracked.

        Only the GENERATED structural layer is dropped from tracking; the
        semantic overlay remains under the tracker/resolver.
        """
        path = str(self._fake_root / "ontology" / "repos" / "isnad-graph.yaml")
        self.assertFalse(hook._should_skip(path))


class ShouldSkipStructuralLayerTests(_FakeRepoRootMixin, unittest.TestCase):
    """#857: the GENERATED structural layer must NOT be checksum-tracked.

    ``ontology/structural/`` is regenerated wholesale by an owned generator
    (#855); it is always-current-by-regeneration, so dirty-tracking it would be
    meaningless churn and ``/ontology-rebuild`` has nothing to resolve there.
    The tracker skips it exactly like it skips ``checksums.json`` itself.
    """

    def test_structural_yaml_is_skipped_absolute(self):
        path = str(self._fake_root / "ontology" / "structural" / "modules.yaml")
        self.assertTrue(hook._should_skip(path))

    def test_structural_nested_is_skipped(self):
        path = str(self._fake_root / "ontology" / "structural" / "isnad-graph" / "index.json")
        self.assertTrue(hook._should_skip(path))

    def test_structural_relative_path_is_skipped(self):
        self.assertTrue(hook._should_skip("ontology/structural/services.yaml"))


class ShouldSkipTopLevelWorktreesTests(_FakeRepoRootMixin, unittest.TestCase):
    """#525: top-level `.worktrees/` paths must be skipped.

    The change-tracker anchors on the orchestrator cwd; an Edit inside a
    worktree gets recorded as a worktree-relative path like
    ``.worktrees/deploy-0348-aisha/...``. Pre-#525 only ``.claude/worktrees/``
    was skipped, so the top-level convention (gitignored as of #523) polluted
    the parent ``checksums.json`` with entries that never resolve and once
    aborted a ``git merge --ff-only``.

    Uses ``_FakeRepoRootMixin`` so the ``REPO_ROOT``-anchored fixtures below
    are independent of whether pytest runs from the main checkout or a linked
    worktree (#686).
    """

    def test_relative_top_level_worktrees_path_is_skipped(self):
        """The exact #525 evidence shape — a worktree-relative path."""
        self.assertTrue(
            hook._should_skip(".worktrees/deploy-0348-aisha/terraform/cloudflare/variables.tf")
        )

    def test_relative_top_level_worktrees_status_file_is_skipped(self):
        self.assertTrue(hook._should_skip(".worktrees/main-w11-unblock/cross-repo-status.json"))

    def test_absolute_top_level_worktrees_path_is_skipped(self):
        wt = str(hook.REPO_ROOT / ".worktrees" / "0528-cwd-anchor" / "ontology" / "domain.yaml")
        self.assertTrue(hook._should_skip(wt))

    def test_worktrees_segment_not_substring_false_match(self):
        """A file merely NAMED with a worktrees substring is NOT skipped.

        Segment-matching (not substring) guards against skipping a real
        source file like ``notes.worktrees.md`` — only a path COMPONENT of
        ``.worktrees`` triggers the skip.
        """
        # Place it under REPO_ROOT so the out-of-repo filter doesn't fire.
        legit = str(hook.REPO_ROOT / "docs" / "notes.worktrees.md")
        self.assertFalse(hook._is_worktree_path(legit))

    def test_claude_worktrees_still_skipped_via_segment(self):
        """The historical convention is also caught by the segment check."""
        self.assertTrue(
            hook._is_worktree_path(".claude/worktrees/A.Virtanen-0143/ontology/services.yaml")
        )

    def test_bare_worktrees_dir_without_claude_parent_not_skipped(self):
        """A dir literally named ``worktrees`` but NOT under ``.claude`` is fine."""
        self.assertFalse(hook._is_worktree_path("src/worktrees/helper.py"))


class ShouldSkipExistingFiltersTests(unittest.TestCase):
    """Regression — pre-existing SKIP_PATTERNS keep working."""

    def test_checksums_file_is_skipped(self):
        self.assertTrue(hook._should_skip("ontology/checksums.json"))

    def test_pycache_is_skipped(self):
        self.assertTrue(hook._should_skip("foo/__pycache__/bar.cpython-312.pyc"))

    def test_git_dir_is_skipped(self):
        self.assertTrue(hook._should_skip(".git/HEAD"))

    def test_annunaki_log_is_skipped(self):
        self.assertTrue(hook._should_skip(".claude/annunaki/errors.jsonl"))


if __name__ == "__main__":
    unittest.main()
