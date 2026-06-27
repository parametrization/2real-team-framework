---
name: plan-phase
description: Plan a phase by creating and reviewing issues
args: team_name, Phase number
---

Plan a phase of work for the `{team_name}` team. Decomposes phase scope into GitHub Issues, assigns them, reviews from multiple perspectives, and proposes a wave structure.

> See [`.claude/team/lifecycle.md`](../../team/lifecycle.md) § Phase Lifecycle for the canonical skill order and preconditions.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

## Instructions

### 1. Gather phase scope

**Start with the project board as the authoritative backlog** (charter `issues.md` § Wave Planning — Project Board Is Authoritative). Do NOT rely on `gh issue list --label X` alone — that will miss issues that never got a label, which systematically excludes work.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Pre-phase drift audit: ensure every open issue across repos is on project 2
for repo in noorinalabs-main noorinalabs-isnad-graph noorinalabs-user-service \
           noorinalabs-deploy noorinalabs-design-system noorinalabs-landing-page \
           noorinalabs-data-acquisition noorinalabs-isnad-ingest-platform; do
  gh issue list --repo "noorinalabs/$repo" --state open --limit 500 --json url --jq '.[].url'
done | sort -u > /tmp/all_open.txt

gh project item-list 2 --owner noorinalabs --format json --limit 1000 \
  --jq '.items[] | select(.content.url) | .content.url' | sort -u > /tmp/board_urls.txt

# Any output here means issues are missing from the board — add them before continuing:
comm -23 /tmp/all_open.txt /tmp/board_urls.txt

# Then pull the full backlog from the board for phase scoping
gh project item-list 2 --owner noorinalabs --format json --limit 1000 > /tmp/board.json
```

Additional context sources:
- Memory/project docs for stated goals
- Previous phase retro for carry-over items
- Cross-repo status (`cross-repo-status.json`) for dependency context

```bash
cat "$REPO_ROOT/cross-repo-status.json" 2>/dev/null
```

**The project board backlog is the candidate pool.** Filter it by phase theme, engineering capacity, and strategic priorities to arrive at the phase scope — but never plan from a narrower view (tech-debt label alone, or meta-issue body alone).

### 2. Decompose into issues

For each work item, create a GitHub Issue with:
- **Title:** Verb-first, specific (e.g., "Add RTL layout support to narrator card component")
- **Body:** Summary, acceptance criteria (checkbox list), origin/rationale, labels
- **Labels:** phase label (`phase-{N}`), repo label, category (`feature`, `bug`, `tech-debt`, `security`, `infra`)

```bash
gh issue create --title "{title}" --body "$(cat <<'EOF'
## Summary
{description}

## Acceptance Criteria
- [ ] {criterion 1}
- [ ] {criterion 2}

## Origin
{why this work exists — user request, retro finding, dependency, etc.}
EOF
)" --label "phase-{N}" --label "{category}"
```

### 3. Assign to team members

For each issue, determine the best assignee based on:
- Expertise match (check roster cards for tech preferences and work affinity)
- Current load balancing (check how many issues each member already has)
- Repo familiarity

Apply the assignee label:

```bash
gh issue edit {NUMBER} --add-label "{FIRSTNAME_LASTNAME}"
```

### 4. Multi-perspective review

Review each issue from 6 perspectives. For each perspective, assess whether the issue description is complete and whether there are concerns:

| Perspective | Focus |
|-------------|-------|
| **Architecture** | System design, API contracts, data model impact |
| **DevOps** | Deployment impact, infrastructure needs, CI changes |
| **Data** | Data migration, pipeline impact, schema changes |
| **Tech Lead** | Scope accuracy, effort estimate, risk |
| **QA** | Testability, edge cases, acceptance criteria completeness |
| **Security** | Auth impact, input validation, data exposure |

For each concern raised, either:
- Update the issue description to address it
- Post a review comment on the issue explaining the concern and resolution

```bash
gh issue comment {NUMBER} --body "$(cat <<'EOF'
**{Perspective} Review**

{findings — concerns, suggestions, or "No concerns"}
EOF
)"
```

### 5. Dependency analysis

Build a dependency graph across the proposed issues:
- Which issues must complete before others can start?
- Which issues touch the same files/systems (serialize to avoid conflicts)?
- Which cross-repo dependencies exist?

### 6. Propose wave structure

Group issues into waves based on:
- **Priority:** live bugs > security > tech debt > features > polish (per charter)
- **Dependencies:** blockers in earlier waves, dependents in later waves
- **Parallelism:** maximize concurrent work by grouping independent issues
- **Repo grouping:** minimize context-switching per agent

**Tech-debt intake per wave (+20%).** For each wave, after the feature/bug/security content is set, allocate **tech-debt-only** issues equal to **20% of that content (rounded up)** — add all available if fewer qualify (a shortfall is healthy, never backfilled with invented work). This is the standing intake policy that `/wave-scope` Step 8.5 enforces per-wave at scope-reconciliation time; surface it here at phase-plan time so the wave tables already reflect the TD allocation. Rationale: a cumulative TD-*ratio* gate whipsaws as the backlog shrinks, so steady *intake* replaces ratio-chasing. See [[feedback_td_intake_20pct_per_wave]] and `/wave-scope` Step 8.5.

**Last-wave-of-phase relaxation (owner 2026-06-16).** The +20% is a per-wave *cap* on every wave **except the last wave of the phase**, where it becomes a **floor**: deliberately pull in a large chunk of tech-debt (well beyond 20%) to clean up before phase exit. When laying out the wave table, size the final wave's TD allocation generously — clearing debt *is* the goal there — rather than holding it to the 20% line. The orchestrator/owner sizes the chunk at `/wave-scope` Step 8.5.

Present the proposed structure:

```
**Phase {N} Plan**

### Wave 1: {theme}
| Issue | Title | Assignee | Priority | Dependencies |
|-------|-------|----------|----------|--------------|
| #N    | ...   | Name     | bug      | None         |

### Wave 2: {theme}
| Issue | Title | Assignee | Priority | Dependencies |
|-------|-------|----------|----------|--------------|
| #N    | ...   | Name     | feature  | Wave 1: #M   |

**Total issues:** {count}
**Estimated waves:** {count}
**Cross-repo dependencies:** {list or "None"}
```

### 7. Present to user for approval

Display the full plan. **Do NOT create issues or start implementation without user approval.** The user may:
- Approve the plan as-is
- Request changes to scope, assignments, or wave grouping
- Defer specific items to a later phase

## What remains manual

- User must approve the plan before issues are created
- Cross-team dependency resolution requires coordination with other repo managers
- Effort estimates are rough — actual complexity may shift items between waves
