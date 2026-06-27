"""Tests for wave_seq — the global monotonic wave-id allocator (main#804).

Design B replaces the per-phase wave number (which reset to 1 each phase and so
collided cross-phase: P5W2 ↔ P6W2 both → ``wave_2_*``) with a single
never-resetting counter. The headline acceptance criterion — *two same-numbered
waves in different phases write to DISTINCT keys* — is
``TestNoCrossPhaseCollision`` below: it is impossible to reproduce the collision
because a global id is never reused.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Helper lives at .claude/lib/wave_seq.py; this test is at
# .claude/lib/tests/test_*.py. parent.parent reaches the lib root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wave_seq  # noqa: E402


def _grandfathered_p6_status() -> dict:
    """The live migration state: in-flight P6W1/W2 keep their bare keys; a
    prior-phase ``wave_4`` graveyard key survives; the counter is seeded to 15
    so the next allocation is the first global wave (16)."""
    return {
        "current_phase": 6,
        "current_wave": "wave-2",
        "global_wave_seq": 15,
        "wave_1_phase": 6,
        "wave_1_phase_ordinal": 1,
        "wave_1_scope": {"phase": 6, "theme": "P6W1"},
        "wave_2_phase": 6,
        "wave_2_phase_ordinal": 2,
        "wave_2_active": True,
        "wave_2_scope": {"phase": 6, "theme": "P6W2"},
        # Prior-phase graveyard (P4) — inert under global numbering.
        "wave_4_scope": {"phase": 4, "theme": "old P4W4"},
        "wave_4_final_pr_count": 19,
    }


class TestExistingWaveNumbers(unittest.TestCase):
    def test_extracts_bare_wave_ids(self) -> None:
        status = _grandfathered_p6_status()
        self.assertEqual(wave_seq.existing_wave_numbers(status), {1, 2, 4})

    def test_trailing_underscore_prevents_prefix_bleed(self) -> None:
        # wave_4_ must not match wave_42_.
        self.assertEqual(wave_seq.existing_wave_numbers({"wave_42_active": True}), {42})


class TestSeedAndCounter(unittest.TestCase):
    def test_seed_respects_historical_floor(self) -> None:
        # No counter, only small per-phase numbers → seed clears the floor.
        status = {"wave_1_phase": 6, "wave_2_phase": 6}
        self.assertEqual(wave_seq.seed_value(status), wave_seq.HISTORICAL_FLOOR)

    def test_seed_clears_any_higher_existing_id(self) -> None:
        status = {"wave_20_phase": 7}
        self.assertEqual(wave_seq.seed_value(status), 20)

    def test_current_seq_reads_explicit_counter(self) -> None:
        self.assertEqual(wave_seq.current_seq(_grandfathered_p6_status()), 15)

    def test_current_seq_self_seeds_when_absent(self) -> None:
        status = _grandfathered_p6_status()
        del status["global_wave_seq"]
        # Falls back to the floor (15) since the only ids are 1/2/4.
        self.assertEqual(wave_seq.current_seq(status), wave_seq.HISTORICAL_FLOOR)

    def test_counter_never_below_existing_ids(self) -> None:
        # A stale low counter must not let allocation re-use an existing id.
        status = {"global_wave_seq": 3, "wave_20_phase": 7}
        self.assertEqual(wave_seq.current_seq(status), 20)

    def test_next_is_monotonic_increment(self) -> None:
        self.assertEqual(wave_seq.next_global_wave(_grandfathered_p6_status()), 16)


class TestPhaseDerivation(unittest.TestCase):
    def test_phase_of_reads_display_stamp(self) -> None:
        self.assertEqual(wave_seq.phase_of(_grandfathered_p6_status(), 1), 6)

    def test_phase_of_falls_back_to_scope(self) -> None:
        status = {"wave_4_scope": {"phase": 4}}
        self.assertEqual(wave_seq.phase_of(status, 4), 4)

    def test_phase_of_none_when_unstamped(self) -> None:
        self.assertIsNone(wave_seq.phase_of({"wave_9_final_pr_count": 2}, 9))

    def test_phase_ordinal_counts_within_phase(self) -> None:
        status = _grandfathered_p6_status()
        # P6 already has waves 1 and 2 → next P6 wave is ordinal 3.
        self.assertEqual(wave_seq.phase_ordinal(status, 6), 3)

    def test_phase_ordinal_first_wave_of_new_phase(self) -> None:
        status = _grandfathered_p6_status()
        # P7 has no waves yet → ordinal 1, even though the global id will be 16.
        self.assertEqual(wave_seq.phase_ordinal(status, 7), 1)


class TestNoCrossPhaseCollision(unittest.TestCase):
    """The acceptance criterion: two same-ORDINAL waves in different phases
    write to DISTINCT global keys — the collision class is gone."""

    def test_same_ordinal_different_phase_distinct_keys(self) -> None:
        status: dict = {"global_wave_seq": 15}

        # Allocate "phase 6, wave 2" (ordinal 2).
        status["wave_16_phase"] = 6
        status["wave_16_phase_ordinal"] = 1
        status["wave_17_phase"] = 6
        status["wave_17_phase_ordinal"] = 2
        status["global_wave_seq"] = 17
        p6_wave2_id = 17

        # Later: allocate "phase 7, wave 2" (also ordinal 2, the historical
        # collision case). It gets a fresh global id, never re-using 17.
        self.assertEqual(wave_seq.next_global_wave(status), 18)  # P7W1
        status["wave_18_phase"] = 7
        status["wave_18_phase_ordinal"] = 1
        status["global_wave_seq"] = 18
        self.assertEqual(wave_seq.next_global_wave(status), 19)  # P7W2
        p7_wave2_id = 19

        # Same human ordinal (Wave 2), different phases → DISTINCT keys.
        self.assertNotEqual(p6_wave2_id, p7_wave2_id)
        self.assertNotEqual(f"wave_{p6_wave2_id}_scope", f"wave_{p7_wave2_id}_scope")
        # The P6 "Wave 2" kept its human ordinal even though its global id is 17.
        self.assertEqual(status["wave_17_phase_ordinal"], 2)


class TestRetroReservationAwareness(unittest.TestCase):
    """Regression for main#885: ``/wave-retro`` Step 9 reserves the next id by
    writing ``wave_{N}_meta_issue`` WITHOUT bumping ``global_wave_seq`` (it stays
    N-1). The subsequent ``/wave-scope`` ``allocate`` must claim N — NOT skip to
    N+1 as it did in the P7 W18→W19 transition (allocated 20 instead of 19)."""

    def _post_retro_reservation(self) -> dict:
        """Status exactly as /wave-retro Step 9 leaves it: P7W18 committed
        (global_wave_seq=18, wave_18 stamped phase 7 ordinal 1), and wave_19
        reserved via its meta_issue key ONLY — counter NOT advanced, no phase
        stamp on 19 yet (mirrors the upsert the retro skill actually performs)."""
        return {
            "current_phase": 7,
            "current_wave": "wave-18",
            "global_wave_seq": 18,
            "wave_18_phase": 7,
            "wave_18_phase_ordinal": 1,
            "wave_18_scope": {"phase": 7, "theme": "P7W1"},
            # Retro Step 9 reservation: meta_issue key, counter still 18.
            "wave_19_meta_issue": "noorinalabs-main#882",
        }

    def test_reserved_wave_detects_pending_reservation(self) -> None:
        self.assertEqual(wave_seq.reserved_wave(self._post_retro_reservation()), 19)

    def test_reserved_wave_none_without_meta_issue_key(self) -> None:
        status = self._post_retro_reservation()
        del status["wave_19_meta_issue"]
        self.assertIsNone(wave_seq.reserved_wave(status))

    def test_reserved_wave_none_when_counter_absent(self) -> None:
        # No committed counter → cannot distinguish reserved from committed;
        # fall back to the seed-safe monotonic path.
        status = self._post_retro_reservation()
        del status["global_wave_seq"]
        self.assertIsNone(wave_seq.reserved_wave(status))

    def test_allocation_target_returns_reserved_id(self) -> None:
        # The headline bug: bare next_global_wave skips to 20; the
        # reservation-aware target claims the reserved 19.
        status = self._post_retro_reservation()
        self.assertEqual(wave_seq.next_global_wave(status), 20)  # the old (wrong) value
        self.assertEqual(wave_seq.allocation_target(status), 19)

    def test_allocation_target_falls_through_when_no_reservation(self) -> None:
        # Normal mid-wave state (no pending meta_issue at counter+1) is unchanged.
        status = _grandfathered_p6_status()
        self.assertEqual(wave_seq.allocation_target(status), wave_seq.next_global_wave(status))

    def test_peek_returns_reserved_id_not_skip(self) -> None:
        with TemporaryDirectory() as d:
            path = Path(d) / "cross-repo-status.json"
            path.write_text(json.dumps(self._post_retro_reservation(), indent=2) + "\n")
            import io
            from contextlib import redirect_stdout

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = wave_seq.main(["peek", str(path)])
            self.assertEqual(rc, 0)
            self.assertEqual(buf.getvalue().strip(), "19")

    def test_allocate_write_claims_reserved_id_and_advances_counter(self) -> None:
        with TemporaryDirectory() as d:
            path = Path(d) / "cross-repo-status.json"
            path.write_text(json.dumps(self._post_retro_reservation(), indent=2) + "\n")

            rc = wave_seq.main(["allocate", str(path), "--phase", "7", "--write"])
            self.assertEqual(rc, 0)

            after = json.loads(path.read_text())
            # Counter advances to the RESERVED id (19), not past it (20).
            self.assertEqual(after["global_wave_seq"], 19)
            self.assertEqual(after["wave_19_phase"], 7)
            # P7 already has wave 18 (ordinal 1); the reserved 19 is ordinal 2.
            self.assertEqual(after["wave_19_phase_ordinal"], 2)
            # No wave_20_* keys were ever created.
            self.assertNotIn("wave_20_phase", after)
            self.assertNotIn("wave_20_phase_ordinal", after)
            # The reservation key is preserved.
            self.assertEqual(after["wave_19_meta_issue"], "noorinalabs-main#882")


class TestAllocateWritesPreserveShape(unittest.TestCase):
    """End-to-end --write goes through upsert_status_keys, so the compact-inline
    file shape is preserved and the result is valid JSON."""

    def _write_status(self, tmp: Path, data: dict) -> Path:
        path = tmp / "cross-repo-status.json"
        path.write_text(json.dumps(data, indent=2) + "\n")
        return path

    def test_allocate_write_persists_counter_and_stamps(self) -> None:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            path = self._write_status(tmp, _grandfathered_p6_status())

            rc = wave_seq.main(["allocate", str(path), "--phase", "6", "--write"])
            self.assertEqual(rc, 0)

            after = json.loads(path.read_text())
            self.assertEqual(after["global_wave_seq"], 16)
            self.assertEqual(after["wave_16_phase"], 6)
            # P6 had waves 1,2 → the new global wave 16 is phase-ordinal 3.
            self.assertEqual(after["wave_16_phase_ordinal"], 3)
            # Grandfathered keys untouched.
            self.assertEqual(after["wave_2_phase"], 6)
            self.assertEqual(after["wave_4_final_pr_count"], 19)

    def test_dry_run_does_not_write(self) -> None:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            path = self._write_status(tmp, _grandfathered_p6_status())
            before = path.read_text()

            rc = wave_seq.main(["allocate", str(path), "--phase", "7"])
            self.assertEqual(rc, 0)
            self.assertEqual(path.read_text(), before)

    def test_peek_is_read_only(self) -> None:
        with TemporaryDirectory() as d:
            tmp = Path(d)
            path = self._write_status(tmp, _grandfathered_p6_status())
            before = path.read_text()

            rc = wave_seq.main(["peek", str(path)])
            self.assertEqual(rc, 0)
            self.assertEqual(path.read_text(), before)


if __name__ == "__main__":
    unittest.main()
