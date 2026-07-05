"""Tests for trust_signals.py verdict-vocabulary parsing (issue #98).

The regression these tests pin: the extraction layer used to count a must-fix
only when a verdict comment read ``RequestOrReplied: ChangesRequested``. This
project's charter (``.claude/team/charter/issues.md``) instead writes
``RequestOrReplied: Request | Replied`` and carries the review *severity* in the
comment body as an enumerated ``Must-fix:`` list. Under the old vocabulary every
real review read as zero. These tests assert the charter vocabulary now scores,
the legacy machine token still scores, and clean reviews / replies do not.

Fixtures are trimmed but shape-faithful to the real Phase 3 PR comments the
issue names (#79, #78, #96, #93). Pure functions only — no gh, no I/O.
"""

from __future__ import annotations

import sys
from pathlib import Path

# trust_signals.py lives in the canonical framework asset tree; its scoring /
# parsing half is pure. Put both the lib dir and its sibling hooks dir (the
# module bridges to _framework_config at import time) on the path.
_LIB = Path(__file__).resolve().parent.parent / "assets" / "lib"
_HOOKS = Path(__file__).resolve().parent.parent / "assets" / "hooks"
sys.path.insert(0, str(_HOOKS))
sys.path.insert(0, str(_LIB))

import trust_signals as ts  # noqa: E402

# ---------------------------------------------------------------------------
# Real-corpus fixtures (trimmed from the Phase 3 PRs the issue names).
# ---------------------------------------------------------------------------

# PR #79 — Tariq's blocking review: a `Request` with an enumerated Must-fix list.
PR79_REQUEST = """Requestor: Tariq Morales (QA)
Requestee: Paloma Gupta
RequestOrReplied: Request

**Review: issues (one must-fix — merge conflict with the moved base)**

Must-fix:
1. **Rebase required — PR is CONFLICTING against the base** (`mergeable: DIRTY`).
   The base moved after you branched; resolve and re-run both suites.

Tech-debt: None filed.
"""

# PR #79 — Paloma's reply. Mentions "must-fix" in prose but is a `Replied`, and
# carries no Must-fix section of its own → clean, not a changes-requested.
PR79_REPLY = """Requestor: Paloma Gupta (Principal SWE)
Requestee: Tariq Morales (QA)
RequestOrReplied: Replied

**Rebase + semantic reconciliation done — ready for re-review.** How the #71
overlap was resolved (semantic, per your must-fix): the ontology block is now
gated on the resolved `ontology.enabled`. Suites green.
"""

# PR #96 — Tariq's blocking review: bare `Must-fix:` label, two enumerated items.
PR96_REQUEST = """Requestor: Tariq Morales (QA)
Requestee: Ibrahim El-Amin
RequestOrReplied: Request

Must-fix:
1. **Permissions-allowlist claim is factually wrong.** Reword to match README.
2. **Ontology meta/child wording overstates.** Children deliberately get none.

Tech-debt: None.
"""

# PR #96 — Tariq's approval, posted as a `Replied` with an explicit empty
# Must-fix value → clean.
PR96_APPROVE = """Requestor: Tariq Morales (QA)
Requestee: Ibrahim El-Amin
RequestOrReplied: Replied

**Review: LGTM — APPROVE.** Fix commit confirmed; CI 11/11 green.

Must-fix: None (all resolved)
Tech-debt: None
"""

# PR #93 — Nia's review: **bold** Must-fix label, one enumerated item.
PR93_REQUEST = """Requestor: Nia.Rossi
Requestee: Tariq.Morales
RequestOrReplied: Request

**Review: LGTM with one must-fix (PR-body record correction — no code change)**

**Must-fix:**
1. Edit the PR body's QA-evidence line to record the corrected pytest numbers.

**Tech-debt:** filed as #94.
"""


# ---------------------------------------------------------------------------
# _has_must_fix_items — the body-severity detector.
# ---------------------------------------------------------------------------


def test_must_fix_bare_label_with_numbered_list():
    assert ts._has_must_fix_items("Must-fix:\n1. Do the thing") is True


def test_must_fix_bold_label_with_numbered_list():
    assert ts._has_must_fix_items("**Must-fix:**\n1. Do the thing") is True


def test_must_fix_label_with_dash_bullet():
    assert ts._has_must_fix_items("Must-fix:\n- fix this") is True


def test_must_fix_inline_item():
    assert ts._has_must_fix_items("Must-fix: rebase against the moved base") is True


def test_must_fix_blank_line_before_list():
    assert ts._has_must_fix_items("Must-fix:\n\n1. item after a blank line") is True


def test_must_fix_none_inline_is_empty():
    assert ts._has_must_fix_items("Must-fix: None") is False


def test_must_fix_none_with_trailer_is_empty():
    assert ts._has_must_fix_items("Must-fix: None (all resolved)") is False


def test_must_fix_na_and_dash_and_zero_are_empty():
    assert ts._has_must_fix_items("Must-fix: N/A") is False
    assert ts._has_must_fix_items("Must-fix: -") is False
    assert ts._has_must_fix_items("Must-fix: 0") is False


def test_no_must_fix_label_at_all():
    assert ts._has_must_fix_items("Just a plain comment, no findings here.") is False


def test_must_fix_hyphen_and_space_spelling_variants():
    assert ts._has_must_fix_items("Must fix:\n1. item") is True
    assert ts._has_must_fix_items("mustfix:\n1. item") is True


def test_must_fix_inside_code_span_is_ignored():
    # A `Must-fix:` token that only appears inside a code span / fenced block is
    # not a real finding.
    assert ts._has_must_fix_items("See `Must-fix: None` in the grammar spec.") is False
    assert (
        ts._has_must_fix_items("```\nMust-fix:\n1. sample\n```\nAll good, no findings.")
        is False
    )


# ---------------------------------------------------------------------------
# _is_changes_requested — token + body resolution.
# ---------------------------------------------------------------------------


def test_request_with_must_fix_is_changes_requested():
    assert ts._is_changes_requested("Request", "Must-fix:\n1. fix it") is True


def test_request_without_must_fix_is_clean():
    assert ts._is_changes_requested("Request", "Must-fix: None") is False
    assert ts._is_changes_requested("Request", "looks good, shipping") is False


def test_replied_is_never_changes_requested_even_with_must_fix_prose():
    # A reply is the response turn — the must-fix was raised in the paired
    # Request, not here.
    assert ts._is_changes_requested("Replied", "resolved your must-fix items") is False
    assert ts._is_changes_requested("Replied", "Must-fix: None (all resolved)") is False


def test_legacy_changesrequested_token_still_scores():
    assert ts._is_changes_requested("ChangesRequested", "") is True
    assert ts._is_changes_requested("changesrequested", "") is True


def test_legacy_approved_token_is_clean():
    assert ts._is_changes_requested("Approved", "") is False


def test_none_verdict_is_clean():
    assert ts._is_changes_requested(None, "Must-fix:\n1. x") is False


# ---------------------------------------------------------------------------
# parse_verdicts over the real-corpus shapes.
# ---------------------------------------------------------------------------


def test_parse_blocking_request_sets_changes_requested():
    (v,) = ts.parse_verdicts([PR79_REQUEST])
    assert v.requestor == "Tariq Morales (QA)"
    assert v.requestee == "Paloma Gupta"
    assert v.verdict == "Request"
    assert v.changes_requested is True
    assert v.false_positive is False


def test_parse_reply_is_not_changes_requested():
    (v,) = ts.parse_verdicts([PR79_REPLY])
    assert v.verdict == "Replied"
    assert v.changes_requested is False


def test_parse_bold_label_request():
    (v,) = ts.parse_verdicts([PR93_REQUEST])
    assert v.verdict == "Request"
    assert v.changes_requested is True


def test_parse_approval_reply_is_clean():
    (v,) = ts.parse_verdicts([PR96_APPROVE])
    assert v.verdict == "Replied"
    assert v.changes_requested is False


def test_parse_skips_non_verdict_comments():
    assert ts.parse_verdicts(["just a plain comment with no verdict line"]) == []


# ---------------------------------------------------------------------------
# End-to-end accounting: the per-PR loop extract_signals runs, exercised on the
# real corpus without touching gh. Proves review signals now score non-zero.
# ---------------------------------------------------------------------------


def _account(pr_comment_sets: dict[str, tuple[str, list[str]]]) -> dict[str, ts.Signals]:
    """Mirror extract_signals' per-PR verdict accounting, pure (no gh).

    ``pr_comment_sets`` maps pr-id -> (author_name, [comment_bodies]).
    """
    signals: dict[str, ts.Signals] = {}

    def bucket(name: str) -> ts.Signals:
        return signals.setdefault(name, ts.Signals())

    for _pr, (author, bodies) in pr_comment_sets.items():
        author_sig = bucket(author)
        author_sig.prs_merged += 1
        had_cr = False
        for v in ts.parse_verdicts(bodies):
            if v.changes_requested:
                had_cr = True
                author_sig.must_fix_received += 1
                if v.requestor:
                    bucket(v.requestor).must_fix_caught += 1
            if v.false_positive and v.requestor:
                bucket(v.requestor).review_false_positives += 1
        if had_cr:
            author_sig.rework_cycles += 1
    return signals


def test_real_corpus_scores_review_signals_non_zero():
    sigs = _account(
        {
            "79": ("Paloma Gupta", [PR79_REQUEST, PR79_REPLY]),
            "96": ("Ibrahim El-Amin", [PR96_REQUEST, PR96_APPROVE]),
            "93": ("Tariq.Morales", [PR93_REQUEST]),
        }
    )

    # The whole point of the fix: the review-quality half is no longer dark.
    total_received = sum(s.must_fix_received for s in sigs.values())
    total_caught = sum(s.must_fix_caught for s in sigs.values())
    total_rework = sum(s.rework_cycles for s in sigs.values())
    assert total_received > 0
    assert total_caught > 0
    assert total_rework > 0

    # Authors of blocked PRs carry the negative author signal + a rework cycle.
    assert sigs["Paloma Gupta"].must_fix_received == 1
    assert sigs["Paloma Gupta"].rework_cycles == 1
    assert sigs["Ibrahim El-Amin"].must_fix_received == 1

    # Reviewers who raised the must-fix carry the positive review signal.
    assert sigs["Tariq Morales (QA)"].must_fix_caught == 2  # caught on #79 and #96
    assert sigs["Nia.Rossi"].must_fix_caught == 1


def test_old_vocabulary_would_have_scored_zero():
    """Guards the regression direction: the legacy token-only rule (verdict ==
    'ChangesRequested') matches none of the charter corpus, so every review
    signal would read zero — which is exactly the #98 bug."""
    for body in (PR79_REQUEST, PR79_REPLY, PR96_REQUEST, PR96_APPROVE, PR93_REQUEST):
        (v,) = ts.parse_verdicts([body])
        # None of these carry the literal machine token.
        assert v.verdict.lower() != "changesrequested"
    # Yet under the new body-aware rule, the blocking ones do resolve.
    assert ts.parse_verdicts([PR79_REQUEST])[0].changes_requested is True


# ---------------------------------------------------------------------------
# Scoring composition — a blocked author is not handed a uniform +1.
# ---------------------------------------------------------------------------


def test_score_delta_discriminates_clean_reviewer_from_blocked_author():
    # Clean reviewer with 2 catches and 2 clean PRs → +1 (or better).
    reviewer = ts.Signals(prs_merged=2, must_fix_caught=2)
    # Author who took must-fixes is not "clean" → no positive bump.
    author = ts.Signals(prs_merged=2, must_fix_received=1, rework_cycles=1)
    assert ts.score_delta(reviewer) >= 1
    assert ts.score_delta(author) <= 0
