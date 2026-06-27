---
name: wave-kickoff
description: Automated wave planning — branch creation, label management, issue labeling, kickoff comments, and execution plan
args: team_name, Phase number, Wave number
---

Automate the wave kickoff process for the `{team_name}` team.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Wave Lifecycle for the canonical skill order and preconditions.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## Instructions

### 0. Run `/board-audit` (Mandatory precondition — added per main#199)

Run `/board-audit` once to ensure project 2 reflects current open-issue state and the `Wave` field is in sync with the wave labels (the new `wave-{X}` form and grandfathered `p{N}-wave-{M}`, #810). Without a current board, downstream steps (scope reconciliation, label application, kickoff comments) can silently miss orphan issues per memory `feedback_wave_planning_from_board.md` (the 37% drift discovery on 2026-04-23).

If `/board-audit` reports drift, address it before proceeding. Labels are canonical; the Wave field is a derived projection synced by the skill (charter `issues.md § Wave Planning — Project Board Is Authoritative`).

### 0a. Verify next-wave scope is reconciled (Mandatory precondition — added P3W5 #273)

`cross-repo-status.json` MUST carry a `wave_{M}_scope_reconciled_at` ISO timestamp written by `/wave-scope {P} {M}`. If a prior-wave retro/completion timestamp is also present, the scope timestamp MUST post-date it. If `wave_{M}_scope_reconciled_at` is absent the kickoff STOPs unconditionally; the staleness check is permissive (no-op) when the prior-wave timestamp is also absent — see "Permissive fallback" below.

```bash
# Note: `{P}` and `{M}` are skill-template placeholders the orchestrator
# string-substitutes BEFORE the bash block runs. After substitution
# `$(({M} - 1))` becomes a literal arithmetic expansion like `$((5 - 1))` —
# they are not bash variables.
REPO_ROOT="$(git rev-parse --show-toplevel)"
SCOPE_TS=$(jq -r '.wave_{M}_scope_reconciled_at // empty' "$REPO_ROOT/cross-repo-status.json")
PRIOR_RETRO_TS=$(jq -r '.wave_$(({M} - 1))_retro_completed_at // .wave_$(({M} - 1))_completed_at // empty' "$REPO_ROOT/cross-repo-status.json")

if [ -z "$SCOPE_TS" ]; then
  echo "ERROR: wave_{M}_scope_reconciled_at missing in cross-repo-status.json."
  echo "  Run /wave-scope {P} {M} before /wave-kickoff."
  exit 1
fi

if [ -n "$PRIOR_RETRO_TS" ] && [ "$SCOPE_TS" \< "$PRIOR_RETRO_TS" ]; then
  echo "ERROR: wave_{M}_scope_reconciled_at ($SCOPE_TS) predates last retro ($PRIOR_RETRO_TS)."
  echo "  Re-run /wave-scope {P} {M} so the reconciliation reflects the current carry-forward + memory-must-include state."
  exit 1
fi

if [ -z "$PRIOR_RETRO_TS" ]; then
  echo "  Scope reconciled at: $SCOPE_TS (no prior-wave timestamp — first wave of phase or fresh project; staleness check skipped)"
else
  echo "  Scope reconciled at: $SCOPE_TS (post-dates last retro: $PRIOR_RETRO_TS)"
fi
```

This check is a deterministic JSON read — no GitHub API calls, no side effects. It catches the off-path case where `/wave-kickoff` is invoked without a recent `/wave-scope` (drift signal: meta-issue out of sync with labels). The common path is covered by `/wave-retro` Step 9, which auto-invokes `/wave-scope {P} {M+1}` at end-of-wave.

**Permissive fallback (intentional).** When neither `wave_{M-1}_retro_completed_at` nor `wave_{M-1}_completed_at` exists in `cross-repo-status.json` — e.g., the first wave of a phase, or a fresh project — the staleness comparison is silently skipped and only the absent-scope check fires. This keeps the precondition usable for Phase-N-Wave-1 cases without requiring a synthetic zero-timestamp. The trade-off: a `wave_{M}_scope_reconciled_at` written years ago with no surrounding context will pass. If that becomes a real failure mode, tighten to fail-closed and require an explicit `WAVE_KICKOFF_ALLOW_NO_PRIOR_RETRO=1` override.

### 0. Derive wave repos in scope (Mandatory first step)

The canonical source for the wave's repo list is `cross-repo-status.json` key `wave_{M}_repos_in_scope` (array of `noorinalabs-*` strings). All subsequent steps iterate this list.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
WAVE_REPOS_IN_SCOPE=$(jq -r ".wave_{M}_repos_in_scope[]" "$REPO_ROOT/cross-repo-status.json")
test -n "$WAVE_REPOS_IN_SCOPE" || { echo "ERROR: wave_{M}_repos_in_scope missing or empty in cross-repo-status.json"; exit 1; }
echo "Wave repos in scope:"
printf '  - %s\n' $WAVE_REPOS_IN_SCOPE
```

If the key is missing, STOP — the wave is not properly scoped. Add `wave_{M}_repos_in_scope` to `cross-repo-status.json` before invoking the skill.

For path resolution: each repo `R` lives at `$REPO_ROOT/$R` EXCEPT `noorinalabs-main`, which IS `$REPO_ROOT`. Use this helper:

```bash
repo_path() {
  local r="$1"
  if [ "$r" = "noorinalabs-main" ]; then echo "$REPO_ROOT"; else echo "$REPO_ROOT/$r"; fi
}
```

### 0.5. Pre-flight checklist (Mandatory — Pattern F mitigation)

Before any branch creation, label work, or agent spawning, complete this checklist for every repo in the wave's planned scope. The Phase 3 Wave 3 retro identified **6 orchestrator-class pre-flight gaps** (wave-branch creation, attribution, child-repo-implementer rule ×2, 2-reviewer planning, naming, spawn order) — all caught by downstream layers, not pre-flight. This step closes Pattern F.

For each repo `R` in `$WAVE_REPOS_IN_SCOPE`:

| # | Check | How to verify |
|---|---|---|
| 0.1 | **Wave branch exists in repo `R`** | `gh api repos/noorinalabs/$R/git/refs/heads/deployments/phase-{N}/wave-{M}` returns 200 (not 404). Step 1 is responsible for creation; this check confirms it landed before subsequent steps run. |
| 0.2 | **Implementer roster confirmed for `R`** | Per child-repo-implementer rule (memory `feedback_child_repo_implementer_rule.md`): implementers come from `R`'s own team roster, not the orchestrator's parent team |
| 0.3 | **Every scoped issue's `actual_repo_for_changes` is correct — RELOCATE if not** | Re-read every issue body; sibling-of references can mislead. Concrete example: deploy#242 was filed as "sibling-of isnad-graph" but the actual code change was in landing-page (caught by Idris-853 in P3W3 only after kickoff). **When an issue's code lands in a different repo than the one it's filed in, you MUST relocate it — do not just note it.** See § 0.3a. |
| 0.4 | **2-reviewer slate drafted per PR** | `wave_3_scope.tier_*` entries each list `assignee` + `reviewer` (and a 2nd reviewer for charter compliance — see charter `pull-requests.md` § Two-Reviewer Assignment at Wave Kickoff) |
| 0.5 | **Agent naming pattern** | `{FirstInitial}.{LastName}/{IIII}-{slug}` per CLAUDE.md § Branching Strategy. Verify in execution plan |
| 0.6 | **Spawn-brief ordering** | Each spawn brief lists reviewer-class identity AHEAD of implementer-class identity. Reviewer-first prevents Pattern B inversion (the implementer drafts → reviewer verifies-vs-artifact chain only works if the reviewer's role is established before the implementer starts coding) |

If any check fails for any repo, STOP and resolve before proceeding. The output of this step is a 6×N table (6 checks × N repos in scope) with explicit YES/NO/N-A entries — paste it into the kickoff comment on the meta-issue so the gap-resolution audit trail lives on the issue.

### 0.3a. Mis-filed-issue relocation protocol (Mandatory — owner directive 2026-06-12)

**Standing owner rule (P4W3): a wave issue whose code lands in a different repo than the one it is filed in MUST be relocated at kickoff — close it in its home repo and re-create it in the repo that actually changes. Noting the discrepancy is not enough; the issue itself moves. Do this every wave.**

For each issue flagged by check 0.3 (`actual_repo_for_changes` ≠ filed repo):

1. **Re-create in the actual repo(s).** Author a new issue in the repo where the code changes, with a faithful body (carry the original scope) plus a `## Provenance` line naming the closed source issue and this relocation rule. If the work splits across *multiple* repos (e.g. a UI in one repo + an HTTP endpoint in another, or per-repo lockfile bumps), create **one issue per repo** — this also serves the smaller-PR / parallelize preference. Apply the category label(s) but NOT the wave label yet.
2. **Board + scope.** `gh project item-add 2 --owner noorinalabs --url <new-url>` for each new issue. Replace the source issue's entry in `cross-repo-status.json` `wave_{M}_scope.tier_*` with the new ref(s) + the drafted implementer/reviewer slate, keyed to the actual repo (`id`).
3. **Close the source issue.** Post a relocation comment on it pointing to the new issue(s), `--remove-label "wave-{X}"` (or the grandfathered `p{N}-wave-{M}` if that is what the issue carries), then `gh issue close … --reason "not planned"`.
4. **Then** proceed to the wave-label apply (§ 7) on the NEW issues so the auto-kickoff-comment hook fires against the correct repo + slate.

Relocation happens BEFORE the slate is persisted and BEFORE any wave-label apply, so the scope and kickoff comments reference the real repos from the start. Precedent: P4W3 relocated main#138 → isnad-graph#970 (UI) + ingest-platform#70 (HTTP endpoint), and main#633 → ingest-platform#71 (pip) + isnad-graph#971 (authlib+pip).

### 1. Create the deployments branch in every wave repo

> **Invariant (#653):** the orchestrator should be on a clean, up-to-date `main` (parked by `/wave-start` § 2) or operating purely via `gh api` — a stale local checkout risks the Step 1a kickoff-comment hook reading an out-of-date local `cross-repo-status.json`.

For **every** repo `R` in `$WAVE_REPOS_IN_SCOPE` (not just the orchestrator repo — main#238 closed in W4), create `deployments/phase-{N}/wave-{M}` from `origin/main`. The skill uses `gh api` directly so it does NOT require a clean local checkout — this is intentional, since the orchestrator session may be running in an unrelated worktree.

**Idempotency contract:** if the branch already exists in `R`, the skill MUST NOT fail. It distinguishes three cases via GitHub's `compare` API:
- `exists-clean` — wave branch SHA == main SHA (just-created or unchanged)
- `exists-ancestor` — wave branch is an ancestor of main (main advanced after kickoff; expected after the kickoff status commit lands)
- `exists-drift` — wave branch and main have diverged (someone pushed a non-main commit onto the wave branch — surface, do NOT overwrite)

**Dry-run mode:** if `WAVE_KICKOFF_DRY_RUN=1` is set in the environment, the skill MUST print the per-repo plan but skip the POST that creates the ref. Reads (lookup of existing ref + main SHA) still execute.

```bash
BRANCH="deployments/phase-{N}/wave-{M}"
declare -A BRANCH_SHA  # repo -> resulting SHA (for status-file update + table)
declare -A BRANCH_STATUS  # repo -> "created" | "exists-clean" | "exists-ancestor" | "exists-drift" | "dry-run-create" | "error:<msg>"

# zsh-safe iteration: here-string into `while read` (NOT `for R in
# $WAVE_REPOS_IN_SCOPE` — zsh does not word-split a parameter, so the whole list
# would collapse into one bogus repo; main#688). The here-string keeps the loop
# in the current shell so the BRANCH_SHA / BRANCH_STATUS assoc arrays persist
# past `done` (a `| while` pipe would lose them to the subshell).
while IFS= read -r R; do
  MAIN_SHA=$(gh api "repos/noorinalabs/$R/git/refs/heads/main" --jq '.object.sha' 2>/dev/null) || {
    BRANCH_STATUS[$R]="error:cannot-read-main"; continue;
  }

  # Probe existing branch. gh api returns the raw 404 JSON body when the ref is absent,
  # which --jq passes through unchanged (non-40-hex). Guard with shape validator so a
  # missing branch yields EXISTING_SHA="" rather than the error body. (live-trigger: e906e135)
  EXISTING_SHA=$(gh api "repos/noorinalabs/$R/git/refs/heads/$BRANCH" --jq '.object.sha' 2>/dev/null || true)
  [[ "$EXISTING_SHA" =~ ^[0-9a-f]{40}$ ]] || EXISTING_SHA=""

  if [ -n "$EXISTING_SHA" ]; then
    BRANCH_SHA[$R]="$EXISTING_SHA"
    if [ "$EXISTING_SHA" = "$MAIN_SHA" ]; then
      BRANCH_STATUS[$R]="exists-clean"
    else
      # Use compare API to distinguish ancestor (main moved forward) from real drift (wave branch diverged)
      STATUS_TYPE=$(gh api "repos/noorinalabs/$R/compare/main...$EXISTING_SHA" --jq '.status' 2>/dev/null || echo "unknown")
      case "$STATUS_TYPE" in
        behind|identical) BRANCH_STATUS[$R]="exists-ancestor" ;;  # wave branch behind main = ancestor case
        ahead|diverged)   BRANCH_STATUS[$R]="exists-drift" ;;     # real drift
        *)                BRANCH_STATUS[$R]="exists-drift" ;;
      esac
    fi
    continue
  fi

  if [ "${WAVE_KICKOFF_DRY_RUN:-0}" = "1" ]; then
    BRANCH_SHA[$R]="$MAIN_SHA"
    BRANCH_STATUS[$R]="dry-run-create"
    continue
  fi

  # Create the ref. 422 means "ref already exists" — race-safe idempotency.
  CREATE_OUT=$(gh api -X POST "repos/noorinalabs/$R/git/refs" \
    -f "ref=refs/heads/$BRANCH" -f "sha=$MAIN_SHA" 2>&1) && {
    BRANCH_SHA[$R]="$MAIN_SHA"
    BRANCH_STATUS[$R]="created"
  } || {
    if echo "$CREATE_OUT" | grep -q "Reference already exists"; then
      BRANCH_SHA[$R]="$MAIN_SHA"; BRANCH_STATUS[$R]="exists-clean"  # raced; treat as no-op
    else
      BRANCH_STATUS[$R]="error:$(echo "$CREATE_OUT" | head -1 | tr -d '"' | cut -c1-80)"
    fi
  }
done <<< "$WAVE_REPOS_IN_SCOPE"
```

Print a status table (always, in both dry-run and live mode):

```
| Repo                              | Branch SHA  | Status         |
|-----------------------------------|-------------|----------------|
| noorinalabs-main                  | 93f3513...  | created        |
| noorinalabs-isnad-graph           | bbf7073...  | exists-clean   |
| noorinalabs-user-service          | 8deb979...  | exists-ancestor|
| noorinalabs-deploy                | 0b3b214...  | exists-drift   |
| noorinalabs-design-system         |  —          | error:cannot-read-main |
```

**Stop-the-line conditions:**
- Any `error:*` — investigate before continuing (likely a missing repo or a permissions gap, not the skill's bug to swallow)
- Any `exists-drift` — a prior session pushed a non-main commit onto this branch. Surface to the user; do NOT overwrite. Decide whether to rebase, fast-forward, or accept.

**Persist results to `cross-repo-status.json`:**

```bash
# Build a JSON object {repo: {sha, status}} and merge under wave_{M}_branches
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
JSON=$(while IFS= read -r R; do
  printf '%s\n' "$R ${BRANCH_SHA[$R]:-null} ${BRANCH_STATUS[$R]}"
done <<< "$WAVE_REPOS_IN_SCOPE" | jq -Rn --arg ts "$TS" --arg branch "$BRANCH" '
  [inputs | split(" ")] |
  map({(.[0]): {sha: (.[1] | if . == "null" then null else . end), status: .[2]}}) |
  add | {branch: $branch, created_at: $ts, repos: .}')

if [ "${WAVE_KICKOFF_DRY_RUN:-0}" != "1" ]; then
  jq --argjson b "$JSON" '.wave_{M}_branches = $b' "$REPO_ROOT/cross-repo-status.json" \
    > "$REPO_ROOT/cross-repo-status.json.tmp" && mv "$REPO_ROOT/cross-repo-status.json.tmp" "$REPO_ROOT/cross-repo-status.json"
fi
```

**Verify step 0.1 holds for every repo before moving on** — every entry in the status table must be `created`, `exists-clean`, `exists-ancestor`, or (with explicit user sign-off) `exists-drift`. A missing or errored wave branch in any child repo is a stop-the-line condition.

**Declare the wave's merge model (Mandatory — one model per wave, main#801).** A wave uses exactly ONE merge model for its whole lifetime — `wave-branch` (every per-issue PR bases on `deployments/phase-{P}/wave-{M}`; the wave→main integration PR is opened at `/wave-wrapup`) OR `direct-to-main` (every PR bases on `main`; the wave branch never accumulates commits). Mixing the two within a wave is the P6W1 stranding bug (charter `pull-requests.md § One Merge Model Per Wave`). Record it now so the `/session-start` reachability check can enforce it mid-wave:

```bash
# Default for a cross-repo wave is wave-branch; a meta-only / single-repo wave
# may declare direct-to-main. Pick deliberately, then record it.
MERGE_MODEL="wave-branch"   # or: direct-to-main
python3 "$REPO_ROOT/.claude/lib/wave_merge_model.py" set {P} {M} "$MERGE_MODEL"
# Read-back-verify:
python3 "$REPO_ROOT/.claude/lib/wave_merge_model.py" model {P} {M}
```

The helper validates the model against the fixed `{direct-to-main, wave-branch}` set and upserts `wave_{M}_merge_model` through the shared `upsert_status_keys.py` (preserving the compact-inline file shape). A typo is rejected (exit 1) rather than silently persisted.

### 1a. Status commits — use `gh api` PUT contents (atomic, no local orphan)

**Status commit pattern (added P3W6 retro 2026-05-08, supersedes local-then-push):**

Wave-status commits (kickoff active state, reconciliation timestamps, completion state) MUST use `gh api -X PUT repos/.../contents/cross-repo-status.json` instead of local checkout + local commit + push. The PUT-contents flow is atomic — no local-orphan-possible (the P3W6 e235b0b orphan was a local kickoff status commit that never reached origin and only surfaced at wrapup).

Recipe:
1. Fetch current sha + content via `gh api .../contents/cross-repo-status.json?ref=main --jq .sha` and `--jq .content | base64 -d`
2. Build new content via `jq` (e.g., `jq '. + {wave_N_kicked_off_at: $now, wave_N_active: true, ...}'`)
3. base64-encode the new content
4. Build PUT payload JSON with `message`, `content` (base64), `sha` (current), `branch: "main"`, `author: {name, email}`, `committer: {name, email}`
5. `gh api -X PUT repos/.../contents/cross-repo-status.json --input <payload>.json`

**MANDATORY — advance the `current_wave` pointer (P3W14 retro Proposed Change #1).** The kickoff status write MUST set `current_wave` to this wave, alongside the active-state keys:

```jq
. + {
  "current_wave": "wave-{M}",
  "last_completed_wave": "wave-{M-1}",
  "next_wave": "wave-{M+1}",
  "wave_{M}_active": true,
  "wave_{M}_kicked_off_at": $now
}
```

`validate_wave_audit` derives the current wave **labels** (both the new `wave-{X}` and the legacy `p{N}-wave-{M}`, #810) from `current_wave` to count open wave issues; if the pointer still names the prior wave, the wave-conclusion audit blocks the **next** wave's `/wave-retro`. This was the one W14 annunaki capture — W14 kicked off without advancing `current_wave`, leaving it at `wave-13`, and the retro was blocked until the pointer was manually corrected. Read-back-verify after the PUT: `gh api .../contents/cross-repo-status.json?ref=main --jq '.content' | base64 -d | jq -r '.current_wave'` MUST print `wave-{M}`.

Attribution: kickoff status commits use Wanjiku Mwangi (TPM); reconciliation/wrapup commits use the role-running implementer.

The local-then-push `jq | mv | git commit | git push` pattern at the end of Step 1 above pre-dates this guidance — it remains acceptable for the `wave_{M}_branches` write (which is wave-branch-scoped, not main) but MUST NOT be used for any commit landing on `main`. Status writes that target `main` (kickoff active, reconciliation, wrapup completion) use the PUT-contents recipe.

### 2. Create wave label

The canonical wave label is the **phase-agnostic** `wave-{X}` (#810, completing
Design B #804), where `{X}` is the global monotonic wave id (== `current_wave`).
Use `wave-x` as a placeholder only when the phase/scope is genuinely undecided.
Legacy `p{N}-wave-{M}` labels on in-flight issues are grandfathered — every
parser/hook still accepts them — but NEW issues get `wave-{X}`.

Check if label `wave-{X}` exists:

```bash
gh label list --search "wave-{X}"
```

If missing, create it:

```bash
gh label create "wave-{X}" --description "Wave {X} (global id)" --color "8B5CF6"
```

### 2a. Pre-create the Project-2 Wave field option (MANDATORY — before label-apply)

**Run this BEFORE Step 7 (label-apply).** The `post_label_change_wave_field_sync`
PostToolUse hook syncs the Wave single-select field when a wave label is applied;
if the option for the new wave does not exist yet the hook can't sync and emits
"Project 2 Wave field has no option 'W{X}'" for every labeled issue — 8 such
captures in P6W17 alone (issue #868, P6W17 retro proposed change #1).

Option-name grammar (#810): `wave-{X}` → `W{X}`; `p{N}-wave-{M}` → `P{N}W{M}`;
`wave-x` → `WX`.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
# Idempotent: no-op if W{X} already exists; creates it if absent and
# read-back-verifies it stuck.  Exits 1 on auth/network/mutation error.
python3 "$REPO_ROOT/.claude/lib/wave_field_option.py" ensure "wave-{X}"
```

**Stop-the-line if this exits non-zero.** A non-zero exit means either the `project`
OAuth scope is missing (`gh auth refresh -s project` to fix) or the GraphQL
mutation failed. Label-apply MUST NOT proceed while the option is absent — every
labeled issue will fire an unresolvable hook capture.

**Verification (read-only check after creation):**

```bash
python3 "$REPO_ROOT/.claude/lib/wave_field_option.py" check "wave-{X}"
# exit 0 = present (proceed); exit 2 = absent (stop); exit 1 = error (stop)
```

Implementation: `.claude/lib/wave_field_option.py` (issue #868). Uses
`updateProjectV2Field` with the full-list-preserve recipe — re-reads all
existing options and re-sends them plus the new one so no option is wiped.

### 3. Pre-wave auth/scope audit

Verify the gh token has the scopes needed for this wave's operations. GitHub periodically hardens scope enforcement (e.g., Projects v2 requires the explicit `project` write scope; classic-Projects API deprecation). A missing scope mid-wave consumes orchestrator + user time chasing OAuth flows.

```bash
gh api -i user 2>&1 | grep -i "x-oauth-scopes"
```

Required scopes (baseline for all waves):
- `repo` — issues, PRs, comments, code
- `read:org` — roster / label lookups
- `project` — adding issues/PRs to the board (`gh project item-add`)
- `workflow` — editing `.github/workflows/*` files
- `gist`, `admin:public_key` — retained from prior grants

If any required scope is missing, instruct the user:
```
gh auth refresh -h github.com -s {missing_scope}
```
Wait for confirmation that scopes are updated before proceeding. Do NOT begin wave assignment with known-missing scopes.

**Why:** Phase 2 Wave 8 surfaced the Projects v2 scope gap mid-retro while trying to add PR #122 to the board. Fixing it interactively consumed ~30 minutes. Catching this at wave-kickoff prevents mid-wave interruptions.

### 4. Pre-wave CI triage

Before assigning issues, verify CI health across all repos in the wave scope:

```bash
gh run list --repo noorinalabs/{repo} --branch main --limit 1 --json conclusion
```

For each repo:
- If `conclusion` is `"success"`, mark it green.
- If `conclusion` is `"failure"` or missing, create a GitHub issue in that repo:
  ```bash
  gh issue create --repo noorinalabs/{repo} --title "CI red on main — triage before wave-{X}" \
    --label "bug" --label "wave-{X}" \
    --body "CI is failing on main. This must be triaged before wave work begins on this repo."
  ```
- Present a summary table to the user:
  | Repo | CI Status | Issue |
  |------|-----------|-------|
  | `noorinalabs-isnad-graph` | pass / **FAIL** | — / #NNN |

Flag repos with known-red CI so engineers are not confused by pre-existing failures.

### 5. Cross-reference wave issues against recent merges

Before posting kickoff comments, check if any wave issues were already resolved:

```bash
gh pr list --repo noorinalabs/{repo} --state merged --limit 20 --json number,title,body
```

For each merged PR:
1. Extract `Closes #N`, `Fixes #N`, or `Resolves #N` references from the PR body and title.
2. Compare those issue numbers against the wave issue list.
3. If a match is found, flag it to the user:
   ```
   ⚠ Issue #{N} ("{title}") may already be resolved by PR #{M} ("{pr_title}").
   Verify before assigning — remove from wave if confirmed fixed.
   ```

Wait for user confirmation before proceeding with assignment. Remove any confirmed-resolved issues from the wave list.

### 6. Collect issue list and assignments

Prompt the user for:
- List of issue numbers for this wave
- Assignee for each issue (FIRSTNAME_LASTNAME label)
- Peer review pairings (reviewer for each engineer)

Validate all assignee labels exist before proceeding:

```bash
gh label list --search "FIRSTNAME"
```

Create any missing labels before applying.

### 7. Label all issues

For each issue, apply the wave label and assignee label:

```bash
gh issue edit {NUMBER} --add-label "wave-{X}" --add-label "{FIRSTNAME_LASTNAME}"
```

**The kickoff comment is posted automatically.** A `PostToolUse` hook (`.claude/hooks/post_wave_kickoff_comment.py`, closes #286) fires on the `--add-label "wave-{X}"` pattern (and the legacy `p{N}-wave-{M}` form), reads the matching assignment row from `cross-repo-status.json` `wave_{X}_scope.tier_*` arrays, and posts the charter-format kickoff comment to the issue. For the phase-agnostic label the hook recovers the (derived-display) phase from `current_phase`. Per `feedback_enforcement_hierarchy`: hook > skill > charter — the prior manual loop (old Step 8) could be skipped or partial-fail, the hook fires deterministically.

Hook behavior:
- Idempotent: re-applying the wave label after disposition correction does NOT double-post (the hook detects the charter heading `**Wave {M} Kickoff — Phase {N}**` in existing comments and skips).
- Meta-issue skip: when the labeled issue is `wave_{M}_meta_issue`, the per-issue kickoff is skipped (the meta-issue gets its own all-hands kickoff comment — see § 8 below).
- Failure-tolerant: if `wave_{M}_scope` is missing or the issue isn't in any tier, the hook logs to `.claude/annunaki/errors.jsonl` and lets the label-apply succeed. A missing scope row is a `/wave-scope` bug, not a label-apply bug.

### 7a. Per-wave orchestration scripts (optional automation)

For waves with many issues across many repos, the labeling + project-board adds in step 7 may be automated by a per-wave orchestration script. Write these scripts to `.claude/skills/wave-kickoff/_orchestration/` using the naming convention `w{N}-{purpose}.py` (e.g., `w5-kickoff.py`, `w5-project-add.py`). The directory is tracked for audit-trail visibility (see #247). Do NOT use `.claude/scratch/` — that location is gitignored and reserved for true ephemeral artifacts (commit messages, mid-task notes).

### 8. Post the meta-issue all-hands kickoff comment

The per-issue kickoff comments (charter format with `Requestor: Fatima Okonkwo`, `Requestee: {Implementer}`) are posted automatically by the hook described in § 7. **This step covers only the meta-issue kickoff** — a single all-hands comment on the wave meta-issue (`wave_{M}_meta_issue`) summarizing the wave theme, all participating implementers, and tier breakdown. Format and exact text vary by wave; recent precedent is #284 (W6) — read it before authoring.

If the wave has no meta-issue (rare; pre-#284 waves), skip this step.

### 9. Ontology librarian — both bakes required (MANDATORY)

**Two hooks enforce this independently, so both steps are required:**

**(a) Orchestrator bakes librarian output into the spawn prompt** — `enforce_ontology_context.py` scans the Agent tool prompt for the literal heading `## Ontology Context` and **blocks** the spawn if absent.

**Coordinator-class exemption (#468):** the `## Ontology Context` bake is REQUIRED for implementer-class spawns and OPTIONAL for coordinator-class spawns (Manager, Pipeline Manager, Project Lead, Program Director, TPM / Technical Program Manager, Release Coordinator). The hook's `COORDINATOR_ROLE_OPENER` regex matches the canonical `You are **{Name}**, {Role}[ for {repo}]` opener and exempts these spawns from step (a). Step (b) below — instructing the agent to run `/ontology-librarian` themselves — still applies to coordinators that may Edit/Write, since Hook 15 fires independently at the Edit/Write surface. Note: spawn-brief composers must canonicalize role titles to the exempt enumeration — e.g., `"Infrastructure Manager"` → `, Manager` for the regex match.

For each implementer in the wave:
1. Identify the repos and code areas they'll modify
2. Run the librarian with a descriptive query:
   ```
   /ontology-librarian {repo} {area being modified}
   ```
3. Include the librarian's output (entities, services, conventions, stale warnings) in the agent's spawn prompt under a `## Ontology Context` section (literal heading — the hook matches on it)

**(b) Instruct the agent to run `/ontology-librarian` themselves as their FIRST action** — Hook 15 (`enforce_librarian_consulted.py`) scans the spawned agent's own transcript independently. Passing baked context from the orchestrator is not enough; Hook 15 still blocks Edit/Write/NotebookEdit until the agent invokes the librarian in their own session.

Spawn prompt pattern that satisfies both:
```
## MANDATORY first action
Run `/ontology-librarian {topic}` **yourself** in this session before any Edit/Write. Hook 15 scans your transcript.

## Ontology Context
(Baked from orchestrator's librarian run. Contents here.)
```

**Why:** In P2W3, running the librarian before spawning agents identified 10 stale issues — saving significant wasted effort. In P2W10 kickoff, the orchestrator forgot the `## Ontology Context` heading on 3 parallel spawns and all 3 were blocked.

### 9a. Delegation pattern — orchestrator spawns, managers request

Per charter `agents.md` § Hub-and-Spoke Orchestration Model + § Single-Leader Constraint:

- **Only the orchestrator (team lead) can call Agent.** Managers and implementers do not have the Agent tool.
- **Single team per session** — the harness provides one implicit team per session (no `TeamCreate`/`TeamDelete` tools). Spawn via the `Agent` tool with `team_name: "noorinalabs"` for cross-repo waves.
- **Managers request implementer spawns** via `SendMessage` to the team lead with full context (name, roster file, issue, branch, reviewers, Contract ownership if applicable).
- **Team lead spawns each implementer** following step 9 above (both bakes).
- **Isolation: every implementer spawn MUST set `isolation: "worktree"`,** even when the parent-side worktree is cosmetic (child-repo work). Per charter `agents.md` § Spawn Isolation Default. The cost is a temporary parent-repo worktree per agent (auto-cleaned if no changes); the benefit is correct workspace-presentation in the harness UI (the operator sees agents under team membership rather than as anonymous background tasks) and consistent Hook 14 (`enforce_ontology_context`) enforcement.

When composing spawn prompts for implementers, pull the manager's specified reviewer pairings, branch names, and Contract expectations into the prompt so the implementer starts with full context.

### 9b. Track each spawned implementer with TaskCreate (Mandatory — added P5W2 retro 2026-06-14)

**Every implementer spawn MUST have a corresponding `TaskCreate` entry** (subject = the issue ref + slug, owner = the implementer name) created at spawn time. The orchestrator owns the task list as the live ledger of in-flight wave work.

**Why:** P5W2 spawned implementers for all scoped issues, but no tasks were tracked. The keystone bug (#1024 narrators-500) implementer produced **zero output** — no branch, no PR, no commit — and because `TaskList` was empty, the stall was **invisible** until the owner manually asked about it near end-of-wave. The keystone nearly didn't ship. A tracked task makes a zero-output stall surface at the next status sweep instead of at a manual nudge.

**Mechanics:**
- At spawn (step 9 / 9a), call `TaskCreate` for each implementer: subject `"{repo}#{issue} — {slug}"`, owner = implementer name, plus the reviewer pairing in the description.
- Mid-wave, `TaskList` is the at-a-glance stall detector: any task still `pending`/`in_progress` with **no branch/PR** is a potential stall. Apply the liveness threshold from charter `agents.md § Agent Liveness Checkpoint, Part (b)`: after **two idle notifications with zero artifact** (no branch, no PR, no commit), auto-flag for takeover — do not wait for a third notification. "Reasonable interval" means two zero-artifact idle notifications, not elapsed time alone.
- `/wave-wrapup` and `/wave-retro` cross-check the task list against merged PRs; a task with no delivered PR is a scope-drop or substitution to reconcile explicitly (already required by those skills' reconciliation steps — this makes the input ledger reliable).

This is the input-side counterpart to the wrapup scope-drop / implementer-substitution reconciliation: those catch silent drops/swaps at *close*; the task ledger catches a zero-output stall *during* the wave.

### 10. Output execution plan

Generate and display a structured execution plan with:
- **Priority ordering:** hotfixes first, then security fixes, then bugs, then features (per charter § Wave Planning & Priority)
- **Issue table:** number, title, assignee, reviewer, priority tier
- **Dependencies:** any cross-PR dependencies identified
- **Estimated parallelism:** which issues can run concurrently

### 11. Report

Present the full plan to the user. Do NOT begin implementation until the user approves.

## What remains manual

- User must approve the execution plan before implementation starts
- User decides which issues to include in the wave
- Cross-team dependency resolution still requires lead coordination
