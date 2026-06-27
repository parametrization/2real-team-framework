---
name: phase-review
description: Phase track-check before /wave-scope — review what's done, what's remaining, what's blocked. Surface the tech-debt ratio. Allow phase-plan revision before the next wave is scoped.
args: Phase number
---

Phase-level track check. **Mandatory before every `/wave-scope`.** Surfaces accomplishments, blockers, and remaining end-state criteria so the owner can choose the next wave's theme deliberately, not reactively.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Phase Lifecycle for the canonical skill order and preconditions.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## When to use

- **Before every `/wave-scope`.** Mandatory pre-step. `/wave-scope` Step 0.5 will block until `/phase-review` has been invoked in the same session.
- **On demand** — owner can run anytime to check phase health.
- Not a replacement for `/retro` (per-wave) or `/plan-phase` (phase-creation).

## What this skill is NOT

- Not a wave reconciliation step — that's `/wave-scope`.
- Not a retrospective — that's `/wave-retro`.
- Not a phase-creation step — `/plan-phase` is the phase-creation skill.
- Does NOT pick the next wave's theme — that's the owner's call after seeing the picture.
- Does NOT modify the phase plan doc without owner confirmation.

## Instructions

### 0. Inputs

- `{P}` — phase number (e.g. `3`)

### 1. Load phase plan

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
PHASE_DOC="$REPO_ROOT/.claude/team/phases/phase-{P}.md"
if [ ! -f "$PHASE_DOC" ]; then
  echo "ERROR: phase plan doc missing at $PHASE_DOC"
  echo "Run /plan-phase first to draft the phase scope, then hand-author the phase plan doc — without it, /phase-review has nothing to check against."
  exit 1
fi
cat "$PHASE_DOC"
```

If the phase plan doc is missing, STOP and direct the owner to `/plan-phase` (which proposes the wave structure that the phase plan doc captures). The phase plan doc itself is hand-authored.

### 2. Pull current state of each tracking issue

Extract tracking issue numbers from the phase plan and pull live state for each:

```bash
TRACKING_ISSUES=$(grep -oE 'noorinalabs-main#[0-9]+' "$PHASE_DOC" | sort -u)

# `while read`, NOT `for issue in $TRACKING_ISSUES` — zsh does not word-split an
# unquoted scalar, so the multi-line list would collapse into one bogus iteration
# (#759, same class as main#688). The `[ -n ]` guard keeps the no-op-on-empty
# behaviour `for` gives when no tracking issues are found.
while IFS= read -r issue; do
  [ -n "$issue" ] || continue
  num=${issue#noorinalabs-main#}
  gh issue view "$num" --repo noorinalabs/noorinalabs-main \
    --json number,title,state,labels,closedAt \
    --jq '"\(.state)\t#\(.number)\t[\(.labels|map(.name)|join(","))]\t\(.title)"'
done <<< "$TRACKING_ISSUES"
```

Categorize each criterion:
- **Done** — tracking issue closed
- **In flight** — tracking issue open + has linked open PRs
- **Open / not started** — tracking issue open + no linked PRs
- **Blocked** — tracking issue open + has `blocked` label or commented blocker

### 3. Tech-debt ratio (P3 exit gate)

```bash
PHASE_START=$(grep '^created:' "$PHASE_DOC" | head -1 | awk '{print $2}')

# New issues filed during phase, all states
TOTAL_NEW=$(gh issue list --repo noorinalabs/noorinalabs-main \
    --search "created:>=$PHASE_START" --state all --limit 500 --json number | jq length)
TOTAL_NEW_TD=$(gh issue list --repo noorinalabs/noorinalabs-main \
    --search "created:>=$PHASE_START label:tech-debt" --state all --limit 500 --json number | jq length)

# Cumulative open
CUM_OPEN=$(gh issue list --repo noorinalabs/noorinalabs-main \
    --state open --limit 500 --json number | jq length)
CUM_OPEN_TD=$(gh issue list --repo noorinalabs/noorinalabs-main \
    --state open --label tech-debt --limit 500 --json number | jq length)

[ "$TOTAL_NEW" -gt 0 ] && new_pct=$((TOTAL_NEW_TD * 100 / TOTAL_NEW)) || new_pct=0
[ "$CUM_OPEN" -gt 0 ] && cum_pct=$((CUM_OPEN_TD * 100 / CUM_OPEN)) || cum_pct=0

echo "New filed this phase: $TOTAL_NEW_TD / $TOTAL_NEW = ${new_pct}% tech-debt"
echo "Cumulative open:      $CUM_OPEN_TD / $CUM_OPEN = ${cum_pct}% tech-debt"
```

If either >10%, flag — phase exit gate not yet met (regardless of criterion-by-criterion checkboxes).

The same query should also run across all 7 child repos for a cross-repo view; aggregate counts.

### 4. Surface to owner

Present a single status block:

```
**Phase {P} Review — {date}**

| # | Criterion | Tracker | State | Notes |
|---|-----------|---------|-------|-------|
| 1 | ... | main#NNN | Open | No PRs |
| 2 | ... | main#NNN | In flight | PR#XXX |
| ... | | | | |

**Tech-debt ratio (exit criterion 9):**
- New filed (phase-to-date): X% (gate: <10%)
- Cumulative open:           X% (gate: <10%)

**Phase exit gate:** {NOT MET / MET}
```

### 5. Allow phase-plan revision

Ask the owner:
- Has the track drifted? (criteria thought-done but actually open, or new urgent items surfaced)
- Should the phase plan be revised before `/wave-scope` runs?

If yes, edit `$PHASE_DOC` with the owner's input, then commit (orchestrator commit identity).

### 6. Hand off to /wave-scope

Print:
```
Phase review complete. Ready to run /wave-scope for the next wave.
```

`/wave-scope` Step 0.5 will check that `/phase-review` ran in this session and proceed.
