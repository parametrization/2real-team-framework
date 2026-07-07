---
name: wave-end
description: Finalize a wave (review, merge, counters, cleanup) — mechanical only; scoring/process analysis lives in /wave-retro
---

Finalize the current wave. This skill is the **mechanical finalize** surface: merge ready
PRs, close resolved issues, record the wave's counters, clean up. It does **no** trust
scoring and no process analysis — that is `/wave-retro`, which runs immediately after this
and reads the counters recorded here.

## Instructions

0. Resolve the framework libs. The state file is owned by `lifecycle.py`; resolve it the
   dual-deploy way — installed location first, framework-source checkout as fallback (so
   this skill runs both in a deployed repo and in the framework source repo itself):

   ```bash
   REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
   LIB="$REPO_ROOT/.claude/lib"
   [ -f "$LIB/lifecycle.py" ] || LIB="$REPO_ROOT/framework/assets/lib"   # framework source repo
   W="$(python3 "$LIB/lifecycle.py" state show | python3 -c 'import json,sys; print(json.load(sys.stdin).get("current_wave","").removeprefix("wave-"))')"
   echo "Finalizing wave: $W"
   ```

1. List all open PRs targeting the current wave's base branch (the integration branch for
   a `wave-branch` merge model, the default branch otherwise — `lifecycle.py merge-model
   get {W}` says which):

   ```bash
   python3 "$LIB/lifecycle.py" merge-model get "$W"
   ```
2. For each PR:
   a. Check CI status — do NOT proceed if failing
   b. Review the diff
   c. Post review comment (charter format)
   d. Create tech-debt issues for findings (label: next phase)
   e. Merge if CI green
   f. Close referenced issues
3. Record the wave's counters and close it **live** — the `wrapup` transition writes
   `wave_{W}_completed_at`, deactivates the wave, advances `last_completed_wave`, and
   records the three counters `/wave-retro` reads for drift verification:

   ```bash
   python3 "$LIB/lifecycle.py" wave wrapup "$W" \
       --pr-count {N} --cr-cycles {C} --concentration {PCT}
   ```

   Count them from the actual merged-PR set, not from memory: `--pr-count` = merged PRs
   this wave, `--cr-cycles` = **PRs** that took >=1 changes-requested round (per-PR, not
   per-verdict — a PR with `reviewers_required=2` can carry 2 ChangesRequested verdicts in
   one round; count the PR once). This mirrors `trust_signals.py`'s `rework_cycles` signal
   ("PRs they authored that needed >=1 rework round") so the two counters never drift.
   `--concentration` = max(PRs by one author) × 100 / total.
4. Run `git worktree prune`
5. Scan docs/ and diagrams for staleness against changes
6. If this is the final wave of the phase, create a PR to the default branch (User
   approval gate applies — never merge without sign-off)
7. Hand off to `/wave-retro` — trust deltas, the forced negative-signal pass, the
   feedback-log entry, process proposals, and the next-wave stub all live there, not here.

## Division of labor

| Surface | Job |
|---------|-----|
| `/wave-end` (this) | Mechanical finalize: review, merge, close issues, record counters, cleanup |
| `/wave-retro` | Scoring/process: drift verification, trust deltas, feedback log, proposals, next-wave stub |
| `/retro` | Lightweight mid-wave pulse (diagnostic only) |
