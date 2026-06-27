#!/usr/bin/env python3
"""Data model for the owned structural ontology generator (main#855, #820 C×T2).

Two layers of types live here:

* The **output contract** types — :class:`Node`, :class:`Edge`, :class:`CodeGraph` —
  serialize to the ``code-graph.json`` interface fixed in issue #855 that #856/#1128
  build against::

      {"nodes": [{id, kind, path, line, lang}],
       "edges": [{src, dst, type}]}

  with ``kind ∈ {file, module, class, interface, type, func, method}`` and
  ``type ∈ {contains, imports, imports_from, calls, inherits, references}``.

  ``interface`` and ``type`` were added in main#870 to capture TypeScript interface and
  type-alias declarations that were previously invisible in TS-heavy repos (~82 decls
  invisible in the isnad-graph pilot).

* The **intermediate extraction** types — :class:`FileInfo`, :class:`SymbolInfo`,
  :class:`ImportInfo` — are the language-agnostic shape every per-language extractor
  (Python ``ast`` / TypeScript / Cypher) emits. The assembler turns them into the
  contract graph, and the ``llms.txt`` renderer reads them directly. Keeping a single
  intermediate shape means a new language only has to produce ``FileInfo`` objects.

Determinism is load-bearing (issue #855: "stable ordering so git diffs are minimal").
:meth:`CodeGraph.to_dict` sorts nodes and edges by a total order and dedups, so the
same source always yields byte-identical JSON regardless of filesystem walk order.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TypedDict

# Contract enums — the fixed vocabulary #856/#1128 build against. Do not extend
# without flagging the #855 owner (the JSON is an interface, not an internal detail).
# ``interface`` and ``type`` added in main#870 for TypeScript interface/type-alias decls.
NODE_KINDS = ("file", "module", "class", "interface", "type", "func", "method")
EDGE_TYPES = ("contains", "imports", "imports_from", "calls", "inherits", "references")

# Stable tie-break rank for sorting nodes that share (path, line).
_KIND_RANK = {kind: i for i, kind in enumerate(NODE_KINDS)}


class NodeDict(TypedDict):
    """Serialized node — the fixed ``code-graph.json`` node shape (#855)."""

    id: str
    kind: str
    path: str
    line: int
    lang: str


class EdgeDict(TypedDict):
    """Serialized edge — the fixed ``code-graph.json`` edge shape (#855)."""

    src: str
    dst: str
    type: str


class GraphDict(TypedDict):
    """The whole ``code-graph.json`` document shape."""

    nodes: list[NodeDict]
    edges: list[EdgeDict]


@dataclass(frozen=True)
class Node:
    """A graph node — a file/module or a symbol defined within one."""

    id: str
    kind: str
    path: str
    line: int
    lang: str

    def to_dict(self) -> NodeDict:
        # Explicit key order = the contract field order (id, kind, path, line, lang).
        return {
            "id": self.id,
            "kind": self.kind,
            "path": self.path,
            "line": self.line,
            "lang": self.lang,
        }

    def sort_key(self) -> tuple[str, int, int, str]:
        return (self.path, self.line, _KIND_RANK.get(self.kind, 99), self.id)


@dataclass(frozen=True)
class Edge:
    """A typed, directed edge between two node ids."""

    src: str
    dst: str
    type: str

    def to_dict(self) -> EdgeDict:
        return {"src": self.src, "dst": self.dst, "type": self.type}

    def sort_key(self) -> tuple[str, str, str]:
        return (self.type, self.src, self.dst)


@dataclass
class CodeGraph:
    """The assembled structural graph for one repo — serializes to ``code-graph.json``."""

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, node: Node) -> None:
        self.nodes.append(node)

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)

    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}

    def to_dict(self) -> GraphDict:
        """Deterministic, deduplicated ``{"nodes": [...], "edges": [...]}``.

        Nodes are deduped by id (first occurrence wins). Edges are deduped by the
        full (src, dst, type) triple AND filtered to those whose both endpoints are
        real nodes — graph integrity: every edge endpoint resolves to a node, so a
        consumer never dereferences a dangling id.
        """
        seen_nodes: set[str] = set()
        unique_nodes: list[Node] = []
        for node in self.nodes:
            if node.id in seen_nodes:
                continue
            seen_nodes.add(node.id)
            unique_nodes.append(node)
        unique_nodes.sort(key=Node.sort_key)

        valid_ids = {n.id for n in unique_nodes}
        seen_edges: set[tuple[str, str, str]] = set()
        unique_edges: list[Edge] = []
        for edge in self.edges:
            if edge.src not in valid_ids or edge.dst not in valid_ids:
                continue
            key = (edge.src, edge.dst, edge.type)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            unique_edges.append(edge)
        unique_edges.sort(key=Edge.sort_key)

        return {
            "nodes": [n.to_dict() for n in unique_nodes],
            "edges": [e.to_dict() for e in unique_edges],
        }


# ----------------------------------------------------------------------------
# Intermediate extraction types — what each language extractor produces.
# ----------------------------------------------------------------------------


@dataclass
class SymbolInfo:
    """A class / function / method extracted from a source file.

    ``bases`` (class base names) and ``calls`` (callee names) are raw, file-local
    name strings; the assembler resolves them to node ids where it can.
    """

    kind: str  # one of: class, func, method
    name: str
    qualname: str
    line: int
    params: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    children: list[SymbolInfo] = field(default_factory=list)


@dataclass
class ImportInfo:
    """One import statement.

    ``kind`` is ``"imports"`` (``import X``) or ``"imports_from"``
    (``from X import a, b``). ``module`` is the imported module string; ``names`` are
    the imported member names (empty for a plain ``import``).
    """

    kind: str
    module: str
    names: list[str] = field(default_factory=list)
    line: int = 0


@dataclass
class FileInfo:
    """Language-agnostic structural summary of one source file."""

    path: str  # repo-relative, POSIX separators
    lang: str  # python | typescript | javascript | cypher
    kind: str  # module (python) | file (everything else)
    summary: str = ""
    imports: list[ImportInfo] = field(default_factory=list)
    symbols: list[SymbolInfo] = field(default_factory=list)
    # Re-export targets (TS ``export ... from './x'``) → ``references`` edges.
    reexports: list[str] = field(default_factory=list)
    # Language-specific extras for the llms.txt section (e.g. cypher labels/rels).
    extra: dict[str, list[str]] = field(default_factory=dict)


def iter_symbols(symbols: list[SymbolInfo]) -> list[SymbolInfo]:
    """Flatten a nested symbol tree into a pre-order list."""
    out: list[SymbolInfo] = []
    for sym in symbols:
        out.append(sym)
        out.extend(iter_symbols(sym.children))
    return out


def serialize_graph(graph_dict: GraphDict) -> str:
    """Canonical ``code-graph.json`` text — one record per line, contract key order.

    NOT ``json.dumps(indent=2)``: pretty-printing puts every field on its own line,
    which both bloats the file (~3x) and makes git diffs span many lines per changed
    record. One compact JSON object per line keeps the file small AND makes diffs
    record-granular — add/remove a node ⇒ exactly one added/removed line (issue #855:
    "deterministic output … so git diffs are minimal"). The output is still valid JSON.

    Both the generator and the merge-driver serialize through here, so a merge result is
    byte-identical to a fresh regenerate.
    """

    def _records(items: list[NodeDict] | list[EdgeDict]) -> str:
        rendered = [
            json.dumps(item, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
            for item in items
        ]
        return ",\n".join(rendered)

    parts = ["{", '"nodes": [']
    if graph_dict["nodes"]:
        parts.append(_records(graph_dict["nodes"]))
    parts.append("],")
    parts.append('"edges": [')
    if graph_dict["edges"]:
        parts.append(_records(graph_dict["edges"]))
    parts.append("]")
    parts.append("}")
    return "\n".join(parts) + "\n"
