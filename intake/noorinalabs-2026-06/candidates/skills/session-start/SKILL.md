---
name: session-start
description: "MANDATORY first action in every session — runs full startup protocol (worktree, team, handoff, ontology, annunaki, wave, charter)"
---

# Session Start Protocol

**This skill MUST be invoked as the FIRST action in every new session.** Do not respond to the user's message, do not read files, do not run any other tool — invoke `/session-start` first. The user's actual request is handled AFTER this completes.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Session Lifecycle for the canonical skill order and preconditions.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149). `$REPO_ROOT` is anchored to the **parent org repo** deterministically via the parent of `git rev-parse --git-common-dir` (not `--show-toplevel`, which resolves to a worktree if run from one) and verified against the parent marker `cross-repo-status.json` + `CLAUDE.md` (#533). Each bash block re-derives it, since Skill blocks run as independent shells.

## Instructions

Execute all 7 steps below. Steps that are independent of each other SHOULD run in parallel. Present results in a single concise status table at the end.

### Step 0 — Worktree cleanup (parent + child repos)

Worktrees accumulate in BOTH the parent repo and every child repo (under
`<child>/.claude/worktrees/`, `<child>/.worktrees/`, and sometimes `/tmp/`).
Prior to #526, Step 0 only cleaned the parent — on 2026-05-24 ~33 stale
child-repo worktrees were found uncaught. The block below iterates the parent
and all 7 child repos, applying a **verify-merged-then-remove guard**:

- **Auto-remove** a worktree only when its HEAD is an ancestor of that repo's
  `origin/main` (i.e. the branch is fully merged). Safe to drop.
- **FLAG (list, do not remove)** any worktree that is NOT verified-merged
  (work in flight, superseded, or closed-issue cases) and any **locked**
  worktree (e.g. the `/tmp/hotfix-user-service` lock case). Surface these for
  a manual decision — never auto-remove unmerged work.

```bash
# Anchor REPO_ROOT to the PARENT org repo deterministically (#533). Using a
# bare `git rev-parse --show-toplevel` resolves to a WORKTREE if /session-start
# is ever invoked from one, which silently breaks child-repo discovery below
# (the `$REPO_ROOT/$child/.git` probes find nothing). --git-common-dir points
# at the MAIN repo's `.git` even from a linked worktree, so its parent is the
# real org root in both the parent-checkout and run-from-worktree cases. We
# then verify the parent marker (cross-repo-status.json + CLAUDE.md) and warn
# loudly rather than silently skip children if it isn't found.
resolve_repo_root() {
  local common_dir candidate
  common_dir="$(git rev-parse --git-common-dir 2>/dev/null)" || common_dir=""
  if [ -n "$common_dir" ]; then
    candidate="$(cd "$common_dir/.." 2>/dev/null && pwd)"
  fi
  if [ -z "$candidate" ]; then
    candidate="$(git rev-parse --show-toplevel 2>/dev/null)"
  fi
  if [ -n "$candidate" ] && [ -f "$candidate/cross-repo-status.json" ] && [ -f "$candidate/CLAUDE.md" ]; then
    printf '%s\n' "$candidate"; return 0
  fi
  printf 'WARN: parent-repo marker not found under %s — child-repo discovery may be incomplete. ' "${candidate:-<unresolved>}" >&2
  printf 'Run /session-start from the parent main checkout (its mandated invocation path).\n' >&2
  printf '%s\n' "${candidate:-$(pwd)}"; return 1
}
REPO_ROOT="$(resolve_repo_root)"

# Pick up any merges/pushes to origin/main since last session (main#713) so the
# session never runs pre-fix hooks/skills off a stale checkout (the failure this
# session hit: opened 22 commits behind, ran the pre-#709 reader). The helper is
# fully guarded — it fast-forwards only a clean, strictly-behind main and refuses
# (no-op) on a diverged/ahead/dirty tree; it never forces or discards local work.
# Non-fatal: a refusal or error must never block session-start.
if [ -f "$REPO_ROOT/.claude/lib/sync_main.py" ]; then
  python3 "$REPO_ROOT/.claude/lib/sync_main.py" "$REPO_ROOT" || true
fi

# Refresh + staleness-guard the embedded child-repo checkouts (#832) — the
# sibling of the sync_main parent fast-forward above, for the children. The
# parent .gitignore's its child clones and they drift badly (during p6-wave-16
# user-service was parked on a phase-3 commit and isnad-graph sat ~207 commits
# behind origin/main — the root cause of #816 and of any agent that reads a
# stale child clone directly). Same safety stance as sync_main: a child that is
# clean and on main is fast-forwarded to origin/main (--ff-only, never force);
# a child that is dirty, diverged, or parked on an old feature branch is FLAGGED
# for a manual decision and left untouched — there is no force-discard path.
# Non-fatal: a flagged/refused child is a SAFE outcome and never blocks session-start.
if [ -f "$REPO_ROOT/.claude/lib/check_child_checkouts.py" ]; then
  python3 "$REPO_ROOT/.claude/lib/check_child_checkouts.py" "$REPO_ROOT" --refresh || true
fi

# Parent repo + the 7 canonical child repos (CLAUDE.md Repository Map).
REPOS=("$REPO_ROOT")
for child in \
  noorinalabs-isnad-graph \
  noorinalabs-user-service \
  noorinalabs-deploy \
  noorinalabs-design-system \
  noorinalabs-data-acquisition \
  noorinalabs-isnad-ingest-platform \
  noorinalabs-landing-page; do
  [ -d "$REPO_ROOT/$child/.git" ] && REPOS+=("$REPO_ROOT/$child")
done

FLAGGED=()
for repo in "${REPOS[@]}"; do
  git -C "$repo" worktree prune
  # Refresh remote tip so the merged-ancestor test is accurate.
  git -C "$repo" fetch --quiet origin main 2>/dev/null || true
  main_repo="$(git -C "$repo" rev-parse --show-toplevel)"

  # Walk worktrees in porcelain form. Records are blank-line separated;
  # fields we care about: worktree <path>, HEAD <sha>, locked [<reason>].
  # Capture porcelain output to a temp file (with a trailing blank line so the
  # last record is flushed) and feed the loop from it — see the note at `done`
  # below for why a temp file rather than `< <(...)` process substitution.
  _wtfile="$(mktemp)"
  { git -C "$repo" worktree list --porcelain; echo; } > "$_wtfile"
  wt="" head="" locked=0
  while IFS= read -r line; do
    case "$line" in
      "worktree "*) wt="${line#worktree }"; head=""; locked=0 ;;
      "HEAD "*)     head="${line#HEAD }" ;;
      "locked"*)    locked=1 ;;
      "")  # end of a record — evaluate it
        [ -z "$wt" ] && continue
        if [ "$wt" = "$main_repo" ]; then wt=""; continue; fi  # skip main checkout
        if [ "$locked" -eq 1 ]; then
          FLAGGED+=("LOCKED  $repo :: $wt")
        elif [ -n "$head" ] && git -C "$repo" merge-base --is-ancestor "$head" origin/main 2>/dev/null; then
          echo "removing merged worktree: $wt"
          git -C "$repo" worktree remove "$wt" 2>/dev/null \
            || git -C "$repo" worktree remove --force "$wt" 2>/dev/null \
            || FLAGGED+=("REMOVE-FAILED  $repo :: $wt")
        else
          FLAGGED+=("UNMERGED  $repo :: $wt (HEAD ${head:-?})")
        fi
        wt="" ;;
    esac
    # NB: the loop is fed from a temp FILE (not a `< <(...)` process
    # substitution) so the whole Step-0 block stays statically analyzable by
    # the Claude Code permission engine — process substitution trips the
    # "shell syntax that cannot be statically analyzed" path and forces a
    # prompt regardless of the allowlist (main, 2026-06-23). A file redirect
    # is analyzable AND keeps the loop in the current shell, so the FLAGGED
    # array accumulation below survives past `done` (a `| while` pipe would
    # run the body in a subshell and silently drop it).
  done < "$_wtfile"
  rm -f "$_wtfile"
done

echo "--- remaining worktrees (parent + children) ---"
for repo in "${REPOS[@]}"; do git -C "$repo" worktree list; done

if [ "${#FLAGGED[@]}" -gt 0 ]; then
  echo "--- FLAGGED for manual decision (NOT removed) ---"
  printf '%s\n' "${FLAGGED[@]}"
fi
```

Report how many merged worktrees were auto-removed and surface the FLAGGED
list (locked + unmerged) to the user for a manual call. Do not force-remove a
FLAGGED worktree without explicit confirmation.

Also report the **child-repo checkout** result from `check_child_checkouts.py`
(#832): how many child clones were fast-forwarded to `origin/main`, and surface
its FLAGGED block (children that are dirty, diverged, or parked on an old feature
branch — these are left untouched and need a manual call). A child sitting many
commits behind `origin/main` is the root cause of stale on-disk child configs
(#816) and of any agent that reads the clone directly drawing wrong conclusions.

### Step 1 — Team orientation

> **Harness note (2026-06-16):** the current Claude Code harness has **no `TeamCreate`/`TeamDelete` tools**. The session runs on a **single implicit team** — there is nothing to tear down or create, and nothing to go stale. (Earlier harness versions exposed explicit team tools and this step ran `TeamDelete` then `TeamCreate`; that is now a no-op and has been removed.)

There is no action to take here beyond confirming the model:

- Spawning is done with the **`Agent` tool**, passing `team_name: "noorinalabs"` for cross-repo wave work. The orchestrator is the sole `Agent`-tool caller.
- Spawned agents join the single implicit `noorinalabs` team automatically; they cannot themselves spawn.

Report "Single implicit team (no create/delete tools in this harness)" and move on.

> **Single-leader constraint:** All managers and implementers spawned during the session — regardless of which repo they work on — belong to the single `noorinalabs` team. See charter `agents.md` § Single-Leader Constraint for the delegation pattern (orchestrator is the sole `Agent`-tool caller; managers `SendMessage` the orchestrator to request implementer spawns).

### Step 2 — Handoff check

Read the session handoff file from in-repo project memory (relocated #732 — memory is now version-controlled at `.claude/memory/`, not the user-space `~/.claude/projects/<cwd>/memory/` path):

```
Read: .claude/memory/session_handoff.md
```

If it exists, extract:
- What was done last session
- What's next
- Current branch, open PRs, open issues
- Any user notes

Summarize in 2-3 sentences. If the file doesn't exist, note "No handoff from previous session."

### Step 3 — Ontology freshness (semantic overlay + structural index)

The ontology has two independent layers that need separate freshness checks (#820/C×T2, #862):

**3a. Semantic overlay** — run `/ontology-rebuild` to resolve dirty checksums from the previous session:
- If 0 dirty files in `checksums.json`, report "Semantic overlay: current" and move on
- If dirty files exist, process them and commit the result

**3b. Structural index** — check whether the generated index at `ontology/structural/llms.txt` is stale relative to the current source tree, and regenerate if it is:

```bash
# Re-anchor REPO_ROOT to the parent (independent shell block — see Step 0 / #533).
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"

# Commit that last produced the structural index
STRUCT_SHA=$(git -C "$REPO_ROOT" log -1 --format="%H" -- ontology/structural/llms.txt 2>/dev/null || echo "")

if [ -z "$STRUCT_SHA" ]; then
  CHANGED="new"
else
  CHANGED=$(git -C "$REPO_ROOT" diff --name-only "$STRUCT_SHA"..HEAD -- \
    '*.py' '*.ts' '*.tsx' '*.js' '*.jsx' '*.cypher' '*.cql' 2>/dev/null | wc -l | tr -d ' ')
fi

if [ "${CHANGED:-0}" = "0" ]; then
  echo "Structural index: current (${STRUCT_SHA:0:8})."
else
  echo "Structural index: ${CHANGED} source file(s) changed since ${STRUCT_SHA:0:8} — regenerating."
  PYTHONPATH="$REPO_ROOT/.claude/lib" python3 -m ontology_gen \
    "$REPO_ROOT" --out "$REPO_ROOT/ontology/structural/" 2>&1 \
    && PYTHONPATH="$REPO_ROOT/.claude/lib" python3 -m ontology_gen.aggregate \
       "$REPO_ROOT" 2>&1 \
    || echo "WARN: structural index regeneration failed — index stays at last committed state."
fi

# Commit regenerated files (if any changed)
if ! git -C "$REPO_ROOT" diff --quiet ontology/structural/; then
  git -C "$REPO_ROOT" add ontology/structural/
  MSGFILE="$(mktemp)"
  printf 'ontology: regenerate structural index (session-start 3b)\n\nSource files changed since last generation; re-ran ontology_gen + aggregate.\n' \
    > "$MSGFILE"
  git -C "$REPO_ROOT" \
    -c user.name="Aino Virtanen" \
    -c user.email="parametrization+Aino.Virtanen@gmail.com" \
    commit -F "$MSGFILE"
  rm -f "$MSGFILE"
  echo "Structural index regenerated and committed."
fi
```

Report both results in the Step output table:
- `3. Ontology | Semantic: {N dirty resolved / current}; Structural: {current @ sha / regenerated}`

**Non-fatal:** a generator failure MUST NOT block session-start. Report the failure and move on — the structural index stays at its last committed state until the next regeneration.

### Step 4 — Annunaki error check

Run `/annunaki` to check the error monitor.

- Report: hook active/inactive, error count, any new errors since last session
- If 5+ unprocessed errors, flag for `/annunaki-attack`
- If 0 errors or all are resolved PreToolUse blocks, report "No action needed"

### Step 5 — Wave/phase orientation

Read the current project state:

```bash
# Re-anchor REPO_ROOT (each Skill bash block is an independent shell — the
# Step 0 value does not carry over). Same parent-anchor as Step 0 (#533):
# parent of --git-common-dir resolves the org root even from a worktree.
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
cat "$REPO_ROOT/cross-repo-status.json"
gh issue list --repo noorinalabs/noorinalabs-main --state open --limit 10 --json number,title,labels
```

Report:
- Active wave and phase
- Whether `cross-repo-status.json` is stale (check `last_updated` fields)
- Open issue count and any blockers
- Open PRs across repos

If the report surfaces unexpected gaps between board view and open-issue counts (e.g., wave-labeled issues missing from project 2, or Wave-field values out of sync with the wave labels (`wave-{X}` or grandfathered `p{N}-wave-{M}`, #810)), invoke `/board-audit` to detect and (with confirmation) repair the drift. Per main#199, labels are canonical and the project's Wave field is a derived projection synced by `/board-audit`.

### Step 5a — Red default-branch workflow detection (P3W14 retro Proposed Change #2)

Surface any **publish/deploy/release workflow whose latest run on the repo's default branch FAILED**, across all org repos. *Rationale:* the GHCR frontend publish (isnad-graph commit 5804476) sat RED on `main` for ~12 days undetected — silently breaking every staging deploy at the frontend-pull step — because nothing surfaced a red default-branch publish at session start.

For each org repo, list the latest default-branch run of each workflow and flag any whose conclusion is `failure`/`timed_out`/`cancelled`, filtered to publish/deploy/release-class workflows (these are the ones whose redness silently rots — a red lint run is loud at PR time; a red publish on `main` is not). For each red run, attempt a **best-effort cause-classification** (P4W4 retro #3 / main#647): inspect the failed job log for base-image-CVE signals — `trivy`/`grype`/`apk`-CVE/`openssl`-class advisory failures — and tag those as a distinct **"base-image drift — fix-forward the base image, not a code regression"** class. This is non-fatal: a `gh api`/log-fetch failure degrades to the unclassified `code/other` tag, never to a false all-green.

```bash
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
# Primary: resolve the repo set from the canonical `current_wave` lifecycle
# pointer (e.g. "wave-5" -> `wave_5_repos_in_scope`), NOT `max_by` over the
# wave NUMBER. Completed *prior-phase* waves (e.g. `wave_7_repos_in_scope` from
# the P4 close-out) are legitimately retained, so "highest number" structurally
# picks a stale 2-repo scope over the live one — main#712 (same defect class as
# the current_wave reader fix #708/#709). `ltrimstr` is null-safe: a missing/
# malformed `current_wave` yields an absent key -> empty -> the hardcoded list.
REPOS=$(jq -r '
  (.current_wave // "" | ltrimstr("wave-")) as $n
  | .["wave_\($n)_repos_in_scope"][]? // empty
' "$REPO_ROOT/cross-repo-status.json" 2>/dev/null)
# Newline-separated fallback (one repo per line) so the `while read` loop below
# is correct under zsh — a space-separated string would be read as ONE line
# (zsh does not word-split an unquoted scalar; #759 / main#688). jq above already
# emits newlines, so both sources share the same shape.
[ -n "$REPOS" ] || REPOS=$(printf '%s\n' \
  noorinalabs-main noorinalabs-isnad-graph noorinalabs-user-service \
  noorinalabs-deploy noorinalabs-design-system noorinalabs-data-acquisition \
  noorinalabs-isnad-ingest-platform noorinalabs-landing-page)

# Best-effort cause classification for a red run (main#647). Echoes "base-image-drift"
# when the failed job log carries a base-image-CVE signal, else "code/other". Never fatal:
# a missing/undownloadable log degrades to "code/other", never a false all-green.
classify_red() {  # $1=repo  $2=run_id
  local log
  log=$(gh run view "$2" --repo "noorinalabs/$1" --log-failed 2>/dev/null) || { echo "code/other"; return 0; }
  if printf '%s' "$log" | grep -Eiq 'trivy|grype|\bCVE-[0-9]{4}-[0-9]+|apk[ -].*(upgrade|CVE)|openssl.*(vuln|CVE|advisor)|base[ -]image'; then
    echo "base-image-drift"
  else
    echo "code/other"
  fi
}

RED=()
# `while read` over the newline-list, NOT `for repo in $REPOS` — zsh does not
# word-split an unquoted scalar (#759 / main#688). Both loops below are fed from
# temp FILES rather than a `<<<` here-string / `< <(...)` process substitution:
# those constructs trip the Claude Code permission engine's "shell syntax that
# cannot be statically analyzed" path and force a prompt regardless of the
# allowlist (main, 2026-06-23). A file redirect is analyzable AND — like the
# here-string it replaces — keeps the loop in the current shell, so the RED
# array survives past `done` (a `| while` pipe would drop it to a subshell).
_repofile="$(mktemp)"
printf '%s\n' "$REPOS" > "$_repofile"
while IFS= read -r repo; do
  [ -n "$repo" ] || continue
  branch=$(gh api "repos/noorinalabs/$repo" --jq '.default_branch' 2>/dev/null || echo main)
  # Latest run per workflow on the default branch; keep only publish/deploy/release-class names with a non-success conclusion.
  _runsfile="$(mktemp)"
  gh api "repos/noorinalabs/$repo/actions/runs?branch=$branch&per_page=50" \
    --jq '[.workflow_runs[] | select((.name // .display_title) | test("publish|deploy|release|promote|ghcr|image";"i"))]
          | group_by(.workflow_id) | map(max_by(.run_started_at))
          | .[] | [(.name // .display_title), .conclusion, .html_url, .id] | @tsv' 2>/dev/null > "$_runsfile"
  while IFS=$'\t' read -r name conclusion url run_id; do
    case "$conclusion" in
      failure|timed_out|cancelled|startup_failure)
        cls=$(classify_red "$repo" "$run_id")
        RED+=("$repo :: $name :: $conclusion :: $cls :: $url") ;;
    esac
  done < "$_runsfile"
  rm -f "$_runsfile"
done < "$_repofile"
rm -f "$_repofile"
if [ ${#RED[@]} -gt 0 ]; then
  printf 'RED default-branch publish/deploy run(s) — investigate before relying on staging:\n'
  printf '  %s\n' "${RED[@]}"
  if printf '%s\n' "${RED[@]}" | grep -q 'base-image-drift'; then
    printf '\n  NOTE: run(s) tagged "base-image-drift" failed on a base-image-CVE signal (trivy/grype/apk/openssl-class advisory),\n'
    printf '  NOT a code regression — fix-forward the base image (rebuild/bump the upstream image), do not chase the wave diff.\n'
  fi
else
  echo "All publish/deploy/release workflows green on default branches."
fi
```

Report any red runs prominently — a red publish/deploy on a default branch is a stop-and-investigate signal, not background noise: it usually means the artifact consumers (staging, downstream pulls) are silently running stale or broken bits. A run tagged `base-image-drift` is a different remediation path than generic redness: the wave's code did not break it — an upstream base image grew a new advisory (e.g. the W4 openssl CVE-2026-45447) — so fix it forward by rebuilding/bumping the base image, not by reverting wave work. If `gh api` calls fail (auth/rate-limit), say so rather than reporting a false all-green; the classifier itself is best-effort and degrades to the unclassified `code/other` tag on any log-fetch failure.

### Step 5b — Wave-merged-but-unwrapped nudge (P5W5 retro Proposed Change #1 / #730)

Surface a wave whose PRs **merged to main but which was never formally wrapped**. *Rationale:* P5W5 merged all 45 of its PRs days before `/wave-wrapup` ran — `wave_5_wrapped_up_at` stayed null, `wave_5_active` stayed true, and the post-wave audits (annunaki-attack, memory) never ran — because nothing at session-start surfaced the gap, so wrap/retro deferred indefinitely.

The signal is the conjunction `wave_{M}_active == true` AND no wrapup marker present (`wave_{M}_wrapped_up_at` / `wave_{M}_wrapup_completed_at` / `wave_{M}_wrapped_at`) AND **0 open wave PRs** across the wave's in-scope repos — scoped to the **current** wave (`current_wave`) only. Scoping to `current_wave` is load-bearing: wave keys are NOT phase-namespaced (memory `project_wave_key_cross_phase_collision` / #683), so the status file legitimately retains stale `wave_4_active: true` rows from a prior phase's W4 — an "any active+unwrapped wave" scan would false-fire on those ghosts. The detection is **non-fatal** and degrades gracefully: a missing `current_wave`, missing scope keys, or a failed `gh` probe yields a benign verdict (never a hard block, never a false nudge mid-wave).

```bash
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
# Always exits 0 (informational nudge, not a gate). Prints a line beginning
# "NUDGE:" only when the wave is merged-but-unwrapped (or active+unwrapped with
# an undetermined open-PR count); otherwise a one-line in-flight/ok status.
if [ -f "$REPO_ROOT/.claude/lib/wave_unwrapped.py" ]; then
  python3 "$REPO_ROOT/.claude/lib/wave_unwrapped.py" check \
    --status "$REPO_ROOT/cross-repo-status.json" || true
fi
```

If the verdict is `unwrapped` (0 open wave PRs) — or the softer `unwrapped_unverified` (open-PR count undetermined because `gh` failed or the wave's scope keys are missing) — surface it prominently as **"wave merged but unwrapped — run `/wave-wrapup`"**. An `in_flight` verdict (open wave PRs remain) is a normal active wave: no nudge. This is informational only — it never blocks the session.

### Step 5c — Wave-branch reachability / merge-model check (main#801)

Surface **mid-wave** any wave-branch commit that is not reachable from `origin/main`, classified against the wave's declared merge model — so model-mixing or stranding surfaces within hours instead of only at the `/wave-wrapup` Step 11.5 gate. *Origin:* P6W1 mixed merge models (some PRs to the wave branch, the doc batch direct to main, no wave→main PR opened) → 5 deliverables stranded off main, caught only at wrapup (charter `pull-requests.md § One Merge Model Per Wave`).

This is a deterministic helper (`.claude/lib/wave_merge_model.py reachability`), model-aware: a `direct-to-main` wave with commits on its wave branch is a hard **VIOLATION** (the P6W1 mixing); a `wave-branch` wave ahead of main with an open wave→main PR is **OK**, and ahead with no PR is an **ADVISORY** stranding-risk reminder. A wave with no declared model (legacy / pre-#801) degrades to advisory-only with a nudge — never a false violation. Non-fatal: a gh/scope error must not block session-start.

```bash
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
# Derive the live phase/wave from the canonical lifecycle pointers (NOT a max
# over wave numbers — retained prior-phase scopes would mis-select; cf. #712).
PHASE=$(jq -r '.current_phase // empty' "$REPO_ROOT/cross-repo-status.json" 2>/dev/null)
WAVE=$(jq -r '(.current_wave // "" | ltrimstr("wave-"))' "$REPO_ROOT/cross-repo-status.json" 2>/dev/null)
if [ -n "$PHASE" ] && [ -n "$WAVE" ] && [ -f "$REPO_ROOT/.claude/lib/wave_merge_model.py" ]; then
  # Helper prints the per-repo report; exit 1 ONLY on a model VIOLATION.
  python3 "$REPO_ROOT/.claude/lib/wave_merge_model.py" reachability "$PHASE" "$WAVE" \
    || echo "⚠ merge-model VIOLATION above — a wave branch carries commits the declared model forbids (#801). Investigate before merging more."
else
  echo "reachability check skipped — current_phase/current_wave not set or helper absent."
fi
```

Report any **VIOLATION** prominently (stop-and-investigate: a wave branch is accumulating work the declared model forbids — the P6W1 mixing). **ADVISORY** lines are reminders that wave-branch work will strand unless `/wave-wrapup` opens the wave→main PR — surface them but they do not block. **OK** across the board needs no action.

### Step 6 — Charter freshness check

Read the tail of the feedback log:

```bash
# Re-anchor REPO_ROOT to the parent (independent shell block — see Step 0 / #533).
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
[ -f "$REPO_ROOT/cross-repo-status.json" ] || REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
tail -40 "$REPO_ROOT/.claude/team/feedback_log.md"
```

Check for:
- Unapplied retro proposals (action items without corresponding changes)
- New hooks or skills introduced since the last charter update
- Any pending fire/hire actions

Report findings or "Charter is current."

## Output format

After all steps complete, present a single status block:

```
**Session Start — Complete**

| Step | Status |
|------|--------|
| 0. Worktree | {clean / N stale removed} |
| 0b. Child checkouts | {N fast-forwarded / M flagged (dirty/diverged/feature-branch) / all current} |
| 1. Team | {created fresh / error} |
| 2. Handoff | {summary} |
| 3. Ontology | Semantic: {N dirty resolved / current}; Structural: {current @ sha / regenerated / regen-failed} |
| 4. Annunaki | {N errors, action needed? / clear} |
| 5. Wave | {active wave, stale?, issues} |
| 5a. Red default-branch runs | {N red publish/deploy runs (M base-image-drift) / all green} |
| 5b. Wave wrap state | {wave merged but unwrapped — run /wave-wrapup / in flight / wrapped} |
| 5c. Wave reachability | {OK / N advisory (stranding risk) / VIOLATION (merge-model mixing) / skipped} |
| 6. Charter | {current / proposals pending} |

{Then address the user's actual message/request}
```

## What this skill does NOT do

- It does not begin any implementation work
- It does not create issues or PRs
- It does not modify the charter or team roster
- It only establishes situational awareness so the session starts informed
