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
