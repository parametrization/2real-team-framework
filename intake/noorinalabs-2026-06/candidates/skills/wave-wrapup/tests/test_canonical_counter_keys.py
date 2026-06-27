#!/usr/bin/env python3
"""Smoke test for /wave-wrapup Step 10.5 canonical counter keys (#318).

Pre-#318 /wave-wrapup did not write the canonical top-level counter keys at
all — the orchestrator had to manually add them at retro time (P3W7
`fb459b2`). Step 10.5 of the skill now invokes `upsert_status_keys.py` to
write three keys: `wave_{M}_final_pr_count`, `wave_{M}_changes_requested_cycles`,
`wave_{M}_top_concentration_pct`.

These tests verify:
1. The shared upsert helper handles the three counter keys correctly on a
   `cross-repo-status.json`-shaped fixture (no existing wave_{M}_* keys).
2. The keys are written at top level (NOT nested under wave_{M}_summary.*),
   matching the `/wave-retro` Step 2.5 lookup contract.
3. Sibling keys are preserved unchanged (no truncation, no reorder).
4. A subsequent re-run is idempotent (replace-in-place, not duplicate).

Run: python3 -m unittest discover -s .claude/skills/wave-wrapup/tests
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Reuse the helper from .claude/lib/ — Step 10.5 of /wave-wrapup invokes it.
# Helper promoted from wave-scope/ to lib/ per main#292 (multi-consumer →
# shared lib). From .claude/skills/wave-wrapup/tests/, lib is 3 levels up
# then ../lib (tests → wave-wrapup → skills → .claude → lib).
_HERE = Path(__file__).resolve().parent
_LIB_DIR = _HERE.parent.parent.parent / "lib"
sys.path.insert(0, str(_LIB_DIR))

from upsert_status_keys import upsert_top_level_key  # noqa: E402


def _apply_three_counter_keys(
    text: str,
    wave_number: int,
    final_pr_count: int,
    cr_cycles: int,
    top_concentration_pct: int,
) -> str:
    """Mirror what /wave-wrapup Step 10.5 does — three upsert_top_level_key calls."""
    text = upsert_top_level_key(text, f"wave_{wave_number}_final_pr_count", str(final_pr_count))
    text = upsert_top_level_key(
        text, f"wave_{wave_number}_changes_requested_cycles", str(cr_cycles)
    )
    text = upsert_top_level_key(
        text, f"wave_{wave_number}_top_concentration_pct", str(top_concentration_pct)
    )
    return text


class CounterKeyWriteTests(unittest.TestCase):
    """Step 10.5 writes 3 top-level keys via upsert_top_level_key."""

    def test_writes_three_keys_at_top_level(self):
        text = (
            "{\n"
            '  "phase": "phase-3",\n'
            '  "wave_9_active": true,\n'
            '  "wave_9_kicked_off_at": "2026-05-09T00:00:00Z"\n'
            "}\n"
        )
        out = _apply_three_counter_keys(text, 9, 12, 6, 17)
        parsed = json.loads(out)
        self.assertEqual(parsed["wave_9_final_pr_count"], 12)
        self.assertEqual(parsed["wave_9_changes_requested_cycles"], 6)
        self.assertEqual(parsed["wave_9_top_concentration_pct"], 17)

    def test_keys_are_top_level_not_nested(self):
        """/wave-retro Step 2.5 reads `.wave_{M}_final_pr_count` — top-level lookup."""
        text = '{\n  "phase": "phase-3",\n  "wave_9_active": true\n}\n'
        out = _apply_three_counter_keys(text, 9, 5, 2, 40)
        parsed = json.loads(out)
        # NOT under a wave_9_summary.* nested block.
        self.assertNotIn("wave_9_summary", parsed)
        self.assertIn("wave_9_final_pr_count", parsed)
        self.assertIn("wave_9_changes_requested_cycles", parsed)
        self.assertIn("wave_9_top_concentration_pct", parsed)

    def test_preserves_existing_siblings(self):
        text = (
            "{\n"
            '  "phase": "phase-3",\n'
            '  "wave_9_active": true,\n'
            '  "wave_9_kicked_off_at": "2026-05-09T00:00:00Z",\n'
            '  "wave_9_repos_in_scope": [\n'
            '    "noorinalabs-main",\n'
            '    "noorinalabs-deploy"\n'
            "  ]\n"
            "}\n"
        )
        out = _apply_three_counter_keys(text, 9, 12, 6, 17)
        parsed = json.loads(out)
        # Sibling values intact
        self.assertTrue(parsed["wave_9_active"])
        self.assertEqual(parsed["wave_9_kicked_off_at"], "2026-05-09T00:00:00Z")
        self.assertEqual(
            parsed["wave_9_repos_in_scope"],
            ["noorinalabs-main", "noorinalabs-deploy"],
        )
        # New keys present
        self.assertEqual(parsed["wave_9_final_pr_count"], 12)

    def test_is_idempotent_on_rerun(self):
        """Re-running Step 10.5 (e.g., wrapup re-invocation) replaces in place."""
        text = '{\n  "phase": "phase-3",\n  "wave_9_active": true\n}\n'
        out1 = _apply_three_counter_keys(text, 9, 12, 6, 17)
        out2 = _apply_three_counter_keys(out1, 9, 12, 6, 17)
        self.assertEqual(out1, out2)
        parsed = json.loads(out2)
        # Exactly one of each — not duplicated.
        self.assertEqual(parsed["wave_9_final_pr_count"], 12)
        # Count occurrences of the key string at line-start indentation.
        self.assertEqual(out2.count('"wave_9_final_pr_count"'), 1)
        self.assertEqual(out2.count('"wave_9_changes_requested_cycles"'), 1)
        self.assertEqual(out2.count('"wave_9_top_concentration_pct"'), 1)

    def test_replace_in_place_with_new_values(self):
        """Re-running with new values updates rather than appends."""
        text = '{\n  "phase": "phase-3",\n  "wave_9_active": true\n}\n'
        out1 = _apply_three_counter_keys(text, 9, 12, 6, 17)
        out2 = _apply_three_counter_keys(out1, 9, 15, 8, 22)
        parsed = json.loads(out2)
        self.assertEqual(parsed["wave_9_final_pr_count"], 15)
        self.assertEqual(parsed["wave_9_changes_requested_cycles"], 8)
        self.assertEqual(parsed["wave_9_top_concentration_pct"], 22)
        # Still single-occurrence per key.
        self.assertEqual(out2.count('"wave_9_final_pr_count"'), 1)

    def test_writes_alongside_wave_summary_block(self):
        """A `wave_{M}_summary` block, if present, coexists at top level.

        Top-level counters remain authoritative; summary block is supplementary.
        """
        text = (
            "{\n"
            '  "phase": "phase-3",\n'
            '  "wave_9_active": true,\n'
            '  "wave_9_summary": {\n'
            '    "total_prs_merged": 12,\n'
            '    "thesis": "wave-shape narrative here"\n'
            "  }\n"
            "}\n"
        )
        out = _apply_three_counter_keys(text, 9, 12, 6, 17)
        parsed = json.loads(out)
        # Both forms present; top-level is authoritative for retro Step 2.5.
        self.assertEqual(parsed["wave_9_final_pr_count"], 12)
        self.assertIn("wave_9_summary", parsed)
        self.assertEqual(parsed["wave_9_summary"]["total_prs_merged"], 12)
        self.assertEqual(parsed["wave_9_summary"]["thesis"], "wave-shape narrative here")


class RetroLookupShapeTests(unittest.TestCase):
    """The keys must be readable via `/wave-retro` Step 2.5's exact jq form."""

    def test_jq_lookup_path_resolves(self):
        """`/wave-retro` Step 2.5 uses `jq -r ".wave_${M}_final_pr_count"`.

        That's a direct top-level lookup. Anything but a top-level scalar
        produces "null" or a syntax error in retro — drift signal.
        """
        text = '{\n  "phase": "phase-3"\n}\n'
        out = _apply_three_counter_keys(text, 9, 12, 6, 17)
        parsed = json.loads(out)
        # Simulate the retro lookup; these must each resolve to a non-null int.
        for key in (
            "wave_9_final_pr_count",
            "wave_9_changes_requested_cycles",
            "wave_9_top_concentration_pct",
        ):
            value = parsed.get(key)
            self.assertIsNotNone(value, f"retro Step 2.5 would see null for {key}")
            self.assertIsInstance(value, int, f"{key} must be int for retro arithmetic")


if __name__ == "__main__":
    unittest.main()
