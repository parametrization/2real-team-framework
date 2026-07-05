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

> **Deltas held FLAT this wave — by evidence, not omission.** The scoring pipeline ran
> end-to-end for the first time (Phase 3's ran zero), but two defects it *surfaced* contaminate
> the signals: verdict-comment grammar misuse (#118 — approvers wrote `Request` not `Replied`
> and filed non-blocking notes under `Must-fix:`) and reviewer-name splitting (#119 — dotted vs
> spaced names bucket apart). The raw deltas (Ibrahim 0, Paloma 0, Tariq 0, Nia −1) are artifacts
> of those defects (Nia's −1 = a false-positive from a note she filed under Must-fix), not
> performance. Scoring the wave's base branch also required a manual override (#117 — branch
> renderer used the global wave seq, not the phase-local ordinal, → 0 PRs). **Re-score
> authoritatively once #117/#118/#119 land.**

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Ibrahim El-Amin | 3 | 3 | held flat — raw delta 0; signals contaminated by #118/#119. 1 PR merged (#112, #100), rebased cleanly to resolve the one real must-fix (Paloma). |
| Paloma Gupta | 3 | 3 | held flat — raw delta 0; raised the wave's only legitimate must-fix (#112 test-union) as reviewer. |
| Nia Rossi | 4 | 4 | held flat — raw delta −1 is a #118 artifact (false-positive from a non-blocking note filed under Must-fix). TL; dogfooded the lifecycle live (#99). |
| Tariq Morales | 3 | 3 | held flat — raw delta 0; authored the gate (#111) that defines the vocab; name-split (#119) fragmented his reviewer credit. |

### Done Well / Needs Improvement (Wave 2 / Phase 4 Wave 1)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Ibrahim El-Amin | Root-caused the silent zero-PR bug behind #100; clean rebase to resolve the test-union conflict | verdict comment on #114 used `Request` + empty `Must-fix:` (should be `Replied`) — contributed to #118 |
| Paloma Gupta | Only reviewer to raise a real blocking must-fix; corpus-driven tests | verdict comment on #112 is the one clean grammar example, but #113's own reviewer flagged latent name-split she inherited |
| Nia Rossi | Dogfooded lifecycle to live state; sharp dual-deploy lib-resolution call | filed a non-blocking false-positive-watch under `Must-fix:` on #115 (#118) → self-inflicted −1 signal |
| Tariq Morales | Authored the verdict-grammar gate; pinned the coupling test | wrote `Requestor: Tariq.Morales` (dotted) → split his own reviewer credit (#119), the very bug he flagged |
