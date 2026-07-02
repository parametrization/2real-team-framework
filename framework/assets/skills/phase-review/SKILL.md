---
name: phase-review
description: Phase-level health check before scoping the next wave — phase-doc tracking state, tech-debt ratio vs the configured exit threshold, owner revision checkpoint
args: Phase number
---

Phase-level track check, run **before scoping the next wave**. Surfaces accomplishments,
blockers, and remaining end-state criteria so the owner chooses the next wave's theme
deliberately, not reactively.

**Config-driven:** the tech-debt exit threshold and labels come from
`.claude/framework.config.json` (fail-open to the documented defaults).

## What this skill is NOT

- Not a wave reconciliation step — that is the wave-lifecycle scoping step
  (`lifecycle.py wave scope`).
- Not a retrospective — that is `/wave-retro` (per wave).
- Not a phase-creation step — `/plan-phase` creates phases.
- It does NOT pick the next wave's theme — that is the owner's call after seeing the
  picture.
- It does NOT modify the phase doc without owner confirmation.

## Instructions

### 0. Resolve config

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CFG="$REPO_ROOT/.claude/framework.config.json"
get() { jq -r "$1 // empty" "$CFG" 2>/dev/null; }   # fail-open dotted read

TEAM_DIR="$REPO_ROOT/$(get '.paths.team')"; [ -d "$TEAM_DIR" ] || TEAM_DIR="$REPO_ROOT/.claude/team"
TD_LABEL="$(get '.labels.tech_debt')";      TD_LABEL="${TD_LABEL:-tech-debt}"

# Tech-debt exit threshold — CONFIG KEY `policy.tech_debt_exit_ratio_pct` (default 10).
TD_EXIT_PCT="$(get '.policy.tech_debt_exit_ratio_pct')"; TD_EXIT_PCT="${TD_EXIT_PCT:-10}"
```

### 1. Load the phase doc

```bash
PHASE_DOC="$TEAM_DIR/phases/phase-{P}.md"
if [ ! -f "$PHASE_DOC" ]; then
  echo "ERROR: phase doc missing at $PHASE_DOC"
  echo "Run /plan-phase first — it records the phase doc this review checks against."
  exit 1
fi
cat "$PHASE_DOC"
```

If the phase doc is missing, STOP and direct the owner to `/plan-phase` (its Step 8
records the doc). Without it, this review has nothing to check against.

### 2. Pull live state for each tracking issue

Extract the tracking issue numbers from the phase doc and pull their current state.
(Note: `while read`, not `for x in $VAR` — zsh does not word-split an unquoted scalar, so
a multi-line list would collapse into one bogus iteration.)

```bash
TRACKING_ISSUES=$(grep -oE '#[0-9]+' "$PHASE_DOC" | tr -d '#' | sort -un)

while IFS= read -r num; do
  [ -n "$num" ] || continue
  gh issue view "$num" --json number,title,state,labels,closedAt \
    --jq '"\(.state)\t#\(.number)\t[\(.labels|map(.name)|join(","))]\t\(.title)"'
done <<< "$TRACKING_ISSUES"
```

Categorize each phase criterion:
- **Done** — tracking issue closed
- **In flight** — open, with linked open PRs
- **Open / not started** — open, no linked PRs
- **Blocked** — open, with a `blocked` label or a commented blocker

For a `meta-and-children` project, tracking refs may be `repo#N` — query the named repo
with `--repo` in that case.

### 3. Tech-debt ratio vs the configured exit threshold

```bash
PHASE_START=$(grep '^created:' "$PHASE_DOC" | head -1 | awk '{print $2}')

# New issues filed during the phase, all states
TOTAL_NEW=$(gh issue list --search "created:>=$PHASE_START" --state all --limit 500 --json number | jq length)
TOTAL_NEW_TD=$(gh issue list --search "created:>=$PHASE_START label:$TD_LABEL" --state all --limit 500 --json number | jq length)

# Cumulative open
CUM_OPEN=$(gh issue list --state open --limit 500 --json number | jq length)
CUM_OPEN_TD=$(gh issue list --state open --label "$TD_LABEL" --limit 500 --json number | jq length)

[ "$TOTAL_NEW" -gt 0 ] && new_pct=$((TOTAL_NEW_TD * 100 / TOTAL_NEW)) || new_pct=0
[ "$CUM_OPEN" -gt 0 ] && cum_pct=$((CUM_OPEN_TD * 100 / CUM_OPEN)) || cum_pct=0

echo "New filed this phase: $TOTAL_NEW_TD / $TOTAL_NEW = ${new_pct}% tech-debt (gate: <${TD_EXIT_PCT}%)"
echo "Cumulative open:      $CUM_OPEN_TD / $CUM_OPEN = ${cum_pct}% tech-debt (gate: <${TD_EXIT_PCT}%)"
```

If either ratio ≥ `TD_EXIT_PCT`, flag it: **the phase exit gate is not met**, regardless
of criterion-by-criterion checkboxes. (`/plan-phase`'s last-wave tech-debt floor exists
to bring these ratios under the gate before exit.)

For a `meta-and-children` project, run the same queries per repo in `project.repos` and
aggregate the counts.

### 4. Surface to the owner

Present a single status block:

```
**Phase {P} Review — {date}**

| # | Criterion | Tracker | State | Notes |
|---|-----------|---------|-------|-------|
| 1 | ... | #NNN | Open | No PRs |
| 2 | ... | #NNN | In flight | PR #XXX |

**Tech-debt ratio (exit gate: <{TD_EXIT_PCT}%):**
- New filed (phase-to-date): {new_pct}%
- Cumulative open:           {cum_pct}%

**Phase exit gate:** {MET / NOT MET — reason}
```

### 5. Owner revision checkpoint

Ask the owner:
- Has the track drifted? (criteria thought done but actually open; new urgent items)
- Should the phase doc be revised before the next wave is scoped?

If yes, edit `$PHASE_DOC` with the owner's input and commit (per the project's commit
identity rules). **Never revise the doc without the owner's explicit confirmation.**

### 6. Hand off to next-wave scoping

Print:

```
Phase review complete. Ready to scope the next wave.
```

The next wave proceeds through the wave-lifecycle steps (`/wave-start`, or
`lifecycle.py wave allocate/start/scope`) once the owner picks the theme.

## What remains manual

- The owner decides the next wave's theme and any phase-doc revisions.
- Blocked criteria need human triage — this skill only surfaces them.
