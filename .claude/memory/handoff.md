<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-08 (Phase 6 Wave 11 COMPLETE; v0.10.3 SHIPPED; harden + process)

## ⚠️ READ THIS FIRST — the review gate is LIVE and permanently armed
`.claude/framework.config.json` has `policy.reviewers_required=2` + `policy.pr_review_gate_enabled=true`.
**Every PR needs 2 distinct clean reviewer verdicts (charter `Requestor:` grammar, author-exclusive) and
no unresolved Must-fix, or `gh pr merge`/`gh pr ready` is BLOCKED** by `validate_pr_review`. Operational
rules (all re-validated in W11):
- **Assign 2 distinct reviewers per PR** (author-exclusive). Clean verdict = `RequestOrReplied: Replied` +
  `Must-fix: None`. A `Request` needs ≥1 `Must-fix:` item; clear it by AMEND-IN-PLACE (edit the original
  comment via `gh api -X PATCH .../issues/comments/<id>`), never a new comment.
- **CI-GREEN IS ENFORCED AT MERGE** — confirm `gh pr view <pr> --json statusCheckRollup` all-SUCCESS and
  re-run a suspected flake rather than merge through it. (W11: all PRs 11–12/12 green.)
- **ROLLUP→MAIN NEEDS THE ESCAPE HATCH** — a verdict-less rollup PR can't clear the armed gate → land via
  `git checkout main && git pull`, `git merge --no-ff <wave-branch>`, `-c` owner identity, `git push`
  (direct push is ungated). Wrapup/bump/retro/memory/ontology commits are also direct pushes.
- **SPAWN WAVE AGENTS WITH DISTINCT NAMES + explicit `isolation: worktree`** (W11 used
  PalomaW11/IbrahimW11/NiaW11 + TariqRevW11/IbrahimRevW11/PalomaRevW11 → no collision). Instruct each agent
  to prefix scratch files with its own name (now CHARTER doctrine via #245 `agents.md`) and chain
  `mkdir -p X && cd X && …` in ad-hoc e2e scripts (also #245, `branching.md`).

## ⚠️ NEW W11 ROLLUP LESSON — don't merge a stale LOCAL wave branch
W11's first rollup merged the LOCAL `deployments/phase6/wave-11` ref, which was NEVER fast-forwarded after
the feature PRs merged into `origin/…` server-side → main got a code-less merge (state.json only). Caught by
a post-merge content probe, fixed with a follow-up merge of `origin/<wave>` before the bump/release.
**At rollup: `git fetch origin` first, then merge `origin/<wave-branch>` explicitly (or `git branch -f
<wave> origin/<wave>`), and VERIFY feature-code is present on the merge parent** (e.g. grep a known new
symbol on `main`) before bumping/releasing. Retro proposal filed to codify this in the rollup runbook.

## Pickup (next concrete step)
**Phase 6 Wave 11 is DONE and released. main is at `52c4a89` (v0.10.3; retro + ontology committed; both
registries published). Nothing in flight; tree clean.** Next action is an **owner decision**: pick the next
wave/phase theme. **No wave reserved.** Next global wave = **17** (Phase 6 Wave 12); wave branch would be
`deployments/phase6/wave-12`; tag `deployments-phase6-wave-12`. A theme-TBD stub is already filed as **#253**
(only the title + Theme line need the owner's edit). Do NOT start a wave without theme + kickoff approval.

### Candidate next material (owner picks the theme)
- **Process (sharpest standing item):** **reserved-5 rotation** — now purely mechanical: giving Nia an
  author wave (W11 S3) removed the "review-only dead end" framing, but a clean difficulty-2 PR still doesn't
  bump, so she holds at 4 while Tariq's 5 rode a catch-less clean wave. Options: rotational-on-streak, split
  author/reviewer-excellence signals, or a "verified-clean-review" positive signal so QA rigor on a clean
  wave isn't zero-credit. Plus the **rollup-hygiene runbook step** (above).
- **Small hardening:** #251 (`real_require_children` CLI/`--real-config` surface — today programmatic-only),
  #252 (`usedNamesFromRoster` warn on unparseable `**Name:**` card), the **rulesets-vs-classic
  branch-protection probe** (CI-gate uses the classic protection endpoint; rulesets-enforced repos read as
  unenforced → safe-side over-block).
- **Larger:** **#110** distribute 2real as a Claude Code skill (exploratory; likely its own Phase 7).
  **More #102 P2** (governance charter modules, GH-Projects auto).

## Decisions made this session
- Owner chose to run **hardening + process as a single wave**; reserved-5 rotation **carried over** (no
  scoring change this wave). Rollup + release **approved** (v0.10.3, tag `deployments-phase6-wave-11`).

## Open threads / blockers
- Awaiting owner theme pick for the next wave (Phase 6 Wave 12 / global 17; stub #253). Nothing blocked.

## Mechanical state
- Branch: main (clean), HEAD `52c4a89`, in sync with origin/main. v0.10.3 live on PyPI + npm.
- Open PRs: (none). Rollup PR #250 served its CI-pass purpose (landed via escape hatch, not its merge button).
- Open issues:
  - #253 Wave 17 — (theme TBD — owner to set) [auto-drafted stub]
  - #252 node: usedNamesFromRoster silently falls back to filename string on unparseable Name field
  - #251 harness: real_require_children guard has no CLI/--real-config surface
  - #110 [Explore] Publish/install 2real as a Claude Code skill
  - #102 Implement + test reverse-mapped process improvements from the noorinalabs-main audit
- Lifecycle: wave 16 wrapped (`wave_16_completed_at` set); `current_wave=wave-16`; wave 17 meta reserved (#253).
- Trust: Tariq 5, Nia/Paloma/Ibrahim 4 (all held; W11 all delta 0).
