---
name: wave-wrapup
description: Finalize a wave — PR review, merge sequencing, issue cleanup, worktree cleanup, and handoff to retro
args: team_name, Phase number, Wave number
---

Finalize a wave by reviewing all open PRs, merging in dependency order, closing resolved issues, and cleaning up. This is the **exit gate** before running `/wave-retro`.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Wave Lifecycle for the canonical skill order and preconditions.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## Instructions

### 1. Inventory open PRs

List all PRs targeting the wave's deployment branch:

```bash
gh pr list --state open --base "deployments/phase-{P}/wave-{M}" --json number,title,author,headRefName,reviews,isDraft,createdAt
```

Also check for PRs targeting `main` that belong to this wave (by label or branch pattern):

```bash
# Canonical label is the phase-agnostic `wave-{X}` (#810); legacy
# `p{N}-wave-{M}` is grandfathered — query both forms.
gh pr list --state open --base main --label "wave-{M}" --json number,title,author,headRefName,reviews
gh pr list --state open --base main --label "p{P}-wave-{M}" --json number,title,author,headRefName,reviews
```

### 2. Check CI status for each PR

For each open PR:

```bash
gh pr checks {NUMBER} --json name,conclusion,status
```

Classify each PR:
| Status | Criteria | Action |
|--------|----------|--------|
| **Ready** | CI green, has peer review | Merge |
| **Needs review** | CI green, no peer review | Request review |
| **CI failing** | CI red | Fix before merge |
| **Draft** | Marked as draft | Exclude (report only) |
| **Blocked** | Has unmerged dependency | Defer until dependency merges |

### 3. Determine merge order

Build a merge dependency graph:
- Parse PR bodies for `Depends on #N` or `After #N` references
- Check if any PR modifies files that another PR also modifies (merge conflict risk)
- Independent PRs can merge in parallel; dependent PRs merge in order

Present the proposed merge sequence:

```
**Merge Sequence: Phase {P} Wave {M}**

| Order | PR | Title | Status | Dependencies | Action |
|-------|-----|-------|--------|--------------|--------|
| 1     | #N  | ...   | Ready  | None         | Merge  |
| 2     | #N  | ...   | Ready  | After #M     | Merge  |
| —     | #N  | ...   | CI failing | — | Fix first |
| —     | #N  | ...   | Draft  | — | Skip |
```

**Do NOT merge any PRs until the user approves the sequence.**

### 4. Review each ready PR

For each PR marked "Ready", perform a review using charter format (same as `/review-pr`):

```bash
gh pr diff {NUMBER}
```

Post review comment:

```
Requestor: {Reviewer.Name}
Requestee: {PR author}
RequestOrReplied: Request

**Review: {LGTM or issues}**
Must-fix: {list or "None"}
Tech-debt: {list or "None"}
```

For each tech-debt item, create a GitHub Issue labeled `tech-debt` and the next wave/phase label.

If must-fix items are found, do NOT merge — report and wait for fixes.

### 5. Merge approved PRs

After user approval, merge in the determined order:

```bash
gh pr merge {NUMBER} --merge --delete-branch
```

After each merge, verify:
- CI passes on the target branch
- No merge conflicts introduced for subsequent PRs

If a merge introduces CI failures, stop and report before continuing.

### 6. Close resolved issues

Run `/wave-audit` logic to close issues resolved by the merged PRs:

```bash
# For each merged PR, check for Closes/Fixes/Resolves references
gh pr view {NUMBER} --json body
```

Close referenced issues with audit comments. Also check for issues matched by branch naming convention.

### 7. Verify completeness

Check that all wave issues are resolved:

```bash
gh issue list --state open --label "wave-{M}" --json number,title
gh issue list --state open --label "p{P}-wave-{M}" --json number,title  # grandfathered
```

For any remaining open issues:
- If the work was deferred, move to the next wave label
- If the work was partially done, document what remains
- Report all unresolved items

### 8. Clean up worktrees (mandatory)

**All wave worktrees MUST be removed before the wrapup is considered complete.** Stale worktrees accumulate across waves and cause branch contention.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
# Prune any stale worktree metadata
git -C "$REPO_ROOT" worktree prune

# List all worktrees and identify wave-related ones
git -C "$REPO_ROOT" worktree list

# Remove each wave worktree (branches matching wave assignees)
# Example: git -C "$REPO_ROOT" worktree remove "$REPO_ROOT/.claude/worktrees/W.Mwangi+0063-fix-branch-freshness-worktree" --force
```

For each worktree:
1. Check if it has uncommitted changes (`git -C <path> status --porcelain`)
2. If clean, remove with `git worktree remove <path>`
3. If dirty, report to the user — do NOT force-remove without approval
4. Delete the remote tracking branch if the PR was merged: `git push origin --delete <branch>` — **feature/worktree branches only; NEVER delete a `deployments/phase-*/wave-*` branch** (wave branches are retained permanently per owner directive 2026-06-09 — see Step 11).

Report what was cleaned:
```
**Worktree Cleanup:**
- Removed: {count} worktrees
- Skipped (dirty): {count}
- Remote branches deleted: {count}
```

**Why:** Phase 2 Wave 1 left 6 stale worktrees after merge because cleanup wasn't enforced.

### 9. Update documentation

Check if any merged PRs affect documentation:

```bash
# List files changed across all merged PRs
for pr in {merged_pr_numbers}; do
    gh pr diff "$pr" --name-only
done
```

Flag any changes to:
- API endpoints (update API docs)
- Configuration files (update deployment docs)
- Architecture (update diagrams)
- Charter or process files (note for retro)

### 9.5. Retro PR body-vs-diff sanity check (added P3W9 #414 — 2026-05-13)

Per `charter/pull-requests.md § Retro PR Body-vs-Diff Discipline` (Skill enforcement clause): if a retro PR for this wave is already open, every charter/skill/trust-matrix file claimed in its PR body MUST appear in the PR's diff. Direct-to-main commits for ratified retro outputs are forbidden — they bypass the two-reviewer gate and `validate_pr_ci_status`, and break the audit trail.

Run this check before emitting the Step 10 wrapup table so any mismatch surfaces in the table itself:

```bash
# Discover the open retro PR for this wave (if any).
# Retro PRs are conventionally titled `retro(P{P}W{M}…)`.
RETRO_PR=$(gh pr list --repo noorinalabs/noorinalabs-main --state open \
  --search 'retro( in:title' \
  --json number,title \
  --jq ".[] | select(.title | test(\"retro\\\\(P{P}W{M}\")) | .number" | head -1)

if [ -z "$RETRO_PR" ]; then
  echo "No open retro PR for P{P}W{M} — skipping body-vs-diff check."
else
  gh pr view "$RETRO_PR" --repo noorinalabs/noorinalabs-main --json files --jq '[.files[].path] | sort' > /tmp/retro_${RETRO_PR}_diff.json
  gh pr view "$RETRO_PR" --repo noorinalabs/noorinalabs-main --json body --jq '.body' > /tmp/retro_${RETRO_PR}_body.md

  # Manually inspect /tmp/retro_${RETRO_PR}_body.md's "Files changed" section and
  # compare each claimed path against /tmp/retro_${RETRO_PR}_diff.json. For each
  # path claimed in the body but missing from the diff JSON, ABORT with a clear
  # "body claims X not in diff" error and surface the mismatch in the Step 10
  # wrapup table. Do NOT proceed to Step 10 until the retro author either
  # commits the missing file to the retro branch (preferred) or amends the body
  # to remove the unsupported claim.
fi
```

Worked example of the failure mode this catches: PR [#124](https://github.com/noorinalabs/noorinalabs-main/pull/124) (W8 retro) body claimed 7 files, diff contained 2 (`feedback_log.md` + `ontology/checksums.json`); the other 5 (`trust_matrix.md`, `charter/pull-requests.md`, `charter/hooks.md`, `skills/wave-retro/SKILL.md`, `skills/wave-kickoff/SKILL.md`) were committed direct-to-main as `2b92605` + `ecd1c76`, bypassing review and CI. The check above would have flagged all 5 missing paths and blocked Step 10 emission until the retro PR was fixed. Filed as [#126](https://github.com/noorinalabs/noorinalabs-main/issues/126); skill-side mirror filed as [#414](https://github.com/noorinalabs/noorinalabs-main/issues/414).

This step mirrors `/wave-retro` Step 6.5 by design — the same check fires from both skills so a body-vs-diff mismatch is caught whether the operator runs `/wave-retro` first (post-author check before requesting reviewers) or `/wave-wrapup` after the retro PR is open (pre-wrapup-table check). The two skills converge on the authoritative shape in `charter/pull-requests.md § Retro PR Body-vs-Diff Discipline`.

### 10. Final wave report

```
**Wave Wrapup: Phase {P} Wave {M}**

**PRs:**
- Merged: {count}
- Deferred: {count} (moved to next wave)
- Still failing CI: {count}

**Issues:**
- Closed: {count}
- Remaining open: {count} (deferred)

**Tech-debt created:** {count} new issues

**Staging promotion:** {success | failure | deferred (criterion #1 not yet live) | overridden: <rationale>} {run URL if any}

**Documentation:** {docs updated | docs need update | no doc changes}

**Worktrees cleaned:** {count}

**Next step:** Run `/wave-retro` for full retrospective with assessments and trust updates.
```

### 10.5. Write canonical counter keys to `cross-repo-status.json`

> **High-volume remote-merge checkpoint (added P3W13 #566 — 2026-05-31).** Before the **first local bookkeeping commit** of the wrapup (the counter-key write below, the ontology rebuild commit, the wrap-marker commit), if this wave merged **N ≥ 10 PRs via `gh` against remote branches**, the local checkout may be many commits behind origin. Re-sync first:
>
> ```bash
> REPO_ROOT="$(git rev-parse --show-toplevel)"
> CUR_BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
> git -C "$REPO_ROOT" fetch --quiet origin "$CUR_BRANCH"
> BEHIND=$(git -C "$REPO_ROOT" rev-list --count "HEAD..origin/$CUR_BRANCH" 2>/dev/null || echo 0)
> if [ "${BEHIND:-0}" -gt 0 ]; then
>   echo "Local is $BEHIND behind origin/$CUR_BRANCH — re-syncing before bookkeeping commit."
>   # Stash/relocate any in-progress local edits FIRST (a hard reset discards them).
>   git -C "$REPO_ROOT" reset --hard "origin/$CUR_BRANCH"
> fi
> ```
>
> **Why:** P3W13 merged 37 PRs remotely while the local parent sat 22 commits behind; the counter-key commit landed on a stale tree and needed a recovery `reset --hard` that discarded uncommitted session state (`.claude/annunaki/errors.jsonl`). Re-syncing **before** the first bookkeeping write — and relocating any local edits first, since the reset is destructive — prevents both the stale-tree commit and the lossy recovery. Origin > local clone for all wrap-time state (charter `pull-requests.md § Origin > Local Clone`).

Write the **top-level** canonical counter keys that `/wave-retro` Step 2.5 verifies. Pre-#318 these were either missing or buried under `wave_{M}_summary.*`, which forced a manual followup commit at retro (P3W7 `fb459b2`). Post-#318 the skill writes them at wrapup time so retro reads cleanly.

Use the shared `upsert_status_keys.py` helper at `.claude/lib/` — it does targeted text-level upsert that preserves the compact-inline shape of `cross-repo-status.json` (a naive `jq … > tmp && mv` reformats every compact line to pretty form, producing a 500-line cosmetic diff per wave — see `main#332`). The helper also validates JSON before AND after the rewrite. Promoted from `/wave-scope` to `.claude/lib/` per `main#292` (multi-consumer → shared lib).

> **Mechanical computation (added P3W10 #421 — 2026-05-13).** Pre-#421 the
> `CHANGES_REQUESTED_CYCLES` and `TOP_CONCENTRATION_PCT` placeholders here
> were filled in by hand by the orchestrator; the resulting null/wrong
> values had to be recomputed at retro for 3 consecutive waves (W4 80%,
> W5 6→4, W9 null+null). The mechanical computation below eliminates the
> recompute pattern by deriving both counters directly from the merged-PR
> set across `wave_{M}_repos_in_scope`. `FINAL_PR_COUNT` remains the
> already-computed Step 10 "PRs: Merged" number.
>
> **Cross-window filter (added P3W10 #423 — 2026-05-13).** When a wave-branch
> is reused across partition events (W9 split mid-wave into pre-partition
> non-deploy PRs + post-partition canonical 6 PRs — owner directive
> 2026-05-12), `gh pr list --base "deployments/phase-{P}/wave-{M}"` returns
> the union of ALL windows, not the canonical wave's window. W9 actuals:
> 30 PRs returned vs 6 canonical → TOP_CONCENTRATION_PCT computed as 50%
> against the cross-window set vs 67% canonical. The fix below uses
> `wave_{M}_kicked_off_at` as a `mergedAt >= X` filter to scope the PR set
> to the canonical window (Option A), plus a `FINAL_PR_COUNT`-vs-tally
> cross-check that loud-fails on residual mismatch (Option B — defense in
> depth for re-roll-within-window edge cases A misses).

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
STATUS="$REPO_ROOT/cross-repo-status.json"

# Counters are computed by the deterministic helper (main#688). It replaces the
# hand-rolled bash that used to live here, which collapsed under zsh: a
# `for R in $WAVE_REPOS_IN_SCOPE` loop does NOT word-split a parameter in zsh
# (this org's shell — `feedback_zsh_shell_environment`), so the whole repo list
# was passed to `gh` as one bogus `--repo` value → "Could not resolve
# repository" → merged PR count 0 → division-by-zero. The helper issues every
# `gh` call as `subprocess.run([...])` with an explicit arg list (no shell, no
# word-split), applies the `wave_{M}_kicked_off_at` cross-window filter
# (Option A — #423), and computes final_pr_count / changes_requested_cycles /
# top_concentration_pct.
#
#   --expect {count_of_merged_PRs}  is the Option-B cross-check: loud-fail
#     (exit 1, NO write) if the tallied PR count != Step 10's "PRs: Merged".
#   --write                         upserts the three canonical top-level keys
#     via upsert_status_keys.py, preserving the compact-inline file shape.
python3 "$REPO_ROOT/.claude/lib/wave_status.py" counters {P} {M} \
    --expect {count_of_merged_PRs} --write

# Read-back verify (memory `feedback_gh_pr_edit_silent_noop` family — any
# upsert pipeline that silently fails produces zero diff but exit 0).
jq -r --arg m "{M}" '
  "wave_" + $m + "_final_pr_count = " + (.["wave_" + $m + "_final_pr_count"] | tostring),
  "wave_" + $m + "_changes_requested_cycles = " + (.["wave_" + $m + "_changes_requested_cycles"] | tostring),
  "wave_" + $m + "_top_concentration_pct = " + (.["wave_" + $m + "_top_concentration_pct"] | tostring)
' "$STATUS"
```

Optionally also write a richer `wave_{M}_summary` block with wave-shape detail (per-tier PR breakdown, charter-change proposals, thesis text — see P3W7 `cross-repo-status.json` for the canonical shape). Top-level keys above remain **authoritative** for `/wave-retro` Step 2.5; the summary block is a supplementary surface for retro-prose composition.

**Why top-level not nested:** `/wave-retro` Step 2.5 reads via `jq -r ".wave_${M}_final_pr_count"` — a direct top-level lookup. Nesting under `wave_{M}_summary.final_pr_count` would require Step 2.5 changes per wave-counter-key, breaking the canonical-key contract. Top-level keeps the read-side simple.

**Acceptance for /wave-retro Step 2.5:**
- All three keys exist at top-level after `/wave-wrapup` completes.
- Values match the rendered Step 10 wave report.
- A `wave_{M}_summary` block, if also present, must not contradict the top-level values (top-level is authoritative).

If a key cannot be computed (e.g., no PRs merged this wave), write the literal `0` — `/wave-retro` Step 2.5 distinguishes "0 cycles" from "key missing" and only the latter is treated as drift.

### 10.6. Per-engineer trust signals (added P6W17 #842 — Option B §4b)

The wave-level counters above describe the *wave*; the trust matrix needs the same evidence broken down **per engineer**. Extract the countable per-engineer signals from the merged-PR set so `/wave-retro` applies mechanical, evidence-anchored trust deltas instead of narrative self-grading. The signals are: `prs_merged`, `must_fix_received` (author), `must_fix_caught` (reviewer), `ci_red_merges`, `rework_cycles`, `review_false_positives`. The helper reuses `wave_status.merged_prs` (so the #423 cross-window filter and the no-shell list-arg-vector contract of main#688 carry over) and parses each PR's verdict comments for the `Requestor:` / `RequestOrReplied:` shape.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
# Per-engineer signal JSON, persisted as a single top-level key so /wave-retro
# Step 4 reads deterministic numbers rather than re-deriving them by hand.
SIGNALS=$(python3 "$REPO_ROOT/.claude/lib/trust_signals.py" extract {P} {M})
python3 "$REPO_ROOT/.claude/lib/upsert_status_keys.py" "$REPO_ROOT/cross-repo-status.json" \
    "wave_{M}_trust_signals=$SIGNALS"

# Read-back verify (gh silent-no-op family) — the block must be present and parse.
jq -e --arg m "{M}" '.["wave_" + $m + "_trust_signals"]' "$REPO_ROOT/cross-repo-status.json" >/dev/null \
    && echo "trust signals written" || echo "ERROR: trust signals not written"
```

**Acceptance:** `wave_{M}_trust_signals` exists at top-level after wrapup, mapping each active engineer to their integer signal counts. `/wave-retro` Step 4 consumes it; if absent, retro re-extracts it directly (the helper is idempotent and reads from the same merged-PR set).

### 10.7. Child structural-index pre-regen — BEFORE the wave→main PRs (added P7W19 retro)

The structural-ontology `staleness-check` only gates PRs to **main**, NOT wave-branch PRs. So a per-issue PR that added a tracked source file (`.py`/`.cypher`/`.ts`/`.tsx`) without regenerating that child's structural index passes its own wave-branch CI but **reddens the wave→main PR** the moment Step 11 opens it — a fix-forward scramble mid-wrapup. Caught in P7W19: da#218 added `queries/validation/sanadset_orphan_inventory.cypher` and the wave→main PR (da#222) went red on staleness-check until the index was regenerated (`b84b478`).

Close it pre-emptively: for each child repo in `wave_{M}_repos_in_scope` (i.e. excluding `noorinalabs-main`, whose index is handled by Step 12b), regenerate the child's structural index from the wave-branch HEAD and commit any diff to the wave branch BEFORE opening the integration PR, so the wave→main PR is green on staleness-check from the start.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
BRANCH="deployments/phase-{P}/wave-{M}"
while IFS= read -r R; do
  [ "$R" = "noorinalabs-main" ] && continue
  CHILD="$REPO_ROOT/$R"
  [ -d "$CHILD" ] || { echo "$R: not checked out locally — regenerate manually if it added tracked source"; continue; }
  # Child generator fetches ontology_gen from noorinalabs-main; regenerate in place.
  ( cd "$CHILD" \
    && git fetch --quiet origin "$BRANCH" && git checkout --quiet "$BRANCH" && git pull --ff-only --quiet origin "$BRANCH" \
    && python3 scripts/structural_ontology.py emit --gen-lib "$REPO_ROOT/.claude/lib" \
    && if ! git diff --quiet -- ontology/structural/; then
         git add ontology/structural/ \
         && git -c user.name="Aino Virtanen" -c user.email="parametrization+Aino.Virtanen@gmail.com" \
              commit -m "ontology(structural): regenerate $R index pre-wave-merge ({P}W{M})" \
         && git push origin "$BRANCH" \
         && echo "$R: structural index regenerated + pushed"
       else echo "$R: structural index already current"; fi )
done <<< "$(jq -r ".wave_{M}_repos_in_scope[]" "$REPO_ROOT/cross-repo-status.json")"
```

This is the child analog of Step 12b (which regenerates the **parent** index). Run it here, before Step 11, not at 12b — by Step 12 the integration PRs are already open and would have already gone red. If a child repo is not checked out locally, surface it so the operator regenerates manually (or accepts the Step-11 fix-forward for that one repo). Source: memory `feedback_wave_branch_merge_not_squash` § Related child-repo wrap gotcha (P7W19 #222).

### 11. Merge to main per repo (every wave)

**Every wave's wrapup merges its wave branch to main** (changed 2026-06-09 — owner directive; previously gated to the final wave only). Each repo in `wave_{M}_repos_in_scope` has its OWN `deployments/phase-{P}/wave-{M}` branch (created by `/wave-kickoff` step 1) that needs its own PR to main. This is the symmetric counterpart of the multi-repo branch creation gap (main#238). Merging each wave keeps `main` continuously current: the next wave bases off main (`/wave-start` § 3 base determination; ref cut by `/wave-kickoff` Step 1), so an unmerged wave would strand its work the moment the following wave starts.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
WAVE_REPOS_IN_SCOPE=$(jq -r ".wave_{M}_repos_in_scope[]" "$REPO_ROOT/cross-repo-status.json")
BRANCH="deployments/phase-{P}/wave-{M}"

# zsh-safe iteration: a here-string into `while IFS= read -r` (NOT
# `for R in $WAVE_REPOS_IN_SCOPE` — zsh does not word-split a parameter, so the
# whole list would collapse into one bogus repo; main#688). The here-string
# keeps the loop in the current shell — relevant for the array-accumulating
# loops below.
while IFS= read -r R; do
  # Skip repos where the wave branch is already merged or doesn't exist
  EXISTING=$(gh api "repos/noorinalabs/$R/git/refs/heads/$BRANCH" --jq '.object.sha' 2>/dev/null || true)
  [ -z "$EXISTING" ] && { echo "$R: no wave branch — skip"; continue; }

  # Check if there's anything to merge (compare branch HEAD vs main HEAD)
  MAIN_SHA=$(gh api "repos/noorinalabs/$R/git/refs/heads/main" --jq '.object.sha')
  if [ "$EXISTING" = "$MAIN_SHA" ]; then
    echo "$R: wave branch ==  main, nothing to merge"; continue
  fi

  # Create PR from this repo's wave branch to its own main
  gh pr create --repo "noorinalabs/$R" --base main --head "$BRANCH" \
    --title "Phase {P} Wave {M} → main ($R)" \
    --body "Final wave merge for $R. All PRs reviewed and merged to wave branch."
done <<< "$WAVE_REPOS_IN_SCOPE"
```

Print a per-repo PR summary table (PR# or "no merge needed") and **wait for user approval before merging any PR**. Each PR must be merged independently.

**Do NOT merge to main without user approval.** This is a significant action that affects all downstream repos.

**Retain the wave branch — do NOT delete it on merge** (owner directive 2026-06-09). Merge each wave→main PR with `gh pr merge <N> --merge` (**never** `--delete-branch`); the `deployments/phase-{P}/wave-{M}` branches are kept permanently as a historical / rollback anchor for every wave. Caveat: if a repo has "Automatically delete head branches" enabled at the repo level, a merge deletes the head branch regardless of the flag — for these repos, either disable that setting or restore the branch immediately after merge (`git push origin <wave-sha>:refs/heads/deployments/phase-{P}/wave-{M}`).

### 11.5. Reachability gate — wave-branch propagation to main (every wave)

After the per-repo wave→main PRs in Step 11 are merged (or declared not-needed), verify each wave-branch is actually reachable from `origin/main`. This is the load-bearing enforcement counterpart to charter `state-claims.md § Sub-rule: merge_commit_sha reachability` — the rule's claim-time discipline becomes a wrapup-time gate.

Origin story: `main#339` — `deployments/phase-3/wave-7` ended up 10 ahead / 15+ behind / diverged from main with no wave→main PR ever opened. The wave was treated as "closed" because individual PRs into the wave-branch were merged, but the wave-branch itself never reached main. PR #305 (the `validate_commit_identity` backslash fix) and 11 hook fixtures sat stranded on a branch no operator was tracking.

This step catches that pattern at wrapup time, before the wave is declared closed.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
WAVE_REPOS_IN_SCOPE=$(jq -r ".wave_{M}_repos_in_scope[]" "$REPO_ROOT/cross-repo-status.json")
BRANCH="deployments/phase-{P}/wave-{M}"

STRANDED=()
# zsh-safe iteration via here-string into `while read` (main#688). The
# here-string (NOT a `| while` pipe) keeps the loop in the current shell so the
# STRANDED array survives past `done`.
while IFS= read -r R; do
  # Skip repos where the wave branch doesn't exist (scope-drop case)
  WAVE_SHA=$(gh api "repos/noorinalabs/$R/git/refs/heads/$BRANCH" --jq '.object.sha' 2>/dev/null || true)
  [ -z "$WAVE_SHA" ] && { echo "$R: no wave branch — skip (scope-drop)"; continue; }

  # Compare wave-branch against main at origin (NOT local clone — per charter
  # pull-requests.md § Origin > Local Clone)
  COMPARE=$(gh api "repos/noorinalabs/$R/compare/main...$BRANCH" \
    --jq '{ahead_by, behind_by, status}')
  AHEAD=$(echo "$COMPARE" | jq -r .ahead_by)
  STATUS=$(echo "$COMPARE" | jq -r .status)

  if [ "$AHEAD" -gt 0 ] || [ "$STATUS" = "diverged" ]; then
    # Check if a wave→main PR exists in any state — explains the gap if so
    PR_EXISTS=$(gh pr list --repo "noorinalabs/$R" --base main --head "$BRANCH" \
      --state all --limit 5 --json number,state,mergedAt \
      --jq '[.[] | select(.state == "MERGED" or .state == "OPEN")] | length')
    STRANDED+=("$R: ahead_by=$AHEAD status=$STATUS wave→main PRs found=$PR_EXISTS")
  else
    echo "$R: wave-branch reachable from main (ahead_by=$AHEAD, status=$STATUS) — OK"
  fi
done <<< "$WAVE_REPOS_IN_SCOPE"

if [ ${#STRANDED[@]} -gt 0 ]; then
  echo "════════════════════════════════════════════════════════════"
  echo "BLOCKED: /wave-wrapup cannot close wave {M} — STRANDED repos:"
  for s in "${STRANDED[@]}"; do echo "  $s"; done
  echo ""
  echo "Each STRANDED repo has wave-branch commits NOT reachable from origin/main."
  echo "Fix-forward options:"
  echo "  (a) Open the wave→main PR (re-run Step 11 if no PR exists)"
  echo "  (b) Merge an already-OPEN wave→main PR"
  echo "  (c) If stranding is INTENTIONAL (descoped wave, rolled-back work), set"
  echo "      STRANDING_OVERRIDE_RATIONALE=\"<explicit reason>\" before re-invoking"
  echo "      /wave-wrapup. The override is logged to the wrapup report and to"
  echo "      cross-repo-status.json under wave_{M}_stranding_override."
  echo "════════════════════════════════════════════════════════════"
  exit 1
fi
```

**Override mechanism** (when stranding is intentional):

```bash
# Only use when the wave is deliberately not merged to main
# (descoped, rolled back, or held for sequencing reasons)
export STRANDING_OVERRIDE_RATIONALE="P3W7 work descoped post-#339 audit; \
  wave-7 branch retained for historical reference, no propagation intended"
# Re-invoke /wave-wrapup — the gate sees the rationale, logs it, and proceeds
```

The override is intentionally noisy: rationale is required (no empty string), logged to the wrapup report, and persisted to `cross-repo-status.json` under `wave_{M}_stranding_override` so subsequent /wave-retro and audit passes can surface it.

### 11.5a. Deployable-merge verification gate — post-merge workflows went green (every wave)

A wave→main merge is a **deployable merge**: it triggers push-to-main workflows that **never ran on the per-issue PRs** (publish/Trivy, schema-drift, structural-ontology, …). Their CI gives **no pre-merge signal**, so a wave can be reachable-on-main (Step 11.5 green) yet have reddened `main` post-merge. This is exactly how `isnad-graph#1131` (libexpat `CVE-2026-45186`) slipped past `#1130`'s green PR and failed the GHCR publish on `main` (main#864).

After Step 11.5 confirms reachability, verify each repo's wave→main merge commit actually went green across its post-merge-only workflows, using the deterministic oracle `.claude/lib/verify_deployable_merge.py` (it polls the Actions runs for the exact merge SHA; a failed run, or a required workflow that produced **no** run at all, is a hard not-verified — the same empty-is-not-ready discipline as `pr_ci_state.py`). `gh pr merge` returns 0 the instant the merge commit exists — long before these workflows even start — so the merge's own exit status proves nothing.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
WAVE_REPOS_IN_SCOPE=$(jq -r ".wave_{M}_repos_in_scope[]" "$REPO_ROOT/cross-repo-status.json")
BRANCH="deployments/phase-{P}/wave-{M}"

UNVERIFIED=()
while IFS= read -r R; do
  # The deployable merge commit is origin/main's HEAD for the repo after Step 11
  # merged the wave→main PR. Resolve it at origin (not the local clone).
  MAIN_SHA=$(gh api "repos/noorinalabs/$R/git/refs/heads/main" --jq '.object.sha' 2>/dev/null || true)
  [ -z "$MAIN_SHA" ] && { echo "$R: cannot read main — skip"; continue; }

  # --require-deployable verifies the post-merge-ONLY workflows (push/tag AND not
  # pull_request) — the genuinely blind ones. Drop the flag to verify every
  # merge-triggered workflow. The no-red safety net fails on ANY run that
  # executed for the SHA and went red, so path-filtered workflows that fired are
  # still covered. Exit codes: 0 = verified (incl. "nothing required" + no red),
  # 1 = NOT verified (a red or silently-dropped required run), 2 = UNDETERMINED
  # (gh/API failure — cannot tell, so surface and treat as blocking).
  python3 "$REPO_ROOT/.claude/lib/verify_deployable_merge.py" \
    "noorinalabs/$R" "$MAIN_SHA" --require-deployable --timeout 1200 --poll 30
  case $? in
    0) echo "$R: deployable merge verified green @ ${MAIN_SHA:0:8}" ;;
    1) UNVERIFIED+=("$R @ ${MAIN_SHA:0:8} — a post-merge workflow failed / was dropped") ;;
    2) UNVERIFIED+=("$R @ ${MAIN_SHA:0:8} — UNDETERMINED (gh/API error; re-run or investigate)") ;;
  esac
done <<< "$WAVE_REPOS_IN_SCOPE"

if [ ${#UNVERIFIED[@]} -gt 0 ]; then
  echo "════════════════════════════════════════════════════════════"
  echo "BLOCKED: /wave-wrapup cannot close wave {M} — deployable merge NOT verified:"
  for u in "${UNVERIFIED[@]}"; do echo "  $u"; done
  echo ""
  echo "A post-merge workflow failed (or never ran) on main after the wave→main merge."
  echo "This is a RED main gate — a stop, not a speed bump (charter no-force-merge)."
  echo "Fix-forward options:"
  echo "  (a) Fix the regression on main via a normal bug→PR→merge cycle (e.g. a"
  echo "      base-image CVE re-pin like isnad-graph#1132), then re-run /wave-wrapup."
  echo "  (b) If the failure is a documented external/standing item (advisory-DB"
  echo "      drift, a no-fix base-image CVE under an active --ignore-vuln), set"
  echo "      DEPLOYABLE_VERIFY_OVERRIDE_RATIONALE=\"<reason + tracking issue>\" and"
  echo "      re-invoke. The override is logged to the report and to"
  echo "      cross-repo-status.json under wave_{M}_deployable_verify_override."
  echo "════════════════════════════════════════════════════════════"
  [ -z "${DEPLOYABLE_VERIFY_OVERRIDE_RATIONALE:-}" ] && exit 1
  echo "OVERRIDDEN: $DEPLOYABLE_VERIFY_OVERRIDE_RATIONALE"
fi
```

A genuinely external red (e.g. a newly-published advisory the fix has not yet propagated for — `feedback_pip_audit_strict_advisory_db_drift`, `feedback_trivy_base_image_cve_org_wide_gate`) is the only case for the override, and it MUST name a tracking issue. A red caused by the wave's own change is fixed forward — never overridden. Include the per-repo result in the Step 10 report; `/wave-retro` records it in the wave history row.

### 11.6. Staging-promotion gate (Phase-3 end-state criterion #3)

A wave is **not closeable until its merged code has been promoted to staging green**. This is the wrapup-time enforcement of Phase-3 end-state criterion #3 (`main#325`) and the charter rule `pull-requests.md § Wave-Wrapup Staging-Promotion Gate`. It runs AFTER the Step 11.5 reachability-to-main gate (code must be on main before it can be promoted to staging) and BEFORE the ontology rebuild.

The canonical staging deploy is `noorinalabs-deploy/.github/workflows/deploy-stg.yml`. The gate inspects the latest run; blocks on red; **defers** (does not fail) when staging does not yet exist — criterion #3 is blocked by criterion #1 (live staging). An explicit rationale env var overrides a red/absent run.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
STATUS="$REPO_ROOT/cross-repo-status.json"
UPSERT="$REPO_ROOT/.claude/lib/upsert_status_keys.py"
STG_WORKFLOW="deploy-stg.yml"
DEPLOY_REPO="noorinalabs/noorinalabs-deploy"

# Fetch the latest deploy-stg.yml run. Empty result = staging not live yet.
STG_RUN=$(gh run list --repo "$DEPLOY_REPO" --workflow "$STG_WORKFLOW" \
  --limit 1 --json databaseId,status,conclusion,url,headSha \
  --jq '.[0] // empty' 2>/dev/null || true)

if [ -z "$STG_RUN" ]; then
  # Criterion #1 not satisfied — defer, do NOT hard-fail. Logged, not silent.
  STG_RESULT="deferred"
  STG_URL=""
  echo "staging-promotion gate DEFERRED — criterion #1 (live staging) not yet satisfied"
  echo "  (no $STG_WORKFLOW run history in $DEPLOY_REPO). Gate auto-activates once staging is live."
else
  STG_STATUS=$(echo "$STG_RUN" | jq -r .status)
  STG_CONCLUSION=$(echo "$STG_RUN" | jq -r .conclusion)
  STG_URL=$(echo "$STG_RUN" | jq -r .url)

  if [ "$STG_STATUS" != "completed" ]; then
    echo "staging deploy still in progress ($STG_STATUS) — re-run /wave-wrapup once $STG_URL completes,"
    echo "or set STG_PROMOTION_OVERRIDE_RATIONALE to close anyway."
    STG_CONCLUSION="in_progress"
  fi

  if [ "$STG_CONCLUSION" = "success" ]; then
    STG_RESULT="success"
    echo "staging promotion GREEN — $STG_URL"
  elif [ -n "${STG_PROMOTION_OVERRIDE_RATIONALE:-}" ]; then
    STG_RESULT="overridden"
    echo "staging promotion NOT green ($STG_CONCLUSION) — OVERRIDDEN:"
    echo "  $STG_PROMOTION_OVERRIDE_RATIONALE"
  else
    echo "════════════════════════════════════════════════════════════"
    echo "BLOCKED: /wave-wrapup cannot close wave {M} — staging promotion is $STG_CONCLUSION."
    echo "  Latest $STG_WORKFLOW run: $STG_URL"
    echo "Fix-forward options:"
    echo "  (a) Fix the regression and re-trigger the staging deploy, then re-run /wave-wrapup."
    echo "  (b) Re-dispatch deploy-stg.yml manually:"
    echo "      gh workflow run $STG_WORKFLOW --repo $DEPLOY_REPO"
    echo "  (c) If a red/absent staging run is INTENTIONALLY acceptable (staging infra"
    echo "      mid-migration, meta-only wave with no deployable surface), set"
    echo "      STG_PROMOTION_OVERRIDE_RATIONALE=\"<explicit reason>\" before re-invoking."
    echo "════════════════════════════════════════════════════════════"
    exit 1
  fi
fi

# Persist the result for /wave-retro Step 2.5 + audit passes. Compact-inline
# preserved via upsert_status_keys.py (NOT jq>tmp>mv — see main#332).
python3 "$UPSERT" "$STATUS" \
    "wave_{M}_stg_promotion=\"${STG_RESULT}\"" \
    "wave_{M}_stg_promotion_url=\"${STG_URL}\""
[ "$STG_RESULT" = "overridden" ] && python3 "$UPSERT" "$STATUS" \
    "wave_{M}_stg_promotion_override_rationale=\"${STG_PROMOTION_OVERRIDE_RATIONALE}\""

# Read-back verify (feedback_gh_pr_edit_silent_noop family).
jq -r --arg m "{M}" '"wave_" + $m + "_stg_promotion = " + (.["wave_" + $m + "_stg_promotion"] | tostring)' "$STATUS"
```

**Override mechanism** (when a red/absent staging run is acceptable):

```bash
# Only use when staging green is genuinely not achievable/applicable for this wave
# (staging infra mid-migration, meta-only wave with no deployable surface).
export STG_PROMOTION_OVERRIDE_RATIONALE="W13 is charter/skill-meta only; no service \
  image changed, so no staging deploy is produced. Gate overridden, criterion #3 \
  unaffected (no deployable surface to promote)."
# Re-invoke /wave-wrapup — the gate logs the rationale, persists it, and proceeds.
```

Include the staging-promotion result (`success`/`failure`/`deferred`/`overridden`) and the run URL in the Step 10 final wave report. `/wave-retro` records it in the wave history row alongside PR count and admin overrides.

### 11.6a. Per-merge deploy watch (active — `/watch-deploy`)

The Step 11.6 gate above inspects only the **latest** `deploy-stg.yml` run. That misses the failure mode deploy#418 surfaced: a wave→main merge in one repo triggers a deploy that fails (e.g. a user-service merge that broke the image pull), which is then masked when a later merge's deploy goes green and becomes "latest". To close this, **actively follow the deploy each wave→main merge triggered**, not just the most-recent run.

For each repo in `wave_{M}_repos_in_scope` that participates in the staging fan-in (`noorinalabs-isnad-graph`, `noorinalabs-user-service` — the repos whose `ghcr-publish.yml` dispatches `deploy-stg.yml`), take that repo's Step 11 wave→main merge commit and run:

```
/watch-deploy stg <merge_sha>
```

`/watch-deploy` polls that specific dispatched deploy to a terminal state, classifies any failure, attempts a single bounded fix-forward (e.g. re-dispatch `stg-latest`), and escalates with a diagnosis otherwise. A wave is not closeable while any fan-in merge's deploy is red and unremediated — fold any escalation into the Step 11.6 block/override decision above.

**Publish-freshness check (P4W4 retro #3 / main#647).** The per-merge watch above follows `deploy-stg.yml`, but a base-image CVE reddens the **publish** (`ghcr-publish.yml`) *upstream* of the deploy: the W4 openssl CVE-2026-45447 reddened isnad-graph's frontend publish and never reached `deploy-stg.yml`, so the deploy watch missed it entirely. For each fan-in repo, also inspect the latest `ghcr-publish.yml` run on its default branch and treat a red publish as a wave-closeability signal — classifying the cause the same way Step 5a of `/session-start` does (base-image-CVE signal → `base-image-drift`, else `code/other`):

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
# Newline-joined so `while read` iterates safely; `for repo in $FANIN` would
# collapse the whole string into one iteration under zsh (main#688). The
# here-string below keeps the loop in the current shell so PUB_RED persists.
FANIN=$'noorinalabs-isnad-graph\nnoorinalabs-user-service'
PUB_RED=()
while IFS= read -r repo; do
  # Only the fan-in repos actually in this wave's scope.
  jq -e --arg r "$repo" '.["wave_{M}_repos_in_scope"] | index($r)' "$REPO_ROOT/cross-repo-status.json" >/dev/null 2>&1 || continue
  branch=$(gh api "repos/noorinalabs/$repo" --jq '.default_branch' 2>/dev/null || echo main)
  # Latest ghcr-publish.yml run on the default branch (empty if the workflow/run is absent).
  IFS=$'\t' read -r run_id conclusion url < <(
    gh api "repos/noorinalabs/$repo/actions/workflows/ghcr-publish.yml/runs?branch=$branch&per_page=1" \
      --jq '(.workflow_runs[0] // empty) | [.id, .conclusion, .html_url] | @tsv' 2>/dev/null
  )
  case "$conclusion" in
    failure|timed_out|cancelled|startup_failure)
      # Best-effort base-image-CVE classification; degrades to code/other on any log-fetch failure.
      cls=code/other
      log=$(gh run view "$run_id" --repo "noorinalabs/$repo" --log-failed 2>/dev/null || true)
      printf '%s' "$log" | grep -Eiq 'trivy|grype|\bCVE-[0-9]{4}-[0-9]+|apk[ -].*(upgrade|CVE)|openssl.*(vuln|CVE|advisor)|base[ -]image' && cls=base-image-drift
      PUB_RED+=("$repo :: ghcr-publish.yml :: $conclusion :: $cls :: $url") ;;
  esac
done <<< "$FANIN"
if [ ${#PUB_RED[@]} -gt 0 ]; then
  printf 'RED fan-in publish run(s) — a wave is NOT closeable while a fan-in publish is red:\n'
  printf '  %s\n' "${PUB_RED[@]}"
  printf '%s\n' "${PUB_RED[@]}" | grep -q base-image-drift && \
    printf '  NOTE: "base-image-drift" = upstream base-image CVE — fix-forward the base image (rebuild/bump), not the wave diff.\n'
else
  echo "Fan-in publishes (ghcr-publish.yml) green on default branches."
fi
```

A red fan-in publish — `base-image-drift` or otherwise — blocks wave closeability the same as a red deploy: fold it into the Step 11.6 block/override decision above. Best-effort: on `gh api` failure, say so rather than reporting a false green.

Landing-page and meta-only repos do not participate in the stg fan-in (no dispatch), so they have no per-merge deploy or publish to watch — skip them.

**Production counterpart:** prod deploys are gated on owner approval (owner directive 2026-06-09). `/wave-wrapup` must NOT approve or trigger them. When the owner approves a queued prod deploy for this wave's promotion, run `/watch-deploy prod <sha>` to monitor it the same way; `/watch-deploy` never advances or auto-remediates prod.

### 12. Ontology update — semantic overlay + structural index (#862)

The ontology has two independent layers to update at wave close (#820/C×T2):

**12a. Semantic overlay** — run `/ontology-rebuild` to process any hand-curated files that changed during this wave. Scope is `ontology/checksums.json` dirty files only; structural is never resolved here.
- If no dirty files, report "Semantic overlay: up to date" and skip
- The resolver auto-updates docs where appropriate and flags recommend-only changes

**12b. Structural index** — regenerate the parent repo's structural index and refresh the cross-repo aggregator. The wave may have added/changed hooks, skills, or lib modules that should be reflected in the index before the wave is closed.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Check how many source files changed since the index was last generated
STRUCT_SHA=$(git -C "$REPO_ROOT" log -1 --format="%H" -- ontology/structural/llms.txt 2>/dev/null || echo "")
if [ -z "$STRUCT_SHA" ]; then
  CHANGED="new"
else
  CHANGED=$(git -C "$REPO_ROOT" diff --name-only "$STRUCT_SHA"..HEAD -- \
    '*.py' '*.ts' '*.tsx' '*.js' '*.jsx' '*.cypher' '*.cql' 2>/dev/null | wc -l | tr -d ' ')
fi

if [ "${CHANGED:-0}" = "0" ]; then
  echo "Structural index: current — no source files changed since last generation."
else
  echo "Structural index: ${CHANGED} source file(s) changed — regenerating."
  PYTHONPATH="$REPO_ROOT/.claude/lib" python3 -m ontology_gen \
    "$REPO_ROOT" --out "$REPO_ROOT/ontology/structural/" 2>&1
  # Refresh the central cross-repo graph
  PYTHONPATH="$REPO_ROOT/.claude/lib" python3 -m ontology_gen.aggregate \
    "$REPO_ROOT" 2>&1 || true

  # Commit if anything changed
  if ! git -C "$REPO_ROOT" diff --quiet ontology/structural/; then
    git -C "$REPO_ROOT" add ontology/structural/
    MSGFILE="$(mktemp)"
    printf 'ontology: regenerate structural index (wave-wrapup step 12b)\n\n%s source files changed this wave; re-ran ontology_gen + aggregate.\n' \
      "${CHANGED}" > "$MSGFILE"
    git -C "$REPO_ROOT" \
      -c user.name="Aino Virtanen" \
      -c user.email="parametrization+Aino.Virtanen@gmail.com" \
      commit -F "$MSGFILE"
    rm -f "$MSGFILE"
    echo "Structural index committed."
  fi
fi
```

Include both results in the final wave report (Step 10):
- `Ontology: Semantic {N files resolved / up to date}; Structural {current / regenerated + committed}`

**Note:** the structural layer at `ontology/structural/` is always-current-by-regeneration — `/ontology-rebuild` does NOT resolve it (that was retired per #857/C×T2). The generator above IS the structural resolve path.

### 12.5. Generic-prompt genericize checkpoint (main#716)

The `suggest_generic_prompt` PostToolUse hook no longer nudges per-edit (that nudge was never actioned — a non-binding mid-task `systemMessage` with no state, no dedup, no closing loop → enforcement-hierarchy decay; `2real-team-framework/generic_prompts/` gained **zero** files across every wave despite it firing constantly). It now **silently tracks** every touched `.claude/` artifact into a pending ledger. This step is the closing loop: once per wave, enumerate the wave's new/changed `.claude/` artifacts (hooks/skills/charter/settings) that **lack a counterpart** in the framework's `generic_prompts/` **and aren't already decided**, and make ONE deliberate genericize-or-skip pass. Decisions are recorded so the same artifact is never re-surfaced.

Two state files back this (see `.claude/lib/generic_prompt_tracker.py`): `.claude/generic_prompt_pending.json` (volatile, gitignored — the candidate set) and `.claude/generic_prompt_ledger.json` (**version-controlled** — the durable genericize/skip decisions, the dedup memory).

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
TRACKER="$REPO_ROOT/.claude/lib/generic_prompt_tracker.py"

# (a) Belt-and-suspenders: the pending ledger is per-machine volatile state, so
# augment it with a git-diff sweep of the meta repo's wave-window .claude/
# changes (in case pending was wiped, or edits happened in a different session).
# Diff the wave branch's merge-base with main against HEAD; degrade to a no-op
# if the wave branch is absent. zsh-safe `while read` (main#688).
WAVE_BRANCH="deployments/phase-{P}/wave-{M}"
BASE=$(git -C "$REPO_ROOT" merge-base main "$WAVE_BRANCH" 2>/dev/null || true)
if [ -n "$BASE" ]; then
  git -C "$REPO_ROOT" diff --name-only --diff-filter=d "$BASE"..HEAD -- '.claude/**' 2>/dev/null \
    | while IFS= read -r f; do
        [ -n "$f" ] && python3 "$TRACKER" record-candidate "$REPO_ROOT/$f" >/dev/null
      done
fi

# (b) List the undecided genericizable candidates — the deliberate worklist.
python3 "$TRACKER" list --wave "P{P}W{M}"
```

For **each** candidate the list prints, make a genericize-or-skip call and record it (this is what stops the artifact re-surfacing next wave):

```bash
# Genericize: draft the product-neutral prompt file in the framework repo
# (strip project-specific names/paths/team/repo), then record the decision with
# the generic file as the detail:
python3 "$TRACKER" record "hooks/<name>.py" genericized \
  --detail "GENERIC_<NAME>_PROMPT.md" --wave "P{P}W{M}"

# Skip: the artifact is too project-coupled to genericize (or not worth it) —
# record WHY so it stays settled:
python3 "$TRACKER" record "skills/<name>/SKILL.md" skipped \
  --detail "<one-line reason — e.g. tightly coupled to noorinalabs wave lifecycle>" \
  --wave "P{P}W{M}"
```

- If `list` reports no undecided candidates, report "Generic-prompt checkpoint: nothing to genericize this wave" and continue.
- **Commit the ledger** (`.claude/generic_prompt_ledger.json`) as part of the wrapup — it is version-controlled durable state. The pending file is gitignored; do not commit it.
- Include a one-line genericized/skipped tally in the Step 10 final wave report.
- This is the deliberate batched replacement for the demoted per-edit hook; do NOT re-introduce a mid-task suggestion.

### 13. Annunaki error attack

> **Preferred surface is `/wave-retro` Step 7.6 (P3W9 #344).** Retro is the natural moment for this audit — findings feed the retro's charter-change proposals. Wrapup retains this step as a fallback for cases where retro is delayed or skipped. The run-marker below prevents double-execution.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
ALREADY_RAN=$(jq -r ".wave_${M}_annunaki_attack_ran_at // empty" "$REPO_ROOT/cross-repo-status.json")

if [ -n "$ALREADY_RAN" ]; then
  echo "Annunaki-attack: already ran at $ALREADY_RAN (via /wave-retro Step 7.6). Skipping."
  # Continue to Step 14.
else
  # Proceed with the attack below; on completion write the marker.
fi
```

Run `/annunaki-attack` to process any errors captured by the Annunaki monitor during this wave. This converts observed errors into preventative automation (hooks, skills, charter updates) before the wave closes.

- If `.claude/annunaki/errors.jsonl` is empty or missing, report "Annunaki: No errors captured this wave" and skip the attack — but still write the run-marker so retro's 7.6 doesn't re-check
- Use the current wave label for any issues created
- Include Annunaki-created issues and PRs in the final wave report totals
- This step runs **before** the memory-to-automation audit so that new hooks/skills from error analysis are visible to the memory audit
- On completion, write `wave_${M}_annunaki_attack_ran_at = <ISO-8601 UTC timestamp>` to `cross-repo-status.json`

### 14. Memory-to-automation audit

> **Preferred surface is `/wave-retro` Step 7.7 (P3W9 #344).** Retro is the natural moment for this audit — findings feed the retro's charter-change proposals and the Aino-spawned conversion issues count toward the same retro's per-engineer assessment + trust update pass. Wrapup retains this step as the canonical procedure body (referenced by retro's 7.7) and as a fallback for retro-delayed cases. The run-marker below prevents double-execution.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
ALREADY_RAN=$(jq -r ".wave_${M}_memory_audit_ran_at // empty" "$REPO_ROOT/cross-repo-status.json")

if [ -n "$ALREADY_RAN" ]; then
  echo "Memory-to-automation audit: already ran at $ALREADY_RAN (via /wave-retro Step 7.7). Skipping."
  # Continue to the rest of the wrapup.
else
  # Proceed with the audit below; on completion write the marker.
fi
```

Examine all memory files in the project memory directory for entries that describe behaviors, rules, or patterns that could be codified as a **hook**, **skill**, or **charter update** instead of remaining as soft memory. On completion, write `wave_${M}_memory_audit_ran_at = <ISO-8601 UTC timestamp>` to `cross-repo-status.json`.

**Process:**

1. **Read all memory files:**
   ```bash
   ls ~/.claude/projects/*/memory/*.md
   ```

2. **For each memory file**, classify it:
   | Category | Criteria | Action |
   |----------|----------|--------|
   | **Hook candidate** | Describes a rule that should be enforced automatically (e.g., "always do X before Y", "never do Z") | Create the hook, add to settings.json, create GH issue for bookkeeping |
   | **Skill candidate** | Describes a repeatable multi-step workflow (e.g., "when doing X, follow these steps") | Create the skill in `.claude/skills/`, create GH issue |
   | **Charter update** | Describes a process rule or convention that should be documented for all agents | Update the relevant charter section, create GH issue |
   | **Keep as memory** | User-specific context, preferences, or project state that doesn't fit the above | Leave as-is |

3. **For each hook/skill/charter candidate:**
   a. Create a GitHub Issue describing the automation opportunity
   b. **Assign to the best-fit team member** based on the charter mapping:
      - Hooks and charter updates → Aino Virtanen (Standards & Quality Lead)
      - Skills → Aino Virtanen or the domain expert for that workflow
      - Code changes → the relevant repo's tech lead
   c. **Spawn or message that person** with the issue details and full context
   d. Wait for them to confirm completion
   e. Once confirmed: verify the implementation (hook works, skill invokes, charter reads correctly)
   f. Push changes and close the issue
   g. **Delete or update the memory file** — if the memory's content is now fully captured in a hook/skill/charter, remove it. If partially captured, update it to reference the new automation.

4. **Report what was converted:**
   ```
   **Memory-to-Automation Audit**

   | Memory File | Classification | Action Taken | Issue |
   |-------------|---------------|--------------|-------|
   | feedback_x.md | Hook | Created validate_x.py | #N |
   | project_y.md | Keep | No action | — |
   | ...         | ...           | ...          | ...   |
   ```

**Why:** Memory files accumulate rules and patterns that should be enforced automatically. If a memory says "always do X", that's a hook. If it says "follow these steps for Y", that's a skill. Leaving these as memories means they only work when the LLM happens to load them — hooks and skills are deterministic.

**Designated owner:** Aino Virtanen handles most conversions (hooks, charter, standards). The orchestrator spawns her with the audit list and she reports back when done.

## What remains manual

- User must approve merge sequence before any PR is merged
- Must-fix items require engineer action before merge
- Deferred issues need user decision on next-wave placement
- Final-wave merge to main requires explicit user approval
- `/wave-retro` must be run separately after wrapup completes
- Memory audit classifications are proposed — user can override keep/convert decisions

## Scope-Drop Reconciliation (added P3W4 retro 2026-05-05)

Before closing a wave, reconcile **declared scope vs delivered scope**. For each repo in `cross-repo-status.json` `wave_{N}_repos_in_scope`:

```bash
gh pr list --repo noorinalabs/{repo} --state merged --base "deployments/phase-{N}/wave-{M}" --json number --jq 'length'
```

If the count is **0**, the repo had declared work that did not ship. Resolve the drop EXPLICITLY — silent drops are not allowed.

**Two valid outcomes:**

1. **De-scoped during wave** — the work was correctly assessed as out-of-scope mid-wave. Move the repo from `wave_{N}_repos_in_scope` to a new `wave_{N}_repos_descoped_during_wave` array in `cross-repo-status.json` with a one-line reason field. Examples: theme misalignment surfaced after kickoff, dependency on next-wave work, planning error.

2. **Carry-forward to next wave** — the work is still real but slipped. File or update the carry-forward issues, label them with the next wave's label, and add references to `cross-repo-status.json` `wave_{N+1}_carry_forward` array.

**Why:** P3W4 declared `noorinalabs-isnad-ingest-platform` in scope but shipped 0 PRs to its wave branch. The drop was invisible at wrap-time because no check enforced reconciliation — the wave closed with a silent scope discrepancy that surfaced only at retro. Operationally, silent drops compound across waves: by W3-of-N, the declared scope drifts arbitrarily far from delivered, and planning-vs-execution accuracy becomes unmeasurable.

**Acceptance:** A wave-wrapup is not complete until every repo in `wave_{N}_repos_in_scope` has either ≥1 PR merged to its wave branch OR an explicit de-scope/carry-forward record. Run this check BEFORE the wave-merge ceremony.

## Implementer-Substitution Reconciliation (added P3W5 retro 2026-05-06)

Symmetric to § Scope-Drop Reconciliation, but for the inverted case: the declared implementer was replaced silently. Before closing a wave, reconcile **declared implementer vs actual PR author** for every PR merged to a wave branch.

```bash
# For each repo in scope, for each merged PR (zsh-safe `while read` fed from the
# repos helper + process substitution — main#688). Command substitution like
# `for repo in $(jq …)` happens to split in zsh, but a parameter
# (`for repo in $REPOS`) would not; standardize on `while read` so the safe form
# is the one operators copy.
while IFS= read -r repo; do
  while IFS= read -r pr; do
    actual=$(gh pr view "$pr" --repo "noorinalabs/$repo" --json author --jq '.author.login')
    branch=$(gh pr view "$pr" --repo "noorinalabs/$repo" --json headRefName --jq '.headRefName')
    # Compare actual against wave_{M}_scope.tier_*[].implementer or .tier_*[].assignee for that issue.
    # Branch prefix (e.g., "T.Mansour/...") is the cheap proxy when author is the github org bot.
  done < <(gh pr list --repo "noorinalabs/$repo" --state merged --base "deployments/phase-{N}/wave-{M}" --json number --jq '.[].number')
done < <(python3 "$REPO_ROOT/.claude/lib/wave_status.py" repos {N} {M})
```

If the actual author (or branch-prefix initials) does not match the kickoff-declared implementer, the substitution must be recorded EXPLICITLY — silent swaps are not allowed.

**Required record:** add an entry to `wave_{N}_decisions.implementer_substitutions` in `cross-repo-status.json`:

```json
{
  "implementer_substitutions": [
    {
      "repo": "noorinalabs-data-acquisition",
      "issue": "data-acquisition#36",
      "declared": "Sofia Cardoso",
      "actual": "Tarek Mansour",
      "swapped_at": "2026-05-05T23:42:00Z",
      "rationale": "<one-line reason — e.g., declared implementer unavailable; reassigned by Pipeline Mgr Dilara>"
    }
  ]
}
```

**Why:** P3W5 declared Sofia Cardoso as the T1A #263 implementer for data-acquisition; the actual PR (data-acquisition#37) was authored by Tarek Mansour with no recorded swap rationale. Same shape as W4's ingest-platform silent-drop, just inverted (silent-substitution vs silent-zero-PR). Both are scope-drift with no audit trail. Operationally, silent substitutions compound the same way silent drops do: trust matrix updates apply to the wrong engineer (Sofia gets credit she didn't earn, Tarek's first wave PR is invisible at retro), and planning-vs-execution accuracy degrades.

**Acceptance:** A wave-wrapup is not complete until every PR with a declared-vs-actual mismatch has either an entry in `wave_{N}_decisions.implementer_substitutions` OR an explicit acknowledgment that the swap is benign (e.g., orchestrator-class spawn doing implementer-class work — already covered by other discipline). Run this check BEFORE the wave-merge ceremony, in the same pass as § Scope-Drop Reconciliation.
