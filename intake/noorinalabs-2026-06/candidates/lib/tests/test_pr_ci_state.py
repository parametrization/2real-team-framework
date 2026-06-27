"""Tests for pr_ci_state — the deterministic CI-readiness query CLI (main#802).

The oracle REUSES validate_pr_ci_status's `fetch_checks` + `classify_rollup`,
so these tests mock `fetch_checks` (never the network) and exercise the real
classifier. Coverage maps directly to the main#802 acceptance:

  1. empty rollup            -> NOT READY (exit 1)   [the load-bearing #802 rule]
  2. all-success rollup      -> READY     (exit 0)
  3. any-failure rollup      -> NOT READY (exit 1)
  4. pending (no failure)    -> NOT READY (exit 1)
  5. PR-fetch failure        -> CiStateError -> CLI exit 2
  6. empty is never "ready"  -> verdict=="empty" and ready() is False
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

# Helper lives at .claude/lib/pr_ci_state.py; test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pr_ci_state as pcs  # noqa: E402


def _check(name: str, *, conclusion: str = "", status: str = "", bucket: str = "") -> dict:
    out: dict = {"name": name}
    if conclusion:
        out["conclusion"] = conclusion
    if status:
        out["status"] = status
    if bucket:
        out["bucket"] = bucket
    return out


class ComputeCiStateTests(unittest.TestCase):
    def _state(self, rollup: list[dict] | None) -> pcs.CiState:
        with mock.patch.object(pcs.gate, "fetch_checks", return_value=rollup):
            return pcs.compute_ci_state("802", repo="noorinalabs/noorinalabs-main")

    # --- 1. empty rollup -> NOT READY (the #802 rule) ----------------------

    def test_empty_rollup_not_ready(self):
        state = self._state([])
        self.assertEqual(state.verdict, "empty")
        self.assertFalse(state.ready(), "empty rollup must be NOT READY (main#802)")
        self.assertEqual(state.check_count, 0)

    def test_empty_rollup_cli_exit_1(self):
        with mock.patch.object(pcs.gate, "fetch_checks", return_value=[]):
            rc = pcs.main(["802", "--repo", "noorinalabs/noorinalabs-main"])
        self.assertEqual(rc, 1, "empty rollup must exit 1 (not ready)")

    # --- 2. all-success -> READY -------------------------------------------

    def test_all_success_ready(self):
        rollup = [
            _check("Lint", conclusion="SUCCESS"),
            _check("Test", conclusion="SUCCESS"),
            _check("skipped-job", conclusion="SKIPPED"),
        ]
        state = self._state(rollup)
        self.assertEqual(state.verdict, "ready")
        self.assertTrue(state.ready())
        self.assertEqual(state.failing, [])
        self.assertEqual(state.pending, [])

    def test_all_success_cli_exit_0(self):
        rollup = [_check("Lint", conclusion="SUCCESS")]
        with mock.patch.object(pcs.gate, "fetch_checks", return_value=rollup):
            rc = pcs.main(["802", "--repo", "noorinalabs/noorinalabs-main"])
        self.assertEqual(rc, 0)

    # --- 3. any-failure -> NOT READY ---------------------------------------

    def test_any_failure_not_ready(self):
        rollup = [
            _check("Lint", conclusion="SUCCESS"),
            _check("Test", conclusion="FAILURE"),
        ]
        state = self._state(rollup)
        self.assertEqual(state.verdict, "failing")
        self.assertFalse(state.ready())
        self.assertIn("Test", state.failing)

    def test_any_failure_cli_exit_1(self):
        rollup = [_check("Test", conclusion="FAILURE")]
        with mock.patch.object(pcs.gate, "fetch_checks", return_value=rollup):
            rc = pcs.main(["802", "--repo", "noorinalabs/noorinalabs-main"])
        self.assertEqual(rc, 1)

    def test_failure_outranks_pending(self):
        """A rollup with both a failure and a pending check is 'failing'."""
        rollup = [
            _check("Test", conclusion="FAILURE"),
            _check("Build", status="IN_PROGRESS"),
        ]
        self.assertEqual(self._state(rollup).verdict, "failing")

    # --- 4. pending (no failure) -> NOT READY ------------------------------

    def test_pending_not_ready(self):
        rollup = [
            _check("Lint", conclusion="SUCCESS"),
            _check("Test", status="IN_PROGRESS"),
        ]
        state = self._state(rollup)
        self.assertEqual(state.verdict, "pending")
        self.assertFalse(state.ready())
        self.assertIn("Test", state.pending)

    # --- 5. fetch failure -> error -> exit 2 -------------------------------

    def test_fetch_failure_raises(self):
        with mock.patch.object(pcs.gate, "fetch_checks", return_value=None):
            with self.assertRaises(pcs.CiStateError):
                pcs.compute_ci_state("802", repo="noorinalabs/noorinalabs-main")

    def test_fetch_failure_cli_exit_2(self):
        with mock.patch.object(pcs.gate, "fetch_checks", return_value=None):
            rc = pcs.main(["802", "--repo", "noorinalabs/noorinalabs-main"])
        self.assertEqual(rc, 2)

    # --- 6. empty is structurally never ready ------------------------------

    def test_ready_iff_verdict_ready(self):
        for rollup, expect_ready in (
            ([], False),
            ([_check("Lint", conclusion="SUCCESS")], True),
            ([_check("Test", conclusion="FAILURE")], False),
            ([_check("Test", status="QUEUED")], False),
        ):
            with self.subTest(rollup=rollup):
                self.assertEqual(self._state(rollup).ready(), expect_ready)


class RenderTests(unittest.TestCase):
    """The empty-rollup report must carry the #802 'never green' note."""

    def test_empty_text_flags_hard_not_ready(self):
        with mock.patch.object(pcs.gate, "fetch_checks", return_value=[]):
            state = pcs.compute_ci_state("802", repo="noorinalabs/noorinalabs-main")
        text = pcs._render_text(state)
        self.assertIn("NOT READY", text)
        self.assertIn("main#802", text)

    def test_json_includes_ready_flag(self):
        rollup = [_check("Lint", conclusion="SUCCESS")]
        with mock.patch.object(pcs.gate, "fetch_checks", return_value=rollup):
            state = pcs.compute_ci_state("802", repo="noorinalabs/noorinalabs-main")
        import json as _json

        payload = _json.loads(pcs._render_json(state))
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["verdict"], "ready")


if __name__ == "__main__":
    unittest.main()
