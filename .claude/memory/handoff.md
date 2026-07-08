<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-08 (Phase 6 Wave 13 COMPLETE; v0.10.5 SHIPPED; harden the machinery)

## ⚠️ READ THIS FIRST — the review gate is LIVE and permanently armed
`.claude/framework.config.json` has `policy.reviewers_required=2` + `policy.pr_review_gate_enabled=true`.
**Every PR needs 2 distinct clean reviewer verdicts (charter `Requestor:` grammar, author-exclusive) and
no unresolved Must-fix, or `gh pr merge`/`gh pr ready` is BLOCKED** by `validate_pr_review`. All re-validated
in W13:
- **Assign 2 distinct reviewers per PR** (author-exclusive). Clean verdict = `RequestOrReplied: Replied` +
  `Must-fix: None`. A `Request` needs ≥1 `Must-fix:`; clear by AMEND-IN-PLACE (`gh api -X PATCH …/comments/<id>`).
- **A clean review SHOULD carry a substantive `Verified:` block** to earn `verified_reviews`. ⚠️ **W13 lesson
  (#270): write `revert→red` with the UNICODE arrow `→`, NOT `revert->red` (ASCII).** `_VERIFIED_CHECK_RE`
  matches `→`/`-`/`to` but the `>` in `->` breaks the match, so an ASCII-arrow block scores ZERO. Two W13
  reviewers lost all credit this way and it glyph-decided the reserved-5 rotation. Fix is filed (#270, HIGH).
- **CI-GREEN ENFORCED AT MERGE** — confirm `gh pr view <pr> --json statusCheckRollup` all-SUCCESS.
- **ROLLUP→MAIN via ESCAPE HATCH** — `git checkout main && git pull`, `git fetch origin`,
  `git merge --no-ff origin/<wave-branch>` (NEVER a stale LOCAL ref), **content-probe main** (grep a new
  symbol) BEFORE bump, `git push`. Wrapup/bump/retro/memory/ontology commits are direct pushes. (Charter
  doctrine #255. Dogfooded clean in W13.)
- **HOOKS ARE WIRED IN PLACE** (W13 S2 finding): `.claude/settings.json` runs `framework/assets/hooks/*`
  directly — there is NO `.claude/hooks/` mirror. `reinstall.py` only byte-mirrors `skills/`. Editing a
  hook = edit the canonical file; verify with `python3 framework/install/reinstall.py --check` (rc=0). Do
  NOT create a `.claude/hooks/` copy (it would be an unwired duplicate). `lib/` is likewise single-source.
- **SPAWN WAVE AGENTS WITH DISTINCT NAMES + explicit `isolation: worktree`** (W13 used PalomaW18/NiaW18/
  IbrahimW18 authors + per-(reviewer,PR) reviewer agents). Prefix scratch with the agent name (#245). Note:
  `gh pr merge --delete-branch` throws a harmless rc=1 when a worktree still pins the local branch — the
  SERVER-side merge still succeeds; verify with `gh pr view <pr> --json state` = MERGED. Prune worktrees +
  delete local branches at wrapup.

## Pickup (next concrete step)
**Phase 6 Wave 13 is DONE, released, and RETRO'd. main is at `446c7c6` (v0.10.5; retro + ontology committed;
both registries published). Nothing in flight; tree clean.** Next action is an **owner decision**: pick the
next wave/phase theme. **No wave reserved.** Next global wave = **19** (Phase 6 Wave 14); wave branch
`deployments/phase6/wave-14`; tag `deployments-phase6-wave-14`. Theme-TBD stub filed as **#271**.
Do NOT start a wave without theme + kickoff approval.

### Two open owner decisions from W13
1. **W18 reserved-5 call (#270-contingent):** mechanically Tariq EARNED the 5 (`verified_reviews=2`) and Nia
   held 4 — but ONLY because Nia's (and Paloma's) substantive #268 review blocks used `revert->red` (ASCII)
   and scored zero. With #270 fixed, Nia (diff-3 author + 2 real reviews) would likely have taken the 5 on
   composite. Owner: accept the mechanical result (let the fixed parser govern from W19), or treat W18's
   rotation as a tie pending #270.
2. **Next theme.**

### Candidate next material (owner picks the theme)
- **Signal/scoring hardening (freshest, owed to W13):** **#270** (HIGH — `_VERIFIED_CHECK_RE` accept `->`
  + load-bearing `revert->red` test), **#269** (rulesets `parameters` non-dict guard, small), and the retro
  proposal to **broaden the `Verified:` credited-token set** (`N passed` / `ruff clean` so suite evidence
  counts, not only named-probe vocabulary).
- **Backlog filed this session:** **#264** (re-audit `botfarm_inc` + `noorinalabs-main` (+ children) for the
  last week's learnings → fold into #102), **#265** (surface a `2real-team restore` product CLI command —
  `repo_space.py` already has `restore_assets`+manifest [#108] but it's not on the product CLI, and its
  contract is "managed assets," not "pristine recovery").
- **Larger:** **#110** distribute 2real as a Claude Code skill (likely Phase 7). **More #102 P2** (governance
  charter modules, GH-Projects auto).

## Decisions made this session
- Owner picked **themes 1+2 combined** ("harden the machinery") → ran as 3 file-disjoint stories. Rollup +
  release **approved** (v0.10.5, tag `deployments-phase6-wave-13`). Also filed two backlog issues (#264, #265)
  mid-wave at owner request.

## Open threads / blockers
- Two owner decisions above (W18 reserved-5, next theme). Nothing blocked.

## Mechanical state
- Branch: main (clean), HEAD `446c7c6`, in sync with origin/main. v0.10.5 live on PyPI + npm.
- Open PRs: (none). All 3 W13 feature PRs merged to the wave branch; rollup landed via escape hatch (probe PASS).
- Open issues:
  - #271 Wave 19 — (theme TBD — owner to set) [auto-drafted stub]
  - #270 trust: `_VERIFIED_CHECK_RE` misses `revert->red` ASCII arrow [HIGH — distorted W18 scoring]
  - #269 harden: rulesets probe `parameters` non-dict guard [non-blocking]
  - #265 [feat] `2real-team restore` product CLI command (pre-install recovery)
  - #264 [audit] re-audit botfarm_inc + noorinalabs-main for last-week learnings → #102
  - #110 [Explore] Publish/install 2real as a Claude Code skill
  - #102 reverse-mapped process improvements from the noorinalabs-main audit
- Lifecycle: wave 18 wrapped (`wave_18_completed_at` set); `current_wave=wave-18`, `last_completed_wave=wave-18`,
  `global_wave_seq=18`; wave 19 meta reserved (#271).
- Trust: **Tariq 5** (EARNED W18 via verified_reviews=2), **Nia/Paloma/Ibrahim 4** (all held; W18 delta 0,
  glyph-contingent for Nia/Paloma — see #270).
