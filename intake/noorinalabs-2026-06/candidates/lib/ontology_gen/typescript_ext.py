#!/usr/bin/env python3
"""TypeScript / React structural extractor — zero-dependency, regex/line based (#855).

Toolchain choice (flagged to the #855 owner as a contract-adjacent decision):
``ts-morph`` (a Node/npm runtime) and ``tree-sitter-typescript`` (a compiled pip dep)
were both considered per the issue. This module uses neither — a self-contained,
stdlib-only line scanner — because:

* **Zero runtime dep** is the lightest possible toolchain (the issue's stated
  preference) and matches the eval's control / supply-chain argument against taking a
  third-party graph tool (#854). The parent repo's CI installs no JS/TS toolchain, so a
  pip/npm dep would have to be added org-wide just to index a layer the parent doesn't
  even have.
* The contract granularity is **module/file + class/func/method**, not per-call-
  expression precision — well within reach of a line scanner over export declarations.

A ``tree_sitter_typescript`` backend can be slotted behind :func:`extract_typescript`
later (the function signature is the seam) if/when richer call-graph fidelity is wanted;
that is explicitly out of scope for #855's pilot.

Captured: imports (incl. relative re-exports → ``references``), exported & top-level
classes, functions, arrow-function consts, React components (PascalCase consts),
interface declarations, and type-alias declarations (#870 — ~82 previously-invisible
isnad-graph pilot decls).
Block comments / strings are not fully tokenized — this is a pragmatic scanner, not a
parser — so exotic constructs may be missed; that is an accepted fidelity trade for
zero deps and is documented for #856/#1128.
"""

from __future__ import annotations

import re

from .model import FileInfo, ImportInfo, SymbolInfo

_JS_EXTS = (".js", ".jsx", ".mjs", ".cjs")

# import ... from '...'  /  import '...'
_RE_IMPORT_FROM = re.compile(r"""^\s*import\b[^;'"]*?\bfrom\s*['"]([^'"]+)['"]""", re.MULTILINE)
_RE_IMPORT_BARE = re.compile(r"""^\s*import\s*['"]([^'"]+)['"]""", re.MULTILINE)
# export ... from '...'  (re-export → references edge target)
_RE_REEXPORT = re.compile(r"""^\s*export\b[^;'"]*?\bfrom\s*['"]([^'"]+)['"]""", re.MULTILINE)

_RE_CLASS = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"
    r"(?:\s+extends\s+([A-Za-z_$][\w$.]*))?",
    re.MULTILINE,
)
_RE_FUNCTION = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*"
    r"([A-Za-z_$][\w$]*)\s*\(([^)]*)\)",
    re.MULTILINE,
)
# const Foo = (...) =>   /   const Foo = async (...) =>   /   const Foo = function
_RE_ARROW_CONST = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?const\s+([A-Za-z_$][\w$]*)\s*"
    r"(?::\s*[^=]+)?=\s*(?:async\s*)?(?:\(([^)]*)\)|[A-Za-z_$][\w$]*)\s*=>",
    re.MULTILINE,
)
# interface Foo [extends Bar, Baz] {   (#870)
_RE_INTERFACE = re.compile(
    r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)"
    r"(?:\s+extends\s+([^{]+?))?(?=\s*\{|\s*$)",
    re.MULTILINE,
)
# type Foo[<...>] = ...   (type-alias declaration, not a type-guard or parameter)  (#870)
_RE_TYPE_ALIAS = re.compile(
    r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)(?:\s*<[^>]*>)?\s*=(?!=)",
    re.MULTILINE,
)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _split_top_level_commas(raw: str) -> list[str]:
    """Split ``raw`` on commas that sit at bracket-nesting depth 0.

    Commas nested inside ``<>`` / ``()`` / ``[]`` / ``{}`` are NOT split points, so a
    base list like ``Bar<Map<K, V>>, Baz`` splits into ``["Bar<Map<K, V>>", "Baz"]``
    rather than naively at the inner ``, `` (#887). Empty / whitespace-only segments
    are dropped. Shared by both the ``extends``/``implements`` base-list parser and the
    parameter splitter so neither re-implements the depth tracking.
    """
    parts: list[str] = []
    depth = 0
    current = ""
    for ch in raw:
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            if current.strip():
                parts.append(current)
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current)
    return parts


def _parse_extends_bases(raw: str) -> list[str]:
    """Return base names from a raw ``extends A, B<T>`` clause (drops generics).

    Splits on top-level commas (depth-aware, so a comma inside a nested generic such as
    ``Map<K, V>`` does not split — #887) and strips generic type-parameters so
    ``Foo<T>`` → ``Foo``.
    """
    bases: list[str] = []
    for part in _split_top_level_commas(raw):
        name = part.strip().split("<")[0].strip()
        if name and re.match(r"^[A-Za-z_$][\w$]*$", name):
            bases.append(name)
    return bases


def _split_params(raw: str) -> list[str]:
    out: list[str] = []
    for part in _split_top_level_commas(raw):
        # Keep just the parameter name (drop type annotations / defaults).
        name = part.strip().split(":")[0].split("=")[0].strip()
        name = name.lstrip(".")  # rest params ...args
        if name:
            out.append(name)
    return out


def _summary(source: str) -> str:
    """First line of a leading ``/** ... */`` or ``//`` banner comment, if any."""
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("/**") or stripped.startswith("/*"):
            body = stripped.lstrip("/*").strip()
            return body if body else ""
        if stripped.startswith("//"):
            return stripped.lstrip("/").strip()
        return ""
    return ""


def extract_typescript(rel_path: str, source: str) -> FileInfo:
    lang = "javascript" if rel_path.endswith(_JS_EXTS) else "typescript"

    imports: list[ImportInfo] = []
    seen_imports: set[str] = set()
    for m in _RE_IMPORT_FROM.finditer(source):
        mod = m.group(1)
        if mod not in seen_imports:
            seen_imports.add(mod)
            imports.append(ImportInfo(kind="imports", module=mod, line=_line_of(source, m.start())))
    for m in _RE_IMPORT_BARE.finditer(source):
        mod = m.group(1)
        if mod not in seen_imports:
            seen_imports.add(mod)
            imports.append(ImportInfo(kind="imports", module=mod, line=_line_of(source, m.start())))

    reexports: list[str] = []
    for m in _RE_REEXPORT.finditer(source):
        target = m.group(1)
        if target not in reexports:
            reexports.append(target)

    symbols: list[SymbolInfo] = []
    seen_symbols: set[str] = set()

    def _add(kind: str, name: str, line: int, params: list[str], bases: list[str]) -> None:
        if name in seen_symbols:
            return
        seen_symbols.add(name)
        symbols.append(
            SymbolInfo(kind=kind, name=name, qualname=name, line=line, params=params, bases=bases)
        )

    for m in _RE_CLASS.finditer(source):
        name = m.group(1)
        base = m.group(2)
        _add("class", name, _line_of(source, m.start()), [], [base] if base else [])
    for m in _RE_FUNCTION.finditer(source):
        name = m.group(1)
        _add("func", name, _line_of(source, m.start()), _split_params(m.group(2)), [])
    for m in _RE_ARROW_CONST.finditer(source):
        name = m.group(1)
        params = _split_params(m.group(2) or "")
        _add("func", name, _line_of(source, m.start()), params, [])
    for m in _RE_INTERFACE.finditer(source):
        name = m.group(1)
        raw_extends = m.group(2) or ""
        bases = _parse_extends_bases(raw_extends) if raw_extends.strip() else []
        _add("interface", name, _line_of(source, m.start()), [], bases)
    for m in _RE_TYPE_ALIAS.finditer(source):
        name = m.group(1)
        _add("type", name, _line_of(source, m.start()), [], [])

    return FileInfo(
        path=rel_path,
        lang=lang,
        kind="file",
        summary=_summary(source),
        imports=imports,
        symbols=symbols,
        reexports=reexports,
    )
