# Generic Lib Prompt: Python Structural Extractor (stdlib `ast`)

## Purpose

Produce one `FileInfo` per `.py` file — capturing modules, classes,
functions/methods, imports, intra-file calls, and base classes — using only the
stdlib `ast`, zero third-party deps. It is the Python language-extractor that
feeds the shared assembler/renderer.

## Reusable Pattern

- **Module/class/function granularity, NOT per-statement.** This keeps the
  resulting index token-economical. Top-level functions and classes are captured;
  class bodies are recursed for methods and nested classes; function bodies are
  **not** recursed for nested `def` closures (low structural value, high token
  cost) — but their full subtree IS walked for `calls` so the call list is
  complete.
- **Raw file-local names for `bases` and `calls`.** The extractor records simple
  name strings; the assembler resolves them to node ids. `obj.bar()` / `self.bar()`
  → `bar` (the attribute name) so a same-class method call resolves.
- **Stable qualnames** (`Outer.method`) as symbol ids.
- **Preserve relative-import dots** (`from . import x` → module `"."`) so the
  resolver can anchor relative imports.
- **First docstring line as the file summary.**
- **Raise `SyntaxError` to the caller**, which records a bare module node — one
  unparseable file never aborts the whole run.

## Algorithm

1. `ast.parse(source)`; take the first docstring line as `summary`.
2. Walk top-level body: build a `SymbolInfo` tree for each `FunctionDef`/
   `AsyncFunctionDef`/`ClassDef`.
   - class: collect `bases`; recurse body for methods (in_class=True) and nested
     classes;
   - function: format params (posonly, args, `*vararg`, kwonly, `**kwarg`), collect
     callee names from the full body via `ast.walk`.
3. Extract imports: `Import` → kind `imports` per alias; `ImportFrom` → kind
   `imports_from` with `("." * level) + (module or "")` and member names.
4. Return `FileInfo(path, lang="python", kind="module", summary, imports, symbols)`.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""Python structural extractor — stdlib ast only, zero third-party deps."""
from __future__ import annotations

import ast

from .model import FileInfo, ImportInfo, SymbolInfo


def _format_params(args: ast.arguments) -> list[str]:
    params = [a.arg for a in getattr(args, "posonlyargs", [])]
    params += [a.arg for a in args.args]
    if args.vararg:
        params.append(f"*{args.vararg.arg}")
    params += [a.arg for a in args.kwonlyargs]
    if args.kwarg:
        params.append(f"**{args.kwarg.arg}")
    return params


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _base_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _collect_calls(body: list[ast.stmt]) -> list[str]:
    seen, names = set(), []
    for stmt in body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Call):
                n = _call_name(sub.func)
                if n and n not in seen:
                    seen.add(n); names.append(n)
    return names


def _build_symbol(node, qual_prefix: str, *, in_class: bool) -> SymbolInfo:
    name = node.name
    qualname = f"{qual_prefix}.{name}" if qual_prefix else name
    if isinstance(node, ast.ClassDef):
        bases = [b for b in (_base_name(b) for b in node.bases) if b is not None]
        sym = SymbolInfo(kind="class", name=name, qualname=qualname, line=node.lineno, bases=bases)
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sym.children.append(_build_symbol(child, qualname, in_class=True))
            elif isinstance(child, ast.ClassDef):
                sym.children.append(_build_symbol(child, qualname, in_class=False))
        return sym
    return SymbolInfo(kind="method" if in_class else "func", name=name, qualname=qualname,
                      line=node.lineno, params=_format_params(node.args),
                      calls=_collect_calls(node.body))


def _extract_imports(tree: ast.Module) -> list[ImportInfo]:
    imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(kind="imports", module=alias.name, line=node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = ("." * node.level) + (node.module or "")
            imports.append(ImportInfo(kind="imports_from", module=module,
                                      names=[a.name for a in node.names], line=node.lineno))
    return imports


def extract_python(rel_path: str, source: str) -> FileInfo:
    tree = ast.parse(source)  # raises SyntaxError to caller → bare module node
    doc = ast.get_docstring(tree, clean=True) or ""
    summary = doc.strip().splitlines()[0].strip() if doc.strip() else ""
    symbols = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(_build_symbol(node, "", in_class=False))
    return FileInfo(path=rel_path, lang="python", kind="module", summary=summary,
                    imports=_extract_imports(tree), symbols=symbols)
```

## Adaptation Notes

- **Granularity is a deliberate token trade.** Module/class/function only; do not
  recurse closures for symbols. Keep the full-body walk for `calls` so the call
  list stays complete even though nested defs aren't minted.
- **Emit raw names, let the assembler resolve.** The extractor's job is extraction,
  not cross-file resolution — keep that separation.
- **Let `SyntaxError` propagate.** The orchestrator catches it and records a bare
  node; swallowing it here would lose the signal that a file didn't parse.
```
