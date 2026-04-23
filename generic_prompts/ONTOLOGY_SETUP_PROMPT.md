# Ontology System Setup Prompt

**Purpose:** Paste this prompt into a new Claude Code session over any repository to bootstrap the same ontology system. It is product-neutral — adapt the directory structure and file names to match the target project.

---

## What you're building

An **ontology system** that maintains a structured knowledge base of the project's domain entities, service topology, and conventions. The ontology lives in an `/ontology/` folder at the project root and is kept current through three roles:

| Role | Type | Purpose |
|------|------|---------|
| **Change Tracker** | PostToolUse hook (Edit/Write) | Automatically updates `checksums.json` whenever files are modified |
| **Change Resolver** | Skill (`/ontology-rebuild`) | Reads dirty checksums, processes changed files, updates ontology |
| **Librarian** | Skill (`/ontology-librarian`) | Read-only reference — staleness check, context lookup |

### Checksums model

`ontology/checksums.json` tracks every file with two hashes:
- `last_tracked` — current file hash (updated by the tracker hook on every Edit/Write)
- `last_resolved` — hash when the ontology was last rebuilt from this file (updated by the resolver)

When `last_tracked != last_resolved`, the file is **dirty** — it has changed since the ontology was last updated from it. A file can be edited multiple times between resolver runs; the tracker just keeps updating `last_tracked`.

## Step-by-step setup

### 1. Create the ontology directory structure

```
/ontology/
  checksums.json          # Change tracking (version-controlled)
  domain.yaml             # Entities, relationships, domain concepts
  services.yaml           # Services, APIs, data stores, integrations, infrastructure
  conventions.md          # Coding conventions, architectural patterns, shared tooling
  repos/                  # Per-repo internal details (if multi-repo project)
    {repo-name}.yaml      # One file per repo/module
```

**For single-repo projects**, skip the `repos/` subdirectory and put repo-specific details directly in `services.yaml`.

**Format guidance:**
- Use YAML when structure is crisp and machine-readable (entities, services, configs)
- Use Markdown when content is narrative (conventions, patterns, decisions)
- Both should be readable by humans AND useful to Claude

### 2. Create the Change Tracker hook

Create a Python script at `.claude/hooks/ontology_tracker.py`:

**Behavior:**
- Fires as a PostToolUse hook on Edit and Write tool calls
- Reads the `file_path` from `tool_input`
- Computes SHA256 of the file
- Updates `checksums.json`: sets `last_tracked` to new hash, preserves `last_resolved`
- Skips: `checksums.json` itself, `__pycache__`, `node_modules`, `.git/`, error logs
- Never blocks (exit 0 always — advisory hook)
- Writes atomically (tmp file + rename)

**Register in `.claude/settings.json`:**
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit",
        "hooks": [{ "type": "command", "command": "python3 /path/to/ontology_tracker.py", "timeout": 10 }]
      },
      {
        "matcher": "Write",
        "hooks": [{ "type": "command", "command": "python3 /path/to/ontology_tracker.py", "timeout": 10 }]
      }
    ]
  }
}
```

### 3. Create the Change Resolver skill (`/ontology-rebuild`)

Create `.claude/skills/ontology-rebuild/SKILL.md`:

**Behavior:**
1. Read `checksums.json`, find all files where `last_tracked != last_resolved`
2. If no dirty files, report "up to date" and stop
3. Process dirty files in order: **code → docs → high-level docs**
4. For each file, determine which ontology file(s) it affects and update them
5. **Auto-update** code-adjacent docs (READMEs, CLAUDE.md) if they've drifted from code
6. **Recommend-only** for: high-level docs (MS Office, PDFs), engineering docs, mermaid diagrams, architecture documents — read for intent but do NOT modify; compile recommendations for human review
7. After processing each file, set `last_resolved = last_tracked` in checksums
8. Also update checksums for any ontology files modified during the pass
9. Report: files processed, ontology changes, auto-updated docs, recommend-only changes
10. Commit ontology changes

**Optional scope argument:** `code`, `docs`, or a specific repo/module name to limit processing.

### 4. Create the Librarian skill (`/ontology-librarian`)

Create `.claude/skills/ontology-librarian/SKILL.md`:

**Behavior:**
1. Read `checksums.json`, count dirty files
2. Report staleness: "current" / "{N} files pending" / "significantly behind"
3. If a query argument is provided, search the ontology for matching entities, services, conventions, repo details
4. When reporting results, flag any source files that are dirty (stale warning)
5. **Never modifies** ontology files — that's the resolver's job
6. **Never triggers** the resolver — reports staleness so the user decides

### 5. Add session-start behavior

At the start of every session, three things should happen (add to `CLAUDE.md` and/or your team charter):

#### a. Ontology staleness check
Run `/ontology-librarian` to check if the ontology is behind. If significantly stale, recommend `/ontology-rebuild` before starting work.

#### Pre-code-change rule (mandatory)
**Every agent MUST consult `/ontology-librarian {topic}` before making code changes.** This is not just a session-start thing — it applies every time an agent is about to modify code, whether it's the main session, a spawned team agent, or a one-off fix. For spawned agents, the orchestrator runs the librarian and includes the output in the agent's prompt. This ensures all code changes are informed by current domain context and prevents architectural conflicts.

#### b. Milestone/wave/phase orientation
Determine the current state of the project's work cycle — whatever nomenclature the project uses (waves, phases, sprints, milestones):
- Read any status file or project board to identify the active milestone
- Report: current milestone, open vs closed items, blockers
- This grounds the session in what's actually happening, not what the charter assumed N milestones ago

#### c. Charter freshness check
The charter/process docs should be living documents that evolve with every milestone:
- Check for unapplied process change proposals from the most recent retrospective
- If new automation (hooks, skills) was introduced since the last charter update, verify it's documented
- Flag any stale charter sections to the user

```markdown
## Ontology

At the start of every session, run `/ontology-librarian` to check ontology staleness.
When starting work on a GH issue, run `/ontology-librarian {topic}` for domain context.

## Session Start

At session start, establish situational awareness:
1. Ontology check (`/ontology-librarian`)
2. Milestone orientation (read status file / project board)
3. Charter freshness check (unapplied retro proposals, undocumented new automation)
```

### 6. Integrate with existing workflows

If you have wave/retro/wrapup workflows:
- Add `/ontology-rebuild` as a step in your wrapup/finalization skill
- Add `/ontology-librarian` as a staleness check in your retro/review skill

### 7. Initial population

Run the resolver against the full codebase to seed the ontology:
1. Scan all source code — extract entities, services, APIs, patterns, data models
2. Scan all docs — check for drift, update where appropriate
3. Scan high-level docs — read for intent, note recommendations
4. Populate all ontology files with extracted knowledge
5. Seed `checksums.json` with hashes for all processed files (both `last_tracked` and `last_resolved` set to the same value)

### 8. Version control

- `checksums.json` MUST be version-controlled so anyone can update and commit the ontology
- All ontology files are version-controlled
- The tracker hook fires for all collaborators using Claude Code on this repo

## Docs update policy

| Doc type | Action |
|----------|--------|
| READMEs, CLAUDE.md, inline code docs | Auto-update to match code |
| High-level docs (MS Office, PDFs) | Read-only — recommend changes |
| Engineering docs, architecture docs | Read-only — recommend changes |
| Mermaid diagrams | Read-only — recommend changes |

## Key design decisions

- **Three separate roles** (tracker/resolver/librarian) because: the tracker is cheap (just hashes), the resolver is expensive (reads files, updates ontology), and the librarian is read-only (quick reference). Separating them means the tracker runs on every edit without slowing anything down, and the resolver only runs when explicitly invoked.
- **Two-hash model** (last_tracked vs last_resolved) because: a file may change multiple times between resolver runs. Only the resolver marks files as resolved.
- **Recommend-only for certain docs** because: MS Office files, architecture diagrams, and engineering docs often represent intentional human decisions. Auto-updating them risks overwriting deliberate choices.
- **Checksums.json is version-controlled** because: anyone should be able to run the resolver and commit the updated ontology. The checksums file is the source of truth for what's been processed.

## After implementation

Review the system in practice and update this prompt with any modifications made during testing. The prompt should always reflect the actual implemented system.
