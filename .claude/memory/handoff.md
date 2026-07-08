<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-08 (Phase 6 Wave 12 COMPLETE; v0.10.4 SHIPPED; symmetric trust scoring + rollup hygiene)

## ⚠️ READ THIS FIRST — the review gate is LIVE and permanently armed
`.claude/framework.config.json` has `policy.reviewers_required=2` + `policy.pr_review_gate_enabled=true`.
**Every PR needs 2 distinct clean reviewer verdicts (charter `Requestor:` grammar, author-exclusive) and
no unresolved Must-fix, or `gh pr merge`/`gh pr ready` is BLOCKED** by `validate_pr_review`. Operational
rules (all re-validated in W12):
- **Assign 2 distinct reviewers per PR** (author-exclusive). Clean verdict = `RequestOrReplied: Replied` +
  `Must-fix: None`. A `Request` needs ≥1 `Must-fix:` item; clear it by AMEND-IN-PLACE (edit the original
  comment via `gh api -X PATCH .../issues/comments/<id>`), never a new comment.
- **NEW in W12 — a clean review SHOULD carry a substantive `Verified:` block** (concrete checks:
  revert→red / determinism Nx / byte-parity / "CI rollup SUCCESS"). That now earns the `verified_reviews`
  positive signal. An EMPTY/boilerplate `Verified:` block earns **0** (anti-gaming `_has_verified_checks`
  gate). Retro proposal #1 (populate-by-default) is filed but NOT yet applied to the charter.
- **CI-GREEN IS ENFORCED AT MERGE** — confirm `gh pr view <pr> --json statusCheckRollup` all-SUCCESS and
  re-run a suspected flake rather than merge through it.
- **ROLLUP→MAIN NEEDS THE ESCAPE HATCH** — a verdict-less rollup PR can't clear the armed gate → land via
  `git checkout main && git pull`, **`git fetch origin`, `git merge --no-ff origin/<wave-branch>`** (NEVER
  the stale LOCAL ref — see below), `-c` owner identity, then **verify feature-code on the merge parent**
  (grep a known new symbol on `main`), `git push` (direct push is ungated). Wrapup/bump/retro/memory/
  ontology commits are also direct pushes. **This runbook step is now CHARTER doctrine (#255, W12 S2).**
- **SPAWN WAVE AGENTS WITH DISTINCT NAMES + explicit `isolation: worktree`** (W12 used
  PalomaW17/IbrahimW17 + NiaRevW17/TariqRevW17/PalomaRevW17 → no collision). Per-agent scratch-file name
  prefix + chained `mkdir -p X && cd X && …` in ad-hoc e2e are CHARTER doctrine (#245).

## Pickup (next concrete step)
**Phase 6 Wave 12 is DONE, released, and RETRO'd. main is at `7acc7bd` (v0.10.4; retro + ontology committed;
both registries published). Nothing in flight; tree clean.** Next action is an **owner decision**: pick the
next wave/phase theme. **No wave reserved.** Next global wave = **18** (Phase 6 Wave 13); wave branch would be
`deployments/phase6/wave-13`; tag `deployments-phase6-wave-13`. A theme-TBD stub is already filed as **#260**
(only the title + Theme line need the owner's edit). Do NOT start a wave without theme + kickoff approval.

### Candidate next material (owner picks the theme)
- **Signal hardening (freshest — owed to the W12 feature):** **#258** (per-(reviewer,PR) `verified_reviews`
  dedup so two clean Verified comments on ONE PR can't double-count) + **#259** (drop the bare `determinism`
  / `ci green` alternation in `_VERIFIED_CHECK_RE` so a negating/non-substantive mention can't satisfy the
  gate). Small, well-scoped; both filed at W12 ship.
- **Process (standing):** **reserved-5 rotation** — now *threshold-bound*: the symmetric `verified_reviews`
  signal is live, but a review-only engineer needs ≥2 substantive Verified reviews on a wave to bump; on a
  2-PR wave reviewers split and each lands at 1. Owner-scoped: adjust threshold, concentrate substantive
  reviews via roster assignment, or leave as steady-state. Plus retro proposal #1 (charter nudge to populate
  `Verified:` blocks by default).
- **Small hardening:** the **rulesets-vs-classic branch-protection probe** (CI-gate uses the classic
  protection endpoint; rulesets-enforced repos read as unenforced → safe-side over-block); #251
  (`real_require_children` CLI/`--real-config` surface), #252 (`usedNamesFromRoster` warn on unparseable
  `**Name:**` card).
- **Larger:** **#110** distribute 2real as a Claude Code skill (exploratory; likely its own Phase 7).
  **More #102 P2** (governance charter modules, GH-Projects auto).

## Decisions made this session
- Owner chose **option (3)** for the reserved-5 question — a "verified-clean-review" positive signal — but
  required it be **SYMMETRIC**: downward signals (PR rework, must-fixes, failing tests/pipeline) must
  counter-balance the upward one. Delivered: `verified_reviews` +1 AND `rework_cycles≥2` −1 (newly active) +
  `must_fix_received` ding tightened ≥3→≥2. Ran hardening (S2 rollup runbook) in the same wave. Rollup +
  release **approved** (v0.10.4, tag `deployments-phase6-wave-12`).

## Open threads / blockers
- Awaiting owner theme pick for the next wave (Phase 6 Wave 13 / global 18; stub #260). Nothing blocked.

## Mechanical state
- Branch: main (clean), HEAD `7acc7bd`, in sync with origin/main. v0.10.4 live on PyPI + npm.
- Open PRs: (none). Rollup landed via escape hatch (explicit `origin/<wave>` merge + content-probe PASS).
- Open issues:
  - #260 Wave 18 — (theme TBD — owner to set) [auto-drafted stub]
  - #259 trust: tighten `_VERIFIED_CHECK_RE` bare `determinism`/`ci green` alternation
  - #258 trust: `verified_reviews` lacks per-(reviewer,PR) dedup
  - #253 Wave 17 meta (served W12; close if still open)
  - #252 node: usedNamesFromRoster silently falls back to filename string on unparseable Name field
  - #251 harness: real_require_children guard has no CLI/--real-config surface
  - #110 [Explore] Publish/install 2real as a Claude Code skill
  - #102 Implement + test reverse-mapped process improvements from the noorinalabs-main audit
- Lifecycle: wave 17 wrapped (`wave_17_completed_at` set); `current_wave=wave-17`, `last_completed_wave=wave-17`,
  `global_wave_seq=17`; wave 18 meta reserved (#260).
- Trust: Tariq 5, Nia/Paloma/Ibrahim 4 (all HELD; W17 all delta 0). Reserved-5 now threshold-bound.
