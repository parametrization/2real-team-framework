#!/usr/bin/env python3
"""Assemble per-file :class:`FileInfo` records into the contract :class:`CodeGraph`.

This is where cross-file resolution happens — turning raw, file-local name strings
(imports, base classes, callees, re-exports) into typed edges between real node ids.

Resolution is deliberately conservative: an edge is emitted only when its target
resolves **unambiguously** to a known repo node. Ambiguous or external targets are
dropped from the graph (they survive as plain text in ``llms.txt``). This keeps the
graph integrity-clean (every endpoint is a node), low-noise, and deterministic — never
guessing a target when two candidates share a name.

Node id scheme (stable, human-readable):
    * file / module node : the repo-relative POSIX path  (e.g. ``.claude/lib/x.py``)
    * symbol node        : ``<path>::<qualname>``         (e.g. ``.claude/lib/x.py::Foo.bar``)
"""

from __future__ import annotations

from collections import defaultdict

from .model import CodeGraph, Edge, FileInfo, ImportInfo, Node, SymbolInfo, iter_symbols

# File extensions a TS-relative import may omit, in resolution-priority order.
_TS_RESOLVE_SUFFIXES = (
    ".ts",
    ".tsx",
    ".d.ts",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    "/index.ts",
    "/index.tsx",
    "/index.js",
    "/index.jsx",
)


def _symbol_node_id(path: str, qualname: str) -> str:
    return f"{path}::{qualname}"


def _posix_join_norm(parts: list[str]) -> str:
    """Join + normalize ``..``/``.`` segments without touching the filesystem."""
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
    """Resolves Python import strings to repo file paths."""

    def __init__(self, py_paths: list[str]) -> None:
        self._by_dotted: dict[str, str] = {}
        self._by_stem: dict[str, list[str]] = defaultdict(list)
        for path in py_paths:
            no_ext = path[:-3] if path.endswith(".py") else path
            segs = no_ext.split("/")
            if segs and segs[-1] == "__init__":
                dotted = ".".join(segs[:-1])
                stem = segs[-2] if len(segs) >= 2 else ""
            else:
                dotted = ".".join(segs)
                stem = segs[-1]
            if dotted:
                self._by_dotted.setdefault(dotted, path)
            if stem:
                self._by_stem[stem].append(path)

    def _by_dotted_lookup(self, dotted: str) -> str | None:
        return self._by_dotted.get(dotted)

    def resolve(self, imp: ImportInfo, importing_path: str) -> str | None:
        module = imp.module
        if module.startswith("."):
            return self._resolve_relative(imp, importing_path)
        return self._resolve_absolute(module)

    def _resolve_absolute(self, module: str) -> str | None:
        hit = self._by_dotted_lookup(module)
        if hit is not None:
            return hit
        last = module.rsplit(".", 1)[-1]
        candidates = self._by_stem.get(last, [])
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _resolve_relative(self, imp: ImportInfo, importing_path: str) -> str | None:
        level = len(imp.module) - len(imp.module.lstrip("."))
        tail = imp.module[level:]
        base_dir_parts = importing_path.split("/")[:-1]  # package dir of importer
        # level 1 == current package; each extra dot climbs one package up.
        up = level - 1
        if up > 0:
            base_dir_parts = base_dir_parts[:-up] if up <= len(base_dir_parts) else []
        target_parts = base_dir_parts + (tail.split(".") if tail else [])
        base = _posix_join_norm(target_parts)
        for candidate in (f"{base}.py", f"{base}/__init__.py"):
            if candidate in self._by_dotted_inverse:
                return candidate
        return None

    # Built lazily: the set of real py paths, for relative-candidate membership.
    @property
    def _by_dotted_inverse(self) -> set[str]:
        return set(self._by_dotted.values())


def _resolve_ts(target: str, importing_path: str, all_paths: set[str]) -> str | None:
    """Resolve a relative TS import/re-export specifier to a repo file path."""
    if not target.startswith("."):
        return None  # bare package import → external
    base_dir_parts = importing_path.split("/")[:-1]
    base = _posix_join_norm(base_dir_parts + target.split("/"))
    if base in all_paths:
        return base
    for suffix in _TS_RESOLVE_SUFFIXES:
        candidate = base + suffix
        if candidate in all_paths:
            return candidate
    return None


def _emit_symbols(
    graph: CodeGraph,
    file_info: FileInfo,
    parent_id: str,
    symbols: list[SymbolInfo],
) -> None:
    for sym in symbols:
        node_id = _symbol_node_id(file_info.path, sym.qualname)
        graph.add_node(
            Node(
                id=node_id,
                kind=sym.kind,
                path=file_info.path,
                line=sym.line,
                lang=file_info.lang,
            )
        )
        graph.add_edge(Edge(src=parent_id, dst=node_id, type="contains"))
        _emit_symbols(graph, file_info, node_id, sym.children)


def assemble(files: list[FileInfo]) -> CodeGraph:
    graph = CodeGraph()
    all_paths = {f.path for f in files}
    py_resolver = _PyResolver([f.path for f in files if f.lang == "python"])

    # Pass 1 — every file/module node and its contained symbol nodes (+ contains edges).
    for file_info in files:
        graph.add_node(
            Node(
                id=file_info.path,
                kind=file_info.kind,
                path=file_info.path,
                line=1,
                lang=file_info.lang,
            )
        )
        _emit_symbols(graph, file_info, file_info.path, file_info.symbols)

    # Pass 2 — cross-file + intra-file edges (endpoints already exist as nodes).
    for file_info in files:
        file_id = file_info.path

        # imports / imports_from
        for imp in file_info.imports:
            if file_info.lang == "python":
                target = py_resolver.resolve(imp, file_info.path)
            else:
                target = _resolve_ts(imp.module, file_info.path, all_paths)
            if target and target != file_id:
                graph.add_edge(Edge(src=file_id, dst=target, type=imp.kind))

        # references (TS re-exports)
        for target_spec in file_info.reexports:
            target = _resolve_ts(target_spec, file_info.path, all_paths)
            if target and target != file_id:
                graph.add_edge(Edge(src=file_id, dst=target, type="references"))

        # intra-file inherits + calls (unambiguous name match within the file)
        name_counts: dict[str, int] = defaultdict(int)
        class_names: dict[str, int] = defaultdict(int)
        for sym in iter_symbols(file_info.symbols):
            name_counts[sym.name] += 1
            if sym.kind == "class":
                class_names[sym.name] += 1

        for sym in iter_symbols(file_info.symbols):
            src_id = _symbol_node_id(file_info.path, sym.qualname)
            if sym.kind == "class":
                for base in sym.bases:
                    base_simple = base.rsplit(".", 1)[-1]
                    if class_names.get(base_simple) == 1:
                        target_sym = _find_symbol(file_info.symbols, base_simple, "class")
                        if target_sym is not None:
                            dst = _symbol_node_id(file_info.path, target_sym.qualname)
                            if dst != src_id:
                                graph.add_edge(Edge(src=src_id, dst=dst, type="inherits"))
            for callee in sym.calls:
                if name_counts.get(callee) == 1:
                    target_sym = _find_symbol(file_info.symbols, callee, None)
                    if target_sym is not None:
                        dst = _symbol_node_id(file_info.path, target_sym.qualname)
                        if dst != src_id:
                            graph.add_edge(Edge(src=src_id, dst=dst, type="calls"))

    return graph


def _find_symbol(symbols: list[SymbolInfo], name: str, kind: str | None) -> SymbolInfo | None:
    for sym in iter_symbols(symbols):
        if sym.name == name and (kind is None or sym.kind == kind):
            return sym
    return None
