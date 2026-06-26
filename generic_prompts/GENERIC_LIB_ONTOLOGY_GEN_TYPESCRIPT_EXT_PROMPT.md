# Generic Lib Prompt: TypeScript/React Structural Extractor (zero-dep regex scanner)

## Purpose

Produce one `FileInfo` per `.ts`/`.tsx`/`.js`/… file — capturing imports
(including relative re-exports), classes, functions, arrow-function consts, React
components, interface declarations, and type-alias declarations — using a
**self-contained, stdlib-only line/regex scanner**, no Node/npm runtime and no
compiled parser dependency.

## Reusable Pattern

- **Zero runtime dependency is the toolchain choice.** A heavier parser
  (`ts-morph`, a compiled `tree-sitter` binding) gives richer fidelity but forces
  a JS/TS toolchain into a repo/CI that may have none. For a module/file +
  class/func/method contract granularity, a line scanner over export declarations
  is sufficient — and the function signature is the seam where a richer backend can
  be slotted later.
- **Multiline-anchored regexes** for each declaration form: `class … extends`,
  `function`, `const X = (…) =>` / `= async (…) =>`, `interface … extends`,
  `type X = …`. Imports via `import … from '…'` and bare `import '…'`; re-exports
  via `export … from '…'` → `references`.
- **Depth-aware comma splitting** for base lists and params: a comma inside
  `<>`/`()`/`[]`/`{}` is NOT a split point, so `Map<K, V>, Baz` splits correctly.
  Strip generics (`Foo<T>` → `Foo`) and param type-annotations/defaults (keep the
  name only).
- **Dedup symbols by name** within a file (the scanner can match the same name in
  multiple forms).
- **Accepted fidelity trade:** strings/block comments are not fully tokenized;
  exotic constructs may be missed. Documented, deliberate, for the zero-dep win.

## Algorithm

1. `lang = javascript if .js/.jsx/.mjs/.cjs else typescript`.
2. Collect imports (from + bare), dedup by module; collect re-export targets.
3. For each declaration regex, find all matches; for each, compute the 1-based line
   (`source.count("\n", 0, pos) + 1`), parse params/bases via the depth-aware
   splitter, and add a deduped `SymbolInfo` of the right kind.
4. Return `FileInfo(path, lang, kind="file", summary, imports, symbols, reexports)`.

## Code Template (stdlib only)

```python
#!/usr/bin/env python3
"""TypeScript/React structural extractor — zero-dependency regex/line scanner."""
from __future__ import annotations

import re

from .model import FileInfo, ImportInfo, SymbolInfo

_JS_EXTS = (".js", ".jsx", ".mjs", ".cjs")

_RE_IMPORT_FROM = re.compile(r"""^\s*import\b[^;'"]*?\bfrom\s*['"]([^'"]+)['"]""", re.MULTILINE)
_RE_IMPORT_BARE = re.compile(r"""^\s*import\s*['"]([^'"]+)['"]""", re.MULTILINE)
_RE_REEXPORT = re.compile(r"""^\s*export\b[^;'"]*?\bfrom\s*['"]([^'"]+)['"]""", re.MULTILINE)
_RE_CLASS = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"
    r"(?:\s+extends\s+([A-Za-z_$][\w$.]*))?", re.MULTILINE)
_RE_FUNCTION = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(([^)]*)\)",
    re.MULTILINE)
_RE_ARROW_CONST = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?const\s+([A-Za-z_$][\w$]*)\s*(?::\s*[^=]+)?"
    r"=\s*(?:async\s*)?(?:\(([^)]*)\)|[A-Za-z_$][\w$]*)\s*=>", re.MULTILINE)
_RE_INTERFACE = re.compile(
    r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)(?:\s+extends\s+([^{]+?))?(?=\s*\{|\s*$)",
    re.MULTILINE)
_RE_TYPE_ALIAS = re.compile(
    r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)(?:\s*<[^>]*>)?\s*=(?!=)", re.MULTILINE)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _split_top_level_commas(raw: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in raw:
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            if cur.strip():
                parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def _parse_extends_bases(raw: str) -> list[str]:
    bases = []
    for part in _split_top_level_commas(raw):
        name = part.strip().split("<")[0].strip()
        if name and re.match(r"^[A-Za-z_$][\w$]*$", name):
            bases.append(name)
    return bases


def _split_params(raw: str) -> list[str]:
    out = []
    for part in _split_top_level_commas(raw):
        name = part.strip().split(":")[0].split("=")[0].strip().lstrip(".")
        if name:
            out.append(name)
    return out


def _summary(source: str) -> str:
    for line in source.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("/**") or s.startswith("/*"):
            return s.lstrip("/*").strip()
        if s.startswith("//"):
            return s.lstrip("/").strip()
        return ""
    return ""


def extract_typescript(rel_path: str, source: str) -> FileInfo:
    lang = "javascript" if rel_path.endswith(_JS_EXTS) else "typescript"
    imports, seen_i = [], set()
    for rx in (_RE_IMPORT_FROM, _RE_IMPORT_BARE):
        for m in rx.finditer(source):
            mod = m.group(1)
            if mod not in seen_i:
                seen_i.add(mod)
                imports.append(ImportInfo(kind="imports", module=mod, line=_line_of(source, m.start())))
    reexports = []
    for m in _RE_REEXPORT.finditer(source):
        if m.group(1) not in reexports:
            reexports.append(m.group(1))

    symbols, seen_s = [], set()

    def _add(kind, name, line, params, bases):
        if name in seen_s:
            return
        seen_s.add(name)
        symbols.append(SymbolInfo(kind=kind, name=name, qualname=name, line=line,
                                  params=params, bases=bases))

    for m in _RE_CLASS.finditer(source):
        _add("class", m.group(1), _line_of(source, m.start()), [], [m.group(2)] if m.group(2) else [])
    for m in _RE_FUNCTION.finditer(source):
        _add("func", m.group(1), _line_of(source, m.start()), _split_params(m.group(2)), [])
    for m in _RE_ARROW_CONST.finditer(source):
        _add("func", m.group(1), _line_of(source, m.start()), _split_params(m.group(2) or ""), [])
    for m in _RE_INTERFACE.finditer(source):
        raw = m.group(2) or ""
        _add("interface", m.group(1), _line_of(source, m.start()), [],
             _parse_extends_bases(raw) if raw.strip() else [])
    for m in _RE_TYPE_ALIAS.finditer(source):
        _add("type", m.group(1), _line_of(source, m.start()), [], [])

    return FileInfo(path=rel_path, lang=lang, kind="file", summary=_summary(source),
                    imports=imports, symbols=symbols, reexports=reexports)
```

## Adaptation Notes

- **Zero-dep is a control/supply-chain decision.** Choose this scanner when adding a
  JS/TS toolchain org-wide just to index a layer is not worth it. Keep
  `extract_typescript`'s signature as the seam so a `tree-sitter` backend can slot
  in later for richer call-graph fidelity.
- **Depth-aware comma splitting is shared** between base-lists and params — don't
  re-implement the nesting tracker in two places.
- **Document the fidelity trade.** A regex scanner misses exotic constructs and
  doesn't tokenize strings/comments; that is the accepted cost of zero deps and
  should be stated for downstream consumers.
- **Dedup symbols by name** so the multiple declaration regexes don't double-mint.
```
