<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-08 (Phase 6 Wave 10 COMPLETE; v0.10.2 SHIPPED; installer hardened)

## ⚠️ READ THIS FIRST — the review gate is LIVE and permanently armed
`.claude/framework.config.json` has `policy.reviewers_required=2` + `policy.pr_review_gate_enabled=true`.
**Every PR needs 2 distinct clean reviewer verdicts (charter `Requestor:` grammar, author-exclusive) and
no unresolved Must-fix, or `gh pr merge`/`gh pr ready` is BLOCKED** by `validate_pr_review`. Operational
rules for running waves (all validated again this wave):
- **Assign 2 distinct reviewers per PR** (author-exclusive); verdicts are charter-grammar PR comments. A
  clean verdict is `RequestOrReplied: Replied` + `Must-fix: None`. A `Request` needs ≥1 `Must-fix:` item.
- **⚠️ CLEARING A `Request` NEEDS AMEND-IN-PLACE** (named step in `pull-requests.md`): the reviewer EDITS
  their original `Request` comment to `Replied`/`Must-fix: None` (`gh api -X PATCH .../issues/comments/<id>`),
  NOT a new comment. As of W9 `trust_signals` credits the resolved catch from comment EDIT-HISTORY, so the
  in-place edit no longer erases `must_fix_caught`. (No catches this wave — both PRs clean first-pass.)
- **⚠️ CI-GREEN IS ENFORCED AT MERGE** (`validate_pr_ci_status`, live on main since W9). Still: the
  orchestrator must confirm `gh pr view <pr> --json statusCheckRollup` is all-SUCCESS before merging and
  RE-RUN a suspected flake rather than merge through it. **W10 did this — both PRs 12/12 green, no red-merge.**
- **⚠️ ROLLUP→MAIN NEEDS THE ESCAPE HATCH** (named step in `pull-requests.md`): a verdict-less rollup PR
  can't clear the armed gate → land via `git checkout main && git pull`, `git merge --no-ff
  deployments/phase6/wave-N`, commit with `-c` identity, `git push origin main` (direct push is ungated).
  Wrapup/bump/memory/ontology commits are also direct pushes.
- **⚠️ SPAWN WAVE AGENTS WITH DISTINCT NAMES + explicit `isolation: worktree`.** W10 used
  PalomaW10/IbrahimW10/NiaW10/PalomaRevW10/TariqW10 → **no collision** (the W9 failure did not recur).
- **⚠️ NEW (W10): per-agent temp-file namespacing.** The job tmp dir is SHARED across concurrent agents —
  two W10 authors clobbered each other's `commitmsg.txt`/`prbody.md`. Instruct every spawned agent to
  prefix scratch files with its own name (`paloma_prbody.md`). Also: in ad-hoc e2e scripts, chain
  `mkdir -p X && cd X && …` so a hook-blocked line can't silently redirect a later `cd` to the worktree root
  (a contained W10 incident — an errant bootstrap ran in Paloma's worktree root, caught + recovered, no PR
  impact).

## Pickup (next concrete step)
**Phase 6 Wave 10 is DONE and released. main is at `d979da2` (v0.10.2, ontology refreshed). Nothing in
flight; tree clean.** Next action is an **owner decision**: pick the next wave/phase theme. **No wave
reserved.** Do NOT start a wave without theme + kickoff approval (gate). Next global wave = **16** (Phase 6
Wave 11); wave branch would be `deployments/phase6/wave-11`; tag `deployments-phase6-wave-11`.

### Candidate next material (owner picks the theme)
- **Small hardening follow-ups (highest-readiness, tightly scoped):** #242 (doc note — amend reconciles
  framework-owned hook lists to canonical), #243 (friendlier error on source-less new-bucket `--real-config`
  partial patch — pre-existing bare `KeyError`), #234 (node RNG seed + name-dedupe root fix, then drop the
  `vitest --retry` quarantine), the **rulesets-vs-classic branch-protection probe** (the CI-gate uses the
  classic protection endpoint; rulesets-enforced repos read as unenforced → safe-side over-block).
- **Process:** the three W15-retro proposals (per-agent temp namespacing; guard e2e `cd`; **resolve the
  reserved-5 rotation** — Nia is flagship-caliber 3 of the last 4 waves without taking the 5). The rotation
  call is the sharpest standing item.
- **Larger:** #101 (noorinalabs meta+children run — owns provisioner item 4, the B10 zero-children guard).
  **#110** distribute 2real as a Claude Code skill (exploratory; likely its own Phase 7). **More #102 P2**
  (governance charter modules, GH-Projects automation).

## What shipped this session — Phase 6 Wave 10 → v0.10.2
Rollup direct-push merge **`69e7ca6`**; bump **`2585ae8`** (0.10.1→0.10.2, PATCH — internal installer/harness
hardening); wrapup **`8fa9f2c`**; ontology **`d979da2`**. Release **v0.10.2** OIDC-published. Tag
`deployments-phase6-wave-10`. Meta **#237** + stories **#238/#239** closed (source tech-debt #162/#155 also
closed). **2 PRs, 0 CR cycles, 50% concentration, 809 tests, all 4 verdicts clean first-pass.** See
[[project_framework_extraction_state]].
- **S1 #238/PR#240 (Paloma → Nia + Tariq):** amend path reconciles (not unions) config hook module-lists
  onto the canonical set — the keep-&-amend `write_config(force=False)` was skipping an existing config, so
  diverged lists survived and `m_config_module_lists_complete` failed. `reconcile_module_lists()` +
  `_RECONCILED_HOOK_LISTS` in `framework/install/bootstrap.py`. Idempotent, fail-open, user fields preserved.
- **S2 #239/PR#241 (Ibrahim → Paloma + Tariq):** real-repo provisioner hardening 4/5 in
  `framework/harness/real_provision.py` — partial-clone fingerprint-on-failure (try/finally,
  `SourceMutatedError` prioritized), de-hardcoded fixtures, merge-not-replace `--real-config`, nested-child
  `mkdir(parents=True)`. Item 4 (B10 zero-children) → #101. Test file renamed to `test_real_provision.py`.

## Team / trust — reserved-5 HELD (Tariq); Nia 5-ready (rotation tension)
- `score 15`: Paloma difficulty=2 / Ibrahim difficulty=3, both delta 0; clean wave, edit-history crediting
  did not fire. **Tariq 5→5** (reserved HELD — sole reviewer of BOTH PRs; mutation-proved a union fails S1's
  oracle and removing S2's `finally` fails its tests). **Nia 4→4** (5-READY; TL-grade S1 review with an
  independent end-to-end amend reproduction — but review-only can't move her off 4; **flagship-caliber 3 of
  the last 4 waves without the 5**). **Paloma 4→4** (flagship S1 author + mutation-probed S2 review).
  **Ibrahim 4→4** (clean S2). trust_matrix.md + feedback_log.md Wave 15 sections committed (`8fa9f2c`).
- **Both W14 orchestration incidents designed out.** Two contained minor W10 incidents (Paloma worktree
  bootstrap-clobber, recovered no-PR-impact; concurrent-agent temp collision) → proposals logged.

## Mechanical state
- Branch: **main** @ `d979da2` (clean; ontology refresh committed).
- Release **v0.10.2** live (verify: `gh release view v0.10.2`; npm `latest`=0.10.2; PyPI `/0.10.2/json`=200
  — all confirmed this session). Open PRs: none. Wave branch `deployments/phase6/wave-10` + both feature
  branches merged & deleted (remote); `deployments-phase6-wave-10` tag preserves the ref. Orchestrator
  worktree `.claude/worktrees/nia-review-s2` (detached) may still be listed — harmless.
- Open issues: **#242**/**#243** (new W10 tech-debt) · **#234** (node RNG) · **#101** (meta+children;
  owns provisioner item 4) · **#102** (more P2) · exploratory **#110**.
- Lifecycle: `last_completed_wave=wave-15` (phase 6, wave-branch, pr=2, cr_cycles=0, concentration=50);
  `current_wave=wave-15`; **no wave reserved**; next allocate = **wave 16** (theme TBD).
