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
3. **Derive the wave's counters mechanically — never transcribe them from the
   handoff.** The three counters `/wave-retro` step 2 reads for drift verification
   MUST be computed from the merged-PR set and `trust_signals.py extract` — the same
   authority the retro reconciles against. The session handoff narrates *final
   verdict state* (a PR amended in place after its fix lands reads "clean"); the
   counters track *round history*. Transcribing the prose is a second source of truth
   and guarantees drift — it bit twice: Wave 22 recorded `--cr-cycles 1` because the
   handoff read "3 PRs / 1 CR cycle" and called #290 "2 clean" (true of its amended
   final state, false of its round history — #290 carried a real rework round), and
   `trust_signals.py extract 22` disagreed on sight; Wave 11 produced the analogous
   rollup slip that motivated the `origin/<wave>` runbook step (#255).

   Compute all three from the same merged-PR set the retro uses, then pass the derived
   values to `wrapup` — do not type numbers from memory:

   ```bash
   # BASE = the wave's PR base — the integration branch for a wave-branch merge model,
   # the default branch otherwise (same resolution as step 1 / `/wave-retro` step 1).
   MM="$(python3 "$LIB/lifecycle.py" merge-model get "$W" 2>/dev/null || echo direct-to-main)"
   # wave-branch    → BASE=<branch.integration template, the wave's phase + $W>
   # direct-to-main → BASE=<default branch>; add `--label "wave-$W"` to scope the wave

   # --pr-count and --concentration come from the merged-PR list itself:
   PRS_JSON="$(gh pr list --state merged --base "$BASE" --json number,author)"
   PR_COUNT="$(echo "$PRS_JSON" | jq 'length')"
   CONCENTRATION="$(echo "$PRS_JSON" | jq -r '
       if length == 0 then 0
       else ((group_by(.author.login) | map(length) | max) * 100 / length | floor)
       end')"

   # --cr-cycles = PRs that took >=1 changes-requested round. `trust_signals.py`
   # increments an author's `rework_cycles` exactly ONCE per PR that carried a rework
   # round, and the extraction is edit-history-aware (the #164 catch ledger / #229
   # comment histories), so an in-place verdict amendment does NOT erase the round.
   # Summing `rework_cycles` across engineers therefore counts reworked PRs per-PR,
   # not per-verdict (a PR with `reviewers_required=2` can carry two ChangesRequested
   # verdicts in one round — still one reworked PR). This is the SAME extraction
   # `/wave-retro` steps 2-3 run, so the wrapup counter and the retro recompute can
   # never diverge:
   CR_CYCLES="$(python3 "$LIB/trust_signals.py" extract "$W" \
       | jq '[.[].rework_cycles] | add // 0')"

   echo "derived counters → --pr-count $PR_COUNT --cr-cycles $CR_CYCLES --concentration $CONCENTRATION"
   ```

   For a `meta-and-children` project, sweep every repo in `project.repos` (this is
   what `trust_signals.py` does internally) and union the per-repo `pr list` results
   before computing `--pr-count` / `--concentration`.

   Then record the counters and close the wave **live** — the `wrapup` transition
   writes `wave_{W}_completed_at`, deactivates the wave, advances `last_completed_wave`,
   and stores the three counters `/wave-retro` reads for drift verification:

   ```bash
   python3 "$LIB/lifecycle.py" wave wrapup "$W" \
       --pr-count "$PR_COUNT" --cr-cycles "$CR_CYCLES" --concentration "$CONCENTRATION"
   ```

   **The recomputed-vs-claimed reconciliation is bidirectional.** `/wave-retro` step 2
   independently recomputes these counters; deriving them mechanically here makes the
   two agree by construction, but state both directions so the reconciliation is
   unambiguous whenever they differ:
   - **recomputed `<` claimed AND the gap is fully explained by edited-in-place
     verdicts** → the **claimed value stands**. A naive recompute from *current*
     comment bodies under-counts a ChangesRequested verdict that was amended in place
     to Approved after the fix landed — the historic round still happened, so the
     wrapup-time count is authoritative-historic. Record a
     `wave_{W}_counter_corrections` entry documenting the measurement conflict; do NOT
     correct the historic count downward. (Deriving `--cr-cycles` from the
     history-aware `extract` above avoids this under-count in the first place.)
   - **recomputed `>` claimed** → **recomputed wins** — the wrapup missed a real round.
     This was Wave 22 (claimed 1, recomputed 2: `extract` found `rework_cycles=1` on
     both #290 and #292). Because this step now derives `--cr-cycles` from that same
     `extract`, this direction should not resurface at retro time again.

   **Emit review-load next to concentration** (#231): concentration tracks *authoring*
   load; the companion number is *reviewing* load — per-reviewer verdict counts, so a
   lopsided slate (one reviewer carrying most verdicts) is a tracked number rather than
   something you balance by eye. Compute it with the skill's bundled `review_load.py`,
   resolved the same dual-deploy way as `$LIB` (installed copy first, framework-source
   fallback), and record the line alongside the counters — `/wave-retro` reads it into the
   feedback log's review-load note:

   ```bash
   RL="$REPO_ROOT/.claude/skills/wave-end/review_load.py"
   [ -f "$RL" ] || RL="$REPO_ROOT/framework/assets/skills/wave-end/review_load.py"
   python3 "$RL" counts "$W"   # {reviewer: {verdicts, prs_reviewed}}, roster-canonicalized
   ```

   A "verdict" is one review turn by its `Requestor:` (both `Request` and the
   amended-in-place `Replied` count once — the amendment convention edits the comment in
   place, so it never inflates the count; see [pull-requests.md](../../team/charter/pull-requests.md)).
4. Run `git worktree prune`
5. Scan docs/ and diagrams for staleness against changes
6. If this is the final wave of the phase, create a PR to the default branch (User
   approval gate applies — never merge without sign-off). When that rollup is landed,
   follow the **rollup pre-flight** in
   [pull-requests.md](../../team/charter/pull-requests.md): `git fetch origin` and merge
   `origin/<wave>` **explicitly** (never a stale local ref), then verify feature-code is on
   the merge parent (`git show <default-branch>:<file> | grep -c <new-symbol>`) BEFORE
   bump/release — a code-less rollup (state.json only) is a stop-and-investigate.
7. Hand off to `/wave-retro` — trust deltas, the forced negative-signal pass, the
   feedback-log entry, process proposals, and the next-wave stub all live there, not here.

## Division of labor

| Surface | Job |
|---------|-----|
| `/wave-end` (this) | Mechanical finalize: review, merge, close issues, record counters, cleanup |
| `/wave-retro` | Scoring/process: drift verification, trust deltas, feedback log, proposals, next-wave stub |
| `/retro` | Lightweight mid-wave pulse (diagnostic only) |
