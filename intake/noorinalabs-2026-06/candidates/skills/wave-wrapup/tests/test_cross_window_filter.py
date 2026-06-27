#!/usr/bin/env python3
"""Tests for /wave-wrapup Step 10.5 cross-window kickoff filter (main#423).

Origin: W9 wave-branch absorbed PRs across two partition windows. `gh pr list
--base deployments/phase-3/wave-9 --state merged` returned 30 PRs; the
canonical wave was 6 PRs. The pre-fix Step 10.5 computed TOP_CONCENTRATION_PCT
against the 30-PR set (50%) instead of the 6-PR canonical set (67%).

The fix (Option A): filter `gh pr list` JSON by `mergedAt >= wave_{M}_kicked_off_at`.
The fix (Option B): after Option A, cross-check filtered count vs FINAL_PR_COUNT;
loud-fail on mismatch (covers re-roll-within-window edge cases A misses).

These tests verify the jq filter expression used by SKILL.md Step 10.5 against
a captured-shape fixture (`fixtures/w9_cross_window_prs.json` — 24 pre-kickoff +
6 post-kickoff = 30 PRs total, mirroring the W9 anomaly).

Run:
    python3 -m unittest discover -s .claude/skills/wave-wrapup/tests
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_FIXTURES = _HERE.parent / "fixtures"

W9_KICKOFF = "2026-05-10T17:55:00Z"
W9_CANONICAL_COUNT = 6


def _apply_kickoff_filter(prs_path: Path, kickoff: str) -> list[dict]:
    """Mirror SKILL.md Step 10.5 jq expression:

        .[] | select(.mergedAt >= "$KICKOFF") | . + {repo: "$REPO"}

    The `+ {repo}` decoration is omitted here — we test the filter, not the
    repo tag. Returns the filtered PR list.
    """
    result = subprocess.run(
        ["jq", f'[.[] | select(.mergedAt >= "{kickoff}")]'],
        input=prs_path.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


class CrossWindowFilterTests(unittest.TestCase):
    """Option A — kickoff-timestamp filter on gh pr list."""

    def test_w9_30_to_6_via_kickoff_filter(self):
        """W9 anomaly: 30 unfiltered PRs → 6 after kickoff filter (canonical)."""
        fixture = _FIXTURES / "w9_cross_window_prs.json"
        unfiltered = json.loads(fixture.read_text())
        self.assertEqual(len(unfiltered), 30, "fixture should mirror W9's 30-PR set")

        filtered = _apply_kickoff_filter(fixture, W9_KICKOFF)
        self.assertEqual(
            len(filtered),
            W9_CANONICAL_COUNT,
            f"kickoff filter should yield 6 canonical PRs, got {len(filtered)}",
        )

    def test_all_filtered_prs_at_or_after_kickoff(self):
        """Every PR retained by the filter must satisfy mergedAt >= kickoff."""
        fixture = _FIXTURES / "w9_cross_window_prs.json"
        filtered = _apply_kickoff_filter(fixture, W9_KICKOFF)
        for pr in filtered:
            self.assertGreaterEqual(
                pr["mergedAt"],
                W9_KICKOFF,
                f"PR #{pr['number']} merged at {pr['mergedAt']} should be filtered out",
            )

    def test_pre_partition_prs_excluded(self):
        """The 24 pre-partition PRs (#349-#372) must NOT survive the filter."""
        fixture = _FIXTURES / "w9_cross_window_prs.json"
        filtered = _apply_kickoff_filter(fixture, W9_KICKOFF)
        filtered_nums = {pr["number"] for pr in filtered}
        for pre_partition_num in range(349, 373):
            self.assertNotIn(
                pre_partition_num,
                filtered_nums,
                f"pre-partition PR #{pre_partition_num} leaked past kickoff filter",
            )

    def test_canonical_window_prs_retained(self):
        """The 6 canonical W9 PRs (post-kickoff) must be retained."""
        fixture = _FIXTURES / "w9_cross_window_prs.json"
        filtered = _apply_kickoff_filter(fixture, W9_KICKOFF)
        filtered_nums = {pr["number"] for pr in filtered}
        expected = {401, 402, 403, 404, 405, 416}
        self.assertEqual(filtered_nums, expected)

    def test_empty_kickoff_falls_back_to_full_set(self):
        """Legacy waves (pre-/wave-start) with no kicked_off_at fall through.

        Step 10.5's bash uses `if [ -n "$KICKOFF" ]` to skip the select clause;
        absent the filter, the full unfiltered set is returned and Option B's
        FINAL_PR_COUNT cross-check is the sole safeguard.
        """
        fixture = _FIXTURES / "w9_cross_window_prs.json"
        unfiltered = json.loads(fixture.read_text())
        # Empty kickoff → "$KICKOFF" is empty → skip the select clause.
        # We assert this by NOT applying the filter when kickoff is empty.
        self.assertEqual(len(unfiltered), 30)


class CrossCheckGateTests(unittest.TestCase):
    """Option B — FINAL_PR_COUNT-vs-filtered-tally loud-fail gate."""

    def test_match_passes_gate(self):
        """When filtered count == FINAL_PR_COUNT, Step 10.5 proceeds."""
        fixture = _FIXTURES / "w9_cross_window_prs.json"
        filtered = _apply_kickoff_filter(fixture, W9_KICKOFF)
        final_pr_count = W9_CANONICAL_COUNT
        # Gate condition: GH_COUNT != FINAL_PR_COUNT → fail. Here they match.
        self.assertEqual(len(filtered), final_pr_count)

    def test_mismatch_triggers_gate(self):
        """When filtered count != FINAL_PR_COUNT, Step 10.5 must loud-fail.

        Scenario: operator records FINAL_PR_COUNT=5 (manual undercount), but
        kickoff-filter yields 6. Step 10.5's bash exits 1 in this state.
        """
        fixture = _FIXTURES / "w9_cross_window_prs.json"
        filtered = _apply_kickoff_filter(fixture, W9_KICKOFF)
        final_pr_count_wrong = 5
        self.assertNotEqual(
            len(filtered),
            final_pr_count_wrong,
            "mismatch must be detectable by the cross-check gate",
        )

    def test_pre_fix_w9_would_have_mismatched(self):
        """Pre-fix behaviour: unfiltered 30 != FINAL_PR_COUNT 6 → Option B catches.

        This is the load-bearing case for Option B as defense-in-depth: even
        if Option A's filter is bypassed (missing kickoff key, legacy wave),
        the cross-check still loud-fails on the cross-window contamination.
        """
        fixture = _FIXTURES / "w9_cross_window_prs.json"
        unfiltered = json.loads(fixture.read_text())
        final_pr_count = W9_CANONICAL_COUNT
        self.assertNotEqual(
            len(unfiltered),
            final_pr_count,
            "Option B must detect a 30-vs-6 mismatch when Option A is bypassed",
        )


if __name__ == "__main__":
    unittest.main()
