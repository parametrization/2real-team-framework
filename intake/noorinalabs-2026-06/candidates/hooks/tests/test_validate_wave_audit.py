#!/usr/bin/env python3
"""Tests for validate_wave_audit hook (Hook 17, issue #195).

Covers the W8 hook-authorship-spec requirement: NEGATIVE MATCH coverage.
Each test documents which negative-space case it guards against.

Run: python3 -m pytest .claude/hooks/tests/test_validate_wave_audit.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_HOOKS_DIR = _HERE.parent
sys.path.insert(0, str(_HOOKS_DIR))

import validate_wave_audit as hook  # noqa: E402


def _skill_input(skill_name: str, args: str = "") -> dict:
    """Build a hook input dict for a Skill call."""
    return {
        "tool_name": "Skill",
        "tool_input": {"skill": skill_name, "args": args},
    }


def _bash_input(command: str) -> dict:
    """Build a hook input dict for a Bash call (for matcher-scoping tests)."""
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def _patch_audit(total: int | None, per_repo: dict[str, int] | None = None):
    """Context manager: patch hook._audit_open_count to return a fixed value."""
    if per_repo is None:
        per_repo = {}
    return mock.patch.object(hook, "_audit_open_count", return_value=(total, per_repo))


def _patch_label(label: str | None):
    """Context manager: patch hook._read_current_wave_labels.

    Accepts a single label for call-site brevity and wraps it in the
    list the hook now returns (#810 dual-form). `None` passes through to
    model the no-active-wave / underivable case.
    """
    labels = None if label is None else [label]
    return mock.patch.object(hook, "_read_current_wave_labels", return_value=labels)


class GatedSkillBlocking(unittest.TestCase):
    """POS — gated skills with open items and no carry-forward → block."""

    def test_wave_wrapup_with_open_items_blocks(self) -> None:
        """POS: /wave-wrapup with open items, no carry-forward → block."""
        with _patch_label("p2-wave-10"), _patch_audit(5, {"noorinalabs-deploy": 5}):
            result = hook.check(_skill_input("wave-wrapup"))
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("p2-wave-10", result["reason"])
        self.assertIn("5", result["reason"])
        self.assertIn("noorinalabs-deploy", result["reason"])

    def test_wave_retro_with_open_items_blocks(self) -> None:
        """POS: /wave-retro is also gated."""
        with _patch_label("p2-wave-10"), _patch_audit(3, {"noorinalabs-main": 3}):
            result = hook.check(_skill_input("wave-retro"))
        assert result is not None
        self.assertEqual(result["decision"], "block")

    def test_handoff_with_open_items_blocks(self) -> None:
        """POS: /handoff is also gated."""
        with _patch_label("p2-wave-10"), _patch_audit(1, {"noorinalabs-isnad-graph": 1}):
            result = hook.check(_skill_input("handoff"))
        assert result is not None
        self.assertEqual(result["decision"], "block")


class CarryForwardWarnsButAllows(unittest.TestCase):
    """POS — gated skills with open items but carry-forward in args → allow with warning."""

    def test_inline_marker_allows(self) -> None:
        """POS: 'Carry-forward: #N → next-wave' inline marker passes."""
        args = "Wave-10 wrapup. Carry-forward: #194 → wave-11, #845 → backlog"
        with _patch_label("p2-wave-10"), _patch_audit(2, {"noorinalabs-main": 2}):
            result = hook.check(_skill_input("wave-wrapup", args=args))
        assert result is not None
        self.assertEqual(result["decision"], "allow")
        self.assertIn("carry-forward marker detected", result["systemMessage"])

    def test_heading_marker_allows(self) -> None:
        """POS: '## Carry-forward' markdown heading passes."""
        args = "## Carry-forward\n\n- #194 → next wave\n- #845 → backlog"
        with _patch_label("p2-wave-10"), _patch_audit(2, {"noorinalabs-main": 2}):
            result = hook.check(_skill_input("wave-wrapup", args=args))
        assert result is not None
        self.assertEqual(result["decision"], "allow")

    def test_arrow_pattern_allows(self) -> None:
        """POS: bare '#N → destination' arrow pattern passes."""
        args = "Items: #194 → wave-11. #845 → backlog. Done."
        with _patch_label("p2-wave-10"), _patch_audit(2, {"noorinalabs-main": 2}):
            result = hook.check(_skill_input("wave-wrapup", args=args))
        assert result is not None
        self.assertEqual(result["decision"], "allow")


class NegativeMatchScoping(unittest.TestCase):
    """NEG — inputs that look like matches but are intentionally excluded."""

    def test_non_gated_skill_does_not_block(self) -> None:
        """NEG: /ontology-librarian is not gated — must allow without audit."""
        with _patch_label("p2-wave-10"), _patch_audit(99, {"noorinalabs-main": 99}):
            result = hook.check(_skill_input("ontology-librarian"))
        self.assertIsNone(result)

    def test_session_start_does_not_block(self) -> None:
        """NEG: /session-start is not gated."""
        with _patch_label("p2-wave-10"), _patch_audit(99, {"noorinalabs-main": 99}):
            result = hook.check(_skill_input("session-start"))
        self.assertIsNone(result)

    def test_bash_with_wave_wrapup_substring_does_not_block(self) -> None:
        """NEG: Bash containing 'wave-wrapup' as substring (substring-bug guard, kin of #216).

        The hook fires on `tool_name == "Skill"` only. A bash invocation
        like `echo "running wave-wrapup later"` MUST NOT trigger.
        """
        result = hook.check(_bash_input('echo "running wave-wrapup later"'))
        self.assertIsNone(result)

    def test_bash_with_handoff_substring_does_not_block(self) -> None:
        """NEG: Bash containing 'handoff' as substring."""
        result = hook.check(_bash_input("git log --grep handoff"))
        self.assertIsNone(result)

    def test_zero_open_items_allows(self) -> None:
        """NEG: gated skill with 0 open items → allow without warning."""
        with _patch_label("p2-wave-10"), _patch_audit(0, {}):
            result = hook.check(_skill_input("wave-wrapup"))
        self.assertIsNone(result)


class FailOpenInfrastructure(unittest.TestCase):
    """NEG — infrastructure failures fail OPEN with system warning, never block."""

    def test_no_active_wave_allows(self) -> None:
        """NEG: cross-repo-status.json has wave_active=false → allow with warning."""
        with _patch_label(None):
            result = hook.check(_skill_input("wave-wrapup"))
        assert result is not None
        self.assertEqual(result["decision"], "allow")
        self.assertIn("could not determine an active wave label", result["systemMessage"])

    def test_audit_total_failure_allows(self) -> None:
        """NEG: every gh call failed (gh missing / no auth) → allow with warning."""
        with _patch_label("p2-wave-10"), _patch_audit(None, {}):
            result = hook.check(_skill_input("wave-wrapup"))
        assert result is not None
        self.assertEqual(result["decision"], "allow")
        self.assertIn("could not query any of", result["systemMessage"])


class WaveLabelDerivation(unittest.TestCase):
    """Coverage on _read_current_wave_labels (#810 dual-form)."""

    def _write_status(self, payload: dict) -> Path:
        """Write a temp cross-repo-status.json and patch hook._STATUS_PATH at it."""
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(payload, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_phase2_wave10_derives_both_forms(self) -> None:
        """Returns BOTH the legacy p{N}-wave-{M} AND the new wave-{X} form (#810).

        Phase comes from the authoritative `current_phase` integer (#831).
        """
        path = self._write_status(
            {"wave_active": True, "current_wave": "wave-10", "current_phase": 2}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertEqual(hook._read_current_wave_labels(), ["p2-wave-10", "wave-10"])
        finally:
            path.unlink()

    def test_current_phase_wins_over_stale_phase_string(self) -> None:
        """#831 regression: the live `current_phase` integer is authoritative;
        a stale top-level `phase` string (the never-advanced phase-4 legacy
        field) must be IGNORED for label derivation."""
        path = self._write_status(
            {
                "wave_active": True,
                "current_wave": "wave-17",
                "current_phase": 6,
                "phase": "phase-4",  # stale legacy field — must not win
            }
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertEqual(hook._read_current_wave_labels(), ["p6-wave-17", "wave-17"])
        finally:
            path.unlink()

    def test_legacy_phase_string_fallback(self) -> None:
        """Defensive fallback: when `current_phase` is absent, the legacy
        `phase` ("phase-{N}") string still resolves (robustness)."""
        path = self._write_status(
            {"wave_active": True, "current_wave": "wave-10", "phase": "phase-2"}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertEqual(hook._read_current_wave_labels(), ["p2-wave-10", "wave-10"])
        finally:
            path.unlink()

    def test_inactive_wave_returns_none(self) -> None:
        path = self._write_status(
            {"wave_active": False, "current_wave": "wave-10", "current_phase": 2}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertIsNone(hook._read_current_wave_labels())
        finally:
            path.unlink()

    def test_missing_file_returns_none(self) -> None:
        with mock.patch.object(hook, "_STATUS_PATH", Path("/tmp/nonexistent-no-thanks.json")):
            self.assertIsNone(hook._read_current_wave_labels())

    def test_malformed_current_wave_returns_none(self) -> None:
        path = self._write_status(
            {"wave_active": True, "current_wave": "not-a-wave", "current_phase": 2}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertIsNone(hook._read_current_wave_labels())
        finally:
            path.unlink()

    def test_missing_both_phase_fields_returns_none(self) -> None:
        """No `current_phase` AND no `phase` → phase unresolvable → None."""
        path = self._write_status({"wave_active": True, "current_wave": "wave-10"})
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertIsNone(hook._read_current_wave_labels())
        finally:
            path.unlink()


class CarryForwardDetection(unittest.TestCase):
    """Coverage on _has_carry_forward — the bypass surface needs to be precise."""

    def test_inline_carry_forward_colon_matches(self) -> None:
        self.assertTrue(hook._has_carry_forward("foo Carry-forward: #1 → backlog"))

    def test_carry_space_forward_matches(self) -> None:
        self.assertTrue(hook._has_carry_forward("Carry forward: #1 → backlog"))

    def test_case_insensitive(self) -> None:
        self.assertTrue(hook._has_carry_forward("CARRY-FORWARD: items"))

    def test_heading_marker_matches(self) -> None:
        self.assertTrue(hook._has_carry_forward("# Wrapup\n\n## Carry-forward\n- #1"))

    def test_arrow_pattern_matches(self) -> None:
        self.assertTrue(hook._has_carry_forward("Items: #194 → wave-11"))

    def test_arrow_with_ascii_arrow_matches(self) -> None:
        self.assertTrue(hook._has_carry_forward("Items: #194 -> wave-11"))

    def test_no_marker_does_not_match(self) -> None:
        """NEG: prose mentioning carry-forward concept without the structured marker."""
        self.assertFalse(hook._has_carry_forward("we are going to carry these forward eventually"))

    def test_empty_args_does_not_match(self) -> None:
        self.assertFalse(hook._has_carry_forward(""))

    def test_unrelated_arrows_do_not_falsely_match(self) -> None:
        """NEG: '#123 -> 456' without word destination does not falsely match."""
        # The pattern requires \w after the arrow — bare numbers should not.
        # This guards against accidental matches in numeric diffs.
        self.assertFalse(hook._has_carry_forward("count: #123 -> 456"))


class WaveBranchDerivation(unittest.TestCase):
    """Coverage on _read_current_wave_branch (#664 exemption target)."""

    def _write_status(self, payload: dict) -> Path:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(payload, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_phase5_wave5_derives_branch(self) -> None:
        path = self._write_status(
            {"wave_active": True, "current_wave": "wave-5", "current_phase": 5}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertEqual(hook._read_current_wave_branch(), "deployments/phase-5/wave-5")
        finally:
            path.unlink()

    def test_branch_uses_current_phase_not_stale_phase_string(self) -> None:
        """#831 core regression: branch derivation must read the authoritative
        `current_phase` (6), NOT the stale top-level `phase` ("phase-4"). The
        bug derived `deployments/phase-4/...`; the fix derives phase-6."""
        path = self._write_status(
            {
                "wave_active": True,
                "current_wave": "wave-17",
                "current_phase": 6,
                "phase": "phase-4",  # stale legacy field — must not win
            }
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertEqual(hook._read_current_wave_branch(), "deployments/phase-6/wave-17")
        finally:
            path.unlink()

    def test_inactive_wave_returns_none(self) -> None:
        path = self._write_status(
            {"wave_active": False, "current_wave": "wave-5", "current_phase": 5}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertIsNone(hook._read_current_wave_branch())
        finally:
            path.unlink()

    def test_missing_file_returns_none(self) -> None:
        with mock.patch.object(hook, "_STATUS_PATH", Path("/tmp/nope-664.json")):
            self.assertIsNone(hook._read_current_wave_branch())

    def test_label_and_branch_share_phase_wave(self) -> None:
        """Label and branch must derive from the SAME phase/wave (no drift)."""
        path = self._write_status(
            {"wave_active": True, "current_wave": "wave-12", "current_phase": 3}
        )
        try:
            with mock.patch.object(hook, "_STATUS_PATH", path):
                self.assertEqual(hook._read_current_wave_labels(), ["p3-wave-12", "wave-12"])
                self.assertEqual(hook._read_current_wave_branch(), "deployments/phase-3/wave-12")
        finally:
            path.unlink()


class PhaseNumDerivation(unittest.TestCase):
    """Direct coverage on _read_phase_num — the authoritative phase reader (#831)."""

    def test_current_phase_int_preferred(self) -> None:
        self.assertEqual(hook._read_phase_num({"current_phase": 6, "phase": "phase-4"}), 6)

    def test_current_phase_string_coerced(self) -> None:
        """A stringified `current_phase` ("6") still coerces to int."""
        self.assertEqual(hook._read_phase_num({"current_phase": "6"}), 6)

    def test_falls_back_to_phase_string(self) -> None:
        self.assertEqual(hook._read_phase_num({"phase": "phase-2"}), 2)

    def test_unparseable_current_phase_falls_back_to_phase_string(self) -> None:
        self.assertEqual(hook._read_phase_num({"current_phase": "n/a", "phase": "phase-7"}), 7)

    def test_neither_field_returns_none(self) -> None:
        self.assertIsNone(hook._read_phase_num({}))

    def test_malformed_phase_string_returns_none(self) -> None:
        self.assertIsNone(hook._read_phase_num({"phase": "phase-x"}))


class ChecksGreen(unittest.TestCase):
    """Coverage on _checks_green — the green-CI half of merge-ready (#664)."""

    def test_empty_rollup_is_green(self) -> None:
        """No checks configured → green (linkage + base guards carry safety)."""
        self.assertTrue(hook._checks_green([]))
        self.assertTrue(hook._checks_green(None))

    def test_all_success_checkruns_green(self) -> None:
        rollup = [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
            {"status": "COMPLETED", "conclusion": "SKIPPED"},
            {"status": "COMPLETED", "conclusion": "NEUTRAL"},
        ]
        self.assertTrue(hook._checks_green(rollup))

    def test_failing_checkrun_not_green(self) -> None:
        rollup = [
            {"status": "COMPLETED", "conclusion": "SUCCESS"},
            {"status": "COMPLETED", "conclusion": "FAILURE"},
        ]
        self.assertFalse(hook._checks_green(rollup))

    def test_pending_checkrun_not_green(self) -> None:
        """NEG: an in-progress check is NOT green (conservative — no false-exempt)."""
        rollup = [{"status": "IN_PROGRESS", "conclusion": ""}]
        self.assertFalse(hook._checks_green(rollup))

    def test_statuscontext_success_green(self) -> None:
        self.assertTrue(hook._checks_green([{"state": "SUCCESS"}]))

    def test_statuscontext_pending_not_green(self) -> None:
        self.assertFalse(hook._checks_green([{"state": "PENDING"}]))

    def test_statuscontext_failure_not_green(self) -> None:
        self.assertFalse(hook._checks_green([{"state": "ERROR"}]))

    def test_unrecognized_shape_not_green(self) -> None:
        """NEG: a shape with neither conclusion/status nor state → not green."""
        self.assertFalse(hook._checks_green([{"weird": "value"}]))

    def test_non_dict_element_not_green(self) -> None:
        self.assertFalse(hook._checks_green(["not-a-dict"]))


class PrIsMergeReady(unittest.TestCase):
    """Coverage on _pr_is_merge_ready — the false-exempt guard (#664 acc. #3)."""

    _WAVE = "deployments/phase-5/wave-5"

    def _pr(self, **overrides) -> dict:
        pr = {
            "number": 700,
            "isDraft": False,
            "state": "OPEN",
            "baseRefName": self._WAVE,
            "mergeable": "MERGEABLE",
            "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
        }
        pr.update(overrides)
        return pr

    def test_ready_pr_is_ready(self) -> None:
        self.assertTrue(hook._pr_is_merge_ready(self._pr(), self._WAVE))

    def test_draft_not_ready(self) -> None:
        self.assertFalse(hook._pr_is_merge_ready(self._pr(isDraft=True), self._WAVE))

    def test_wrong_base_not_ready(self) -> None:
        """NEG: a PR into main (not the wave branch) must NOT exempt — acc. #3."""
        self.assertFalse(hook._pr_is_merge_ready(self._pr(baseRefName="main"), self._WAVE))

    def test_conflicting_not_ready(self) -> None:
        self.assertFalse(hook._pr_is_merge_ready(self._pr(mergeable="CONFLICTING"), self._WAVE))

    def test_unknown_mergeable_not_ready(self) -> None:
        """NEG: UNKNOWN (GitHub still computing) is conservatively not-ready."""
        self.assertFalse(hook._pr_is_merge_ready(self._pr(mergeable="UNKNOWN"), self._WAVE))

    def test_red_checks_not_ready(self) -> None:
        self.assertFalse(
            hook._pr_is_merge_ready(
                self._pr(statusCheckRollup=[{"status": "COMPLETED", "conclusion": "FAILURE"}]),
                self._WAVE,
            )
        )

    def test_closed_state_not_ready(self) -> None:
        self.assertFalse(hook._pr_is_merge_ready(self._pr(state="MERGED"), self._WAVE))


class CountOpenWithExemption(unittest.TestCase):
    """Coverage on _count_open_for_repo merge-ready-PR exemption (#664)."""

    _LABELS = ["p5-wave-5", "wave-5"]

    def test_no_open_issues_returns_zero(self) -> None:
        with mock.patch.object(hook, "_open_issue_numbers_for_repo", return_value=[]):
            self.assertEqual(
                hook._count_open_for_repo(
                    "noorinalabs-main", self._LABELS, "deployments/phase-5/wave-5"
                ),
                0,
            )

    def test_issue_list_failure_returns_none(self) -> None:
        """NEG: issue-list subprocess failure → None (caller fails open)."""
        with mock.patch.object(hook, "_open_issue_numbers_for_repo", return_value=None):
            self.assertIsNone(
                hook._count_open_for_repo(
                    "noorinalabs-main", self._LABELS, "deployments/phase-5/wave-5"
                )
            )

    def test_no_wave_branch_counts_all(self) -> None:
        """NEG: branch underivable → no exemption applied, every issue counts."""
        with mock.patch.object(hook, "_open_issue_numbers_for_repo", return_value=[1, 2, 3]):
            self.assertEqual(hook._count_open_for_repo("noorinalabs-main", self._LABELS, None), 3)

    def test_exempt_issues_subtracted(self) -> None:
        """POS: issues with a merge-ready wave-branch PR are subtracted."""
        with (
            mock.patch.object(hook, "_open_issue_numbers_for_repo", return_value=[10, 11, 12]),
            mock.patch.object(hook, "_mergeready_exempt_issues", return_value={11, 12}),
        ):
            self.assertEqual(
                hook._count_open_for_repo(
                    "noorinalabs-main", self._LABELS, "deployments/phase-5/wave-5"
                ),
                1,
            )

    def test_all_exempt_returns_zero(self) -> None:
        """POS: every open issue exempt → 0 (the wrapup chicken-and-egg fix)."""
        with (
            mock.patch.object(hook, "_open_issue_numbers_for_repo", return_value=[10, 11]),
            mock.patch.object(hook, "_mergeready_exempt_issues", return_value={10, 11}),
        ):
            self.assertEqual(
                hook._count_open_for_repo(
                    "noorinalabs-main", self._LABELS, "deployments/phase-5/wave-5"
                ),
                0,
            )

    def test_exempt_set_failure_counts_all(self) -> None:
        """NEG: PR-list failure → empty exempt set → all issues count (fail strict)."""
        with (
            mock.patch.object(hook, "_open_issue_numbers_for_repo", return_value=[10, 11]),
            mock.patch.object(hook, "_mergeready_exempt_issues", return_value=set()),
        ):
            self.assertEqual(
                hook._count_open_for_repo(
                    "noorinalabs-main", self._LABELS, "deployments/phase-5/wave-5"
                ),
                2,
            )


class ClosingRefsInText(unittest.TestCase):
    """Coverage on _closing_refs_in_text — PR-body/title linkage parse (#664).

    Linkage is parsed from body/title because GitHub's structured
    closingIssuesReferences is always empty for wave-branch-based PRs (it only
    populates for default-branch PRs).
    """

    def test_closes_matches(self) -> None:
        self.assertEqual(hook._closing_refs_in_text("Closes #664."), {664})

    def test_keyword_conjugations_match(self) -> None:
        for text in (
            "close #1",
            "closed #1",
            "Fixes #1",
            "fix #1",
            "fixed #1",
            "Resolves #1",
            "resolved #1",
        ):
            with self.subTest(text=text):
                self.assertEqual(hook._closing_refs_in_text(text), {1})

    def test_colon_separator_matches(self) -> None:
        self.assertEqual(hook._closing_refs_in_text("Closes: #5"), {5})

    def test_multiple_refs_collected(self) -> None:
        text = "Closes #1\nbody\nFixes #2 and resolves #3"
        self.assertEqual(hook._closing_refs_in_text(text), {1, 2, 3})

    def test_bare_mention_does_not_match(self) -> None:
        """NEG: a passing '#664' mention without a keyword must NOT exempt (acc. #3)."""
        self.assertEqual(hook._closing_refs_in_text("see #664 for context"), set())

    def test_cross_repo_ref_not_matched(self) -> None:
        """NEG: 'Closes octo/repo#5' is a different repo's issue — not local."""
        self.assertEqual(hook._closing_refs_in_text("Closes octo/repo#5"), set())

    def test_prefix_word_not_matched(self) -> None:
        """NEG: 'prefix #5' must not match the 'fix' substring."""
        self.assertEqual(hook._closing_refs_in_text("prefix #5"), set())

    def test_no_separator_not_matched(self) -> None:
        """NEG: GitHub requires whitespace/colon; 'Closes#5' does not link."""
        self.assertEqual(hook._closing_refs_in_text("Closes#5"), set())

    def test_empty_text(self) -> None:
        self.assertEqual(hook._closing_refs_in_text(""), set())


class MergereadyExemptIssuesSubprocess(unittest.TestCase):
    """Coverage on _mergeready_exempt_issues gh shell-out + body-linkage parse."""

    _WAVE = "deployments/phase-5/wave-5"

    def _completed(self, stdout: str, returncode: int = 0):
        m = mock.Mock()
        m.stdout = stdout
        m.returncode = returncode
        return m

    def _ready_pr(self, number: int, body: str = "", title: str = "") -> dict:
        return {
            "number": number,
            "isDraft": False,
            "state": "OPEN",
            "baseRefName": self._WAVE,
            "mergeable": "MERGEABLE",
            "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
            "body": body,
            "title": title,
        }

    def test_collects_declared_closes_of_ready_prs(self) -> None:
        """POS: a ready PR's body closing-keyword refs become the exempt set."""
        prs = json.dumps([self._ready_pr(700, body="Fix.\n\nCloses #42\nFixes #43")])
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed(prs)):
            result = hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE)
        self.assertEqual(result, {42, 43})

    def test_title_ref_also_collected(self) -> None:
        """POS: a closing keyword in the title also links."""
        prs = json.dumps([self._ready_pr(700, body="no refs", title="thing (resolves #44)")])
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed(prs)):
            result = hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE)
        self.assertEqual(result, {44})

    def test_not_ready_pr_links_ignored(self) -> None:
        """NEG: a draft PR's closing refs never become exempt."""
        draft = self._ready_pr(701, body="Closes #50")
        draft["isDraft"] = True
        prs = json.dumps([draft])
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed(prs)):
            result = hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE)
        self.assertEqual(result, set())

    def test_bare_mention_in_ready_pr_not_exempt(self) -> None:
        """NEG: a ready PR that only *mentions* #50 (no keyword) does not exempt it."""
        prs = json.dumps([self._ready_pr(700, body="related to #50 but does other work")])
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed(prs)):
            result = hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE)
        self.assertEqual(result, set())

    def test_pr_list_failure_returns_empty_set(self) -> None:
        """NEG: gh pr list nonzero exit → empty set (fail strict, no false-exempt)."""
        with mock.patch.object(
            hook.subprocess, "run", return_value=self._completed("", returncode=1)
        ):
            self.assertEqual(hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE), set())

    def test_pr_list_filenotfound_returns_empty_set(self) -> None:
        with mock.patch.object(hook.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE), set())

    def test_pr_list_malformed_json_returns_empty_set(self) -> None:
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed("not json")):
            self.assertEqual(hook._mergeready_exempt_issues("noorinalabs-main", self._WAVE), set())


class OpenIssueNumbersForLabelSubprocess(unittest.TestCase):
    """Coverage on _open_issue_numbers_for_label gh shell-out (per single label)."""

    def _completed(self, stdout: str, returncode: int = 0):
        m = mock.Mock()
        m.stdout = stdout
        m.returncode = returncode
        return m

    def test_parses_numbers(self) -> None:
        payload = json.dumps([{"number": 1}, {"number": 2}, {"number": 3}])
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed(payload)):
            self.assertEqual(
                hook._open_issue_numbers_for_label("noorinalabs-main", "p5-wave-5"),
                [1, 2, 3],
            )

    def test_empty_output_is_empty_list(self) -> None:
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed("")):
            self.assertEqual(
                hook._open_issue_numbers_for_label("noorinalabs-main", "p5-wave-5"), []
            )

    def test_failure_returns_none(self) -> None:
        with mock.patch.object(
            hook.subprocess, "run", return_value=self._completed("", returncode=1)
        ):
            self.assertIsNone(hook._open_issue_numbers_for_label("noorinalabs-main", "p5-wave-5"))

    def test_malformed_json_returns_none(self) -> None:
        with mock.patch.object(hook.subprocess, "run", return_value=self._completed("nope")):
            self.assertIsNone(hook._open_issue_numbers_for_label("noorinalabs-main", "p5-wave-5"))


class OpenIssueNumbersUnion(unittest.TestCase):
    """Coverage on _open_issue_numbers_for_repo dual-form UNION (#810)."""

    def test_unions_across_label_forms_dedup(self) -> None:
        """POS: legacy + new label results are unioned and deduplicated."""

        def _per_label(repo, label):
            return {"p5-wave-5": [10, 11], "wave-5": [11, 12]}[label]

        with mock.patch.object(hook, "_open_issue_numbers_for_label", side_effect=_per_label):
            self.assertEqual(
                hook._open_issue_numbers_for_repo("noorinalabs-main", ["p5-wave-5", "wave-5"]),
                [10, 11, 12],
            )

    def test_any_label_query_failure_returns_none(self) -> None:
        """NEG: if ANY per-label query fails → None (caller fails open per-repo)."""

        def _per_label(repo, label):
            return [10] if label == "p5-wave-5" else None

        with mock.patch.object(hook, "_open_issue_numbers_for_label", side_effect=_per_label):
            self.assertIsNone(
                hook._open_issue_numbers_for_repo("noorinalabs-main", ["p5-wave-5", "wave-5"])
            )

    def test_new_form_only_issue_counts(self) -> None:
        """POS: an issue carrying ONLY the new wave-{X} form still registers."""

        def _per_label(repo, label):
            return [] if label == "p5-wave-5" else [42]

        with mock.patch.object(hook, "_open_issue_numbers_for_label", side_effect=_per_label):
            self.assertEqual(
                hook._open_issue_numbers_for_repo("noorinalabs-main", ["p5-wave-5", "wave-5"]),
                [42],
            )


class CheckEndToEndExemption(unittest.TestCase):
    """check() integration: a fully-exempt wave allows /wave-wrapup (#664)."""

    def test_all_issues_exempt_allows_wrapup(self) -> None:
        """POS: the only open wave issues have merge-ready wave-branch PRs → allow.

        Exercises the real _audit_open_count → _count_open_for_repo exemption
        path, mocking only the subprocess-touching leaves.
        """

        def _issues(repo, labels):
            return [664] if repo == "noorinalabs-main" else []

        with (
            mock.patch.object(
                hook, "_read_current_wave_labels", return_value=["p5-wave-5", "wave-5"]
            ),
            mock.patch.object(
                hook, "_read_current_wave_branch", return_value="deployments/phase-5/wave-5"
            ),
            mock.patch.object(hook, "_open_issue_numbers_for_repo", side_effect=_issues),
            mock.patch.object(hook, "_mergeready_exempt_issues", return_value={664}),
        ):
            result = hook.check(_skill_input("wave-wrapup"))
        self.assertIsNone(result)

    def test_non_exempt_issue_still_blocks(self) -> None:
        """NEG: an open wave issue WITHOUT a merge-ready PR still blocks wrapup."""

        def _issues(repo, labels):
            return [664] if repo == "noorinalabs-main" else []

        with (
            mock.patch.object(
                hook, "_read_current_wave_labels", return_value=["p5-wave-5", "wave-5"]
            ),
            mock.patch.object(
                hook, "_read_current_wave_branch", return_value="deployments/phase-5/wave-5"
            ),
            mock.patch.object(hook, "_open_issue_numbers_for_repo", side_effect=_issues),
            mock.patch.object(hook, "_mergeready_exempt_issues", return_value=set()),
        ):
            result = hook.check(_skill_input("wave-wrapup"))
        assert result is not None
        self.assertEqual(result["decision"], "block")
        self.assertIn("noorinalabs-main", result["reason"])
        self.assertIn("Open items across the org: 1", result["reason"])


if __name__ == "__main__":
    unittest.main()
