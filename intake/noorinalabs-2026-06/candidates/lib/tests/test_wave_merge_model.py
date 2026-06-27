"""Tests for wave_merge_model — one-merge-model-per-wave + mid-wave wave-branch
reachability (main#801).

Verifies:
  1. validate_merge_model accepts the two models and rejects anything else.
  2. read_merge_model returns the recorded model, None when absent, and raises
     on a present-but-invalid value.
  3. classify_reachability covers every model×state combination:
       - no branch / not-ahead          → ok
       - direct-to-main + ahead         → VIOLATION (the P6W1 mixing), w/ or w/o PR
       - wave-branch  + ahead + open PR → ok
       - wave-branch  + ahead + no PR   → advisory (stranding risk)
       - unrecorded   + ahead           → advisory (legacy-wave degrade, never violation)
       - diverged status with ahead_by 0 is still treated as ahead.
  4. check_reachability maps each in-scope repo through classify via an injected
     gather (no network).
  5. EVERY gh call in the I/O layer goes through subprocess.run with a LIST arg
     vector and never shell=True — the word-split regression guard (main#688).
  6. set records wave_{M}_merge_model through the shared upsert helper and the
     CLI round-trips it; reachability's exit code is 1 only on a VIOLATION.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

# Helper lives at .claude/lib/wave_merge_model.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wave_merge_model as wmm  # noqa: E402

_REPOS = [
    "noorinalabs-main",
    "noorinalabs-isnad-graph",
    "noorinalabs-deploy",
]


def _write_status(tmp: Path, extra: dict) -> Path:
    path = tmp / "cross-repo-status.json"
    base = {"wave_2_repos_in_scope": list(_REPOS)}
    base.update(extra)
    path.write_text(json.dumps(base, indent=2))
    return path


class ValidateModelTest(unittest.TestCase):
    def test_accepts_both_models(self) -> None:
        self.assertEqual(wmm.validate_merge_model("direct-to-main"), "direct-to-main")
        self.assertEqual(wmm.validate_merge_model("wave-branch"), "wave-branch")

    def test_rejects_unknown(self) -> None:
        with self.assertRaises(ValueError):
            wmm.validate_merge_model("hybrid")
        with self.assertRaises(ValueError):
            wmm.validate_merge_model("")


class ReadModelTest(unittest.TestCase):
    def test_present(self) -> None:
        with TemporaryDirectory() as d:
            path = _write_status(Path(d), {"wave_2_merge_model": "wave-branch"})
            self.assertEqual(wmm.read_merge_model("2", path), "wave-branch")

    def test_absent_returns_none(self) -> None:
        with TemporaryDirectory() as d:
            path = _write_status(Path(d), {})
            self.assertIsNone(wmm.read_merge_model("2", path))

    def test_invalid_value_raises(self) -> None:
        with TemporaryDirectory() as d:
            path = _write_status(Path(d), {"wave_2_merge_model": "nonsense"})
            with self.assertRaises(ValueError):
                wmm.read_merge_model("2", path)


class ClassifyTest(unittest.TestCase):
    def test_no_branch_is_ok(self) -> None:
        sev, _ = wmm.classify_reachability(
            "wave-branch", branch_exists=False, ahead_by=0, status="absent", open_wave_main_pr=False
        )
        self.assertEqual(sev, wmm.OK)

    def test_not_ahead_is_ok(self) -> None:
        for model in (wmm.DIRECT_TO_MAIN, wmm.WAVE_BRANCH, None):
            sev, _ = wmm.classify_reachability(
                model, branch_exists=True, ahead_by=0, status="identical", open_wave_main_pr=False
            )
            self.assertEqual(sev, wmm.OK, model)

    def test_direct_to_main_ahead_is_violation(self) -> None:
        sev, msg = wmm.classify_reachability(
            wmm.DIRECT_TO_MAIN,
            branch_exists=True,
            ahead_by=3,
            status="ahead",
            open_wave_main_pr=False,
        )
        self.assertEqual(sev, wmm.VIOLATION)
        self.assertIn("mixing prohibited", msg)

    def test_direct_to_main_ahead_with_open_pr_still_violation(self) -> None:
        # An open wave→main PR under a direct-to-main wave means the wave drifted
        # into the model it did not declare — still a violation.
        sev, msg = wmm.classify_reachability(
            wmm.DIRECT_TO_MAIN,
            branch_exists=True,
            ahead_by=2,
            status="ahead",
            open_wave_main_pr=True,
        )
        self.assertEqual(sev, wmm.VIOLATION)
        self.assertIn("drifted", msg)

    def test_wave_branch_ahead_with_open_pr_is_ok(self) -> None:
        sev, _ = wmm.classify_reachability(
            wmm.WAVE_BRANCH, branch_exists=True, ahead_by=5, status="ahead", open_wave_main_pr=True
        )
        self.assertEqual(sev, wmm.OK)

    def test_wave_branch_ahead_no_pr_is_advisory(self) -> None:
        sev, msg = wmm.classify_reachability(
            wmm.WAVE_BRANCH, branch_exists=True, ahead_by=5, status="ahead", open_wave_main_pr=False
        )
        self.assertEqual(sev, wmm.ADVISORY)
        self.assertIn("WILL strand", msg)

    def test_unrecorded_model_ahead_degrades_to_advisory(self) -> None:
        # Legacy wave: never a hard violation, only an advisory + nudge.
        for pr in (True, False):
            sev, msg = wmm.classify_reachability(
                None, branch_exists=True, ahead_by=4, status="ahead", open_wave_main_pr=pr
            )
            self.assertEqual(sev, wmm.ADVISORY)
            self.assertIn("NOT declared", msg)

    def test_diverged_with_zero_ahead_is_treated_as_ahead(self) -> None:
        # status=diverged but ahead_by reported 0 → still ahead (defensive).
        sev, _ = wmm.classify_reachability(
            wmm.DIRECT_TO_MAIN,
            branch_exists=True,
            ahead_by=0,
            status="diverged",
            open_wave_main_pr=False,
        )
        self.assertEqual(sev, wmm.VIOLATION)


class CheckReachabilityTest(unittest.TestCase):
    def test_maps_each_repo_through_classify(self) -> None:
        # Injected gather: main behind (ok), isnad-graph ahead+no-PR, deploy no branch.
        states = {
            "noorinalabs-main": {
                "branch_exists": True,
                "ahead_by": 0,
                "status": "identical",
                "open_wave_main_pr": False,
            },
            "noorinalabs-isnad-graph": {
                "branch_exists": True,
                "ahead_by": 3,
                "status": "ahead",
                "open_wave_main_pr": False,
            },
            "noorinalabs-deploy": {
                "branch_exists": False,
                "ahead_by": 0,
                "status": "absent",
                "open_wave_main_pr": False,
            },
        }

        def fake_gather(repo: str, branch: str, run_gh) -> dict:
            assert branch == "deployments/phase-6/wave-2"
            return states[repo]

        with TemporaryDirectory() as d:
            path = _write_status(Path(d), {"wave_2_merge_model": "wave-branch"})
            results = wmm.check_reachability("6", "2", path, gather=fake_gather)

        by_repo = {r["repo"]: r["severity"] for r in results}
        self.assertEqual(by_repo["noorinalabs-main"], wmm.OK)
        self.assertEqual(by_repo["noorinalabs-isnad-graph"], wmm.ADVISORY)
        self.assertEqual(by_repo["noorinalabs-deploy"], wmm.OK)


class GhArgListGuardTest(unittest.TestCase):
    """Every gh invocation in the I/O layer must be a LIST arg vector, never a
    shell string and never shell=True (main#688 word-split guard)."""

    def test_gather_uses_arg_list_no_shell(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, *args, **kwargs):  # noqa: ANN001
            # Structural guards: arg vector is a list, gh is argv[0], no shell.
            self.assertIsInstance(cmd, list)
            self.assertEqual(cmd[0], "gh")
            self.assertNotIn("shell", kwargs)
            calls.append(cmd)
            # First call = ref lookup; then compare; then pr list.
            if cmd[1] == "api" and "git/refs" in cmd[2]:
                return subprocess.CompletedProcess(cmd, 0, stdout="abc123\n", stderr="")
            if cmd[1] == "api" and "compare" in cmd[2]:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout=json.dumps({"ahead_by": 2, "behind_by": 0, "status": "ahead"}),
                    stderr="",
                )
            return subprocess.CompletedProcess(cmd, 0, stdout="1\n", stderr="")

        with mock.patch("subprocess.run", side_effect=fake_run):
            state = wmm._gather_repo_state(
                "noorinalabs-deploy", "deployments/phase-6/wave-2", wmm._run_gh
            )
        self.assertEqual(state["ahead_by"], 2)
        self.assertTrue(state["open_wave_main_pr"])
        self.assertTrue(calls)

    def test_gather_missing_branch_returns_not_exists(self) -> None:
        def fake_run(cmd, *args, **kwargs):  # noqa: ANN001
            raise subprocess.CalledProcessError(1, cmd, stderr="Not Found")

        with mock.patch("subprocess.run", side_effect=fake_run):
            state = wmm._gather_repo_state(
                "noorinalabs-deploy", "deployments/phase-6/wave-2", wmm._run_gh
            )
        self.assertFalse(state["branch_exists"])


class SetAndCliTest(unittest.TestCase):
    def test_set_records_and_roundtrips(self) -> None:
        with TemporaryDirectory() as d:
            path = _write_status(Path(d), {})
            rc = wmm.main(["set", "6", "2", "wave-branch", "--status", str(path)])
            self.assertEqual(rc, 0)
            self.assertEqual(wmm.read_merge_model("2", path), "wave-branch")

    def test_set_rejects_invalid_model(self) -> None:
        with TemporaryDirectory() as d:
            path = _write_status(Path(d), {})
            rc = wmm.main(["set", "6", "2", "hybrid", "--status", str(path)])
            self.assertEqual(rc, 1)

    def test_model_command_errors_when_absent(self) -> None:
        with TemporaryDirectory() as d:
            path = _write_status(Path(d), {})
            rc = wmm.main(["model", "6", "2", "--status", str(path)])
            self.assertEqual(rc, 1)

    def test_reachability_exit_code_violation(self) -> None:
        with TemporaryDirectory() as d:
            path = _write_status(Path(d), {"wave_2_merge_model": "direct-to-main"})

            def fake_gather(repo, branch, run_gh):  # noqa: ANN001
                return {
                    "branch_exists": True,
                    "ahead_by": 1,
                    "status": "ahead",
                    "open_wave_main_pr": False,
                }

            with mock.patch.object(wmm, "_gather_repo_state", fake_gather):
                rc = wmm.main(["reachability", "6", "2", "--status", str(path)])
            self.assertEqual(rc, 1)

    def test_reachability_exit_code_advisory_is_zero(self) -> None:
        with TemporaryDirectory() as d:
            path = _write_status(Path(d), {"wave_2_merge_model": "wave-branch"})

            def fake_gather(repo, branch, run_gh):  # noqa: ANN001
                return {
                    "branch_exists": True,
                    "ahead_by": 1,
                    "status": "ahead",
                    "open_wave_main_pr": False,
                }

            with mock.patch.object(wmm, "_gather_repo_state", fake_gather):
                rc = wmm.main(["reachability", "6", "2", "--status", str(path)])
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
