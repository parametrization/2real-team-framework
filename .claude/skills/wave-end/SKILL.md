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

   # REFUSE to derive counters from a read you cannot trust. `extract` fails SILENT
   # under a GraphQL rate limit (returns `{}`, exit 0), and `gh pr list --json` is
   # GraphQL-backed too — the SAME 5,000/hr bucket — so when the budget is pre-exhausted
   # BOTH come back empty and a naive `${PR_COUNT:-0}` collapses to 0, then the
   # cross-check compares 0 == 0 and reports health (#307 review). Three ORTHOGONAL
   # defenses run before any counter is derived or `wave wrapup` is called:

   # (A) Preflight the GraphQL budget over an INDEPENDENT channel. `gh api rate_limit`
   #     is served over REST — a different bucket that does NOT drain with GraphQL — so
   #     it stays readable when `gh pr list` / `extract` cannot. If GraphQL is at/near
   #     zero, the wave read WILL return empty-but-successful; abort now, naming the
   #     limit. `GQL_FLOOR` is a fail-fast margin; (B) and (C) are the hard guarantees.
   GQL_FLOOR=100
   GQL_REMAINING="$(gh api rate_limit --jq '.resources.graphql.remaining' 2>/dev/null)"
   case "$GQL_REMAINING" in
       ''|*[!0-9]*)
           echo 'ABORT: could not read the GraphQL rate-limit budget (REST rate_limit failed).' >&2
           echo '  Cannot establish that the wave read will succeed — refusing to record counters.' >&2
           exit 1 ;;
   esac
   if [ "$GQL_REMAINING" -lt "$GQL_FLOOR" ]; then
       echo "ABORT: GraphQL budget near-exhausted ($GQL_REMAINING < $GQL_FLOOR)." >&2
       echo '  gh pr list and trust_signals extract both draw on this bucket and would' >&2
       echo '  return empty-but-successful, recording FALSE zero counters. Wait for reset —' >&2
       echo '  gh api rate_limit --jq .resources.graphql — then re-run step 3 from the top.' >&2
       exit 1
   fi

   # (B) --pr-count is identity-AGNOSTIC (a count of PRs, not authors, so `gh`'s single
   #     dogfood `.author.login` is fine here) — but its READ can still fail. Capture the
   #     exit status EXPLICITLY: a failed `gh pr list` must not collapse into '' and then
   #     0 via `${VAR:-0}`. A non-zero exit, or non-numeric stdout, is an ABORT, not a
   #     zero. (This is what the pre-exhausted case trips — `gh pr list` exits non-zero.)
   PR_LIST="$(gh pr list --state merged --base "$BASE" --json number)"; PR_LIST_RC=$?
   PR_COUNT="$(printf '%s' "$PR_LIST" | jq 'length' 2>/dev/null)"
   if [ "$PR_LIST_RC" -ne 0 ] || ! printf '%s' "$PR_COUNT" | grep -Eq '^[0-9]+$'; then
       echo "ABORT: gh pr list failed (exit $PR_LIST_RC) or returned a non-numeric count." >&2
       echo '  A failed read is NOT an empty wave — refusing to record zero counters.' >&2
       exit 1
   fi

   # --cr-cycles and --concentration are BOTH identity-SENSITIVE, so both derive from
   # `trust_signals.py extract` — the only source that resolves team-member identity (it
   # parses the `Co-Authored-By` trailers); grouping `gh`'s `.author.login` would collapse
   # a dogfooded repo to ~100% concentration forever (#307). Extract ONCE — a second call
   # could straddle a rate-limit boundary and return different data:
   SIG="$(python3 "$LIB/trust_signals.py" extract "$W")"

   # (C) Cross-check `extract` against the now-TRUSTED PR_COUNT (reads (A)+(B) confirmed
   #     succeeded). `extract` still fails SILENT (`{}`, exit 0) — the #300 follow-up; the
   #     library-level fix is #311 on the trust_signals surface, not touched here. An
   #     empty map — or ANY disagreement, which also catches a PARTIAL read — for a wave
   #     that merged PRs is an ABORT, never a zero. A genuinely empty wave reaches here
   #     only after the reads SUCCEEDED, so PR_COUNT == 0 is then a real zero and proceeds:
   SIG_ENGINEERS="$(printf '%s' "$SIG" | jq 'length' 2>/dev/null || echo 0)"
   SIG_PR_TOTAL="$(printf '%s' "$SIG" | jq '[.[].authored_prs | length] | add // 0' 2>/dev/null || echo 0)"
   if [ "$PR_COUNT" -gt 0 ] && { [ "${SIG_ENGINEERS:-0}" -eq 0 ] || [ "${SIG_PR_TOTAL:-0}" -ne "$PR_COUNT" ]; }; then
       echo "ABORT: trust_signals extract could not be trusted for wave $W" >&2
       echo "  gh pr list count = $PR_COUNT, but extract shows $SIG_ENGINEERS engineer(s)" >&2
       echo "  covering $SIG_PR_TOTAL authored PR(s). An empty/short extract for a wave that" >&2
       echo "  merged PRs means the READ FAILED (usually a GraphQL rate limit), NOT that no" >&2
       echo "  rework happened. Do NOT run 'wave wrapup' with these numbers. Wait for reset" >&2
       echo "  and re-run step 3 from the top." >&2
       exit 1
   fi

   # --cr-cycles = PRs that took >=1 changes-requested round. `trust_signals.py`
   # increments an author's `rework_cycles` exactly ONCE per PR that carried a rework
   # round, and the extraction is edit-history-aware (the #164 catch ledger / #229
   # comment histories), so an in-place verdict amendment does NOT erase the round.
   # Summing `rework_cycles` across engineers therefore counts reworked PRs per-PR,
   # not per-verdict (a PR with `reviewers_required=2` can carry two ChangesRequested
   # verdicts in one round — still one reworked PR). This is the SAME extraction
   # `/wave-retro` steps 2-3 run, so the wrapup counter and the retro recompute can
   # never diverge:
   CR_CYCLES="$(echo "$SIG" | jq '[.[].rework_cycles] | add // 0')"

   # --concentration = max(PRs by one author) × 100 / total, over the SAME identity-aware
   # `authored_prs` lists `/wave-retro` step 2 reconciles against (integer floor; guard
   # total == 0):
   CONCENTRATION="$(echo "$SIG" | jq '
       [ .[].authored_prs | length ] as $lens
       | ($lens | add) as $total
       | if ($total // 0) == 0 then 0 else (($lens | max) * 100 / $total | floor) end')"

   echo "derived counters → --pr-count $PR_COUNT --cr-cycles $CR_CYCLES --concentration $CONCENTRATION"
   ```

   For a `meta-and-children` project, `trust_signals.py extract` already sweeps every
   repo in `project.repos` internally, so `--cr-cycles` / `--concentration` need no
   manual sweep; union the per-repo `gh pr list` results yourself only for `--pr-count`.

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
