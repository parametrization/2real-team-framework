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
