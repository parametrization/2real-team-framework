"""Tests for check_agent_liveness — the agent-liveness sweep (#745, from #735).

Covers the two mechanized charter rules:
  * agents.md § Agent Liveness Checkpoint — (a) TaskCreate-per-implementer and
    (b) zero-artifact-after-N-idle-notifications.
  * agents.md § Throttle-Stall Recovery — the 30/45/60-min cadence.

The snapshots here are the failure shapes the rules exist to catch: the P5W2
#1024 / P5W3 #1038 zero-artifact stalls and the W12 ig#931 throttle gap.
"""

from __future__ import annotations

import dataclasses
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_agent_liveness import (  # noqa: E402
    IDLE_NOTIFICATION_FLAG_THRESHOLD,
    THROTTLE_FIRST_PING_MIN,
    THROTTLE_SECOND_PING_MIN,
    THROTTLE_TAKEOVER_MIN,
    Finding,
    SnapshotError,
    evaluate,
    has_artifact,
    has_pending_work,
    main,
    task_exists_for,
)

NO_ARTIFACT = {"branch_pushed": False, "pr_opened": False, "commits": 0}


def _impl(**over) -> dict:
    """An otherwise-live implementer entry; override fields per test."""
    base = {
        "name": "Nadia Khoury",
        "issue_ref": "main#745",
        "role": "implementer",
        "idle_notifications": 0,
        "idle_minutes": 0,
        "worktree_dirty": False,
        "artifacts": {"branch_pushed": True, "pr_opened": True, "commits": 3},
    }
    base.update(over)
    return base


def _task(**over) -> dict:
    base = {
        "subject": "main#745 — mechanize liveness",
        "owner": "Nadia Khoury",
        "status": "in_progress",
    }
    base.update(over)
    return base


def _snap(impls, tasks=None) -> dict:
    return {"implementers": impls, "tasks": tasks if tasks is not None else [_task()]}


class HasArtifactTests(unittest.TestCase):
    def test_none(self):
        self.assertFalse(has_artifact(NO_ARTIFACT))

    def test_branch_only(self):
        self.assertTrue(has_artifact({"branch_pushed": True}))

    def test_pr_only(self):
        self.assertTrue(has_artifact({"pr_opened": True}))

    def test_commits_only(self):
        self.assertTrue(has_artifact({"commits": 1}))

    def test_dirty_worktree_is_not_an_artifact(self):
        # A dirty worktree is the throttle signal, not forward-progress evidence.
        self.assertFalse(has_artifact(NO_ARTIFACT))


class HasPendingWorkTests(unittest.TestCase):
    def test_dirty_worktree(self):
        self.assertTrue(has_pending_work({"worktree_dirty": True, "artifacts": {}}))

    def test_branch_pushed_no_pr(self):
        self.assertTrue(
            has_pending_work({"artifacts": {"branch_pushed": True, "pr_opened": False}})
        )

    def test_committed_not_pushed(self):
        self.assertTrue(has_pending_work({"artifacts": {"commits": 2, "branch_pushed": False}}))

    def test_clean_pr_open_is_not_pending(self):
        self.assertFalse(
            has_pending_work(
                {"artifacts": {"branch_pushed": True, "pr_opened": True, "commits": 3}}
            )
        )

    def test_nothing_started_is_not_pending(self):
        # Zero-artifact + clean worktree is Part (b)'s domain, not throttle's.
        self.assertFalse(has_pending_work({"artifacts": NO_ARTIFACT}))


class TaskExistsForTests(unittest.TestCase):
    def test_match(self):
        self.assertTrue(task_exists_for(_impl(), [_task()]))

    def test_owner_mismatch(self):
        self.assertFalse(task_exists_for(_impl(), [_task(owner="Aino Virtanen")]))

    def test_ref_mismatch(self):
        self.assertFalse(task_exists_for(_impl(), [_task(subject="main#999 — something else")]))

    def test_case_and_space_insensitive_owner(self):
        self.assertTrue(
            task_exists_for(_impl(name="nadia   khoury"), [_task(owner="Nadia Khoury")])
        )

    def test_deleted_task_does_not_count(self):
        self.assertFalse(task_exists_for(_impl(), [_task(status="deleted")]))

    def test_completed_task_counts_as_created(self):
        # The rule asserts the TaskCreate happened, not that it is still open.
        self.assertTrue(task_exists_for(_impl(), [_task(status="completed")]))

    def test_empty_ledger(self):
        self.assertFalse(task_exists_for(_impl(), []))


class EvaluateLiveTests(unittest.TestCase):
    def test_fully_live_no_findings(self):
        report = evaluate(_snap([_impl()]))
        self.assertTrue(report.ok())
        self.assertEqual(report.findings, [])
        self.assertEqual(report.checked, ["Nadia Khoury"])

    def test_idle_but_has_artifact_and_no_pending_work_is_live(self):
        # Idle after a clean handoff (PR open) is not a stall.
        report = evaluate(_snap([_impl(idle_minutes=120, idle_notifications=3)]))
        self.assertTrue(report.ok())


class MissingTaskTests(unittest.TestCase):
    def test_missing_task_flagged(self):
        report = evaluate(_snap([_impl()], tasks=[]))
        rules = [f.rule for f in report.findings]
        self.assertIn("missing-task", rules)
        self.assertFalse(report.ok())

    def test_missing_task_action_and_severity(self):
        report = evaluate(_snap([_impl()], tasks=[]))
        f = next(f for f in report.findings if f.rule == "missing-task")
        self.assertEqual(f.action, "recreate-task")
        self.assertEqual(f.severity, "moderate")


class ZeroArtifactTests(unittest.TestCase):
    def test_one_idle_notification_reprobe(self):
        report = evaluate(_snap([_impl(artifacts=NO_ARTIFACT, idle_notifications=1)]))
        f = next(f for f in report.findings if f.rule == "zero-artifact")
        self.assertEqual(f.action, "reprobe")
        self.assertEqual(f.severity, "low")

    def test_two_idle_notifications_auto_flag(self):
        # The P5W2 #1024 / P5W3 #1038 shape: 2nd zero-artifact idle = stall.
        report = evaluate(_snap([_impl(artifacts=NO_ARTIFACT, idle_notifications=2)]))
        f = next(f for f in report.findings if f.rule == "zero-artifact")
        self.assertEqual(f.action, "auto-flag-takeover")
        self.assertEqual(f.severity, "moderate")

    def test_zero_notifications_no_zero_artifact_finding(self):
        report = evaluate(_snap([_impl(artifacts=NO_ARTIFACT, idle_notifications=0)]))
        self.assertNotIn("zero-artifact", [f.rule for f in report.findings])

    def test_threshold_constant(self):
        self.assertEqual(IDLE_NOTIFICATION_FLAG_THRESHOLD, 2)

    def test_artifact_present_suppresses_finding(self):
        report = evaluate(_snap([_impl(artifacts={"commits": 1}, idle_notifications=5)]))
        self.assertNotIn("zero-artifact", [f.rule for f in report.findings])


class ThrottleStallTests(unittest.TestCase):
    def _throttle_finding(self, idle_minutes):
        report = evaluate(
            _snap(
                [
                    _impl(
                        worktree_dirty=True,
                        artifacts=NO_ARTIFACT,
                        idle_minutes=idle_minutes,
                        idle_notifications=0,
                    )
                ]
            )
        )
        return [f for f in report.findings if f.rule == "throttle-stall"]

    def test_below_first_threshold_no_finding(self):
        self.assertEqual(self._throttle_finding(THROTTLE_FIRST_PING_MIN - 1), [])

    def test_first_ping_at_30(self):
        fs = self._throttle_finding(THROTTLE_FIRST_PING_MIN)
        self.assertEqual(fs[0].action, "first-ping")
        self.assertEqual(fs[0].severity, "low")

    def test_second_ping_at_45(self):
        fs = self._throttle_finding(THROTTLE_SECOND_PING_MIN)
        self.assertEqual(fs[0].action, "second-ping")
        self.assertEqual(fs[0].severity, "moderate")

    def test_takeover_at_60(self):
        fs = self._throttle_finding(THROTTLE_TAKEOVER_MIN)
        self.assertEqual(fs[0].action, "auto-takeover")
        self.assertEqual(fs[0].severity, "high")

    def test_takeover_well_past_60(self):
        # W12 ig#931: 9h37m undetected -> auto-takeover.
        fs = self._throttle_finding(577)
        self.assertEqual(fs[0].action, "auto-takeover")

    def test_no_throttle_without_pending_work(self):
        # Idle a long time but clean handoff (no pending work) — not a throttle.
        report = evaluate(_snap([_impl(idle_minutes=300, worktree_dirty=False)]))
        self.assertEqual([f for f in report.findings if f.rule == "throttle-stall"], [])


class ComplementaryOverlapTests(unittest.TestCase):
    def test_dirty_zero_artifact_fires_both_rules(self):
        # A dirty worktree with no commit AND 2 idle notifications is both a
        # zero-artifact stall (notification-driven) and a throttle-stall
        # (time-driven). The charter calls these complementary.
        report = evaluate(
            _snap(
                [
                    _impl(
                        artifacts=NO_ARTIFACT,
                        worktree_dirty=True,
                        idle_notifications=2,
                        idle_minutes=70,
                    )
                ]
            )
        )
        rules = {f.rule for f in report.findings}
        self.assertIn("zero-artifact", rules)
        self.assertIn("throttle-stall", rules)


class ReviewerExclusionTests(unittest.TestCase):
    def test_reviewer_excluded_from_all_checks(self):
        report = evaluate(
            _snap(
                [
                    _impl(
                        name="Aino Virtanen",
                        role="reviewer",
                        artifacts=NO_ARTIFACT,
                        worktree_dirty=True,
                        idle_notifications=5,
                        idle_minutes=300,
                    )
                ],
                tasks=[],
            )
        )
        self.assertTrue(report.ok())
        self.assertEqual(report.excluded, ["Aino Virtanen"])
        self.assertEqual(report.checked, [])

    def test_role_defaults_to_implementer(self):
        impl = _impl(artifacts=NO_ARTIFACT, idle_notifications=2)
        del impl["role"]
        report = evaluate(_snap([impl]))
        self.assertFalse(report.ok())
        self.assertEqual(report.checked, ["Nadia Khoury"])


class SnapshotValidationTests(unittest.TestCase):
    def test_non_object_snapshot(self):
        with self.assertRaises(SnapshotError):
            evaluate([])  # type: ignore[arg-type]

    def test_implementers_not_a_list(self):
        with self.assertRaises(SnapshotError):
            evaluate({"implementers": {}, "tasks": []})

    def test_implementer_missing_name(self):
        with self.assertRaises(SnapshotError):
            evaluate({"implementers": [{"issue_ref": "x"}], "tasks": []})

    def test_missing_keys_default_empty(self):
        # An empty snapshot is valid and trivially clean.
        report = evaluate({})
        self.assertTrue(report.ok())


class CliTests(unittest.TestCase):
    def _run(self, snapshot, extra=None):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(snapshot, fh)
            path = fh.name
        try:
            return main([path, *(extra or [])])
        finally:
            Path(path).unlink()

    def test_exit_zero_when_live(self):
        self.assertEqual(self._run(_snap([_impl()])), 0)

    def test_exit_one_on_finding(self):
        self.assertEqual(self._run(_snap([_impl(artifacts=NO_ARTIFACT, idle_notifications=2)])), 1)

    def test_exit_two_on_bad_json(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            fh.write("{not json")
            path = fh.name
        try:
            self.assertEqual(main([path]), 2)
        finally:
            Path(path).unlink()

    def test_exit_two_on_missing_file(self):
        self.assertEqual(main(["/nonexistent/snapshot.json"]), 2)

    def test_json_output(self):
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            rc = self._run(
                _snap([_impl(artifacts=NO_ARTIFACT, idle_notifications=2)]),
                extra=["--json"],
            )
        self.assertEqual(rc, 1)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["findings"][0]["rule"], "zero-artifact")

    def test_stdin_input(self):
        snap = json.dumps(_snap([_impl()]))
        with mock.patch("sys.stdin", io.StringIO(snap)):
            self.assertEqual(main([]), 0)


class FindingShapeTests(unittest.TestCase):
    def test_finding_is_frozen_dataclass(self):
        f = Finding("n", "r", "rule", "act", "low", "d")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            f.severity = "high"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
