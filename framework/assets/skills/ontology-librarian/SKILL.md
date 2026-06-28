---
name: ontology-librarian
description: Read-only ontology reference — checks staleness of BOTH layers (hand-curated semantic overlay + generated structural index) and retrieves relevant context. Never modifies either layer.
args: query
---

The ontology librarian provides **read-only** access to the project ontology. It checks
staleness in **both layers** — the hand-curated **semantic overlay** and the generated
**structural index** — retrieves relevant context, and reports which references may be out of
date. It never modifies either layer.

> **Two-layer model.** The **semantic overlay** (`<ontology>/domain.yaml`, `services.yaml`,
> `conventions.md`, `<ontology>/repos/*.yaml`) is hand-curated and tracked by
> `<ontology>/checksums.json`. The **structural index** (`<ontology>/structural/llms.txt`,
> `code-graph.json`, `cross-repo-graph.json`) is generated wholesale by `ontology_gen` (+ the
> `ontology_gen.aggregate` cross-repo aggregator) — always-current when regenerated, never
> hand-edited, not checksum-tracked. The librarian surfaces both; staleness reports distinguish
> which layer is behind.
>
> `<ontology>` = `paths.ontology` from `.claude/framework.config.json` (default `ontology`).
> Read it once: `ONTO="$(jq -r '.paths.ontology // "ontology"' .claude/framework.config.json 2>/dev/null)"`.

The `query` argument is optional. If provided, it's a natural-language question or entity/service
name to look up. If omitted, runs a staleness check and provides a summary.

## When to use

- **Session start** — `/session-start` reports ontology health when this skill is installed.
- **Starting work** — look up relevant entities/services/patterns + the structural neighborhood
  of the code you're about to change.
- **Manual** — answer questions about the domain, architecture, or conventions.

## Instructions

### 1. Staleness check — BOTH layers

```bash
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ONTO="$(jq -r '.paths.ontology // "ontology"' "$REPO_ROOT/.claude/framework.config.json" 2>/dev/null || echo ontology)"
[ -d "$REPO_ROOT/$ONTO" ] || { echo "No ontology layer at $ONTO — nothing to report."; exit 0; }
```

**1a. Semantic overlay (checksums.json)** — count dirty files (`last_tracked != last_resolved`):

```bash
CK="$REPO_ROOT/$ONTO/checksums.json"
if [ -f "$CK" ]; then
  DIRTY=$(jq '[.files | to_entries[] | select(.value.last_tracked != .value.last_resolved)] | length' "$CK" 2>/dev/null)
  echo "Semantic overlay: ${DIRTY:-0} dirty file(s) — $([ "${DIRTY:-0}" -eq 0 ] && echo current || echo 'run /ontology-rebuild')"
else
  echo "Semantic overlay: no checksums.json (untracked)."
fi
```

Buckets: 0 = current · 1–5 = slightly behind · 6–15 = consider rebuild · 16+ = rebuild before work.
The librarian does NOT trigger the resolver — it reports so the user decides.

**1b. Structural index (committed index vs source tree)** — measured by the git commit that
last touched `llms.txt` vs source files changed since:

```bash
STRUCT="$REPO_ROOT/$ONTO/structural/llms.txt"
if [ -f "$STRUCT" ]; then
  SHA=$(git -C "$REPO_ROOT" log -1 --format=%H -- "$ONTO/structural/llms.txt" 2>/dev/null)
  grep '^# ' "$STRUCT" | head -5
  if [ -n "$SHA" ]; then
    CHANGED=$(git -C "$REPO_ROOT" diff --name-only "$SHA"..HEAD -- \
      '*.py' '*.ts' '*.tsx' '*.js' '*.jsx' '*.cypher' '*.cql' 2>/dev/null | wc -l | tr -d ' ')
    echo "Structural index: ${CHANGED:-0} source file(s) changed since last generation."
    [ "${CHANGED:-0}" -gt 0 ] && echo "  Regenerate: PYTHONPATH=.claude/lib python3 -m ontology_gen . --out $ONTO/structural/"
  fi
else
  echo "Structural index: not generated — PYTHONPATH=.claude/lib python3 -m ontology_gen . --out $ONTO/structural/"
fi
```

The two layers are independent: the overlay can be dirty while the structural index is current,
and vice versa.

### 2. Context retrieval (if a query was given)

**2a. Semantic overlay** — search `domain.yaml` (entities/relationships), `services.yaml`
(services/APIs/stores), `conventions.md` (patterns), `repos/*.yaml` (repo internals).

**2b. Structural index** — `llms.txt` is **section-loadable**: each `## <path>` block is
independent, so read only relevant sections rather than the whole file.

```bash
grep -n "^## .*${Q}\|- .*${Q}\|- class .*${Q}\|- func .*${Q}" "$REPO_ROOT/$ONTO/structural/llms.txt" | head -30
```

Node-id forms: file/module = repo-relative POSIX path (bare) or `<repo>/<path>` in the
cross-repo graph; symbol = `<path>::<qualname>`.

Present findings concisely under **Semantic overlay** / **Structural index** / **Staleness notes**.

### 3. Summary (if no query)

Give a brief health summary of both layers: overlay (dirty count, entity/service counts,
repos covered) and structural index (files/nodes/edges header, last generated, drift,
cross-repo graph present?).

### 4. Stale-reference warnings

When reporting query results, flag any contributing source files that are dirty (overlay) or
modified since the last structural regeneration.

## Remediation (the librarian reports; it never runs these)

| Layer | Stale signal | Remediation |
|-------|-------------|-------------|
| Semantic overlay | N dirty in `checksums.json` | `/ontology-rebuild` |
| Structural index (per repo) | N source files changed since last `llms.txt` commit | `PYTHONPATH=.claude/lib python3 -m ontology_gen . --out <ontology>/structural/` |
| Cross-repo graph | structural index or a child index updated | `PYTHONPATH=.claude/lib python3 -m ontology_gen.aggregate .` |
