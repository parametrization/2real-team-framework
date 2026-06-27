#!/usr/bin/env python3
"""Python structural extractor — stdlib ``ast`` only, zero third-party deps (#855).

Produces a :class:`~ontology_gen.model.FileInfo` per ``.py`` file capturing modules,
classes, functions/methods, imports, intra-file calls and base classes. Granularity is
deliberately module/class/function — NOT per-statement — to keep the ``llms.txt`` and
``code-graph.json`` token-economical (the C×T2 property graphify lost on, eval #854).

Scope rules (token economy):

* Top-level functions and classes are captured; class bodies are recursed for methods
  and nested classes. Function bodies are **not** recursed for nested ``def`` closures
  (low structural value, high token cost) — but their full subtree IS scanned for
  ``calls`` so the call list is complete.
* ``bases``/``calls`` are raw file-local name strings; the assembler resolves them.
"""

from __future__ import annotations

import ast

from .model import FileInfo, ImportInfo, SymbolInfo


def _format_params(args: ast.arguments) -> list[str]:
    """Flatten an ``ast.arguments`` into an ordered list of parameter display names."""
    params: list[str] = []
    params.extend(a.arg for a in getattr(args, "posonlyargs", []))
    params.extend(a.arg for a in args.args)
    if args.vararg is not None:
        params.append(f"*{args.vararg.arg}")
    params.extend(a.arg for a in args.kwonlyargs)
    if args.kwarg is not None:
        params.append(f"**{args.kwarg.arg}")
    return params


def _base_name(node: ast.expr) -> str | None:
    """Render a class-base expression to a dotted name (``A``, ``mod.A``); else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _base_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _call_name(node: ast.expr) -> str | None:
    """Render a call target to a simple name.

    ``foo()`` → ``foo``; ``obj.bar()`` / ``self.bar()`` → ``bar`` (the attribute name,
    so a same-class method call resolves). Anything more exotic → None.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _collect_calls(body: list[ast.stmt]) -> list[str]:
    """All callee names invoked anywhere within ``body`` (deduped, source order)."""
    seen: set[str] = set()
    names: list[str] = []
    for stmt in body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Call):
                name = _call_name(sub.func)
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
    return names


def _build_symbol(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    qual_prefix: str,
    *,
    in_class: bool,
) -> SymbolInfo:
    name = node.name
    qualname = f"{qual_prefix}.{name}" if qual_prefix else name

    if isinstance(node, ast.ClassDef):
        bases = [b for b in (_base_name(base) for base in node.bases) if b is not None]
        sym = SymbolInfo(
            kind="class",
            name=name,
            qualname=qualname,
            line=node.lineno,
            bases=bases,
        )
        # Recurse class body for methods and nested classes (but not free functions
        # nested inside methods).
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sym.children.append(_build_symbol(child, qualname, in_class=True))
            elif isinstance(child, ast.ClassDef):
                sym.children.append(_build_symbol(child, qualname, in_class=False))
        return sym

    # FunctionDef / AsyncFunctionDef
    return SymbolInfo(
        kind="method" if in_class else "func",
        name=name,
        qualname=qualname,
        line=node.lineno,
        params=_format_params(node.args),
        calls=_collect_calls(node.body),
    )


def _extract_imports(tree: ast.Module) -> list[ImportInfo]:
    imports: list[ImportInfo] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(kind="imports", module=alias.name, line=node.lineno))
        elif isinstance(node, ast.ImportFrom):
            # Preserve explicit relative-import dots so the resolver can anchor them.
            module = ("." * node.level) + (node.module or "")
            names = [a.name for a in node.names]
            imports.append(
                ImportInfo(kind="imports_from", module=module, names=names, line=node.lineno)
            )
    return imports


def extract_python(rel_path: str, source: str) -> FileInfo:
    """Parse ``source`` (already read) of a ``.py`` file at ``rel_path``.

    Raises :class:`SyntaxError` to the caller, which records the file as a bare module
    node so a single unparseable file never aborts the whole run.
    """
    tree = ast.parse(source)
    docstring = ast.get_docstring(tree, clean=True) or ""
    summary = docstring.strip().splitlines()[0].strip() if docstring.strip() else ""

    symbols: list[SymbolInfo] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(_build_symbol(node, "", in_class=False))
        elif isinstance(node, ast.ClassDef):
            symbols.append(_build_symbol(node, "", in_class=False))

    return FileInfo(
        path=rel_path,
        lang="python",
        kind="module",
        summary=summary,
        imports=_extract_imports(tree),
        symbols=symbols,
    )
