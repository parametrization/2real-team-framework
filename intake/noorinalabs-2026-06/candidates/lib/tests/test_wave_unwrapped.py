"""Tests for wave_unwrapped — the session-start "wave merged but unwrapped"
detector (main#730).

Verifies:
  1. current_wave_number parses "wave-2" -> "2" and degrades on junk.
  2. is_wrapped recognizes every historical marker spelling and ignores
     completed_at (which marks an earlier point — must NOT count as wrapped).
  3. The verdict matrix: ok / in_flight / unwrapped / unwrapped_unverified.
  4. Detection is scoped to current_wave only — a stale cross-phase
     wave_4_active=true ghost (main#683) does NOT false-fire.
  5. base_branch prefers wave_{M}_branches.branch over a stale phase key.
  6. A gh failure degrades to unwrapped_unverified, never a false 0/nudge-miss.
  7. The `check` CLI always exits 0 (non-fatal) and prints a NUDGE only when
     the verdict warrants one.
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

# Helper lives at .claude/lib/wave_unwrapped.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wave_unwrapped  # noqa: E402


def _status(**overrides) -> dict:
    """A baseline live-wave-2 status; overrides patch individual keys."""
    data = {
        "current_wave": "wave-2",
        "wave_2_active": True,
        "wave_2_repos_in_scope": ["noorinalabs-main", "noorinalabs-isnad-graph"],
        "wave_2_branches": {"branch": "deployments/phase-6/wave-2"},
    }
    data.update(overrides)
    return data


class CurrentWaveNumberTest(unittest.TestCase):
    def test_parses_prefixed_form(self) -> None:
        self.assertEqual(wave_unwrapped.current_wave_number({"current_wave": "wave-2"}), "2")

    def test_bare_digit(self) -> None:
        self.assertEqual(wave_unwrapped.current_wave_number({"current_wave": "7"}), "7")

    def test_missing_or_junk_is_none(self) -> None:
        self.assertIsNone(wave_unwrapped.current_wave_number({}))
        self.assertIsNone(wave_unwrapped.current_wave_number({"current_wave": "wave-x"}))
        self.assertIsNone(wave_unwrapped.current_wave_number({"current_wave": 2}))


class IsWrappedTest(unittest.TestCase):
    def test_each_marker_variant_counts(self) -> None:
        for marker in ("wrapped_up_at", "wrapup_completed_at", "wrapped_at"):
            with self.subTest(marker=marker):
                self.assertTrue(
                    wave_unwrapped.is_wrapped({f"wave_2_{marker}": "2026-06-20T00:00:00Z"}, "2")
                )

    def test_null_marker_not_wrapped(self) -> None:
        self.assertFalse(wave_unwrapped.is_wrapped({"wave_2_wrapped_up_at": None}, "2"))

    def test_completed_at_does_not_count(self) -> None:
        # completed_at marks an earlier lifecycle point; counting it would mask
        # the merge->wrapup gap #730 exists to detect.
        self.assertFalse(
            wave_unwrapped.is_wrapped({"wave_2_completed_at": "2026-06-09T00:00:00Z"}, "2")
        )


class BaseBranchTest(unittest.TestCase):
    def test_prefers_recorded_branch_over_stale_phase(self) -> None:
        data = _status()
        # Even with a misleading phase arg, the recorded branch wins.
        self.assertEqual(wave_unwrapped.base_branch(data, "2", "4"), "deployments/phase-6/wave-2")

    def test_constructs_from_phase_when_no_branch(self) -> None:
        self.assertEqual(wave_unwrapped.base_branch({}, "2", "6"), "deployments/phase-6/wave-2")

    def test_none_when_unresolvable(self) -> None:
        self.assertIsNone(wave_unwrapped.base_branch({}, "2", None))


class EvaluateVerdictTest(unittest.TestCase):
    def test_unwrapped_fires_on_zero_open_prs(self) -> None:
        with mock.patch.object(wave_unwrapped, "count_open_prs", return_value=0):
            res = wave_unwrapped.evaluate(_status())
        self.assertEqual(res["verdict"], "unwrapped")
        self.assertEqual(res["open_pr_count"], 0)
        self.assertIn("/wave-wrapup", res["message"])

    def test_in_flight_when_open_prs_remain(self) -> None:
        with mock.patch.object(wave_unwrapped, "count_open_prs", return_value=3):
            res = wave_unwrapped.evaluate(_status())
        self.assertEqual(res["verdict"], "in_flight")

    def test_ok_when_wrapped(self) -> None:
        res = wave_unwrapped.evaluate(
            _status(wave_2_wrapped_up_at="2026-06-20T00:00:00Z"), check_prs=False
        )
        self.assertEqual(res["verdict"], "ok")
        self.assertTrue(res["wrapped"])

    def test_ok_when_inactive(self) -> None:
        res = wave_unwrapped.evaluate(_status(wave_2_active=False), check_prs=False)
        self.assertEqual(res["verdict"], "ok")

    def test_ok_when_no_current_wave(self) -> None:
        res = wave_unwrapped.evaluate({}, check_prs=False)
        self.assertEqual(res["verdict"], "ok")
        self.assertIsNone(res["wave"])

    def test_gh_failure_degrades_to_unverified(self) -> None:
        with mock.patch.object(wave_unwrapped, "count_open_prs", return_value=None):
            res = wave_unwrapped.evaluate(_status())
        self.assertEqual(res["verdict"], "unwrapped_unverified")

    def test_no_gh_flag_degrades_to_unverified(self) -> None:
        # check_prs=False must not invoke gh and must not claim 0 open PRs.
        with mock.patch.object(wave_unwrapped, "_run_gh", side_effect=AssertionError("gh called")):
            res = wave_unwrapped.evaluate(_status(), check_prs=False)
        self.assertEqual(res["verdict"], "unwrapped_unverified")
        self.assertIsNone(res["open_pr_count"])

    def test_missing_scope_keys_degrade_unverified(self) -> None:
        data = _status()
        del data["wave_2_repos_in_scope"]
        with mock.patch.object(wave_unwrapped, "_run_gh", side_effect=AssertionError("gh called")):
            res = wave_unwrapped.evaluate(data)
        self.assertEqual(res["verdict"], "unwrapped_unverified")


class CrossPhaseGhostTest(unittest.TestCase):
    """A stale wave_4_active=true from a prior phase (main#683) must not fire —
    detection is scoped to current_wave (=2 here)."""

    def test_stale_prior_phase_wave_ignored(self) -> None:
        data = _status(
            wave_4_active=True,  # leftover P5W4 ghost, unwrapped
        )
        with mock.patch.object(wave_unwrapped, "count_open_prs", return_value=3):
            res = wave_unwrapped.evaluate(data)
        # Verdict reflects wave 2 (in flight), never wave 4.
        self.assertEqual(res["wave"], "2")
        self.assertEqual(res["verdict"], "in_flight")


class CountOpenPrsTest(unittest.TestCase):
    def test_sums_across_repos_via_arg_list(self) -> None:
        calls: list[list[str]] = []

        def fake_gh(args: list[str]) -> str:
            calls.append(args)
            return json.dumps([{"number": 1}, {"number": 2}])

        with mock.patch.object(wave_unwrapped, "_run_gh", side_effect=fake_gh):
            total = wave_unwrapped.count_open_prs(["a", "b"], "deployments/phase-6/wave-2")
        self.assertEqual(total, 4)  # 2 repos * 2 PRs
        # Every gh call is a list arg vector with the correct base.
        for c in calls:
            self.assertIsInstance(c, list)
            self.assertIn("deployments/phase-6/wave-2", c)

    def test_gh_error_returns_none(self) -> None:
        import subprocess

        with mock.patch.object(
            wave_unwrapped, "_run_gh", side_effect=subprocess.CalledProcessError(1, ["gh"])
        ):
            self.assertIsNone(wave_unwrapped.count_open_prs(["a"], "base"))


class CliTest(unittest.TestCase):
    def _write(self, data: dict) -> Path:
        tmp = Path(self._tmp.name) / "cross-repo-status.json"
        tmp.write_text(json.dumps(data))
        return tmp

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_check_prints_nudge_and_exits_zero(self) -> None:
        status = self._write(_status())
        buf = io.StringIO()
        with mock.patch.object(wave_unwrapped, "count_open_prs", return_value=0):
            with redirect_stdout(buf):
                rc = wave_unwrapped.main(["check", "--status", str(status)])
        self.assertEqual(rc, 0)
        self.assertIn("NUDGE", buf.getvalue())
        self.assertIn("/wave-wrapup", buf.getvalue())

    def test_check_no_nudge_when_in_flight(self) -> None:
        status = self._write(_status())
        buf = io.StringIO()
        with mock.patch.object(wave_unwrapped, "count_open_prs", return_value=2):
            with redirect_stdout(buf):
                rc = wave_unwrapped.main(["check", "--status", str(status)])
        self.assertEqual(rc, 0)
        self.assertNotIn("NUDGE", buf.getvalue())

    def test_check_unreadable_status_exits_zero(self) -> None:
        rc = wave_unwrapped.main(["check", "--status", "/no/such/path.json"])
        self.assertEqual(rc, 0)

    def test_json_output(self) -> None:
        status = self._write(_status())
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wave_unwrapped.main(["check", "--status", str(status), "--no-gh", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["wave"], "2")
        self.assertEqual(payload["verdict"], "unwrapped_unverified")


if __name__ == "__main__":
    unittest.main()
