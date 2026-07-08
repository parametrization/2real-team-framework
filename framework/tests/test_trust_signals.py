"""Tests for trust_signals.py — verdict-vocabulary parsing (#98) and phase-aware
integration-branch resolution (#100).

Two independent concerns share this module because they exercise the same lib:

* **Verdict vocabulary (#98)** — the extraction layer used to count a must-fix
  only when a verdict comment read ``RequestOrReplied: ChangesRequested``. This
  project's charter (``.claude/team/charter/issues.md``) instead writes
  ``RequestOrReplied: Request | Replied`` and carries the review *severity* in
  the comment body as an enumerated ``Must-fix:`` list. Under the old vocabulary
  every real review read as zero. These tests assert the charter vocabulary now
  scores, the legacy machine token still scores, and clean reviews / replies do
  not. Fixtures are trimmed but shape-faithful to the real Phase 3 PR comments
  the issue names (#79, #78, #96, #93). Pure functions only — no gh, no I/O.

* **Integration-branch resolution (#100)** — the ``branch.integration`` template
  that scopes the merged-PR set must substitute both ``{phase}`` and ``{wave}``;
  phase is resolved from ``wave_<id>_phase`` in the state file, and
  unknown/unresolved tokens degrade to a literal placeholder rather than raising.
  No network (``_integration_base`` / ``_phase_for_wave`` are pure aside from an
  optional state-file read).
"""

from __future__ import annotations

import json
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
# review_false_positives must-fix gate (#131).
#
# A review false-positive is, by contract, a Must-fix item the reviewer RAISED
# that was later withdrawn. Retraction vocabulary in a comment that raised no
# must-fix item is not a retraction and must not score.
# ---------------------------------------------------------------------------

# PR #115 — Nia's approval, posted as a `Replied` with `Must-fix: None`. Its
# Tech-debt line carries the phrase "false-positive watch" — a forward-looking
# note about a hypothetical gate weakness, NOT a retraction of anything she
# raised. Exact shape from the live #131 repro.
PR115_CLEAN_APPROVAL = """Requestor: Nia Rossi
Requestee: Paloma Gupta
RequestOrReplied: Replied

**Review: LGTM — APPROVE.** CI green; the trust-gate change reads correctly.

Must-fix: None
Tech-debt: Minor false-positive watch (accept as-is) — the retraction heuristic
could over-match forward-looking prose; worth a follow-up but not blocking here.
"""

# A comment that DID raise a Must-fix finding and, in the same comment, retracts
# it as a false-positive → still a genuine review false-positive (don't
# over-correct and break the real signal).
PR_RETRACTED_MUST_FIX = """Requestor: Tariq Morales (QA)
Requestee: Ibrahim El-Amin
RequestOrReplied: Request

Must-fix:
1. The allowlist claim looks wrong here.

On second read this was a false-positive — the README already matches. Withdrawing.
"""


def test_clean_approval_with_false_positive_watch_scores_zero():
    # Regression for #131: `Must-fix: None` + "false-positive watch" prose must
    # NOT be counted as a review false-positive.
    (v,) = ts.parse_verdicts([PR115_CLEAN_APPROVAL])
    assert v.verdict == "Replied"
    assert v.changes_requested is False
    assert v.false_positive is False


def test_retracted_must_fix_still_counts_as_false_positive():
    # Positive case: a comment that raised a must-fix and then retracts it in
    # the same body still scores — the real signal is preserved.
    (v,) = ts.parse_verdicts([PR_RETRACTED_MUST_FIX])
    assert v.changes_requested is True
    assert v.false_positive is True


def test_extract_shape_clean_reviewer_no_false_positive():
    # End-to-end over parse_verdicts: the #115 shape yields
    # review_false_positives == 0 for the reviewer.
    fp = 0
    for v in ts.parse_verdicts([PR115_CLEAN_APPROVAL]):
        if v.false_positive and v.requestor:
            fp += 1
    assert fp == 0


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


# ===========================================================================
# Roster name normalization (#119): identity captured as `First.Last`,
# `First Last`, and `First Last (Role)` must fold to one canonical roster
# identity before bucketing; a name absent from the roster passes through.
# ===========================================================================


class _RosterCfg:
    """Config stub with a `.path` so `_roster_names` can resolve the roster file.

    The real config lives at `<repo>/.claude/framework.config.json`, so
    `cfg.path.parent.parent` is the repo root. Mirrors that layout under tmp.
    """

    def __init__(self, path: Path, values: dict | None = None) -> None:
        self.path = path
        self._v = values or {}

    def get(self, key: str, default=None):
        return self._v.get(key, default)


def _roster_cfg(tmp_path: Path, roster: dict[str, str]) -> _RosterCfg:
    """Write a roster at the default `identity.roster_source` and return a cfg."""
    claude = tmp_path / ".claude"
    (claude / "team").mkdir(parents=True)
    (claude / "team" / "roster.json").write_text(json.dumps(roster))
    return _RosterCfg(claude / "framework.config.json")


_ROSTER = {
    "Tariq Morales": "Tariq.Morales@example.com",
    "Ibrahim El-Amin": "Ibrahim.El-Amin@example.com",
    "Nia Rossi": "Nia.Rossi@example.com",
}


# --------------------------------------------------------------- _name_key


def test_name_key_folds_dotted_spaced_and_role_variants() -> None:
    # The exact three variants issue #119 names collapse to one key.
    assert (
        ts._name_key("Tariq.Morales")
        == ts._name_key("Tariq Morales")
        == ts._name_key("Tariq Morales (QA)")
        == "tariq morales"
    )


def test_name_key_preserves_hyphen_but_folds_dot() -> None:
    # A dotted first/last separator becomes a space; the hyphen inside a
    # surname is preserved (Ibrahim.El-Amin -> "ibrahim el-amin").
    assert ts._name_key("Ibrahim.El-Amin") == "ibrahim el-amin"
    assert ts._name_key("Ibrahim El-Amin (Senior SWE)") == "ibrahim el-amin"


# --------------------------------------------------------------- _canonicalizer


def test_canonicalizer_maps_all_variants_to_roster_identity(tmp_path) -> None:
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    for variant in ("Tariq.Morales", "Tariq Morales", "Tariq Morales (QA)"):
        assert canon(variant) == "Tariq Morales"
    assert canon("Ibrahim.El-Amin") == "Ibrahim El-Amin"


def test_canonicalizer_passes_absent_name_through(tmp_path) -> None:
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    # A name not on the roster is returned verbatim — never dropped, never raised.
    assert canon("Some Contractor") == "Some Contractor"
    assert canon("dependabot[bot]") == "dependabot[bot]"


def test_canonicalizer_fails_open_without_roster(tmp_path) -> None:
    # No roster file at all (and cfg with no path) → every name passes through.
    missing_cfg = _RosterCfg(tmp_path / ".claude" / "framework.config.json")
    canon = ts._canonicalizer(missing_cfg)
    assert canon("Tariq.Morales") == "Tariq.Morales"
    assert ts._canonicalizer(_Cfg({}))("Tariq.Morales") == "Tariq.Morales"


# --------------------------------------------------------------- end-to-end bucketing


def _account_canon(
    canon, pr_sets: dict[str, tuple[str, list[str]]]
) -> dict[str, ts.Signals]:
    """extract_signals' per-PR accounting with the roster canonicalizer applied
    to both author and requestor identity — pure (no gh)."""
    signals: dict[str, ts.Signals] = {}

    def bucket(name: str) -> ts.Signals:
        return signals.setdefault(canon(name), ts.Signals())

    for _pr, (author, bodies) in pr_sets.items():
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


def test_variants_bucket_to_single_engineer_end_to_end(tmp_path) -> None:
    """The #119 defect, end to end: Tariq reviewing as `Tariq Morales (QA)` on one
    PR and `Tariq.Morales` on another must land in ONE ledger entry, not split."""
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    # PR96: Tariq (as "(QA)") catches a must-fix on Ibrahim's PR.
    # PR93: Tariq (as dotted "Tariq.Morales") catches a must-fix on Nia's PR.
    pr93_by_nia = """Requestor: Tariq.Morales
Requestee: Nia Rossi
RequestOrReplied: Request

**Must-fix:**
1. Correct the recorded numbers.
"""
    sigs = _account_canon(
        canon,
        {
            "96": ("Ibrahim El-Amin", [PR96_REQUEST]),
            "93": ("Nia Rossi", [pr93_by_nia]),
        },
    )
    # Exactly one Tariq bucket — no phantom `Tariq.Morales` split.
    tariq_keys = [k for k in sigs if "tariq" in k.lower()]
    assert tariq_keys == ["Tariq Morales"]
    assert sigs["Tariq Morales"].must_fix_caught == 2


def test_absent_reviewer_still_buckets_without_roster(tmp_path) -> None:
    # Fail-open path: with no roster, the dotted and (Role) forms remain distinct
    # (unchanged legacy behavior) but nothing crashes or is dropped.
    canon = ts._canonicalizer(_RosterCfg(tmp_path / ".claude" / "cfg.json"))
    sigs = _account_canon(canon, {"96": ("Ibrahim El-Amin", [PR96_REQUEST])})
    assert sigs["Ibrahim El-Amin"].must_fix_received == 1
    assert sigs["Tariq Morales (QA)"].must_fix_caught == 1


# ===========================================================================
# N=2 review process (#203): a single PR reviewed by TWO distinct reviewers.
# These drive the REAL ``ts._account_pr`` (not a test mirror), so they are the
# mutation bar for the attribution invariants that a 1-reviewer-era
# implementation silently gets wrong: a catch must be credited to the RIGHT
# Requestor (never dropped, never double-counted onto one reviewer), the author
# must take one ``must_fix_received`` per blocking reviewer, and ``rework_cycles``
# must count the PR ONCE regardless of how many reviewers blocked it.
# ===========================================================================


def _verdict_body(requestor: str, verdict: str, must_fix: str | None) -> str:
    """A charter-format verdict comment; *must_fix* None → clean, str → blocking."""
    mf = "Must-fix: None" if must_fix is None else f"Must-fix:\n1. {must_fix}"
    return (
        f"Requestor: {requestor}\n"
        "Requestee: Paloma.Gupta\n"
        f"RequestOrReplied: {verdict}\n\n"
        "**Review**\n"
        f"{mf}\n"
        "Tech-debt: None\n"
    )


def test_two_distinct_reviewers_each_mustfix_credited_once(tmp_path) -> None:
    """One PR, two DISTINCT reviewers each raise a must-fix (the N=2 case).

    Every catch is credited to its own Requestor — exactly once each, never
    dropped, never both folded onto one reviewer. The author takes one
    ``must_fix_received`` per blocking reviewer (2), but the PR is a SINGLE
    ``rework_cycles`` round.

    Mutation bar (all in ``_account_pr``):
      * moving ``rework_cycles += 1`` inside the per-verdict loop (the naive
        1-reviewer shortcut) makes ``rework_cycles == 2`` → this test fails;
      * crediting the catch to a single fixed reviewer instead of ``v.requestor``
        drops one of the two ``must_fix_caught == 1`` assertions → fails;
      * counting only the first blocking verdict makes ``must_fix_received == 1``
        → fails.
    """
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=500,
        comment_bodies=[
            _verdict_body("Tariq.Morales", "Request", "Fix the thing."),
            _verdict_body("Nia.Rossi", "Request", "Fix the other thing."),
        ],
        ci_red=False,
    )
    assert sigs["Paloma Gupta"].must_fix_received == 2  # one per blocking reviewer
    assert sigs["Paloma Gupta"].rework_cycles == 1  # ONE PR, not one-per-verdict
    assert sigs["Tariq Morales"].must_fix_caught == 1  # credited to the right reviewer
    assert sigs["Nia Rossi"].must_fix_caught == 1  # the second catch is not dropped


def test_two_reviewers_one_clean_one_mustfix_credits_only_blocker(tmp_path) -> None:
    """One PR, two distinct reviewers: one clean approval, one must-fix.

    Only the blocking reviewer earns the catch; the clean reviewer earns none.
    The author takes exactly one ``must_fix_received`` and one ``rework_cycles``.

    Mutation bar: crediting ``must_fix_caught`` off the clean verdict too (an
    attribution that ignores ``v.changes_requested``) gives Tariq a phantom
    bucket with a catch → the "Tariq absent" assertion fails. (A clean reviewer
    produces no trust signal here — approvals are the oracle's concern, not this
    scorer's — so a clean-only reviewer is legitimately not in the map.)
    """
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=501,
        comment_bodies=[
            _verdict_body("Tariq.Morales", "Replied", None),  # clean
            _verdict_body("Nia.Rossi", "Request", "Fix this."),  # blocking
        ],
        ci_red=False,
    )
    assert sigs["Paloma Gupta"].must_fix_received == 1
    assert sigs["Paloma Gupta"].rework_cycles == 1
    assert sigs["Nia Rossi"].must_fix_caught == 1
    assert "Tariq Morales" not in sigs  # clean reviewer earns no catch / no bucket


def test_durable_ledger_attributes_two_distinct_reviewers(tmp_path) -> None:
    """The #164 durable review-catch ledger, at N=2: two distinct reviewers each
    recorded a catch on one PR, and both live comments were later amended clean.

    The ledger stays authoritative for the whole PR — both catches survive the
    amendment and land on the right (distinct) reviewers; the author still takes
    two ``must_fix_received`` and one ``rework_cycles``.

    Mutation bar: a 1-reviewer ledger read (e.g. only the first entry, or folding
    every entry onto one reviewer) drops Nia's catch → the two
    ``must_fix_caught == 1`` assertions fail. Reading the amended-clean live
    comments instead of the ledger makes ``must_fix_received == 0`` → fails.
    """
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ledger = [
        {"repo": "o/r", "pr": 502, "requestor": "Tariq.Morales", "requestee": "Paloma.Gupta"},
        {"repo": "o/r", "pr": 502, "requestor": "Nia.Rossi", "requestee": "Paloma.Gupta"},
    ]
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=502,
        # Both blocking comments were amended in place to clean after the fix.
        comment_bodies=[
            _verdict_body("Tariq.Morales", "Replied", None),
            _verdict_body("Nia.Rossi", "Replied", None),
        ],
        ci_red=False,
        review_catches=ledger,
    )
    assert sigs["Paloma Gupta"].must_fix_received == 2  # ledger, not amended comments
    assert sigs["Paloma Gupta"].rework_cycles == 1
    assert sigs["Tariq Morales"].must_fix_caught == 1
    assert sigs["Nia Rossi"].must_fix_caught == 1


# ===========================================================================
# Integration-branch resolution (#100): phase-aware branch.integration template.
# ===========================================================================


class _Cfg:
    """Minimal stand-in for the shared config object: dotted ``.get(key, default)``."""

    def __init__(self, values: dict) -> None:
        self._v = values

    def get(self, key: str, default=None):
        return self._v.get(key, default)


# --------------------------------------------------------------- _render_branch_template


def test_render_substitutes_both_tokens() -> None:
    out = ts._render_branch_template(
        "deployments/phase{phase}/wave-{wave}", phase=6, wave="1"
    )
    assert out == "deployments/phase6/wave-1"


def test_render_leaves_unknown_token_literal() -> None:
    # An unresolved token must not raise (mirrors the shell sed behaviour).
    out = ts._render_branch_template("deployments/phase{phase}/wave-{wave}", wave="3")
    assert out == "deployments/phase{phase}/wave-3"


def test_render_wave_only_template() -> None:
    out = ts._render_branch_template("deployments/wave-{wave}", wave="7", phase=2)
    assert out == "deployments/wave-7"


# --------------------------------------------------------------- _integration_base


def test_integration_base_phase_aware() -> None:
    cfg = _Cfg({"branch.integration": "deployments/phase{phase}/wave-{wave}"})
    assert ts._integration_base(cfg, "1", phase=6) == "deployments/phase6/wave-1"


def test_integration_base_phase_aware_phase4() -> None:
    # Regression for issue #100: config unchanged between phases, phase drives the branch.
    cfg = _Cfg({"branch.integration": "deployments/phase{phase}/wave-{wave}"})
    assert ts._integration_base(cfg, "1", phase=4) == "deployments/phase4/wave-1"


def test_integration_base_missing_phase_is_safe() -> None:
    # No phase supplied for a phase-namespaced template → literal token, no KeyError.
    cfg = _Cfg({"branch.integration": "deployments/phase{phase}/wave-{wave}"})
    assert ts._integration_base(cfg, "2") == "deployments/phase{phase}/wave-2"


def test_integration_base_generic_default() -> None:
    # Empty config → generic wave-only default still resolves.
    cfg = _Cfg({})
    assert ts._integration_base(cfg, "9") == "deployments/wave-9"


def test_integration_base_literal_default_branch() -> None:
    # A project merging straight to a named branch (no tokens) passes through.
    cfg = _Cfg({"branch.integration": "main"})
    assert ts._integration_base(cfg, "5", phase=3) == "main"


# --------------------------------------------------------------- _phase_for_wave


def test_phase_for_wave_reads_state(tmp_path) -> None:
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"wave_1_phase": 6, "wave_2_phase": 7}))
    assert ts._phase_for_wave("1", state) == 6
    assert ts._phase_for_wave("2", state) == 7


def test_phase_for_wave_missing_key_is_none(tmp_path) -> None:
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"wave_1_phase": 6}))
    assert ts._phase_for_wave("9", state) is None


def test_phase_for_wave_no_status_path_is_none() -> None:
    assert ts._phase_for_wave("1", None) is None


def test_phase_for_wave_unreadable_is_none(tmp_path) -> None:
    assert ts._phase_for_wave("1", tmp_path / "does-not-exist.json") is None


# ===========================================================================
# Phase-local wave ordinal (#117): the {wave} token must render the phase-local
# ordinal (wave_<id>_phase_ordinal), not the global wave seq. The sibling of
# #100 one layer down — #100 fixed {phase}, this fixes {wave}.
# ===========================================================================


# --------------------------------------------------------------- _wave_ordinal_for_wave


def test_wave_ordinal_reads_state(tmp_path) -> None:
    state = tmp_path / "state.json"
    # Global wave 2 is the FIRST wave of phase 4 (ordinal 1); global wave 3 the
    # second (ordinal 2) — the exact Phase 4 shape the retro tripped over.
    state.write_text(
        json.dumps({"wave_2_phase_ordinal": 1, "wave_3_phase_ordinal": 2})
    )
    assert ts._wave_ordinal_for_wave("2", state) == 1
    assert ts._wave_ordinal_for_wave("3", state) == 2


def test_wave_ordinal_missing_key_is_none(tmp_path) -> None:
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"wave_2_phase_ordinal": 1}))
    assert ts._wave_ordinal_for_wave("9", state) is None


def test_wave_ordinal_no_status_path_is_none() -> None:
    assert ts._wave_ordinal_for_wave("2", None) is None


def test_wave_ordinal_unreadable_is_none(tmp_path) -> None:
    assert ts._wave_ordinal_for_wave("2", tmp_path / "does-not-exist.json") is None


# --------------------------------------------------------------- _integration_base ordinal


def test_integration_base_uses_phase_local_ordinal() -> None:
    # THE #117 bug: global wave id 2 is phase 4 ordinal 1 → the branch is
    # deployments/phase4/wave-1, NOT deployments/phase4/wave-2 (the global id).
    cfg = _Cfg({"branch.integration": "deployments/phase{phase}/wave-{wave}"})
    assert (
        ts._integration_base(cfg, "2", phase=4, wave_ordinal=1)
        == "deployments/phase4/wave-1"
    )


def test_integration_base_ordinal_falls_back_to_wave_id() -> None:
    # Generic (non-phased) project: no ordinal stamped → the global wave id fills
    # {wave}, so deployments/wave-9 still renders for wave 9.
    cfg = _Cfg({})
    assert ts._integration_base(cfg, "9") == "deployments/wave-9"
    assert ts._integration_base(cfg, "9", wave_ordinal=None) == "deployments/wave-9"


# --------------------------------------------------------------- end-to-end wiring


def test_base_resolved_from_state_end_to_end(tmp_path) -> None:
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"wave_1_phase": 4}))
    cfg = _Cfg({"branch.integration": "deployments/phase{phase}/wave-{wave}"})
    phase = ts._phase_for_wave("1", state)
    assert ts._integration_base(cfg, "1", phase=phase) == "deployments/phase4/wave-1"


def test_base_resolves_phase4_wave1_from_global_wave_2(tmp_path) -> None:
    """The confirmed regression, end to end: scoring global wave 2 (Phase 4 Wave
    1) must target deployments/phase4/wave-1 — resolving BOTH tokens from state
    (phase=4, ordinal=1) — so the retro finds the wave's PRs with no override."""
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "wave_2_phase": 4,
                "wave_2_phase_ordinal": 1,
                "wave_3_phase": 4,
                "wave_3_phase_ordinal": 2,
            }
        )
    )
    cfg = _Cfg({"branch.integration": "deployments/phase{phase}/wave-{wave}"})
    base = ts._integration_base(
        cfg,
        "2",
        phase=ts._phase_for_wave("2", state),
        wave_ordinal=ts._wave_ordinal_for_wave("2", state),
    )
    assert base == "deployments/phase4/wave-1"
    # And the current wave (global 3) is the second phase-4 branch.
    base3 = ts._integration_base(
        cfg,
        "3",
        phase=ts._phase_for_wave("3", state),
        wave_ordinal=ts._wave_ordinal_for_wave("3", state),
    )
    assert base3 == "deployments/phase4/wave-2"


# ===========================================================================
# Durable review-catch ledger (#164): the charter's amendment convention has a
# reviewer edit a blocking Must-fix comment IN PLACE to Replied/Must-fix: None
# once the fix lands. Re-deriving must_fix_caught/must_fix_received purely
# from the (now-amended) live comment body erases the historic catch and can
# drop the reviewer out of the engineer map entirely — exactly what happened
# to Tariq in Phase 6 Wave 6 (see wave_6_counter_corrections in state.json).
# ===========================================================================


# --------------------------------------------------------------- _review_catches_for_wave


def test_review_catches_for_wave_missing_file_is_empty(tmp_path) -> None:
    assert ts._review_catches_for_wave("6", tmp_path / "absent.json") == []


def test_review_catches_for_wave_no_status_path_is_empty() -> None:
    assert ts._review_catches_for_wave("6", None) == []


def test_review_catches_for_wave_missing_key_is_empty(tmp_path) -> None:
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"wave_6_changes_requested_cycles": 3}))
    assert ts._review_catches_for_wave("6", state) == []


def test_review_catches_for_wave_reads_recorded_entries(tmp_path) -> None:
    state = tmp_path / "state.json"
    entries = [
        {
            "repo": "acme/proj",
            "pr": 154,
            "requestor": "Tariq Morales",
            "requestee": "Paloma Gupta",
        }
    ]
    state.write_text(json.dumps({"wave_6_review_catches": entries}))
    assert ts._review_catches_for_wave("6", state) == entries


# --------------------------------------------------------------- record_review_catch


def test_record_review_catch_appends_and_persists_to_disk(tmp_path) -> None:
    state = tmp_path / "state.json"
    # The real state file is always written one-key-per-line (see lifecycle's
    # _initial_text / upsert_status_keys' compact-inline shape) — mirror that
    # here since record_review_catch's write path (lifecycle.persist) upserts
    # text-level and expects that shape, not a single-line json.dumps blob.
    state.write_text(json.dumps({"wave_6_active": True}, indent=2) + "\n")

    updated = ts.record_review_catch(
        state,
        "6",
        repo="acme/proj",
        pr=154,
        requestor="Tariq Morales",
        requestee="Paloma Gupta",
        at="2026-07-06T00:00:00Z",
    )
    expected = [
        {
            "repo": "acme/proj",
            "pr": 154,
            "requestor": "Tariq Morales",
            "requestee": "Paloma Gupta",
            "recorded_at": "2026-07-06T00:00:00Z",
        }
    ]
    assert updated == expected

    # Round-trips through disk and preserves the pre-existing key untouched.
    on_disk = json.loads(state.read_text())
    assert on_disk["wave_6_active"] is True
    assert on_disk["wave_6_review_catches"] == expected


def test_record_review_catch_accumulates_across_calls_not_deduplicated(tmp_path) -> None:
    # Each call is one catch event — repeated must-fix rounds on the same PR
    # by the same reviewer are distinct cycles, never collapsed.
    state = tmp_path / "state.json"
    state.write_text(json.dumps({}))
    ts.record_review_catch(
        state, "6", repo="acme/proj", pr=154, requestor="Tariq Morales",
        requestee="Paloma Gupta", at="t1",
    )
    updated = ts.record_review_catch(
        state, "6", repo="acme/proj", pr=156, requestor="Tariq Morales",
        requestee="Ibrahim El-Amin", at="t2",
    )
    assert [c["pr"] for c in updated] == [154, 156]
    assert ts._review_catches_for_wave("6", state) == updated


def test_record_review_catch_seeds_empty_state_file(tmp_path) -> None:
    state = tmp_path / "state.json"
    updated = ts.record_review_catch(
        state, "6", repo="acme/proj", pr=154, requestor="Tariq Morales",
        requestee="Paloma Gupta", at="2026-07-06T00:00:00Z",
    )
    assert json.loads(state.read_text())["wave_6_review_catches"] == updated


# --------------------------------------------------------------- _account_pr ledger-authoritative accounting

# The exact shape from the Wave 6 defect: Tariq's blocking review, later
# amended IN PLACE (same comment) to Replied/Must-fix: None once Paloma's fix
# landed. Live parsing alone now reads this PR as clean.
_AMENDED_CLEAN_BODY = """Requestor: Tariq Morales (QA)
Requestee: Paloma Gupta
RequestOrReplied: Replied

Fix confirmed — all resolved.

Must-fix: None
"""

# The same PR's review BEFORE the amendment — still live/pending.
_LIVE_PENDING_BODY = """Requestor: Tariq Morales
Requestee: Paloma Gupta
RequestOrReplied: Request

Must-fix:
1. still needs a fix
"""


def test_account_pr_ledger_authoritative_over_amended_comment() -> None:
    # THE #164 fix, isolated: a ledger entry recorded at issue time still
    # produces the catch even though the live comment now reads clean.
    signals: dict[str, ts.Signals] = {}
    ts._account_pr(
        signals,
        lambda n: n,
        author="Paloma Gupta",
        repo="acme/proj",
        number=154,
        comment_bodies=[_AMENDED_CLEAN_BODY],
        ci_red=False,
        review_catches=[
            {
                "repo": "acme/proj",
                "pr": 154,
                "requestor": "Tariq Morales",
                "requestee": "Paloma Gupta",
            }
        ],
    )
    assert signals["Paloma Gupta"].must_fix_received == 1
    assert signals["Paloma Gupta"].rework_cycles == 1
    assert signals["Tariq Morales"].must_fix_caught == 1


def test_account_pr_without_ledger_reproduces_the_164_defect() -> None:
    # Documents the PRE-fix behavior directly: an EMPTY ledger (a wave that
    # never called record_review_catch) falls back to live-comment parsing,
    # so the amended body reads as fully clean and the reviewer never
    # appears — exactly the bug #164 reported.
    signals: dict[str, ts.Signals] = {}
    ts._account_pr(
        signals,
        lambda n: n,
        author="Paloma Gupta",
        repo="acme/proj",
        number=154,
        comment_bodies=[_AMENDED_CLEAN_BODY],
        ci_red=False,
        review_catches=[],
    )
    assert signals["Paloma Gupta"].must_fix_received == 0
    assert "Tariq Morales (QA)" not in signals


def test_account_pr_ledger_present_does_not_double_count_still_pending_review() -> None:
    # A ledger entry recorded at issue time plus a STILL-LIVE (not yet
    # amended) Must-fix comment for the same PR must count as ONE catch, not
    # two — the ledger supersedes live parsing entirely for a PR it covers.
    signals: dict[str, ts.Signals] = {}
    ts._account_pr(
        signals,
        lambda n: n,
        author="Paloma Gupta",
        repo="acme/proj",
        number=154,
        comment_bodies=[_LIVE_PENDING_BODY],
        ci_red=False,
        review_catches=[
            {
                "repo": "acme/proj",
                "pr": 154,
                "requestor": "Tariq Morales",
                "requestee": "Paloma Gupta",
            }
        ],
    )
    assert signals["Paloma Gupta"].must_fix_received == 1
    assert signals["Tariq Morales"].must_fix_caught == 1


def test_account_pr_ledger_scoped_to_matching_repo_and_pr_only() -> None:
    # A ledger entry for a DIFFERENT PR must not leak into this one's
    # accounting — the filter is (repo, pr)-scoped.
    signals: dict[str, ts.Signals] = {}
    ts._account_pr(
        signals,
        lambda n: n,
        author="Paloma Gupta",
        repo="acme/proj",
        number=154,
        comment_bodies=[_AMENDED_CLEAN_BODY],
        ci_red=False,
        review_catches=[
            {
                "repo": "acme/proj",
                "pr": 999,
                "requestor": "Tariq Morales",
                "requestee": "Someone Else",
            }
        ],
    )
    assert signals["Paloma Gupta"].must_fix_received == 0


# --------------------------------------------------------------- extract_signals end-to-end (load-bearing)


def test_extract_signals_amend_in_place_does_not_erase_catch(tmp_path, monkeypatch) -> None:
    """LOAD-BEARING: end to end through the real extract_signals entrypoint
    (the CLI's extract/score subcommands call exactly this). A reviewer amends
    their blocking verdict comment in place after the fix lands — the charter
    convention — so gh now serves only the clean, amended body. Without the
    #164 fix (revert _account_pr's ledger branch, or pass review_catches=[]
    from extract_signals) this fails: must_fix_received drops to 0 and
    "Tariq Morales" never appears in the signals map at all.
    """
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "wave_6_review_catches": [
                    {
                        "repo": "acme/proj",
                        "pr": 154,
                        "requestor": "Tariq Morales",
                        "requestee": "Paloma Gupta",
                    }
                ]
            }
        )
    )

    monkeypatch.setattr(
        ts,
        "merged_prs",
        lambda wave, status_path=None, *, label=None, cfg=None: [
            {"repo": "acme/proj", "number": 154, "commit_author_name": "Paloma Gupta"}
        ],
    )
    monkeypatch.setattr(
        ts, "_pr_comment_bodies", lambda repo, number: [_AMENDED_CLEAN_BODY]
    )
    monkeypatch.setattr(ts, "_pr_ci_is_red", lambda repo, number: False)

    sigs = ts.extract_signals("6", state, cfg=_Cfg({}))

    assert sigs["Paloma Gupta"].must_fix_received == 1
    assert sigs["Paloma Gupta"].rework_cycles == 1
    assert sigs["Tariq Morales"].must_fix_caught == 1


def test_wave6_fixture_rescoring_with_amended_catches(tmp_path, monkeypatch) -> None:
    """Reproduces the exact Phase 6 Wave 6 scenario recorded in
    wave_6_counter_corrections (state.json): PRs #154/#156/#160, all caught by
    Tariq Morales, all amended in place to Replied/Must-fix: None after their
    fixes landed. Pre-#164 this recomputed to must_fix_caught=0 for Tariq (he
    dropped out of the engineer map entirely) and an aggregate
    changes_requested_cycles of 0 — vs. the wrapup-recorded 3, the exact
    divergence the state.json note records as a manual correction. With the
    ledger populated (as record_review_catch would have done at issue time)
    the scorer now recomputes the true count with no manual correction needed.
    """
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "wave_6_review_catches": [
                    {
                        "repo": "acme/proj",
                        "pr": 154,
                        "requestor": "Tariq Morales",
                        "requestee": "Paloma Gupta",
                    },
                    {
                        "repo": "acme/proj",
                        "pr": 156,
                        "requestor": "Tariq Morales",
                        "requestee": "Ibrahim El-Amin",
                    },
                    {
                        "repo": "acme/proj",
                        "pr": 160,
                        "requestor": "Tariq Morales",
                        "requestee": "Nia Rossi",
                    },
                ]
            }
        )
    )

    fake_prs = [
        {"repo": "acme/proj", "number": 154, "commit_author_name": "Paloma Gupta"},
        {"repo": "acme/proj", "number": 156, "commit_author_name": "Ibrahim El-Amin"},
        {"repo": "acme/proj", "number": 160, "commit_author_name": "Nia Rossi"},
    ]
    bodies_by_pr = {
        154: [_AMENDED_CLEAN_BODY],
        156: [_AMENDED_CLEAN_BODY.replace("Paloma Gupta", "Ibrahim El-Amin")],
        160: [_AMENDED_CLEAN_BODY.replace("Paloma Gupta", "Nia Rossi")],
    }

    monkeypatch.setattr(
        ts, "merged_prs", lambda wave, status_path=None, *, label=None, cfg=None: fake_prs
    )
    monkeypatch.setattr(
        ts, "_pr_comment_bodies", lambda repo, number: bodies_by_pr[number]
    )
    monkeypatch.setattr(ts, "_pr_ci_is_red", lambda repo, number: False)

    sigs = ts.extract_signals("6", state, cfg=_Cfg({}))

    assert sigs["Tariq Morales"].must_fix_caught == 3
    assert sigs["Paloma Gupta"].must_fix_received == 1
    assert sigs["Ibrahim El-Amin"].must_fix_received == 1
    assert sigs["Nia Rossi"].must_fix_received == 1

    # Aggregate consistency: the wrapup-recorded changes_requested_cycles (3)
    # now matches what the scorer recomputes, with no manual correction.
    aggregate_changes_requested_cycles = sum(s.rework_cycles for s in sigs.values())
    assert aggregate_changes_requested_cycles == 3


# --------------------------------------------------------------- CLI record-catch


def test_cli_record_catch_appends_to_state_file(tmp_path) -> None:
    state = tmp_path / "state.json"
    state.write_text(json.dumps({}))

    rc = ts.main(
        [
            "record-catch",
            "6",
            "--repo",
            "acme/proj",
            "--pr",
            "154",
            "--requestor",
            "Tariq Morales",
            "--requestee",
            "Paloma Gupta",
            "--at",
            "2026-07-06T00:00:00Z",
            "--status",
            str(state),
        ]
    )
    assert rc == 0
    on_disk = json.loads(state.read_text())
    assert on_disk["wave_6_review_catches"] == [
        {
            "repo": "acme/proj",
            "pr": 154,
            "requestor": "Tariq Morales",
            "requestee": "Paloma Gupta",
            "recorded_at": "2026-07-06T00:00:00Z",
        }
    ]


# ===========================================================================
# #229 — trust scorer reads reality: edit-history catch crediting + difficulty
# weight. The gate oracle (pr_review_state) REQUIRES a reviewer to resolve a
# blocking Request by editing it in place to Replied; the scorer read that same
# current state, so an amended catch scored must_fix_caught=0 / must_fix_received
# =0 (W13: Tariq's real data-loss catch scored mechanically zero). These credit
# the catch from GitHub's comment edit history instead, and add a coarse per-PR
# difficulty weight so the reserved-5 rotation is mechanical.
# ===========================================================================


# ----------------------------------------------------------- difficulty_weight


def test_difficulty_weight_trivial_is_tier_1() -> None:
    # A one-line config change / doc typo.
    assert ts.difficulty_weight(1, 0, 1) == 1
    assert ts.difficulty_weight(0, 0, 0) == 1
    assert ts.difficulty_weight(39, 0, 2) == 1  # just under both tier-2 bars


def test_difficulty_weight_moderate_is_tier_2() -> None:
    assert ts.difficulty_weight(40, 0, 1) == 2  # lines bar
    assert ts.difficulty_weight(0, 0, 3) == 2  # files bar
    assert ts.difficulty_weight(199, 0, 7) == 2  # just under both tier-3 bars


def test_difficulty_weight_flagship_is_tier_3() -> None:
    assert ts.difficulty_weight(200, 0, 1) == 3  # lines bar
    assert ts.difficulty_weight(0, 0, 8) == 3  # files bar
    # #227 (the W13 flagship): 1101 additions across 6 files → tier 3.
    assert ts.difficulty_weight(1101, 0, 6) == 3


def test_difficulty_weight_counts_deletions_and_clamps_garbage() -> None:
    # A large deletion is still work; negatives clamp to 0 (never < tier 1).
    assert ts.difficulty_weight(0, 250, 1) == 3
    assert ts.difficulty_weight(-500, -9, -3) == 1


def test_pr_diffstat_reads_record_fail_open() -> None:
    assert ts._pr_diffstat({"additions": 200, "deletions": 5, "changedFiles": 6}) == (
        200,
        5,
        6,
    )
    # Missing / non-int fields degrade to 0, never raise.
    assert ts._pr_diffstat({}) == (0, 0, 0)
    assert ts._pr_diffstat({"additions": "x", "deletions": None}) == (0, 0, 0)


# ------------------------------------------------- _collapse_history / verdicts


def test_collapse_history_credits_amended_away_catch() -> None:
    """The core #229 case: a blocking Request amended in place to a clean Replied
    still yields a changes_requested Verdict attributed to the original reviewer."""
    current = _verdict_body("Tariq.Morales", "Replied", None)  # amended clean
    original = _verdict_body("Tariq.Morales", "Request", "Data-loss in the amend path.")
    v = ts._collapse_history([current, original])
    assert v is not None
    assert v.changes_requested is True
    assert v.requestor == "Tariq.Morales"
    assert v.requestee == "Paloma.Gupta"


def test_collapse_history_no_edits_matches_parse_verdicts() -> None:
    """Backward-compat: a never-edited comment (single revision) collapses to
    exactly parse_verdicts([body])[0] — a clean no-amend wave is unchanged."""
    for body in (
        _verdict_body("Nia.Rossi", "Replied", None),
        _verdict_body("Tariq.Morales", "Request", "Fix this."),
    ):
        collapsed = ts._collapse_history([body])
        (expected,) = ts.parse_verdicts([body])
        assert collapsed == expected


def test_collapse_history_non_verdict_comment_is_none() -> None:
    assert ts._collapse_history(["just a plain chat comment, no verdict header"]) is None


def test_collapse_history_false_positive_taken_from_current_body() -> None:
    """A retraction lives only in the live comment — false_positive comes from the
    CURRENT revision, not resurrected from a historical blocking revision."""
    current = (
        "Requestor: Nia.Rossi\nRequestee: Paloma.Gupta\nRequestOrReplied: Replied\n\n"
        "**Review**\nMust-fix:\n1. Withdrawn — this was a false-positive on my part.\n"
    )
    original = _verdict_body("Nia.Rossi", "Request", "Original blocking finding.")
    v = ts._collapse_history([current, original])
    assert v is not None
    assert v.changes_requested is True  # credited from history
    assert v.false_positive is True  # detected from the current retraction body


def test_verdicts_from_histories_drops_non_verdicts_and_keeps_one_per_comment() -> None:
    histories = [
        [_verdict_body("Tariq.Morales", "Replied", None),
         _verdict_body("Tariq.Morales", "Request", "Blocking.")],
        ["plain non-verdict comment"],
        [_verdict_body("Nia.Rossi", "Replied", None)],
    ]
    vs = ts.verdicts_from_histories(histories)
    assert len(vs) == 2  # the plain comment is dropped
    assert vs[0].changes_requested is True
    assert vs[1].changes_requested is False


# --------------------------------------- _account_pr with comment_histories


def test_account_pr_credits_amended_catch_from_history(tmp_path) -> None:
    """The mutation bar for #229: reading histories, an amended-away catch still
    credits the reviewer (must_fix_caught) and author (must_fix_received).

    Mutation bar: reverting _account_pr to parse the CURRENT bodies only (the
    W13 bug) makes must_fix_caught == 0 and must_fix_received == 0 → this fails.
    """
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=600,
        comment_histories=[
            # Tariq's blocking Request, later amended in place to a clean Replied.
            [_verdict_body("Tariq.Morales", "Replied", None),
             _verdict_body("Tariq.Morales", "Request", "Data-loss in amend path.")],
        ],
        ci_red=False,
        difficulty=3,
    )
    assert sigs["Tariq Morales"].must_fix_caught == 1  # survived the amendment
    assert sigs["Paloma Gupta"].must_fix_received == 1
    assert sigs["Paloma Gupta"].rework_cycles == 1
    assert sigs["Paloma Gupta"].difficulty_points == 3


def test_account_pr_history_clean_wave_scores_no_catch(tmp_path) -> None:
    """Backward-compat via the history path: a clean review (no revision ever
    blocking) yields no catch — identical to the legacy live-comment path."""
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=601,
        comment_histories=[[_verdict_body("Tariq.Morales", "Replied", None)]],
        ci_red=False,
        difficulty=1,
    )
    assert sigs["Paloma Gupta"].must_fix_received == 0
    assert sigs["Paloma Gupta"].rework_cycles == 0
    assert "Tariq Morales" not in sigs
    assert sigs["Paloma Gupta"].difficulty_points == 1


def test_account_pr_ledger_still_authoritative_over_history(tmp_path) -> None:
    """The #164 ledger takes precedence over the #229 history path when present —
    belts-and-braces, never double-counting."""
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=602,
        # History ALSO shows the catch; the ledger must not add a second one.
        comment_histories=[
            [_verdict_body("Tariq.Morales", "Replied", None),
             _verdict_body("Tariq.Morales", "Request", "Blocking.")],
        ],
        ci_red=False,
        review_catches=[
            {"repo": "o/r", "pr": 602, "requestor": "Tariq.Morales",
             "requestee": "Paloma.Gupta"},
        ],
    )
    assert sigs["Tariq Morales"].must_fix_caught == 1  # once, not twice
    assert sigs["Paloma Gupta"].must_fix_received == 1
    assert sigs["Paloma Gupta"].rework_cycles == 1


# ------------------------------------------- wave-13 re-score (the AC anchor)


def test_wave13_rescore_credits_tariq_catch_and_paloma_received(tmp_path) -> None:
    """Re-scoring W13's flagship PR #227 with the fix credits Tariq's real
    data-loss catch and Paloma's received must-fix — reconstructed from the real
    comment edit history (Tariq's Request amended in place to Replied; three
    other clean reviews never edited). Before #229 both scored zero (finding #1).
    """
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    # Real #227 history shape: Tariq's blocking comment (id 4904379564) was edited
    # in place from Request+Must-fix to Replied+Must-fix:None; the other three
    # comments (two of Nia's, one Tariq follow-up) were clean and never edited.
    tariq_current = _verdict_body("Tariq.Morales", "Replied", None)
    tariq_original = _verdict_body(
        "Tariq.Morales", "Request",
        "Amend-disposition surgical removal deletes pre-existing user files — "
        "unrecoverable data loss.",
    )
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="parametrization/2real-team-framework",
        number=227,
        comment_histories=[
            [tariq_current, tariq_original],                       # the catch
            [_verdict_body("Nia.Rossi", "Replied", None)],         # clean
            [_verdict_body("Tariq.Morales", "Replied", None)],     # clean follow-up
            [_verdict_body("Nia.Rossi", "Replied", None)],         # clean re-review
        ],
        ci_red=False,
        difficulty=ts.difficulty_weight(1101, 0, 6),  # the real diffstat → tier 3
    )
    assert sigs["Tariq Morales"].must_fix_caught == 1  # was 0 pre-#229
    assert sigs["Paloma Gupta"].must_fix_received == 1  # was 0 pre-#229
    assert sigs["Paloma Gupta"].rework_cycles == 1
    assert sigs["Paloma Gupta"].difficulty_points == 3  # flagship, not a one-liner


# ------------------------------------------- difficulty in distribution


def test_difficulty_breaks_reserved_5_toward_flagship_author() -> None:
    """The reserved-5 goes to the flagship author mechanically: two engineers with
    identical PR counts and clean records, but one shipped a tier-3 flagship and
    the other a tier-1 one-liner — only the flagship author keeps the proposed 5.
    """
    flagship = ts.Signals(prs_merged=1, difficulty_points=3)
    trivial = ts.Signals(prs_merged=1, difficulty_points=1)
    out = ts.apply_distribution_discipline(
        {
            "Flagship": (ts.MAX_SCORE, flagship),
            "Trivial": (ts.MAX_SCORE, trivial),
        }
    )
    assert out["Flagship"] == ts.MAX_SCORE  # top composite keeps the 5
    assert out["Trivial"] == ts.MAX_SCORE - 1  # capped to 4


def test_distribution_unchanged_without_difficulty() -> None:
    """Backward-compat: with difficulty_points == 0 for everyone the composite
    ranking is exactly as before (difficulty is purely additive from 0)."""
    a = ts.Signals(prs_merged=2, must_fix_caught=2)
    b = ts.Signals(prs_merged=1)
    out = ts.apply_distribution_discipline(
        {"A": (ts.MAX_SCORE, a), "B": (ts.MAX_SCORE, b)}
    )
    assert out["A"] == ts.MAX_SCORE
    assert out["B"] == ts.MAX_SCORE - 1


# ------------------------------------------- _pr_comment_histories (I/O, mocked)


def test_pr_comment_histories_parses_graphql(monkeypatch) -> None:
    canned = json.dumps(
        {"data": {"repository": {"pullRequest": {"comments": {"nodes": [
            {"body": "CURRENT",
             "userContentEdits": {"nodes": [{"diff": "NEWEST"}, {"diff": "ORIGINAL"}]}},
            {"body": "CLEAN", "userContentEdits": {"nodes": []}},
        ]}}}}}
    )
    monkeypatch.setattr(ts, "_run_gh", lambda args: canned)
    got = ts._pr_comment_histories("o/r", 700)
    assert got == [["CURRENT", "NEWEST", "ORIGINAL"], ["CLEAN"]]


def test_pr_comment_histories_fail_open_on_error(monkeypatch) -> None:
    def boom(args):
        raise ts.subprocess.CalledProcessError(1, ["gh"])

    monkeypatch.setattr(ts, "_run_gh", boom)
    # Fail-open sentinel is None (distinct from [] = a PR with zero comments).
    assert ts._pr_comment_histories("o/r", 701) is None


def test_pr_comment_histories_bad_repo_is_none() -> None:
    assert ts._pr_comment_histories("no-slash-repo", 702) is None


# ===========================================================================
# Symmetric trust scoring (#254): verified_reviews (+) and the rework /
# must-fix downward signals. These pin the score_delta weight table and the
# extraction of the anti-gaming `Verified:` block.
# ===========================================================================


def _verified_body(
    requestor: str,
    *,
    verdict: str = "Replied",
    verified_lines: tuple[str, ...] = (
        "revert→red on the failing test",
        "5× determinism",
        "byte-parity OK",
    ),
    must_fix: str | None = None,
) -> str:
    """A charter-format verdict comment carrying a ``Verified:`` block.

    ``verified_lines=()`` emits a bare ``Verified:`` (boilerplate/empty). A
    ``must_fix`` str makes it a blocking ``Request`` regardless of ``verdict``.
    """
    mf = "Must-fix: None" if must_fix is None else f"Must-fix:\n1. {must_fix}"
    vblock = (
        "Verified:\n" + "\n".join(f"- {ln}" for ln in verified_lines)
        if verified_lines
        else "Verified:"
    )
    return (
        f"Requestor: {requestor}\n"
        "Requestee: Paloma.Gupta\n"
        f"RequestOrReplied: {verdict}\n\n"
        "**Review**\n"
        f"{mf}\n"
        f"{vblock}\n"
        "Tech-debt: None\n"
    )


# ------------------------------------------------- score_delta weight table


def test_verified_reviews_two_gives_clean_wave_bonus() -> None:
    """2+ verified reviews on a clean wave is +1 — the QA-rigor path when there
    are no must-fixes to catch. Load-bearing on the new positive branch: deleting
    the ``verified_reviews >= 2`` bump makes ``rigorous`` score 0.
    """
    assert ts.score_delta(ts.Signals(prs_merged=1)) == 0  # a lone clean PR: no bump
    rigorous = ts.Signals(prs_merged=1, verified_reviews=2)
    assert ts.score_delta(rigorous) == 1
    # one verified review is not enough — the threshold is 2, like the others.
    assert ts.score_delta(ts.Signals(prs_merged=1, verified_reviews=1)) == 0


def test_rework_cycles_two_dings_and_blocks_clean_bonus() -> None:
    """``rework_cycles >= 2`` is −1 AND, being a negative now, blocks the
    clean-wave ``prs_merged >= 2`` bonus (a rework-heavy wave cannot also collect
    the positive). Load-bearing on both the ding and ``has_negative``.
    """
    heavy = ts.Signals(prs_merged=2, rework_cycles=2)
    assert heavy.has_negative() is True  # rework is now a negative
    assert ts.score_delta(heavy) == -1  # −1 for rework; +1 bonus is blocked
    # A single rework cycle is a negative too (blocks the clean-wave bonus) but
    # does not reach the −1 ding threshold: net 0, not the +1 a clean 2-PR wave
    # would earn.
    one = ts.Signals(prs_merged=2, rework_cycles=1)
    assert one.has_negative() is True
    assert ts.score_delta(one) == 0


def test_must_fix_received_two_now_dings() -> None:
    """The author ding threshold tightened 3 → 2: two received must-fixes is −1
    (it was free under the old ``>= 3``). Load-bearing on the threshold constant.
    """
    assert ts.score_delta(ts.Signals(prs_merged=1, must_fix_received=2)) == -1
    # One received must-fix is still free (blocks the bonus, but no ding).
    assert ts.score_delta(ts.Signals(prs_merged=1, must_fix_received=1)) == 0


def test_clean_no_new_signal_wave_scores_exactly_as_before() -> None:
    """Regression guard: a wave carrying NONE of the new signals scores exactly
    the prior deltas — 2 clean PRs + 2 catches → +2; a lone clean PR → 0; an
    empty wave → 0. Ensures the #254 changes are purely additive.
    """
    assert ts.score_delta(ts.Signals(prs_merged=2, must_fix_caught=2)) == 2
    assert ts.score_delta(ts.Signals(prs_merged=1)) == 0
    assert ts.score_delta(ts.Signals()) == 0


# --------------------------------------------------- _has_verified_checks (pure)


def test_has_verified_checks_recognizes_concrete_tokens() -> None:
    assert ts._has_verified_checks("Verified:\n- revert→red\n") is True
    assert ts._has_verified_checks("Verified:\n- 5× determinism run\n") is True
    assert ts._has_verified_checks("Verified: byte-parity confirmed\n") is True
    assert ts._has_verified_checks("Verified:\n- CI rollup SUCCESS\n") is True


def test_has_verified_checks_rejects_boilerplate() -> None:
    assert ts._has_verified_checks("Verified:\n- looks good to me\n") is False
    assert ts._has_verified_checks("Verified:\n") is False
    assert ts._has_verified_checks("no verified block at all") is False
    # A concrete token OUTSIDE the Verified block (in Tech-debt) is not borrowed.
    assert (
        ts._has_verified_checks("Verified: none\nTech-debt: byte-parity follow-up\n")
        is False
    )


# ------------------------------------------------- verified_reviews extraction


def test_verified_block_credits_reviewer_verified_review(tmp_path) -> None:
    """A reviewer's clean verdict with a concrete ``Verified:`` block credits one
    ``verified_reviews`` to the Requestor — and no phantom catch.
    """
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=800,
        comment_bodies=[_verified_body("Tariq.Morales")],
        ci_red=False,
    )
    assert sigs["Tariq Morales"].verified_reviews == 1
    assert sigs["Tariq Morales"].must_fix_caught == 0  # clean review, not a catch


def test_boilerplate_verified_block_earns_no_credit(tmp_path) -> None:
    """An empty or token-less ``Verified:`` block yields verified_reviews=0
    (anti-gaming). Load-bearing on the concrete-token requirement.
    """
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    for lines in ((), ("done",), ("looks good",)):
        sigs: dict[str, ts.Signals] = {}
        ts._account_pr(
            sigs,
            canon,
            author="Paloma Gupta",
            repo="o/r",
            number=801,
            comment_bodies=[_verified_body("Tariq.Morales", verified_lines=lines)],
            ci_red=False,
        )
        assert sigs.get("Tariq Morales", ts.Signals()).verified_reviews == 0


def test_verified_block_on_blocking_request_not_credited(tmp_path) -> None:
    """A Verified block on a BLOCKING ``Request`` is not a verified review — the
    catch scores, but verified_reviews stays 0 (only clean verdicts credit it).
    Load-bearing on the ``not v.changes_requested`` guard.
    """
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=802,
        comment_bodies=[
            _verified_body("Tariq.Morales", verdict="Request", must_fix="Fix the bug."),
        ],
        ci_red=False,
    )
    assert sigs["Tariq Morales"].must_fix_caught == 1
    assert sigs["Tariq Morales"].verified_reviews == 0


# ===========================================================================
# Trust-signal hardening (#258 / #259, W18 S1): the verified_reviews signal
# had the same latent double-counting shape the N=2 review work exposed for
# must_fix_caught, and _VERIFIED_CHECK_RE credited non-substantive / negating
# mentions. These pin the per-(reviewer, PR) dedup and the tightened regex.
# ===========================================================================


def test_verified_reviews_deduped_per_reviewer_per_pr(tmp_path) -> None:
    """#258 (LOAD-BEARING): two clean ``Verified:`` verdicts by the SAME reviewer
    on the SAME PR credit ``verified_reviews`` exactly ONCE — even across name
    spellings (``Tariq.Morales`` / ``Tariq Morales (QA)`` fold to one). A DISTINCT
    reviewer on the same PR still counts, and the same reviewer on a DIFFERENT PR
    (a separate ``_account_pr`` call) counts again.

    Mutation bar (``_account_pr``): removing the per-(reviewer, PR) dedup set
    double-counts Tariq's two comments → ``verified_reviews == 2`` on the first PR
    and ``== 3`` after the second → both dedup assertions fail.
    """
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=810,
        comment_bodies=[
            _verified_body("Tariq.Morales"),  # first clean Verified
            _verified_body("Tariq Morales (QA)"),  # SAME reviewer, variant spelling
            _verified_body("Nia.Rossi"),  # a DISTINCT reviewer
        ],
        ci_red=False,
    )
    assert sigs["Tariq Morales"].verified_reviews == 1  # deduped per (reviewer, PR)
    assert sigs["Nia Rossi"].verified_reviews == 1  # distinct reviewer still counts

    # A DIFFERENT PR (a separate _account_pr call) credits Tariq independently.
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=811,
        comment_bodies=[_verified_body("Tariq.Morales")],
        ci_red=False,
    )
    assert sigs["Tariq Morales"].verified_reviews == 2  # +1 on a different PR


def test_verified_check_re_rejects_negating_or_bare_mention() -> None:
    """#259 (LOAD-BEARING): a NEGATING / non-substantive determinism or CI-green
    mention no longer satisfies the gate — only the substantive, quantified forms
    do. The bare ``determinism`` and bare ``green ci`` / ``ci green`` alternations
    were dropped.

    Mutation bar (``_VERIFIED_CHECK_RE``): restoring the bare ``determinism``
    alternation makes "no determinism check run" credit → the first assertion
    flips to True → fails. Likewise restoring ``green ci`` / ``ci green`` re-credits
    "ci green not verified" → the second assertion fails.
    """
    # Negating / non-substantive mentions must NOT count.
    assert ts._has_verified_checks("Verified:\n- no determinism check run\n") is False
    assert ts._has_verified_checks("Verified:\n- ci green not verified\n") is False
    # The substantive, quantified forms are still credited unchanged.
    assert ts._has_verified_checks("Verified:\n- 5× determinism run\n") is True
    assert ts._has_verified_checks("Verified:\n- revert→red\n") is True
    assert ts._has_verified_checks("Verified:\n- byte-parity OK\n") is True
    assert ts._has_verified_checks("Verified:\n- CI rollup SUCCESS\n") is True


# ===========================================================================
# Scoring-ledger overhaul (#272, W19 S1): five symmetric heuristics + a
# distribution-health probe. Every rule stays a pure function of countable
# signals and preserves the ±2/wave clamp.
# ===========================================================================


# ---------------------------------------------- H1: broadened Verified token set


def test_revert_arrow_ascii_credits_verified_review_270(tmp_path) -> None:
    """LOAD-BEARING (#270): the ASCII arrow ``revert->red`` MUST match and credit a
    ``verified_reviews`` signal — the exact glyph that glyph-decided the W18
    rotation (both #268 reviewers' substantive blocks scored zero because the
    ``>`` broke the old ``revert\\s*(?:→|-+|to)?\\s*red`` tail). A false-negative
    here re-opens #270.

    Mutation bar: reverting ``_VERIFIED_CHECK_RE``'s arrow group to the old
    ``(?:→|-+|to)?`` leaves the ``>`` of ``->`` unconsumed → ``revert->red``
    stops matching → ``_has_verified_checks`` is False → ``verified_reviews`` is
    0 → every assertion below fails.
    """
    # Pure detector: BOTH the ASCII and the unicode arrow match.
    assert ts._has_verified_checks("Verified:\n- revert->red on the failing test\n") is True
    assert ts._has_verified_checks("Verified:\n- revert→red on the failing test\n") is True
    # Credit path (end-to-end through _account_pr): the ASCII-arrow Verified block
    # credits exactly one verified_reviews to the reviewer.
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=930,
        comment_bodies=[
            _verified_body(
                "Tariq.Morales", verified_lines=("revert->red on the failing test",)
            ),
        ],
        ci_red=False,
    )
    assert sigs["Tariq Morales"].verified_reviews == 1


def test_verified_check_re_accepts_generic_suite_evidence() -> None:
    """#H1: generic suite receipts each carrying a number or named tool are
    creditable; a bare phrase with neither is still rejected (anti-gaming).
    """
    for tok in ("42 passed", "42 tests pass", "5 tests passed", "ruff clean",
                "coverage 91%", "all green"):
        assert ts._has_verified_checks(f"Verified:\n- {tok}\n") is True, tok
    # Anti-gaming contract preserved: a bare "tests pass" (no adjacent number or
    # named tool) does NOT count.
    assert ts._has_verified_checks("Verified:\n- tests pass\n") is False
    assert ts._has_verified_checks("Verified:\n- all the tests pass\n") is False


# ----------------------------------------------------- H2: clean_first_pass


def test_clean_first_pass_credited_on_nontrivial_clean_pr(tmp_path) -> None:
    """#H2: a tier>=2 PR merged with no must-fix and no rework earns one
    ``clean_first_pass`` (+1 in the clean-wave branch, once/capped)."""
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=900,
        comment_bodies=[
            _verdict_body("Tariq.Morales", "Replied", None),
            _verdict_body("Nia.Rossi", "Replied", None),
        ],
        ci_red=False,
        difficulty=2,
    )
    p = sigs["Paloma Gupta"]
    assert p.clean_first_pass == 1
    assert p.gate_bypasses == 0  # two clean distinct reviews, nothing unresolved
    assert ts.score_delta(p) == 1  # the clean-first-pass +1


def test_clean_first_pass_not_farmed_by_trivial_pr(tmp_path) -> None:
    """#H2: a trivial (tier 1) PR cannot farm the clean-first-pass credit."""
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=901,
        comment_bodies=[
            _verdict_body("Tariq.Morales", "Replied", None),
            _verdict_body("Nia.Rossi", "Replied", None),
        ],
        ci_red=False,
        difficulty=1,
    )
    assert sigs["Paloma Gupta"].clean_first_pass == 0


def test_clean_first_pass_blocked_on_unclean_wave() -> None:
    """#H2: the +1 only fires on an otherwise-clean wave (``has_negative`` gates
    it) — a must-fix-heavy author with a clean_first_pass gets no bonus."""
    dirty = ts.Signals(prs_merged=2, clean_first_pass=1, must_fix_received=2)
    assert dirty.has_negative() is True
    assert ts.score_delta(dirty) == -1  # the ding, no clean-first-pass +1


# ----------------------------------------------------- H3: graduated dings


def test_graduated_must_fix_and_rework_dings() -> None:
    """#H3: dings deepen with count — >=2 is −1, >=4 is −2 — for both
    ``must_fix_received`` and ``rework_cycles``, still clamped at −2 total."""
    assert ts.score_delta(ts.Signals(prs_merged=1, must_fix_received=2)) == -1
    assert ts.score_delta(ts.Signals(prs_merged=1, must_fix_received=4)) == -2
    assert ts.score_delta(ts.Signals(prs_merged=1, rework_cycles=2)) == -1
    assert ts.score_delta(ts.Signals(prs_merged=1, rework_cycles=4)) == -2
    # Combined deep dings stay clamped at −2 (the ±2/wave floor holds).
    assert ts.score_delta(ts.Signals(must_fix_received=4, rework_cycles=4)) == -2


# ------------------------------------------- H4: missed-catch (durable only)


def test_missed_catch_dings_clean_reviewer_via_history(tmp_path) -> None:
    """#H4: on a PR where a DIFFERENT reviewer's must-fix is durably recorded
    (edit-history path), a reviewer who only posted a CLEAN verdict is dinged one
    ``missed_catches``; the catcher is never dinged.

    Mutation bar: dropping the ``rk in catcher_keys`` guard dings the catcher too;
    dropping the durability gate would (correctly) not fire here since history IS
    durable, but see the live-only test below.
    """
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=910,
        comment_histories=[
            # Nia caught a must-fix, later amended in place to clean.
            [_verdict_body("Nia.Rossi", "Replied", None),
             _verdict_body("Nia.Rossi", "Request", "Data loss in the amend path.")],
            # Tariq only ever posted a clean review — negligent approval.
            [_verdict_body("Tariq.Morales", "Replied", None)],
        ],
        ci_red=False,
    )
    assert sigs["Nia Rossi"].must_fix_caught == 1
    assert sigs["Nia Rossi"].missed_catches == 0  # the catcher is not dinged
    assert sigs["Tariq Morales"].missed_catches == 1  # clean approval past the catch


def test_missed_catch_via_ledger_deduped_across_name_variants(tmp_path) -> None:
    """#H4: the durable ledger (#164) also drives the missed-catch, and a reviewer
    who posted two clean comments (variant spellings) is dinged exactly once."""
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ledger = [
        {"repo": "o/r", "pr": 911, "requestor": "Nia.Rossi", "requestee": "Paloma.Gupta"},
    ]
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=911,
        # All live comments read clean (Nia's was amended); Tariq posts twice.
        comment_bodies=[
            _verdict_body("Nia.Rossi", "Replied", None),
            _verdict_body("Tariq.Morales", "Replied", None),
            _verdict_body("Tariq Morales (QA)", "Replied", None),
        ],
        ci_red=False,
        review_catches=ledger,
    )
    assert sigs["Nia Rossi"].must_fix_caught == 1
    assert sigs["Nia Rossi"].missed_catches == 0
    assert sigs["Tariq Morales"].missed_catches == 1  # deduped per (reviewer, PR)


def test_missed_catch_not_fired_on_live_comment_only(tmp_path) -> None:
    """#H4: a legacy live-comment-bodies-only PR (no ledger, no history) does NOT
    fire the missed-catch — that catch is itself editable, so the signal would be
    gameable. This mirrors the #203 ``credits_only_blocker`` invariant.

    Mutation bar: dropping the ``durable_catch_source`` gate dings Tariq here →
    the last assertion fails.
    """
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=912,
        comment_bodies=[
            _verdict_body("Nia.Rossi", "Request", "Fix this."),  # live blocking
            _verdict_body("Tariq.Morales", "Replied", None),  # clean
        ],
        ci_red=False,
    )
    assert sigs["Nia Rossi"].must_fix_caught == 1
    assert sigs.get("Tariq Morales", ts.Signals()).missed_catches == 0


# ------------------------------------------------------- H5: gate-bypass


def test_gate_bypass_on_unresolved_must_fix(tmp_path) -> None:
    """#H5: a merge whose CURRENT comment state still carries an unresolved
    blocking must-fix scores one ``gate_bypasses`` (hard ding) on the author."""
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=920,
        comment_bodies=[
            _verdict_body("Nia.Rossi", "Request", "Still unresolved at merge."),
            _verdict_body("Tariq.Morales", "Replied", None),
        ],
        ci_red=False,
    )
    assert sigs["Paloma Gupta"].gate_bypasses == 1


def test_gate_bypass_on_too_few_clean_reviews(tmp_path) -> None:
    """#H5: a merge with fewer than 2 distinct clean reviewer verdicts (the armed
    gate's bar) scores a gate-bypass."""
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=921,
        comment_bodies=[_verdict_body("Tariq.Morales", "Replied", None)],  # only one
        ci_red=False,
    )
    assert sigs["Paloma Gupta"].gate_bypasses == 1


def test_no_gate_bypass_in_healthy_two_clean_review_merge(tmp_path) -> None:
    """#H5: near-zero in a healthy wave — two distinct clean reviews and nothing
    unresolved → no gate-bypass. Distinct-count is canonical (a name variant of
    one reviewer is not a second reviewer)."""
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=922,
        comment_bodies=[
            _verdict_body("Tariq.Morales", "Replied", None),
            _verdict_body("Nia.Rossi", "Replied", None),
        ],
        ci_red=False,
        difficulty=2,
    )
    assert sigs["Paloma Gupta"].gate_bypasses == 0


def test_gate_bypass_variant_spellings_not_two_distinct(tmp_path) -> None:
    """#H5: two clean comments by the SAME reviewer under different spellings are
    ONE distinct reviewer → still a gate-bypass (the 2-reviewer bar isn't met)."""
    canon = ts._canonicalizer(_roster_cfg(tmp_path, _ROSTER))
    sigs: dict[str, ts.Signals] = {}
    ts._account_pr(
        sigs,
        canon,
        author="Paloma Gupta",
        repo="o/r",
        number=923,
        comment_bodies=[
            _verdict_body("Tariq.Morales", "Replied", None),
            _verdict_body("Tariq Morales (QA)", "Replied", None),
        ],
        ci_red=False,
    )
    assert sigs["Paloma Gupta"].gate_bypasses == 1


# --------------------------------------------------- distribution_health


def test_distribution_health_healthy_spread() -> None:
    r = ts.distribution_health([2, 3, 4, 5])
    assert r.degenerate is False
    assert r.reasons == []
    assert (r.minimum, r.maximum, r.spread, r.n) == (2, 5, 3, 4)


def test_distribution_health_all_pinned_min() -> None:
    r = ts.distribution_health([1, 1, 1, 1])
    assert r.all_at_min is True
    assert r.degenerate is True
    assert "min" in r.reasons[0]


def test_distribution_health_all_pinned_max() -> None:
    r = ts.distribution_health([5, 5, 5])
    assert r.all_at_max is True
    assert r.degenerate is True
    assert "max" in r.reasons[0]


def test_distribution_health_zero_variance_off_the_rails() -> None:
    # Everyone identical but NOT at a rail → zero-variance flag, not min/max.
    r = ts.distribution_health([3, 3, 3])
    assert r.zero_variance is True
    assert r.all_at_min is False and r.all_at_max is False
    assert r.degenerate is True
    assert r.variance == 0.0


def test_distribution_health_low_variance_flagged() -> None:
    r = ts.distribution_health([3, 3, 3, 4])
    assert r.low_variance is True
    assert r.zero_variance is False
    assert r.spread == 1
    assert r.degenerate is True


def test_distribution_health_accepts_dict_and_empty() -> None:
    d = ts.distribution_health({"a": 2, "b": 4})
    assert d.n == 2 and d.degenerate is False
    e = ts.distribution_health([])
    assert e.n == 0 and e.degenerate is False and e.reasons == ["no scores to assess"]
