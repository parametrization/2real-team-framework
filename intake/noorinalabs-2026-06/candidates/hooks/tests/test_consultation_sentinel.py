#!/usr/bin/env python3
"""Tests for `_consultation_sentinel` shared helper.

Covers the four acceptance properties from #176:
- Path namespacing by skill (no collision across skills).
- TTL semantics (fresh vs stale via mtime).
- Fail-open on OSError (the helper never raises).
- Shell/Python parity via subprocess (the skill writes from shell; the
  hook reads from Python — both must compute the same path).

Plus dogfood / regression:
- The existing `enforce_librarian_consulted` test suite remains green
  (verified via `pytest .claude/hooks/tests/`) — this file only adds
  coverage of the helper's surface area.

Run: python3 -m pytest .claude/hooks/tests/test_consultation_sentinel.py -v
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import _consultation_sentinel as sentinel  # noqa: E402


class CwdSentinelHashTests(unittest.TestCase):
    """Hash formula must match the shell idiom `pwd | sha1sum | cut -c1-16`."""

    def test_matches_shell_idiom_with_trailing_newline(self):
        """Python hash MUST include the trailing newline that `pwd` emits."""
        sample = "/home/parameterization/code/noorinalabs-main"
        expected = hashlib.sha1((sample + "\n").encode("utf-8")).hexdigest()[:16]
        self.assertEqual(sentinel.cwd_sentinel_hash(sample), expected)

    def test_hash_is_16_chars(self):
        self.assertEqual(len(sentinel.cwd_sentinel_hash("/anywhere")), 16)

    def test_different_cwds_produce_different_hashes(self):
        h1 = sentinel.cwd_sentinel_hash("/a")
        h2 = sentinel.cwd_sentinel_hash("/b")
        self.assertNotEqual(h1, h2)

    def test_resolves_user_expansion(self):
        """`~/x` and the expanded form must hash identically."""
        h_tilde = sentinel.cwd_sentinel_hash("~/x")
        h_expanded = sentinel.cwd_sentinel_hash(os.path.expanduser("~/x"))
        self.assertEqual(h_tilde, h_expanded)

    def test_unparseable_path_falls_back_without_raising(self):
        """Pathological inputs must not raise (helper is fail-open)."""
        # A null byte is a path that os.path.abspath can sometimes handle,
        # but the helper's try/except should catch any ValueError. Just
        # confirm no exception escapes.
        try:
            sentinel.cwd_sentinel_hash("\x00bad")
        except Exception as e:  # noqa: BLE001
            self.fail(f"cwd_sentinel_hash raised on bad input: {e}")


class ConsultationSentinelPathTests(unittest.TestCase):
    """Pure path-composition tests (no filesystem access required)."""

    def test_canonical_shape(self):
        path = sentinel.consultation_sentinel_path("/home/user/repo", "ontology-librarian")
        self.assertEqual(
            path.relative_to("/home/user/repo"),
            Path(".claude/.consulted/ontology-librarian")
            / f"{sentinel.cwd_sentinel_hash('/home/user/repo')}.marker",
        )

    def test_namespacing_by_skill_distinct_paths(self):
        """Two skills under the same cwd must produce distinct sentinel paths."""
        p_lib = sentinel.consultation_sentinel_path("/x", "ontology-librarian")
        p_wave = sentinel.consultation_sentinel_path("/x", "wave-kickoff")
        self.assertNotEqual(p_lib, p_wave)
        self.assertIn("/ontology-librarian/", str(p_lib))
        self.assertIn("/wave-kickoff/", str(p_wave))

    def test_namespacing_same_hash_filename(self):
        """Different skills produce the SAME hash filename (cwd is the only
        hash input); the namespace lives in the directory, not the filename."""
        p1 = sentinel.consultation_sentinel_path("/x", "ontology-librarian")
        p2 = sentinel.consultation_sentinel_path("/x", "wave-kickoff")
        self.assertEqual(p1.name, p2.name)


class WriteConsultationSentinelTests(unittest.TestCase):
    """Skill-side write API."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="consult_sentinel_test_")

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_write_creates_marker_at_canonical_path(self):
        written = sentinel.write_consultation_sentinel("ontology-librarian", cwd=self._tmp)
        self.assertIsNotNone(written)
        assert written is not None
        expected = sentinel.consultation_sentinel_path(self._tmp, "ontology-librarian")
        self.assertEqual(written, expected)
        self.assertTrue(expected.exists())

    def test_write_body_contains_timestamp_and_cwd(self):
        written = sentinel.write_consultation_sentinel("ontology-librarian", cwd=self._tmp)
        assert written is not None
        body = written.read_text(encoding="utf-8")
        # ISO8601 form like YYYY-MM-DDTHH:MM:SSZ
        self.assertRegex(body, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
        # cwd appears too (so a human inspecting the marker can identify
        # which agent wrote it).
        self.assertIn(self._tmp, body)

    def test_write_creates_namespaced_subdirectory(self):
        written = sentinel.write_consultation_sentinel("wave-kickoff", cwd=self._tmp)
        assert written is not None
        self.assertTrue(written.parent.is_dir())
        # The subdirectory IS the skill name.
        self.assertEqual(written.parent.name, "wave-kickoff")

    def test_write_fails_open_on_oserror(self):
        """If the path can't be created (read-only fs, etc.), return None."""
        # Use a cwd inside a read-only directory.
        ro_dir = os.path.join(self._tmp, "readonly")
        os.makedirs(ro_dir)
        os.chmod(ro_dir, 0o555)  # read+exec, no write
        try:
            # write should fail at mkdir time; helper returns None, no raise.
            result = sentinel.write_consultation_sentinel("ontology-librarian", cwd=ro_dir)
            self.assertIsNone(result)
        finally:
            os.chmod(ro_dir, 0o755)

    def test_write_defaults_to_os_getcwd(self):
        """No cwd arg → write under os.getcwd()."""
        # Run from a known cwd via subprocess.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    f"import sys; sys.path.insert(0, {str(_HOOKS_DIR)!r}); "
                    "import _consultation_sentinel as s; "
                    "p = s.write_consultation_sentinel('test-skill'); "
                    "print(p)"
                ),
            ],
            cwd=self._tmp,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        written = result.stdout.strip()
        self.assertTrue(written.startswith(self._tmp))
        self.assertIn("/.claude/.consulted/test-skill/", written)


class ConsultationSentinelIsFreshTests(unittest.TestCase):
    """Hook-side read API: TTL semantics + freshness comparisons."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="consult_sentinel_test_")

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_at_offset(self, skill: str, mtime_offset: float) -> Path:
        """Write a sentinel at the canonical path, then shift its mtime."""
        path = sentinel.consultation_sentinel_path(self._tmp, skill)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ts content\n", encoding="utf-8")
        if mtime_offset != 0:
            new_time = time.time() + mtime_offset
            os.utime(path, (new_time, new_time))
        return path

    def test_fresh_sentinel_returns_true(self):
        self._write_at_offset("ontology-librarian", mtime_offset=0)
        self.assertTrue(sentinel.consultation_sentinel_is_fresh(self._tmp, "ontology-librarian"))

    def test_stale_sentinel_returns_false(self):
        """Mtime older than TTL → not fresh."""
        self._write_at_offset(
            "ontology-librarian", mtime_offset=-(sentinel.DEFAULT_TTL_SECONDS + 10)
        )
        self.assertFalse(sentinel.consultation_sentinel_is_fresh(self._tmp, "ontology-librarian"))

    def test_just_within_ttl_returns_true(self):
        """Mtime exactly TTL-10s in the past → still fresh."""
        self._write_at_offset(
            "ontology-librarian", mtime_offset=-(sentinel.DEFAULT_TTL_SECONDS - 10)
        )
        self.assertTrue(sentinel.consultation_sentinel_is_fresh(self._tmp, "ontology-librarian"))

    def test_future_mtime_returns_false(self):
        """A future-dated marker (clock skew or antedate) MUST NOT attest."""
        self._write_at_offset("ontology-librarian", mtime_offset=+3600)
        self.assertFalse(sentinel.consultation_sentinel_is_fresh(self._tmp, "ontology-librarian"))

    def test_missing_sentinel_returns_false(self):
        self.assertFalse(sentinel.consultation_sentinel_is_fresh(self._tmp, "ontology-librarian"))

    def test_custom_ttl_seconds(self):
        """Caller-supplied TTL overrides the default."""
        self._write_at_offset("ontology-librarian", mtime_offset=-30)
        # Default TTL (3600): fresh.
        self.assertTrue(sentinel.consultation_sentinel_is_fresh(self._tmp, "ontology-librarian"))
        # Tighter TTL (10s): stale.
        self.assertFalse(
            sentinel.consultation_sentinel_is_fresh(self._tmp, "ontology-librarian", ttl_seconds=10)
        )

    def test_empty_cwd_returns_false(self):
        self.assertFalse(sentinel.consultation_sentinel_is_fresh("", "ontology-librarian"))

    def test_empty_skill_returns_false(self):
        self.assertFalse(sentinel.consultation_sentinel_is_fresh(self._tmp, ""))

    def test_namespacing_isolation(self):
        """A sentinel for skill A must NOT attest for skill B in the same cwd."""
        self._write_at_offset("ontology-librarian", mtime_offset=0)
        self.assertTrue(sentinel.consultation_sentinel_is_fresh(self._tmp, "ontology-librarian"))
        self.assertFalse(sentinel.consultation_sentinel_is_fresh(self._tmp, "wave-kickoff"))

    def test_different_cwds_isolation(self):
        """A sentinel in cwd A must NOT attest for cwd B."""
        other = tempfile.mkdtemp(prefix="consult_sentinel_test_other_")
        try:
            self._write_at_offset("ontology-librarian", mtime_offset=0)
            self.assertTrue(
                sentinel.consultation_sentinel_is_fresh(self._tmp, "ontology-librarian")
            )
            self.assertFalse(sentinel.consultation_sentinel_is_fresh(other, "ontology-librarian"))
        finally:
            import shutil

            shutil.rmtree(other, ignore_errors=True)


class FindAttestingSentinelTests(unittest.TestCase):
    """Tolerant-read scan (#429): accept any fresh marker whose BODY records
    the matching cwd, even if the filename hash deviates from the canonical
    formula. Defends against ad-hoc writers that picked a non-standard hash
    (live evidence in cedric-0066-dark-mode-tokens worktree where two
    markers existed under the same cwd with hashes computed differently)."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="consult_sentinel_findany_")

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_marker(self, filename_hash: str, body_cwd: str, mtime_offset: float = 0.0) -> Path:
        skill_dir = Path(self._tmp) / sentinel.SENTINEL_PARENT_DIR / "ontology-librarian"
        skill_dir.mkdir(parents=True, exist_ok=True)
        marker = skill_dir / f"{filename_hash}.marker"
        marker.write_text(f"2026-05-14T00:00:00Z {body_cwd}\n", encoding="utf-8")
        if mtime_offset:
            new_time = time.time() + mtime_offset
            os.utime(marker, (new_time, new_time))
        return marker

    def test_canonical_marker_found(self):
        """Canonical hash filename + matching body cwd → accepted."""
        canonical_hash = sentinel.cwd_sentinel_hash(self._tmp)
        m = self._write_marker(canonical_hash, self._tmp)
        found = sentinel.find_attesting_sentinel(self._tmp, "ontology-librarian")
        self.assertEqual(found, m)

    def test_noncanonical_hash_filename_but_matching_body_accepted(self):
        """#429 rescue case: filename hash is wrong (writer forgot \\n in
        the shell idiom), but body cwd matches → accept it."""
        import hashlib

        wrong_hash = hashlib.sha1(self._tmp.encode()).hexdigest()[:16]  # no \n
        # Sanity: the wrong hash MUST differ from the canonical one, else
        # the test isn't exercising the tolerant-read path.
        self.assertNotEqual(wrong_hash, sentinel.cwd_sentinel_hash(self._tmp))
        m = self._write_marker(wrong_hash, self._tmp)
        found = sentinel.find_attesting_sentinel(self._tmp, "ontology-librarian")
        self.assertEqual(found, m, "wrong-hash filename with right body cwd must attest")

    def test_arbitrary_filename_but_matching_body_accepted(self):
        """Even a totally garbage filename works as long as the body
        records the correct cwd. This is intentional — the body is the
        attestation, the filename is a lookup convenience."""
        m = self._write_marker("not-a-hash-at-all", self._tmp)
        found = sentinel.find_attesting_sentinel(self._tmp, "ontology-librarian")
        self.assertEqual(found, m)

    def test_wrong_body_cwd_rejected(self):
        """Body cwd points at a DIFFERENT directory → reject. Guards the
        isolation property — a leftover marker from another worktree
        must not unlock this one."""
        other_dir = tempfile.mkdtemp(prefix="consult_other_")
        try:
            wrong_hash = "deadbeefcafe1234"
            self._write_marker(wrong_hash, other_dir)
            found = sentinel.find_attesting_sentinel(self._tmp, "ontology-librarian")
            self.assertIsNone(found, "cross-cwd body must not attest")
        finally:
            import shutil

            shutil.rmtree(other_dir, ignore_errors=True)

    def test_stale_marker_with_matching_body_rejected(self):
        """Even with correct body cwd, an over-TTL marker must not attest."""
        canonical_hash = sentinel.cwd_sentinel_hash(self._tmp)
        self._write_marker(
            canonical_hash, self._tmp, mtime_offset=-(sentinel.DEFAULT_TTL_SECONDS + 60)
        )
        found = sentinel.find_attesting_sentinel(self._tmp, "ontology-librarian")
        self.assertIsNone(found)

    def test_missing_skill_dir_returns_none(self):
        """No skill subdirectory at all → None (no error)."""
        found = sentinel.find_attesting_sentinel(self._tmp, "ontology-librarian")
        self.assertIsNone(found)

    def test_empty_cwd_or_skill_returns_none(self):
        self.assertIsNone(sentinel.find_attesting_sentinel("", "ontology-librarian"))
        self.assertIsNone(sentinel.find_attesting_sentinel(self._tmp, ""))

    def test_body_cwd_with_spaces_resolves_correctly(self):
        """Body cwd may contain spaces — `split(None, 1)` handles that."""
        spaced = os.path.join(self._tmp, "dir with spaces")
        os.makedirs(spaced)
        # Write the marker under the spaced cwd's skill dir so the scan
        # path lines up.
        marker_dir = Path(spaced) / sentinel.SENTINEL_PARENT_DIR / "ontology-librarian"
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker = marker_dir / "abc123.marker"
        marker.write_text(f"2026-05-14T00:00:00Z {spaced}\n", encoding="utf-8")
        found = sentinel.find_attesting_sentinel(spaced, "ontology-librarian")
        self.assertEqual(found, marker)

    def test_realpath_equivalence_via_symlink(self):
        """Body cwd recorded via symlink path, lookup via real path → match.
        Both sides resolve through realpath so symlink hops don't mask."""
        real = os.path.join(self._tmp, "real")
        os.makedirs(real)
        link = os.path.join(self._tmp, "link")
        os.symlink(real, link)
        # Marker lives in the real dir, body records the symlink path.
        marker_dir = Path(real) / sentinel.SENTINEL_PARENT_DIR / "ontology-librarian"
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker = marker_dir / "zzz.marker"
        marker.write_text(f"2026-05-14T00:00:00Z {link}\n", encoding="utf-8")
        # Lookup via real — match.
        found_via_real = sentinel.find_attesting_sentinel(real, "ontology-librarian")
        self.assertEqual(found_via_real, marker)
        # Lookup via link (realpath resolves to real) — also match.
        found_via_link = sentinel.find_attesting_sentinel(link, "ontology-librarian")
        self.assertEqual(found_via_link, marker)


class ShellPythonParityTests(unittest.TestCase):
    """The shell idiom in SKILL.md and the Python helper must produce
    identical paths. If they diverge, no sentinel would ever match."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="consult_sentinel_parity_")

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_shell_writes_path_python_reads(self):
        """Run the canonical SKILL.md shell idiom; assert the helper sees the marker."""
        result = subprocess.run(
            [
                "bash",
                "-c",
                (
                    "mkdir -p .claude/.consulted/ontology-librarian && "
                    "HASH=$(pwd | sha1sum | cut -c1-16) && "
                    "printf '%s %s\\n' "
                    '"$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(pwd)" '
                    '> .claude/.consulted/ontology-librarian/"$HASH".marker && '
                    "echo $HASH"
                ),
            ],
            cwd=self._tmp,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"shell failed: {result.stderr}")
        shell_hash = result.stdout.strip()
        py_hash = sentinel.cwd_sentinel_hash(self._tmp)
        self.assertEqual(
            shell_hash,
            py_hash,
            "Shell `pwd | sha1sum | cut -c1-16` and Python helper diverged — "
            "skill-written sentinels would never be recognized by the hook.",
        )
        # And the helper must see the marker as fresh.
        self.assertTrue(sentinel.consultation_sentinel_is_fresh(self._tmp, "ontology-librarian"))

    def test_python_writes_shell_reads_same_path(self):
        """Symmetric direction: helper writes, shell sees the same path."""
        written = sentinel.write_consultation_sentinel("ontology-librarian", cwd=self._tmp)
        self.assertIsNotNone(written)
        assert written is not None
        # Compute the expected filename via shell.
        shell_cmd = (
            "echo .claude/.consulted/ontology-librarian/$(pwd | sha1sum | cut -c1-16).marker"
        )
        result = subprocess.run(
            ["bash", "-c", shell_cmd],
            cwd=self._tmp,
            capture_output=True,
            text=True,
        )
        shell_relpath = result.stdout.strip()
        py_relpath = str(written.relative_to(self._tmp))
        self.assertEqual(shell_relpath, py_relpath)


if __name__ == "__main__":
    unittest.main(verbosity=2)
