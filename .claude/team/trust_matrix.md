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

## Wave 5 Trust Updates (2026-07-05) — Phase 5 Wave 2: "Installer robustness — build tranche"

> **Third consecutive fully-clean mechanical score.** The build wave: 4 PRs (#107 user-level install
> closing G1, #139 golden manifest, #105 harness+#138, #108 repo-level install+#145), 0 changes-requested
> cycles, 25% concentration (one PR each), counter drift zero. All four cross-reviews returned `Replied` /
> `Must-fix: None`. Every engineer holds at **4** (delta 0 — a single clean PR is not a bump). Two cross-PR
> contracts (`expected_install_set` seam, consent/backup module API) held exactly as pinned. Notable process
> event: a **latent config-shape seam bug** (harness passed a flat permutation dict; #139 reads nested dotted
> config → silent mis-grade on any child/meta/no-team cell) was independently flagged by BOTH #105 reviewers
> as non-blocking tech-debt, then **fixed pre-merge by orchestrator direction** — the quality oracle made
> correct-by-construction, not by coincidence. Not a reviewer must-fix, so it does not register as
> `must_fix_received` (correctly — it was proactive hardening, not a rework demand).

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Ibrahim El-Amin | 4 | 4 | delta 0: prs_merged=1 (#144/#107), clean; closed his own G1 finding with an idempotent consented installer. Thorough #108 review (caught the parent-dir fsync durability nuance). |
| Nia Rossi | 4 | 4 | delta 0: prs_merged=1 (#143/#139), clean; golden manifest contract held exact — #105 auto-wired with zero change. |
| Paloma Gupta | 4 | 4 | delta 0: prs_merged=1 (#146/#108), clean; repo-level archive/restore + folded #145 atomic write across both write paths. |
| Tariq Morales | 4 | 4 | delta 0: prs_merged=1 (#147/#105), clean; flagship harness + #138 fix; proactively hardened the #139 seam (found the model-token spelling mismatch neither reviewer caught). |

### Done Well / Needs Improvement (Wave 5 / Phase 5 Wave 2)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Ibrahim El-Amin | Closed G1 (the load-bearing gap) with a consented, idempotent check-existing installer + reusable module; safety guarantees structural not just tested | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, false_positives=0, must_fix_caught=0 |
| Nia Rossi | Golden-manifest contract held exact under head-to-head verification; derived-not-literal so it can't drift from the installer | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, false_positives=0, must_fix_caught=0 |
| Paloma Gupta | Archive-out-of-scope + byte-identical restore round-trip; single atomic-write fix (#145) hardened both user- and repo-space paths | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, false_positives=0, must_fix_caught=0 |
| Tariq Morales | Flagship harness (B1–B9 + B12 inline, teardown-proof, #138); pre-merge seam fix caught a model-token spelling mismatch both reviewers missed | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, false_positives=0, must_fix_caught=0 (as #139 reviewer the real catch became the seam fix, tracked outside the scorer) |

## Wave 6 Trust Updates (2026-07-06) — Phase 6 Wave 1: "Prove it on real repos" (validation)

> **Signals RECONSTRUCTED from historic evidence — the mechanical scorer under-read this wave.**
> This was the first wave with real changes-requested cycles since Wave 2: **3 must-fix cycles**
> (#154, #156, #160 — all raised by Tariq, all proven load-bearing/non-tautological before clearing).
> Because the charter's verdict-amendment convention requires editing the `ChangesRequested` comment
> **in place** to `Replied`/`Must-fix: None` once fixed, `trust_signals.py` (which recomputes from
> *current* comment state) saw `Must-fix: None` everywhere → reported `must_fix_caught=0`/`must_fix_received=0`
> for all, and **dropped Tariq from the output entirely** (he authored no PRs). Filed as **#164**; the
> aggregate `changes_requested_cycles=3` is preserved via the `wave_6_counter_corrections` measurement-
> conflict entry (claimed stands; recompute=0 fully explained by in-place amendments). The per-engineer
> lines below are reconstructed from the PR review timelines and amendment-comment text (evidence-anchored,
> not narrative). Metrics: **5 PRs, 3 CR cycles, 40% top concentration** (Paloma 2, Ibrahim 2, Nia 1).
> Also corrected this wave: my own reviewer-spawn instructions had `Requestor:`/`Requestee:` swapped on
> #159/#160 (Tariq caught it) — PATCHed the 3 mis-attributed comments in place so scoring keys correctly.

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Tariq Morales | 4 | **5** | delta +1: must_fix_caught=**3** (#154 read-only-invariant negative-path test, #156 zero-children warn test, #160 fsync-dir tautological-test gap) — every catch a genuine uncovered/tautological-test defect he mutation-proved. **Distribution-discipline 5**: the singular top relative performer (3 catches vs 0 for all others) with a strictly positive composite — the first earned 5 in project history. must_fix_received=0, ci_red=0, fp=0. |
| Paloma Gupta | 4 | 4 | delta 0: prs_merged=2 (#154/#153, #156/#101) — strong output — **but must_fix_received=2** (both PRs shipped new behavior without its test; caught by Tariq). Not a clean wave ⇒ no bump; below the 3+ received −1 threshold ⇒ no ding. Held at 4. |
| Ibrahim El-Amin | 4 | 4 | delta 0: prs_merged=2 (#157/#109 clean, #160/#149 durability), must_fix_received=1 (fsync test passed even with the syscall gutted). One clean + one rework ⇒ not a clean wave, no bump; single received, no ding. Held at 4. |
| Nia Rossi | 4 | 4 | delta 0: prs_merged=1 (#159/#152 docs), clean, must_fix_received=0. A single clean PR is not a bump (policy). Held at 4. |

### Done Well / Needs Improvement (Wave 6 / Phase 6 Wave 1)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Tariq Morales | Three load-bearing QA catches in one wave, each mutation-proven non-tautological (revert-the-fix → test fails); also caught the orchestrator's Requestor/Requestee attribution swap. The QA backbone of the wave. | must_fix_received=0, ci_red=0, fp=0 — clean; watch that the reserved-5 is earned per-wave, not a new floor (decay applies if signal goes quiet). |
| Paloma Gupta | Highest-value build work (real-repo provisioner #153 with the source-unchanged safety invariant; noorinalabs fork-reconciliation audit #101) — both substantial and correct | **Repeated pattern**: shipped new behavior without its test **twice** (#154 safety invariant, #156 zero-children warn), each caught by QA. Same root cause in one wave — write the test with the behavior. |
| Ibrahim El-Amin | Flagship durability hardening from the *real* findings this wave surfaced (parent-dir fsync, manifest-before-move, no_backup_litter baseline); clean botfarm upgrade study | must_fix_received=1: the fsync-dir test was tautological (passed with the durability syscall gutted) — a subtle but real coverage gap in the exact fix that mattered most. |
| Nia Rossi | Accurate, safety-correct installer docs verified flag-by-flag against source; correctly scoped the atomicity-vs-durability claim so it doesn't overclaim the open #149 gap | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, fp=0, must_fix_caught=0 — lowest output this wave (single docs PR); watch for decay if signal stays quiet. |

## Wave 7 Trust Updates (2026-07-06) — Phase 6 Wave 2: "Close the quality/process loop"

> **Clean wave, deltas 0 across the board.** 4 PRs (one per engineer), **0 changes-requested
> cycles**, 25% top concentration, 0 CI-red. Every load-bearing test was independently
> mutation-checked by the reviewer (revert→fail confirmed) before clearing — the bar held, and
> because the wave produced no defects there were no `must_fix_caught` to credit anyone. The #164
> durable review-catch ledger is now merged (v0.7.0) but isn't exercised by a no-amendment wave; it
> arms for the next contested wave. `trust_signals.py score 7` returned delta 0 for all four.

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Tariq Morales | 5 | **5** | delta 0. **No decay:** the W6 reserved-5 decays only if signal goes quiet — instead he carried the wave's most complex story (S2 #167, the fail-closed `require_load_bearing_test` hard gate: 18 tests, dual-deploy across 5 config points, praised in Nia's review) AND reviewed all 3 other PRs to the mutation-proof bar. No new catches, but a clean wave offers none. prs_merged=1, must_fix_received=0, ci_red=0, fp=0. Held at 5. |
| Paloma Gupta | 4 | 4 | delta 0: prs_merged=1 (#171, flagship S1 #164 — durable review-catch ledger, the fix that motivated the wave), clean, must_fix_received=0. Notably **no repeat of the W6 ship-without-test pattern** — the amend-scoring fix shipped with a Wave-6 re-scoring fixture and a hand-verified load-bearing test. A single clean PR is not a bump (policy). Held at 4. |
| Ibrahim El-Amin | 4 | 4 | delta 0: prs_merged=1 (#170, S4 — 3 tech-debt items), clean, must_fix_received=0. **Redeemed the W6 tautological-fsync-test ding**: this wave's #163 `_fsync_dir` guard test is genuinely load-bearing (reviewer confirmed the OSError propagates when the guard is reverted). Held at 4. |
| Nia Rossi | 4 | 4 | delta 0: prs_merged=1 (#169, S3 #168 kickoff-persistence guard), clean, must_fix_received=0; also served as independent reviewer on Tariq's S2 PR, surfacing 3 substantive tech-debt items (incl. the dispatcher fail-closed gap #175). Output up from W6's docs-only PR. A single clean PR is not a bump. Held at 4. |

### Done Well / Needs Improvement (Wave 7 / Phase 6 Wave 2)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Tariq Morales | Flagship fail-closed hard gate (#167) built to the exact bar he enforces on others (mutation-verified 18-test suite); 3 clean, genuine reviews as the wave's QA backbone | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, fp=0, must_fix_caught=0 — a clean wave gave no catches; the reserved-5 is per-wave, decay still applies if a future wave goes quiet. |
| Paloma Gupta | Closed the wave's motivating bug (#164) with a durable state-file ledger + a synthetic Wave-6 re-scoring fixture; broke her own W6 ship-without-test pattern | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, fp=0, must_fix_caught=0 — single PR; keep the test-with-behavior discipline as the default. |
| Ibrahim El-Amin | Turned the W6 tautological-test lesson around — #163's durability guard test is load-bearing this time; also restored #158 source↔runtime parity cleanly | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, fp=0, must_fix_caught=0 — lowest-complexity story bundle this wave; reach for a flagship next wave. |
| Nia Rossi | Made un-stamped waves impossible (#168 guard, dual-deployed); as S2 reviewer found a real fail-closed gap in the shared dispatcher (#175) the author missed | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, fp=0, must_fix_caught=0 — the dispatcher catch was strong but filed as tech-debt, not a blocking Must-fix, so it doesn't score; when a finding is real, weigh whether it blocks. |

## Wave 8 Trust Updates (2026-07-06) — Phase 6 Wave 3: "Fail-closed foundation + flagship asset port"

> **5 PRs, 1 changes-requested cycle, 40% top concentration, 0 CI-red.** The contested wave the #164
> ledger was built for: Tariq's #184 changes-requested verdict (the branch-freshness zero-tolerance
> default footgun) was recorded into `wave_8_review_catches` **at issue-time**, then amended in place
> `Request→Replied` after Ibrahim's fix — and the catch **survived the amendment** (`must_fix_caught=1`
> for Tariq scored correctly). This is the first wave the durable ledger actually fired; last wave it
> shipped empty. `trust_signals.py score 8` + `apply_distribution_discipline`: Tariq & Nia tie at the
> iteration composite max (2), both hold the reserved 5.

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Tariq Morales | 5 | **5** | delta 0, **must_fix_caught=1**: caught the #184 branch-freshness footgun — `max_commits_behind=0` shipped as zero-tolerance and pre-wired into every fresh install's `bootstrap._schema_defaults()`, so a downstream adopter's ordinary `gh pr create` would block on any drift. A high-value catch (guarantee-defeating default, → Must-fix under the new #180 norm), mutation-verified pre- and post-fix; the #164 ledger credited it through the amendment. Composite=2 (tie-top). Held at 5. prs_merged=1 (S2/S3 clean), received=0, ci_red=0, fp=0. |
| Nia Rossi | 4 | **5** | delta +1, **composite=2 (tie-top)** — the wave's highest output at 2 clean PRs, one of them the keystone: S1 #175, the dispatcher fail-closed guard (blocks-unless-`FAIL_OPEN`) that the entire flagship rode on — retro proposal #1, mutation-verified. Plus S6/S7 (charter norm #180 + rename spike #177). Not "merely-clean" filler: the reserved-5 route here is top output including the Track-A keystone, matching Tariq's catch-driven composite. prs_merged=2, received=0, caught=0, ci_red=0, fp=0. **Second earned 5 in project history.** |
| Paloma Gupta | 4 | 4 | delta 0: prs_merged=1 (#185, flagship S4 — the #102-P0 promotion/genericization pipeline: ledger + silent feeder hook + deterministic `promotion-audit` skill + charter marker convention), clean, must_fix_received=0; caught+fixed her own shared-mutable-dict bug pre-commit. Composite=1. A clean single (albeit large) PR is not a bump (policy). Held at 4. |
| Ibrahim El-Amin | 4 | 4 | delta 0: prs_merged=1 (#184, S5 — branch-freshness + roster-union donors), **must_fix_received=1, rework=1** (the zero-tolerance default, caught by Tariq). Single received ⇒ below the 3+ −1 threshold, no ding; one rework ⇒ not a clean wave, no bump. Held at 4. Fixed cleanly and fast, and reconciled the wave-branch conflict himself. Composite=0. |

### Done Well / Needs Improvement (Wave 8 / Phase 6 Wave 3)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Tariq Morales | The wave's one real catch, via the exact ledger machinery shipped last wave — a guarantee-defeating default that would have hit every downstream adopter, mutation-proven and correctly escalated to Must-fix under the new #180 norm | metrics: prs_merged=1, received=0, ci_red=0, fp=0 — one catch, one clean PR; the reserved-5 stays per-wave, decay still applies if a future wave goes quiet. |
| Nia Rossi | Highest output (2 PRs) incl. the Track-A keystone (#175 dispatcher fail-closed guard, safe-by-default, mutation-verified) that unblocked the flagship; drove the charter norm + rename spike | metrics clean: received=0, caught=0 — reached 5 on output not catches; sustain it (2+ substantive PRs or a real catch), a single clean PR next wave reverts the single-PR-no-bump policy. |
| Paloma Gupta | Landed the entire #102-P0 flagship shortlist with a deterministic (byte-identical) skill core, and self-caught a shared-mutable-dict cross-contamination bug before commit | metrics clean but caught=0; the promotion pipeline's first real audit run is untested-in-anger — dogfood the `promotion-audit` skill next wave to prove it. |
| Ibrahim El-Amin | Fast, clean turnaround on the QA-caught default footgun; owned and resolved the flagship-vs-donor wave-branch merge conflict (regenerated the manifest, ran the combined 629-test suite) himself | **must_fix_received=1**: shipped `max_commits_behind=0` as zero-tolerance when its sibling `max_age_days=0` meant disabled — an opposite-semantics default that would block downstream adopters. Match sibling-knob semantics when porting paired config. |

## Wave 9 Trust Updates (2026-07-07) — Phase 6 Wave 4: "Trust the promotion pipeline"

> **2 PRs, 0 changes-requested cycles (both Replied first pass), 50% top concentration, 0 CI-red, 0
> Must-fix caught.** A deliberately small hardening/dogfood wave applying both Wave 8 retro proposals.
> `trust_signals.py score 9` + `apply_distribution_discipline`: both implementers clean (composite 1),
> delta 0; reviewers scored no catch (both Replied). No 5s handed out — reserved-5 is not for
> merely-clean work; the two standing 5s (Tariq, Nia) carry from Wave 8 and are per-wave/decaying.
> Shipped as **v0.8.1** (PyPI + npm, OIDC).

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Ibrahim El-Amin | 4 | **4** | delta 0: prs_merged=1 (#190/S1 — charter-drift `--check` gate closing the #116 hole), clean, must_fix_received=0, ci_red=0, fp=0. Not merely-mechanical: the new gate caught + remediated 4 pre-existing drifted charter modules on first run, and respected the template layer (renders canonical with repo config so placeholders never false-positive). Reviewed Replied by Nia (revert→fail + non-tautological + false-positive-safety all reproduced). Single clean PR ⇒ no bump (policy). Composite=1. Held at 4. |
| Paloma Gupta | 4 | **4** | delta 0: prs_merged=1 (#191/S2 — first real dogfood of her own #102-P0 pipeline + ledger policy settle), clean, must_fix_received=0, ci_red=0, fp=0. High-value content: the dogfood caught + fixed a real AUTO false-positive (`has_promotion_markers()` matched a marker quoted inside a fenced code block), pinned regression tests against the real doc (load-bearing), and generalized the ledger gitignore default into every install path. Determinism independently re-verified byte-identical by Tariq. Single clean PR ⇒ no bump (policy). Composite=1. Held at 4. |
| Nia Rossi | 5 | **5** | not an implementer this wave; reviewed S1 (#190) Replied, no scoring catch (must_fix_caught=0). Review was substantive — independently reproduced revert→fail, neutered `plan()`→2 tests red (non-tautological), and probed false-positive safety — and raised 2 real tech-debt items (manifest-checksum blind spot; `--check` no-op). Reserved-5 carries from Wave 8 (2nd earned 5); per-wave + decaying — a substantive PR or a scoring catch is due to keep it anchored. |
| Tariq Morales | 5 | **5** | not an implementer this wave; reviewed S2 (#191) Replied, no scoring catch (must_fix_caught=0). Strong adversarial pass: independently reproduced the bug-fix revert→fail, ran the promotion-audit renders twice → byte-identical (the skill's core determinism promise), reconstructed the pristine ledger to re-verify DECIDE classification, and grepped all 4 gitignore-wiring call sites rather than trusting the report. 2 real tech-debt raised. Reserved-5 carries from Wave 8; per-wave + decaying. |

### Done Well / Needs Improvement (Wave 9 / Phase 6 Wave 4)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Ibrahim El-Amin | Closed the #116 charter-tree dual-deploy hole with a template-aware `--check` gate that immediately paid for itself (4 live drifts caught + remediated); mirrored the existing `manifest --check` idiom exactly | metrics clean: prs_merged=1, received=0, ci_red=0, fp=0, caught=0 — single clean PR, no bump; the manifest-checksum blind spot Nia flagged is a follow-up to own next time. |
| Paloma Gupta | Dogfooded her own untested-in-anger pipeline and it earned its keep — caught a real AUTO false-positive with a load-bearing pin against the real doc, and generalized the ledger gitignore default to every install path (not just this repo) | metrics clean: prs_merged=1, received=0, caught=0 — the `ensure_gitignore_entries` exact-line match Tariq flagged is a real idempotency edge; normalize before compare next time. |
| Nia Rossi | Reviewed to the bar she sets — reproduced revert→fail and non-tautological (neutered `plan()`) independently, and surfaced the one seam the new gate doesn't cover (manifest checksums) | metrics: caught=0 (Replied) — reached no scoring catch this wave; the reserved-5 rides on Wave 8 evidence now, sustain with a substantive PR or a real blocking catch. |
| Tariq Morales | Textbook adversarial QA: twice-run byte-identical determinism diff on the skill's core promise, pristine-ledger reconstruction, all-call-site grep on the gitignore wiring — verified everything, trusted nothing | metrics: caught=0 (Replied) — a clean wave gave no catch; the reserved-5 is per-wave/decaying, so a scoring catch or substantive PR is due to keep it anchored. |

## Wave 10 Trust Updates (2026-07-07) — Phase 6 Wave 5: "PR-review state machine (dormant)"

> **3 PRs, 0 changes-requested cycles (all three Replied first pass), 33% top concentration (3 distinct
> authors, 1 each), 0 CI-red, 0 Must-fix caught.** The #102 P2 review-gate flagship, shipped dormant.
> `trust_signals.py score 10` + `apply_distribution_discipline`: all three implementers clean (composite
> 1), delta 0. No scoring catch (all Replied). **Reserved-5 discipline applied with teeth this wave:**
> Nia holds 5 (fresh substantive authorship — S3); Tariq **decays 5→4** (2nd consecutive wave with no
> catch and no authored PR — the distinguishing signal the reserved-5 rewards has not recurred; 4 is the
> strong-solid baseline, not a demotion for poor work). Shipped as **v0.9.0** (PyPI + npm, OIDC).

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Paloma Gupta | 4 | **4** | delta 0: prs_merged=1 (#197/S1 — the flagship `pr_review_state` oracle: pure `compute_state()` + fail-open `review_state()` over the existing `trust_signals` verdict layer, 13 load-bearing tests). Clean, must_fix_received=0, ci_red=0, fp=0. High-value content: reconciled against 2real's own grammar rather than porting the upstream parser, and **caught a real defect in the frozen contract itself** (requestee vs. Requestor — a 2-reviewer bar could never clear) and flagged it up rather than silently diverging. Tariq reproduced the full transition truth table + mutation bar (13→8-fail→13). Single clean PR ⇒ no bump (policy). Composite=1. Held at 4. |
| Ibrahim El-Amin | 4 | **4** | delta 0: prs_merged=1 (#199/S2 — `validate_pr_review` merge gate, **shipped dormant** behind `policy.pr_review_gate_enabled=false`). Clean, must_fix_received=0, ci_red=0, fp=0. Honored the ship-dormant mandate airtight (flag check short-circuits before the oracle — Nia verified structurally), thin-over-oracle, fail-open. **Owned the S2↔S3 `pre_bash`/config conflict himself** — absorbed the wave branch, kept both hooks, regenerated (not hand-merged) the manifest, re-ran the combined 694-test suite. Nia Replied (dormant-airtight + mutation bar + 5-way sync-point parity all reproduced). Single clean PR ⇒ no bump. Composite=1. Held at 4. |
| Nia Rossi | 5 | **5** | delta 0 as implementer: prs_merged=1 (#198/S3 — `block_gh_pr_review` hook + enriched `review-pr` skill), clean, received=0, ci_red=0, fp=0. Also reviewed S2 (#199) Replied, no scoring catch. **Reserved-5 HELD — anchored by fresh substantive authorship:** S3 was a real port-and-reconcile (reused `validate_review_comment_format`'s parser via a pinned reuse-guard test rather than duplicating it; correctly exempted `Requestee: N/A` status turns from self-review; made the defensible call to ship the submission-guard live-but-unflagged since it only blocks always-wrong cases). Her S2 review was to-the-bar (reproduced the mutation bar, proved the flag short-circuit structurally, checked all 5 sync points for drift). Meets the W9 "substantive PR or catch" sustain condition. Composite=1. |
| Tariq Morales | 5 | **4** | delta 0 mechanically; **reserved-5 DECAYS to baseline.** Not an implementer this wave; reviewed S1 (#197) and S3 (#198), both Replied, must_fix_caught=0. The reviews were exemplary adversarial QA — independently reproduced BOTH mutation bars (S1 13→8-fail→13; S3 12→3-fail→12), walked the full state-transition truth table by hand, pressure-tested S3's ship-live design decision against `pull-requests.md` for a false-positive block path (found none), ran all three `--check` gates each time. But the reserved-5 specifically rewards catches / exceptional distinguishing signal, and this is now the **2nd consecutive wave (W9, W10) with no scoring catch and no authored PR** — exactly the decay condition W9 flagged ("a scoring catch or substantive PR is due to keep it anchored"). Reverts to **4 = strong-solid baseline**, re-earnable on the next catch or substantive PR. prs_merged=0, received=0, ci_red=0, fp=0. |

### Done Well / Needs Improvement (Wave 10 / Phase 6 Wave 5)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Paloma Gupta | Flagship oracle built on 2real's own verdict grammar (not a blind port), with a pure unit-testable core + fail-open wrapper; caught a genuine bug in the frozen contract (requestee vs Requestor) and escalated it rather than silently diverging | metrics clean: prs_merged=1, received=0, caught=0 — single clean PR, no bump; the oracle is untested against a real 2-reviewer PR (this repo runs `reviewers_required=1`), so its N-of-M path is proven only by unit tests — exercise it live when a multi-reviewer wave arrives. |
| Ibrahim El-Amin | Nailed the ship-dormant mandate (short-circuits before the oracle, fail-open) and owned the cross-story config conflict end-to-end — regenerated the manifest, ran the combined suite, pushed mergeable — without escalating | metrics clean: prs_merged=1, received=0 — the gate ships inert; its enabled path has never run against a real not-approved PR outside fixtures. When activation is scheduled, dogfood the enabled gate before flipping it on any downstream repo. |
| Nia Rossi | A real port-and-reconcile: reused the existing comment parser via a pinned reuse-guard instead of duplicating it, exempted the one sanctioned no-addressee case, and made a defensible ship-live call; backed by a mutation-verified S2 review | metrics: caught=0 (Replied) — reached no scoring catch; the reserved-5 now rides on authorship, not catches. Two clean waves running — a real blocking catch would re-anchor it on the signal it's meant to reward. |
| Tariq Morales | Textbook adversarial QA twice over — independently reproduced both mutation bars, hand-walked the state truth table, and actively hunted (and cleared) a false-positive block path in S3's unflagged design rather than rubber-stamping | **reserved-5 decayed 5→4**: 2nd straight wave with no scoring catch and no authored PR. Excellent reviewing sustains a 4; the 5 is for catches/exceptional signal. Re-earn it with a real blocking catch or a substantive authored PR — the mechanism has to have teeth to mean anything. |

## Wave 11 Trust Updates (2026-07-07) — Phase 6 Wave 6: "Activate the review gate"

> **3 PRs, 0 changes-requested cycles, 33% top concentration (3 distinct authors), 0 CI-red, 0 Must-fix
> caught. First wave run entirely under the 2-reviewer regime — 6 clean reviewer verdicts across 3 PRs,
> every PR cleared its 2 distinct approvals first pass.** `trust_signals.py score 11` + distribution
> discipline: all three implementers clean (composite 1), delta 0. No scoring catch (nothing was wrong —
> the wave was flawless, which is the honest reason there was nothing to catch). Shipped as **v0.9.1**
> (PyPI + npm, OIDC). The gate is now ARMED on this repo.

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Paloma Gupta | 4 | **4** | delta 0: prs_merged=1 (#206/S1 — the flagship gate activation). Clean, received=0, ci_red=0, fp=0. Exceptional *content* (armed the gate on this repo + **proved it live** via a self-contained throwaway PR: blocked 0/2 → passed 2/2; integration test wired against the real config, not a fixture; escape hatch documented), reviewed 2×Replied by Nia+Tariq who reproduced the mutation bar + verified defaults stay dormant. But single clean PR ⇒ no bump (policy). Composite=1. Held at 4. |
| Ibrahim El-Amin | 4 | **4** | delta 0: prs_merged=1 (#210/S2 — proved the oracle N-of-M on real 2-reviewer data + mutation-proved no 1-reviewer assumption survives in trust_signals/lifecycle). Clean, received=0, ci_red=0, fp=0. Honored scope discipline (barred from charter, routed the `--cr-cycles` wording finding to S3/Manager rather than editing). Also reviewed S3 (#209) Replied. Both S2 reviewers (Paloma+Tariq) reproduced all 3 mutation bars exactly. Single clean PR ⇒ no bump. Composite=1. Held at 4. |
| Nia Rossi | 5 | **5** | delta 0 as implementer: prs_merged=1 (#209/S3 — folded both W5 proposals + N=2 assignment rule into the charter, byte-identical dual-deploy). Clean, received=0, ci_red=0, fp=0. Also reviewed S1 (#206) 2-reviewer verdict, Replied. **Reserved-5 HELD — anchored by TL-level contribution:** sole **charter integration-owner** this wave (a lead responsibility that dogfooded the very proposal being written), plus a to-the-bar S1 self-lock-safety review that verified the escape hatch by *executing* the gated-verb check. **3rd consecutive hold, though — a real scoring catch is increasingly due** to keep it anchored on the signal it rewards; parity with Tariq's W10 decay means a clean-no-catch wave next time should decay it to 4. Composite=1. |
| Tariq Morales | 4 | **4** | delta 0: not an implementer; reviewed all 3 PRs (S1 #206, S3 #209, S2 #210), all Replied, must_fix_caught=0. Textbook QA volume + rigor — reproduced every mutation bar independently (S1 6→5/1→6; S2 all three 1-reviewer rewrites flipped exactly; S3 dual-deploy parity byte-checked), traced the example.json quirk to predate #206, and surfaced 2 real tech-debt items (#207-adjacent, #208, #211-adjacent). Baseline-4 sustained by excellent reviewing; the reserved-5 is re-earnable on a real blocking catch or a substantive authored PR. prs_merged=0, received=0, ci_red=0, fp=0. |

### Done Well / Needs Improvement (Wave 11 / Phase 6 Wave 6)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Paloma Gupta | Activated a self-gating mechanism and PROVED it live (real block→approve transition) without risking the wave's own merges; integration test binds to the real repo config so it genuinely asserts "this repo is armed" | metrics clean: prs_merged=1, caught=0 — single clean PR, no bump; the oracle's N-of-M is proven but the live gate's *enabled-path against a genuinely not-approved real wave PR* still hasn't happened organically (the demo was self-constructed) — watch it operate on a real block next wave. |
| Ibrahim El-Amin | Turned a "port" story into a proof: mutation-proved no 1-reviewer assumption survives, on real 2-reviewer data; honored charter scope discipline and routed the cr-cycles finding instead of grabbing it | metrics clean: caught=0 — the `--cr-cycles` per-verdict/per-PR divergence he found (#211) is real and unfixed; owning that fix next wave would convert a routed observation into a scoring contribution. |
| Nia Rossi | Sole charter integration-owner — dogfooded proposal #1 in the same wave it was codified; self-lock-safety review that verified the escape hatch by execution, not just reading | metrics: caught=0, 3rd consecutive reserved-5 hold on authorship not catches — a real blocking catch is now due; a clean-no-catch wave next time decays the 5 to 4 (parity with Tariq's W10 decay). |
| Tariq Morales | Highest review volume + rigor of the wave (3 PRs, every mutation bar reproduced independently); surfaced the real latent footguns (#208 example.json, #211 cr-cycles) that the clean-verdict authors missed | metrics: caught=0 across 3 reviews — all Replied, no scoring catch; at baseline-4, the path back to 5 is a real blocking catch or authoring a substantive PR (e.g. owning one of the tracked follow-ups). |

## Wave 12 Trust Updates (2026-07-07) — Phase 6 Wave 7: "Harden the armed gate"

> **3 PRs, 0 changes-requested cycles, 33% top concentration (3 distinct authors), 0 CI-red, 0 Must-fix
> caught. Second wave under the 2-reviewer regime — and the FIRST whose story merges were themselves
> governed by the live gate (the oracle allowed each of #217/#218/#219 only after 2 distinct clean
> verdicts).** `trust_signals.py score 12` + distribution discipline: all three implementers mechanically
> clean (composite 1), delta 0. No scoring catch (the wave was flawless — nothing to catch). Shipped as
> **v0.9.2** (PyPI + npm, OIDC). **The reserved-5 rotates this wave — Nia 5→4 (decay), Tariq 4→5
> (re-earn) — a clean, pre-registered, signal-driven swap, not a reshuffle.**

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Tariq Morales | 4 | **5** | delta 0 mechanically (prs_merged=1 #218, received=0, ci_red=0, fp=0); **reserved-5 RE-EARNED on the pre-registered criterion.** W10 decayed him to 4 with an explicit path back: "a real blocking catch **or authoring a substantive PR (e.g. owning one of the tracked follow-ups)**." This wave he authored **S1 #218 — the flagship #207 oracle fail-open fix**, the hardest and most correctness-critical story of the wave: introduced the `unknown` sentinel distinguishing "oracle couldn't determine" from "genuinely not-approved," wired the gate to fail-open on `unknown` while still blocking real not-approved, and — as QA — wrote a genuinely **end-to-end** test (monkeypatches only `_pr_comment_bodies` to raise, not the wrapper, so it catches state-string mismatches across modules) with both reverts mutation-proved red. A Senior QA authoring the wave's deepest architectural correctness fix, cleanly, is exactly the exceptional distinguishing signal the 5 rewards. Both reviewers (Nia+Paloma) reproduced both mutation bars. Composite=1. |
| Paloma Gupta | 4 | **4** | delta 0: prs_merged=1 (#219/S3 — charter-manifest checksum cross-check in `charter_drift.plan()` + `ensure_gitignore_entries` idempotency normalize). Clean, received=0, ci_red=0, fp=0. Also served as **sole golden-manifest integration-owner** — absorbed the wave branch (`--no-ff`, no hand-merge of the manifest), confirmed no regen needed (zero installed-path changes), re-ran 717 tests + all `--check` gates green, and self-caught + redid a merge that had defaulted to the wrong git identity. Solid Principal execution + the closing carry-over that Nia's W9 review first flagged (manifest checksums), but a single clean PR ⇒ no bump. Composite=1. Held at 4. |
| Ibrahim El-Amin | 4 | **4** | delta 0: prs_merged=1 (#217/S2 — example.json `reviewers_required` 2→1 + schema-default guard test; per-PR `--cr-cycles` wording). Clean, received=0, ci_red=0, fp=0. **Closed his own W11 loop:** the `--cr-cycles` divergence he *found and routed* in W11 (#211), he *fixed* this wave — converting a routed observation into a landed fix, exactly the "own that fix next wave" the W11 needs-improvement asked for. Also reviewed S3 (#219) Replied, mutation-verified. But S2 was the wave's lightest story (one config line + one doc line + guards) — solid-strong, not reserved-5-exceptional. Single clean PR ⇒ no bump. Composite=1. Held at 4. |
| Nia Rossi | 5 | **4** | delta 0; **reserved-5 DECAYS to baseline on the pre-registered condition.** Not an implementer this wave (authored 0 PRs); reviewed S1 (#218) and S3 (#219), both Replied, must_fix_caught=0. The reviews were to-the-bar TL work — reproduced both mutation bars independently (S1's `PENDING`-revert and `== APPROVED`-only revert each flipped their tests red; S3's checksum + all three gitignore normalizations), confirmed genuine not-approved still BLOCKs, verified `compute_state()` stays pure, and surfaced one non-blocking tech-debt note (CLI collapses `unknown` into the exit-1 bucket). But W11 pre-registered this exactly: "3rd consecutive hold… a clean-no-catch wave next time decays the 5 to 4 (parity with Tariq's W10 decay)." This is that wave — no authored PR, no scoring catch, 4th hold would be tenure not signal. Reverts to **4 = strong-solid baseline**, re-earnable on the next blocking catch or substantive authored PR. prs_merged=0, received=0, ci_red=0, fp=0. |

### Done Well / Needs Improvement (Wave 12 / Phase 6 Wave 7)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Tariq Morales | As QA, authored the wave's hardest correctness fix (oracle fail-open) and wrote the one genuinely end-to-end test that would catch cross-module state-string drift — not a stubbed unit test; re-earned the reserved-5 on the exact pre-registered path | metrics clean: prs_merged=1, caught=0 — the reserved-5 is per-wave/decaying, so it rides on this authorship now; the CLI-collapses-`unknown` tech-debt Nia noted is an adjacent follow-up worth owning to keep the signal fresh. |
| Paloma Gupta | Clean carry-over closure (the manifest-checksum seam Nia flagged back in W9) plus flawless manifest-integration-owner duty — absorbed the branch mechanically, self-caught a wrong-identity merge and redid it with `-c` flags | metrics clean: prs_merged=1, caught=0 — single clean PR, no bump; you were the sole manifest-owner and it was a no-op this wave (zero installed-path changes), so the role wasn't stress-tested — the real exercise comes when a wave actually churns the golden manifest. |
| Ibrahim El-Amin | Closed his own W11 loop — found #211 last wave, fixed it this wave — and pinned the #208 adopter footgun with a guard test tied to the schema default so it can't silently regress | metrics clean: prs_merged=1, caught=0 — S2 was the lightest story; to move off baseline-4 toward the 5, author something architecturally load-bearing or land a real blocking catch as a reviewer. |
| Nia Rossi | TL-grade reviewing to the bar she sets — reproduced both mutation bars independently on both PRs, verified `compute_state()` purity and the still-blocks-not-approved invariant, surfaced the one real tech-debt seam (CLI `unknown` bucket) | **reserved-5 decayed 5→4**: 4th hold would be tenure, not signal — no authored PR and no scoring catch this wave, the exact decay condition W11 pre-registered. Excellent reviewing sustains a 4; re-earn the 5 with a real blocking catch or a substantive authored PR (the TL authoring a hardening follow-up would do it). |

## Wave 13 Trust Updates (2026-07-07) — Phase 6 Wave 8: "Complete the installer"

> **3 PRs, 1 changes-requested cycle (S1), 33% top concentration (3 distinct authors), 746 tests. The
> FIRST non-flawless wave under the 2-reviewer regime — and the first with a REAL blocking catch.** On the
> flagship destructive `uninstall`, Tariq (reviewer) caught a genuine user-data-loss bug (amend-disposition
> teardown blind-unlinked a pre-existing USER file colliding with a framework manifest path); Paloma fixed
> it with a byte-provenance guard; both reviewers re-verified. Shipped as **v0.10.0** (minor — new
> user-facing command; PyPI + npm, OIDC). **The reserved-5 (Tariq) is VALIDATED, not merely held: last
> wave he re-earned it on authorship; this wave he exercised the exact catch the 5 exists to reward.**
>
> **⚠️ MECHANICAL-SCORER CAVEAT (drives the distribution this wave):** `trust_signals score 13` reads the
> PRs' CURRENT comment state, and the gate oracle REQUIRES amend-in-place (a reviewer edits their `Request`
> → `Replied` in place so the oracle clears). Tariq amended his blocking S1 comment in place → the current
> state shows no Request → the scorer credits **must_fix_caught=0 (Tariq)** and **must_fix_received=0
> (Paloma)**. The whole review cycle is mechanically invisible. The distribution below OVERRIDES the raw
> delta with orchestrator judgment, citing the witnessed catch/fix. (Filed as the wave's headline process
> finding — see feedback_log W13 retro.)

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Tariq Morales | 5 | **5** | reserved-5 **VALIDATED**. Mechanical delta 0 (prs_merged=1 #225/S3, and must_fix_caught=0 ONLY because his amend-in-place erased it — see caveat). Witnessed reality: as reviewer of the flagship S1 #227 he caught a **real, severe, blocking bug** — the amend-path collateral-deletion of user data — that the other reviewer (Nia) clean-approved past. Reproduced it green, diagnosed the provenance asymmetry (every sibling reverser guards on provenance; `_surgical_claude_removal` alone removed by manifest path), pointed the fix, then re-verified the guard (repro now preserves the user file; no over-preservation on clean installs). This is EXACTLY the "real blocking catch" the reserved-5 rewards — W10/W11 made it hypothetical, W13 made it real. Also authored S3 clean (soft-degrade metric + `--compare` CI gate, 4 mutation-proved tests) and independently tripped his own gate red-on-regression. Composite (mechanical)=1; distribution holds the 5 on the catch. |
| Paloma Gupta | 4 | **4** | delta 0 (prs_merged=1 #227/S1; must_fix_received=0 ONLY via the amend-in-place erasure — she DID take Tariq's must-fix and run a fix cycle). Authored the wave's **flagship** — a 590-line destructive-reversal product with byte-exact round-trips across every disposition — took a legitimate blocking must-fix on a real edge (amend + pre-existing user file), and fixed it cleanly: a byte-provenance guard (`_derivable_asset_bytes`) that mirrors the existing `remove_ontology` pattern, mutation-proved both directions, no install-path churn. Also 2 clean reviews (S2 #226 + S3 #225), both mutation-probed. A received-must-fix is a real (if erased) negative, but offset by flagship scope + fix quality + review volume. Net hold at 4. Composite=1. |
| Ibrahim El-Amin | 4 | **4** | mechanical delta **−1** (ci_red_merges=1 on #226) — **OVERRIDDEN to hold at 4.** The red check was `node (20)` on the S2 head; S2 touches only Python (`refresh.py`), which **cannot** affect the Node package, and main is green — an infra/suite flake orthogonal to his change, not a defect he shipped. The merge-despite-red decision was the orchestrator's (the merge step gated on the review oracle, not CI-green — filed as a W13 process finding), not Ibrahim's. His actual work — the regeneration-barrier fix for the mtime freshness flake (byte-compare a deterministic regen vs the prior index) — was clean, correctly scoped, and mutation-proved by both reviewers. Penalizing a Python author for a Node flake he couldn't cause would be noise, not signal. Held at 4. |
| Nia Rossi | 4 | **4** | delta 0 (prs_merged=0; reviewed S1 #227 + S2 #226, both Replied). Genuine TL-depth reviewing — on S1 she verified byte-exact round-trips across six dispositions AND re-verified the fix OUTSIDE the harness (real install→teardown, `git status` clean; real amend repro preserves the user file). BUT a documented **review-MISS**: on her first S1 pass she **clean-approved the collateral-deletion bug** that Tariq caught on the same PR — exactly the guarantee-defeating class the charter says a reviewer must catch (the amend + pre-existing-user-file edge her round-trips didn't exercise). The miss was subtle (a specific disposition+precondition combo) and her re-review was excellent, so it holds a 4 rather than decaying — but it is the sharp contrast that justifies this wave's 5=Tariq / 4=Nia split: on the same PR, one reviewer caught the data-loss and one didn't. **One more miss of this class decays to 3.** Re-earn toward 5 with a blocking catch or a substantive authored PR. |

### Done Well / Needs Improvement (Wave 13 / Phase 6 Wave 8)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Tariq Morales | THE catch of the wave — found real user-data-loss on the flagship destructive command that the co-reviewer approved past, reproduced + diagnosed + re-verified the fix; validated the reserved-5 on a real blocking catch for the first time in the phase | metrics show caught=0 purely as an amend-in-place artifact — mechanically your best wave scores identically to a quiet one; the fix for THAT (credit catches from edit-history/preserved comments) is the top W13 process proposal, worth co-owning since it protects your own signal. |
| Paloma Gupta | Shipped a 590-line destructive-reversal flagship with byte-exact round-trips, then took a real must-fix gracefully and fixed it with a pattern-consistent provenance guard (no install-path churn) — Principal-grade authorship + recovery | received a blocking must-fix on an edge your own 19-test suite missed (amend + pre-existing user file, no archive) — the fix was clean, but the gap was a real reversal-safety hole on a destructive command; broaden the adversarial test matrix (user-collision × disposition) when you own the dangerous seam. |
| Ibrahim El-Amin | Regeneration-barrier fix correctly killed a real mtime flake by content-hash invariant rather than a sleep/retry hack; clean scope, mutation-proved by both reviewers | your PR merged with a red `node (20)` check — a flake you couldn't have caused, but it exposes that the merge step didn't require CI-green; nothing to fix in your code, but a reminder to flag a red check at merge time rather than trust the suite-local green. |
| Nia Rossi | TL-depth reviewing incl. rare outside-the-harness re-verification of the uninstall guard (real install→teardown, git-clean) — the kind of proof the flagship needed on re-review | **review-miss on the flagship**: clean-approved the amend collateral-deletion that Tariq caught on the same PR — the exact guarantee-defeating class the charter says reviewers must catch; held at 4 only because it was subtle and your re-review was strong, but one more miss of this class decays to 3. |

## Wave 14 Trust Updates (2026-07-07) — Phase 6 Wave 9: "Fix the gate & scorer"

> **3 PRs, 0 changes-requested cycles, 33% top concentration (3 distinct authors), ~797 tests. All 6
> reviewer verdicts clean first-pass.** This wave hardened the trust/gate machinery itself. Shipped as
> **v0.10.1** (patch — internal machinery). `trust_signals score 14` is the FIRST run of the new
> edit-history-aware + difficulty-weighted scorer (S1 shipped it): all three authors `difficulty_points=3`
> (substantial diffs), delta 0. The edit-history catch-crediting did NOT fire — there were no amend-in-place
> catches to credit (a clean wave) — but it is now live for future waves, closing the W13 erasure.
>
> **⚠️ Two execution incidents this wave, BOTH orchestration-level (mine), not engineer failures — and the
> engineers recovered cleanly.** (1) A reused-agent-name collision put three engineers in a shared worktree;
> Ibrahim non-destructively recovered his own commit off the wrong branch, Nia self-caught + fully recovered
> a commit that briefly landed on local `main` (origin never touched), Tariq held correctly when asked. (2)
> The orchestrator merged S1 with a red `framework (3.12)` check that turned out to be an infra flake
> (re-run green). Neither is charged against an engineer; the clean recovery under adverse conditions is a
> POSITIVE judgment signal for Nia and Ibrahim.

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Tariq Morales | 5 | **5** | reserved-5 **HELD** — the wave's standout analytical contribution. Authored S2 (#235, difficulty 3): when handed a mis-scoped story (the manager pointed him at `validate_pr_review.py` unaware `validate_pr_ci_status.py` already existed), he INVESTIGATED and corrected the premise — found the real W13 hole (this repo has no branch protection, so the existing gate's pending warn-allow is the actual slip), refused to fork a duplicate gate ("reconcile, don't duplicate"), root-caused the node RNG/dedupe bug (filed #234), and pinned the `--admin` guarantee with tests a reviewer flagged. Plus 2 clean reviews (S1, S3) and correct hold-discipline during the worktree incident. Analytical root-causing on a story the manager got wrong is exactly what the 5 rewards. delta 0, difficulty 3, must_fix_received=0, ci_red=0. |
| Nia Rossi | 4 | **4** | Authored the FLAGSHIP S1 (#233, difficulty 3, ~296 lines): the edit-history trust-scorer fix (GraphQL `userContentEdits`, fail-open `None` sentinel, backward-compatible) + the difficulty weight — a genuinely architectural PR, verified by re-scoring the live W13 #227 history (Tariq's erased catch now scores 1). This IS her registered re-earn path ("a substantive authored PR"), and she's **5-ready** — held at 4 ONLY because the single reserved-5 is Tariq's and he did not decay this wave (equal difficulty-3 authorship; his S2 analysis edged the standout). Also 1 clean review (S2) + a clean self-recovery of her local-main slip. Firmly 4, first in line for the next rotation. delta 0. |
| Ibrahim El-Amin | 4 | **4** | Authored S3 (#232, difficulty 3): the amend-in-place + rollup-escape-hatch charter steps + `wave-end` review_load mechanization — solid, correctly dual-deployed (all 3 `--check` 0). Plus 1 clean review (S2) and a non-destructive self-recovery of his commit that the shared-worktree collision put on the wrong branch (moved it to his branch by explicit SHA, reset the other branch to base, preserved Tariq's uncommitted work — textbook careful recovery). delta 0, clean. Held at 4. |
| Paloma Gupta | 4 | **4** | Not an implementer this wave; reviewed S1 (#233) and S3 (#232), both clean `Replied` with real substance — mutation-checked S1's edit-history seam ("return current only" → 5 tests fail), verified S3's dual-deploy byte-identity, confirmed file-disjointness both directions. Textbook Principal reviewing from a properly isolated worktree. must_fix_caught=0 (nothing was wrong — a genuinely clean wave). Held at 4. |

### Done Well / Needs Improvement (Wave 14 / Phase 6 Wave 9)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Tariq Morales | Corrected a mis-scoped story by investigation rather than building what was asked — found the real root cause, reconciled instead of duplicating, root-caused the node bug; the wave's standout | metrics clean, caught=0 — the reserved-5 now rides on analytical authorship each wave; the rulesets-vs-classic branch-protection probe Nia flagged is a natural follow-up to own. |
| Nia Rossi | Flagship architectural PR that fixed the exact W13 scorer-erasure, verified against live history; clean self-recovery of a local-main slip | 5-ready but blocked by the single reserved-5; the local-main `cd`-to-root slip (now a recorded hazard memory) is the one blemish — avoid it next time and the flagship pattern takes the 5. |
| Ibrahim El-Amin | Correct, dual-deployed S3 + a textbook non-destructive recovery of a wrong-branch commit under a live collision | metrics clean, caught=0; S3 was the lightest story (docs + a counting helper) — to move toward 5, author something architecturally load-bearing or land a real blocking catch. |
| Paloma Gupta | Two genuine mutation-checked reviews from clean isolation; the only engineer who neither authored nor hit an incident — pure steady reviewing | caught=0 across 2 reviews (clean wave, nothing to catch); consider authoring next wave — a reviewer-only wave can't move you off 4. |

## Wave 15 Trust Updates (2026-07-08) — Phase 6 Wave 10: "Harden the installer"

> **2 PRs, 0 changes-requested cycles, 50% top concentration (2 distinct authors), 809 tests. All 4
> reviewer verdicts clean first-pass.** Two file-disjoint installer/harness tech-debt fixes (the deferred
> W8 follow-on). Shipped as **v0.10.2** (patch — internal hardening). `trust_signals score 15`: Paloma
> `difficulty_points=2` (S1, ~195 lines), Ibrahim `difficulty_points=3` (S2, ~258 lines), both delta 0.
> Edit-history catch-crediting did NOT fire again — a clean wave, no amend-in-place catches to credit.
>
> **✅ The two W14 orchestration incidents did NOT recur.** Agents were spawned with DISTINCT names
> (PalomaW10/IbrahimW10/NiaW10/PalomaRevW10/TariqW10) + explicit `isolation: worktree` → no worktree
> collision. Both feature PRs were confirmed 12/12 CI-green (`gh pr view --json statusCheckRollup`) BEFORE
> the gated merge → no red-merge. The W14 process proposals worked as intended.
>
> **One contained incident (Paloma, non-charged):** during an ad-hoc e2e check, a compound Bash command
> interacting with the identity hook (hook blocked the line before its `mkdir` ran; a follow-up `cd` into
> the never-created dir silently failed → subsequent commands ran in the worktree root) caused an errant
> `bootstrap` to clobber `.claude/framework.config.json` and drop install artifacts **inside her isolated
> worktree**. She detected it immediately via `git status`, restored with `git checkout`, removed the stray
> artifacts, and verified the final PR diff was exactly the 2 intended files. Contained to the throwaway
> worktree, never reached the PR — a POSITIVE detection/recovery signal, not a defect.

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Tariq Morales | 5 | **5** | reserved-5 **HELD**. Sole reviewer of BOTH PRs (author-exclusive on neither), and the only reviewer to QA-probe across the whole wave. Mutation-proved every load-bearing guarantee: on S1, rewrote the reconcile as a union and confirmed it FAILS 3 tests (a union would pass the subset oracle while leaving stale garbage — the exact trap); on S2, reverted to pre-#155 skip-on-failure and confirmed BOTH item-1 fingerprint tests fail. Surfaced 2 precise non-blocking tech-debt notes (framework-list reset semantics; a pre-existing bare `KeyError`) without inflating them to blockers. QA rigor that keeps the reserved-5 earned. delta 0, must_fix_received=0, ci_red=0. |
| Ibrahim El-Amin | 4 | **4** | Authored S2 (#241, difficulty 3): all 4 in-scope provisioner items, cleanly — the safety-critical item 1 (after-fingerprint in `finally`, `SourceMutatedError` prioritized, original error not swallowed) verified load-bearing by both reviewers' mutation probes. Correctly deferred item 4 to #101 (documented, not dropped), and flagged the concurrent-agent temp-file collision (switched to uniquely-named files) — good operational awareness. Also renamed a mis-paired test file to satisfy the pairing gate rather than bypass it. delta 0, clean. Held at 4 — solid senior authorship, no blocking catch or flagship-architectural seam to move to 5. |
| Nia Rossi | 4 | **4** | Reviewed S1 (#240), clean `Replied` with real depth — drove an ACTUAL amend over a hand-diverged config (stale entries dropped, canonical order verified, oracle flipped False→True), confirmed user-field preservation field-by-field, and ran the same union-mutation probe independently. TL-grade verification. But a review-only wave (as her own W14 note to Paloma warned) can't move her off 4 — **still 5-ready, now 3 of the last 4 waves at flagship-or-flagship-review caliber without taking the reserved-5.** The rotation tension is now the sharpest standing item. delta 0. |
| Paloma Gupta | 4 | **4** | Authored the flagship S1 (#240, difficulty 2): the amend-reconcile fix — correct converge-on-canonical semantics, idempotent, fail-open, user fields preserved (verified by all three review lenses). ALSO reviewed S2 (#241) with genuine mutation probes (reverted the `finally` block → tests fail; reverted merge→replace → `KeyError`; grepped out all `/home/` literals). Author + substantive cross-review in one wave. The contained worktree incident was caught and cleanly recovered by her own `git status` discipline — no PR impact. delta 0. Held at 4; a blocking catch or a larger architectural seam is the path to 5. |

### Done Well / Needs Improvement (Wave 15 / Phase 6 Wave 10)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Tariq Morales | QA-probed both PRs with real union/finally-removal mutations; kept 2 tech-debt notes appropriately non-blocking; the reserved-5 rode on QA rigor this wave, not authorship | metrics clean, caught=0 (genuinely clean wave); the #243 KeyError follow-up you surfaced is a natural pickup to own end-to-end. |
| Ibrahim El-Amin | Clean 4-item provisioner fix with the safety-critical fingerprint path proven load-bearing; documented the #101 deferral; flagged the temp-collision | to move toward 5, author an architecturally load-bearing seam or land a real blocking catch — S2 was solid-but-scoped hardening. |
| Nia Rossi | TL-grade S1 review with an independent end-to-end amend reproduction + union mutation probe | 5-ready but review-only this wave — as your own W14 guidance said, that can't move you off 4; author or catch next wave and the reserved-5 rotation finally resolves in your favor. |
| Paloma Gupta | Flagship authorship + a genuinely mutation-probed cross-review in the same wave; self-caught and recovered a worktree clobber with zero PR impact | the errant-bootstrap incident traces to a compound `cd`-after-hook-block Bash pattern — tighten e2e scripting (guard `cd` on `mkdir` success, or run e2e in an explicit scratch dir) so a hook-blocked line can't silently redirect later commands. |

## Wave 16 Trust Updates (2026-07-08) — Phase 6 Wave 11 "Harden + Process" → v0.10.3

> **3 PRs, 0 changes-requested cycles, 33% top concentration (3 distinct authors). All 6 reviewer
> verdicts clean first-pass.** Three file-disjoint stories: S1 provisioner/config hardening (#243/#244/#242),
> S2 node-flake root-fix (#234), S3 charter process hardening (#245). Shipped as **v0.10.3** (patch).
> `trust_signals score 16`: every author `delta 0` (one clean PR each — a single clean PR is not a bump).
> No must-fixes existed anywhere in the wave, so no reviewer earned catch-credit (`must_fix_caught=0` across
> the board) — a genuinely clean wave, not a scoring gap.
>
> **✅ Both prior orchestration incident classes stayed designed-out.** Agents spawned with distinct names
> (PalomaW11/IbrahimW11/NiaW11 + TariqRevW11/IbrahimRevW11/PalomaRevW11) + explicit `isolation: worktree` →
> no collision; every PR confirmed CI-green before the gated merge → no red-merge. Notably, **S3 (#247)
> promoted the W14/W15 fixes for these very incidents into the charter** (per-agent scratch namespacing +
> e2e cd/mkdir hygiene), so the operational lessons are now enforced doctrine rather than tribal memory.
>
> **One self-inflicted orchestration slip (orchestrator, non-charged to engineers):** the rollup merged a
> STALE LOCAL wave branch (feature PRs had merged server-side into `origin/…`; the local ref was never
> updated), landing a code-less merge commit (state.json only) on main. Caught immediately by a
> post-merge content probe (`usedNamesFromRoster` = 0 refs on main), corrected with a follow-up merge of
> `origin/deployments/phase6/wave-11` before the version bump/release — no release shipped without the
> code. Lesson: fast-forward the local wave ref (or merge `origin/<wave>` explicitly) at rollup time.

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Tariq Morales | 5 | **5** | reserved-5 **HELD** (incumbent; no decay — decay needs 3 consecutive signal-less waves). Sole QA reviewer on all 3 PRs (author-exclusive on none). Did real verification: proved both #248 fixes revert→red, ran the node suite 5× for determinism, checked charter byte-parity + `charter_drift=[]`, and caught that #242's doc note lists the correct SIX reconciled hook keys where the issue prose said "five". But `must_fix_caught=0` — a clean wave offered no catch to demonstrate rigor beyond clean verification. delta 0. |
| Nia Rossi | 4 | **4** | Authored S3 (#247, difficulty 2) — **finally an author wave, which resolves the W15 "review-only dead end" concern directly**. Clean docs-only charter hardening with verified dual-deploy byte-parity and a correctly-handled stale-manifest checksum (fixed via `install_charter(refresh=True)`, the sanctioned path). But a single clean difficulty-2 PR is not a +1 bump, so the reserved-5 rotation is still unresolved — now less about "she never authors" and more about the mechanical rule that clean-but-small work holds at 4. delta 0. |
| Ibrahim El-Amin | 4 | **4** | Authored S2 (#234, difficulty 3, the meatiest story): root-caused the node flake (dedupe compared role-prefixed filenames, never bare names) + made the RNG seedable, proved determinism (5–15× clean) before removing the `--retry=2` quarantine, and left the load-bearing tests genuinely revert→red. Also cross-reviewed S1 with real revert probes. Solid senior authorship; no blocking catch or architectural seam to move to 5. delta 0. |
| Paloma Gupta | 4 | **4** | Authored the multi-issue S1 (#248, difficulty 2): friendly `MissingFixtureError`, a well-judged default-off opt-in zero-children guard (preserving the legitimate childless smoke-test), and an accurate doc note. Also cross-reviewed S2 with 5× determinism runs + dedupe revert probe. Author + substantive cross-review in one wave, all clean. delta 0; a blocking catch or larger seam is the path to 5. |

### Done Well / Needs Improvement (Wave 16 / Phase 6 Wave 11)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Tariq Morales | QA-verified all 3 PRs with real revert→red / determinism / byte-parity probes; caught the five-vs-six hook-key doc discrepancy; kept 2 findings appropriately non-blocking tech-debt | reviewed 3/3 but `must_fix_caught=0` — a genuinely clean wave (nothing to catch), so the reserved-5 held on clean verification rather than a demonstrated catch this wave. |
| Nia Rossi | Author wave at last (S3) — clean charter hardening with proven dual-deploy parity and a sanctioned manifest-refresh recovery | `prs_merged=1`, difficulty-2 docs work → not a +1 bump; the reserved-5 rotation stays unresolved on the mechanical clean-but-small rule, not on opportunity now. |
| Ibrahim El-Amin | Root-caused the node flake and proved determinism before dropping the CI quarantine; load-bearing tests genuinely revert→red; cross-reviewed S1 with real probes | node flake root-fix was well-scoped hardening, not an architecturally load-bearing seam — author or catch bigger to reach 5. |
| Paloma Gupta | Multi-issue S1 with a well-judged default-off guard + accurate docs; cross-reviewed S2 with 5× determinism runs | `must_fix_received=0` and clean, but no blocking catch or larger architectural seam — the standing path to 5. |

## Wave 17 Trust Updates (2026-07-08) — Phase 6 Wave 12 "Symmetric trust scoring + rollup hygiene" → v0.10.4

> **2 PRs, 0 changes-requested cycles, 50% top concentration (2 distinct authors). All 4 reviewer
> verdicts clean first-pass.** Two file-disjoint stories: S1 made trust scoring **symmetric** (new
> `verified_reviews` positive signal + newly-active `rework_cycles≥2` ding + `must_fix_received` ding
> tightened ≥3→≥2, #254/PR #257), S2 codified the W11 stale-local-branch rollup slip into the charter
> runbook (#255/PR #256). Shipped as **v0.10.4** (patch). `trust_signals score 17`: every engineer
> **delta 0**.
>
> **✅ Debut validation of the signal this very wave shipped.** `verified_reviews` fired correctly and
> *discriminated*: on #257 both reviewers (Nia, Tariq) wrote substantive `Verified:` blocks → each
> credited +1; on #256 both reviewers (Tariq, Paloma) left **empty** `Verified:` blocks → the anti-gaming
> `_has_verified_checks` gate **rejected both** (0 credit). The feature was exercised in both the credit
> and the reject direction on its own introduction wave — the strongest possible dogfood. But each reviewer
> reached only `verified_reviews=1`, below the `≥2` clean-wave bonus threshold, so no bump — correct for a
> small 2-PR wave (a single clean review is not a bump, mirroring the single-clean-PR rule).
>
> **✅ S2 rollup-hygiene step dogfooded during this wave's own rollup.** The escape-hatch merge used
> `git fetch origin` + explicit `git merge --no-ff origin/deployments/phase6/wave-12`, then content-probed
> `main` (`verified_reviews` ×9 + `Rollup pre-flight` present) BEFORE the version bump — no repeat of the
> W11 code-less-merge slip.
>
> **Reserved-5 tension persists mechanically.** The symmetric signal shipped partly to give QA rigor on a
> clean wave a non-zero path, but on a 2-PR wave where reviewers split across the two PRs, each lands at
> `verified_reviews=1` and no delta moves. Tariq holds 5 by incumbency (no decay — needs 3 signal-less
> waves; he has a signal). This is by-design steady-state for a small clean wave, not a scoring gap — but
> the rotation is still unresolved and now waits on a wave large enough (or a reviewer concentrated enough)
> to clear the `≥2` verified-review threshold. New tech-debt #258 (per-(reviewer,PR) dedup) / #259 (tighten
> bare-`determinism` regex) filed against the signal.

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Tariq Morales | 5 | **5** | reserved-5 **HELD** (incumbent; no decay — has a signal: `verified_reviews=1` from a substantive #257 Verified block that also surfaced tech-debt #258/#259). Reviewed both PRs; his #256 review left an empty `Verified:` block (correctly earned 0 credit there). `verified_reviews=1 < 2` bonus threshold, `must_fix_caught=0`. delta 0. |
| Nia Rossi | 4 | **4** | Review-only again this wave: `verified_reviews=1` (substantive #257 Verified block with an independent anti-gaming reasoning trail). The new symmetric signal registered for her — the first wave it *could* — but at 1, below the `≥2` bonus. No authored PR this wave. delta 0; the reserved-5 rotation stays unresolved on the threshold, not on opportunity. |
| Ibrahim El-Amin | 4 | **4** | Authored S2 (#256, difficulty 2): codified the rollup-hygiene runbook step with dual-tree byte-parity and template-rendered charter (`{{default_branch}}` canonical). `prs_merged=1` — a single clean PR is not a +1. His own review verdicts on #256 were clean but with empty Verified blocks (`verified_reviews=0`). delta 0. |
| Paloma Gupta | 4 | **4** | Authored the flagship S1 (#257, difficulty 3, the meatiest story): made scoring symmetric end-to-end (new `verified_reviews` parse + `_has_verified_checks` anti-gaming gate + `rework_cycles≥2` / `must_fix_received≥2` dings + 9 load-bearing tests), and self-recovered a `git checkout` clobber of uncommitted edits during her own revert→red probe with zero PR impact. `prs_merged=1`, not a bump. delta 0; a blocking catch or larger seam remains the path to 5. |

### Done Well / Needs Improvement (Wave 17 / Phase 6 Wave 12)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Tariq Morales | Substantive #257 Verified block (14-case anti-gaming battery reasoning) that also surfaced two real non-blocking tech-debt items (#258/#259) as issues rather than blocking must-fixes | `verified_reviews=1 < 2` and `must_fix_caught=0` — his #256 Verified block was left empty (correctly zero-credit), so only one of his two reviews counted; reserved-5 held on incumbency, not a demonstrated bump. |
| Nia Rossi | First wave the symmetric signal could register for a review-only engineer, and it did (`verified_reviews=1`) with an independent block-scoping reasoning trail | still review-only (`prs_merged=0`); `verified_reviews=1 < 2` bonus threshold → no bump. Author, or concentrate enough substantive reviews to clear `≥2`, to move the reserved-5 rotation. |
| Ibrahim El-Amin | Clean dual-tree charter authorship with template-render parity; dogfoodable rollup-hygiene step that this wave's own rollup then exercised | `prs_merged=1` (not a bump) and his own #256 review Verified blocks were empty (`verified_reviews=0`) — writing a substantive Verified block on reviews would have earned the new positive signal. |
| Paloma Gupta | Shipped the symmetric-scoring feature end-to-end with anti-gaming gate + 9 revert→red tests; self-caught and recovered a `git checkout` clobber with zero PR impact | the clobber traces to using `git checkout -- <file>` during a revert→red probe on a file with *other* uncommitted edits — use an in-memory/patch probe (as she then did) rather than `git checkout` when the working tree carries unstaged work. |

## Wave 18 Trust Updates (2026-07-08) — Phase 6 Wave 13 "Harden the machinery" → v0.10.5

> **3 PRs, 0 changes-requested cycles, 33% top concentration (3 distinct authors). All 6 reviewer
> verdicts clean first-pass.** Three file-disjoint hardening stories: S1 `verified_reviews` per-(reviewer,PR)
> dedup + tightened `_VERIFIED_CHECK_RE` (#258/#259, PR #266), S2 rulesets-aware CI gate (#262, PR #267),
> S3 `require_children` `--real-config` surface + node unparseable-card warn (#251/#252, PR #268). Shipped
> **v0.10.5** (patch). `trust_signals score 18`: **Tariq +1 (earned), everyone else delta 0.**
>
> **🔑 First time the reserved-5 was EARNED by signal, not held by incumbency.** With 3 PRs, reviewers
> spread across the wave: Tariq reviewed #266 + #267 with substantive `Verified:` blocks → `verified_reviews=2`
> → the clean-wave +1 bonus fires (clamped at 5). This is exactly the mechanism the W12 symmetric signal was
> built for, finally exercised at the ≥2 threshold.
>
> **⚠️ BUT the rotation outcome was decided by an arrow glyph — a parser false-negative this wave's own
> scoring exposed (tech-debt #270).** `_VERIFIED_CHECK_RE`'s revert-red alternation `revert\s*(?:→|-+|to)?\s*red`
> matches `revert→red` / `revert-red` / `revert to red` but NOT `revert->red` (the `>` in the ASCII arrow
> breaks it). Both #268 reviewers (Nia, Paloma) wrote genuinely substantive blocks but phrased them
> `Revert->red`, and S3 offered no `determinism`/`byte-parity` fallback token → their real verification earned
> **zero** credit. So **Nia landed at `verified_reviews=1`** (only her #266 block, which used `→`, credited)
> and **Paloma at 0** — NOT a reflection of review rigor. Had Nia's #268 block matched, she'd have hit
> `verified_reviews=2` as a difficulty-3 author and, on composite, likely **taken** the reserved 5. The
> mechanical scores below STAND (evidence-anchored to what the parser credits), but the rotation call this
> wave is glyph-contingent — flagged for the owner pending the #270 fix.
>
> **✅ Every shipped signal-change was dogfooded on its own retro:** the #258 dedup (Tariq's 2 credits are
> across 2 distinct PRs, not double-counted) and the #259 regex both ran live in `score 18`; the S2 rollup
> step content-probed main before bump (PASS).

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Tariq Morales | 5 | **5** | delta **+1** (clamped at 5): `verified_reviews=2` (substantive `Verified:` blocks on #266 AND #267, both using `→`) clears the clean-wave bonus. First time the reserved-5 is EARNED by the symmetric signal rather than held by incumbency. `must_fix_caught=0` (clean wave, nothing to catch). |
| Nia Rossi | 4 | **4** | delta 0 mechanically — BUT glyph-contingent. Authored S2 (#267, difficulty 3) AND did 2 substantive reviews (#266, #268); `verified_reviews=1` only because her #268 block used `->` (uncredited, #270). With the fix she'd be `verified_reviews=2` → +1 → likely the reserved-5 on composite (difficulty-3 author + 2 reviews). Held at 4 on the mechanical count; rotation call deferred to owner pending #270. |
| Paloma Gupta | 4 | **4** | delta 0. Authored S1 (#266, difficulty 2 — the `verified_reviews` dedup + regex tightening itself); `verified_reviews=0` only because her substantive #268 review block used `->` (uncredited, #270), not for lack of rigor. `prs_merged=1` is not a bump regardless. |
| Ibrahim El-Amin | 4 | **4** | delta 0. Authored S3 (#268, difficulty 2) AND reviewed #267 with a substantive `→` block (`verified_reviews=1`, correctly credited — surfaced the non-blocking #269 payload-guard observation). `prs_merged=1` not a bump; `verified_reviews=1 < 2`. |

### Done Well / Needs Improvement (Wave 18 / Phase 6 Wave 13)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Tariq Morales | Two substantive `Verified:` blocks (#266 revert→red battery + #267 full fail-open tri-state audit) → first EARNED reserved-5 via `verified_reviews=2` | `must_fix_caught=0` — a clean wave offered no catch; the 5 rode verified-review rigor, not a demonstrated blocking catch. |
| Nia Rossi | Difficulty-3 S2 authorship + 2 rigorous reviews incl. a merge/round-trip config-plumbing trace on #268 | `verified_reviews=1` ONLY because her #268 block used `->` (parser #270) — as a convention nudge, use `→` (or the fixed parser) so real rigor scores; substantively she reviewed 2 PRs. |
| Paloma Gupta | Authored the `verified_reviews` hardening itself (S1) + a substantive end-to-end sidecar-toggle review on #268 | `verified_reviews=0` is a parser artifact (#270, `->` in her #268 block), not a rigor gap — the #270 fix is hers to consider next. |
| Ibrahim El-Amin | Difficulty-2 S3 author + a correctly-credited substantive #267 review that surfaced real tech-debt (#269) as an issue not a false must-fix | `prs_merged=1` and `verified_reviews=1 < 2` — one authored PR + one review; a second substantive review or a blocking catch is the path up. |

## Wave 21 Trust Updates (2026-07-08) — Phase 6 Wave 16 "Reward the reviewer + clear the gate debt" → v0.11.1

> **2 PRs, 1 changes-requested cycle, 50% top concentration (2 distinct authors). Review-load: Tariq 2/4
> verdicts, Nia 1, Paloma 1.** Two file-disjoint stories: S1 the reserved-5 composite fix itself (#275, PR
> #286) and S2 the docs/refactor load-bearing-test exception (#284, PR #287). Shipped **v0.11.1** (patch).
>
> **🔑 CALIBRATION UN-PARKED — this is the first wave scored under the new composite AND the first with
> deltas APPLIED since W18** (W19/W20 deltas were parked pending the #275 owner decision; that decision —
> "fix the composite, don't widen the scale, un-park from W21" — is now executed). The new composite credits
> `must_fix_caught` + `verified_reviews` at `REVIEW_VALUE_WEIGHT=2` and caps `difficulty_points` at
> `DIFFICULTY_COMPOSITE_CAP=2`. Composites this wave: **Paloma 5, Tariq 4, Nia 2, Ibrahim 1.**
>
> **✅ The fix works as intended — and this is NOT the W20 failure mode.** Under the OLD author-only
> composite Tariq (a pure reviewer this wave) would have scored ~0 and been structurally demoted; the new
> composite lifts him to **4** (2 for catching the #287 bypass + 2 for a substantive verified review on #286).
> The reserved-5 still rotates **Tariq → Paloma**, but Paloma legitimately out-contributed everyone on BOTH
> axes: she caught the #287 bypass as a reviewer AND shipped the hardest clean PR (#286, difficulty 2,
> clean-first-pass). High-value review now *competes* for the 5 instead of being zeroed — exactly the #275
> intent. The rotation is a single-seat mechanical result on a genuinely top wave, not a demotion for cause.
>
> **⚠️ Scoring-hygiene event (worked around live, durable fix filed #288):** Ibrahim's author reply-to-must-fix
> on #287 was initially formatted with reviewer verdict grammar (`Requestor: Ibrahim` / `RequestOrReplied:`),
> so the extractor counted the author as a third reviewer of his own PR and handed him two SPURIOUS reviewer
> signals (`missed_catches=1`, `verified_reviews=1`). The merge gate (`validate_pr_review`) is author-exclusive
> and was NOT fooled — but `trust_signals`/`review_load` are not, an inconsistency. Corrected by amending the
> note to a plain comment (spurious signals → 0, re-verified) BEFORE these deltas were computed; #288 filed to
> give the scorer author-exclusivity parity with the gate. The scores below are on the CLEANED signals.

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Paloma Gupta | 4 | **5** | delta **+1** → **reserved-5 (EARNED, rotated in)**. Authored S1 #286 (difficulty 2, `clean_first_pass=1`, `prs_merged=1`) AND caught the #287 `_patch_is_docs_only` bypass as a reviewer (`must_fix_caught=1`). Composite **5** — top of the wave on both axes (author + reviewer value), strictly above Tariq's 4. This is the reserved-5 the #275 fix was built to make reachable. |
| Tariq Morales | 5 | **4** | delta 0 (signals clean & positive: `must_fix_caught=1` on the #287 bypass, `verified_reviews=1` substantive block on #286). Rotates OFF the reserved-5 by the single-seat discipline — composite **4**, below Paloma's 5. NOT a demotion for cause; under the old composite this would have been ~0, so the #275 fix materially protected his standing (4, not lower). |
| Nia Rossi | 4 | **4** | delta 0. Review-only this wave: `verified_reviews=1` (substantive `Verified:` block on #286), `verified_reviews=1 < 2` bonus threshold, no authored PR. Composite 2. |
| Ibrahim El-Amin | 4 | **3** | delta **−1**: `must_fix_received=2` (the #287 classifier bypass — the same defect raised independently by both reviewers) + `rework_cycles=1`. Authored S2 #287 (difficulty 3); the bypass fix landed clean with revert→red regression tests, but the received must-fix + rework round is the negative signal. `prs_merged=1`. Composite 1. |

### Done Well / Needs Improvement (Wave 21 / Phase 6 Wave 16)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Paloma Gupta | Hybrid top-wave: authored the reserved-5 composite fix itself (S1, difficulty 2) AND caught the #287 bypass as reviewer — the exact review-value the fix now rewards; dogfooded her own feature on this retro | metrics clean: prs_merged=1, must_fix_received=0, ci_red=0, false_positives=0, must_fix_caught=1, verified_reviews=0 (her #287 review carried a must-fix so it earned `must_fix_caught`, not `verified_reviews`). |
| Tariq Morales | Caught the `_patch_is_docs_only` self-close+trailing-code bypass with an executing PoC (`must_fix_caught=1`) + a substantive #286 verified block; carried 2/4 of the review load | metrics clean, but rotates off the reserved-5 — the single seat went to a hybrid author+reviewer; a wave where he both catches a defect AND authors a hard PR is the path back to 5. |
| Nia Rossi | Substantive verified review on #286 with concrete checks | review-only again (`prs_merged=0`), `verified_reviews=1 < 2` bonus threshold — author or concentrate ≥2 substantive reviews to move. |
| Ibrahim El-Amin | Root-caused and fixed the classifier bypass robustly (symmetric across both branches, fail-safe) with revert→red tests; fast, clean scoring-hygiene self-correction on the author-note grammar | `must_fix_received=2` + `rework_cycles=1` (the bypass shipped in the first #287 push and needed a rework round); and the author-note verdict-grammar slip (worked around, #288 filed). |

---

## Wave 22 Trust Updates (2026-07-09) — "Mine the siblings, close the gate-parity debt" → v0.12.0

First retro scored under the **author-exclusive scorer** the wave itself shipped (#288/#292). Review
load came back 6 verdicts across 3 PRs × 2 reviewers with **zero author self-verdicts** — the fix
visible in its own telemetry. Signals via `trust_signals.py extract/score 22`.

> **⚠️ Scoring-engine defect hit live (filed #296, unfixed at retro time):**
> `negative_signal_line()` renders only 4 of the 6 `has_negative()` members — `missed_catches` and
> `gate_bypasses` are omitted — so an engineer whose only negative is a missed catch gets the literal
> line `"Name: "`. `validate_negative_signal_pass()` does not reject a blank-after-colon line either,
> so the forced pass accepts it. Ibrahim's −1 this wave is driven **entirely** by `missed_catches=1`,
> and its receipt came back blank; his negative-signal line below was **hand-written**. Pointedly,
> `gate_bypasses` — the signal this wave's own S3 (#293) made reachable — is equally unreportable.

> **Reserved-5 resolved as a TIE (owner call).** Paloma and Tariq both close at composite **4**
> — Paloma `1 + 2×1 caught + min(3,2) − 1 recv`, Tariq `0 + 2×2 caught`. `apply_distribution_discipline`
> permits every engineer at the max composite to hold 5, and the reserved-5 wording now reads "top
> relative performer(s)" to match — pluralized in #301 after this tie (at retro time it read singular,
> which forced the owner call). Owner seated **both**. This is the author-vs-reviewer parity #275 was
> built to produce: a pure reviewer who caught both of the wave's must-fixes now ranks level with a
> flagship author.

> **Owner override — Ibrahim held at 3.** The mechanical delta was **−1 → 2** (`missed_catches=1`).
> The owner held him at **3**: the missed catch was doc-level (a false prior-art claim), while he
> authored the wave's security fix (#294, difficulty 3) **clean-first-pass** — a positive that
> `has_negative()`'s all-or-nothing gate suppressed entirely. Recorded as an **override, not a
> computed delta**; the suppression rule itself is filed as debt.

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Paloma Gupta | 5 | **5** | delta **0**. Authored S2 #292 (difficulty 3, `prs_merged=1`) and caught the #294 must-fix as reviewer (`must_fix_caught=1`); `must_fix_received=1` + `rework_cycles=1` from her own CR round net it to zero. Composite **4** — tied top. **Holds the reserved 5 on the tie.** |
| Tariq Morales | 4 | **5** | delta **+1** → reserved-5 (EARNED, tie-seated). `must_fix_caught=2` — caught the wave's *only two* durable must-fixes, on #292 (false "mirrors the merge gate" prior-art claim) and #290 (the #881 no-op misclassification) — with zero negatives: `must_fix_received=0`, `rework_cycles=0`, `ci_red_merges=0`, `review_false_positives=0`. Composite **4**, tied top on pure review value with `prs_merged=0`. Carried 3/6 of the review load. |
| Nia Rossi | 4 | **3** | delta **−1**: `must_fix_received=2` + `rework_cycles=1`. Authored S1 #290 (difficulty 2); **both** reviewers independently raised the same durable must-fix — the audit's #1-ranked "P0" (#881) was a no-op — forcing the reclassification in `a244f60`/`98f9a45`. Composite **1**. |
| Ibrahim El-Amin | 3 | **3** | **OWNER OVERRIDE — held.** Mechanical delta **−1 → 2** from `missed_catches=1` (clean verdict on #292 past Tariq's durable must-fix). Offsetting, unscored: authored S3 #294 — the wave's hardest story (difficulty 3, the live self-approval bypass) — with `clean_first_pass=1`, `must_fix_received=0`, `rework_cycles=0`, and both reviewers proving the fix end-to-end through the live gate. `has_negative()` suppressed that clean-first-pass bonus outright. Composite **3**. |

**Distribution health** (`distribution_health([5,5,3,3])`): `degenerate=False`, no reasons — the ledger
is still discriminating (spread 2, both tiers populated). **Retirement triggers:** none fired
(`retirement_trigger` clean for all four; Ibrahim's recent history `[4,3,3]` never reaches `<=2`).
**Decay:** none — every engineer produced signal this wave.

### Done Well / Needs Improvement (Wave 22 / Phase 7 Wave 1)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Tariq Morales | The wave's decisive reviewer: `must_fix_caught=2`, both durable, both on *claims* rather than code — a false prior-art assertion (#292) and a mis-ranked no-op "P0" (#290). Independently re-diffed `92aaaba` against `parse_verdicts` rather than taking the author's word. Reviewed all 3 PRs. | metrics clean: prs_merged=0, must_fix_received=0, ci_red_merges=0, false_positives=0, must_fix_caught=2, verified_reviews=0. Authored nothing this wave — the reserved 5 now rests entirely on review value; `verified_reviews=0` means even his substantive blocks earned `must_fix_caught` instead. |
| Paloma Gupta | Shipped the author-exclusive scorer (#292) and caught the #294 must-fix — value on both axes, second wave running. Her review of #294 probed the adversarial axis (false-exclusion via shared surname) rather than the happy path. | 1 must-fix received, 1 rework cycle(s) — the false "mirrors the merge gate" claim shipped in her first #292 push and needed Tariq to catch it; the doc asserted a property the code did not yet have. |
| Nia Rossi | Produced the Phase-7 mining audit that anchors the next several waves, and accepted the demotion of her own #1-ranked finding on evidence. | 2 must-fix received, 1 rework cycle(s) — the audit's headline "P0" (#881) was a **no-op**, caught independently by *both* reviewers. Verify-before-rank: the finding was ranked #1 without diffing it against `parse_verdicts`. |
| Ibrahim El-Amin | Authored the wave's security fix (#293/#294) clean-first-pass on the hardest story: closed a live self-approval bypass, reused the S2 helper so gate and scorer share **one** exclusion rule, and held the pinned `ReviewState` output shape (#194/#193) by adding keyword-only inputs. | 1 missed catch as reviewer — issued a clean verdict on #292 past the durable must-fix Tariq raised, i.e. approved a doc claim asserting a property the code did not yet have (`missed_catches=1`, `delta=−1`, owner-overridden). `clean_first_pass=1` was suppressed by the `has_negative()` gate. Receipt for this ding came back **blank** from the scorer — see #296. |

## Wave 23 Trust Updates (2026-07-09) — "The record must not lie"

> **⚠️ SCORING PARKED — no deltas applied this wave (owner decision, 2026-07-09; filed #314).**
> The mechanical scorer returned an internally contradictory result. `composite()` — the
> reserved-5 ranking key — subtracts `must_fix_received`, `ci_red_merges` and
> `review_false_positives`, but **not `missed_catches`**, while `score_delta()` charges −1 per
> missed catch. Consequences, both reproduced live on this wave's data:
>
> 1. **Ibrahim ranks first and last simultaneously** — highest composite (**7**) and worst
>    delta (**−2 → 1**, the floor).
> 2. **His composite demotes two others.** `apply_distribution_discipline` caps a proposed 5
>    unless `composite == top`. Ibrahim's 7 is top and he is not proposed a 5, so Paloma (6)
>    and Tariq (6) are both capped **5 → 4** for a *third engineer's* number.
>
> Root cause: `verified_reviews=2` and `missed_catches=2` came from **the same two reviews** —
> Ibrahim's clean verdicts on #307 and #309, each carrying a substantive `Verified:` block, each
> past a defect his co-reviewer caught. `_has_verified_checks` validates that a receipt is
> detailed; it cannot validate that the review worked. The composite pays `+2×2` for the ritual;
> the delta charges `−1×2` for the outcome; the two never reconcile.
>
> Writing `Ibrahim 3→1` and `Paloma/Tariq 5→4` into the permanent ledger would record three
> demotions produced by a defect rather than by conduct — in the wave themed *the record must
> not lie*. **Scores below are the mechanical output, recorded as evidence, NOT applied.**
> Precedent: W15, W20 (scoring parked pending #275).

| Rated | Old | New | Reason (cites signals) |
|-------|-----|-----|------------------------|
| Paloma Gupta | 5 | **5** *(held; mech. 4)* | delta **0**. Authored S1 #306 (`prs_merged=1`, difficulty 3); caught the wave's sharpest defect as reviewer (`must_fix_caught=1`, `verified_reviews=1`) — twice on #307: the `author.login` concentration collapse, then the abort guard that anchored on a GraphQL read failing in lockstep with the read it checked. `must_fix_received=1` + `rework_cycles=1` net to zero. Composite **6**. Mechanically capped 5→4 by Ibrahim's composite 7 — **not applied** (#314). |
| Tariq Morales | 5 | **5** *(held; mech. 4)* | delta **0**. Authored S4 #309 (`prs_merged=1`, difficulty 3); caught the #306 must-fix (`must_fix_caught=1`, `verified_reviews=1`) — `validate_negative_signal_pass` still accepting `"Ibrahim El-Amin: None"`, i.e. #296's failure surviving inside #296's own fix. `must_fix_received=1` + `rework_cycles=1` from the closing keywords in his own commit message net to zero. Composite **6**. Mechanically capped 5→4 by a third engineer's composite — **not applied** (#314). |
| Nia Rossi | 3 | **3** *(parked; mech. 2)* | delta **−1**: `must_fix_received=1`, `rework_cycles=1`, `missed_catches=1`. Authored S2 #307 (difficulty 3); its abort guard cross-checked `extract` against `gh pr list`, which shares the GraphQL bucket `extract` drains — under a pre-exhausted budget both fail together and the guard certifies `0 == 0`. Caught the #309 commit-message closing keywords as reviewer (`must_fix_caught=1`). Composite **6**. Her delta is the one *uncontaminated* by #314 (both negatives are counted in `composite`); parked with the rest for a single coherent ledger entry. |
| Ibrahim El-Amin | 3 | **3** *(parked; mech. 1)* | delta **−2**: `missed_catches=2` — clean verdicts on #307 and #309, each with a substantive `Verified:` block, each past the defect his co-reviewer caught. Offsetting, suppressed by `has_negative()`: authored S3 #305, **the wave's only clean-first-pass PR** (`prs_merged=1`, `clean_first_pass=1`, `must_fix_received=0`, `rework_cycles=0`). Composite **7 — the wave's highest**, inflated by `verified_reviews=2` earned on precisely the two reviews that failed. Second consecutive wave his positives were gated away (cf. Wave 22 owner override). **Not applied** (#314; policy question in #302). |

**Distribution health** (`distribution_health([4,4,2,1])` on the mechanical output): `degenerate=False`,
no reasons. **Retirement triggers:** none fired — `retirement_trigger` clean for all four; Ibrahim's
history `[4,3,1]` never reaches `<=2` in all three. **Decay:** none — every engineer produced signal.
**Reserved 5:** unresolved this wave. The mechanical seat-holder by composite is Ibrahim (7), who is
simultaneously proposed the floor score; the seat is **held by Paloma and Tariq** pending #314.

### Done Well / Needs Improvement (Wave 23)

| Engineer | Done Well | Needs Improvement (forced negative-signal line) |
|----------|-----------|--------------------------------------------------|
| Paloma Gupta | Two catches on one PR, both reproduced against the live API rather than argued. The second — that Nia's abort guard anchored on a read failing in lockstep with the read it checked — required noticing that `gh pr list` and `extract` share one GraphQL bucket, then demonstrating the guard skipping under a genuinely exhausted budget. Refused to clear her block at round 2 when a fix looked plausible but did not fire. | 1 must-fix received, 1 rework cycle(s) — her #306 validator still accepted `"Ibrahim El-Amin: None"`, the exact string #296 exists to ban: `_BARE_NONE_RE` was whole-line-anchored while the emitter only ever produces `"{name}: {gap}"`, so the bare-None branch never fired against real input. |
| Tariq Morales | Caught #296's failure mode surviving inside #296's own fix, with an executing PoC rather than a reading of the regex. Then, told his own commit message carried the defect his PR exists to prevent, amended it message-only and proved the tree byte-identical (`c9e67d5` before and after) so his reviewer's approval remained honest. | 1 must-fix received, 1 rework cycle(s) — commit `73c901a` carried **four** closing keywords, two bound to #296, in the very commit shipping the auto-close guard. It would have auto-closed issue 296 from the wrong commit on rollup. His own hook masks backticks — right for PR bodies (markdown), wrong for commit messages (plain text), which is why his self-check read clean (#312). |
| Nia Rossi | Caught the #309 commit-message closing keywords. Fixed her own guard twice under adversarial review without defending the earlier version, and on the second pass anchored on `gh api rate_limit` — REST, a genuinely orthogonal bucket — rather than another GraphQL read. Ran the revert→red herself. | 1 must-fix received, 1 rework cycle(s), 1 missed catch(es) as reviewer. Her first abort guard's "independent" anchor was not independent; `test_genuinely_empty_wave_proceeds` did not miss the bug, it **encoded it as a requirement**. A passing suite certified the blind spot. |
| Ibrahim El-Amin | The wave's only clean-first-pass PR (#305). Handled its genuinely hard question well: he edited a blockquote inside the *Wave 22* retro section during a wave themed on not rewriting the record, and both reviewers independently reached the same conclusion — the old text made a **present-tense claim about live policy** the PR falsifies, so freezing it would leave the ledger asserting something currently false. He back-annotated, preserved the historical fact, and left `trust_matrix.md:197` byte-untouched. | 2 missed catch(es) as reviewer — clean verdicts on #307 and #309, each carrying a substantive `Verified:` block, each past a real defect his co-reviewer found. The blocks were detailed and the reviews still did not work; `_has_verified_checks` cannot tell the difference, and the composite paid `+4` for them (#314). Verify-the-claim, not the shape: on #309 the closing keywords were in the commit message he had in hand. |
