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

## Retrospective: Wave 6 (Phase 6 Wave 1) — 2026-07-06 — "Prove it on real repos" (validation)

### Wave Metrics
- **5 PRs merged** to `deployments/phase6/wave-1`: #154 (#153 real-repo provisioner, Paloma), #157
  (#109 botfarm upgrade study, Ibrahim), #156 (#101 noorinalabs reconcile, Paloma), #159 (#152
  installer docs, Nia), #160 (#149 durability hardening, Ibrahim).
- **3 changes-requested cycles** (all Tariq): #154, #156, #160 — each amended in place to
  `Replied`/`Must-fix: None` after the fix landed.
- Issues closed: #153, #101, #109, #152, #149. Tech-debt filed: #161 (CONTRIBUTING flag-table
  row), #162 (amend-path stale config module lists / finding-6), #163 (unguarded `os.close` in
  `_fsync_dir`), #164 (amend-in-place erases per-reviewer must_fix_caught from the scorer). #102
  (18-asset noorinalabs port) deferred to Wave 2 as a per-hook rewiring effort.
- CI health: 0 CI-red merges; every PR merged CLEAN (11/11 checks).
- **Lifecycle reconciliation:** the Wave-1 kickoff was never persisted last session
  (`state.json` read `current_wave=wave-5`); reconstructed via the full allocate→start→scope→
  kickoff→wrapup sequence (commit `922614f`). Wave physically ran on GitHub the whole time.

### Counter Corrections
- `changes_requested_cycles`: **claimed 3, recomputed 0 → claimed stands.** The recompute-to-0 is
  fully explained by the in-place verdict amendments (`trust_signals` reads current comment state).
  Recorded as `wave_6_counter_corrections` (measurement conflict, not an arithmetic error). This is
  the trigger for **#164**.

### Top-Implementer Concentration
- max PRs by one author = 2 (Paloma **and** Ibrahim) / 5 total = **40%**. Below the 60% force-call
  threshold; load spread across three authors on a validation-themed wave. Healthy.

### Per-Engineer Assessments (reconstructed — see #164)
- **Tariq Morales** — must_fix_caught=**3**, all load-bearing and mutation-proven (revert-the-fix →
  test fails). Delta **+1 → 4→5** (distribution-discipline reserved 5: the singular top performer,
  3 catches vs 0 for all others; first earned 5 in project history). Also caught the orchestrator's
  Requestor/Requestee attribution swap on #159/#160.
- **Paloma Gupta** — prs_merged=2, must_fix_received=**2** (#154, #156 both shipped new behavior
  without its test). Delta **0 → 4** (not clean ⇒ no bump; <3 received ⇒ no ding). Negative-signal
  line: repeated ship-without-test pattern, same root cause twice in one wave.
- **Ibrahim El-Amin** — prs_merged=2 (#157 clean, #160 rework), must_fix_received=1 (tautological
  fsync test). Delta **0 → 4**. Negative-signal line: the tautological test landed in the exact fix
  that mattered most (durability).
- **Nia Rossi** — prs_merged=1 (#159 docs), clean. Delta **0 → 4** (single clean PR is not a bump).
  Negative-signal line: lowest output this wave; watch for decay if signal stays quiet.

### Top 3 Going Well
1. **The validation theme paid off in the wild:** the read-only source-unchanged invariant held
   across all real sources (no `SourceMutatedError`); botfarm restored byte-identical on a 150-file
   diverged install; live-pin resolution caught botfarm's `main` advancing mid-session; and real
   durability bugs (parent-dir fsync gap, archive non-atomicity) surfaced and were fixed same-wave.
2. **QA depth is real, not theater:** 3 genuine load-bearing catches, each mutation-proven
   non-tautological before clearing — exactly the bar that keeps the quality oracle honest.
3. **Clean delivery under real review pressure:** 0 CI-red, every PR CLEAN at merge, tech-debt
   triaged into tracked issues rather than dropped.

### Top 3 Pain Points
1. **The verdict amend-in-place convention erases per-reviewer scoring signal** (#164). The
   mechanical scorer, run post-amendment, reported `must_fix_caught=0` for everyone and dropped the
   wave's standout reviewer (Tariq) from the output entirely. The retro had to hand-reconstruct.
2. **Repeated ship-without-test on new behavior** (Paloma ×2, Ibrahim ×1 tautological). The gap was
   never the logic — it was test coverage of newly-added behavior, caught only at QA. A pre-review
   self-check ("does every new behavior have a load-bearing test?") would move these left.
3. **Lifecycle state wasn't persisted at kickoff** — the wave ran for its entire life with
   `state.json` stuck at `wave-5`, requiring a full retroactive reconciliation at wrapup. The
   kickoff → state-write step is not enforced.

### Proposed Process/Framework Changes (APPROVED by owner 2026-07-06 — scheduled into a wave)

> **Owner approval 2026-07-06:** all three approved. #1 and #3 are code changes (trust scoring +
> lifecycle kickoff enforcement) to be scoped into a wave; #2 is a charter/review-process rule
> (dual-deploy: `framework/assets/**` canonical + this repo, per #116). None applied yet — they
> convert from "proposed" to "accepted backlog" and land through the normal wave/team flow.

1. **Resolve #164** so per-reviewer `must_fix_caught` survives the amendment convention (read edit
   history, or record catches at issue-time into `state.json`, or post a distinct `Replied`
   follow-up instead of editing in place). Without this, every clean-after-fix wave under-credits QA.
   **Rationale:** this wave the scorer would have zeroed the single most important contributor.
2. **Add a pre-review author self-check gate:** "every new behavior has a load-bearing (revert →
   fail) test" before requesting review. **Rationale:** all 3 must-fixes this wave were this exact
   class; moving it left saves a full review→fix→re-verify cycle each.
3. **Make lifecycle kickoff persistence non-optional** — `/wave-start` (or kickoff) should fail
   loudly if `state.json` doesn't advance `current_wave`, so a wave can't run un-stamped.
   **Rationale:** avoids the retroactive reconciliation this retro needed.

---

## Wave 7 Retro (2026-07-06) — Phase 6 Wave 2: "Close the quality/process loop" → v0.7.0

All three W6 process proposals above were **owner-approved 2026-07-06 and delivered this wave**:
proposal 1 → #164 (PR #171), proposal 2 → #167 (PR #172, hard gate), proposal 3 → #168 (PR #169).

### Metrics
- **4 PRs, 0 changes-requested cycles, 25% top concentration, 0 CI-red.** One clean PR per engineer.
- 466 → **507 tests** (+41), ruff clean, `.claude/` in sync with canonical assets.
- Reviews: Tariq (QA) on S1/S3/S4, Nia (Tech Lead) on Tariq's S2 — all `Replied`/Must-fix: None,
  each load-bearing claim independently mutation-checked (revert→fail) before clearing.
- Shipped as **v0.7.0** (minor: new hard-gate hook is a backward-compatible feature) — published to
  PyPI + npm via OIDC; `deployments-phase6-wave-2` lightweight tag on the merge commit.

### Top 3 Going Well
1. **Closed the loop the framework opened on itself:** the scorer that mis-read W6 (#164) is fixed
   and merged; kickoff can no longer run un-stamped (#168, proven this very wave — kickoff was
   stamped live and `assert-kickoff` now gates it); the load-bearing-test discipline is now a
   fail-closed machine gate (#167), not just a convention.
2. **Two W6 negative-signal patterns visibly corrected:** Paloma shipped #164 *with* its test +
   fixture (no repeat of ship-without-test); Ibrahim's #163 durability test is load-bearing this
   time (no repeat of the tautological fsync test).
3. **Clean delivery at speed:** 4 parallel worktree stories, all green first-pass, zero rework.

### Top 3 Pain Points / Watch
1. **A clean wave hides scorer coverage:** the #164 ledger fix can't be validated by a wave with no
   amendments — first contested wave (likely #102) is its real test. Don't assume it works until then.
2. **Reviewer found a real gap filed only as tech-debt (#175):** `dispatcher.py` swallows uncaught
   hook exceptions as ALLOW, undermining the very fail-closed intent of #167. A genuine
   fail-closed-guarantee hole shipped in the same wave that introduced the fail-closed hook.
3. **S2 gate is v1-scoped:** diff-wide `test_touched` (#174) and empty exception policy (#176) mean
   the gate both under-enforces (one unrelated test edit satisfies the diff) and over-blocks (pure
   refactors) until hardened. It is live in this repo — watch for friction.

### Process proposals from THIS retro (approval-gated)
1. **Harden the fail-closed guarantee before relying on it:** resolve #175 (dispatcher must not
   ALLOW on uncaught exception) as a prerequisite before the #167 gate is trusted org-wide.
   **Rationale:** a fail-closed hook behind a fail-open dispatcher is fail-open.
   **Status: APPLIED via #182** (Wave 3, S1) — `dispatcher.py` now blocks-unless-`FAIL_OPEN`: an
   uncaught `check()` exception in a fail-closed hook (incl. `require_load_bearing_test`) blocks
   instead of allowing; the 9 legacy fail-open hooks declare `FAIL_OPEN=True` (behavior unchanged).
2. **Weigh block-vs-tech-debt at review time:** Nia's dispatcher finding was real but filed as
   tech-debt, so it scored nothing and doesn't hold the merge. Consider a norm: a finding that
   defeats a shipping feature's core guarantee is a Must-fix, not tech-debt.
   **Status: APPLIED via #180** (Wave 3, S6) — the norm is now written into the charter's
   Verdict-Comment Grammar (`framework/assets/team/charter/issues.md` § Request vs. Replied,
   Must-fix vs. Tech-debt), with the #175 case as the worked example.

### Next wave (owner decision — not started)
No wave reserved. Standing flagship candidate: **#102** (mined-asset port / fork reconciliation) —
explicitly deferred to run on the scorer this wave fixed. Also open: S2 hardening tranche
(#174/#175/#176), Phase-5 debt (#142/#148/#141), #162 (installer wave), #110.

---

## Wave 8 Retro (2026-07-06) — Phase 6 Wave 3: "Fail-closed foundation + flagship asset port"

**Shipped v0.8.0** (rollup #186, meta #178). 5 PRs, **1 changes-requested cycle** (the #184
branch-freshness footgun), 40% top concentration (Nia 2 PRs), 0 CI-red, 629 tests. Owner bundled
everything flagged at the end of Wave 2: #102 flagship P0 + ready P1 donors, the S2-hardening tranche
(#174/#175/#176), and both W2-retro proposals — plus a new rename cost-out spike (#177).

### Metrics / trust
`trust_signals score 8` + distribution discipline: **Tariq 5→5** (must_fix_caught=1, the #184 catch),
**Nia 4→5** (composite tie-top: 2 clean PRs incl. the #175 keystone — second earned 5),
**Paloma 4→4** (clean flagship #185), **Ibrahim 4→4** (1 must_fix_received/rework, caught+fixed).

### Top 3 going well
1. **The #164 durable ledger fired for real.** Tariq's #184 changes-requested verdict was recorded at
   issue-time and *survived* his in-place `Request→Replied` amendment — the exact scenario it was
   built for and couldn't be validated by W2's clean wave. The quality machinery now demonstrably works.
2. **QA caught the one guarantee-defeating defect before it shipped downstream.** The branch-freshness
   `max_commits_behind=0` zero-tolerance default (pre-wired into every fresh install) would have
   blocked adopters' ordinary `gh pr create`. Escalated to Must-fix under the brand-new #180 norm —
   the norm earned its keep in its first wave.
3. **Both W2-retro proposals closed the loop:** #175 dispatcher fail-closed (proposal #1, PR #182) and
   the Must-fix-vs-tech-debt charter norm (proposal #2, PR #180). Track A hardened the gate the
   flagship then rode on — sequencing worked.

### Top 3 pain points / watch
1. **Charter tree isn't reinstall-managed.** `reinstall.py`'s `_MANAGED_TREES` covers only `skills/`,
   so `team/charter/**` edits must be hand-applied to both canonical and runtime copies — protected
   only by reviewer diligence (Paloma flagged this on #181). **Proposal below.**
2. **The promotion pipeline is untested-in-anger.** #102-P0 shipped a deterministic `promotion-audit`
   skill, but its first real memory→charter→skill→hook audit hasn't been run on this repo. Dogfood it
   next wave before trusting its auto-promotions.
3. **S2 gate residual edges (documented tech-debt, not fixed):** additive `_deep_merge` means a repo
   writing `load_bearing_test_exceptions: {}` can't clear the seeded `refactor` class; stem-naming
   doesn't retroactively pair legacy modules (`dispatcher.py`, `bootstrap.py`). Both over-block
   (fail-safe direction), acceptable for now.

### Process proposals from THIS retro (approval-gated — not yet applied)
1. **Make `reinstall.py` mirror the charter tree** (add `team/charter/**` to `_MANAGED_TREES`, or add a
   `manifest --check`-style charter-drift gate). **Rationale:** the dual-deploy #116 guarantee has a
   hole for charter edits — a silent canonical↔runtime charter drift would pass CI today. **Status:
   APPLIED via #189/PR #190 (Wave 9)** — chose the `--check` gate route (`charter_drift.py`); caught +
   remediated 4 pre-existing drifted charter modules on first run.
2. **Dogfood `promotion-audit` before relying on its auto-promotions.** Run the skill on this repo's
   own memory/charter next wave and verify its AUTO-tier promotions + DECIDE-tier draft issues by hand
   once, the way the #164 ledger got its first contested-wave validation here. **Status: APPLIED via
   #187/PR #191 (Wave 9)** — dogfooded on the real 3-candidate ledger (all DECIDE, none mis-auto);
   caught + fixed an AUTO false-positive bug (fenced-code marker match); ledger policy settled.

### Next wave (owner decision — not started)
No wave reserved. Standing flagship candidate: **#102 P2 tranche** (governance charter modules,
wave-lifecycle GH-Projects automation, ontology-consultation enforcement, headcount budget) — now
unblocked by the P0 pipeline shipped this wave. Also open: installer-completeness wave
(#162/#142/#148/#141/#155), #110 (installer-as-skill), and the two proposals above.

---

## Wave 9 Retro (2026-07-07) — Phase 6 Wave 4: "Trust the promotion pipeline"

**2 PRs · 0 changes-requested cycles (both Replied first pass) · 50% top concentration · 0 CI-red · 0
Must-fix caught.** A deliberately small hardening wave that applied BOTH Wave 8 retro proposals and
dogfooded the #102-P0 promotion pipeline for real before the larger #102 P2 tranche builds on it —
same "trust the machinery before you rely on it" discipline as the scorer-fix-before-W2 and
gate-hardening-before-W3-flagship. `trust_signals.py score 9`: both implementers clean, delta 0; no 5s
(reserved-5 not handed out for merely-clean work). Shipped as **v0.8.1** (PyPI + npm, OIDC).

### Top 3 going well
1. **Both proposals didn't just get built — they paid for themselves on first run.** S1's charter-drift
   gate immediately caught 4 pre-existing drifted charter modules; S2's dogfood caught a real AUTO
   false-positive bug (`has_promotion_markers()` bare-substring-matched a doc that *quotes* the marker
   in a fenced block). Dogfooding worked exactly as intended — the pipeline is now validated-in-anger.
2. **Cleanest wave yet: 0 changes-requested cycles, both PRs approved first pass.** Both reviewers
   (Nia on S1, Tariq on S2) independently reproduced every load-bearing claim — revert→fail on both
   fixes, twice-run byte-identical determinism diff on the promotion-audit skill — rather than trusting
   author reports. Real verification, still zero blocking findings.
3. **Ledger policy settled durably, not just for this repo.** `bootstrap.ensure_gitignore_entries()`
   wires the gitignore default into every install path, so downstream adopters never hit the
   untracked-noise surprise we did — the fix generalizes (the dual-deploy #116 instinct applied to a
   runtime-state default).

### Top 3 pain points / watch
1. **Charter-drift gate has a manifest blind spot (Nia tech-debt).** `plan()` doesn't cross-check
   `.charter-manifest.json` checksums against the live charter — a manual re-render that bypasses
   `install_charter(force=True)` could leave a stale manifest the gate won't catch, and `--refresh-charter`
   could then misclassify a module as hand-evolved. Fail-safe direction, but a real gap.
2. **`ensure_gitignore_entries` exact-line matching (Tariq tech-debt).** Matches gitignore entries by
   exact line-equality, so a variant existing form (leading `/`, glob, inline comment) would append an
   effective duplicate. And `is_owned` now treats ANY `.gitignore` at any depth as owned — one notch
   coarser, so a future genuinely-stray install-time `.gitignore` write would be silently accepted.
3. **Two clean waves in a row for the reviewers' reserved-5s (Nia, Tariq both at 5).** The reserved-5
   is per-wave and decays if a future wave goes quiet; neither had a scoring catch this wave (both
   Replied). Not a problem yet — but the 5s are now riding on prior-wave evidence, so a substantive
   contribution or real catch is due to keep them anchored.

### Process proposals from THIS retro (approval-gated — not yet applied)
1. **Close the charter-manifest blind spot:** have `charter_drift.py plan()` also verify
   `.charter-manifest.json` checksums against the live charter tree (fold Nia's tech-debt into the
   existing gate). Low effort, closes the one seam the new gate doesn't cover.
2. **Harden `ensure_gitignore_entries` matching:** normalize before compare (strip leading `/`, ignore
   inline comments, treat glob-equivalent forms as present) so re-install is truly idempotent across
   hand-edited `.gitignore` variants. Fold Tariq's tech-debt in.

### Next wave (owner decision — not started)
No wave reserved. Standing flagship candidate: **#102 P2 tranche** (governance charter modules,
wave-lifecycle GH-Projects automation, ontology-consultation enforcement, headcount budget) — now on a
**dogfooded** pipeline. Also open: installer-completeness (#162/#142/#148/#141/#155), #110, and the two
small tech-debt proposals above (both fold cleanly into an early slot of any wave).

---

## Wave 10 Retro (2026-07-07) — Phase 6 Wave 5: "PR-review state machine (dormant)" → v0.9.0

**Shape:** 3 stories / 3 PRs, **0 changes-requested cycles** (all three Replied first pass), 33% top
concentration (3 distinct authors), 694 tests (+33), 0 CI-red, 0 Must-fix caught. Shipped the #102 P2
review-gate flagship — `pr_review_state` oracle (S1), `block_gh_pr_review` submission guard (S3, live),
`validate_pr_review` merge gate (S2, dormant). Released v0.9.0 (minor; new public API + hooks). PRs
#197/#198/#199 → wave branch → rollup #200 → main.

### Going well
1. **Reconcile-not-duplicate held across all three stories.** Every hook built on 2real's existing
   grammar (`trust_signals.parse_verdicts`, `validate_review_comment_format`) instead of porting the
   upstream ~1189-line parallel parser — pinned by a reuse-guard test in S3. The discipline even surfaced
   a real bug: Paloma caught that the *frozen contract* said "distinct requestees" where the charter
   grammar makes the reviewer the `Requestor:` (a 2-reviewer bar could never clear), and escalated it.
2. **Ship-dormant executed and proven, not just asserted.** The self-lock footgun (`reviewers_required=1`
   is live here, so a live merge gate would brick the team's own merges mid-wave) was identified before
   kickoff and mitigated with `policy.pr_review_gate_enabled=false`. Nia verified *structurally* that the
   flag check short-circuits before the oracle is ever consulted — dormancy is airtight, not incidental.
3. **Dependency sequencing worked.** S1+S3 ran in parallel (S3 is parsing-based, independent of the new
   oracle); S2 was held until S1 merged so it built against the real API, not a guess. Every load-bearing
   claim was independently reproduced by the reviewer (both mutation bars re-run), never taken on faith.

### Pain points
1. **The S2↔S3 config-sync conflict was predictable and not pre-empted.** Both stories were always going
   to register a hook into the same `hooks.pre_bash` list across 5 sync points + regenerate the golden
   manifest. It surfaced as a CONFLICTING PR and cost one resolution round-trip. Foreseeable at planning.
2. **The oracle's N-of-M path is unexercised in anger.** `reviewers_required=1` on this repo means the
   multi-reviewer approval logic is proven only by unit tests — the framework ships a state machine whose
   real multi-reviewer behavior has never run live.
3. **The frozen contract shipped with a real bug.** The pinned `ReviewState` contract was authored in
   prose without checking it against the actual verdict grammar/`trust_signals` — the requestee/Requestor
   error got through planning and was caught downstream by the implementer, later than it should've been.

### New proposals (owner-approved at Phase 6 Wave 6 kickoff — both folded into the charter this wave)
1. **Single integration-owner for shared registries.** When 2+ stories in a wave touch the same shared
   config list / registry (`pre_bash`, `_DEFAULTS`, golden manifest), designate one story as the
   integration owner for that list (or serialize those specific edits) so the predictable merge conflict
   is pre-empted rather than resolved after the fact. Low effort, removes a recurring round-trip.
   **Status: APPLIED via #204 (Phase 6 Wave 6, S3)** — written into the charter as
   `framework/assets/team/charter/issues.md` § Wave Planning → "Single Integration-Owner for Shared
   Registries" (canonical + dual-deployed to runtime, byte-identical via `charter_drift.py --check`).
   Dogfooded live this wave: S3 (Nia) was the sole charter integration-owner; S2 (Ibrahim) was barred
   from editing `charter/**` and routed wording through the lead's relay.
2. **Pin contracts against code, not just prose.** When a wave freezes an inter-story contract, validate
   it against the actual grammar/parsing layer at authoring time (a quick grammar check), not only in
   narrative. Would have caught the requestee/Requestor bug before it reached an implementer.
   **Status: APPLIED via #204 (Phase 6 Wave 6, S3)** — written into the charter as
   `framework/assets/team/charter/issues.md` § Wave Planning → "Pin Frozen Contracts Against Code, Not
   Prose" (canonical + dual-deployed to runtime).

### Carry-over (still unapplied, from Wave 9 retro — no early slot claimed this flagship wave)
- **Charter-manifest checksum cross-check** in `charter_drift.py plan()` (Nia's #190 tech-debt).
- **Normalize `ensure_gitignore_entries` matching** before compare for idempotency (Tariq's #191 tech-debt).
Both remain good early-slot fold-ins for the next hardening wave.
