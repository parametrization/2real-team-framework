"""Tests for the wave-end skill's review_load.py — per-reviewer review-load
counts recorded next to concentration in the wrapup (#231; W11/W12/W13 proposal).

Stdlib + pytest only; no network — the pure counting/render core is exercised on
hand-built verdict-comment data (the same verdict grammar trust_signals parses).
Covers verdict attribution to the Requestor, the per-PR distinct-review count,
roster canonicalization of name variants, amend-in-place NOT inflating the count,
and the compact render line.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_SKILL_DIR = _FRAMEWORK_ROOT / "assets" / "skills" / "wave-end"
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "hooks"))
sys.path.insert(0, str(_FRAMEWORK_ROOT / "assets" / "lib"))
sys.path.insert(0, str(_SKILL_DIR))

import review_load as rl  # noqa: E402


def _verdict(requestor: str, requestee: str, must_fix: str = "None") -> str:
    """A charter-shaped verdict comment body (see team/charter/issues.md)."""
    replied = "Request" if must_fix != "None" else "Replied"
    return (
        f"Requestor: {requestor}\n"
        f"Requestee: {requestee}\n"
        f"RequestOrReplied: {replied}\n\n"
        f"Must-fix: {must_fix}\n"
    )


# --------------------------------------------------------------- review_load (core)


def test_counts_one_verdict_per_reviewer_per_pr() -> None:
    prs = [
        (1, "Paloma.Gupta", [_verdict("Nia.Rossi", "Paloma.Gupta"), _verdict("Tariq.Morales", "Paloma.Gupta")]),
        (2, "Ibrahim.El-Amin", [_verdict("Nia.Rossi", "Ibrahim.El-Amin"), _verdict("Paloma.Gupta", "Ibrahim.El-Amin")]),
    ]
    loads = rl.review_load(prs)
    assert loads["Nia.Rossi"].verdicts == 2
    assert loads["Nia.Rossi"].prs_reviewed == 2
    assert loads["Tariq.Morales"].verdicts == 1
    assert loads["Paloma.Gupta"].verdicts == 1


def test_two_verdicts_same_pr_counts_two_verdicts_one_pr() -> None:
    """A reviewer posting two verdict comments on ONE PR is 2 verdicts but 1 PR."""
    prs = [
        (7, "Paloma.Gupta", [_verdict("Nia.Rossi", "Paloma.Gupta", must_fix="- fix X"), _verdict("Nia.Rossi", "Paloma.Gupta")]),
    ]
    loads = rl.review_load(prs)
    assert loads["Nia.Rossi"].verdicts == 2
    assert loads["Nia.Rossi"].prs_reviewed == 1


def test_amend_in_place_does_not_inflate_count() -> None:
    """The amendment convention edits the SAME comment — the count is over the
    final comment set, so an amended Request→Replied is still one verdict."""
    posted_then_amended = [_verdict("Tariq.Morales", "Paloma.Gupta")]  # ends as one Replied
    loads = rl.review_load([(9, "Paloma.Gupta", posted_then_amended)])
    assert loads["Tariq.Morales"].verdicts == 1
    assert loads["Tariq.Morales"].prs_reviewed == 1


def test_verdict_without_requestor_is_skipped() -> None:
    no_requestor = "RequestOrReplied: Replied\n\nMust-fix: None\n"
    loads = rl.review_load([(3, "Paloma.Gupta", [no_requestor, _verdict("Nia.Rossi", "Paloma.Gupta")])])
    assert set(loads) == {"Nia.Rossi"}
    assert loads["Nia.Rossi"].verdicts == 1


def test_non_verdict_comments_ignored() -> None:
    chatter = "LGTM, nice work!\n"
    loads = rl.review_load([(4, "Nia.Rossi", [chatter, _verdict("Paloma.Gupta", "Nia.Rossi")])])
    assert set(loads) == {"Paloma.Gupta"}


def test_author_self_verdict_is_excluded() -> None:
    """#288: a verdict whose Requestor is the PR's own author (the author wearing
    reviewer grammar on their own PR — the W21 slip) never adds to the load; a
    genuine reviewer on the same PR still counts."""
    prs = [
        (
            5,
            "Ibrahim.El-Amin",
            [
                # Ibrahim's own must-fix reply that slipped into Requestor grammar
                # on his own PR — author-excluded, contributes nothing.
                _verdict("Ibrahim.El-Amin", "Ibrahim.El-Amin"),
                # A genuine reviewer of Ibrahim's PR — still counts.
                _verdict("Paloma.Gupta", "Ibrahim.El-Amin"),
            ],
        ),
    ]
    loads = rl.review_load(prs)
    assert set(loads) == {"Paloma.Gupta"}
    assert loads["Paloma.Gupta"].verdicts == 1
    assert "Ibrahim.El-Amin" not in loads


def test_author_self_verdict_excluded_folds_name_variants() -> None:
    """#288: author-exclusion folds through canon, so a self-verdict written in a
    name variant of the author is still excluded."""

    def canon(name: str) -> str:
        key = name.replace(".", " ").split(" (")[0].strip().lower()
        return {"ibrahim el-amin": "Ibrahim El-Amin"}.get(key, name)

    prs = [
        (
            6,
            "Ibrahim.El-Amin",
            [_verdict("Ibrahim El-Amin (Senior)", "Ibrahim.El-Amin")],
        ),
    ]
    loads = rl.review_load(prs, canon=canon)
    assert loads == {}


def test_unknown_author_disables_exclusion() -> None:
    """#288 is fail-open: a PR with an unknown (``None``) author excludes nothing
    — the reviewer's verdict still counts."""
    loads = rl.review_load([(8, None, [_verdict("Nia.Rossi", "Paloma.Gupta")])])
    assert loads["Nia.Rossi"].verdicts == 1


def test_order_independent() -> None:
    a = [(1, "X", [_verdict("Nia.Rossi", "X")]), (2, "X", [_verdict("Tariq.Morales", "X")])]
    b = list(reversed(a))
    assert rl.review_load(a) == rl.review_load(b)


def test_empty_prs_yields_empty() -> None:
    assert rl.review_load([]) == {}


def test_canon_folds_name_variants() -> None:
    """A canon mapper folds Requestor variants to one identity (roster-fold parity
    with trust_signals): Nia.Rossi / 'Nia Rossi (Staff)' are one reviewer."""

    def canon(name: str) -> str:
        key = name.replace(".", " ").split(" (")[0].strip().lower()
        return {"nia rossi": "Nia Rossi"}.get(key, name)

    prs = [
        (1, "X", [_verdict("Nia.Rossi", "X")]),
        (2, "Y", [_verdict("Nia Rossi (Staff)", "Y")]),
    ]
    loads = rl.review_load(prs, canon=canon)
    assert set(loads) == {"Nia Rossi"}
    assert loads["Nia Rossi"].verdicts == 2
    assert loads["Nia Rossi"].prs_reviewed == 2


# --------------------------------------------------------------- render_counts_line


def test_render_counts_line_sorted_and_labeled() -> None:
    loads = {
        "Tariq Morales": rl.ReviewLoad(verdicts=1, prs_reviewed=1),
        "Nia Rossi": rl.ReviewLoad(verdicts=2, prs_reviewed=2),
    }
    line = rl.render_counts_line(loads)
    assert line == "review-load (verdicts): Nia Rossi 2 / Tariq Morales 1"


def test_render_counts_line_empty_is_explicit() -> None:
    assert rl.render_counts_line({}) == "review-load (verdicts): (no reviewer verdicts)"
