#!/usr/bin/env python3
"""Tests for the `session_handoff` Stop hook's wave/phase reader (#708).

Regression coverage: `_get_wave_status()` used to read the top-level keys
`wave` / `started`, neither of which exists in cross-repo-status.json, so it
always reported "unknown". The fix reads the canonical lifecycle keys
`current_phase` / `current_wave` / `wave_<N>_started_at`.

Run from the repo root:
    ENVIRONMENT=test python3 -m pytest \\
        .claude/hooks/tests/test_session_handoff.py -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import session_handoff as hook  # noqa: E402


def _live_shaped(**overrides: object) -> dict:
    """A dict shaped like the real cross-repo-status.json, incl. stale keys."""
    data: dict = {
        "current_phase": 5,
        "current_wave": "wave-5",
        "wave_5_started_at": "2026-06-16T22:51:14Z",
        "wave_5_kicked_off_at": None,
        # Stale flat keys that the buggy reader trusted:
        "phase": "phase-4",
        "wave": None,
        "started": None,
        "last_updated": "2026-06-15T01:52:55Z",
    }
    data.update(overrides)
    return data


class WavePhaseStartedTests(unittest.TestCase):
    def test_reads_canonical_keys_not_stale_flat_keys(self) -> None:
        phase, wave, started = hook._wave_phase_started(_live_shaped())
        self.assertEqual(phase, "5")
        self.assertEqual(wave, "wave-5")
        self.assertEqual(started, "2026-06-16T22:51:14Z")
        # The stale flat keys must NOT leak through.
        self.assertNotEqual(phase, "phase-4")
        self.assertNotEqual(wave, "unknown")

    def test_falls_back_to_kicked_off_at_when_started_missing(self) -> None:
        data = _live_shaped()
        del data["wave_5_started_at"]
        data["wave_5_kicked_off_at"] = "2026-06-16T20:00:00Z"
        _, _, started = hook._wave_phase_started(data)
        self.assertEqual(started, "2026-06-16T20:00:00Z")

    def test_falls_back_when_started_present_but_null(self) -> None:
        data = _live_shaped(wave_5_started_at=None, wave_5_kicked_off_at="2026-06-16T20:00:00Z")
        _, _, started = hook._wave_phase_started(data)
        self.assertEqual(started, "2026-06-16T20:00:00Z")

    def test_started_unknown_when_no_timestamps(self) -> None:
        data = _live_shaped(wave_5_started_at=None, wave_5_kicked_off_at=None)
        _, _, started = hook._wave_phase_started(data)
        self.assertEqual(started, "unknown")

    def test_missing_canonical_keys_graceful(self) -> None:
        phase, wave, started = hook._wave_phase_started({"last_updated": "x"})
        self.assertEqual(phase, "unknown")
        self.assertEqual(wave, "unknown")
        self.assertEqual(started, "unknown")


class GetWaveStatusTests(unittest.TestCase):
    def _write_status(self, tmp: Path, data: dict) -> None:
        (tmp / "cross-repo-status.json").write_text(json.dumps(data), encoding="utf-8")

    def test_wrapper_reports_phase_and_wave(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            self._write_status(tmp, _live_shaped())
            original = hook.REPO_ROOT
            try:
                hook.REPO_ROOT = tmp
                result = hook._get_wave_status()
            finally:
                hook.REPO_ROOT = original
        self.assertEqual(result, "Phase 5, Wave wave-5 (started 2026-06-16T22:51:14Z)")
        self.assertNotIn("unknown", result)
        self.assertNotIn("phase-4", result)

    def test_wrapper_missing_file(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            original = hook.REPO_ROOT
            try:
                hook.REPO_ROOT = Path(d)
                result = hook._get_wave_status()
            finally:
                hook.REPO_ROOT = original
        self.assertEqual(result, "No cross-repo-status.json found")


class HandoffPathLocationTests(unittest.TestCase):
    """#741: the Stop hook must write the handoff into the in-repo,
    version-controlled .claude/memory/ — NOT the user-space auto-memory dir —
    so it and the /session-start skill agree on one file (no split-brain).
    """

    def test_handoff_file_is_in_repo_memory(self) -> None:
        expected = hook.REPO_ROOT / ".claude" / "memory" / "session_handoff.md"
        self.assertEqual(hook.HANDOFF_FILE, expected)

    def test_handoff_not_in_user_space(self) -> None:
        self.assertNotIn("/.claude/projects/", hook.HANDOFF_FILE.as_posix())
        self.assertFalse(hook.HANDOFF_FILE.is_relative_to(Path.home() / ".claude" / "projects"))

    def test_tracked_memory_index_autochurn_removed(self) -> None:
        # The Stop hook no longer auto-rewrites the tracked MEMORY.md index line
        # (#741); ensure the constant is gone so the churn can't silently return.
        self.assertFalse(hasattr(hook, "MEMORY_INDEX"))


if __name__ == "__main__":
    unittest.main()
