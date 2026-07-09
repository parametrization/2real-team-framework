"""Regression tests for the wave-end skill's step-3 counter derivation (#300).

`/wave-end` derives the three wrapup counters mechanically so they cannot drift
against `/wave-retro`'s recompute. Two of the three are IDENTITY-SENSITIVE and must
come from `trust_signals.py extract` (which resolves team identity from
``Co-Authored-By`` trailers), NOT from ``gh``'s ``.author.login`` — in a dogfooded
single-account repo every PR carries one login, so grouping by it collapses
concentration to ~100% forever (Paloma's Wave-23 must-fix on PR #307).

Three layers, no network:
  * an arithmetic mirror of the documented jq derivation, exercised on the real
    Wave-22 ``extract`` shape → asserts `cr_cycles == 2` AND `concentration == 33`
    (matching `wave_22_top_concentration_pct` in state and the retro recompute);
  * a mirror of the step-3 abort gate distinguishing the THREE states the original
    guard conflated — genuinely-empty wave (proceed), read-failed (abort), reads-
    disagree (abort). `gh pr list` is GraphQL-backed, the SAME bucket ``extract``
    drains, so under a pre-exhausted budget both fail in lockstep and a naive
    ``${PR_COUNT:-0}`` collapse sails past a cross-check that also anchors on 0 (the
    #307 review defect). The gate anchors on the ORTHOGONAL REST ``rate_limit`` bucket
    and on ``gh pr list``'s captured exit status, neither of which fails in lockstep;
  * a content guard that both SKILL.md trees derive concentration from the
    identity-aware ``authored_prs`` (never ``group_by(.author.login)``) and carry all
    three abort defenses.
"""

from __future__ import annotations

import json
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


_GQL_FLOOR = 100


def _read_trusted(
    graphql_remaining: object, pr_list_rc: int, pr_list_stdout: object
) -> tuple[bool, int | None]:
    """Mirror of SKILL.md defenses (A)+(B): establish that the reads SUCCEEDED before
    any zero is believed. (A) the GraphQL budget, probed over the ORTHOGONAL REST
    `rate_limit` bucket, must be numeric and >= the floor — a pre-exhausted budget
    means `gh pr list` / `extract` would return empty-but-successful in lockstep. (B)
    `gh pr list` must exit 0 AND yield a numeric count — a failed read must NOT
    collapse into an empty string and then a 0. Returns (trusted, pr_count)."""
    # (A) orthogonal budget probe
    if not isinstance(graphql_remaining, int) or isinstance(graphql_remaining, bool):
        return (False, None)
    if graphql_remaining < _GQL_FLOOR:
        return (False, None)
    # (B) explicit exit-status + numeric-count discipline
    if pr_list_rc != 0:
        return (False, None)
    try:
        parsed = json.loads(pr_list_stdout)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return (False, None)
    if not isinstance(parsed, list):
        return (False, None)
    return (True, len(parsed))


def _crosscheck_aborts(sig: dict, pr_count: int) -> bool:
    """Mirror of SKILL.md defense (C): with a TRUSTED pr_count, cross-check extract's
    identity-aware `authored_prs` total. `extract` fails SILENT (returns `{}`, exit 0),
    so an empty/short result for a wave that merged PRs is the read having FAILED, not
    a genuine zero; any disagreement (empty OR partial) aborts. pr_count == 0 here is a
    real empty wave (the reads already proved trustworthy) and proceeds."""
    if pr_count <= 0:
        return False
    engineers = len(sig)
    sig_pr_total = sum(len(v.get("authored_prs", [])) for v in sig.values())
    return engineers == 0 or sig_pr_total != pr_count


def _derivation_aborts(
    *, graphql_remaining: object, pr_list_rc: int, pr_list_stdout: object, sig: dict
) -> bool:
    """The full step-3 gate: an untrusted read aborts BEFORE the cross-check ever sees
    a (possibly collapsed) zero; only a trusted read reaches the cross-check."""
    trusted, pr_count = _read_trusted(graphql_remaining, pr_list_rc, pr_list_stdout)
    if not trusted:
        return True
    assert pr_count is not None
    return _crosscheck_aborts(sig, pr_count)


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


# ------------------------------------------- defense (C): cross-check on a TRUSTED count


def test_crosscheck_empty_extract_with_merged_prs_aborts() -> None:
    """`extract` returned `{}` (silent, exit 0) but the wave merged 3 PRs. Recording
    cr_cycles=0/concentration=0 would be a silent lie — abort."""
    assert _crosscheck_aborts({}, pr_count=3) is True


def test_crosscheck_partial_extract_aborts() -> None:
    """A partial read (2 of the wave's 3 PRs) disagrees with PR_COUNT — abort, so the
    cross-check catches truncated reads, not only total failures."""
    partial = {"Nia Rossi": {"authored_prs": [290]}, "Paloma Gupta": {"authored_prs": [292]}}
    assert _crosscheck_aborts(partial, pr_count=3) is True


def test_crosscheck_healthy_extract_proceeds() -> None:
    """The Wave-22 read matches PR_COUNT (3 authored PRs) — derive and record."""
    assert _crosscheck_aborts(_WAVE_22, pr_count=3) is False


# -------------------- defenses (A)+(B): distinguish the THREE states the bug conflated
# genuinely empty wave (reads succeeded, 0 PRs) -> proceed;  read failed -> abort;
# reads disagree -> abort.  The old suite asserted `_should_abort({}, 0) is False`,
# which ENCODED the pre-exhausted bug as intended behavior (#307 review).

_HEALTHY_GQL = 4800  # REST rate_limit reports GraphQL healthy while a wave is read


def test_genuinely_empty_wave_proceeds() -> None:
    """State 1 — reads SUCCEEDED (budget healthy, `gh pr list` exit 0, `[]`) and the
    wave merged nothing. A real zero: proceed."""
    assert (
        _derivation_aborts(
            graphql_remaining=_HEALTHY_GQL, pr_list_rc=0, pr_list_stdout="[]", sig={}
        )
        is False
    )


def test_pre_exhausted_lockstep_read_aborts() -> None:
    """State 2, the revert->red case (#307 review): GraphQL is pre-exhausted, so BOTH
    `gh pr list` (exit 1, empty stdout) and `extract` (`{}`) fail in lockstep. The old
    code let PR_COUNT collapse to 0 and the cross-check compared 0 == 0 and 'passed'.
    Now the orthogonal REST budget probe AND the captured exit status BOTH abort."""
    assert (
        _derivation_aborts(
            graphql_remaining=0, pr_list_rc=1, pr_list_stdout="", sig={}
        )
        is True
    )


def test_gh_pr_list_nonzero_exit_aborts() -> None:
    """State 2 — even with a (stale) healthy-looking budget, a non-zero `gh pr list`
    exit is a failed read, not an empty wave: abort, never a collapsed 0."""
    assert (
        _derivation_aborts(
            graphql_remaining=_HEALTHY_GQL, pr_list_rc=1, pr_list_stdout="", sig={}
        )
        is True
    )


def test_gh_pr_list_nonnumeric_stdout_aborts() -> None:
    """State 2 — `gh pr list` exited 0 but stdout is not a JSON array (a warning line,
    a truncated body): the count is untrustworthy — abort."""
    assert (
        _derivation_aborts(
            graphql_remaining=_HEALTHY_GQL,
            pr_list_rc=0,
            pr_list_stdout="GraphQL: API rate limit exceeded",
            sig={},
        )
        is True
    )


def test_rate_limit_probe_unreadable_aborts() -> None:
    """State 2 — the orthogonal budget probe itself failed (non-int remaining): we
    cannot establish the read will succeed, so refuse to record."""
    assert (
        _derivation_aborts(
            graphql_remaining=None, pr_list_rc=0, pr_list_stdout="[]", sig={}
        )
        is True
    )


def test_near_zero_budget_aborts_before_reading() -> None:
    """State 2 — budget positive but below the fail-fast floor: abort with the
    rate-limit diagnostic rather than proceeding into a read that will come back
    empty-but-successful."""
    assert (
        _derivation_aborts(
            graphql_remaining=_GQL_FLOOR - 1,
            pr_list_rc=0,
            pr_list_stdout="[]",
            sig={},
        )
        is True
    )


def test_reads_disagree_aborts() -> None:
    """State 3 — reads succeeded (budget healthy, 3 PRs listed) but `extract` only
    covers 2 of them (a partial GraphQL read): abort on the disagreement."""
    listed = json.dumps([{"number": 290}, {"number": 292}, {"number": 294}])
    partial = {"Nia Rossi": {"authored_prs": [290]}, "Paloma Gupta": {"authored_prs": [292]}}
    assert (
        _derivation_aborts(
            graphql_remaining=_HEALTHY_GQL, pr_list_rc=0, pr_list_stdout=listed, sig=partial
        )
        is True
    )


def test_full_healthy_path_proceeds() -> None:
    """All three defenses pass: healthy budget, 3 PRs listed, extract covers all 3 —
    derive and record."""
    listed = json.dumps([{"number": 290}, {"number": 292}, {"number": 294}])
    assert (
        _derivation_aborts(
            graphql_remaining=_HEALTHY_GQL, pr_list_rc=0, pr_list_stdout=listed, sig=_WAVE_22
        )
        is False
    )


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
    empty/short extract, AND when the reads themselves failed (pre-exhausted budget /
    non-zero `gh pr list`). The three orthogonal defenses (#307 review) must be present."""
    for path in _SKILL_TREES:
        text = path.read_text(encoding="utf-8")
        # (A) orthogonal REST budget probe — cannot fail in lockstep with GraphQL.
        assert ".resources.graphql.remaining" in text, f"{path}: missing REST rate_limit preflight (A)"
        assert "ABORT: GraphQL budget near-exhausted" in text, f"{path}: missing near-exhausted abort (A)"
        # (B) explicit `gh pr list` exit-status capture — no ${VAR:-0} collapse.
        assert "PR_LIST_RC=$?" in text, f"{path}: missing gh pr list exit-status capture (B)"
        assert "ABORT: gh pr list failed" in text, f"{path}: missing failed-read abort (B)"
        # (C) cross-check against the trusted count, catching empty/partial extracts.
        assert "ABORT: trust_signals extract could not be trusted" in text, (
            f"{path}: missing the silent-extract-failure abort guardrail (C)"
        )
        assert "[.[].authored_prs | length] | add" in text, f"{path}: missing PR_COUNT cross-check (C)"
        assert text.count('extract "$W")') == 1, f"{path}: extract must be called exactly once"
