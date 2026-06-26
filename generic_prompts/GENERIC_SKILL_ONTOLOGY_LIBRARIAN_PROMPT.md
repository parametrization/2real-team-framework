# Generic Skill: Ontology Librarian (Read-Only Knowledge Reference)

## Purpose

A **read-only** reference over the project's knowledge base ("ontology"). It
checks staleness, retrieves relevant context for a query, and reports which
references may be out of date. **It never modifies anything** — to act on
staleness, the user runs the resolver or the generator.

## Two-layer model

The ontology has two cooperating layers, surfaced together but updated
differently:

| Layer | Contents | Tracked by | Refreshed by |
|---|---|---|---|
| **Semantic overlay** | hand-curated domain/services/conventions + per-repo internals (YAML/MD) | a checksums file (dirty-tracking) | the **resolver** skill (`/ontology-rebuild`) |
| **Structural index** | generated file/module/symbol graph + cross-repo aggregation | NOT checksum-tracked | the **generator** (regenerated wholesale) |

The two are independent: the overlay can be dirty while the index is current, and
vice versa. Staleness reports distinguish which layer is behind.

The `query` argument is optional: if provided, it's a natural-language question or
entity/service name to look up; if omitted, run a staleness check + summary.

## When to use

- **Session start** — report ontology health for both layers.
- **Before starting work on an issue** — look up relevant entities, services,
  patterns before coding.
- **One-off changes** — check what the ontology knows about the area you'll modify.
- **Manual** — answer questions about domain, architecture, conventions.

## Workflow

### 0. Write the consultation sentinel (if a "librarian-consulted" hook exists)

If an advisory hook checks that the librarian was consulted before edits, write a
cwd-keyed sentinel file it recognizes as a second acceptance signal (robust
against transcript-flush races in worktree/subagent sessions). Namespace the
sentinel dir by skill name; keep it gitignored. **Do not remove this step** —
deleting it reintroduces the subagent race.

### 1. Staleness check — BOTH layers

**1a. Semantic overlay:** read the checksums file, count dirty files
(`last_tracked != last_resolved`). Report a graduated message (current / slightly
behind / consider rebuild / strongly recommend rebuild). The librarian does NOT
trigger the resolver — it reports so the user decides.

**1b. Structural index:** the generated index is always-current-by-regeneration;
measure staleness by comparing the commit that last touched the index against the
source files changed since. Report current / N files changed → regenerate
(printing the generator command). If never generated, say so.

### 2. Context retrieval (if a query was provided)

Search **both layers**:
- **Semantic overlay:** entity lookup (domain), service lookup (services),
  convention lookup, per-repo internals.
- **Structural index:** the index is **section-loadable** — each path block is
  independent, so read only the relevant sections rather than the whole large
  file. Match modules/functions/classes/edges relevant to the query.

Present findings concisely under headings for semantic overlay, structural index,
and staleness notes.

### 3. Summary (if no query)

Give a brief health summary for both layers: overlay health + entity/service
counts + repos covered + last rebuild; structural coverage (files/nodes/edges) +
last generated + drift + whether the cross-repo graph is present.

### 4. Stale-reference warnings

When reporting query results, check whether any contributing source files are
dirty (overlay) or modified since the last structural regeneration; if so, append
a warning naming them and the relevant layer.

## Remediation table (what to run when each layer is stale)

| Layer | Stale signal | Remediation |
|---|---|---|
| Semantic overlay | N dirty in checksums | the resolver skill (`/ontology-rebuild`) |
| Structural index | N source files changed since last index commit | the generator |
| Cross-repo graph | index regenerated / child indices updated | the aggregator |

The librarian never runs these — it only reports.

## What remains manual

- It never modifies ontology files or triggers the resolver/generator.
- Structural questions about the ontology *design* go to the project owner.

## Adaptation Notes

- The **read-only / report-only** contract is essential — this skill must never
  mutate the knowledge base; that keeps it safe to run anywhere, anytime.
- The **two-layer split** (hand-curated overlay vs generated index) is the key
  reusable design; if your knowledge base is single-layer, drop 1b/2b.
- **Section-loadability** of the generated index keeps lookups cheap on a large
  file — design the index so each path block is independently readable.
