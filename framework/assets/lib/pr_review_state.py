#!/usr/bin/env python3
"""Config-driven, fail-open N-reviewer approval-state oracle for a PR (#194).

The team's merge gate and trust scorer already agree on ONE review-verdict
grammar — the charter's ``Requestor:`` / ``Requestee:`` / ``RequestOrReplied:``
header plus a body ``Must-fix:`` / ``Tech-debt:`` severity split
(``.claude/team/charter/issues.md``). ``trust_signals.parse_verdicts`` is the
single parser for that grammar. This oracle does **not** re-implement any of it:
it consumes already-parsed :class:`trust_signals.Verdict` objects and computes a
pure state machine over them — the N-of-M approval state of a PR.

Reconcile, don't duplicate
==========================
This is deliberately NOT a blind port of another project's ``pr_review_state``
(which forked its own comment parsing). 2real evolved its own verdict grammar
and already parses it in one place; re-parsing here would fork that vocabulary
and let the oracle drift from the gate/scorer. So:

* **Parsing** is ``trust_signals``' job — the thin :func:`review_state` wrapper
  fetches a PR's comment bodies via ``trust_signals._pr_comment_bodies`` and
  parses them via ``trust_signals.parse_verdicts``.
* **The state machine** is this module's job — pure, no I/O, unit-testable on a
  hand-built ``list[Verdict]`` (:func:`compute_state`).

The amend-in-place convention (a reviewer edits their blocking
``Request`` / ``Must-fix:`` comment *in place* to ``Replied`` / ``Must-fix:
None`` once the fix lands — charter Reply Protocol) is handled for free: the
oracle reads the PR's **current** comment bodies, so an amended-clean verdict
parses with ``changes_requested=False`` and stops counting as an open must-fix
(and its author now counts toward approvals).

Reviewer identity
=================
Per the charter and ``trust_signals.extract_signals``, the **reviewer** is the
verdict comment's ``Requestor:`` field (``Requestee:`` is the addressed PR
author). Approvals are therefore counted over distinct **Requestors** whose
current verdict is clean (a ``Replied`` / non-``Must-fix`` review), NOT over
requestees. [PINNED-CONTRACT NOTE #194/#193: the frozen ``ReviewState`` *shape*
is honored exactly — ``state`` / ``approvals`` (int) / ``reviewers_required``
(int) / ``unresolved_must_fix`` (list). The contract's descriptive comment said
"distinct requestees"; the charter grammar makes the reviewer the ``Requestor``
(a requestee is the single PR author, so counting requestees could never reach a
2-reviewer bar), so this implementation counts distinct Requestors. Flagged to
Hiro on #193; the dict shape S2/S3 build against is unchanged.]

Fail-open posture (FAIL_OPEN = True)
====================================
This is a lib, not a hook, but it declares the same fail-open intent as the
Wave-3 dispatcher: an error must NEVER manufacture a false ``"approved"`` and
never hard-fail the caller.

* ``reviewers_required`` is read from ``policy.reviewers_required`` via the
  shared config, which fail-opens to its schema default (1) when the config is
  missing/unreadable; a non-integer/negative value or a config-load exception
  degrades to :data:`_FAIL_OPEN_REVIEWERS_REQUIRED`.
* :func:`review_state` catches comment-fetch / parse errors and returns an
  ``unknown`` state (approvals=0, no must-fix) rather than raising or inventing
  an approval — "couldn't determine the state" (#207/#214). This is
  deliberately NOT ``pending``: ``pending`` means the oracle *evaluated* the PR
  and found it genuinely not-yet-approved (a real, actionable state a caller
  should block on); ``unknown`` means the oracle *could not evaluate* the PR at
  all (a transient comment-fetch/transport error). Collapsing the two used to
  let a flaky GitHub API call read identically to a real "not approved" and
  BLOCK ``gh pr merge`` — the opposite of the fail-open promise. Callers (see
  ``validate_pr_review.py``) must treat ``unknown`` like an oracle exception:
  fail-open ALLOW, never block on it.

State machine (PINNED CONTRACT — frozen for S2/S3; ``unknown`` added #214)
==========================================================================
``ReviewState`` is a plain dict::

    {
      "state": "pending" | "changes_requested" | "approved" | "unknown",
      "approvals": int,            # distinct reviewers (Requestors) with a
                                   # current clean/approved verdict
      "reviewers_required": int,   # policy.reviewers_required (fail-open default)
      "unresolved_must_fix": list, # one entry per current changes-requested verdict
    }

    state == "approved"          iff approvals >= reviewers_required
                                     AND unresolved_must_fix == []
    state == "changes_requested" iff any current verdict carries an unresolved
                                     Must-fix (takes precedence over approvals)
    state == "unknown"           iff the oracle could not fetch/parse the PR's
                                     comments at all (fail-open — never
                                     produced by :func:`compute_state`, only by
                                     the :func:`review_state` I/O wrapper on a
                                     caught exception)
    else                             "pending"

    INVARIANT: the oracle must NEVER fabricate an "approved" verdict. On any
    doubt (including "unknown") it reports something a caller can safely
    fail-open on instead of a false approval.

CLI::

    python3 lib/pr_review_state.py <pr_number> --repo <owner/repo> [--json]

Exit codes: 0 approved, 1 otherwise (pending / changes_requested / unknown). The
I/O wrapper fail-opens to ``unknown`` on a fetch error (never ``pending``, and
never a fabricated ``approved``), so the CLI prints ``UNKNOWN`` / exit 1 in that
case — a caller scripting against this CLI's exit code should check ``--json``
``state`` if it needs to distinguish "not approved" from "couldn't tell".
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TypedDict

# trust_signals.py is a same-dir sibling (the canonical lib tree). It carries the
# single verdict parser (parse_verdicts) and the comment-fetch helper this oracle
# reuses; it also bridges to _framework_config in the sibling hooks dir. Mirror
# its own lib->hooks path bridge so this module is importable wherever the
# framework is deployed (in-place canonical, or a target's .claude/lib).
_LIB_DIR = Path(__file__).resolve().parent
_HOOKS_DIR = _LIB_DIR.parent / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))
sys.path.insert(0, str(_LIB_DIR))

import trust_signals as ts  # noqa: E402  (single verdict parser — no re-parse here)
from _framework_config import config  # noqa: E402

#: Fail-open declaration, consistent with the Wave-3 dispatcher convention. An
#: error must never manufacture a false "approved" nor hard-fail the caller.
FAIL_OPEN = True

#: Last-resort reviewers-required floor when the config cannot be read at all
#: (config() itself fail-opens to the schema default of 1, so this only bites on
#: a raised exception or a malformed value). One reviewer is the least-surprising
#: non-zero bar; a value of 0 would make an unreviewed PR read "approved".
_FAIL_OPEN_REVIEWERS_REQUIRED = 1

# The legal states, exported for callers/tests that assert the vocabulary.
PENDING = "pending"
CHANGES_REQUESTED = "changes_requested"
APPROVED = "approved"
#: "The oracle could not determine the state" (comment-fetch/transport error) —
#: NOT a synonym for PENDING. Produced only by :func:`review_state`'s exception
#: handler, never by :func:`compute_state`. Callers must fail-open ALLOW on this,
#: exactly like an oracle exception (#207/#214) — never fabricate "approved",
#: but also never let "couldn't tell" masquerade as "not approved" and block.
UNKNOWN = "unknown"


class MustFixEntry(TypedDict):
    """One open (unresolved) blocking verdict, at the granularity of a Verdict."""

    requestor: str | None
    requestee: str | None
    verdict: str | None


class ReviewState(TypedDict):
    """The pinned N-reviewer approval state of a PR (frozen shape — S2/S3)."""

    state: str
    approvals: int
    reviewers_required: int
    unresolved_must_fix: list[MustFixEntry]


def compute_state(
    verdicts: list[ts.Verdict], reviewers_required: int
) -> ReviewState:
    """Pure N-of-M approval state over already-parsed *verdicts*. No I/O.

    Consumes :class:`trust_signals.Verdict` objects (from
    ``trust_signals.parse_verdicts``) and applies the pinned state machine:

    * an **unresolved must-fix** is any current verdict with
      ``changes_requested=True`` (``trust_signals`` resolved the charter's
      body-severity rule at parse time). One entry per such verdict lands in
      ``unresolved_must_fix``. If any exist, the state is ``changes_requested``
      regardless of approval count.
    * **approvals** = the number of distinct reviewers (the ``Requestor:``
      identity) who have a current *clean* verdict and who do NOT currently
      carry an unresolved must-fix. Identities are folded with
      ``trust_signals._name_key`` so ``Tariq.Morales`` / ``Tariq Morales`` /
      ``Tariq Morales (QA)`` count once. A reviewer whose blocking comment was
      amended in place to ``Replied`` now parses clean and counts here.
    * ``approved`` requires ``approvals >= reviewers_required`` AND no unresolved
      must-fix; otherwise ``pending``.

    Pure and total: never raises on the parsed input, never does I/O.
    """
    unresolved: list[MustFixEntry] = [
        {
            "requestor": v.requestor,
            "requestee": v.requestee,
            "verdict": v.verdict,
        }
        for v in verdicts
        if v.changes_requested
    ]

    # A reviewer with any current blocking verdict is not counted as an approver,
    # even if they also left a separate clean comment — their standing review is
    # still "changes requested" until they amend it.
    blocking_reviewers = {
        ts._name_key(v.requestor)
        for v in verdicts
        if v.changes_requested and v.requestor
    }
    approvers: set[str] = set()
    for v in verdicts:
        if v.changes_requested or not v.requestor:
            continue
        key = ts._name_key(v.requestor)
        if key in blocking_reviewers:
            continue
        approvers.add(key)
    approvals = len(approvers)

    if unresolved:
        state = CHANGES_REQUESTED
    elif approvals >= reviewers_required:
        state = APPROVED
    else:
        state = PENDING

    return {
        "state": state,
        "approvals": approvals,
        "reviewers_required": reviewers_required,
        "unresolved_must_fix": unresolved,
    }


def _reviewers_required(cfg: Any = None) -> int:
    """``policy.reviewers_required`` from shared config; fail-open.

    ``config()`` already fail-opens to the schema default (1) on a
    missing/unreadable config. This adds a second guard: a config-load exception
    or a non-integer/negative value degrades to
    :data:`_FAIL_OPEN_REVIEWERS_REQUIRED` rather than raising or admitting a
    bar of 0 (which would read an unreviewed PR as "approved").
    """
    try:
        cfg = cfg if cfg is not None else config()
        val = cfg.get("policy.reviewers_required", _FAIL_OPEN_REVIEWERS_REQUIRED)
        n = int(val)
    except (ValueError, TypeError, OSError, AttributeError):
        return _FAIL_OPEN_REVIEWERS_REQUIRED
    return n if n >= 1 else _FAIL_OPEN_REVIEWERS_REQUIRED


def review_state(repo: str, pr: int, *, cfg: Any = None) -> ReviewState:
    """Thin I/O wrapper: fetch a PR's comments, parse them, compute the state.

    Delegates parsing to ``trust_signals.parse_verdicts`` (single verdict
    grammar) over the comment bodies from ``trust_signals._pr_comment_bodies``,
    reads ``reviewers_required`` from shared config, and returns the pinned
    :class:`ReviewState`.

    Fail-open: any comment-fetch / parse error returns an ``unknown`` state
    (approvals=0, no must-fix) rather than raising or inventing an approval — an
    error must never manufacture a false "approved". ``unknown`` is deliberately
    NOT ``pending``: it says "the oracle could not tell", which callers (the
    ``validate_pr_review`` gate) must treat as a fail-open ALLOW, exactly like a
    raised exception — a transient comment-fetch failure must never read as an
    ordinary "not approved" and BLOCK a merge (#207/#214).
    """
    required = _reviewers_required(cfg)
    try:
        bodies = ts._pr_comment_bodies(repo, int(pr))
        verdicts = ts.parse_verdicts(bodies)
    except Exception:  # noqa: BLE001 — fail-open: degrade to unknown, never raise
        return {
            "state": UNKNOWN,
            "approvals": 0,
            "reviewers_required": required,
            "unresolved_must_fix": [],
        }
    return compute_state(verdicts, required)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _render_text(repo: str, pr: int, state: ReviewState) -> str:
    lines = [
        f"PR #{pr} ({repo}) — review state: {state['state'].upper()}",
        f"  approvals: {state['approvals']}/{state['reviewers_required']} required",
    ]
    if state["unresolved_must_fix"]:
        lines.append(f"  unresolved must-fix verdicts: {len(state['unresolved_must_fix'])}")
        for mf in state["unresolved_must_fix"]:
            who = mf.get("requestor") or "(unknown reviewer)"
            lines.append(f"    - from {who}")
    else:
        lines.append("  unresolved must-fix verdicts: none")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pr_review_state",
        description=(
            "Compute a PR's N-reviewer approval state from the charter verdict "
            "grammar (parsed by trust_signals). Exit 0 if approved, 1 if not "
            "(pending / changes_requested)."
        ),
    )
    p.add_argument("pr_number", type=int, help="PR number to query")
    p.add_argument(
        "--repo",
        required=True,
        help="target repo as OWNER/NAME (e.g. acme/widget)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of the text report",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    state = review_state(args.repo, args.pr_number)
    if args.json:
        print(json.dumps(state, indent=2, sort_keys=True))
    else:
        print(_render_text(args.repo, args.pr_number, state))
    return 0 if state["state"] == APPROVED else 1


if __name__ == "__main__":
    raise SystemExit(main())
