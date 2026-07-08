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

---

## Wave 11 Retro (2026-07-07) — Phase 6 Wave 6: "Activate the review gate" → v0.9.1

**Shape:** 3 stories / 3 PRs, **0 changes-requested cycles**, 33% top concentration (3 distinct authors),
706 tests (+6), 0 CI-red, 0 Must-fix caught. **First wave run entirely under the 2-reviewer regime — 6
clean verdicts across 3 PRs.** Armed the PR-review gate on this repo (`reviewers_required=2` +
`pr_review_gate_enabled=true`); framework defaults stay dormant. Released v0.9.1 (patch). PRs
#206/#209/#210 → wave branch → rollup #212 → main. Gate now live on `main`.

### Going well
1. **The gate validated itself.** S1's PR #206 was the first PR ever to clear the 2-reviewer bar, and
   the two reviewers' verdicts *were* the live data proving the oracle reports `approved 2/2`. Plus a
   self-contained throwaway PR demonstrated the block→approve transition (0/2 blocked → 2/2 passed). We
   activated a mechanism and proved it on its own activation PR in the same wave.
2. **Dogfooded proposal #1 while codifying it.** S3 was sole charter integration-owner and S2 was barred
   from charter — so the exact `pre_bash`/charter conflict that cost a round-trip last wave simply could
   not occur. The "single integration-owner for shared registries" rule proved itself *before* it was
   written into the charter. This is the strongest possible evidence a process proposal is sound.
3. **Scope discipline held under temptation.** Three real findings surfaced mid-wave (#207 fail-open
   scope, #208 example.json default, #211 cr-cycles wording) and all three were tracked, not folded — and
   S2 *routed* the cr-cycles finding to the charter owner rather than grabbing it, honoring the very
   integration-owner rule being codified.

### Pain points
1. **The enabled gate still hasn't blocked a genuine accident.** The live proof was a *self-constructed*
   throwaway PR with synthetic (real-identity) verdicts. We've proven the mechanism fires; we haven't yet
   observed it catch a real not-approved merge attempt in the wild. The next organic under-reviewed PR is
   the real test.
2. **A codified instruction is now stale (#211).** `wave-end/SKILL.md`'s `--cr-cycles` counts *verdicts*,
   which double-counts at N≥2 vs the scorer's per-PR `rework_cycles`. The Manager had to compute the
   wrapup number correctly by hand this wave. A wrong-but-official instruction is a latent trap — this is
   exactly the kind of doc↔code drift a `--check` gate is meant to prevent.
3. **Review load doubled and concentrated.** 6 verdicts for 3 PRs; Tariq carried 3 of them. Sustainable
   at this size, but as waves grow, review-load concentration on QA is a scaling risk worth watching.

### New proposals (need owner approval before a future wave adopts them)
1. **A near-term hardening slot for the gate-activation debt.** #207 (make the gate fail-open on oracle
   *fetch* error, not just exceptions), #208 (example.json `reviewers_required`→1), and #211 (cr-cycles
   per-PR wording) are all correctness debt created by *this* activation. Fold them together next wave so
   the freshly-armed gate is robust before it governs many PRs. Owning #211 also converts Ibrahim's
   routed finding into a real contribution.
2. **Track review-load balance in the wrapup.** Record per-reviewer verdict counts alongside concentration
   so lopsided review load (one reviewer carrying most verdicts) is visible before it becomes a bottleneck.

### Carry-over (still unapplied — now 3 waves deferred; the deferred-debt list is growing)
- **Charter-manifest checksum cross-check** in `charter_drift.py plan()` (W9, Nia #190).
- **Normalize `ensure_gitignore_entries` matching** before compare (W9, Tariq #191).
A dedicated hardening wave folding these + the 3 new follow-ups (#207/#208/#211) is increasingly warranted.

---

## Wave 12 Retro (2026-07-07) — Phase 6 Wave 7: "Harden the armed gate" → v0.9.2

**Shape:** 3 stories / 3 PRs, **0 changes-requested cycles**, 33% top concentration (3 distinct authors),
717 tests (+11), 0 CI-red, 0 Must-fix caught. Hardened the gate armed in v0.9.1 and **cleared the entire
deferred-debt tail** (the 3 gate-activation follow-ups #207/#208/#211 + both W9 carry-overs). Released
v0.9.2 (patch). PRs #217/#218/#219 → wave branch → rollup #220 → main.

### Going well
1. **The deferred-debt list is EMPTY for the first time this phase.** Five items across three waves —
   #207/#208/#211 (gate-activation follow-ups) + the two W9 carry-overs (charter-manifest checksum
   cross-check; `ensure_gitignore_entries` normalize) — all landed in one focused wave. The "hardening
   slot" W11 proposed became W12, and it fully drained the backlog it was created for.
2. **The gate governed its own maintenance.** This was the first wave whose story merges ran *through*
   the live 2-reviewer gate: the oracle allowed each of #217/#218/#219 only after 2 distinct clean
   verdicts. We hardened the gate while the gate was gating us — and it behaved exactly as specified.
3. **Both W11 proposals were applied inside one wave, not just filed.** Proposal #1 (hardening slot) *was*
   this wave. Proposal #2 (review-load balance) was applied by design: 6 verdicts spread Nia 2 / Paloma 2
   / Tariq 1 / Ibrahim 1 — no reviewer carried more than 2, versus Tariq's 3-of-6 in W11. And the
   single-integration-owner rule was dogfooded a second time (Paloma sole manifest-owner) with zero
   conflict.
4. **Trust discipline predicted its own outcome.** W11 pre-registered both moves in writing: Nia's 5
   "decays on a clean-no-catch wave," Tariq's path back to 5 is "owning one of the tracked follow-ups."
   Both fired mechanically this wave — Nia authored nothing + caught nothing (5→4), Tariq authored the
   flagship #207 fix (4→5). A clean, non-arbitrary rotation the team could have predicted in advance.

### Pain points
1. **Story-difficulty is invisible to the scorer.** Tariq (5) and Ibrahim (4) both authored one clean PR
   with identical mechanical signals (delta 0, composite 1). The differentiation — S1 was the wave's
   deepest correctness fix, S2 its lightest config/doc touch — lives *only* in the retro narrative, not
   in `trust_signals`. The judgment is sound but unmechanized; a difficulty/impact weight would make the
   reserved-5 rotation reproducible instead of hand-argued.
2. **The rollup can no longer merge through its own gate.** With the gate permanently armed (unlike W6,
   where local main was still dormant at rollup time), rollup PR #220 carried no verdicts of its own and
   the oracle correctly refused `gh pr merge`. We used the documented direct-push escape hatch — correct,
   but it's an *undocumented-in-charter* operational step that a future orchestrator could get wrong.
3. **Manifest-owner was a no-op this wave.** Zero installed-path changes meant Paloma's integration-owner
   duty reduced to "confirm no regen needed." The role that caused the W5 conflict still hasn't been
   stress-tested under real golden-manifest churn.

### New proposals (need owner approval before a future wave adopts them)
1. **Codify the rollup-merge path under a permanently-armed gate** (in `pull-requests.md` + `wave-end`):
   the sanctioned way to land a rollup is a direct-push merge to `main` via the escape hatch (the stories
   already each carry 2 verdicts; re-reviewing the rollup is theater). Document it so it's a named step,
   not tribal knowledge — this is the first phase where every future rollup hits this.
2. **Mechanize review-load in the wrapup** (carry W11 proposal #2 from principle to implementation):
   `wave-end` records per-reviewer verdict counts next to concentration, so review-load balance is a
   tracked number rather than something the orchestrator balances by hand.
3. **(Stretch) Weight trust signal by story difficulty/impact.** Give the scorer a coarse per-PR
   difficulty tag so a flagship correctness fix and a one-line config change don't read identically. Would
   make reserved-5 rotations mechanical rather than narrative-argued (addresses pain point #1).

### Carry-over
- **NONE.** The deferred-debt list is empty for the first time this phase — both W9 carry-overs landed in
  S3 this wave. Future waves start from a clean debt slate.

---

## Wave 13 Retro (2026-07-07) — Phase 6 Wave 8: "Complete the installer"

**3 PRs · 1 changes-requested cycle · 33% concentration (3 distinct authors) · 746 tests · shipped v0.10.0
(minor — new `2real-team uninstall` command; PyPI + npm OIDC).** The first NON-flawless wave under the
2-reviewer regime, and the more valuable for it: the gate intercepted a real user-data-loss bug on the
flagship destructive command before it could reach main.

### What went well
1. **The gate paid for itself — a real defect interception.** On the flagship `uninstall`, Tariq (reviewer)
   caught that the amend-disposition teardown blind-unlinked a pre-existing USER file colliding with a
   framework manifest path (unrecoverable data loss). This is the first wave with a genuine blocking catch
   — the prior three were flawless, so the 2-reviewer cost had bought nothing yet. This wave it stopped a
   destructive bug one step before main. That is the entire justification for the regime, realized.
2. **The reserved-5 self-justified via same-PR contrast.** On ONE PR (#227), Tariq caught the data-loss and
   Nia clean-approved past it. No narrative needed to defend 5=Tariq / 4=Nia — the split is visible in the
   PR history. Last wave the reserved-5 was re-earned on authorship (hypothetical catch); this wave it was
   validated on a real catch.
3. **File-disjoint story design held perfectly.** Three stories, zero shared files (install+package /
   ontology-freshness / harness+CI). Parallel authoring AND parallel review with no merge contention; the
   only integration step (folding wave-8 into the flagship branch) was a clean no-conflict ort merge that
   changed only the other two stories' files.
4. **The fix cycle ran cleanly through the live gate.** Request → fix (byte-provenance guard) → both
   reviewers re-verified → amend-in-place → oracle `approved` → merge. The gate governed a real
   changes-requested round, not just clean first-passes.

### Pain points / findings
1. **HEADLINE: amend-in-place ERASES the review-cycle trust signals.** The gate oracle requires a reviewer
   to resolve a `Request` by editing it in place to `Replied` (any *current* comment parsing as a Must-fix
   blocks the merge). But `trust_signals score` reads the same current comment state — so once Tariq
   amended his blocking S1 comment, the scorer saw **must_fix_caught=0 (Tariq)** and **must_fix_received=0
   (Paloma)**. The wave's single most valuable review contribution — a real data-loss catch — scored
   mechanically ZERO, and the author's rework was invisible. The gate and the scorer both read "current
   state" but want opposite things from a resolved Request. The distribution had to override the raw delta
   by hand (documented in trust_matrix W13).
2. **A PR merged with a red CI check.** S2 #226's head carried a `node (20)` failure (a flake — S2 is
   Python-only and cannot affect the Node package; main is green). It merged anyway because the merge step
   gates on the review oracle, NOT on CI-green. A flake this time; a real red next time would slip the same
   way. (The scorer *did* catch it as ci_red_merges=1 — but attributed it to the Python author.)
3. **Reviewers instinctively post a NEW comment instead of amending in place.** Tariq's first re-review was
   a fresh `Replied` comment; the oracle stayed `changes_requested` (the old `Request` still stood) until
   he amended the original in place. The amend-in-place convention is load-bearing for the oracle but
   neither obvious nor enforced.

### New proposals (need owner approval before a future wave adopts them)
1. **Credit resolved catches in `trust_signals` (fixes finding #1 — top priority).** Score the review cycle
   from something durable, not the mutable current state: parse the comment EDIT history (GitHub exposes
   it) so an amended-away `Request` still counts `must_fix_caught`/`must_fix_received`, OR require the
   resolving reviewer to leave a preserved "resolved: was-Must-fix" marker the scorer counts. Without this,
   the scorer systematically under-credits exactly the reviews that did the most — the ones that caught a
   real bug and got it fixed.
2. **Add a CI-green precondition to the merge step (fixes finding #2).** The orchestrator's merge should
   require the PR's required checks green (or explicitly surface a red at merge time), not trust
   suite-local green. Plus: investigate `node (20)` flakiness so it stops manufacturing false ci_red
   signals. (Adjacent: this also stops the scorer mis-attributing infra flakes to authors.)
3. **Make amend-in-place explicit in the reviewer flow (fixes finding #3).** A named step in
   `pull-requests.md` / a wave-review helper: "to clear your Request, EDIT it in place to Replied — do not
   post a new comment." Consider a tiny helper that PATCHes the reviewer's own verdict comment.
4. **(Carried from W11/W12, still unimplemented) Mechanize review-load + rollup escape-hatch in wrapup.**
   Per-reviewer verdict counts next to concentration; and codify the rollup direct-push escape hatch as a
   named `wave-end` step (used again cleanly this wave).

### Carry-over
- **Deliberately deferred (the natural S1 follow-on, kept out to preserve file-disjointness):** #162
  (amend-path leaves stale config module lists) and #155 (5 provisioner-hardening items) — both live in
  `bootstrap.py`/provisioner code that would have collided with the flagship. Prime candidates for a
  focused installer-hardening follow-up.
- **Tech-debt surfaced in S3/S1 reviews (non-blocking):** `_derivable_asset_bytes` re-implements the
  charter `{{key}}` substitution inline rather than sharing `install_charter`'s render path (guarded by the
  round-trip test); harness PYTHONPATH-shadow assert; width-sensitive soft-degrade notice marker.

---

## Wave 14 Retro (2026-07-07) — Phase 6 Wave 9: "Fix the gate & scorer"

**3 PRs · 0 changes-requested cycles · 33% concentration (3 distinct authors) · ~797 tests · shipped
v0.10.1 (patch, PyPI + npm OIDC).** Applied the W13 retro proposals — the wave hardened the trust/gate
machinery it ran through. Clean deliverables, but TWO orchestration-level execution incidents made this the
messiest-run wave of the phase. Both are the orchestrator's, not the engineers'.

### What went well
1. **The machinery now reads reality.** S1 credits resolved catches from comment edit-history (closing the
   W13 erasure — verified by re-scoring live #227) + adds difficulty weighting; S2 closes the real
   pending-checks merge-slip; S3 documents amend-in-place + the rollup escape-hatch and mechanizes
   review-load. The three W13 proposals landed in one wave.
2. **A mis-scoped story was corrected by investigation, not obedience.** The manager pointed S2 at the wrong
   file (unaware `validate_pr_ci_status.py` already existed). Tariq investigated, found the real root cause
   (no branch protection → the existing gate's pending warn-allow is the actual hole), and refused to fork a
   duplicate gate. "Reconcile, don't duplicate" caught a manager error before code was written.
3. **Engineers recovered from a live worktree collision with ZERO work lost.** Ibrahim non-destructively
   moved his commit off the wrong branch by explicit SHA and reset the other branch to base; Nia self-caught
   and fully recovered a commit that briefly landed on local `main` (origin untouched); Tariq held correctly
   when asked. Adverse-condition judgment was excellent across the board.

### Incidents / pain points
1. **Worktree-isolation failure from reused agent names (orchestration).** Re-spawning W9 authors with the
   same names (Nia/Tariq/Ibrahim) while the W8 namesakes were still shutting down routed the new agents into
   the ORCHESTRATOR's shared worktree instead of isolated ones → branches tangled (S3's commit briefly on
   S2's branch, etc.). No data lost, but hours of recovery. ROOT CAUSE: name reuse during shutdown overlap +
   not using the explicit `isolation: worktree` spawn parameter. Once re-spawned with distinct names +
   explicit isolation, it could not recur.
2. **Orchestrator merged S1 with a red CI check — the exact mistake S2 fixes.** The merge command and the
   CI-result read landed in the same step, so the merge fired before the red `framework (3.12)` was seen. It
   was an infra flake (zero failed steps; re-run green), but the process gap is real. The irony: this is
   precisely the W13 slip S2 just fixed — but S2's hook wasn't on `main` yet at merge time, and the
   orchestrator's manual merge discipline is separate from the hook.
3. **The difficulty weight doesn't break a tie of equals.** All three authors scored difficulty tier 3, so
   the new weight didn't mechanize the Tariq-vs-Nia reserved-5 call — judgment still decided, and Nia
   (flagship author) is 5-ready but stalled behind the incumbent 5. The 3-bucket coarseness is intentional
   but leaves near-equal substantial PRs to narrative.

### New proposals (need owner approval before a future wave adopts them)
1. **Codify safe re-spawning (fixes incident #1).** When spawning/re-spawning wave agents: ALWAYS use the
   explicit `isolation: worktree` parameter and names distinct from any still-terminating agent. Add it as a
   wave-kickoff checklist line so orchestration can't repeat the collision.
2. **Reinstall v0.10.1's CI-green hook onto THIS repo so the next wave is protected by the fix this wave
   shipped (fixes incident #2 mechanically).** The `validate_pr_ci_status.py` gate is wired in place, so its
   new pending-block logic is live on `main` now — but confirm it (check `settings.json` wiring) and, going
   forward, the orchestrator must gate `gh pr merge` on CONFIRMED-green `gh pr checks` conclusions (and
   re-run a suspected flake rather than merge through it), until/unless the hook fully covers the manual
   path. (Aligns with the standing "reinstall on this repo" rule, #116.)
3. **Reserved-5 vs. difficulty ties.** Consider a finer difficulty signal (or additive review-load) so two
   near-equal flagship authors don't both stall behind an incumbent 5 — or make the reserved-5 explicitly
   rotational on a difficulty tie. Nia has now authored flagship-caliber PRs two of the last three waves
   without taking the 5.

### Carry-over
- **Rulesets-vs-classic branch-protection probe (Nia's S2 tech-debt):** the CI-gate uses the *classic*
  `branches/{base}/protection` endpoint, which 404s for repos enforcing checks via the newer **rulesets**
  feature → those read as unenforced and get a safe-side OVER-block (never a slip). A rulesets probe is the
  completeness follow-up.
- **#234** — node RNG seed + name-dedupe root fix (then remove the S2 `vitest --retry` quarantine).
- Minor nit: unused `pr_key` loop var in `review_load.py` (Tariq's S3 review).

## Wave 15 Retro (2026-07-08) — Phase 6 Wave 10: "Harden the installer"

**Shipped v0.10.2 (patch).** 2 file-disjoint stories, 2 PRs, **0 changes-requested cycles**, 50%
concentration (2 authors), 809 tests. All 4 reviewer verdicts clean first-pass. Meta #237; stories
#238 (fix #162) + #239 (fix #155, 4/5 items). The deferred W8 installer-hardening follow-on, and the
"installer-hardening second" half of the approved W9→W10 two-wave plan.

### What went well
1. **Both W14 incidents were designed out.** Agents spawned with distinct names + explicit
   `isolation: worktree` → **no worktree collision**. Both PRs confirmed 12/12 CI-green via
   `statusCheckRollup` **before** the gated merge → **no red-merge**. The W14 proposals worked; the
   CI-green hook is live on main as a backstop but the orchestrator's manual green-check held on its own.
2. **Reviews were genuinely adversarial, not rubber-stamps.** All three reviewers ran mutation probes:
   Nia + Tariq independently confirmed a union-instead-of-reconcile fails the S1 oracle; Paloma + Tariq
   confirmed removing S2's `finally` block or reverting merge→replace fails the tests. This is the review
   rigor the phase has been building toward — and it held on a clean wave (nothing to catch, but the
   probes proved the tests are load-bearing rather than passing trivially).
3. **File-disjoint scoping held clean** (`framework/install/bootstrap.py` vs
   `framework/harness/real_provision.py`) — zero cross-story churn, both PRs mergeable independently.
4. **Engineers self-corrected without escalation:** Ibrahim renamed a mis-paired test to satisfy the
   pairing gate (didn't bypass it) and switched to uniquely-named temp files on collision; Paloma caught
   and recovered her own worktree clobber via `git status` before it touched the PR.

### Incidents (both contained, non-charged, minor)
1. **Errant bootstrap in Paloma's isolated worktree.** A compound Bash command interacted with the
   identity hook: the hook blocked the line *before* its `mkdir` ran, so a later `cd` into the
   never-created dir silently failed and subsequent commands executed in the worktree root — an ad-hoc
   `bootstrap` then clobbered `.claude/framework.config.json` and dropped install artifacts. Detected
   immediately (`git status`), restored (`git checkout`), stray artifacts removed; the final PR diff was
   verified to be exactly the 2 intended files. **Contained to the throwaway worktree; never reached the
   PR.** Root pattern: a hook-blocked line in a `&&`/`;` chain can leave a later `cd` pointing at the
   wrong dir.
2. **Concurrent-agent temp-file collision.** Two parallel author agents both wrote `commitmsg.txt`/
   `prbody.md` into the shared job tmp dir and clobbered each other mid-run. Ibrahim switched to
   `ibrahim_*`-prefixed names. No lost work. (Reviewers were subsequently instructed to prefix temp files
   per-agent; it worked.)

### New proposals (need owner approval before a future wave adopts them)
1. **Per-agent temp-file namespacing as a spawn-prompt standard (fixes incident #2).** Every spawned
   agent must write scratch/commit-message/PR-body files under a name prefixed with its own identity
   (e.g. `paloma_prbody.md`), never a bare shared name, since the job tmp dir is shared across concurrent
   agents. Add it to the author/reviewer prompt boilerplate.
2. **Guard e2e `cd` on `mkdir` success (fixes incident #1).** When an agent runs ad-hoc end-to-end
   checks, either run them in an explicit pre-created scratch dir or chain `mkdir -p X && cd X && …` so a
   hook-blocked or failed `mkdir` cannot silently redirect later commands into the worktree root. Consider
   a short "e2e hygiene" note in the engineer charter.
3. **Resolve the reserved-5 rotation (now the sharpest standing item).** Nia has delivered
   flagship-or-flagship-review caliber work in 3 of the last 4 waves (W12 flagship, W14 flagship author,
   W15 TL-grade review) without ever taking the reserved-5, purely because Tariq (the incumbent 5) hasn't
   decayed. The W14 "finer difficulty signal / rotational-on-tie" proposal is still unadopted; W15 makes
   it pressing — either make the reserved-5 explicitly rotational when a 4 posts N consecutive
   flagship-caliber waves, or split author-vs-reviewer excellence into distinct signals so a review-only
   wave isn't a dead end for a 5-ready engineer.

### Carry-over (open, owner picks into a future wave)
- **New this wave:** #242 (doc note: amend reconciles framework-owned hook lists to canonical) · #243
  (friendlier error on source-less new-bucket `--real-config` partial patch — pre-existing).
- **Still open:** #101 item 4 (bare B10 zero-children guard) · #234 (node RNG seed + name-dedupe, then
  drop the `vitest --retry` quarantine) · the rulesets-vs-classic branch-protection probe · #110
  (distribute as a Claude Code skill) · more #102 P2.

## Retrospective: Wave 16 (Phase 6 Wave 11) — 2026-07-08 — "Harden + Process"

### Wave Metrics
3 PRs merged (#248 S1, #249 S2, #247 S3), all file-disjoint. Issues closed: #243 #244 #242 #234 #245.
6/6 reviewer verdicts clean first-pass (2 per PR, author-exclusive). CI 12/12 green on the rollup; both
publish workflows (npm + PyPI, OIDC) succeeded → **v0.10.3**. Tech-debt filed: #251 (real_require_children
CLI surface), #252 (usedNamesFromRoster warn on unparseable card). **Counter drift: none** — claimed
pr=3/cr=0/conc=33 all matched recomputation exactly (3 PRs, one per author, zero ChangesRequested).

### Top-Implementer Concentration
1 / 3 = **33%** — evenly split across Paloma, Ibrahim, Nia (each authored one story). Healthy; well below
the 60% force-call threshold.

### Per-Engineer Assessments
- **Tariq Morales** (5→5): QA on all 3, real revert/determinism/parity verification, caught the doc
  five-vs-six hook-key discrepancy; `must_fix_caught=0` (clean wave, nothing to catch). delta 0.
- **Nia Rossi** (4→4): authored S3 — the author wave that answers the W15 review-only concern; clean
  difficulty-2 docs work is not a bump. delta 0.
- **Ibrahim El-Amin** (4→4): authored S2 (difficulty 3), root-caused the node flake + proved determinism
  before dropping the quarantine; cross-reviewed S1. delta 0.
- **Paloma Gupta** (4→4): authored S1 (multi-issue, well-judged default-off guard); cross-reviewed S2 with
  5× determinism runs. delta 0.

### Top 3 Going Well
1. **The prior incident classes are now designed-out AND codified.** No name collision, no red-merge — and
   S3 promoted the very W14/W15 fixes for those incidents into the charter, so they are enforced doctrine now.
2. **Even load distribution** (33%, three distinct authors) with fully file-disjoint stories → zero merge
   conflict, zero cross-story review contention.
3. **Clean first-pass across the board** — 6/6 verdicts clean with genuine mutation/determinism probes, 0 CR
   cycles, 0 red-merges.

### Top 3 Pain Points
1. **Orchestrator rollup slip:** the first rollup merged a STALE LOCAL wave branch (feature PRs had merged
   into `origin/…`; local ref never fast-forwarded), landing a code-less merge on main. Caught by a
   post-merge content probe and corrected before the bump/release — but it should not have happened.
2. **Reserved-5 rotation still unresolved.** Giving Nia an author wave removed the "review-only dead end"
   framing, but the mechanical "one clean small PR ≠ bump" rule still holds her at 4 while Tariq's 5 rides
   on a catch-less clean wave. The tension is now purely mechanical, and sharper for it.
3. **Clean waves starve reviewer signal.** With no must-fixes anywhere, QA rigor (Tariq's real probes)
   earned zero countable credit — `must_fix_caught` only rewards catching defects that exist.

### Proposed Process Changes (approval-gated — NOT applied)
1. **Rollup hygiene step:** add an explicit "fast-forward the local wave ref (or merge `origin/<wave>`) and
   verify feature-code presence on the merge parent" step to the wave-end/escape-hatch rollup runbook, so a
   stale-local-branch rollup is caught before it reaches main. — Rationale: pain point #1, this wave.
2. **Reserved-5 rotation (carry-over, now owner-scoped):** the owner deferred the scoring change this wave;
   W16 confirms the tension is mechanical (clean-small work can't bump). Options remain: rotational-on-streak,
   or split author/reviewer-excellence signals, or a "verified-clean-review" positive signal so QA rigor on a
   clean wave isn't zero-credit. — Rationale: pain points #2 and #3.

---

## Retrospective: Wave 17 (Phase 6 Wave 12) — 2026-07-08 — "Symmetric trust scoring + rollup hygiene" → v0.10.4

### Wave Metrics
- **2 PRs merged** (#257 S1, #256 S2), **0 changes-requested cycles**, **50% top concentration** (2 distinct
  authors — Paloma, Ibrahim). All **4 reviewer verdicts clean first-pass**. Shipped **v0.10.4** (patch) to
  main + PyPI + npm via OIDC. Tag/Release `deployments-phase6-wave-12`.
- **Counter drift (Step 2):** claimed `pr_count=2 / cr=0 / concentration=50` — recomputed from the merged-PR
  set: 2 PRs, 0 ChangesRequested verdicts (all `Replied`), max 1/2 by one author = 50%. **All three match;
  no corrections.**
- **Issues:** #254/#255 closed; tech-debt #258 (per-(reviewer,PR) `verified_reviews` dedup) + #259 (tighten
  bare-`determinism`/`ci green` in `_VERIFIED_CHECK_RE`) filed against the new signal; meta #253 open.
- **Tests:** trust suite +9 load-bearing (revert→red) tests for the symmetric signals.

### Top-Implementer Concentration
1 PR each by Paloma (#257) and Ibrahim (#256) = **50%** — two distinct authors on a 2-PR wave; the metric is
at its structural floor for two stories and reads as healthy distribution, not fragility.

### Per-Engineer Assessments (mechanical — `trust_signals score 17`)
- **Paloma Gupta** — author S1 #257 (difficulty 3): `prs_merged=1, must_fix_received=0, verified_reviews=0,
  rework=0`. **delta 0** (single clean PR is not a bump). Shipped the symmetric-scoring feature end-to-end;
  self-recovered a `git checkout` clobber of uncommitted edits with zero PR impact.
- **Ibrahim El-Amin** — author S2 #256 (difficulty 2): `prs_merged=1, must_fix_received=0, verified_reviews=0,
  rework=0`. **delta 0**. Clean dual-tree charter authorship; his own #256 review Verified blocks were empty
  (0 credit).
- **Tariq Morales** — reviewer: `verified_reviews=1, must_fix_caught=0`. **delta 0**. Substantive #257
  Verified block (surfaced tech-debt #258/#259); #256 Verified block empty (correctly 0 credit). Reserved-5
  held on incumbency (no decay — has a signal).
- **Nia Rossi** — reviewer: `verified_reviews=1, prs_merged=0`. **delta 0**. First wave the new signal could
  register for a review-only engineer, and it did — but `1 < 2` bonus threshold.
- **Forced negative-signal pass (Step 4):** all four lines are `metrics clean: {numbers}` — validated clean,
  no bare "None". **No decay** (all four have a signal this wave). **No retirement triggers.**

### Top 3 Going Well
1. **The shipped signal validated itself on its own wave, both directions.** `verified_reviews` credited the
   two substantive `Verified:` blocks (#257: Nia, Tariq) and the anti-gaming gate *rejected* the two empty
   ones (#256: Tariq, Paloma). Credit-and-reject dogfood on the introduction wave.
2. **The S2 rollup-hygiene step was dogfooded during this wave's own rollup** — explicit
   `git merge --no-ff origin/deployments/phase6/wave-12` + content-probe before bump. No repeat of the W11
   code-less-merge slip.
3. **Clean execution end-to-end:** 4/4 first-pass clean verdicts, 0 CR cycles, both registries published, all
   worktrees pruned.

### Top 3 Pain Points
1. **Reserved-5 rotation still unresolved — now threshold-bound.** The symmetric signal shipped partly to give
   QA rigor a non-zero path, but on a 2-PR wave reviewers split across PRs and each lands at
   `verified_reviews=1 < 2`. Correct-by-design for a small wave, but the rotation waits on a larger/more-
   concentrated wave to clear the threshold.
2. **Empty `Verified:` blocks left credit on the table.** Ibrahim (author) and both reviewers on #256 wrote
   `Verified:` with no substantive checks — zero-credit under the new gate. Reviewers should populate the
   block to earn the signal now that it exists.
3. **Signal edge-cases already known at ship (#258/#259).** Per-(reviewer,PR) dedup absent and a bare-
   `determinism` regex alternation are filed but unaddressed — small hardening owed to the new signal.

### Proposed Process Changes (approval-gated — NOT applied)
1. **Populate `Verified:` blocks by default.** Add a charter/PR-doc nudge that a clean review verdict SHOULD
   carry a substantive `Verified:` block (concrete checks: revert→red / determinism Nx / byte-parity), since
   an empty block now earns 0 `verified_reviews`. — Rationale: pain point #2.
2. **Reserved-5 rotation (carry-over):** the symmetric signal is now live; the remaining lever is whether a
   review-only engineer can clear `≥2` verified reviews on a normal wave, or whether the threshold/roster
   assignment should concentrate substantive reviews. Owner-scoped; no change applied. — Rationale: pain #1.
3. **Land #258/#259** (per-PR dedup + tighter `_VERIFIED_CHECK_RE`) in a near-term hardening slice. — Rationale:
   pain point #3.

---

## Retrospective: Wave 18 (Phase 6 Wave 13) — 2026-07-08 — "Harden the machinery" → v0.10.5

### Wave Metrics
- **3 PRs merged** (#266 S1, #267 S2, #268 S3), **0 changes-requested cycles**, **33% top concentration**
  (3 distinct authors — Paloma, Nia, Ibrahim). All **6 reviewer verdicts clean first-pass**. Shipped **v0.10.5**
  (patch) to main + PyPI + npm via OIDC. Tag/Release `deployments-phase6-wave-13`.
- **Counter drift (Step 2):** claimed `3 / 0 / 33` — recompute: 3 PRs, 0 ChangesRequested (all `Replied`),
  max 1/3 by one author = 33%. **All match; no corrections.**
- **Issues:** #258/#259/#251/#252 closed (auto-closed when the rollup landed the `Closes #` commits on main).
  New tech-debt: **#269** (guard non-dict `parameters` in rulesets probe), **#270** (`_VERIFIED_CHECK_RE`
  misses `revert->red` ASCII arrow — distorted this wave's scoring). Meta #260 open.
- **Tests:** +9 trust (S1) + rulesets/combiner suite (S2) + provisioner/node (S3); full suites green on all PRs.

### Top-Implementer Concentration
1 PR each by Paloma/Nia/Ibrahim = **33%** — three distinct authors, healthy distribution.

### Per-Engineer Assessments (mechanical — `trust_signals score 18`)
- **Tariq Morales** — reviewer: `verified_reviews=2` (substantive `→` blocks on #266 + #267). **delta +1**
  (clean-wave bonus at ≥2, clamped at 5). First reserved-5 EARNED by signal, not incumbency.
- **Nia Rossi** — author S2 (#267, diff 3) + 2 reviews: `verified_reviews=1`, `prs_merged=1`. **delta 0** —
  but glyph-contingent (see headline finding): her #268 block used `->` and went uncredited (#270).
- **Paloma Gupta** — author S1 (#266, diff 2) + 1 review: `verified_reviews=0` (her #268 block used `->`,
  #270), `prs_merged=1`. **delta 0.**
- **Ibrahim El-Amin** — author S3 (#268, diff 2) + 1 review (#267, correctly credited `→`):
  `verified_reviews=1`, `prs_merged=1`. **delta 0.**
- **Forced negative-signal pass (Step 4):** all four `metrics clean: {numbers}` (validated, no bare "None").
  **No decay** (all have a signal). **No retirement triggers.**

### Top 3 Going Well
1. **The reserved-5 was earned by the symmetric signal for the first time** — Tariq's `verified_reviews=2`
   across two substantive reviews cleared the ≥2 bonus. The W12 mechanism works as designed at scale.
2. **The wave dogfooded every one of its own shipped changes:** #258 dedup + #259 regex ran live in
   `score 18`; the S2 rollup-hygiene step content-probed main before bump (PASS).
3. **Clean execution:** 3/3 file-disjoint stories, 6/6 first-pass clean verdicts with independent revert→red
   reproductions, 0 CR cycles, both registries published.

### Top 3 Pain Points
1. **A parser false-negative decided the reserved-5 rotation (#270).** `_VERIFIED_CHECK_RE` matches
   `revert→red` but not `revert->red` (ASCII arrow). Both #268 reviewers used `->`, so their genuinely
   substantive reviews scored zero — Nia (a difficulty-3 author with 2 real reviews) held at 4 where the fix
   would likely have given her the 5. Scoring fairness now hinges on a glyph.
2. **`verified_reviews` credit is fragile to phrasing.** S3-type stories offer no `determinism`/`byte-parity`
   fallback token, so the whole block rides one arrow glyph. The credited-token set may be too narrow (no
   `N passed` / `ruff clean`).
3. **Two of three reviewers lost earned credit to #270**, muddying the wave's headline signal-result — the
   "Tariq earned it" story is real but the "others didn't" story is mostly a parser artifact.

### Proposed Process Changes (approval-gated — NOT applied)
1. **Land #270 early next wave** — broaden the revert-red alternation to accept `->`, add a load-bearing
   `revert->red` test. Highest-value fairness fix. — Rationale: pain #1/#2.
2. **Owner call on W18's reserved-5** — the mechanical result stands (Tariq 5 earned, Nia 4), but the rotation
   was glyph-contingent; the owner may choose to treat it as a tie pending #270, or accept it and let the
   fixed parser govern from W19. — Rationale: pain #1.
3. **Broaden the `Verified:` credited-token set** (consider `N passed`, `ruff clean`) so substantive suite
   evidence counts, not only the named-probe vocabulary. — Rationale: pain #2. (Separate judgment from the
   narrow #270 arrow fix.)

---

## Retrospective: Wave 20 (Phase 6 Wave 15 / global 20) — 2026-07-08 — "tech-debt cleanup + restore-story closeout + calibration watch"

### Wave Metrics
- **2 PRs merged / 1 changes-requested cycle / 50% concentration.** v0.11.0 shipped to main + PyPI + npm.
- S1 #279/PR #283 (Ibrahim → Paloma + Tariq): git-native `2real-team install-branch` staging.
- S2 #280/PR #282 (Nia → Ibrahim + Tariq): node CLI teardown/restore parity (`uninstall` + `restore`).
- Issues closed: #279, #280, #281 (meta). Tech-debt filed: #284 (docs/refactor load-bearing exception).
- **Counter corrections:** `changes_requested_cycles` claimed=1, current-state recompute=0 — claimed stands
  (Tariq's #283 Request was cleared by editing the verdict in place to Replied per amendment convention;
  the recompute under-counts edited-in-place verdicts). Documented in `wave_20_counter_corrections`.

### Top-Implementer Concentration
1 PR each by Nia (#282) and Ibrahim (#283) → max 1/2 = **50%** — even split, no fragility flag.

### Per-Engineer Assessments (mechanical; deltas PARKED — see below)
- **Ibrahim El-Amin** — author #283, difficulty=3, must_fix_received=1, rework=1, verified_reviews=1. delta 0.
  Negative-signal: 1 must-fix received + 1 rework — install-branch CLI shipped with `install_config=None`
  (`repo.expect=fresh`), refusing every realistic repo; fixed on re-review with an end-to-end success test.
- **Nia Rossi** — author #282, clean_first_pass=1, difficulty=3, prs_merged=1. delta +1.
  Negative-signal: metrics clean (prs_merged=1, no negatives); no reviewer-side verified block earned.
- **Tariq Morales** — reviewer, **must_fix_caught=1**, verified_reviews=1, difficulty=0. delta 0.
  Negative-signal: metrics clean; caught the wave's only defect but below the +1 reviewer bump threshold (≥2).
- **Paloma Gupta** — reviewer, **missed_catches=1**, verified_reviews=1, difficulty=0. delta −1.
  Negative-signal: 1 missed catch — clean Replied verdict on #283 that missed the `install_config=None`
  defect Tariq subsequently caught.

### ⚠️ Trust deltas PARKED (calibration watch #275 — data-point #2)
Consistent with the W19 park, **W20 trust deltas are NOT applied.** Standing matrix HELD at **Tariq 5,
Nia/Paloma/Ibrahim 4**. `distribution_health([5,5,3,4]) = spread 2, variance 0.69, degenerate=False` — a
HEALTHY spread, NOT the W19 degeneracy (which now reads as an all-clean-wave artifact). But the mechanical
result would rotate the reserved-5 from **Tariq (caught the wave's only defect) → Nia (clean author)**,
because the reserved-5 composite is dominated by author-only `difficulty_points`. This reproduces W19
finding #2 (pure-reviewer structural demotion). Full analysis + recommendation recorded as data-point #2 on
#275. **Owner decision pending** — see Proposed Changes.

### Top 3 Going Well
1. **The symmetric ledger differentiated correctly on a real event.** A single must-fix flowed to three
   scorecards as designed: Tariq +caught, Ibrahim +received/rework, Paloma +missed. The mechanism works.
2. **QA caught a genuine functional defect before merge** (#283 refused every realistic repo) — the
   2-reviewer gate did exactly its job; the fix shipped with a real end-to-end success test.
3. **Restore-story family complete across both language surfaces** (#278 Python restore → #279 install-branch
   → #280 node parity), cleanly closed out in one focused wave.

### Top 3 Pain Points
1. **Reserved-5 composite structurally demotes reviewers (#275 data-point #2).** The engineer who caught the
   wave's only defect drops 5→4 while a clean author takes the 5, purely because `difficulty_points` is
   author-only. Perverse incentive for high-value review work.
2. **One reviewer missed a defect a peer caught (Paloma, #283).** Two reviewers, non-overlapping coverage —
   the gate held because Tariq caught it, but a single-reviewer wave would have shipped the defect.
3. **A docstring-only edit tripped the load-bearing-test gate** (#284) — the gate can't yet distinguish
   pure-doc changes from behavior, forcing a revert of a legitimate doc cross-ref.

### Proposed Process Changes (approval-gated — NOT applied)
1. **Act on #275 with a targeted composite fix, not a range widen.** Credit `must_fix_caught` +
   `verified_reviews` in the reserved-5 composite (or cap `difficulty_points`' share) so a high-value reviewer
   can hold the 5. The scale-broadening trigger did NOT fire; the composite trigger fired twice. — Rationale:
   pain #1.
2. **Seed a narrow docs/refactor `load_bearing_test_exceptions` class (#284)** so pure-doc changes don't trip
   the behavior gate, kept tight enough not to become a test-skipping loophole. — Rationale: pain #3.
3. **Note reviewer coverage overlap in review assignment** — when two reviewers are assigned, nudge them to
   target different surfaces (already done ad hoc this wave), to reduce simultaneous misses. — Rationale: pain #2.

## Retrospective: Wave 21 (Phase 6 Wave 16) — 2026-07-08 — "Reward the reviewer + clear the gate debt" → v0.11.1

### Wave Metrics
2 PRs merged (#286, #287), 1 changes-requested cycle (#287), CI 11/11 green on both. Counters recorded fresh
at wrapup (pr-count=2, cr-cycles=1, concentration=50%) — no drift. Tech-debt filed: #288 (author-exclusive
scorer parity) + an npm-CI durability note. Issues closed: #275 (calibration resolved), #284 (done), #285
(wave meta). Shipped v0.11.1 to main + PyPI + npm.

### Top-Implementer Concentration & Review-Load
Authoring: 1/2 = 50% (Paloma #286, Ibrahim #287 — 2 distinct authors). Below the 60% force-call line.
Review-load (#231): Tariq 2/4 verdicts (both PRs), Nia 1, Paloma 1 — Tariq carried half the slate, expected
for a 2-story wave he was on both of; not lopsided at this volume.

### Per-Engineer Assessments (mechanical, cleaned signals)
- **Paloma Gupta** — prs_merged=1, difficulty=2, clean_first_pass=1, must_fix_caught=1 (caught the #287
  bypass as reviewer). Composite 5. delta +1 → **4→5, reserved-5 earned/rotated in**.
- **Tariq Morales** — must_fix_caught=1 (the #287 bypass), verified_reviews=1 (#286). Composite 4. delta 0 →
  **5→4** (rotates off the single-seat reserved-5; NOT for cause — under the old composite he'd have been ~0).
- **Nia Rossi** — verified_reviews=1 (#286), review-only. Composite 2. delta 0 → **4→4**.
- **Ibrahim El-Amin** — prs_merged=1, difficulty=3, must_fix_received=2 (#287 bypass, raised by both
  reviewers), rework_cycles=1. Composite 1. delta −1 → **4→3**.

Negative-signal pass: clean (validated, no bare "None").

### Calibration Close-Out (#275) — UN-PARKED
First wave scored under the new composite (`REVIEW_VALUE_WEIGHT=2`, `DIFFICULTY_COMPOSITE_CAP=2`) and first
with deltas APPLIED since W18 (W19/W20 were parked pending the owner decision). Decision executed: fix the
composite, keep the 1–5 scale, un-park from W21. Result validates the fix — Tariq's pure-reviewer composite
rose from ~0 (old) to 4 (new); the reserved-5 rotated to Paloma only because she out-contributed on BOTH
axes (review catch + hardest clean authoring), which is the intended behavior, not the W20 "clean author
displaces defect-catcher" failure mode.

### Top 3 Going Well
1. **The adversarial 2-reviewer gate caught a real gate-weakening bug** — both reviewers independently
   reproduced the `_patch_is_docs_only` self-close+trailing-code bypass with executing PoCs before it reached
   the wave branch; fix landed symmetric across both classifier branches with revert→red tests.
2. **#275 calibration closed with a targeted fix, dogfooded on its own retro** — the composite that scored
   this wave is the composite this wave shipped.
3. **Release recovered from a CI-drift publish failure without version churn** — npm@12 dropping node-20
   support was diagnosed, hotfixed (pin `npm@^11.5.1` + `workflow_dispatch`), and re-published; both
   registries at 0.11.1.

### Top 3 Pain Points
1. **Author reply used reviewer verdict grammar → corrupted scoring** (author counted as a third reviewer,
   spurious `missed_catches`/`verified_reviews`). The scorer/review-load are not author-exclusive while the
   merge gate is — a real inconsistency. Worked around by amend; #288 filed.
2. **npm publish CI was unpinned** (`npm install -g npm@latest`) — npm@12 requiring node ≥22 broke the
   release publish on the node-20 runner. Fixed by pinning, but node 20 will EOL.
3. **`gh api` `-f` vs `-F` @file trap** hit twice (Tariq, Ibrahim) — `-f/--raw-field` sends the literal
   `@path` string; only `-F/--field` expands `@file`. The orchestrator's own guidance propagated the wrong flag.

### Proposed Process Changes
1. **#288 (Phase 7):** one shared author-exclusivity helper across `validate_pr_review` + `trust_signals` +
   `review_load`; charter note that author must-fix replies are plain comments, never `Requestor:` grammar;
   revert→red tests. — Rationale: pain #1.
2. **Memory correction:** `gh api -X PATCH` bodies must use `-F body=@file`, never `-f`. — Rationale: pain #3.
3. **npm-CI durability:** consider bumping the publish runner to node 22 next Phase to keep `npm@latest`
   viable. — Rationale: pain #2.
