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
# Author-exclusion (#293): the author's own self-verdict never counts toward the
# merge bar. Closes the live self-approval bypass — an author's clean
# `Requestor: <self>` supplied one of the required approvals on their own PR, so
# a single real reviewer + the author cleared a 2-reviewer bar.
# ---------------------------------------------------------------------------


def test_author_self_clean_verdict_excluded_bypass_repro():
    """Tariq's exact repro (#293): author self-verdict + ONE genuine reviewer at
    bar=2 must read `pending`, not `approved`.

    BEFORE #293 this was `approvals=2 / approved` — the author supplied one of
    the two "approvals" on their own PR. Mutation bar: neutralizing the
    author-exclusion (dropping the `is_author_self_review` filter) flips this
    back to approved -> fails.
    """
    verdicts = [
        _approval("Ibrahim.El-Amin"),  # author's own clean self-verdict
        _approval("Nia.Rossi"),  # the ONE genuine reviewer
    ]
    state = prs.compute_state(
        verdicts, reviewers_required=2, author="Ibrahim.El-Amin"
    )
    assert state["approvals"] == 1  # only Nia — the author self-verdict dropped
    assert state["state"] == "pending"


def test_two_genuine_reviewers_still_approved_with_author_set():
    """Author-exclusion must not tighten the gate for legitimate PRs: two
    genuine (non-author) reviewers still reach `approved` even when the author is
    threaded in.

    Mutation bar: an over-broad exclusion (e.g. excluding by Requestee, or
    dropping every verdict) would strip a real reviewer here -> fails.
    """
    verdicts = [_approval("Nia.Rossi"), _approval("Tariq.Morales")]
    state = prs.compute_state(
        verdicts, reviewers_required=2, author="Ibrahim.El-Amin"
    )
    assert state["approvals"] == 2
    assert state["state"] == "approved"


def test_author_self_must_fix_does_not_manufacture_a_blocking_reviewer():
    """An author's own `Must-fix` self-verdict is dropped entirely (#293): it
    creates NEITHER an unresolved-must-fix blocker NOR a phantom reviewer. An
    author can neither block nor approve their own PR.

    Here the author self-blocks and two genuine reviewers approve at bar=2 ->
    the self-block must not flip the state to changes_requested.

    Mutation bar: excluding the author only from `approvers` but NOT from
    `unresolved_must_fix` would leave the self-must-fix standing and read
    changes_requested -> fails.
    """
    verdicts = [
        _changes_requested("Ibrahim.El-Amin"),  # author self-`Must-fix`
        _approval("Nia.Rossi"),
        _approval("Tariq.Morales"),
    ]
    state = prs.compute_state(
        verdicts, reviewers_required=2, author="Ibrahim.El-Amin"
    )
    assert state["unresolved_must_fix"] == []  # self-block dropped, not standing
    assert state["approvals"] == 2  # the two genuine reviewers
    assert state["state"] == "approved"


def test_author_exclusion_folds_name_variants():
    """Author `Ibrahim El-Amin` and verdict `Requestor: Ibrahim.El-Amin` are the
    same person — the self-verdict is excluded despite the punctuation variant
    (default canon folds via `_name_key`, the same fold the approver set uses).

    Mutation bar: comparing raw (unfolded) strings would miss the variant and
    count the author self-verdict -> the bypass repro would reach approved.
    """
    verdicts = [
        _approval("Ibrahim.El-Amin"),  # author's self-verdict (dotted form)
        _approval("Nia.Rossi"),
    ]
    state = prs.compute_state(
        verdicts, reviewers_required=2, author="Ibrahim El-Amin"  # spaced form
    )
    assert state["approvals"] == 1
    assert state["state"] == "pending"


def test_author_none_fails_open_to_pre_293_count():
    """FAIL-OPEN: an unresolved author (`author=None`, the default) excludes
    nothing — behavior is exactly the pre-#293 count. A missing author must never
    tighten the gate into a false block.

    The bypass repro WITHOUT a resolved author still reaches `approved` (the
    pre-fix behavior), proving the exclusion is gated on a known author and never
    fabricated. Mutation bar: making author-exclusion fire on `author=None` (or
    raising) would flip this to pending -> fails.
    """
    verdicts = [_approval("Ibrahim.El-Amin"), _approval("Nia.Rossi")]

    # explicit None
    state = prs.compute_state(verdicts, reviewers_required=2, author=None)
    assert state["approvals"] == 2
    assert state["state"] == "approved"

    # default (author param omitted) — identical pre-#293 behavior
    state_default = prs.compute_state(verdicts, reviewers_required=2)
    assert state_default["approvals"] == 2
    assert state_default["state"] == "approved"


def test_review_state_wrapper_threads_author_and_excludes_self(monkeypatch):
    """End-to-end through the I/O wrapper: the head-commit author is fetched and
    threaded into `compute_state`, so an author self-verdict + one genuine
    reviewer at bar=2 reads `pending` — the live merge gate no longer counts a
    self-approval (#293).

    Mutation bar: reverting `review_state` to call `compute_state` without the
    fetched author flips this to approved -> fails.
    """
    author_body = (
        "Requestor: Ibrahim.El-Amin\nRequestee: Ibrahim.El-Amin\n"
        "RequestOrReplied: Replied\n\n**Review: self-check**\n"
        "Must-fix: None\nTech-debt: None\n"
    )
    reviewer_body = (
        "Requestor: Nia.Rossi\nRequestee: Ibrahim.El-Amin\n"
        "RequestOrReplied: Replied\n\n**Review: LGTM**\n"
        "Must-fix: None\nTech-debt: None\n"
    )
    monkeypatch.setattr(
        ts, "_pr_comment_bodies", lambda _repo, _num: [author_body, reviewer_body]
    )
    monkeypatch.setattr(prs, "_pr_head_author", lambda _repo, _num: "Ibrahim.El-Amin")

    class _Cfg:
        def get(self, _dotted, default=None):
            return 2

    state = prs.review_state("acme/widget", 42, cfg=_Cfg())
    assert state["approvals"] == 1  # only Nia; the author self-verdict excluded
    assert state["state"] == "pending"


def test_review_state_wrapper_author_fetch_failure_fails_open(monkeypatch):
    """If the author cannot be resolved (`_pr_head_author` -> None), the wrapper
    excludes nothing and computes the pre-#293 state — an author-fetch failure
    must never manufacture a false block or an `unknown`. Two clean Requestors
    (one of whom happens to be the real author) still reach `approved`.

    Mutation bar: turning an author-fetch failure into a block/unknown would flip
    this off `approved` -> fails.
    """
    body_a = (
        "Requestor: Ibrahim.El-Amin\nRequestee: Ibrahim.El-Amin\n"
        "RequestOrReplied: Replied\n\n**Review: self**\nMust-fix: None\nTech-debt: None\n"
    )
    body_b = (
        "Requestor: Nia.Rossi\nRequestee: Ibrahim.El-Amin\n"
        "RequestOrReplied: Replied\n\n**Review: LGTM**\nMust-fix: None\nTech-debt: None\n"
    )
    monkeypatch.setattr(ts, "_pr_comment_bodies", lambda _repo, _num: [body_a, body_b])
    monkeypatch.setattr(prs, "_pr_head_author", lambda _repo, _num: None)

    class _Cfg:
        def get(self, _dotted, default=None):
            return 2

    state = prs.review_state("acme/widget", 42, cfg=_Cfg())
    assert state["state"] == "approved"  # fail-open: no exclusion
    assert state["approvals"] == 2


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


def test_review_state_wrapper_fail_opens_to_unknown_on_fetch_error(monkeypatch):
    """A comment-fetch error returns "unknown" — never a raised exception,
    never a manufactured "approved", and (#207/#214) NOT masked as an ordinary
    "pending". "pending" means the oracle evaluated the PR and found it
    genuinely not-yet-approved; "unknown" means it couldn't evaluate the PR at
    all (a transient fetch/transport error). Collapsing the two used to let a
    flaky GitHub API call block `gh pr merge` exactly like a real "not
    approved" — the opposite of a fail-open gate.

    Mutation bar: reverting the except-handler in `review_state` back to
    `state=PENDING` makes this fail.
    """

    def _boom(_repo, _num):
        raise RuntimeError("gh exploded")

    monkeypatch.setattr(ts, "_pr_comment_bodies", _boom)

    class _Cfg:
        def get(self, _dotted, default=None):
            return 1

    state = prs.review_state("acme/widget", 7, cfg=_Cfg())
    assert state["state"] == "unknown"
    assert state["state"] == prs.UNKNOWN
    assert state["state"] != "pending"
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
    # Keep hermetic: author-exclusion (#293) added a head-commit author fetch to
    # the wrapper; stub it (no genuine reviewer here is the author) so the test
    # never shells out to a live `gh`.
    monkeypatch.setattr(prs, "_pr_head_author", lambda _repo, _num: None)

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
    monkeypatch.setattr(prs, "_pr_head_author", lambda _repo, _num: None)

    class _Cfg:
        def get(self, _dotted, default=None):
            return 1

    state = prs.review_state("acme/widget", 99, cfg=_Cfg())
    assert state["state"] == "changes_requested"
    assert len(state["unresolved_must_fix"]) == 1


# ---------------------------------------------------------------------------
# N=2 end-to-end matrix (#203): the three review outcomes at reviewers_required=2,
# driven through the full fetch→parse→compute chain on charter-format bodies whose
# shape is taken from the real wave-6 multi-reviewer PR (#206: two distinct clean
# Requestors — Nia.Rossi + Tariq.Morales) and a real blocking verdict (#93 shape).
# This is the regression anchor for the live proof captured in the #203 PR body:
# the oracle's N-of-M path, exercised end-to-end rather than only on hand-built
# Verdict objects.
# ---------------------------------------------------------------------------

# Two distinct clean Requestors — the exact shape PR #206 carries.
_N2_CLEAN_TARIQ = (
    "Requestor: Tariq.Morales\nRequestee: Paloma.Gupta\nRequestOrReplied: Replied\n\n"
    "**Review: verified — ships as-is**\nMust-fix: None\nTech-debt: None\n"
)
_N2_CLEAN_NIA = (
    "Requestor: Nia.Rossi\nRequestee: Paloma.Gupta\nRequestOrReplied: Replied\n\n"
    "**Review: LGTM — ships as-is**\nMust-fix: None\nTech-debt: None\n"
)
# A real blocking verdict (bold Must-fix label, one enumerated item — the #93 shape).
_N2_MUSTFIX_NIA = (
    "Requestor: Nia.Rossi\nRequestee: Paloma.Gupta\nRequestOrReplied: Request\n\n"
    "**Review: one must-fix**\n**Must-fix:**\n1. Correct the recorded numbers.\n"
    "**Tech-debt:** None\n"
)


def _n2_state(bodies, monkeypatch):
    monkeypatch.setattr(ts, "_pr_comment_bodies", lambda _repo, _num: bodies)
    # Hermetic: stub the #293 head-commit author fetch (none of these Requestors
    # is the PR author) so the wrapper never shells out to a live `gh`.
    monkeypatch.setattr(prs, "_pr_head_author", lambda _repo, _num: None)

    class _Cfg:  # reviewers_required = 2 (the standing N=2 bar)
        def get(self, _dotted, default=None):
            return 2

    return prs.review_state("acme/widget", 206, cfg=_Cfg())


def test_n2_two_distinct_clean_requestors_approved(monkeypatch):
    """2 distinct clean Requestors ⇒ approved, approvals=2 (the PR #206 case)."""
    state = _n2_state([_N2_CLEAN_TARIQ, _N2_CLEAN_NIA], monkeypatch)
    assert state["state"] == "approved"
    assert state["approvals"] == 2
    assert state["reviewers_required"] == 2
    assert state["unresolved_must_fix"] == []


def test_n2_one_clean_one_unresolved_mustfix_changes_requested(monkeypatch):
    """1 clean + 1 unresolved Must-fix ⇒ changes_requested (must-fix precedence)."""
    state = _n2_state([_N2_CLEAN_TARIQ, _N2_MUSTFIX_NIA], monkeypatch)
    assert state["state"] == "changes_requested"
    assert state["approvals"] == 1  # the clean reviewer still counts
    assert len(state["unresolved_must_fix"]) == 1


def test_n2_one_clean_only_pending(monkeypatch):
    """1 clean approval only ⇒ pending (approvals below the required 2)."""
    state = _n2_state([_N2_CLEAN_TARIQ], monkeypatch)
    assert state["state"] == "pending"
    assert state["approvals"] == 1
    assert state["reviewers_required"] == 2
