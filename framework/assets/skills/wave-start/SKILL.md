---
name: wave-start
description: "Initialize a new wave"
---

# Wave Start

Initialize a new wave (`args`: phase number `{N}`, wave number `{M}`).

> Config-driven + fail-open: reads `.claude/framework.config.json` via `jq`; missing keys fall
> back to the documented defaults. Wave kickoff requires **explicit User approval** before work
> begins — this skill only sets up infrastructure.

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

### 5. Run retro

Run the `/retro` skill if this is not the first wave, so carry-over items from the previous
wave are surfaced before new work starts.

### 6. Report

```
**Wave Initialized: Phase {N} Wave {M}**

- Checkout parked on clean `$DEFAULT_BRANCH` @ {short_sha}
- Wave branch: `$WAVE_BRANCH` (base: {base_branch})
- Stale worktrees pruned: {count}
- Branch URL: {url}
```

## What remains manual

- User confirms if active worktrees should be removed
- The Step 2 STOP-guards do not auto-discard — the user resolves dirty/unmerged state and
  re-runs
- Wave kickoff (plan presentation + user go-ahead) happens after this skill completes
