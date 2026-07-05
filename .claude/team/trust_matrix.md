# Trust Identity Matrix

All team members maintain a trust score for every other team member they interact with.

## Scale

| Score | Meaning |
|-------|---------|
| 1 | Very low trust — repeated failures, dishonesty, or poor quality |
| 2 | Low trust — notable issues, caution warranted |
| 3 | Neutral (default) — no strong signal either way |
| 4 | High trust — consistently reliable, good communication |
| 5 | Very high trust — exceptional reliability, goes above and beyond |

## Rules

- **Default:** Every pair starts at **3**.
- **Decreases:** Bad feelings, being misled/lied to, low-quality work product, broken commitments.
- **Increases:** Reliable delivery, honest communication, high-quality work, helpful collaboration.
- **Scope:** Trust is directional — A's trust in B may differ from B's trust in A.

## Matrix

Rows = the team member rating. Columns = the team member being rated.

| Rater / Rated | Hiro Morales | Nia Rossi | Paloma Gupta | Ibrahim El-Amin | Tariq Morales |
|---------------|---|---|---|---|---|
| Hiro Morales |
| Nia Rossi |
| Paloma Gupta |
| Ibrahim El-Amin |
| Tariq Morales |

## Change Log

*(Record trust changes here with date, rater, rated, old score, new score, and reason.)*

## Wave 1 Trust Updates (2026-07-05) — Phase 3 installer overhaul → v0.4.0

> **Provisional / reconstructed.** Backfilled retro (no live `state.json`). Review signals are a
> manual `Must-fix:` tally because `trust_signals.py` couldn't parse this project's `Request`
> verdict vocabulary (tech-debt). Re-score authoritatively once that bug is fixed before treating
> these as durable. Scores are per-engineer (retro model), not the directional pairwise matrix above.

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Nia Rossi | 3 | 4 | delta +1: prs_merged=3, must_fix_received=0, ci_red=0 (clean, ≥2 PRs); caught=1 as reviewer |
| Ibrahim El-Amin | 3 | 3 | delta 0: prs_merged=5 but must_fix_received=2 (#78, #96) → not clean, no bump |
| Paloma Gupta | 3 | 3 | delta 0: prs_merged=3, must_fix_received=1 (#79 semantic-conflict rebase) → not clean |
| Tariq Morales | 3 | 3 | delta 0: must_fix_caught=3 (top reviewer) but must_fix_received=1 (#93); reviewer +1 is gated behind clean |

### Done Well / Needs Improvement (Wave 1)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Nia Rossi | Only fully-clean author with ≥2 PRs; caught 1 must-fix as reviewer | metrics clean: prs_merged=3, must_fix_received=0, ci_red=0, false_positives=0, must_fix_caught=1 |
| Ibrahim El-Amin | Highest output (5 PRs), 0 CI-red | 2 must-fix received (#78, #96) — two rework rounds |
| Paloma Gupta | 3 PRs merged, 0 CI-red | 1 must-fix received (#79 rebase/semantic ontology conflict) |
| Tariq Morales | Reviewed nearly every PR; caught the most must-fixes (3) | 1 must-fix received (#93, from Nia) |

## Wave 2 Trust Updates (2026-07-05) — Phase 4 Wave 1: "self-hosting & quality machinery"

> **AUTHORITATIVE re-score (2026-07-05), replacing the earlier flat-hold.** The three
> prerequisites landed in Phase 4 Wave 2 — #117 (branch phase-ordinal), #119 (name
> normalization), #118 (verdict-grammar semantics) — so the scorer now finds all 4 PRs
> (#112–#115) with no base override and buckets by unified identity (no `Tariq.Morales` split).
> The three mis-tagged approval comments (#113/#114/#115 wrote `RequestOrReplied: Request` for
> what were approvals with `Must-fix: None`) were corrected in place to `Replied` per #118,
> clearing the phantom `must_fix_received` and phantom reviewer "catches". **PR #112
> (Paloma → Ibrahim) is a genuine `Request` with a real blocking must-fix and was left intact.**
> Result: deltas Ibrahim 0, Paloma 0, Tariq 0, Nia 0. Nia's raw −1 is a confirmed artifact of a
> newly-isolated scorer defect (**#131** — `review_false_positives` fires on the phrase
> "false-positive" even when the comment raised no must-fix; her clean approval mentioned a
> "false-positive watch" under `Tech-debt:`), not performance — held at 0. Durable scores
> unchanged from the flat-hold, but now **earned**: 2 of 3 contamination sources eliminated, the
> 3rd isolated as #131.

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Ibrahim El-Amin | 3 | 3 | delta 0 (authoritative): prs_merged=1 (#112/#100), must_fix_received=1 — the wave's one **real** must-fix (Paloma, add/add test conflict), resolved by clean rebase. |
| Paloma Gupta | 3 | 3 | delta 0 (authoritative): prs_merged=1 (#113/#98), clean; must_fix_caught=1 as reviewer (raised the real #112 blocker). A single clean PR is not a bump. |
| Nia Rossi | 4 | 4 | delta 0 (held): raw −1 is the confirmed #131 false-positive artifact (0 must-fixes raised ⇒ 0 retractable). TL; dogfooded the lifecycle live (#99). |
| Tariq Morales | 3 | 3 | delta 0 (authoritative): prs_merged=1 (#115/#111), metrics clean; the phantom must_fix_received cleared once #113's grammar was corrected. |

### Done Well / Needs Improvement (Wave 2 / Phase 4 Wave 1) — re-scored

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Ibrahim El-Amin | Root-caused the silent zero-PR bug behind #100; clean rebase to resolve the real test-union must-fix | 1 must-fix received (#112, genuine — the wave's only real change-request) |
| Paloma Gupta | Only reviewer to raise a real blocking must-fix (#112); corpus-driven tests | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, false_positives=0, must_fix_caught=1 |
| Nia Rossi | Dogfooded lifecycle to live state; sharp dual-deploy lib-resolution call | raw fp=1 is the #131 scorer defect (false-positive phrase-match on a `Tech-debt:` note), not a real retraction |
| Tariq Morales | Authored the verdict-grammar gate (#111) whose semantics (#118) enabled this very re-score | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, false_positives=0 |

## Wave 3 Trust Updates (2026-07-05) — Phase 4 Wave 2: "quality-machinery hardening & tech-debt floor"

> **First fully-clean mechanical score — zero manual overrides on this wave's own signals.**
> Reviewers used the #118-corrected grammar (every verdict `Replied` + `Must-fix: None`;
> non-blocking notes under `Tech-debt:`), so the signal set is uncontaminated — no phantom
> must-fixes, zero false-positives. 10 PRs, 0 changes-requested cycles, 30% top concentration;
> counter drift zero (recomputed = recorded). Every engineer earns delta +1 (≥2 clean PRs, 0
> must-fix received, 0 CI-red, 0 fp). **Distribution discipline caps Nia's arithmetic 5 to 4** —
> the wave's top output (Ibrahim & Tariq, 3 PRs each) only reached 4, so there is no singular
> standout warranting a 5; the team converges at 4 (steady-state high trust).

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Ibrahim El-Amin | 3 | 4 | delta +1: prs_merged=3 (#123/#125/#129), must_fix_received=0, ci_red=0, fp=0 — clean, ≥2 PRs. Shipped the flagship reinstall gate (#116). |
| Tariq Morales | 3 | 4 | delta +1: prs_merged=3 (#126/#128/#130), all clean; authored #118 whose semantics unblocked the Wave 1 re-score. |
| Paloma Gupta | 3 | 4 | delta +1: prs_merged=2 (#121/#124), clean; delivered both re-score prerequisites (#117/#119) with disjoint-diff discipline. |
| Nia Rossi | 4 | 4 | delta +1 arithmetic → 5, **capped to 4** by distribution discipline (not the singular top performer). prs_merged=2 (#122/#127), clean; TL #77↔#116 coordination. |

### Done Well / Needs Improvement (Wave 3 / Phase 4 Wave 2)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Ibrahim El-Amin | Shipped reinstall-on-change + CI parity gate (#116); 3 clean PRs, correct byte-mirror scoping | metrics clean: prs_merged=3, must_fix_received=0, ci_red=0, false_positives=0, must_fix_caught=0 |
| Tariq Morales | Authored the verdict-grammar semantics (#118) that made the re-score possible; 3 clean PRs | metrics clean numbers, but must_fix_caught=0 as reviewer despite the QA role — watch review depth as the tech-debt floor clears |
| Paloma Gupta | Both re-score prerequisites (#117/#119); pre-empted the test-file conflict with disjoint hunks | metrics clean: prs_merged=2, must_fix_received=0, ci_red=0, false_positives=0, must_fix_caught=0 |
| Nia Rossi | TL cross-issue coordination — the #77↔#116 refresh-vs-force call that kept two PRs from fighting | capped from an arithmetic 5: prs_merged=2, no singular-standout composite this wave |

## Wave 4 Trust Updates (2026-07-05) — Phase 5 Wave 1: "Installer robustness — discovery tranche"

> **Steady state confirmed — a second consecutive fully-clean mechanical score.** A discovery
> wave: two `[Explore]` spikes (#103 taxonomy+metrics, #106 user-space audit), one design/spec
> (#104 methodology), one code fix (#131 scorer false-positive gate). 4 PRs, 0 changes-requested
> cycles, 25% top concentration (one PR each — perfectly even load), counter drift zero. The
> #131 fix landed this wave, so the scorer's own last artifact is now closed: the signal set is
> clean *by construction*, no override needed. Every engineer scores **delta 0** — a single clean
> PR is not a bump (policy) — so the team holds at **4 across the board**. No decay (all had signal
> this wave). Reviews were substantive (Nia raised 4 tracked follow-ups on #103; Tariq caught a
> real `record_id` join-key collision on #104) but all non-blocking → filed as tech-debt (#138/#139),
> so `must_fix_caught=0` mechanically for every reviewer. Clean work, not shallow review.

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Ibrahim El-Amin | 4 | 4 | delta 0: prs_merged=1 (#135/#106), must_fix_received=0, ci_red=0, fp=0 — clean, but a single clean PR is not a bump. |
| Nia Rossi | 4 | 4 | delta 0: prs_merged=1 (#137/#104), clean; single clean PR, no bump. Substantive review of #103 (4 tech-debt) registers non-blocking. |
| Paloma Gupta | 4 | 4 | delta 0: prs_merged=1 (#134/#131), clean; single clean PR, no bump. |
| Tariq Morales | 4 | 4 | delta 0: prs_merged=1 (#136/#103), clean; single clean PR, no bump. Caught the #104 record_id collision (tech-debt #138). |

### Done Well / Needs Improvement (Wave 4 / Phase 5 Wave 1)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Ibrahim El-Amin | Audit surfaced the load-bearing **G1** invisible dependency (agent-teams flag never written by the installer) — the finding that justifies #107 | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, false_positives=0, must_fix_caught=0 |
| Nia Rossi | Methodology consumed #103's B1–B12 + metric ids verbatim; flagged `cli_bridge_soft_degrade` as an explicit fold-in rather than silently redefining | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, false_positives=0, must_fix_caught=0 (review depth good but all non-blocking) |
| Paloma Gupta | Shipped the #131 scorer gate with a real coupling test (the exact #115 shape) + positive guard; independently confirmed G1 as #135 reviewer via grep | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, false_positives=0, must_fix_caught=0 |
| Tariq Morales | Taxonomy + ~31 metrics grounded in real installer exit codes; as #137 reviewer caught the `record_id` join-key collision (a genuine spec defect → #138) | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, false_positives=0, must_fix_caught=0 |
