"""Regression tests for the wave-end skill's step-3 counter derivation (#300).

`/wave-end` derives the three wrapup counters mechanically so they cannot drift
against `/wave-retro`'s recompute. Two of the three are IDENTITY-SENSITIVE and must
come from `trust_signals.py extract` (which resolves team identity from
``Co-Authored-By`` trailers), NOT from ``gh``'s ``.author.login`` — in a dogfooded
single-account repo every PR carries one login, so grouping by it collapses
concentration to ~100% forever (Paloma's Wave-23 must-fix on PR #307).

Two layers, no network:
  * an arithmetic mirror of the documented jq derivation, exercised on the real
    Wave-22 ``extract`` shape → asserts `cr_cycles == 2` AND `concentration == 33`
    (matching `wave_22_top_concentration_pct` in state and the retro recompute);
  * a content guard that both SKILL.md trees derive concentration from the
    identity-aware ``authored_prs`` and never re-introduce ``group_by(.author.login)``.
"""

from __future__ import annotations

from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _FRAMEWORK_ROOT.parent
_SKILL_TREES = (
    _REPO_ROOT / ".claude" / "skills" / "wave-end" / "SKILL.md",
    _FRAMEWORK_ROOT / "assets" / "skills" / "wave-end" / "SKILL.md",
)


# ------------------------------------------------------------ documented arithmetic
# Pure mirrors of the SKILL.md jq. `--cr-cycles` sums per-engineer `rework_cycles`
# (one increment per reworked PR); `--concentration` is max/total over the same
# identity-aware `authored_prs` lists, integer floor, guarded for total == 0.


def _cr_cycles(sig: dict) -> int:
    return sum(int(v.get("rework_cycles", 0)) for v in sig.values())


def _concentration(sig: dict) -> int:
    lens = [len(v.get("authored_prs", [])) for v in sig.values()]
    total = sum(lens)
    return 0 if total == 0 else (max(lens) * 100) // total


def _should_abort(sig: dict, pr_count: int) -> bool:
    """Mirror of SKILL.md step-3 guardrail: refuse to derive counters from an
    extract that cannot be trusted. `extract` fails SILENT under a rate limit
    (returns `{}`, exit 0), so an empty/short result for a wave that merged PRs is
    the read having FAILED, not a genuine zero. Cross-check extract's identity-aware
    `authored_prs` total against the independently-known PR count; any disagreement
    (empty OR partial) aborts. A legitimately empty wave (pr_count == 0) proceeds."""
    if pr_count <= 0:
        return False
    engineers = len(sig)
    sig_pr_total = sum(len(v.get("authored_prs", [])) for v in sig.values())
    return engineers == 0 or sig_pr_total != pr_count


# The real `trust_signals.py extract 22` shape (identity-resolved from trailers):
# #290 Nia and #292 Paloma each carried one rework round; #294 Ibrahim clean.
_WAVE_22 = {
    "Ibrahim El-Amin": {"rework_cycles": 0, "authored_prs": [294], "must_fix_received": 0},
    "Nia Rossi": {"rework_cycles": 1, "authored_prs": [290], "must_fix_received": 2},
    "Paloma Gupta": {"rework_cycles": 1, "authored_prs": [292], "must_fix_received": 1},
    "Tariq Morales": {"rework_cycles": 0, "authored_prs": []},
}


def test_wave22_cr_cycles_is_two() -> None:
    """The bar: Wave 22 replays to cr_cycles = 2, refuting the handoff's `1`."""
    assert _cr_cycles(_WAVE_22) == 2


def test_wave22_concentration_is_33_identity_aware() -> None:
    """The must-fix bar: concentration derives from `authored_prs` → 33 (matching
    `wave_22_top_concentration_pct` and the retro), NOT the ~100 an `.author.login`
    group_by yields when all three PRs share one dogfood account."""
    assert _concentration(_WAVE_22) == 33
    assert _concentration(_WAVE_22) != 100

    # The single-account collapse the fix removes: with all three PRs under one
    # `.author.login`, group_by yields a single group of size 3 → 3*100//3 = 100.
    logins = ["parametrization", "parametrization", "parametrization"]
    groups: dict[str, int] = {}
    for login in logins:
        groups[login] = groups.get(login, 0) + 1
    collapsed_pct = max(groups.values()) * 100 // len(logins)
    assert collapsed_pct == 100  # what group_by(.author.login) produced — the bug


def test_concentration_guards_zero_total() -> None:
    assert _concentration({"A": {"authored_prs": []}}) == 0
    assert _concentration({}) == 0


def test_concentration_floor_matches_jq() -> None:
    """max*100/total floored — 2 of 3 PRs → 66 (parity with jq `| floor`)."""
    sig = {
        "A": {"authored_prs": [1, 2]},
        "B": {"authored_prs": [3]},
    }
    assert _concentration(sig) == 66


# ------------------------------------------------------- silent-extract-failure abort


def test_empty_extract_with_merged_prs_aborts() -> None:
    """The core defect: `extract` returned `{}` (rate-limited, exit 0) but the wave
    merged PRs. Recording cr_cycles=0/concentration=0 would be a silent lie — abort."""
    assert _should_abort({}, pr_count=3) is True


def test_partial_extract_aborts() -> None:
    """A partial read (2 of the wave's 3 PRs) also disagrees with PR_COUNT — abort,
    so the cross-check catches truncated reads, not only total failures."""
    partial = {"Nia Rossi": {"authored_prs": [290]}, "Paloma Gupta": {"authored_prs": [292]}}
    assert _should_abort(partial, pr_count=3) is True


def test_healthy_extract_proceeds() -> None:
    """The Wave-22 read matches PR_COUNT (3 authored PRs) — derive and record."""
    assert _should_abort(_WAVE_22, pr_count=3) is False


def test_genuinely_empty_wave_proceeds() -> None:
    """A wave that merged nothing is a real zero, not a failed read — no abort."""
    assert _should_abort({}, pr_count=0) is False


# ---------------------------------------------------------------- skill content guard


def test_both_trees_derive_concentration_from_authored_prs() -> None:
    for path in _SKILL_TREES:
        text = path.read_text(encoding="utf-8")
        assert ".[].authored_prs | length" in text, f"{path}: concentration must use authored_prs"
        assert "group_by(.author.login)" not in text, (
            f"{path}: concentration must NOT group by .author.login "
            "(collapses to ~100% in a single-account repo — #300)"
        )


def test_both_trees_derive_cr_cycles_from_extract() -> None:
    for path in _SKILL_TREES:
        text = path.read_text(encoding="utf-8")
        assert "[.[].rework_cycles] | add" in text, f"{path}: cr-cycles must sum rework_cycles from extract"


def test_both_trees_guard_against_silent_extract_failure() -> None:
    """Both trees must abort — not record zeros — when a merged-PR wave yields an
    empty/short extract (the silent rate-limit failure, #300 follow-up)."""
    for path in _SKILL_TREES:
        text = path.read_text(encoding="utf-8")
        assert "ABORT: trust_signals extract could not be trusted" in text, (
            f"{path}: missing the silent-extract-failure abort guardrail"
        )
        # The cross-check that catches partial reads, and the single-call capture.
        assert "[.[].authored_prs | length] | add" in text, f"{path}: missing PR_COUNT cross-check"
        assert text.count('extract "$W")') == 1, f"{path}: extract must be called exactly once"
