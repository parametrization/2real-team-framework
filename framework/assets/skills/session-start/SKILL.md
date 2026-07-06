---
name: session-start
description: "Run first in every session — loads memory, confirms team, reads the last handoff, and reports git/PR/CI + lifecycle + ontology status in one table."
---

# Session Start Protocol

Invoke `/session-start` as the **first action in a new session**, before responding to the
user's request. It orients you: what the project is, where the work left off, and what state
the repo + lifecycle are in. The user's actual request is handled after this completes.

This skill is **config-driven and fail-open**: every step reads `paths.*` from
`.claude/framework.config.json` and **skips cleanly** when a subsystem isn't present (no
ontology dir, no state file, no roster, no `gh`). A fresh single-repo project runs a short
version; a meta+children project runs the full sweep. Nothing here mutates state.

> All paths are rooted at `$REPO_ROOT` (re-derived per block, since Skill bash blocks are
> independent shells). For a meta-repo, `$REPO_ROOT` is the parent; child repos live in
> immediate subdirectories that are themselves git repos.

## Instructions

Run the steps below; independent ones may run in parallel. Present one concise status table at
the end.

### Step 0 — Resolve config + root

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CFG="$REPO_ROOT/.claude/framework.config.json"
get() { jq -r "$1 // empty" "$CFG" 2>/dev/null; }   # fail-open dotted read
MEM_DIR="$REPO_ROOT/$(get '.paths.memory' || echo .claude/memory)"
TEAM_DIR="$REPO_ROOT/$(get '.paths.team' || echo .claude/team)"
ONTO_DIR="$REPO_ROOT/$(get '.paths.ontology' || echo ontology)"
STATE_FILE="$REPO_ROOT/$(get '.paths.state_file' || echo .claude/state.json)"
PROJECT_MODEL="$(get '.project.model' || echo single-repo)"
```

### Step 1 — Memory (load the index)

```bash
[ -f "$MEM_DIR/MEMORY.md" ] && cat "$MEM_DIR/MEMORY.md" || echo "No project memory index."
```

Read on-demand any topic file whose one-line hook looks relevant to the user's request.

### Step 2 — Team orientation

```bash
[ -f "$TEAM_DIR/roster.json" ] && jq -r 'to_entries[] | "  \(.key) — \(.value)"' "$TEAM_DIR/roster.json" 2>/dev/null \
  || echo "No roster — solo/unconfigured."
if [ -f "$REPO_ROOT/.claude/lib/roster_consistency_check.py" ]; then
  python3 "$REPO_ROOT/.claude/lib/roster_consistency_check.py" --repo-root "$REPO_ROOT" 2>/dev/null \
    || echo "roster drift — see roster_consistency_check.py output above (advisory only)."
fi
```

Confirm the single implicit team. Spawn members via the `Agent` tool when work needs them
(only the orchestrator spawns; managers request spawns via `SendMessage`).

`roster_consistency_check.py` is advisory-only (non-blocking): it flags `roster.json` <->
`roster/*.md` drift (e.g. a hand-edited card whose `user.email` no longer matches the roster
allowlist) without halting the session. For a meta+children project, a CI job can additionally run
`.claude/lib/roster_union_sync.py --owner <org>` (`continue-on-error`) to catch a child persona
missing from the parent's union roster — see that module's docstring for the local-vs-remote
resolution it uses.

### Step 3 — Handoff (read where the last session left off)

```bash
HANDOFF="$MEM_DIR/handoff.md"
[ -f "$HANDOFF" ] && { echo "=== Last handoff ==="; cat "$HANDOFF"; } || echo "No prior handoff."
```

This is the pickup point. `/handoff` writes it at session end.

### Step 4 — Repo + change state

```bash
echo "Branch: $(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
git -C "$REPO_ROOT" status -sb | head -1
if command -v gh >/dev/null 2>&1; then
  gh pr list --state open --json number,title,headRefName --jq '.[] | "  PR #\(.number) \(.title)"' 2>/dev/null || true
  CUR="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
  gh pr view "$CUR" --json statusCheckRollup \
    --jq '.statusCheckRollup[]? | "  \(.name // .context): \(.conclusion // .state)"' 2>/dev/null || true
fi
```

For a meta-repo (`PROJECT_MODEL == meta`), repeat the open-PR check per child git-repo subdir.

### Step 5 — Lifecycle / wave status

```bash
if [ -f "$STATE_FILE" ] && [ -f "$REPO_ROOT/.claude/lib/lifecycle.py" ]; then
  python3 "$REPO_ROOT/.claude/lib/lifecycle.py" state show 2>/dev/null || true
  python3 "$REPO_ROOT/.claude/lib/lifecycle.py" wave peek 2>/dev/null || true
  python3 "$REPO_ROOT/.claude/lib/lifecycle.py" merge-model get 2>/dev/null || true
else
  echo "No lifecycle state — project not running waves (or pre-first-wave)."
fi
```

### Step 6 — Ontology freshness (if present)

```bash
if [ -d "$ONTO_DIR" ]; then
  if ls "$REPO_ROOT/.claude/skills/ontology-librarian" >/dev/null 2>&1; then
    echo "Ontology present — run /ontology-librarian for a staleness report (both layers)."
  else
    echo "Ontology dir present at $ONTO_DIR (no librarian skill installed yet)."
  fi
else
  echo "No ontology layer."
fi
```

When the librarian skill is installed, prefer invoking `/ontology-librarian` here for the real
two-layer staleness check (semantic overlay + structural index).

> The **`ontology_refresh` SessionStart hook** (wired in `settings.json` when installed) already
> regenerates the *structural* layer on staleness before this skill runs, so the structural index
> is current by the time you read it. This step's job is to surface the report (and flag a dirty
> *semantic overlay*, which the hook never touches — that's `/ontology-rebuild`'s job).

### Step 7 — Charter / feedback freshness

```bash
FB="$TEAM_DIR/feedback_log.md"
[ -f "$FB" ] && echo "feedback_log.md present — scan tail for unapplied proposals." || echo "No feedback log."
```

### Step 8 — Report

Emit ONE table the user reads at a glance:

```
| Area       | Status                                            |
|------------|---------------------------------------------------|
| Memory     | {N memories | none}                               |
| Team       | {N members | solo}                                |
| Handoff    | {pickup summary | none}                           |
| Repo       | branch {X}, {clean|dirty}, {N} open PRs           |
| CI         | {green | red: <job> | none}                       |
| Lifecycle  | {wave {X} <phase> · merge-model {Y} | none}       |
| Ontology   | {present → /ontology-librarian | none}            |
| Charter    | {N unapplied proposals | clean | n/a}             |
```

Then address the user's request.
