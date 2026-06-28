---
name: ontology-rebuild
description: Reconcile the hand-curated semantic overlay — scan dirty checksums, update ontology files + auto-updatable docs from code, mark resolved. Never touches the generated structural layer.
args: scope
---

Rebuild the **semantic overlay** for files that have changed since the last resolution pass.
The `scope` argument is optional — if omitted, processes all dirty files; otherwise `code`,
`docs`, or a specific repo name to limit scope.

> `<ontology>` = `paths.ontology` from `.claude/framework.config.json` (default `ontology`).
> Read it once: `ONTO="$(jq -r '.paths.ontology // "ontology"' .claude/framework.config.json 2>/dev/null || echo ontology)"`.

> **This skill resolves the SEMANTIC OVERLAY only.** For the generated structural index
> (`<ontology>/structural/llms.txt`, `code-graph.json`), run the generator instead:
> `PYTHONPATH=.claude/lib python3 -m ontology_gen . --out <ontology>/structural/` and the
> aggregator `PYTHONPATH=.claude/lib python3 -m ontology_gen.aggregate .`.

## Two-layer model

| Layer | Contents | Update path |
|-------|----------|-------------|
| **Semantic overlay** | `domain.yaml`, `services.yaml`, `conventions.md`, `repos/*.yaml`, hand-edited `*.md` | **This skill** — reads `checksums.json` dirty entries, reconciles against code |
| **Structural index** | `structural/llms.txt`, `code-graph.json`, `cross-repo-graph.json` | Generator (`ontology_gen` + `.aggregate`) — regenerated wholesale, never hand-edited |

- **Change Tracker** (`ontology_tracker` PostToolUse hook) — sets `last_tracked` on every
  Edit/Write to a hand-curated overlay file. Skips the generated structural layer.
- **Change Resolver** (this skill) — reads dirty entries, updates the overlay + auto-updatable
  docs, sets `last_resolved = last_tracked`.
- **Librarian** (`/ontology-librarian`) — read-only, surfaces both layers.

A file is "dirty" when `last_tracked != last_resolved` in `checksums.json`.

### The structural layer is OUT OF SCOPE

The structural layer is generated and always-current-by-regeneration; the tracker hook skips
it, so it never appears as a dirty entry and `/ontology-rebuild` must never hand-edit it.

### Code is the final arbiter of truth

This skill derives the overlay and auto-updatable docs **FROM the code**. When code and a
doc/ontology entry disagree, **the code wins** — update the doc/ontology to match the code,
never the reverse. Recommend-only docs (architecture docs, diagrams) are flagged for human
review rather than auto-rewritten, but the conflict is still reported with code as reference.

## Instructions

### 1. Read checksums and identify dirty files

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ONTO="$(jq -r '.paths.ontology // "ontology"' "$REPO_ROOT/.claude/framework.config.json" 2>/dev/null || echo ontology)"
cat "$REPO_ROOT/$ONTO/checksums.json" 2>/dev/null || { echo "No checksums.json — nothing to resolve."; exit 0; }
```

Build the list where `last_tracked != last_resolved`. If none, report "Ontology up to date" and
stop. If `scope` is given, filter: `code` (source extensions), `docs` (`.md`/`.rst`/`.txt`), or
`{repo-name}` (files under that repo's subdir).

### 2. Process files in order: code → docs → high-level-docs

1. **Source code** — extract entities, services, APIs, patterns, data models.
2. **Auto-updatable docs** (READMEs, CLAUDE.md, inline docs) — update if drifted from code.
3. **Recommend-only docs** (architecture docs, diagrams) — read for intent; note recommendations,
   do NOT modify.

For each file, determine the overlay file(s) it affects and update them:
- entities/relationships → `domain.yaml`
- services/APIs/stores/infra → `services.yaml`
- conventions/patterns/tooling → `conventions.md`
- repo internals → `repos/{repo-name}.yaml`

### 3. Cross-reference + consistency

Check for orphaned entities (referenced not defined), stale references (defined but gone from
source), and cross-repo integration consistency between `services.yaml` and repo files.

### 4. Update checksums

For each processed file set `last_resolved = last_tracked` and `resolved_at = now`. Also
re-track any overlay files modified during this pass.

### 5. Report

```
**Ontology Rebuild Complete**
Files processed: {count}
Overlay updated: domain.yaml {…}, services.yaml {…}, conventions.md {…}, repos/{name}.yaml {…}
Docs auto-updated: {list}
Recommend-only (human review): {file: change}
Consistency issues: {list or None}
```

### 6. Commit

Stage and commit overlay changes + any auto-updated docs, using your team's standards/quality
identity (or the project commit identity — per-commit `-c user.name/-c user.email`, never global
git config):

```bash
cd "$REPO_ROOT" && git add "$ONTO/" && \
  git -c user.name="<Name>" -c user.email="<email>" commit -m "ontology: rebuild — {summary}"
```

## What remains manual

- Recommend-only doc updates require human review.
- New top-level ontology categories should be discussed first.
- Removing entities requires confirmation — prefer marking deprecated.
- **The structural index is never resolved here** — regenerate it with the generator / aggregator.
