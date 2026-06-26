# Generic Lib Prompt: Git Union Merge-Driver for a Generated Graph Artifact

## Purpose

A custom git merge-driver for a single committed artifact (`code-graph.json`) that
parallel branches all **regenerate** — exactly the "parallel panels appending to a
shared file" conflict hazard. A textual 3-way merge produces spurious conflicts on
the sorted node/edge arrays even when the two sides touched different source files.
This driver instead **semantically union-merges**: parse both sides (and base),
union nodes by id and edges by `(src, dst, type)`, re-sort via the canonical model
ordering, write the result — so concurrent regenerations merge cleanly and
deterministically.

## Reusable Pattern

- **Semantic union, not text merge.** Load each side's JSON into the model, union
  into one `CodeGraph`, and serialize through the SAME canonical serializer the
  generator uses — so a merge result is byte-identical to a fresh regenerate.
- **Self-contained dual-import bootstrap.** Git invokes a merge-driver as a *plain
  script* (`python3 .../merge_driver.py %O %A %B`), not `python3 -m`, so at runtime
  there is no parent package and a relative `from .model import` fails. Try the
  package-relative import first (for `-m`/in-package callers); on `ImportError`,
  insert the lib dir on `sys.path` and import absolutely. This makes the script run
  under the exact invocation git uses, with no `PYTHONPATH` baked into git config.
- **Git's argument convention:** `driver %O %A %B [%P]` — `%O` base, `%A` ours
  (result is written back here), `%B` theirs. Exit 0 = merged cleanly.
- **Robust load:** a missing/corrupt side loads as empty rather than aborting.

## Algorithm

1. Parse argv: `base ours theirs [pathname]` (need ≥3).
2. Load nodes/edges from each present path; extend a single `CodeGraph`.
3. `to_dict()` (dedup by id / triple, re-sort) → `serialize_graph`.
4. Write the merged text back to the *ours* path (`%A`). Return 0.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Git union merge-driver for a generated code-graph.json.

Git calls: driver %O %A %B [%P]  (base, ours/output, theirs). Exit 0 = merged.
Wire via .gitattributes + git config:
    git config merge.codegraph-union.name 'code-graph union merge'
    git config merge.codegraph-union.driver \
        'python3 <path>/merge_driver.py %O %A %B %P'
"""
from __future__ import annotations

import json
import sys

# Git runs this as a PLAIN SCRIPT, so there is no parent package at runtime and the
# package-relative import fails. Try it first (for `-m`/in-package use), then
# bootstrap the lib dir onto sys.path and import absolutely.
try:
    from .model import CodeGraph, Edge, Node, serialize_graph
except ImportError:  # pragma: no cover — exercised via the plain-script subprocess
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ontology_gen.model import CodeGraph, Edge, Node, serialize_graph


def _load(path: str) -> tuple[list[Node], list[Edge]]:
    try:
        with open(path, encoding="utf-8") as h:
            data = json.load(h)
    except (OSError, json.JSONDecodeError):
        return [], []
    nodes = [Node(id=str(n["id"]), kind=str(n["kind"]), path=str(n["path"]),
                  line=int(n["line"]), lang=str(n["lang"]))
             for n in data.get("nodes", []) if isinstance(n, dict) and "id" in n]
    edges = [Edge(src=str(e["src"]), dst=str(e["dst"]), type=str(e["type"]))
             for e in data.get("edges", []) if isinstance(e, dict) and {"src", "dst", "type"} <= e.keys()]
    return nodes, edges


def union_merge(ours: str, theirs: str, base: str | None = None) -> str:
    graph = CodeGraph()
    for path in (p for p in (base, ours, theirs) if p):
        nodes, edges = _load(path)
        graph.nodes.extend(nodes); graph.edges.extend(edges)
    return serialize_graph(graph.to_dict())


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        sys.stderr.write("usage: merge_driver.py <base %O> <ours %A> <theirs %B> [%P]\n")
        return 2
    base, ours, theirs = argv[0], argv[1], argv[2]
    merged = union_merge(ours, theirs, base)
    with open(ours, "w", encoding="utf-8") as h:
        h.write(merged)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
```

## Adaptation Notes

- **Use this for any regenerated, committed, sorted-array artifact** that parallel
  branches conflict on. The union-by-key + canonical-reserialize approach
  generalizes beyond a code graph.
- **The dual-import bootstrap is essential.** Without the `ImportError` fallback the
  driver fails the moment git invokes it as a plain script. Keep the
  package-relative path first so `-m` and tests still work.
- **Serialize through the generator's canonical function**, so a merge equals a
  regenerate byte-for-byte — that equality is what makes the merge trustworthy.
- **Wire it via `.gitattributes` + `git config`** (a setup target/script);
  child repos that locate the driver in a sibling checkout register an absolute
  path resolved at registration time.
```
