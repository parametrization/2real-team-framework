#!/usr/bin/env python3
"""Tests for the `session_start` SessionStart hook's wave/phase reader (#708).

Regression coverage: `_wave_status()` used to read the flat keys `phase`
(which lags a phase behind — #683 cross-phase collision), `wave` (which does
not exist), and `last_updated`. The fix reads the canonical lifecycle keys
`current_phase` / `current_wave` / `wave_<N>_started_at`.

Run from the repo root:
    ENVIRONMENT=test python3 -m pytest \\
        .claude/hooks/tests/test_session_start.py -v
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import session_start as hook  # noqa: E402


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


class WaveStatusWrapperTests(unittest.TestCase):
    def test_wrapper_reports_phase_and_wave(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            status = Path(d) / "cross-repo-status.json"
            status.write_text(json.dumps(_live_shaped()), encoding="utf-8")
            original = hook._CROSS_REPO_STATUS
            try:
                hook._CROSS_REPO_STATUS = status
                result = hook._wave_status()
            finally:
                hook._CROSS_REPO_STATUS = original
        self.assertEqual(result, "Phase 5, Wave wave-5 (started: 2026-06-16T22:51:14Z)")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertNotIn("unknown", result)
        self.assertNotIn("phase-4", result)

    def test_wrapper_returns_none_on_missing_file(self) -> None:
        original = hook._CROSS_REPO_STATUS
        try:
            hook._CROSS_REPO_STATUS = Path("/nonexistent/cross-repo-status.json")
            result = hook._wave_status()
        finally:
            hook._CROSS_REPO_STATUS = original
        self.assertIsNone(result)


class HandoffPathLocationTests(unittest.TestCase):
    """#741: the SessionStart hook must read the handoff from the in-repo,
    version-controlled .claude/memory/ — NOT the user-space
    ~/.claude/projects/<encoded>/memory/ auto-memory dir. Reading user-space
    while the /session-start skill reads in-repo is the split-brain this fixes.
    """

    def test_handoff_is_in_repo_memory(self) -> None:
        expected = hook._PROJECT / ".claude" / "memory" / "session_handoff.md"
        self.assertEqual(hook._HANDOFF, expected)

    def test_handoff_not_in_user_space(self) -> None:
        self.assertNotIn("/.claude/projects/", hook._HANDOFF.as_posix())
        self.assertFalse(hook._HANDOFF.is_relative_to(Path.home() / ".claude" / "projects"))


if __name__ == "__main__":
    unittest.main()
