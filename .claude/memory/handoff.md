<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-05 (Phase 4 planned; Phase 3 retro backfilled)

## Pickup (next concrete step)
**Phase 4 is planned and on the tracker — next step is `/wave-start` for Wave 1** (approval-gated;
do not start a wave without the user's go-ahead). Theme = **"self-hosting & quality machinery"**
(doc: `.claude/team/phases/phase-4.md`).
- **Wave 1 (foundational machinery):** #100 (Ibrahim, phase-aware `branch.integration`), #98
  (Paloma, `trust_signals.py` verdict-vocab fix), #111 (Tariq, port `validate_review_comment_format`),
  #99 (Nia, dogfood `lifecycle.py` into /wave-start + /wave-end).
- **Wave 2 (last wave → tech-debt floor):** #94, #90, #77, #82, #74, #75.
All 11 labeled `phase-4` + assignee; six-perspective review notes posted on #98/#111/#99/#74/#75.

**Also possible next:** commit this session's artifacts (see Open threads) if the user wants them
to survive; or start the deferred exploratory backlog (#101–#110).

## Decisions made this session
- **Phase 4 theme = self-hosting & quality machinery** (user pick over review-gate tranche /
  pure tech-debt / full-roadmap). Review-gate tranche stays deferred; #111 pulls only the
  comment-format validator from it.
- **Phase 3 modeled as ONE tracked wave** (global wave 1) for the retro — all 13 PRs merged to
  the single `deployments/phase3/wave-1` branch, so per-wave split is impossible retroactively.
  Merge model recorded as **wave-branch** (config still says `direct-to-main` → that's #94).
- **Trust deltas are provisional**: the scoring engine read all review signals as zero (vocab
  mismatch #98), so deltas came from a manual `Must-fix:` tally. Re-score authoritatively once
  #98 lands. Only Nia +1→4; Ibrahim/Paloma/Tariq flat at 3.
- **New exploratory backlog left unscheduled/unassigned** (user: "plan for them later").
- **Not committing** this session's work (user said proceed without committing).
- npm secret rotation confirmed DONE by user.

## Open threads / blockers
- ⚠️ **Uncommitted working-tree changes** (9 dirty entries): `.claude/state.json` (new, backfilled),
  `.claude/framework.config.json` (added `branch.integration`/`labels` — the `branch.integration`
  value is **phase-3-specific**, a retro-extraction stopgap that #100 is meant to fix; revisit
  before committing), `.claude/team/feedback_log.md` + `trust_matrix.md` (Wave 1 retro entry,
  provisional), `.claude/team/phases/phase-4.md` (new), `.claude/memory/handoff.md`, and
  regenerated `ontology/structural/{code-graph.json,llms.txt}` (post-file hook). `.claude/worktrees/`
  untracked. Nothing committed; `main` still @ `9100ff7`.
- **Exploratory backlog #101–#110** has no phase/assignee yet — needs a future `/plan-phase`.
  Cross-links: A2→A1(#101); B2→B1→B3 (#103/#104/#105); D2(#107)↔E1(#108) share consent/backup
  pattern; C1(#109) is the real-repo acceptance test for E1's archive/restore.
- No CI/blocker issues. v0.4.0 live on both registries.

## Background (prior session, condensed)
Phase 3 shipped **v0.4.0** (installer overhaul: unified `install.config.yaml`, meta/child modes,
ontology-at-install, Node CLI bridge, skills 5→13, dispatcher Agent/Stop routing) via rollup
PR #97 → main; released + published OIDC on PyPI + npm. The 12 shipped wave issues (#64–#70, #73,
#85–#88) were closed this session via `/wave-audit` (tagged `fixed-in-phase3-wave-1`).

## Mechanical state
- Branch: **main** @ `9100ff7` (9 uncommitted entries — see Open threads); `deployments/phase3/wave-1` retained @ `4085a3f`
- Latest release: **v0.4.0** (target `6605da8`), live on PyPI + npm; repo holds zero Actions secrets (fully OIDC)
- Open PRs: (none)
- Open issues: **20** — Phase 4 (11: #74 #75 #77 #82 #90 #94 #98 #99 #100 #111; waves in phase-4.md) + unscheduled backlog (10: #101–#110)
- Lifecycle: `state.json` present — last_completed_wave=wave-1 (phase 3, wave-branch, 13 PRs, cr_cycles=4, concentration=38%); `global_wave_seq=1`, so next allocate = wave 2
