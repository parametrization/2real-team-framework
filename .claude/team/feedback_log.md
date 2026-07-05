# Team Feedback Log — 2real-team-framework

Track all feedback events here. Format:

```
## [DATE] — [FROM] → [TO] — Severity: [minor/moderate/severe]
[Feedback content]
[Action taken, if any]
```

---

## Retrospective: Wave 5 (Phase 5 Wave 2, "Installer robustness — build tranche") — 2026-07-05

> **The build wave.** Implemented what Wave 1 designed: the install/test/teardown harness, the golden
> manifest, and the consented backup/amend/restore installs at user + repo level. Closed the load-bearing
> **G1** gap. Third consecutive fully-clean mechanical score.

### Wave Metrics
- **4 PRs merged** into `deployments/phase5/wave-2`: #144 (#107, Ibrahim), #143 (#139, Nia),
  #147 (#105, Tariq), #146 (#108, Paloma). **6 issues closed** (#105/#107/#108/#138/#139/#145).
- **0 changes-requested cycles** — all 4 cross-assigned charter reviews returned `Replied` / `Must-fix: None`.
  Integrated tip: `ruff` clean, **442 tests** (376→442, +66); reinstall-parity + golden-manifest drift guards in sync.
- **Counter drift: zero** — recorded (4 / 0 / 25%) == recomputed.
- Post-merge activation verified: `files_installed_complete` grades on all cells (was a pending-#139 skip);
  `install_success_rate 1.00`.
- Tech-debt filed: **#148** (cli_bridge_soft_degrade impl + --compare CI gate), **#149** (durability/fidelity
  hardening: parent-dir fsync, foreign-asset detection, child/meta manifest snapshot). Deferred: **#142** (product uninstall).

### Top-Implementer Concentration
Ibrahim 1 / Nia 1 / Tariq 1 / Paloma 1 → **max 1 / 4 = 25%**. Perfectly even; no fragility flag.

### Per-Engineer Assessments
All four: `prs_merged=1, must_fix_received=0, ci_red=0, false_positives=0` → **delta 0** (single clean PR
is not a bump). Hold at **4 across the board**. See `trust_matrix.md` Wave 5.

### Top 3 Going Well
1. **Cross-PR contracts held exactly** — Nia's `expected_install_set` seam and Ibrahim's consent/backup
   module API were both consumed verbatim (#105 auto-wired with zero change; #108 reused the module). Pinning
   the contracts in the kickoff brief paid off — parallel tracks converged without divergence.
2. **The quality oracle caught a bug in itself, pre-merge** — a latent config-shape mismatch (flat permutation
   dict vs #139's nested dotted config) would have silently mis-graded child/meta/no-team installs. Both #105
   reviewers flagged it independently; the pre-merge fix surfaced a deeper model-token spelling mismatch neither
   caught. Fixed correct-by-construction rather than shipped correct-by-coincidence.
3. **G1 closed** — the load-bearing invisible dependency (agent-teams flag) is now a consented, idempotent,
   backup-safe user-level install; a fresh clone can be made team-capable without hand-editing `~/.claude`.

### Top 3 Pain Points
1. **"Correct by coincidence" nearly shipped** — the seam bug was non-blocking only because the current matrix
   happens to run the metric solely on single-repo+team cells. Lesson: for a *measurement* tool, a metric that
   silently defaults is worse than one that errors. Consider: metrics should fail-loud on unresolved config,
   not fall back to a default set. (Process note, not a charter change yet.)
2. **`must_fix_caught` still under-credits QA** — the reviewers' most valuable find (the seam) registered as
   tech-debt, and its fix as orchestrator-directed hardening, so no reviewer scored a "catch." Third wave running
   this pattern; worth a scoring-model look in a later wave.
3. **Harness completeness deferred** — `cli_bridge_soft_degrade` unimplemented and `--compare` not yet a CI gate
   (#148); the harness measures well but isn't yet a standing CI guard.

### Proposed Process Changes
1. **(Candidate, not applied)** Metrics in the harness should **fail-loud on unresolved/unknown config** rather
   than silently returning a default expected-set — Rationale: Wave 5's seam bug. Fold into #148 when the harness
   is hardened; surface for owner approval then.
2. *(No charter amendments proposed — the review process worked: the seam was caught by review, escalated, fixed.)*

> **Phase 5 opens.** First wave of the installer-robustness phase: a *discovery* tranche that
> defines what a good install looks like before Wave 2 builds the harness. Two `[Explore]` spikes
> + one design spec + one code fix. Notably, the #131 scorer fix landed here — so this is the
> **second consecutive fully-clean mechanical score** and the first where the machinery had *no*
> known scoring artifacts left to override around.

### Wave Metrics
- **4 PRs merged** into `deployments/phase5/wave-1`: #134 (#131, Paloma), #135 (#106, Ibrahim),
  #136 (#103, Tariq), #137 (#104, Nia). 4 issues closed (#103/#104/#106/#131).
- **0 changes-requested cycles** — all 4 cross-assigned charter reviews returned `Replied` / `Must-fix: None`.
  Integrated tip: `ruff` clean, **376 tests** (373→376, +3 from the #131 regression suite). Reinstall-parity in sync.
- **Counter drift: zero** — recorded (4 / 0 / 25%) == recomputed (4 / 0 / 25%).
- Tech-debt filed: **#138** (metric-record `record_id` collision across permutations → #105),
  **#139** (install-quality metric-vocabulary reconciliation in #103's doc), **#141** (pre-existing
  flaky `test_meta_install_aggregate_is_idempotent` under full-suite load — surfaced by Ibrahim's #134 review).

### Top-Implementer Concentration
Paloma 1 / Ibrahim 1 / Tariq 1 / Nia 1 → **max 1 / 4 = 25%**. Perfectly even; no fragility flag.
Deliberate 1-issue-per-engineer split for a discovery wave.

### Per-Engineer Assessments
All four: `prs_merged=1, must_fix_received=0, ci_red=0, false_positives=0, rework=0` → **delta 0**
(single clean PR is not a bump). Hold at **4 across the board**. Reviews substantive but all
non-blocking (Nia's 4 #103 follow-ups, Tariq's #104 `record_id` catch → tech-debt #138/#139), so
`must_fix_caught=0` mechanically. See `trust_matrix.md` Wave 4 for the full table.

### Top 3 Going Well
1. **The dogfood loop closed on itself** — #131 (surfaced by Phase 4's own re-score) fixed and
   verified in this wave; the scorer now has zero known artifacts and scored the wave clean by construction.
2. **Discovery-first sequencing paid off** — #103's metric vocabulary was reused verbatim by #104,
   and cross-review caught real spec defects (record_id collision) *before* any harness code exists to inherit them.
3. **The #106 audit found a load-bearing gap (G1)** — the agent-teams env flag the installer never
   writes — independently confirmed by grep in review. This is the concrete justification for the Wave 2 user-level installer.

### Top 3 Pain Points
1. **Two design docs can silently diverge** — #103 and #104 nearly disagreed on `install_success_rate`
   granularity; caught in review, tracked as #139. A shared metric glossary would prevent recurrence.
2. **`must_fix_caught` under-credits QA on clean waves** — genuinely good review work (Nia/Tariq)
   registers as tech-debt, not a scored catch. Not a bug, but the signal set gives reviewers no
   upside on a clean wave. Watch across waves; consider a tracked-tech-debt review signal later.
3. **Owner-decision items accumulate across spikes** — 11 OWNER-DECISION callouts across #103/#106/#104
   now need wave-end sign-off in one batch (below). Manageable here; would not scale to a larger spike wave.

### Proposed Process Changes
1. **Batch owner-decision sign-off at wave-end** (done this wave) — Rationale: spikes intentionally
   defer behavior-changing calls; collecting them into one approval gate keeps the owner in control
   without blocking mid-wave. No charter change proposed; already the practice.
2. *(No charter/skill amendments proposed this wave — the machinery behaved as designed.)*

> **Phase 4's final wave.** Ran fully through the live state machine; the retro also closed the
> Wave 1 (Phase 4 Wave 1) authoritative re-score commitment. First wave to score clean with **zero
> manual overrides on its own signals** — the machinery is now trustworthy on itself.

### Wave Metrics
- **10 PRs merged** into `deployments/phase4/wave-2`: #121 (#117, Paloma), #122 (#77, Nia),
  #123 (#90, Ibrahim), #124 (#119, Paloma), #125 (#74, Ibrahim), #126 (#118, Tariq),
  #127 (#82, Nia), #128 (#75, Tariq), #129 (#116, Ibrahim), #130 (#94, Tariq). 10 issues closed.
- **0 changes-requested cycles** — all 10 cross-assigned charter reviews returned `Replied`/clean.
  Integrated tip: `ruff` clean, **373 tests** (331→373). Reinstall-parity gate (#116) in sync.
- **Counter drift: zero** — recorded (10 / 0 / 30%) == recomputed (10 / 0 / 30%).
- Tech-debt filed: **#131** (false-positive heuristic — the last isolated re-score artifact).

### Top-Implementer Concentration
Ibrahim 3 / Tariq 3 / Paloma 2 / Nia 2 → **max 3 / 10 = 30%**. Balanced; no fragility flag.

### Wave 1 (Phase 4 Wave 1) authoritative re-score — commitment CLOSED
Prereqs #117/#119/#118 all landed this wave. The three mis-tagged approval comments
(#113/#114/#115 wrote `Request` for approvals with `Must-fix: None`) were corrected in place to
`Replied` per #118; **#112 (Paloma → Ibrahim), a genuine `Request` with a real blocking must-fix,
was left intact.** Re-score: Ibrahim/Paloma/Tariq delta 0 (authoritative, clean); Nia held 0 (raw
−1 = confirmed #131 artifact: `review_false_positives` fired on a "false-positive watch" phrase she
filed under `Tech-debt:`, though she raised zero must-fixes). Durable scores unchanged (Nia 4,
others 3) — now **earned, not held**. 2 of 3 contamination sources eliminated; the 3rd isolated
as #131. This validates the Phase 4 thesis end-to-end: surface defects in W1 → fix in W2 →
re-score W1 clean.

### Per-Engineer Assessments (Wave 3)
All four earn delta **+1** (≥2 clean PRs, must_fix_received=0, ci_red=0, fp=0). Nia's arithmetic
5 is capped to 4 by distribution discipline (not the singular top performer; top output only
reached 4). **New durable scores: Ibrahim 3→4, Tariq 3→4, Paloma 3→4, Nia 4 (held at cap).** The
team converges at 4 — steady-state high trust, exactly the Phase 4 target. Forced negative-signal
lines: three "metrics clean" (with receipts) + Tariq's real gap (must_fix_caught=0 despite QA
role). No retirement triggers fire (no score ≤2 or CI-red streaks).

### Top 3 Going Well
1. **The machinery self-scores clean** — first wave with an uncontaminated signal set; the
   #118-corrected review grammar produced zero phantom must-fixes and zero false-positives.
2. **Re-score commitment honored end-to-end** — the two-wave loop (surface → fix → re-score)
   closed, converting Wave 1 from "held-flat pending" to authoritative with a single documented
   residual (#131).
3. **Balanced, clean delivery** — 10/10 PRs, 30% concentration, 0 CR cycles, 373 green, reinstall
   parity gate live.

### Top 3 Pain Points
1. **One residual scorer defect (#131)** — the false-positive heuristic fires on vocabulary, not
   on an actually-raised must-fix; still forces a documented override for Nia's Wave 1 line.
2. **QA caught nothing mechanically (must_fix_caught=0 team-wide)** — the wave genuinely had no
   real defects, but reviews were lighter-touch approvals; watch that review pressure doesn't
   decay as the tech-debt floor clears.
3. **Live-charter drift lingers** (#122 tech-debt) — `.claude/team/charter/charter.md:26` still
   reads `--force`; the modular-vs-monolithic dogfood gap (Nia) is unresolved.

### Proposed Process Changes (approval-gated — not yet applied)
1. **Fix #131** — gate `review_false_positives` on an actually-raised `Must-fix:` item (reuse
   `_has_must_fix_items`). *Rationale: the last known false signal in the scorer.*
2. **Reconcile live-charter drift** — reinstall/refresh the monolithic dogfood charter, or file
   the modular-charter migration. *Rationale: closes the source↔runtime gap #116 targets.*
3. **Phase 4 is complete** (tech-debt floor reached; only exploratory #101–#110 and the fresh
   #131 remain). Promote `deployments/phase4/wave-2` → `main` + release, then open a Phase 5
   theme decision. *Rationale: nothing Phase-4-scoped remains open.*

### Re-score status
Wave 1 (P4W1): **CLOSED** — authoritative, #131 caveat noted. Wave 3 (P4W2): clean, no pending
re-score.

---

## Retrospective: Wave 2 (Phase 4 Wave 1, "self-hosting & quality machinery") — 2026-07-05

> **First live retro.** State machine drove the wave (via #99); counters recorded live at wrapup,
> no backfill. Two Phase 4 exit criteria met: state written live, retros need no backfill.

### Wave Metrics
- **4 PRs merged** into `deployments/phase4/wave-1` — #112 (#100, Ibrahim), #113 (#98, Paloma),
  #114 (#99, Nia), #115 (#111, Tariq). 4 issues closed (#98/#99/#100/#111).
- **1 legitimate changes-requested cycle** (Paloma → #112, test-union merge order; resolved by
  Ibrahim's rebase). Recorded `wave_2_changes_requested_cycles=1`.
- CI green on every PR; integrated tip: `ruff` clean, **331 tests** (270→331; union suite +
  #114/#115 additions). Counter drift: **zero** (recomputed = recorded).
- Tech-debt filed this retro: **#116** (owner reinstall rule), **#117/#118/#119** (retro defects).

### Top-Implementer Concentration
1 PR each across 4 engineers → **max 1 / 4 = 25%**. Balanced; no fragility or theme-fit flag.

### Per-Engineer Assessments (signals contaminated — see trust matrix)
Deltas held flat. Raw signals: Ibrahim/Paloma/Tariq delta 0, Nia delta −1 (a #118 false-positive
artifact). Every author showed a phantom `must_fix_received=1` because approving reviewers wrote
`Request` (not `Replied`) and filed non-blocking notes under `Must-fix:`. See #118/#119.

### Top 3 Going Well
1. **The quality machinery runs end-to-end** — Phase 3's retro scored all-zero; this one executed
   the full pipeline and (by design) caught its own remaining defects.
2. **Clean, balanced delivery** — 4/4 PRs, 25% concentration, one real must-fix, zero CI-red.
3. **Cross-coupling reconciled in isolation** — #111 defined the vocab, #98 aligned to it, both
   pinned the same regex; three independent reviewers confirmed the coupling survives integration.

### Top 3 Pain Points
1. **Branch renderer ignores phase-local ordinal (#117)** — scored 0 PRs until manually overridden;
   the retro could not self-score. Sibling of #100.
2. **Verdict-grammar semantics unenforced (#118)** — `Request` vs `Replied` and Must-fix-vs-Tech-debt
   placement are convention-only; misuse silently contaminated trust signals.
3. **Reviewer-name splitting (#119)** — dotted vs spaced names fragment one person's ledger.

### Proposed Process Changes (approval-gated — not yet applied)
1. **Fix #117** so `{wave}` resolves to `wave_<id>_phase_ordinal` for phase-namespaced projects —
   restores authoritative self-scoring. *(Rationale: retro must not need a manual base override.)*
2. **Fix #118** — charter clarity + gate warning on the two misuse patterns. *(Rationale: the
   scorer is only as good as the review vocabulary; structure-only enforcement isn't enough.)*
3. **Fix #119** — roster-normalize captured names before bucketing. *(Rationale: split identities
   silently understate reviewer contribution.)*
4. **Adopt #116** — reinstall-on-change rule to end source↔runtime drift.
5. Minor fold-ins (from PR reviews, non-blocking): `/wave-start` allocate-idempotency guard
   (re-run double-advances state); `_phase_for_wave`↔`lifecycle.phase_of` shared resolver;
   `merged_prs` phase-passthrough + bad-JSON fail-open tests; wave-end in `DUAL_DEPLOY_REQUIRED`.

### Re-score commitment
Once #117/#118/#119 land, re-run `trust_signals score` on this wave's corrected comments and
replace the flat-held deltas with authoritative numbers (same commitment the Phase 3 entry made).

---

## Retrospective: Wave 1 (Phase 3, "installer overhaul → v0.4.0") — 2026-07-05

> **Reconstructed retro.** Phase 3 was run without the lifecycle state machine (no
> `state.json`). State was backfilled on 2026-07-05 from the merged-PR record and this retro
> run then. Phase 3's three "waves" all merged to a single integration branch
> (`deployments/phase3/wave-1`), so mechanically they are **one** tracked wave (global wave 1)
> covering all 13 PRs — they cannot be split three ways after the fact by base branch.

### Wave Metrics
- Merged PRs: **13** (into `deployments/phase3/wave-1`), rolled to `main` via PR #97, shipped v0.4.0.
- Issues closed: 12 wave issues (#64–#70, #73, #85–#88) — closed 2026-07-05 via /wave-audit.
- CI health: green at every merge head (PRs before #76 predate CI-on-wave-branches, so no checks).
- Merge model: **wave-branch** (features → wave branch → main). NOTE: config declares
  `direct-to-main` — the config/practice mismatch is open tech-debt #94.
- Counter corrections: none — counters were reconstructed at retro time from PR data, not
  recorded at a historical wrapup, so drift is zero by construction.

### Top-Implementer Concentration
Ibrahim El-Amin 5 / 13 = **38%** — below the 60% force-call threshold. Load was reasonably
spread across four engineers (Ibrahim 5, Nia 3, Paloma 3, Tariq 2). *Theme-fit:* the wave was
installer/bootstrap-heavy, Ibrahim's domain. No fragility flag.

### Per-Engineer Assessments (signals + deltas)
Extraction note: `trust_signals.py` returned **all-zero** review signals because it matches the
verdict token `ChangesRequested`, but this project's charter convention writes
`RequestOrReplied: Request` with severity in the body (`Must-fix:`). The must-fix signals below
are a **supplementary manual tally** of the `Must-fix:` markers; the pure scoring layer
(`score_delta`/discipline) was then run on the corrected signals. Deltas are therefore
**provisional** pending the vocabulary fix (see proposed changes).

- **Nia Rossi** — prs_merged=3, must_fix_received=0, must_fix_caught=1, ci_red=0 → delta **+1** →
  **3→4**. Only fully-clean author with ≥2 PRs. Negative-signal line: *metrics clean*.
- **Ibrahim El-Amin** — prs_merged=5, must_fix_received=2 (#78, #96), caught=0, ci_red=0 →
  delta **0** → **3→3**. Highest output, but two rework rounds keep it off a bump.
  Negative-signal line: *2 must-fix received*.
- **Paloma Gupta** — prs_merged=3, must_fix_received=1 (#79 rebase/semantic-conflict), caught=0 →
  delta **0** → **3→3**. Negative-signal line: *1 must-fix received*.
- **Tariq Morales** — prs_merged=2, must_fix_received=1 (#93, from Nia), must_fix_caught=3,
  ci_red=0 → delta **0** → **3→3**. Reviewed nearly every PR and caught the most issues, but the
  model gates the reviewer +1 behind being "clean," and he received one must-fix → no bump.

### Top 3 Going Well
1. Clean delivery: 13 PRs, zero CI-red merges, shipped v0.4.0 to both registries first try.
2. Real review pressure: QA (Tariq) reviewed nearly every PR; must-fixes were raised and resolved
   (e.g. #79's semantic ontology-conflict rebase) rather than waved through.
3. Load spread across four engineers (38% top concentration) despite an installer-heavy theme.

### Top 3 Pain Points
1. **The framework didn't dogfood its own lifecycle state machine** — Phase 3 ran with no
   `state.json`; this retro was only possible by after-the-fact backfill.
2. **Trust-scoring is blind to this project's own review vocabulary** — `trust_signals.py`
   matches `ChangesRequested`; the charter uses `Request` + body `Must-fix:`. Left uncorrected,
   every engineer scores falsely "clean → +1."
3. **Waves weren't isolated as branches** — 2 & 3 shared wave-1's integration branch, so
   per-wave mechanical scoring is impossible retroactively.

### Proposed Process/Framework Changes (approval-gated — not yet applied)
1. Fix `trust_signals.py` verdict vocabulary to match the charter (`Request`/`Replied` + body
   `Must-fix:` severity), OR align the charter to emit `ChangesRequested`. → new tech-debt issue.
2. Drive every wave through `lifecycle.py` (allocate→…→wrapup) so `state.json` exists live and
   retros need no backfill. Wire it into /wave-start and /wave-end. → new tech-debt issue.
3. Reconcile `policy.merge_model` (`direct-to-main`) vs actual wave-branch practice — already
   tracked as **#94**.
4. Make `branch.integration` phase-aware (template supports only `{wave}`, not `{phase}`), so
   phase-namespaced projects can be scored without hand-editing config. → new tech-debt issue.
