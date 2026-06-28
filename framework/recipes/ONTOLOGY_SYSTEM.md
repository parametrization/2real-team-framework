# ONTOLOGY: two-layer ontology system (generator + tracker + librarian skills)

## Purpose

Give a project a structured, mostly-self-maintaining knowledge base of its own code and
domain — applied to a **meta + children** layout where the parent repo's immediate
subdirectories are themselves git repos. The product-neutral extraction of the source
project's ontology machinery.

## The two layers

| Layer | Contents | Update path | Tracked? |
|-------|----------|-------------|----------|
| **Semantic overlay** (hand-curated) | `<ontology>/domain.yaml`, `services.yaml`, `conventions.md`, `repos/*.yaml`, hand-edited `*.md` | `/ontology-rebuild` resolves dirty entries from code | `<ontology>/checksums.json` |
| **Structural index** (generated) | `<ontology>/structural/llms.txt`, `code-graph.json`, `cross-repo-graph.json` | regenerate with `ontology_gen` (+ `.aggregate`) | NO — always-current-by-regeneration |

`<ontology>` = `paths.ontology` from `.claude/framework.config.json` (default `ontology`).

## What it provides

- **`lib/ontology_gen/`** — a zero-dependency code-graph generator. `generate(root, out, name)`
  discovers git-tracked source (Python `ast` / TypeScript-by-regex / Cypher), extracts a
  file/symbol/edge graph, and writes `code-graph.json` (record-per-line, diff-friendly) +
  a section-loadable `llms.txt`. `aggregate(root)` **discovers** the in-scope repos (the parent
  + every immediate subdir that is a git repo) and unions their per-repo indices into one
  **`<repo>/`-namespaced** cross-repo graph; absent indices are skipped gracefully.
- **`hooks/ontology_tracker.py`** — PostToolUse change-tracker. On Edit/Write/MultiEdit to a
  hand-curated overlay file, records its SHA in `checksums.json` (`last_tracked`). **Inert by
  default** — does nothing unless an ontology dir (or `checksums.json`) exists, so it's safe to
  wire everywhere. Skips the generated `structural/` layer, `checksums.json` itself, worktree
  copies, and out-of-tree files. Advisory; never blocks.
- **`lib/ontology_gen/refresh.py`** — `refresh(root, …)` regenerates `structural/` **only when
  stale** (a source file newer than `code-graph.json`); deterministic, so a regen is byte-stable
  when nothing changed. For `meta-and-children` it also re-aggregates the cross-repo graph.
- **`hooks/ontology_refresh.py` + `hooks/start_dispatcher.py`** — a **SessionStart** hook that
  keeps the structural layer current automatically. `start_dispatcher` runs the config list
  `hooks.session_start` (default `["ontology_refresh"]`); the refresh hook is **inert unless an
  ontology dir exists** and never blocks session start. Wired by the bootstrapper's
  `SessionStart` matcher-less block.
- **`assets/ontology/` (seed overlay template)** — generic `domain.yaml` / `services.yaml` /
  `conventions.md` / `README.md`. `bootstrap.py --with-ontology` lays these into
  `<ontology>/` (skip-if-exists), which also *activates* the two ontology hooks (both inert
  until the dir exists).
- **`/ontology-librarian`** — read-only staleness (both layers) + lookup.
- **`/ontology-rebuild`** — reconcile the semantic overlay from code; sets `last_resolved`.

## Config

- `paths.ontology` — overlay + structural live here.
- `hooks.post_file: ["ontology_tracker"]` — dispatched by `post_dispatcher.py` for file tools
  (the bootstrapper wires a `Edit|Write|MultiEdit|NotebookEdit` PostToolUse matcher).
- `project.model` — `meta-and-children` is what the aggregator's discovery targets; a
  `single-repo` project just generates its own index (aggregation is a no-op union of one).

## Commands

```bash
# Per-repo structural index (run in each repo):
PYTHONPATH=.claude/lib python3 -m ontology_gen . --out ontology/structural/
# Cross-repo aggregation (run at the parent root; discovers child git-repos):
PYTHONPATH=.claude/lib python3 -m ontology_gen.aggregate .
# Explicit repo set override (repeatable):
PYTHONPATH=.claude/lib python3 -m ontology_gen.aggregate . --repo api=svc-api --repo web=svc-web
```

## How to adapt

- **More languages:** add an extractor module (mirror `python_ext.py` / `cypher_ext.py`) and
  wire its extensions into `generate._SUPPORTED` + `_extract_one`.
- **Different child discovery:** pass an explicit `repos={name: subdir}` to `aggregate()` (or
  `--repo` on the CLI) instead of the default `.git`-presence scan.
- **Lifecycle integration:** the `ontology_refresh` SessionStart hook already regenerates on
  staleness at every session start. `/session-start` also reports ontology health, and wave
  wrapup can call `ontology_gen.refresh.refresh(root, force=True)` to guarantee a fresh index
  before review. Add more SessionStart behaviours by appending to `hooks.session_start`.

## Tests

`framework/tests/test_ontology_gen.py` — generator artifacts/counts + import-edge resolution,
aggregator namespacing + graceful skip of absent indices + child discovery, and the tracker
hook (inert-without-ontology, overlay-edit recorded, structural/checksums/worktree/wrong-tool
skips).
