# Ontology — two-layer knowledge base

This directory is the project's structured, mostly-self-maintaining knowledge base of its own
code and domain. It has **two layers**:

| Layer | Files | Who maintains | Tracked by |
|-------|-------|---------------|------------|
| **Semantic overlay** (hand-curated) | `domain.yaml`, `services.yaml`, `conventions.md`, `repos/*.yaml` | **you** (humans + agents) | `checksums.json` |
| **Structural index** (generated) | `structural/llms.txt`, `structural/code-graph.json`, `structural/cross-repo-graph.json` | the `ontology_gen` generator | not tracked — always-current by regeneration |

## Semantic overlay — the part you write

These files capture *intent* that can't be read off the code: what the domain entities mean,
what each service/component is for, and the conventions the project holds itself to. Edit them
by hand. The `ontology_tracker` hook records a checksum on every edit (`checksums.json`); when a
file's `last_tracked != last_resolved` it is **dirty** and `/ontology-rebuild` reconciles it
against the current code.

This is a **seed template** — replace the example entries with your project's real ones.

## Structural index — generated, don't hand-edit

`structural/` is regenerated wholesale from source by the generator:

```bash
# per-repo index (run in each repo):
PYTHONPATH=.claude/lib python3 -m ontology_gen . --out ontology/structural/
# cross-repo roll-up (meta+children — run at the parent root):
PYTHONPATH=.claude/lib python3 -m ontology_gen.aggregate .
```

The **`ontology_refresh` SessionStart hook** keeps it fresh automatically: at the start of each
session it regenerates the index if any source file is newer than it (deterministic, so a
no-op when nothing changed).

## Reading it

`/ontology-librarian` is the read-only entry point — it reports staleness of **both** layers
and retrieves relevant context. `/ontology-rebuild` reconciles the semantic overlay. Both
resolve `<ontology>` from `paths.ontology` in `.claude/framework.config.json` (default
`ontology`).

---

**This repo's choice:** unlike the generic default above, `2real-team-framework` **commits**
`structural/` so the index travels with the code and reviewers see graph changes in the diff.
The `ontology_refresh` hook keeps it deterministic — it only changes when source changes.
