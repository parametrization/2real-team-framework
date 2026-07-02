---
name: plan-phase
description: Plan a phase — decompose scope into a reviewed issue set, propose wave structure with configured tech-debt intake, create issues only after user approval
args: Phase number
---

Plan a phase of work: decompose the phase scope into a reviewed, dependency-ordered issue
set, propose a wave structure, and — **only after explicit user approval** — create the
issues.

**Config-driven:** board settings, labels, and the tech-debt intake percentage come from
`.claude/framework.config.json` (fail-open to the documented defaults). Never hard-code a
project choice here.

## Instructions

### 0. Resolve config

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CFG="$REPO_ROOT/.claude/framework.config.json"
get() { jq -r "$1 // empty" "$CFG" 2>/dev/null; }   # fail-open dotted read

TEAM_DIR="$REPO_ROOT/$(get '.paths.team')"; [ -d "$TEAM_DIR" ] || TEAM_DIR="$REPO_ROOT/.claude/team"
TD_LABEL="$(get '.labels.tech_debt')";      TD_LABEL="${TD_LABEL:-tech-debt}"
BOARD_ENABLED="$(get '.board.enabled')"
BOARD_NUM="$(get '.board.project_number')"
OWNER="$(get '.scm.owner')"

# Tech-debt intake percentage — CONFIG KEY `policy.tech_debt_intake_pct` (default 20).
TD_INTAKE_PCT="$(get '.policy.tech_debt_intake_pct')"; TD_INTAKE_PCT="${TD_INTAKE_PCT:-20}"
```

### 1. Gather phase scope

**Use the full backlog as the candidate pool.** Never plan from a narrower view (a single
label query, or a meta-issue body alone) — that systematically excludes work that never
got a label.

If a planning board is configured (`board.enabled` true + `board.project_number` set), the
board is the authoritative backlog — audit for drift first:

```bash
if [ "$BOARD_ENABLED" = "true" ] && [ -n "$BOARD_NUM" ]; then
  # Every open issue should be on the board; any output below = drift — add the
  # missing issues to the board before continuing.
  gh issue list --state open --limit 500 --json url --jq '.[].url' | sort -u > /tmp/open_issues.txt
  gh project item-list "$BOARD_NUM" --owner "$OWNER" --format json --limit 1000 \
    --jq '.items[] | select(.content.url) | .content.url' | sort -u > /tmp/board_urls.txt
  comm -23 /tmp/open_issues.txt /tmp/board_urls.txt
else
  gh issue list --state open --limit 500 --json number,title,labels,body
fi
```

For a `meta-and-children` project, repeat the open-issue sweep per repo in `project.repos`
and aggregate.

Additional context sources:
- Project memory / docs for stated goals
- The previous phase's retro entries in `$TEAM_DIR/feedback_log.md` for carry-over items
- The previous phase doc under `$TEAM_DIR/phases/` (if present) for unmet exit criteria

### 2. Draft the issue set (do NOT create anything yet)

For each work item, draft (in the plan, not on the issue tracker):

- **Title:** verb-first, specific (e.g., "Add branch-pattern matching to stale-issue audit")
- **Body:** Summary, acceptance criteria (checkbox list), origin/rationale
- **Labels:** phase label (`phase-{N}`), category (`feature`, `bug`, `tech-debt`,
  `security`, `infra`), and repo label for meta-and-children projects
- **Proposed assignee:** best fit from the roster (`identity.roster_source`) by expertise
  match, current load, and repo familiarity

Issue creation happens in Step 7, after the Step-6 approval gate.

### 3. Six-perspective structured review

Review every drafted issue from all six perspectives:

| Perspective | Focus |
|-------------|-------|
| **Architecture** | System design, API contracts, data-model impact |
| **DevOps** | Deployment impact, infrastructure needs, CI changes |
| **Data** | Data migration, pipeline impact, schema changes |
| **Tech Lead** | Scope accuracy, effort estimate, risk |
| **QA** | Testability, edge cases, acceptance-criteria completeness |
| **Security** | Auth impact, input validation, data exposure |

For each concern raised, either fold the resolution into the draft body now, or record a
review note to post as an issue comment after creation:

```bash
gh issue comment {NUMBER} --body "$(cat <<'EOF'
**{Perspective} Review**

{findings — concerns, suggestions, or "No concerns"}
EOF
)"
```

### 4. Dependency analysis

Build a dependency graph across the drafted issues:
- Which issues must complete before others can start?
- Which issues touch the same files/systems (serialize to avoid conflicts)?
- For meta-and-children projects: which cross-repo dependencies exist?

### 5. Propose wave structure — with the configured tech-debt intake

Group issues into waves by:
- **Priority:** live bugs > security > tech debt > features > polish
- **Dependencies:** blockers in earlier waves, dependents later
- **Parallelism:** maximize concurrent work by grouping independent issues
- **Repo grouping** (meta-and-children): minimize context-switching per agent

**Tech-debt intake per wave (`policy.tech_debt_intake_pct`, default 20).** For each wave,
after the feature/bug/security content is set, allocate **tech-debt-only** issues equal to
`TD_INTAKE_PCT`% of that content, **rounded up** — add all available if fewer qualify (a
shortfall is healthy; never backfill with invented work). Steady *intake* replaces
ratio-chasing: a cumulative tech-debt-ratio gate whipsaws as the backlog shrinks, so the
per-wave intake is the standing policy.

**Last-wave-of-phase relaxation.** The intake percentage is a per-wave *cap* on every wave
**except the last wave of the phase**, where it becomes a **floor**: deliberately pull in a
large chunk of tech-debt (well beyond the configured percentage) to clean up before phase
exit — clearing debt *is* the goal there. `/phase-review`'s exit threshold
(`policy.tech_debt_exit_ratio_pct`) is the gate this relaxation exists to satisfy.

Present the proposed structure:

```
**Phase {N} Plan**

### Wave 1: {theme}
| Issue | Title | Assignee | Priority | Dependencies |
|-------|-------|----------|----------|--------------|
| draft | ...   | Name     | bug      | None         |

### Wave 2: {theme}
| Issue | Title | Assignee | Priority | Dependencies |
|-------|-------|----------|----------|--------------|
| draft | ...   | Name     | feature  | Wave 1: ...  |

**Total issues:** {count}  ·  **Estimated waves:** {count}
**Tech-debt intake:** {TD_INTAKE_PCT}% per wave ({allocated} of {content} items; final wave: floor)
**Cross-repo dependencies:** {list or "None"}
```

### 6. APPROVAL GATE — present the plan, then STOP

Display the full plan. **Do NOT create issues or start implementation without explicit
user approval.** The user may:
- Approve the plan as-is
- Request changes to scope, assignments, or wave grouping
- Defer specific items to a later phase

Only the approved plan moves to Step 7.

### 7. Create the approved issues

For each approved draft:

```bash
gh issue create --title "{title}" --body "$(cat <<'EOF'
## Summary
{description}

## Acceptance Criteria
- [ ] {criterion 1}
- [ ] {criterion 2}

## Origin
{why this work exists — user request, retro finding, dependency, phase goal}
EOF
)" --label "phase-{N}" --label "{category}"
```

Then assign (assignee-label convention) and board-add if a board is configured:

```bash
gh issue edit {NUMBER} --add-label "{FIRSTNAME_LASTNAME}"
[ "$BOARD_ENABLED" = "true" ] && gh project item-add "$BOARD_NUM" --owner "$OWNER" --url "{ISSUE_URL}" || true
```

### 8. Record the phase doc

Write `$TEAM_DIR/phases/phase-{N}.md` capturing the approved plan: a `created: {date}`
line, the phase goals / exit criteria, and the tracking table of created issue numbers per
wave. `/phase-review` reads this doc as its source of truth — a phase without it cannot be
health-checked.

## What remains manual

- The Step-6 approval gate: the user approves the plan before any issue is created.
- Cross-team dependency resolution requires coordination outside this repo.
- Effort estimates are rough — actual complexity may shift items between waves.
