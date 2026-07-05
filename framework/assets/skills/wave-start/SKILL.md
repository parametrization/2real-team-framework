---
name: wave-start
description: "Initialize a new wave"
---

# Wave Start

Initialize a new wave (`args`: phase number `{N}`, wave number `{M}`).

> Config-driven + fail-open: reads `.claude/framework.config.json` via `jq`; missing keys fall
> back to the documented defaults. This skill sets up wave infrastructure AND records the
> lifecycle state live (`allocate → start → scope`); the **kickoff transition** fires only
> after **explicit User approval** (step 7).

## Instructions

### 0. Resolve config + wave grammar

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CFG="$REPO_ROOT/.claude/framework.config.json"
get() { jq -r "$1 // empty" "$CFG" 2>/dev/null; }   # fail-open dotted read

N={phase}; M={wave}
DEFAULT_BRANCH="$(get '.scm.default_branch')"; : "${DEFAULT_BRANCH:=main}"
ONTO_DIR="$(get '.paths.ontology')";           : "${ONTO_DIR:=ontology}"
BRANCH_TMPL="$(get '.branch.integration')";    : "${BRANCH_TMPL:=deployments/phase{phase}/wave-{wave}}"
WAVE_BRANCH="$(printf '%s' "$BRANCH_TMPL" | sed "s/{phase}/$N/g; s/{wave}/$M/g")"
echo "Wave branch: $WAVE_BRANCH (default branch: $DEFAULT_BRANCH)"

# Framework libs: installed location first, framework-source checkout as fallback.
# Dual-deploy: bootstrap copies assets/lib → a deployed repo's .claude/lib; the
# framework SOURCE repo has no .claude/lib, so it falls back to framework/assets/lib.
LIB="$REPO_ROOT/.claude/lib"
[ -f "$LIB/lifecycle.py" ] || LIB="$REPO_ROOT/framework/assets/lib"   # framework source repo

# Merge model this wave lives under (one model for its whole life — mixing strands work).
# Config default; the owner confirms/overrides at the kickoff gate (step 7).
MERGE_MODEL="$(get '.policy.merge_model')"; : "${MERGE_MODEL:=direct-to-main}"
```

### 1. Clean stale worktrees

```bash
git -C "$REPO_ROOT" worktree prune
git -C "$REPO_ROOT" worktree list
```

Report any worktrees that were pruned. If active worktrees remain, list them and confirm with
the user before proceeding (they may belong to in-progress work).

### 2. Park the orchestrator's checkout on the fresh default branch — STOP-guards

Get the orchestrator's checkout onto a clean, up-to-date `$DEFAULT_BRANCH` **before** any
branch work. Without this, a wave can be cut while the working tree sits on a stale,
already-merged feature branch, and any local commit lands against a stale base.

This step **guards** rather than auto-discards — only regenerable session churn may be set
aside. If there is genuine uncommitted or unmerged work, it STOPs so the operator decides.

```bash
cd "$REPO_ROOT"
git fetch origin "$DEFAULT_BRANCH"

# REGENERABLE allowlist — paths that regenerate every session and may be safely
# stashed (NOT a reason to STOP): the generated structural ontology layer
# (code-graph.json / llms.txt / cross-repo-graph.json, rebuilt by the
# ontology_refresh hook) and the checksum tracker (re-tracked on next edit).
REGENERABLE="^($ONTO_DIR/structural/|$ONTO_DIR/checksums\.json$)"

# Guard A — non-regenerable uncommitted changes → STOP (do NOT auto-discard).
# `cut -c4-` takes the path field of `git status --porcelain` (handles spaces/renames).
NON_REGEN_DIRTY=$(git status --porcelain | cut -c4- | grep -vE "$REGENERABLE" || true)
if [ -n "$NON_REGEN_DIRTY" ]; then
  echo "STOP: working tree has non-regenerable uncommitted changes:"
  echo "$NON_REGEN_DIRTY" | sed 's/^/  /'
  echo "Commit, stash, or discard them deliberately before /wave-start — this skill will not auto-discard."
  exit 1
fi

# Guard B — current branch is ahead of origin (unmerged local work) → STOP.
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
AHEAD=$(git rev-list --count "origin/$DEFAULT_BRANCH..HEAD")
if [ "$AHEAD" -gt 0 ]; then
  echo "STOP: current branch '$CURRENT_BRANCH' is $AHEAD commit(s) ahead of origin/$DEFAULT_BRANCH (unmerged work)."
  echo "Land or set it aside before starting a wave — this skill will not auto-discard."
  exit 1
fi

# Safe to park: stash only the regenerable churn (recoverable via `git stash list`), then
# move to the fresh default branch with a fast-forward-only pull (never a merge commit).
git stash push -- "$ONTO_DIR/structural" "$ONTO_DIR/checksums.json" 2>/dev/null || true
git checkout "$DEFAULT_BRANCH"
git pull --ff-only origin "$DEFAULT_BRANCH"

# Assert: on a clean default branch before proceeding.
test "$(git rev-parse --abbrev-ref HEAD)" = "$DEFAULT_BRANCH" || { echo "STOP: not on $DEFAULT_BRANCH after checkout"; exit 1; }
test -z "$(git status --porcelain | cut -c4- | grep -vE "$REGENERABLE" || true)" \
  || { echo "STOP: $DEFAULT_BRANCH checkout is not clean after pull"; exit 1; }
echo "Parked on clean $DEFAULT_BRANCH @ $(git rev-parse --short HEAD)"
```

If either guard STOPs, surface the reason to the user and **wait — do not work around it**.
(zsh note: the block above avoids bash-isms; it runs the same under zsh and bash.)

### 3. Determine base branch

The base is the previous wave's deployments branch if it exists and is still unmerged
(waves in one release train stack); otherwise the default branch.

```bash
git -C "$REPO_ROOT" ls-remote --heads origin "deployments/phase$N/*"
```

If unsure which applies, present the candidates to the user and confirm.

### 4. Create and push the wave branch

```bash
git -C "$REPO_ROOT" checkout -b "$WAVE_BRANCH" "{base_branch}"
git -C "$REPO_ROOT" push -u origin "$WAVE_BRANCH"
```

### 5. Record lifecycle state (allocate → start → scope)

Write the wave into the lifecycle state file **live** — this is what lets retros read
`state.json` instead of backfilling it by hand. The state file is config'd
(`paths.state_file`, default `.claude/state.json`) and owned by `lifecycle.py`.

```bash
python3 "$LIB/lifecycle.py" wave peek                          # preview the next id (no write)

# Idempotency: if this wave was already allocated (a re-run of /wave-start), skip the
# allocate below and reuse its id from `lifecycle.py state show` — allocate --write
# advances the monotonic counter and must run exactly once per wave.
W="$(python3 "$LIB/lifecycle.py" wave allocate --phase "$N" --write | sed -n 's/^wave id: //p')"
echo "Allocated global wave id: $W  (display: Phase $N, Wave $M)"

python3 "$LIB/lifecycle.py" wave start "$W"
python3 "$LIB/lifecycle.py" wave scope "$W" --repos "$(get '.project.name')" --phase "$N"
python3 "$LIB/lifecycle.py" state show
```

`allocate --write` advances the monotonic `global_wave_seq` and stamps `wave_{W}_phase` +
`wave_{W}_phase_ordinal` (the "Phase N, Wave M" display); `start` sets `current_wave`,
`wave_{W}_active=true`, `wave_{W}_started_at`; `scope` records `wave_{W}_repos_in_scope` +
`wave_{W}_scope_reconciled_at`. For a multi-repo (meta) project pass the comma-separated
in-scope subset to `--repos` instead of the single project name.

### 6. Run retro

Run the `/retro` skill if this is not the first wave, so carry-over items from the previous
wave are surfaced before new work starts.

### 7. Kick off (User approval gate)

Wave kickoff requires **explicit User approval** — present the plan and wait for the
go-ahead. **Only after** the User approves, record the kickoff transition live:

```bash
python3 "$LIB/lifecycle.py" wave kickoff "$W" --merge-model "$MERGE_MODEL"
```

This stamps `wave_{W}_kicked_off_at`, declares `wave_{W}_merge_model`, and re-points
`current_wave`. Confirm the model with the User first: a wave whose per-issue PRs base on
the integration branch is `wave-branch`; one whose PRs base straight on the default branch
is `direct-to-main`. Do **not** run this before the go-ahead — it marks the wave as
officially started and work beginning.

### 8. Report

```
**Wave Initialized: Phase {N} Wave {M}**

- Checkout parked on clean `$DEFAULT_BRANCH` @ {short_sha}
- Wave branch: `$WAVE_BRANCH` (base: {base_branch})
- Stale worktrees pruned: {count}
- Lifecycle: allocated global wave id `{W}`, `wave_{W}_active=true`, merge model `$MERGE_MODEL`
- State file: `{state_path}` (written live by `lifecycle.py`)
- Branch URL: {url}
```

## What remains manual

- User confirms if active worktrees should be removed
- The Step 2 STOP-guards do not auto-discard — the user resolves dirty/unmerged state and
  re-runs
- Wave kickoff (Step 7) is an approval gate: the plan is presented and the `wave kickoff`
  lifecycle transition fires only on the User's explicit go-ahead
