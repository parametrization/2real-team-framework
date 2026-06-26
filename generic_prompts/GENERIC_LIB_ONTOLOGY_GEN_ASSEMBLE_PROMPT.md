# Generic Lib Prompt: Code-Graph Assembler (name → typed-edge resolution)

## Purpose

Turn a list of per-file extraction records (`FileInfo`, each carrying raw
file-local name strings for imports, base classes, callees, and re-exports) into
the assembled `CodeGraph` — minting file/symbol nodes and resolving those raw
names into typed edges between real node ids. This is where cross-file resolution
happens.

## Reusable Pattern

- **Conservative resolution.** Emit an edge ONLY when its target resolves
  **unambiguously** to a known repo node. Ambiguous or external targets are
  dropped from the graph (they survive as plain text in the human-readable
  index). This keeps the graph integrity-clean (every endpoint is a node),
  low-noise, and deterministic — never guess between two same-named candidates.
- **Two passes.** Pass 1 mints every file/module node and its contained symbol
  nodes (with `contains` edges), so Pass 2 can add cross-file/intra-file edges
  knowing every endpoint already exists.
- **Language-specific resolvers behind one interface.** A Python dotted/relative
  import resolver and a relative-path TS specifier resolver each map a raw import
  to a repo file path; the assembler calls whichever matches the file's language.
- **Intra-file inherits/calls by unambiguous name match.** Within a file, resolve
  a base class or callee only when exactly one symbol of the right kind has that
  name (`name_counts[...] == 1`) — otherwise skip.
- **Pure path math, no filesystem.** Relative-import resolution normalizes
  `..`/`.` segments against the importer's package dir without touching disk.

## Algorithm

1. Build the set of all file paths and a Python resolver from the `.py` paths.
2. **Pass 1:** for each file, add its file/module node, then recursively add
   symbol nodes + `contains` edges.
3. **Pass 2:** for each file:
   - resolve each import to a target path; if it resolves and isn't self → add an
     `imports`/`imports_from` edge;
   - resolve each re-export target → `references` edge;
   - for intra-file symbols, count names; for a class, resolve each base whose
     simple name is unique-in-file → `inherits`; for each callee unique-in-file →
     `calls`.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Assemble per-file FileInfo records into the contract CodeGraph.

Edges are emitted only on UNAMBIGUOUS resolution to a known repo node; ambiguous
or external targets are dropped (kept as text in the human index).
"""
from __future__ import annotations

from collections import defaultdict

from .model import CodeGraph, Edge, FileInfo, ImportInfo, Node, SymbolInfo, iter_symbols

_TS_SUFFIXES = (".ts", ".tsx", ".d.ts", ".js", ".jsx", ".mjs", ".cjs",
                "/index.ts", "/index.tsx", "/index.js", "/index.jsx")


def _sym_id(path: str, qualname: str) -> str:
    return f"{path}::{qualname}"


def _posix_join_norm(parts: list[str]) -> str:
    stack: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if stack:
                stack.pop()
            continue
        stack.append(part)
    return "/".join(stack)


class _PyResolver:
    def __init__(self, py_paths: list[str]) -> None:
        self._by_dotted: dict[str, str] = {}
        self._by_stem: dict[str, list[str]] = defaultdict(list)
        for path in py_paths:
            no_ext = path[:-3] if path.endswith(".py") else path
            segs = no_ext.split("/")
            if segs and segs[-1] == "__init__":
                dotted, stem = ".".join(segs[:-1]), (segs[-2] if len(segs) >= 2 else "")
            else:
                dotted, stem = ".".join(segs), segs[-1]
            if dotted:
                self._by_dotted.setdefault(dotted, path)
            if stem:
                self._by_stem[stem].append(path)

    def resolve(self, imp: ImportInfo, importing_path: str) -> str | None:
        if imp.module.startswith("."):
            level = len(imp.module) - len(imp.module.lstrip("."))
            tail = imp.module[level:]
            base = importing_path.split("/")[:-1]
            up = level - 1
            if up > 0:
                base = base[:-up] if up <= len(base) else []
            target = _posix_join_norm(base + (tail.split(".") if tail else []))
            real = set(self._by_dotted.values())
            for c in (f"{target}.py", f"{target}/__init__.py"):
                if c in real:
                    return c
            return None
        hit = self._by_dotted.get(imp.module)
        if hit:
            return hit
        cands = self._by_stem.get(imp.module.rsplit(".", 1)[-1], [])
        return cands[0] if len(cands) == 1 else None


def _resolve_ts(target: str, importing_path: str, all_paths: set[str]) -> str | None:
    if not target.startswith("."):
        return None
    base = _posix_join_norm(importing_path.split("/")[:-1] + target.split("/"))
    if base in all_paths:
        return base
    for suf in _TS_SUFFIXES:
        if base + suf in all_paths:
            return base + suf
    return None


def _emit_symbols(graph, fi, parent_id, symbols) -> None:
    for sym in symbols:
        nid = _sym_id(fi.path, sym.qualname)
        graph.add_node(Node(id=nid, kind=sym.kind, path=fi.path, line=sym.line, lang=fi.lang))
        graph.add_edge(Edge(src=parent_id, dst=nid, type="contains"))
        _emit_symbols(graph, fi, nid, sym.children)


def _find(symbols, name, kind):
    for s in iter_symbols(symbols):
        if s.name == name and (kind is None or s.kind == kind):
            return s
    return None


def assemble(files: list[FileInfo]) -> CodeGraph:
    graph, all_paths = CodeGraph(), {f.path for f in files}
    py = _PyResolver([f.path for f in files if f.lang == "python"])
    for fi in files:  # Pass 1
        graph.add_node(Node(id=fi.path, kind=fi.kind, path=fi.path, line=1, lang=fi.lang))
        _emit_symbols(graph, fi, fi.path, fi.symbols)
    for fi in files:  # Pass 2
        for imp in fi.imports:
            t = py.resolve(imp, fi.path) if fi.lang == "python" else _resolve_ts(imp.module, fi.path, all_paths)
            if t and t != fi.path:
                graph.add_edge(Edge(src=fi.path, dst=t, type=imp.kind))
        for spec in fi.reexports:
            t = _resolve_ts(spec, fi.path, all_paths)
            if t and t != fi.path:
                graph.add_edge(Edge(src=fi.path, dst=t, type="references"))
        names, classes = defaultdict(int), defaultdict(int)
        for s in iter_symbols(fi.symbols):
            names[s.name] += 1
            if s.kind == "class":
                classes[s.name] += 1
        for s in iter_symbols(fi.symbols):
            src = _sym_id(fi.path, s.qualname)
            if s.kind == "class":
                for base in s.bases:
                    bs = base.rsplit(".", 1)[-1]
                    if classes.get(bs) == 1:
                        tgt = _find(fi.symbols, bs, "class")
                        if tgt and _sym_id(fi.path, tgt.qualname) != src:
                            graph.add_edge(Edge(src=src, dst=_sym_id(fi.path, tgt.qualname), type="inherits"))
            for callee in s.calls:
                if names.get(callee) == 1:
                    tgt = _find(fi.symbols, callee, None)
                    if tgt and _sym_id(fi.path, tgt.qualname) != src:
                        graph.add_edge(Edge(src=src, dst=_sym_id(fi.path, tgt.qualname), type="calls"))
    return graph
```

## Adaptation Notes

- **Conservatism is the design, not a limitation.** Resolving a target only when it
  is unambiguous is what keeps the graph clean and deterministic. Better to drop an
  ambiguous edge than to guess and mislead a consumer.
- **Add a language by adding a resolver.** The assembler is language-agnostic apart
  from the per-language import resolver it dispatches to; everything else (node
  minting, intra-file inherits/calls) works off the shared `FileInfo`.
- **Endpoints must already be nodes.** The two-pass order guarantees Pass 2 never
  references an unminted node; the model's `to_dict` additionally drops any edge
  with a missing endpoint as a backstop.
```
