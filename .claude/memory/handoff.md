<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-08 (Phase 6 Wave 15 / global wave 20 SHIPPED; v0.11.0; trust scoring STILL PARKED — decision now actionable)

## ⚠️ READ FIRST — trust scoring is PARKED and the #275 decision is now RIPE
Two live waves have now scored under the symmetric ledger and the calibration watch (**#275**) has
its second data-point. **Owner decision is pending and now actionable:**
- **Standing trust matrix stays at W18 values: Tariq 5, Nia/Paloma/Ibrahim 4.** No W19 or W20 deltas
  were written to `trust_matrix.md`; the W20 feedback-log retro entry records the mechanical result but
  marks it PARKED.
- **W19 (data-point #1):** degenerate/compressed distribution — but that was an all-clean wave.
- **W20 (data-point #2):** distribution is HEALTHY (`[5,5,3,4]`, spread 2, variance 0.69, NOT degenerate).
  So the **scale-broadening trigger did NOT fire** — 1–5 looks granular enough; the W19 compression reads
  as an all-clean-wave artifact. **BUT the reserved-5-composite trigger FIRED (twice now):** the mechanical
  W20 result rotates the reserved-5 from **Tariq (caught the wave's only defect) → Nia (clean author)**,
  purely because the reserved-5 composite is dominated by author-only `difficulty_points`. A pure reviewer
  can never out-composite a clean author, so high-value review work is structurally demoted.
- **Recommendation on #275 (owner decides): do NOT widen the range; instead credit `must_fix_caught` +
  `verified_reviews` in the reserved-5 composite (or cap `difficulty_points`' share)** so a high-value
  reviewer can hold the 5. Full analysis is data-point #2 on **#275** (issuecomment-4919046932).

## ⚠️ Review gate is LIVE and permanently armed (unchanged)
`.claude/framework.config.json`: `policy.reviewers_required=2` + `policy.pr_review_gate_enabled=true`.
Every PR needs **2 distinct clean reviewer verdicts** (charter `Requestor:` grammar, author-exclusive)
and no unresolved Must-fix, or `gh pr merge`/`gh pr ready` is BLOCKED by `validate_pr_review`.
- Clean verdict = `RequestOrReplied: Replied` + `Must-fix: None` + a substantive `Verified:` block (earns
  `verified_reviews`; anti-gaming rejects boilerplate). `Request` needs ≥1 `Must-fix:`; clear by
  AMEND-IN-PLACE (`gh api -X PATCH …/comments/<id>`), never a second verdict comment.
- `_VERIFIED_CHECK_RE` matches `revert->red` (ASCII) + `revert→red` + `N passed`/`ruff clean`/`coverage N%`/`all green`.
- `require_load_bearing_test` HARD-BLOCKS `gh pr create`/`gh pr ready` when a behavior file adds substantive
  lines (INCLUDING docstrings) without a test in the same PR. No docs/refactor exception seeded yet — **#284**
  filed to add one (a W20 docstring-only edit tripped it).
- CI-GREEN ENFORCED AT MERGE — confirm `gh pr view <pr> --json statusCheckRollup` all-SUCCESS.
- **ROLLUP→MAIN via ESCAPE HATCH** — `git checkout main && git pull --ff-only`, `git fetch origin`,
  `git merge --no-ff origin/<wave>` (owner `-c` identity + `-F` message), **content-probe main** (grep a new
  symbol) BEFORE bump, `git push`. Wrapup/bump/retro/memory/ontology commits are direct pushes.
- **HOOKS + lib WIRED IN PLACE** — `.claude/settings.json` runs `framework/assets/hooks/*` and
  `framework/assets/lib/*` directly; NO `.claude/hooks/` mirror. `reinstall.py` byte-mirrors only `skills/`.
- Spawn wave agents with DISTINCT names + explicit `isolation: worktree`; prefix scratch with the agent name.
  `gh pr merge --delete-branch` throws harmless rc=1 while a worktree pins the local branch — server merge
  still succeeds (verify `gh pr view --json state` = MERGED). Prune worktrees + delete local branches at wrapup.

## Pickup (next concrete step)
**W20 (Phase 6 Wave 15 / global 20) is SHIPPED: v0.11.0 on main + PyPI + npm; wrapped; worktrees pruned;
issues #279/#280/#281 closed; release `deployments-phase6-wave-15` cut.** main HEAD after retro commit; tree
should be clean. Next action is an **owner decision**, either:
1. **Resolve #275** (reserved-5 composite fix vs. keep parking vs. broaden) — recommendation above; OR
2. **Pick the Wave 21 theme** (stub **#285** filed, `wave_21_meta_issue` reserved; global wave 21). Do NOT
   start a wave without theme + kickoff approval.
Phase 7 is queued to open with sibling-repo mining (#264/#102) as an exploratory section (owner-deferred).

## What W20 shipped (v0.11.0, "restore-story closeout" — 2 file-disjoint stories, 2 PRs / 1 CR / 50%)
- **S1 #279 / PR #283** (Ibrahim → Paloma + Tariq): `2real-team install-branch` — git-native staged install.
  Creates a throwaway install branch off HEAD, runs the bootstrapper there as one commit; operator `git merge`
  to keep or `git branch -D` to discard. Engine `framework/install/install_branch.py`; bridge
  `stage_install_framework`. Refuses non-git/dirty; composes with manifest restore. **1 CR cycle:** Tariq
  caught that the packaged command passed `install_config=None` (`repo.expect=fresh`) → refused every realistic
  repo; fixed by defaulting `--expect=any` + exposing `--expect`/`--config`, with an end-to-end success test.
- **S2 #280 / PR #282** (Nia → Ibrahim + Tariq): node CLI teardown/restore parity — `uninstall` + `restore`
  bridged to bundled Python (`buildTeardownArgv`/`runTeardown`, `uninstall`/`restore` aliases,
  `describeTeardownDegradation`); `--dry-run`/`--non-interactive` pass through.

## Open threads / decisions
1. **#275 calibration** — decision RIPE (see top). Recommendation: targeted composite fix, not a range widen.
2. **#284** — seed a docs/refactor `load_bearing_test_exceptions` class (W20 flag).
3. **Wave 21 theme** — OPEN (stub #285).

## Mechanical state
- Branch: main, HEAD after the W20 retro/memory/ontology commit; v0.11.0 live on PyPI + npm.
- Open PRs: none.
- Lifecycle: `current_wave=wave-20`, `last_completed_wave=wave-20`, `global_wave_seq=20`,
  `wave_20_completed_at` set; counters 2/1/50 (+ `wave_20_counter_corrections` for the CR-cycle
  measurement conflict); `wave_21_meta_issue=#285` reserved (peek → 21).
- Trust: **Tariq 5, Nia/Paloma/Ibrahim 4** (W18 values HELD — W19+W20 deltas parked pending #275).
- Open issues: #285 (wave-21 stub), #284 (load-bearing exception), #275 (calibration — decision ripe),
  #264 (Phase 7 sibling-repo mining), #110, #102. Housekeeping: large backlog of stale LOCAL feature
  branches from past waves (all merged server-side) — optional cleanup, harmless.
