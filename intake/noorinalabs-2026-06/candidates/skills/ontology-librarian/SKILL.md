---
name: ontology-librarian
description: Read-only ontology reference — staleness check, context lookup, and knowledge retrieval
args: query
---

The ontology librarian provides read-only access to the project ontology. It checks for staleness in **both layers** — the hand-curated semantic overlay AND the generated structural index — retrieves relevant context, and reports which references may be out of date. It never modifies either layer.

> **Two-layer model (C×T2, #820/#856):** The ontology has two cooperating layers. The **semantic overlay** (`domain.yaml`, `services.yaml`, `conventions.md`, `ontology/repos/*.yaml`) is hand-curated and tracked by `checksums.json`. The **structural index** (`ontology/structural/llms.txt`, `code-graph.json`, `cross-repo-graph.json`) is generated wholesale by the owned generator (`.claude/lib/ontology_gen/`, #855) + aggregator (`ontology_gen.aggregate`, #856) — always-current when regenerated, never hand-edited, not checksum-tracked. The librarian surfaces both; staleness reports distinguish which layer is behind.

> Note: all repo paths in bash blocks below are rooted at `$REPO_ROOT` to avoid cwd drift when the skill is invoked from a worktree or child-repo subdirectory (#149).

The `query` argument is optional. If provided, it's a natural language question or entity/service name to look up. If omitted, runs a staleness check and provides a summary.

## When to use

- **Session start** — run automatically to report ontology health (both layers)
- **Starting work on a GH issue** — look up relevant entities, services, and patterns before coding
- **One-off changes** — check what the ontology knows about the area you're about to modify
- **Manual invocation** — answer questions about the domain, architecture, or conventions

## Instructions

### 0. Write Hook 15 consultation sentinel

Before anything else, write a cwd-keyed sentinel file that Hook 15 (`enforce_librarian_consulted`) reads as a second acceptance signal. This is required because in worktree-subagent sessions the transcript JSONL the hook scans may not yet contain this Skill `tool_use` entry (race on transcript flush — see issue #169). The sentinel is a robust fallback that survives the flush race.

Per #176 the sentinel directory is namespaced by skill name under `.claude/.consulted/<skill>/` so future transcript-reading hooks can reuse the same scheme without colliding. The shared helper lives at `.claude/hooks/_consultation_sentinel.py` and exposes `write_consultation_sentinel(skill_name)` for any future skill-side caller.

```bash
mkdir -p .claude/.consulted/ontology-librarian
HASH=$(pwd | sha1sum | cut -c1-16)
printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(pwd)" > .claude/.consulted/ontology-librarian/"$HASH".marker
```

**Do not remove this step.** It is the Hook 15 consultation marker for the current cwd; deleting it re-introduces the #169 regression for subagents working in worktrees. The directory is gitignored.

### 1. Staleness check — BOTH layers

#### 1a. Semantic overlay (checksums.json)

Read `ontology/checksums.json` and count dirty files (where `last_tracked != last_resolved`):

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
cat "$REPO_ROOT/ontology/checksums.json"
```

Report semantic overlay staleness:
- **0 dirty files**: "Semantic overlay: current."
- **1–5 dirty files**: "{N} files pending — semantic overlay slightly behind; run `/ontology-rebuild`."
- **6–15 dirty files**: "{N} files pending — consider running `/ontology-rebuild`."
- **16+ dirty files**: "{N} files pending — strongly recommend `/ontology-rebuild` before starting work."

**Important:** The librarian does NOT trigger the resolver. It reports staleness so the user can decide.

#### 1b. Structural index staleness (committed index vs source tree)

The structural index at `ontology/structural/llms.txt` is generated wholesale — its staleness is measured by comparing the git commit that last touched `llms.txt` against the source files modified since that commit.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"

# Commit + date that last regenerated the structural index
STRUCT_COMMIT=$(git -C "$REPO_ROOT" log --oneline -1 --format="%H %ai" -- ontology/structural/llms.txt 2>/dev/null || echo "")
STRUCT_SHA=$(printf '%s' "$STRUCT_COMMIT" | cut -d' ' -f1)

# Read the header metadata from the committed index (files/nodes/edges/langs)
echo "Structural index header:"
grep "^# " "$REPO_ROOT/ontology/structural/llms.txt" 2>/dev/null | head -5
echo ""

if [ -z "$STRUCT_SHA" ]; then
  echo "STRUCTURAL INDEX: not yet generated — run the generator:"
  echo "  PYTHONPATH=.claude/lib python3 -m ontology_gen . --out ontology/structural/"
else
  # Count source files changed since the last index generation
  CHANGED=$(git -C "$REPO_ROOT" diff --name-only "$STRUCT_SHA"..HEAD -- \
    '*.py' '*.ts' '*.tsx' '*.js' '*.jsx' '*.cypher' '*.cql' 2>/dev/null | wc -l | tr -d ' ')
  echo "Structural index last generated: $STRUCT_COMMIT"
  echo "Source files changed since then: ${CHANGED:-0}"
  if [ "${CHANGED:-0}" -eq 0 ]; then
    echo "STRUCTURAL INDEX: current."
  elif [ "${CHANGED:-0}" -le 5 ]; then
    echo "STRUCTURAL INDEX: ${CHANGED} source file(s) changed — slightly behind."
    echo "  Regenerate: PYTHONPATH=.claude/lib python3 -m ontology_gen . --out ontology/structural/"
  else
    echo "STRUCTURAL INDEX: ${CHANGED} source files changed — consider regenerating before detailed structural queries."
    echo "  Regenerate: PYTHONPATH=.claude/lib python3 -m ontology_gen . --out ontology/structural/"
  fi
fi
```

Report structural staleness alongside the overlay staleness. The two are independent: the overlay can be dirty while the structural index is current, and vice versa.

### 2. Context retrieval (if query provided)

If a `query` argument was given, search **both layers** for relevant information.

#### 2a. Semantic overlay lookup

1. **Entity lookup** — search `ontology/domain.yaml` for matching entities, relationships
2. **Service lookup** — search `ontology/services.yaml` for matching services, APIs, data stores
3. **Convention lookup** — search `ontology/conventions.md` for relevant patterns
4. **Repo lookup** — search `ontology/repos/*.yaml` for repo-specific details

#### 2b. Structural index lookup

Search `ontology/structural/llms.txt` for modules, functions, classes, and edges relevant to the query. The file is **section-loadable** — each `## <path>` block is independent, so read only the relevant sections rather than the full 4,000+ line file.

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
# Find sections matching the query topic (path fragment, function name, class name)
grep -n "^## .*{query_keyword}\|- .*{query_keyword}\|- class .*{query_keyword}\|- func .*{query_keyword}" \
  "$REPO_ROOT/ontology/structural/llms.txt" | head -30
```

Read the full section for any matched path by extracting from the matching `## <path>` line to the blank line that precedes the next `## ` heading. For structural node ids used as `structural_ref:` in the overlay, the form is:
- File/module: `<repo-relative POSIX path>` (bare) or `<repo>/<path>` (central cross-repo graph)
- Symbol: `<path>::<qualname>` (e.g. `.claude/lib/ontology_gen/aggregate.py::aggregate`)

Present findings in a concise format:

```
**Ontology: {query}**

**Semantic overlay:**
  Entities: {matching entities and their relationships}
  Services: {matching services and their integrations}
  Conventions: {relevant patterns or rules}
  Repo details: {repo-specific information}

**Structural index:**
  Modules: {matching file sections from llms.txt}
  Symbols: {matching functions/classes/methods with line-number @N references}
  Edges: {imports/calls/inherits relevant to the query}

**Staleness notes:**
  Semantic overlay: {current | N files dirty — run /ontology-rebuild}
  Structural index: {current | N source files changed since last generation — regenerate with generator}
```

### 3. Summary (if no query)

If no query was provided, give a brief ontology health summary covering both layers:

```
**Ontology Status**

**Semantic overlay:**
  Health: {current | {N} files behind — run /ontology-rebuild}
  Domain: {count} entities, {count} relationships
  Services: {count} services, {count} data stores
  Repos covered: {list}
  Last full rebuild: {most recent resolved_at timestamp}

**Structural index (ontology/structural/llms.txt):**
  Coverage: {files=N nodes=N edges=N langs=...} (from header comment)
  Last generated: {commit sha + date}
  Drift: {current | N source files changed since last generation}
  Cross-repo graph: {present | absent} (ontology/structural/cross-repo-graph.json)

{staleness details and remediation instructions if any}
```

### 4. Stale reference warnings

When reporting query results, check if any of the source files that contributed to those ontology entries are dirty (semantic overlay) or have been modified since the last structural regeneration. If so, append a warning:

```
Warning: The following source files may have changed since the last update:
  - {file_path} (changed {tracked_at}, last resolved {resolved_at})  [semantic overlay]
  - {file_path} (modified after structural index @ {commit_sha})  [structural index]
```

## Remediation — what to run when each layer is stale

| Layer | Stale signal | Remediation |
|-------|-------------|-------------|
| Semantic overlay | `N` dirty in `checksums.json` | `/ontology-rebuild` |
| Structural index (parent) | `N` source files changed since last `llms.txt` commit | `PYTHONPATH=.claude/lib python3 -m ontology_gen . --out ontology/structural/` |
| Cross-repo graph | Structural index regenerated or child repo indices updated | `PYTHONPATH=.claude/lib python3 -m ontology_gen.aggregate .` |

The librarian never runs these — it only reports. To act on the staleness, run the appropriate command or skill (see `/session-start` Step 3 and `/wave-wrapup` Step 12 for the lifecycle integration points).

## What remains manual

- The librarian never modifies ontology files — use `/ontology-rebuild` (semantic overlay) or the generator (structural index) for that
- The librarian never triggers the resolver or generator — it reports, the user decides
- Structural questions about the ontology design should go to the project owner
