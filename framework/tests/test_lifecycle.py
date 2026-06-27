"""Tests for the generic lifecycle state machine.

Covers the pure allocator math, the merge-model validate/get/set, the
reachability classifier matrix, and the lifecycle transitions (start/scope/
kickoff/wrapup) writing the canonical wave_{W}_* keys + advancing the pointers —
all against an explicit --state tmp file with deterministic --at timestamps.
Stdlib + pytest only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))
import lifecycle  # noqa: E402


# --------------------------------------------------------------- allocator


def test_peek_fresh_project_is_one() -> None:
    assert lifecycle.allocation_target({}, floor=0) == 1


def test_peek_respects_floor() -> None:
    assert lifecycle.allocation_target({}, floor=15) == 16


def test_next_from_explicit_counter() -> None:
    assert lifecycle.allocation_target({"global_wave_seq": 7}) == 8


def test_seed_from_existing_keys_without_counter() -> None:
    state = {"wave_3_active": True, "wave_5_final_pr_count": 2}
    # no global_wave_seq → seed is max existing (5) → next is 6
    assert lifecycle.allocation_target(state) == 6


def test_reservation_is_claimed_not_skipped() -> None:
    # committed counter 7, but wave_8 reserved by a meta-issue → claim 8, not 9.
    state = {"global_wave_seq": 7, "wave_8_meta_issue": "#42"}
    assert lifecycle.reserved_wave(state) == 8
    assert lifecycle.allocation_target(state) == 8


def test_phase_ordinal_counts_within_phase() -> None:
    state = {"wave_16_phase": 6, "wave_17_phase": 6, "wave_18_phase": 7}
    assert lifecycle.phase_ordinal(state, 6) == 3  # next wave is P6's 3rd
    assert lifecycle.phase_ordinal(state, 7) == 2


# --------------------------------------------------------------- merge model


def test_validate_merge_model_rejects_typo() -> None:
    lifecycle.validate_merge_model("wave-branch")
    lifecycle.validate_merge_model("direct-to-main")
    try:
        lifecycle.validate_merge_model("wavebranch")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on invalid model")


def test_read_merge_model_absent_is_none() -> None:
    assert lifecycle.read_merge_model({}, "16") is None
    assert lifecycle.read_merge_model({"wave_16_merge_model": "wave-branch"}, "16") == "wave-branch"


# --------------------------------------------------------------- reachability


def test_reachability_direct_to_main_violation() -> None:
    sev, _ = lifecycle.classify_reachability(
        lifecycle.DIRECT_TO_MAIN, branch_exists=True, ahead_by=3, status="ahead",
        open_integration_pr=False,
    )
    assert sev == lifecycle.VIOLATION


def test_reachability_wave_branch_with_pr_ok() -> None:
    sev, _ = lifecycle.classify_reachability(
        lifecycle.WAVE_BRANCH, branch_exists=True, ahead_by=3, status="ahead",
        open_integration_pr=True,
    )
    assert sev == lifecycle.OK


def test_reachability_wave_branch_no_pr_advisory() -> None:
    sev, _ = lifecycle.classify_reachability(
        lifecycle.WAVE_BRANCH, branch_exists=True, ahead_by=3, status="ahead",
        open_integration_pr=False,
    )
    assert sev == lifecycle.ADVISORY


def test_reachability_no_branch_or_reachable_is_ok() -> None:
    sev, _ = lifecycle.classify_reachability(
        None, branch_exists=False, ahead_by=0, status="absent", open_integration_pr=False,
    )
    assert sev == lifecycle.OK
    sev2, _ = lifecycle.classify_reachability(
        lifecycle.WAVE_BRANCH, branch_exists=True, ahead_by=0, status="identical",
        open_integration_pr=False,
    )
    assert sev2 == lifecycle.OK


# --------------------------------------------------------------- transitions


def test_full_lifecycle_writes_canonical_keys(tmp_path: Path) -> None:
    state = tmp_path / "state.json"

    lifecycle.start_wave(state, "16", at="2026-01-01T00:00:00Z")
    lifecycle.scope_wave(state, "16", ["api", "web"], phase=6, at="2026-01-01T01:00:00Z")
    lifecycle.kickoff_wave(state, "16", merge_model="wave-branch", at="2026-01-01T02:00:00Z")
    lifecycle.wrapup_wave(state, "16", pr_count=5, cr_cycles=2, concentration=40,
                          at="2026-01-01T03:00:00Z")

    s = json.loads(state.read_text())
    assert s["current_wave"] == "wave-16"
    assert s["last_completed_wave"] == "wave-16"
    assert s["wave_16_started_at"] == "2026-01-01T00:00:00Z"
    assert s["wave_16_repos_in_scope"] == ["api", "web"]
    assert s["wave_16_phase"] == 6
    assert s["wave_16_merge_model"] == "wave-branch"
    assert s["wave_16_kicked_off_at"] == "2026-01-01T02:00:00Z"
    assert s["wave_16_active"] is False  # wrapup deactivated
    assert s["wave_16_final_pr_count"] == 5
    assert s["wave_16_changes_requested_cycles"] == 2
    assert s["wave_16_top_concentration_pct"] == 40
    assert s["wave_16_completed_at"] == "2026-01-01T03:00:00Z"


def test_persist_preserves_existing_and_is_valid_json(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    # The compact-inline shape lifecycle produces / upsert extends.
    state.write_text('{\n  "owner": "acme",\n  "global_wave_seq": 15\n}\n')
    lifecycle.start_wave(state, "16", at="2026-01-01T00:00:00Z")
    s = json.loads(state.read_text())  # must still parse
    assert s["owner"] == "acme"  # untouched
    assert s["global_wave_seq"] == 15
    assert s["wave_16_active"] is True


# --------------------------------------------------------------- CLI


def test_cli_state_path_and_wave_flow(tmp_path: Path) -> None:
    state = tmp_path / "lc.json"

    def run(*a: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(_FRAMEWORK_ROOT / "assets" / "lib" / "lifecycle.py"), *a],
            capture_output=True, text=True,
        )

    # peek on a fresh explicit state file → 1
    r = run("wave", "peek", "--state", str(state))
    assert r.returncode == 0 and r.stdout.strip() == "1", r.stderr

    # allocate --write phase 1 → claims 1, persists counter + phase stamp
    r = run("wave", "allocate", "--phase", "1", "--write", "--state", str(state))
    assert r.returncode == 0, r.stderr
    s = json.loads(state.read_text())
    assert s["global_wave_seq"] == 1 and s["wave_1_phase"] == 1

    # peek now advances to 2
    r = run("wave", "peek", "--state", str(state))
    assert r.stdout.strip() == "2"

    # merge-model set/get round-trips
    assert run("merge-model", "set", "1", "wave-branch", "--state", str(state)).returncode == 0
    r = run("merge-model", "get", "1", "--state", str(state))
    assert r.stdout.strip() == "wave-branch"

    # invalid model rejected at the CLI (argparse choices)
    assert run("merge-model", "set", "1", "bogus", "--state", str(state)).returncode != 0
