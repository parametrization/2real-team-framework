# Generic Lib Prompt: Cross-Repo Structural-Index Aggregator

## Purpose

Roll each repo's independently-generated structural index
(`ontology/structural/code-graph.json`) up into a single **cross-repo view**: a
union of every in-scope repo's nodes and edges, **namespaced by repo** so ids
never collide. This is the central-aggregator half of a distributed topology —
each repo commits its own generated index; a parent repo aggregates them.

## Reusable Pattern

- **Union + namespace.** Every node id/path and every edge endpoint is prefixed
  `<repo>/`, so the repo name becomes a virtual top-level directory and the same
  relative path in two repos yields two distinct nodes. Ids can never collide.
- **Offline and deterministic.** No DB, no network, no LLM. Reads whatever indices
  are present on disk.
- **Degrade gracefully.** A repo whose index hasn't been generated/committed yet is
  simply skipped and *reported* (present/absent status per repo), not an error.
  Malformed individual records are skipped rather than aborting the whole roll-up.
- **Same document shape + canonical serializer as a per-repo index**, so the
  cross-repo artifact is itself record-granular-diffable and union-mergeable by the
  same merge-driver. Route through the shared `to_dict()` so dedup/sort/integrity
  are identical to a fresh generate.
- **Repo map in one place** (short namespace → subdir), overridable via CLI for
  ad-hoc scoping.

## Algorithm

1. For each repo in the map (sorted, for deterministic reporting): resolve its
   index path; load it; if absent/unreadable/malformed-shape → record absent,
   continue.
2. Namespace every node and edge with the `<repo>/` prefix; skip records missing
   required keys.
3. Extend a single `CodeGraph` with all namespaced nodes/edges.
4. `to_dict()` (dedup + sort + integrity) → serialize → write the central artifact.
5. Report present/absent repos and contribution counts.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Cross-repo structural-index aggregator — union, namespaced by repo.

Offline, deterministic, degrades gracefully when a repo's index is absent.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .model import CodeGraph, Edge, GraphDict, Node, serialize_graph

# short namespace -> repo subdir relative to the parent root. "main"="." rolls the
# parent's own index in alongside the children.
DEFAULT_REPOS: dict[str, str] = {"main": ".", "child-a": "child-a", "child-b": "child-b"}
INDEX_RELPATH = "ontology/structural/code-graph.json"
DEFAULT_OUT = "ontology/structural/cross-repo-graph.json"


@dataclass(frozen=True)
class RepoIndexStatus:
    name: str
    index_path: Path
    present: bool
    nodes: int
    edges: int


def _load_namespaced(name: str, path: Path) -> tuple[list[Node], list[Edge]] | None:
    try:
        with path.open(encoding="utf-8") as h:
            data = json.load(h)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    raw_n, raw_e = data.get("nodes", []), data.get("edges", [])
    if not isinstance(raw_n, list) or not isinstance(raw_e, list):
        return None
    p = f"{name}/"
    nodes = [Node(id=p + str(n["id"]), kind=str(n["kind"]), path=p + str(n["path"]),
                  line=int(n["line"]), lang=str(n["lang"]))
             for n in raw_n if isinstance(n, dict) and {"id", "kind", "path", "line", "lang"} <= n.keys()]
    edges = [Edge(src=p + str(e["src"]), dst=p + str(e["dst"]), type=str(e["type"]))
             for e in raw_e if isinstance(e, dict) and {"src", "dst", "type"} <= e.keys()]
    return nodes, edges


def aggregate(main_root: Path, repos: dict[str, str] | None = None):
    repo_map = repos if repos is not None else DEFAULT_REPOS
    graph, statuses = CodeGraph(), []
    for name in sorted(repo_map):
        index_path = (main_root / repo_map[name] / INDEX_RELPATH).resolve()
        loaded = _load_namespaced(name, index_path)
        if loaded is None:
            statuses.append(RepoIndexStatus(name, index_path, False, 0, 0))
            continue
        nodes, edges = loaded
        graph.nodes.extend(nodes); graph.edges.extend(edges)
        statuses.append(RepoIndexStatus(name, index_path, True, len(nodes), len(edges)))
    return graph.to_dict(), statuses


def write_aggregate(main_root: Path, out_path: Path, repos=None):
    gd, statuses = aggregate(main_root, repos)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(serialize_graph(gd), encoding="utf-8")
    return len(gd["nodes"]), len(gd["edges"]), statuses


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aggregate")
    p.add_argument("main_root", nargs="?", default=".")
    p.add_argument("--out", default=DEFAULT_OUT)
    args = p.parse_args(argv)
    main_root = Path(args.main_root).resolve()
    if not main_root.is_dir():
        sys.stderr.write(f"error: not a directory: {main_root}\n")
        return 2
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = main_root / out_path
    nodes, edges, statuses = write_aggregate(main_root, out_path)
    present = [s for s in statuses if s.present]
    sys.stderr.write(f"aggregate: {out_path} (repos={len(present)}/{len(statuses)} "
                     f"nodes={nodes} edges={edges})\n")
    for s in statuses:
        mark = f"+ {s.name}: nodes={s.nodes} edges={s.edges}" if s.present else f"- {s.name}: absent"
        sys.stderr.write(f"  {mark}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

## Adaptation Notes

- **Namespacing is the collision guard.** Prefix every id, path, AND edge endpoint —
  missing the edge endpoints would leave dangling references after the union.
- **Absent is normal, not an error.** Index files come and go as repos generate/
  commit; report present/absent and keep exit 0 so the aggregator can run anytime.
- **Reuse the model's `to_dict` + serializer** so the cross-repo artifact obeys the
  same dedup/sort/integrity and is mergeable by the same union merge-driver.
- **Keep the repo map in one constant**, overridable for ad-hoc scoping; mirror it
  with whatever lists the same repo set elsewhere.
```
