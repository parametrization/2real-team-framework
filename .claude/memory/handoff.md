<!-- handoff: manual — written by the /handoff skill; the session_handoff auto-hook must not overwrite this file. Delete it (or this line) to re-enable auto-refresh. -->
# Session Handoff — 2026-07-08 (Phase 6 Wave 14 / global wave 19 SHIPPED; v0.10.6; trust scoring PARKED for calibration)

## ⚠️ READ FIRST — trust scoring for W19 is intentionally PARKED
The new symmetric ledger (shipped W19) produced a **degenerate distribution on its first live
wave**. Owner decision (2026-07-08): **hold the scale at 1–5, do NOT broaden yet, watch 2–3 more
waves** (calibration watch **#275**), then decide. Consequences:
- **Standing trust matrix stays at W18 values: Tariq 5, Nia/Paloma/Ibrahim 4.** No W19 deltas
  were written to `trust_matrix.md`, and no W19 `feedback_log.md` retro entry was appended.
- W19's observed deltas + the two findings (scale saturation; pure-reviewer structural demotion
  via `difficulty_points`) are captured as **data-point #1 in issue #275** — the baseline the
  next wave is measured against.
- A range-broadening hotfix (1–5 → 1–10 + composite rebalance + score migration) was **planned
  and then deferred** by the owner. If the next 1–2 waves reproduce compression/reviewer-demotion,
  that's the trigger. Draft plan lives in #275 (re-baseline Tariq 7 / others 6; weight
  `verified_reviews`/`must_fix_caught` ×2; cap `difficulty_points` contribution).

## ⚠️ Review gate is LIVE and permanently armed (unchanged)
`.claude/framework.config.json`: `policy.reviewers_required=2` + `policy.pr_review_gate_enabled=true`.
Every PR needs **2 distinct clean reviewer verdicts** (charter `Requestor:` grammar, author-exclusive)
and no unresolved Must-fix, or `gh pr merge`/`gh pr ready` is BLOCKED by `validate_pr_review`.
- Clean verdict = `RequestOrReplied: Replied` + `Must-fix: None`. `Request` needs ≥1 `Must-fix:`;
  clear by AMEND-IN-PLACE (`gh api -X PATCH …/comments/<id>`).
- A clean review SHOULD carry a substantive `Verified:` block to earn `verified_reviews`. **The
  #270 ASCII-arrow bug is FIXED (W19 S1/#277):** `_VERIFIED_CHECK_RE` now matches `revert->red`
  (ASCII) as well as `revert→red`, plus `N passed`/`ruff clean`/`coverage N%`/`all green`.
- CI-GREEN ENFORCED AT MERGE — confirm `gh pr view <pr> --json statusCheckRollup` all-SUCCESS.
- **ROLLUP→MAIN via ESCAPE HATCH** — `git checkout main && git pull --ff-only`, `git fetch origin`,
  `git merge --no-ff origin/<wave>` (owner `-c` identity + `-F` message), **content-probe main**
  (grep a new symbol) BEFORE bump, `git push`. Wrapup/bump/retro/memory/ontology commits are
  direct pushes.
- **HOOKS + lib WIRED IN PLACE** — `.claude/settings.json` runs `framework/assets/hooks/*` and
  `framework/assets/lib/*` directly; NO `.claude/hooks/` mirror. `reinstall.py` byte-mirrors only
  `skills/`. Edit the canonical file; verify `python3 framework/install/reinstall.py --check` (rc=0).
- Spawn wave agents with DISTINCT names + explicit `isolation: worktree`; prefix scratch with the
  agent name. `gh pr merge --delete-branch` may throw harmless rc=1 while a worktree pins the local
  branch — server merge still succeeds (verify `gh pr view --json state` = MERGED). Prune worktrees
  + delete local branches at wrapup.

## Pickup (next concrete step)
**W19 (Phase 6 Wave 14 / global 19) is SHIPPED: v0.10.6 on main + PyPI + npm; wrapped; worktrees
pruned; meta #271 closed. main at `43575a1`; tree clean.** The only unfinished business is the
PARKED trust decision above. Next action is an **owner decision**: pick the next wave's theme (or
run another wave and let #275 accumulate a second data point). **No wave reserved; next global wave
= 20** (Phase 6 Wave 15); no wave-20 meta stub filed yet. Do NOT start a wave without theme +
kickoff approval.

## What W19 shipped (v0.10.6, "widen the symmetric ledger" — 3 file-disjoint stories, 3 PRs/0 CR/33%)
- **S1 #277** (Paloma): new heuristics H1–H5 in `trust_signals.py` — H1 broadened `_VERIFIED_CHECK_RE`
  (absorbs #270 ASCII-arrow fix + `N passed`/`ruff clean`/`coverage N%`/`all green`); H2
  `clean_first_pass` (+1, difficulty≥2, zero must-fix/rework); H3 graduated dings (−1 @≥2, −2 @≥4);
  H4 `missed_catches` (−1); H5 `gate_bypasses` (−1). Plus `distribution_health()` +
  `apply_distribution_discipline()` (both wired into wave-retro SKILL Step 5). All 6 verdicts clean.
- **S2 #278** (Ibrahim): `2real-team restore` product CLI (`framework/install/restore.py`) — reverses
  archived `.claude/` + `.bak` files, dry-run + consent, non-TTY refuses. `find_latest_archive` moved
  to `repo_space.py`. Follow-ups filed: **#279** (git-native install-branch strategy), **#280** (node
  parity for teardown/restore).
- **S3 #276** (Nia): `_rulesets_enforce_required_checks` `parameters` non-dict guard (fixes #269
  AttributeError → fail-open preserved).

## Open threads / decisions
1. **Calibration (#275)** — parked; watching. Trigger = next 1–2 waves reproduce the pattern.
2. **Next theme** — OPEN. Candidates below.

### Candidate next material (owner picks)
- **Calibration follow-through:** if the pattern holds, execute the #275 broadening plan.
- **W19 follow-ups:** #279 (install-branch restore strategy), #280 (node teardown/restore parity).
- **Backlog:** #264 (re-audit botfarm_inc + noorinalabs-main → #102), #265 (was restore CLI —
  now SHIPPED via #278; verify/close), #110 (distribute 2real as a Claude Code skill), more #102 P2.

## Mechanical state
- Branch: main (clean), HEAD `43575a1`, in sync with origin/main. v0.10.6 live on PyPI + npm.
- Open PRs: none.
- Lifecycle: `current_wave=wave-19`, `last_completed_wave=wave-19`, `global_wave_seq=19`;
  `wave_19_completed_at` set; counters 3/0/33; no wave-20 meta reserved.
- Trust: **Tariq 5, Nia/Paloma/Ibrahim 4** (W18 values HELD — W19 deltas parked pending #275).
- Open issues: #280, #279, #275 (calibration watch), #270 (FIXED in #277 — verify/close), #269
  (FIXED in #276 — verify/close), #264, #110, #102.
