---
name: wave-retro
description: Full end-of-wave retrospective — mechanical evidence-anchored trust scoring via trust_signals.py, counter drift verification, feedback log, process proposals, next-wave stub
args: Wave id (defaults to last completed wave)
---

Run the full retrospective for a completed wave. Per-engineer trust scoring here is
**mechanical and evidence-anchored** — narrative self-grading is banned. Every delta the
retro records is computed by `trust_signals.py` from countable signals and must cite them.

Run `/wave-end` (mechanical finalize: merges, issue closure, counters, cleanup) **before**
this skill. For a quick mid-wave pulse instead, use `/retro`.

## Instructions

### 0. Resolve config, libs, and the wave

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CFG="$REPO_ROOT/.claude/framework.config.json"
get() { jq -r "$1 // empty" "$CFG" 2>/dev/null; }   # fail-open dotted read

TEAM_DIR="$REPO_ROOT/$(get '.paths.team')";        [ -d "$TEAM_DIR" ] || TEAM_DIR="$REPO_ROOT/.claude/team"
STATE_FILE="$REPO_ROOT/$(get '.paths.state_file')"; [ -f "$STATE_FILE" ] || STATE_FILE="$REPO_ROOT/.claude/state.json"
DEFAULT_BRANCH="$(get '.scm.default_branch')";      DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"

# Drift-verification tolerances — CONFIG KEYS (defaults: ±2 absolute, ±5 percent).
DRIFT_ABS="$(get '.policy.retro_counter_drift_abs')"; DRIFT_ABS="${DRIFT_ABS:-2}"
DRIFT_PCT="$(get '.policy.retro_counter_drift_pct')"; DRIFT_PCT="${DRIFT_PCT:-5}"

# Framework libs: installed location first, framework-source checkout as fallback.
LIB="$REPO_ROOT/.claude/lib"
[ -f "$LIB/trust_signals.py" ] || LIB="$REPO_ROOT/framework/assets/lib"

# The wave under retro: the argument, else the last completed wave.
python3 "$LIB/lifecycle.py" state show   # read last_completed_wave → {W}
```

**Precondition:** the wave is wrapped up — `wave_{W}_completed_at` exists in the state
file (written by `/wave-end` via `lifecycle.py wave wrapup`). If it doesn't, stop and run
`/wave-end` first: this skill analyzes a finished wave; it never merges or cleans up.

If an ontology layer is installed, run `/ontology-librarian` first and note staleness in
the findings — the wrapup should have left it fresh, so staleness here is a process gap.

### 1. Gather the wave's merged PRs

The PR base depends on the wave's merge model:

```bash
MM="$(python3 "$LIB/lifecycle.py" merge-model get "{W}" 2>/dev/null || echo direct-to-main)"
# wave-branch     → BASE = branch.integration template with {wave} → {W}
# direct-to-main  → BASE = $DEFAULT_BRANCH, additionally filtered by the wave label
gh pr list --state merged --base "{BASE}" --json number,title,author,body,mergedAt,reviews
```

For each merged PR, also collect review comments and CI data:

```bash
gh pr view {NUMBER} --json reviews,comments
gh run list --branch {PR_BRANCH} --json conclusion,name
```

For a `meta-and-children` project, sweep every repo in `project.repos` (this matches what
`trust_signals.py` does internally).

### 2. Counter drift verification

`/wave-end` records three counters at wrapup time; they tend to drift. Recompute them
from the Step-1 PR data and reconcile **before** any number is narrated into the retro:

```bash
CLAIMED_PR_COUNT=$(jq -r ".wave_{W}_final_pr_count // empty" "$STATE_FILE")
CLAIMED_CR_CYCLES=$(jq -r ".wave_{W}_changes_requested_cycles // empty" "$STATE_FILE")
CLAIMED_CONCENTRATION=$(jq -r ".wave_{W}_top_concentration_pct // empty" "$STATE_FILE")

# Recompute from Step-1 data:
#   ACTUAL_PR_COUNT      — merged PRs across the wave's in-scope repos
#   ACTUAL_CR_CYCLES     — ChangesRequested verdicts across those PRs
#   ACTUAL_CONCENTRATION — max(PRs by one author) * 100 / total PRs
```

**Per-counter handling** (tolerances are the configured `policy.retro_counter_drift_abs`
/ `policy.retro_counter_drift_pct`):

1. **Within tolerance** (absolute diff ≤ `DRIFT_ABS` OR percentage diff ≤ `DRIFT_PCT`):
   correct the counter and record the gap —

   ```bash
   python3 "$LIB/upsert_status_keys.py" "$STATE_FILE" \
     "wave_{W}_counter_corrections=[{\"key\":\"{counter}\",\"claimed\":{claimed},\"actual\":{actual},\"corrected_at\":\"{ISO8601}\"}]"
   ```

   and note the correction in the feedback-log entry (Step 6).
2. **Beyond tolerance** (exceeds both): **retro-blocker** — investigate the wrapup-time
   arithmetic in `/wave-end` before continuing, and file a follow-up issue against it.

**CR-cycle semantics — wrapup-time count is authoritative-historic.** Recomputing
`changes_requested_cycles` from *current* comment state under-counts whenever a
ChangesRequested verdict was later edited in place to Approved (which verdict-amendment
review conventions require after fixes land). When recomputed < claimed AND the gap is
fully explained by edited-in-place verdicts (check the PR review timeline), the **claimed
value stands** — record a `wave_{W}_counter_corrections` entry documenting the measurement
conflict; do NOT "correct" the historical count downward.

**Acceptance:** Step 3 does not begin until every `wave_{W}_*` counter either matches the
recomputation or has a corrections entry recording the gap.

### 3. Mechanical per-engineer scoring

Extract the countable signals and the proposed deltas (idempotent over the same merged-PR
set — safe to re-run):

```bash
python3 "$LIB/trust_signals.py" extract "{W}" --status "$STATE_FILE"   # per-engineer signals JSON
python3 "$LIB/trust_signals.py" score   "{W}" --status "$STATE_FILE"   # + deltas, discipline, forced negative line
```

`score` emits, per engineer: `signals` (`prs_merged`, `must_fix_caught`,
`must_fix_received`, `ci_red_merges`, `rework_cycles`, `review_false_positives`, plus the
`authored_prs` evidence list), `delta` (the bidirectional trust delta, clamped to ±2 per
wave), `proposed_from_neutral` (after distribution discipline), and
`negative_signal_line`. If the wave was label-scoped, pass `--label` accordingly.

Assess each engineer **from the countable signals only** — never from narrative
impressions:

```
### {Engineer Name}
- PRs: #{N1}, #{N2}
- Signals: prs_merged={x}, must_fix_caught={x}, must_fix_received={x}, ci_red_merges={x}, rework_cycles={x}, review_false_positives={x}
- Delta: {delta} (cite the signal(s) behind it)
- Negative-signal line: {negative_signal_line — a specific gap OR "metrics clean: {numbers}", NEVER a bare "None"}
- Severity: {none|minor|moderate|severe}
```

### 4. Forced negative-signal pass (bare "None" is banned)

Every active engineer MUST get a `negative_signal_line`: a specific evidence-backed gap,
or an explicit `metrics clean: {numbers}` that still shows the receipts. Collect the lines
you wrote (one per engineer) and mechanically reject any bare `None` / `N/A` / `-`:

```bash
# One line per engineer in /tmp/negative_signal_lines.txt, then:
python3 - "$LIB" /tmp/negative_signal_lines.txt <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import trust_signals
lines = [ln.rstrip("\n") for ln in open(sys.argv[2]) if ln.strip()]
bad = trust_signals.validate_negative_signal_pass(lines)
if bad:
    print("FORCED-PASS VIOLATION (bare None banned):", bad)
    sys.exit(1)
print("negative-signal pass clean")
PY
```

A non-empty result is a forced-pass violation — fix the offending lines before continuing.

### 5. Update the trust matrix

Edit `$TEAM_DIR/trust_matrix.md` on the retro branch so the update lands in the same retro
PR as the feedback log — never as a separate direct-to-default commit.

Every row applies the mechanical policy from `trust_signals.py` and cites its numbers:

- **Delta:** `new = clamp(old + delta, 1, 5)` — bidirectional, already clamped to ±2 per
  wave by `score_delta`. Each CI-red merge / review false-positive is −1; 3+ must-fix
  received is −1; a clean wave with 2+ PRs merged or 2+ must-fix caught as reviewer is +1
  each. A single clean PR is **not** a bump.
- **Decay toward neutral:** an engineer with no signal for 3 consecutive waves drifts one
  step toward 3 (`trust_signals.decay(old, waves_since_signal)`). A stale 4 or 2 is no
  longer earned; decay is one step per retro, never a reset.
- **Distribution discipline:** 5 is reserved for the wave's top relative performer with a
  strictly positive composite (`trust_signals.apply_distribution_discipline`) — never
  handed out for merely-clean work; other proposed 5s are capped to 4.
- **Retirement trigger:** run
  `trust_signals.retirement_trigger(score_history, ci_red_history)` per engineer (both
  histories oldest→newest). If it fires (score ≤ 2 in each of the last 3 waves, or ≥ 1
  CI-red merge in each of the last 3 waves), surface a **persona-archive recommendation**
  for owner confirmation — never auto-retire.

Append a `## Wave {W} Trust Updates ({DATE}) — {theme}` section containing:
- A `| Rated | Old | New | Reason |` table — every `Reason` cites signal numbers, not
  prose impressions.
- A `### Done Well / Needs Improvement (Wave {W})` matrix whose "Needs Improvement"
  column is the forced negative-signal line (no bare "None" — Step 4 already validated).

### 6. Append to the feedback log

Append a retro entry to `$TEAM_DIR/feedback_log.md`:

```markdown
## Retrospective: Wave {W} — {DATE}

### Wave Metrics
{PRs merged, issues closed, CI health, tech-debt filed, counter corrections from Step 2}

### Top-Implementer Concentration
{max PRs by one author} / {total PRs} = {pct}% by {engineer}

### Per-Engineer Assessments
{from Step 3 — signals, deltas, negative-signal lines}

### Top 3 Going Well
1. {finding}

### Top 3 Pain Points
1. {finding}

### Proposed Process Changes
1. {change} — Rationale: {why}
```

**Concentration call:** if concentration ≥ 60%, force the call — *theme-fit* (the wave was
themed on a domain one engineer owns → "going well", with a forward-looking planning flag)
or *fragility* (a multi-domain wave where one engineer absorbed the load → "pain point",
with explicit redistribution actions for the next wave). The metric is visibility, not
policy.

### 7. Propose process/charter changes — approval-gated

Based on pain points, propose specific amendments:

```
**Proposed change:** {what}
**Section:** {charter/skill/doc section}
**Rationale:** {why, anchored to a retro finding}
```

**Do NOT apply any charter or process change without explicit user approval.**

### 8. Present the full retro inline

Output the complete summary directly in the conversation — the user must see it without
opening files: wave metrics + counter corrections, per-engineer assessments, trust-matrix
changes (who moved and the citing signals), concentration call, top-3 going well / pain
points, proposed changes, and any retirement recommendations.

### 9. Draft the next-wave meta-issue stub

Close the retro→next-wave handoff loop: every retro ends with *either* an existing
next-wave meta-issue *or* a ready-to-theme stub — never a bare "go create an issue"
blocker.

```bash
NEXT_WAVE="$(python3 "$LIB/lifecycle.py" wave peek)"
META_HITS=$(gh issue list --state open --search "\"Wave $NEXT_WAVE —\" in:title" --json number,title)
HIT_COUNT=$(echo "$META_HITS" | jq 'length')
```

- **`HIT_COUNT == 1`:** the meta-issue exists — proceed to scoping the next wave
  (`lifecycle.py wave allocate/start/scope`, per the wave-lifecycle steps) when the owner
  gives the go-ahead.
- **`HIT_COUNT > 1`:** ambiguous — list the hits as a blocker; the owner resolves before
  any scoping.
- **`HIT_COUNT == 0`:** auto-draft the stub. The scaffold is mechanical; **only the theme
  is an owner decision**:

  ```bash
  NEW_URL=$(gh issue create --title "Wave $NEXT_WAVE — (theme TBD — owner to set)" --body "$(cat <<'MD'
  ## Theme

  **TBD — owner to set.** Replace this line (and the title) with the wave theme.

  ## Carry-forward from Wave {W} (auto-scaffold)
  {deferred items from this wave's scope, or the retro's pain-point follow-ups}

  ## Candidate scope
  - Open issues labeled for the next wave, plus the configured tech-debt intake
    (`policy.tech_debt_intake_pct`) applied at planning time.
  - See the Wave {W} retro entry in the feedback log for follow-ups to fold in.

  ---
  *Auto-drafted stub from /wave-retro Step 9. Owner sets the theme; the title and the
  Theme line are the only manual edits.*
  MD
  )")
  NEW_NUM=$(echo "$NEW_URL" | grep -oE '[0-9]+$')
  python3 "$LIB/upsert_status_keys.py" "$STATE_FILE" "wave_${NEXT_WAVE}_meta_issue=\"#$NEW_NUM\""
  ```

  This reserves the id via the `wave_{N}_meta_issue` key only — do **not** bump the wave
  counter here. The lifecycle allocator is reservation-aware: it claims a reserved id at
  `global_wave_seq + 1` instead of skipping it; adding a counter bump would double-advance.
  Surface the stub URL and stop — the theme is the only manual step left.

## Division of labor

| Surface | Job |
|---------|-----|
| `/wave-end` | Mechanical finalize: review, merge, close issues, record counters, cleanup |
| `/wave-retro` (this) | Scoring/process: drift verification, trust deltas, feedback log, proposals, next-wave stub |
| `/retro` | Lightweight mid-wave pulse (diagnostic only) |

## What remains manual

- The user approves all charter/process changes before they are applied.
- Trust-matrix changes are proposed — the user can veto specific adjustments.
- Retirement recommendations require owner confirmation; nothing is auto-archived.
- The next wave's theme is an owner decision; the stub only scaffolds it.
