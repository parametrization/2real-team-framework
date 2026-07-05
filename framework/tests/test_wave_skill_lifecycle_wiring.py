"""Lifecycle wiring in the wave-start / wave-end skills (issue #99).

The framework must dogfood its own lifecycle state machine: the wave skills have to
drive `lifecycle.py` so `.claude/state.json` is written **live** as a wave runs
(allocate → start → scope → kickoff … wrapup) — no manual backfill at retro time.

Two things are asserted:

  1. **Wiring is present** — both the canonical (`framework/assets/skills/`) and the
     dogfood (`.claude/skills/`) copies of wave-start / wave-end invoke the right
     `lifecycle.py` transitions, and resolve the lib the dual-deploy way (installed
     `.claude/lib` first, `framework/assets/lib` fallback) so the lib is runnable in
     the framework SOURCE repo too (the exact gap #99 closes).
  2. **The sequence transitions state live** — driving the wave-start transitions
     through the CLI leaves a mid-wave `state.json` (active wave, pointer, merge
     model recorded) *before* wrapup, mirroring what the skill leaves on disk.

Stdlib + pytest only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _FRAMEWORK_ROOT.parent
_LIB = _FRAMEWORK_ROOT / "assets" / "lib" / "lifecycle.py"

# Both trees a wave skill must live in (dual-deploy): canonical + dogfood.
_SKILL_TREES = (
    _FRAMEWORK_ROOT / "assets" / "skills",
    _REPO_ROOT / ".claude" / "skills",
)

# The dual-deploy lib-resolution idiom every lifecycle-driving skill uses.
_LIB_FALLBACK = 'LIB="$REPO_ROOT/.claude/lib"'
_LIB_SOURCE_FALLBACK = '[ -f "$LIB/lifecycle.py" ] || LIB="$REPO_ROOT/framework/assets/lib"'


def _skill_text(tree: Path, name: str) -> str:
    return (tree / name / "SKILL.md").read_text(encoding="utf-8")


def _both_copies(name: str):
    return [pytest.param(tree, id=f"{name}:{tree.parent.name}/{tree.name}") for tree in _SKILL_TREES]


# --------------------------------------------------------------- dual-deploy presence


def test_wave_end_has_canonical_asset_copy() -> None:
    """wave-end must ship a canonical copy, not just a dogfood one (dual-deploy)."""
    assert (_FRAMEWORK_ROOT / "assets" / "skills" / "wave-end" / "SKILL.md").is_file()


@pytest.mark.parametrize("tree", _SKILL_TREES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_wave_skills_resolve_lib_dual_deploy(tree: Path) -> None:
    """Both skills resolve the lib installed-first, source-fallback (runnable in-repo)."""
    for name in ("wave-start", "wave-end"):
        text = _skill_text(tree, name)
        assert _LIB_FALLBACK in text, f"{name} missing installed-lib resolution"
        assert _LIB_SOURCE_FALLBACK in text, f"{name} missing framework-source lib fallback"


# --------------------------------------------------------------- transition wiring


@pytest.mark.parametrize("tree", _SKILL_TREES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_wave_start_drives_allocate_start_scope_kickoff(tree: Path) -> None:
    text = _skill_text(tree, "wave-start")
    for verb in ("wave allocate", "wave start", "wave scope", "wave kickoff"):
        assert f'lifecycle.py" {verb}' in text, f"wave-start does not invoke `lifecycle.py {verb}`"
    # The kickoff transition must sit behind the User-approval gate.
    assert "User approval" in text or "User Approval" in text


@pytest.mark.parametrize("tree", _SKILL_TREES, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_wave_end_drives_wrapup_and_merge_model(tree: Path) -> None:
    text = _skill_text(tree, "wave-end")
    assert 'lifecycle.py" wave wrapup' in text, "wave-end does not invoke `lifecycle.py wave wrapup`"
    assert 'lifecycle.py" merge-model get' in text, "wave-end does not read the merge model"


# --------------------------------------------------------------- live transition e2e


def _run(*a: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_LIB), *a], capture_output=True, text=True)


def test_wave_start_sequence_transitions_state_live(tmp_path: Path) -> None:
    """Driving the wave-start transitions leaves a live mid-wave state — before wrapup.

    This is the regression guard for #99: the wave is `active`, `current_wave` points at
    it, and the merge model is recorded on disk while work is still in flight, so a retro
    reads real state instead of backfilling.
    """
    state = tmp_path / "state.json"

    # allocate → claims wave 1 for phase 4, persists counter + phase stamps.
    r = _run("wave", "allocate", "--phase", "4", "--write", "--state", str(state))
    assert r.returncode == 0, r.stderr
    w = "1"

    # start → scope → kickoff (the wave-start portion of the lifecycle).
    assert _run("wave", "start", w, "--at", "2026-07-05T00:00:00Z", "--state", str(state)).returncode == 0
    assert _run("wave", "scope", w, "--repos", "acme", "--phase", "4",
                "--at", "2026-07-05T00:00:00Z", "--state", str(state)).returncode == 0
    assert _run("wave", "kickoff", w, "--merge-model", "wave-branch",
                "--at", "2026-07-05T00:00:00Z", "--state", str(state)).returncode == 0

    s = json.loads(state.read_text())
    # Mid-wave, BEFORE wrapup: active + pointed-at + model recorded, no completion stamp.
    assert s["global_wave_seq"] == 1
    assert s["current_wave"] == "wave-1"
    assert s["wave_1_active"] is True
    assert s["wave_1_phase"] == 4
    assert s["wave_1_repos_in_scope"] == ["acme"]
    assert s["wave_1_kicked_off_at"] == "2026-07-05T00:00:00Z"
    assert s["wave_1_merge_model"] == "wave-branch"
    assert "wave_1_completed_at" not in s
    assert s.get("last_completed_wave") != "wave-1"

    # wrapup → closes it live (what wave-end records).
    assert _run("wave", "wrapup", w, "--pr-count", "3", "--cr-cycles", "1", "--concentration", "50",
                "--at", "2026-07-05T09:00:00Z", "--state", str(state)).returncode == 0
    s = json.loads(state.read_text())
    assert s["wave_1_active"] is False
    assert s["wave_1_completed_at"] == "2026-07-05T09:00:00Z"
    assert s["last_completed_wave"] == "wave-1"
    assert s["wave_1_final_pr_count"] == 3
