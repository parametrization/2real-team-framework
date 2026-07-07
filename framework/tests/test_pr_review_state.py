"""Load-bearing tests for pr_review_state.py — the N-reviewer approval oracle (#194).

The oracle is a PURE state machine (:func:`compute_state`) over already-parsed
``trust_signals.Verdict`` objects, plus a thin fail-open I/O wrapper
(:func:`review_state`) that reuses ``trust_signals`` for comment fetch + verdict
parsing (it does NOT re-implement charter-comment parsing).

These tests are the mutation bar for the transition truth table:

  pending -> changes_requested -> approved,
  the amend-in-place Request->Replied convention,
  N-of-M distinct-reviewer approvals,
  and an unresolved Must-fix blocking "approved" even at N approvals.

Reverting any of the transition logic in ``compute_state`` (drop the
must-fix-precedence branch, flip ``>=`` to ``>``, stop excluding a
currently-blocking reviewer, or stop folding distinct reviewer names) makes at
least one test here fail. Every case builds ``Verdict`` lists directly — no live
``gh``, no I/O. The two wrapper tests monkeypatch the comment-fetch helper to
prove the wrapper reuses ``parse_verdicts`` and fail-opens.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Mirror test_trust_signals.py's path bridge: the canonical lib tree plus its
# sibling hooks dir (the modules bridge to _framework_config at import time).
_LIB = Path(__file__).resolve().parent.parent / "assets" / "lib"
_HOOKS = Path(__file__).resolve().parent.parent / "assets" / "hooks"
sys.path.insert(0, str(_HOOKS))
sys.path.insert(0, str(_LIB))

import pr_review_state as prs  # noqa: E402
import trust_signals as ts  # noqa: E402


# ---------------------------------------------------------------------------
# Verdict builders (pure — the state machine's real input shape).
# ---------------------------------------------------------------------------


def _approval(requestor: str, requestee: str = "Paloma.Gupta") -> ts.Verdict:
    """A clean/approving verdict (``Replied``, no must-fix) by *requestor*."""
    return ts.Verdict(
        requestor=requestor,
        requestee=requestee,
        verdict="Replied",
        false_positive=False,
        changes_requested=False,
    )


def _changes_requested(requestor: str, requestee: str = "Paloma.Gupta") -> ts.Verdict:
    """A blocking verdict (``Request`` + enumerated must-fix) by *requestor*."""
    return ts.Verdict(
        requestor=requestor,
        requestee=requestee,
        verdict="Request",
        false_positive=False,
        changes_requested=True,
    )


# ---------------------------------------------------------------------------
# Transition truth table (pure compute_state).
# ---------------------------------------------------------------------------


def test_pending_when_no_approvals_and_no_must_fix():
    """No verdicts at all, one reviewer required -> pending (never approved)."""
    state = prs.compute_state([], reviewers_required=1)
    assert state["state"] == "pending"
    assert state["approvals"] == 0
    assert state["unresolved_must_fix"] == []


def test_pending_when_approvals_below_required():
    """1 distinct approval but 2 required -> pending (the N-of-M lower edge)."""
    state = prs.compute_state([_approval("Nia.Rossi")], reviewers_required=2)
    assert state["state"] == "pending"
    assert state["approvals"] == 1


def test_approved_at_exactly_required():
    """approvals == reviewers_required with no must-fix -> approved (the >= edge).

    Mutation bar: flipping ``approvals >= reviewers_required`` to ``>`` makes
    this exact-threshold case read pending -> this test fails.
    """
    state = prs.compute_state([_approval("Nia.Rossi")], reviewers_required=1)
    assert state["state"] == "approved"
    assert state["approvals"] == 1


def test_changes_requested_when_any_unresolved_must_fix():
    """Any current blocking verdict -> changes_requested, and it is enumerated."""
    verdicts = [_changes_requested("Tariq.Morales")]
    state = prs.compute_state(verdicts, reviewers_required=1)
    assert state["state"] == "changes_requested"
    assert len(state["unresolved_must_fix"]) == 1
    assert state["unresolved_must_fix"][0]["requestor"] == "Tariq.Morales"


def test_unresolved_must_fix_blocks_approved_even_at_n_approvals():
    """N distinct approvals but one open must-fix -> changes_requested, NOT approved.

    Mutation bar: dropping the ``if unresolved: changes_requested`` precedence
    branch (letting the approval count win) flips this to approved -> fails.
    """
    verdicts = [
        _approval("Nia.Rossi"),
        _approval("Ibrahim.El-Amin"),
        _changes_requested("Tariq.Morales"),
    ]
    state = prs.compute_state(verdicts, reviewers_required=2)
    assert state["approvals"] == 2  # the two clean reviewers still counted
    assert state["state"] == "changes_requested"


# ---------------------------------------------------------------------------
# N-of-M distinct-reviewer approvals.
# ---------------------------------------------------------------------------


def test_n_of_m_needs_two_distinct_reviewers():
    """reviewers_required=2 needs 2 DISTINCT reviewers; two comments from one
    reviewer do not reach the bar.

    Mutation bar: counting raw clean-verdict comments instead of DISTINCT
    reviewer identities would read this (2 comments, 1 person) as approved ->
    fails.
    """
    one_person_twice = [_approval("Nia.Rossi"), _approval("Nia.Rossi")]
    state = prs.compute_state(one_person_twice, reviewers_required=2)
    assert state["approvals"] == 1
    assert state["state"] == "pending"

    two_people = [_approval("Nia.Rossi"), _approval("Ibrahim.El-Amin")]
    state = prs.compute_state(two_people, reviewers_required=2)
    assert state["approvals"] == 2
    assert state["state"] == "approved"


def test_distinct_reviewers_fold_name_variants():
    """``Tariq.Morales`` / ``Tariq Morales`` / ``Tariq Morales (QA)`` are ONE
    reviewer, not three.

    Mutation bar: dropping the ``_name_key`` folding counts the variants as 3
    distinct approvers and wrongly reaches a 2-reviewer bar -> fails.
    """
    variants = [
        _approval("Tariq.Morales"),
        _approval("Tariq Morales"),
        _approval("Tariq Morales (QA)"),
    ]
    state = prs.compute_state(variants, reviewers_required=2)
    assert state["approvals"] == 1
    assert state["state"] == "pending"


# ---------------------------------------------------------------------------
# Amend-in-place Request -> Replied convention.
# ---------------------------------------------------------------------------


def test_amend_in_place_request_to_replied_clears_and_counts_as_approval():
    """A reviewer's blocking Request, once amended in place to a clean Replied,
    stops blocking AND now counts toward approvals.

    The amendment edits the SAME comment, so re-parsing the PR's current bodies
    yields a clean verdict for that reviewer. Modelled as before/after Verdict
    lists (compute_state is pure over the CURRENT parse).
    """
    # BEFORE the fix lands: Tariq blocks, Nia approves. required=2.
    before = [_changes_requested("Tariq.Morales"), _approval("Nia.Rossi")]
    s_before = prs.compute_state(before, reviewers_required=2)
    assert s_before["state"] == "changes_requested"
    assert s_before["approvals"] == 1  # only Nia; Tariq is currently blocking

    # AFTER Tariq amends his Request -> Replied in place (now clean).
    after = [_approval("Tariq.Morales"), _approval("Nia.Rossi")]
    s_after = prs.compute_state(after, reviewers_required=2)
    assert s_after["unresolved_must_fix"] == []
    assert s_after["approvals"] == 2
    assert s_after["state"] == "approved"


def test_blocking_reviewer_not_double_counted_as_approver():
    """A reviewer who left BOTH a clean note and a still-open must-fix is not an
    approver — their standing review is changes-requested until amended.

    Mutation bar: dropping the ``blocking_reviewers`` exclusion counts that
    reviewer as an approver -> this test's approvals assertion fails.
    """
    verdicts = [
        _approval("Tariq.Morales"),  # an earlier clean note
        _changes_requested("Tariq.Morales"),  # a later, still-open block
    ]
    state = prs.compute_state(verdicts, reviewers_required=1)
    assert state["state"] == "changes_requested"
    assert state["approvals"] == 0


# ---------------------------------------------------------------------------
# Fail-open posture.
# ---------------------------------------------------------------------------


def test_reviewers_required_fail_open_defaults():
    """A None/garbage/zero policy value degrades to the fail-open floor, never 0
    (a 0 bar would read an unreviewed PR as approved)."""

    class _Cfg:
        def __init__(self, val):
            self._val = val

        def get(self, _dotted, default=None):
            return self._val if self._val is not None else default

    assert prs._reviewers_required(_Cfg(None)) == prs._FAIL_OPEN_REVIEWERS_REQUIRED
    assert prs._reviewers_required(_Cfg("nonsense")) == prs._FAIL_OPEN_REVIEWERS_REQUIRED
    assert prs._reviewers_required(_Cfg(0)) == prs._FAIL_OPEN_REVIEWERS_REQUIRED
    assert prs._reviewers_required(_Cfg(3)) == 3


def test_review_state_wrapper_fail_opens_to_pending_on_fetch_error(monkeypatch):
    """A comment-fetch error returns pending — never a raised exception and
    never a manufactured 'approved'."""

    def _boom(_repo, _num):
        raise RuntimeError("gh exploded")

    monkeypatch.setattr(ts, "_pr_comment_bodies", _boom)

    class _Cfg:
        def get(self, _dotted, default=None):
            return 1

    state = prs.review_state("acme/widget", 7, cfg=_Cfg())
    assert state["state"] == "pending"
    assert state["approvals"] == 0
    assert state["unresolved_must_fix"] == []


def test_review_state_wrapper_reuses_parse_verdicts(monkeypatch):
    """End-to-end through the wrapper on REAL charter-format comment bodies:
    proves the oracle reuses ``trust_signals.parse_verdicts`` (no re-parse) and
    produces the same verdict semantics — two clean approvals reach approved."""

    nia = (
        "Requestor: Nia.Rossi\nRequestee: Paloma.Gupta\nRequestOrReplied: Replied\n\n"
        "**Review: LGTM — ships as-is**\nMust-fix: None\nTech-debt: None\n"
    )
    ibrahim = (
        "Requestor: Ibrahim.El-Amin\nRequestee: Paloma.Gupta\nRequestOrReplied: Replied\n\n"
        "**Review: looks good**\nMust-fix: None\nTech-debt: None\n"
    )

    monkeypatch.setattr(ts, "_pr_comment_bodies", lambda _repo, _num: [nia, ibrahim])

    class _Cfg:
        def get(self, _dotted, default=None):
            return 2

    state = prs.review_state("acme/widget", 42, cfg=_Cfg())
    assert state["approvals"] == 2
    assert state["reviewers_required"] == 2
    assert state["state"] == "approved"


def test_review_state_wrapper_surfaces_must_fix_from_real_body(monkeypatch):
    """A real charter ``Request`` + enumerated ``Must-fix:`` body flows through
    parse_verdicts to a changes_requested state (severity read from the body,
    not the token — the charter's rule, applied by trust_signals)."""

    blocking = (
        "Requestor: Tariq.Morales\nRequestee: Paloma.Gupta\nRequestOrReplied: Request\n\n"
        "**Review: one must-fix**\nMust-fix:\n1. Rebase — the branch is CONFLICTING.\n"
        "Tech-debt: None\n"
    )

    monkeypatch.setattr(ts, "_pr_comment_bodies", lambda _repo, _num: [blocking])

    class _Cfg:
        def get(self, _dotted, default=None):
            return 1

    state = prs.review_state("acme/widget", 99, cfg=_Cfg())
    assert state["state"] == "changes_requested"
    assert len(state["unresolved_must_fix"]) == 1
