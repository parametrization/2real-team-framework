# Generic Lib Prompt: Structural Code-Graph Data Model + Canonical Serializer

## Purpose

Define the data model for a **generated structural code-graph** — a machine- and
agent-readable index of a repository's files, symbols, and the typed edges between
them — plus a **deterministic, diff-friendly serializer** for it. This is the
contract layer that a generator, a cross-repo aggregator, an `llms.txt` renderer,
and a git merge-driver all build against, so the JSON shape is fixed and stable.

The model carries two layers of types: the **output contract** (Node / Edge /
CodeGraph) that serializes to the committed `code-graph.json`, and the
**intermediate extraction** types (FileInfo / SymbolInfo / ImportInfo) that every
per-language extractor emits, which the assembler turns into the contract graph.

## Reusable Pattern

- **Fixed enums as the interface.** `kind ∈ {file, module, class, interface, type,
  func, method}` and `edge type ∈ {contains, imports, imports_from, calls,
  inherits, references}`. Treat them as an interface, not an internal detail — a
  new kind is a contract change.
- **Stable node-id scheme:** a file/module node id is its repo-relative POSIX path;
  a symbol node id is `<path>::<qualname>`. Human-readable and collision-free
  within a repo.
- **Determinism is load-bearing.** `to_dict()` dedups (nodes by id, edges by the
  `(src, dst, type)` triple), filters edges to those whose BOTH endpoints are real
  nodes (graph integrity — no dangling ids), and sorts by a total order with an
  explicit tie-break (e.g. path, line, kind-rank, id). Same source → byte-identical
  JSON regardless of filesystem walk order.
- **One-record-per-line serialization, NOT `json.dumps(indent=2)`.** Pretty-printing
  bloats the file ~3x and makes a single changed record span many diff lines. One
  compact JSON object per line keeps the file small AND makes diffs record-granular
  (add/remove a node ⇒ exactly one added/removed line). Output is still valid JSON.
- **Single serializer for everyone.** Generator and merge-driver both serialize
  through this function, so a merge result is byte-identical to a fresh regenerate.
- **A single intermediate `FileInfo` shape** means adding a language only requires
  producing `FileInfo` objects — nothing downstream changes.

## Algorithm (`to_dict` + serialize)

1. Dedup nodes by id (first wins); sort by `sort_key`.
2. Compute the valid-id set; keep only edges with both endpoints valid; dedup by
   triple; sort by `sort_key`.
3. Serialize: emit `{"nodes": [ ...one compact object per line, comma-separated... ],
   "edges": [ ... ]}` with a single trailing newline.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Data model + canonical serializer for a structural code-graph."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TypedDict

NODE_KINDS = ("file", "module", "class", "interface", "type", "func", "method")
EDGE_TYPES = ("contains", "imports", "imports_from", "calls", "inherits", "references")
_KIND_RANK = {k: i for i, k in enumerate(NODE_KINDS)}


class NodeDict(TypedDict):
    id: str; kind: str; path: str; line: int; lang: str


class EdgeDict(TypedDict):
    src: str; dst: str; type: str


class GraphDict(TypedDict):
    nodes: list[NodeDict]; edges: list[EdgeDict]


@dataclass(frozen=True)
class Node:
    id: str; kind: str; path: str; line: int; lang: str

    def to_dict(self) -> NodeDict:
        return {"id": self.id, "kind": self.kind, "path": self.path,
                "line": self.line, "lang": self.lang}

    def sort_key(self) -> tuple:
        return (self.path, self.line, _KIND_RANK.get(self.kind, 99), self.id)


@dataclass(frozen=True)
class Edge:
    src: str; dst: str; type: str

    def to_dict(self) -> EdgeDict:
        return {"src": self.src, "dst": self.dst, "type": self.type}

    def sort_key(self) -> tuple:
        return (self.type, self.src, self.dst)


@dataclass
class CodeGraph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, n: Node) -> None: self.nodes.append(n)
    def add_edge(self, e: Edge) -> None: self.edges.append(e)

    def to_dict(self) -> GraphDict:
        seen, uniq = set(), []
        for n in self.nodes:
            if n.id not in seen:
                seen.add(n.id); uniq.append(n)
        uniq.sort(key=Node.sort_key)
        valid = {n.id for n in uniq}
        seen_e, uniq_e = set(), []
        for e in self.edges:
            if e.src not in valid or e.dst not in valid:
                continue
            key = (e.src, e.dst, e.type)
            if key in seen_e:
                continue
            seen_e.add(key); uniq_e.append(e)
        uniq_e.sort(key=Edge.sort_key)
        return {"nodes": [n.to_dict() for n in uniq], "edges": [e.to_dict() for e in uniq_e]}


# --- intermediate extraction types (what each language extractor emits) ---
@dataclass
class SymbolInfo:
    kind: str; name: str; qualname: str; line: int
    params: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    children: list["SymbolInfo"] = field(default_factory=list)


@dataclass
class ImportInfo:
    kind: str          # "imports" | "imports_from"
    module: str
    names: list[str] = field(default_factory=list)
    line: int = 0


@dataclass
class FileInfo:
    path: str; lang: str; kind: str
    summary: str = ""
    imports: list[ImportInfo] = field(default_factory=list)
    symbols: list[SymbolInfo] = field(default_factory=list)
    reexports: list[str] = field(default_factory=list)
    extra: dict[str, list[str]] = field(default_factory=dict)


def iter_symbols(symbols: list[SymbolInfo]) -> list[SymbolInfo]:
    out = []
    for s in symbols:
        out.append(s); out.extend(iter_symbols(s.children))
    return out


def serialize_graph(g: GraphDict) -> str:
    def _records(items) -> str:
        return ",\n".join(json.dumps(i, ensure_ascii=False, separators=(",", ":")) for i in items)
    parts = ["{", '"nodes": [']
    if g["nodes"]:
        parts.append(_records(g["nodes"]))
    parts += ["],", '"edges": [']
    if g["edges"]:
        parts.append(_records(g["edges"]))
    parts += ["]", "}"]
    return "\n".join(parts) + "\n"
```

## Adaptation Notes

- **Treat the enums as an interface.** Downstream consumers (aggregator, renderer,
  any DB loader) depend on the kind/edge-type vocabulary. Extend it deliberately
  and flag the owner — it is not an internal detail.
- **Keep `to_dict` the single dedup/sort/integrity choke point.** Every path that
  produces a graph (fresh generate, cross-repo aggregate, merge) routes through it,
  which is what makes a merge byte-identical to a regenerate.
- **Do not switch to pretty-printed JSON.** The one-record-per-line format is what
  makes the committed artifact small and its diffs record-granular.
- **Adding a language = producing `FileInfo`.** The intermediate shape is the seam;
  nothing else changes for a new extractor.
```
