<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-08 (Phase 6 Wave 10 COMPLETE; v0.10.2 SHIPPED; installer hardened)

> This session was **orientation-only** (session-start + handoff refresh). No code/wave work ran;
> tree is clean and unchanged from the v0.10.2 release. The pickup below carries forward from the
> W10 close-out and is still current.

## ⚠️ READ THIS FIRST — the review gate is LIVE and permanently armed
`.claude/framework.config.json` has `policy.reviewers_required=2` + `policy.pr_review_gate_enabled=true`.
**Every PR needs 2 distinct clean reviewer verdicts (charter `Requestor:` grammar, author-exclusive) and
no unresolved Must-fix, or `gh pr merge`/`gh pr ready` is BLOCKED** by `validate_pr_review`. Operational
rules for running waves (all validated again in W10):
- **Assign 2 distinct reviewers per PR** (author-exclusive); verdicts are charter-grammar PR comments. A
  clean verdict is `RequestOrReplied: Replied` + `Must-fix: None`. A `Request` needs ≥1 `Must-fix:` item.
- **⚠️ CLEARING A `Request` NEEDS AMEND-IN-PLACE** (named step in `pull-requests.md`): the reviewer EDITS
  their original `Request` comment to `Replied`/`Must-fix: None` (`gh api -X PATCH .../issues/comments/<id>`),
  NOT a new comment. As of W9 `trust_signals` credits the resolved catch from comment EDIT-HISTORY, so the
  in-place edit no longer erases `must_fix_caught`.
- **⚠️ CI-GREEN IS ENFORCED AT MERGE** (`validate_pr_ci_status`, live on main since W9). The orchestrator
  must confirm `gh pr view <pr> --json statusCheckRollup` is all-SUCCESS before merging and RE-RUN a
  suspected flake rather than merge through it. (W10: both PRs 12/12 green, no red-merge.)
- **⚠️ ROLLUP→MAIN NEEDS THE ESCAPE HATCH** (named step in `pull-requests.md`): a verdict-less rollup PR
  can't clear the armed gate → land via `git checkout main && git pull`, `git merge --no-ff
  deployments/phase6/wave-N`, commit with `-c` identity, `git push origin main` (direct push is ungated).
  Wrapup/bump/memory/ontology commits are also direct pushes.
- **⚠️ SPAWN WAVE AGENTS WITH DISTINCT NAMES + explicit `isolation: worktree`.** W10 used
  PalomaW10/IbrahimW10/NiaW10/PalomaRevW10/TariqW10 → no collision (the W9 failure did not recur).
- **⚠️ per-agent temp-file namespacing.** The job tmp dir is SHARED across concurrent agents — two W10
  authors clobbered each other's `commitmsg.txt`/`prbody.md`. Instruct every spawned agent to prefix scratch
  files with its own name (`paloma_prbody.md`). Also chain `mkdir -p X && cd X && …` in ad-hoc e2e scripts
  so a hook-blocked line can't silently redirect a later `cd` to the worktree root.

## Pickup (next concrete step)
**Phase 6 Wave 10 is DONE and released. main is at `8f32067` (v0.10.2; ontology + memory committed). Nothing
in flight; tree clean.** Next action is an **owner decision**: pick the next wave/phase theme. **No wave
reserved.** Do NOT start a wave without theme + kickoff approval (gate). Next global wave = **16** (Phase 6
Wave 11); wave branch would be `deployments/phase6/wave-11`; tag `deployments-phase6-wave-11`.

### Candidate next material (owner picks the theme)
- **Small hardening (highest-readiness):** #242 (doc note — amend reconciles framework-owned hook lists to
  canonical), #243 (friendlier error on source-less new-bucket `--real-config` partial patch — pre-existing
  bare `KeyError`), #234 (node RNG seed + name-dedupe root fix, then drop the `vitest --retry` quarantine),
  the **rulesets-vs-classic branch-protection probe** (CI-gate uses the classic protection endpoint;
  rulesets-enforced repos read as unenforced → safe-side over-block).
- **Process (sharpest standing item):** **resolve the reserved-5 rotation** — Nia is flagship-caliber in 3
  of the last 4 waves without ever taking the reserved-5. Plus the two other W15-retro proposals (per-agent
  temp namespacing; guard e2e `cd`).
- **Larger:** **#244** (provisioner item 4 — B10 zero-children guard). **#110** distribute 2real as a Claude
  Code skill (exploratory; likely its own Phase 7). **More #102 P2** (governance charter modules,
  GH-Projects auto).

## Decisions made this session
- None substantive — session was orientation + handoff refresh only. State carried forward from W10.

## Open threads / blockers
- Awaiting owner theme pick for the next wave (Phase 6 Wave 11 / global wave 16). Nothing blocked.

## Mechanical state
- Branch: main (clean), HEAD `8f32067`, in sync with origin/main
- Open PRs: (none)
- Open issues:
  - #244 harness: guard/warn when B10 --include-real runs with zero children (provisioner #155 item 4)
  - #243 harness: friendlier error on source-less new-bucket --real-config partial patch
  - #242 docs(install): note amend reconciles framework-owned hook lists to canonical
  - #234 Node suite flake: generateName dedupe compares role-prefixed filenames, not bare names + unseeded RNG
  - #110 [Explore] Publish/install 2real as a Claude Code skill (no API key, setup inside Claude Code)
  - #102 Implement + test reverse-mapped process improvements from the noorinalabs-main audit
- Lifecycle: no active wave state (pre-first-wave / between waves)
